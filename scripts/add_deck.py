#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click>=8.1"]
# ///
# harness-component: scripts
# harness-version: 1.0.0
"""Register a deck: copy it to decks/<id>/source.pptx and write meta.json."""

from __future__ import annotations

import click
import shutil
import zipfile
from pathlib import Path

from common import DECKS, save_meta, sha256, slug


def slide_count(path: Path) -> int:
    with zipfile.ZipFile(path) as z:
        return sum(1 for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))


@click.command(help=__doc__)
@click.argument("pptx", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--id", "deck_id_opt", help="deck id (default: slug of the file name)")
@click.option("--source-url", default="", help="where the deck came from")
def main(pptx: Path, deck_id_opt: str | None, source_url: str) -> None:
    deck_id = deck_id_opt or slug(pptx.name)
    target = DECKS / deck_id
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pptx, target / "source.pptx")
    meta = {
        "id": deck_id,
        "original_name": pptx.name,
        "source_url": source_url,
        "sha256": sha256(pptx),
        "slides": slide_count(pptx),
        "size_bytes": pptx.stat().st_size,
    }
    save_meta(deck_id, meta)
    print(f"{deck_id}: {meta['slides']} slide(s) -> {target.relative_to(DECKS.parent.parent)}")


if __name__ == "__main__":
    main()
