#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click>=8.1"]
# ///
# harness-component: scripts
# harness-version: 1.0.0
"""Run the deterministic stages for one deck: register, render both sides, extract XML, diff."""

from __future__ import annotations

import click
import subprocess
import sys
from pathlib import Path

from common import DECKS, slug

SCRIPTS = Path(__file__).resolve().parent


def step(name: str, *args: str) -> None:
    """Run a stage as its own uv script, so it resolves the dependencies it declares.

    Not `sys.executable`: this script's environment only carries what its own header asks for,
    which is not what diff.py or collect.py need."""
    print(f"== {name} {' '.join(args)}", flush=True)
    subprocess.run(["uv", "run", "--script", str(SCRIPTS / name), *args], check=True)


@click.command(help=__doc__)
@click.argument("target")
@click.option("--id", "deck_id_opt", help="deck id (default: slug of the file name)")
@click.option("--source-url", default="", help="where the deck came from")
@click.option("--skip-lo", is_flag=True, help="reuse existing LibreOffice renders")
def main(target: str, deck_id_opt: str | None, source_url: str, skip_lo: bool) -> None:
    target = Path(target)
    if target.suffix.lower() == ".pptx" and target.exists():
        deck_id = deck_id_opt or slug(target.name)
        step("add_deck.py", str(target), "--id", deck_id, "--source-url", source_url)
    else:
        deck_id = target
        if not (DECKS / deck_id / "source.pptx").exists():
            sys.exit(f"unknown deck id {deck_id}")
    if not (skip_lo and (DECKS / deck_id / "lo-img").exists()):
        step("render_lo.py", deck_id)
    step("render_bo.py", deck_id)
    step("extract_xml.py", deck_id)
    step("diff.py", deck_id)
    (DECKS / deck_id / "reports").mkdir(exist_ok=True)
    print(f"done: {deck_id}")


if __name__ == "__main__":
    main()
