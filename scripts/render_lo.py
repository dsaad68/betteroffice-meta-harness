#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click>=8.1"]
# ///
# harness-component: scripts
# harness-version: 1.0.0
"""Render the reference images with LibreOffice via pptx-pdf into decks/<id>/lo-img/NN.png."""

from __future__ import annotations

import click
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import DPI, FONT_DIR, PPTX_PDF, deck_dir, slide_name


def render(deck_id: str) -> None:
    d = deck_dir(deck_id)
    out = d / "lo-img"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    if not PPTX_PDF.exists():
        sys.exit(f"pptx-pdf binary not found at {PPTX_PDF}")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [str(PPTX_PDF), str(d / "source.pptx"), "--png", tmp, "--dpi", str(DPI), "--hidden", "--font-dir", str(FONT_DIR)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        (d / "lo-log.txt").write_text(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            sys.exit(f"{deck_id}: pptx-pdf failed ({proc.returncode}); see lo-log.txt")
        for png in sorted(Path(tmp).glob("slide-*.png")):
            n = int(re.search(r"(\d+)", png.stem).group(1))
            shutil.move(str(png), out / f"{slide_name(n)}.png")
    print(f"{deck_id}: {len(list(out.glob('*.png')))} LibreOffice image(s)")


@click.command(help=__doc__)
@click.argument("deck_id")
def main(deck_id: str) -> None:
    render(deck_id)


if __name__ == "__main__":
    main()
