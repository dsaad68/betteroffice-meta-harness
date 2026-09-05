# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# harness-component: scripts
# harness-version: 1.0.0
"""Shared paths and helpers for the render improvement harness."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
ROOT = HARNESS.parent
DECKS = HARNESS / "decks"
ISSUES = HARNESS / "issues"
FONT_DIR = ROOT / "packages" / "fonts" / "assets"
CJK_DIR = ROOT / "packages" / "fonts-cjk" / "assets"
PPTX_PDF = Path.home() / "GitHub" / "pptx-pdf" / "target" / "release" / "pptx-pdf"
DPI = 96
SCALE = 1.0


def ensure_binding(engine: Path | None = None) -> None:
    """Put the locally built `betteroffice_pptx` on `sys.path`.

    It is compiled from the working repo by `setup_worktree.sh`, and a script's isolated uv
    environment does not load the venv's `.pth`, so it has to be found explicitly.
    `BETTEROFFICE_BINDING` overrides, which is how a candidate engine in another worktree is
    selected.

    uv *can* build this itself — `[tool.uv.sources]` works in inline script metadata, and a git or
    editable path source both resolve it. Neither is used here on purpose: the engine is the thing
    under measurement, so it changes per worktree and per run, and a source pinned in the script
    header cannot say "whichever worktree I am currently comparing". A path source would also have
    to be written relative to the script, and these scripts are deliberately copied into more than
    one repository. `llm.txt` records the git-source form for anyone with no local build."""
    if importlib.util.find_spec("betteroffice_pptx") is not None:
        return
    for candidate in (engine, os.environ.get("BETTEROFFICE_BINDING"),
                      ROOT / "bindings" / "python-pptx" / "python"):
        if candidate and (Path(candidate) / "betteroffice_pptx").is_dir():
            sys.path.insert(0, str(candidate))
            return


def slug(text: str) -> str:
    text = re.sub(r"\.pptx$", "", text, flags=re.I)
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:48].rstrip("-") or "deck"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def deck_dir(deck_id: str) -> Path:
    d = DECKS / deck_id
    if not (d / "source.pptx").exists():
        sys.exit(f"{deck_id}: no source.pptx under {d}; run add_deck.py first")
    return d


def load_meta(deck_id: str) -> dict:
    return json.loads((DECKS / deck_id / "meta.json").read_text())


def save_meta(deck_id: str, meta: dict) -> None:
    (DECKS / deck_id / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def slide_name(n: int) -> str:
    return f"{n:02d}"
