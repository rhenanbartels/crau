import logging
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import click
from scrapy.crawler import CrawlerProcess
from scrapy.utils.conf import arglist_to_dict

from .spider import CrauSpider
from .utils import get_urls_from_file, get_warc_uris, get_warc_record
from .version import __version__


def run_command(command):
    print(f"*** Running command: {command}")
    return subprocess.call(shlex.split(command))


def load_settings(ctx, param, value):
    settings = {
        "STATS_CLASS": "crau.utils.StdoutStatsCollector",
        "LOG_LEVEL": "CRITICAL",
        "HTTPCACHE_ENABLED": False,
    }
    settings.update(arglist_to_dict(value))
    return settings


@click.group()
@click.version_option(version=__version__)
def cli():
    # TODO: set prog_name to "crau"
    pass


@cli.command("list", help="List URIs of response records stored in a WARC file")
@click.argument("warc_filename")
def list_uris(warc_filename):
    for uri in get_warc_uris(warc_filename):
        click.echo(uri)


@cli.command("extract", help="Extract URL content from archive")
@click.argument("warc_filename")
@click.argument("uri")
@click.argument("output")
def extract_uri(warc_filename, uri, output):
    record = get_warc_record(warc_filename, uri)
    content = record.content_stream().read()

    # TODO: write it lazily
    if output == "-":
        sys.stdout.buffer.write(content)
    else:
        with open(output, mode="wb") as fobj:
            fobj.write(content)


@cli.command("archive", help="Archive a list of URLs to a WARC file")
@click.argument("warc_filename")
@click.option("--input-filename", "-i")
@click.option("--input-encoding", default="utf-8")
@click.option("--cache", is_flag=True)
@click.option("--max-depth", default=1)
@click.option("--log-level", required=False)
@click.option("--settings", "-s", multiple=True, default=[], callback=load_settings)
@click.argument("URLs", nargs=-1, required=False)
def archive(
    warc_filename,
    input_filename,
    input_encoding,
    cache,
    max_depth,
    log_level,
    settings,
    urls,
):

    if not input_filename and not urls:
        click.echo(
            "ERROR: at least one URL must be provided (or a file containing one per line).",
            err=True,
        )
        exit(1)

    if input_filename:
        if not Path(input_filename).exists():
            click.echo(f"ERROR: filename {input_filename} does not exist.", err=True)
            exit(2)
        urls = get_urls_from_file(input_filename, encoding=input_encoding)

    if cache:
        settings["HTTPCACHE_ENABLED"] = True

    if log_level:
        settings["LOG_LEVEL"] = log_level

    process = CrawlerProcess(settings=settings)
    process.crawl(
        CrauSpider, warc_filename=warc_filename, urls=urls, max_depth=max_depth
    )
    process.start()


@cli.command("play", help="Run a backend playing your archive")
@click.argument("warc_filename")
def play(warc_filename):
    filename = Path(warc_filename)
    if not filename.exists():
        click.echo(f"ERROR: filename {warc_filename} does not exist.", err=True)
        exit(2)

    full_filename = filename.absolute()
    collection_name = filename.name.split(".")[0]
    temp_dir = tempfile.mkdtemp()
    old_cwd = os.getcwd()

    os.chdir(temp_dir)
    run_command(f'wb-manager init "{collection_name}"')
    run_command(f'wb-manager add "{collection_name}" "{full_filename}"')
    run_command(f"wayback")
    shutil.rmtree(temp_dir)
    os.chdir(old_cwd)
