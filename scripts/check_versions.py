#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click>=8.1"]
# ///
# harness-component: scripts
# harness-version: 1.0.0
"""Check that every component's declared version matches harness.lock.toml."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent.parent


def declared_frontmatter(path: Path) -> str | None:
    text = path.read_text()
    if not text.startswith("---\n"):
        return None
    head = text[4 : text.index("\n---\n", 3)]
    found = re.search(r"^version:\s*(\S+)", head, re.M)
    return found.group(1) if found else None


def declared_header(path: Path) -> str | None:
    found = re.search(r"^# harness-version:\s*(\S+)", path.read_text(), re.M)
    return found.group(1) if found else None


@click.command(help=__doc__)
def main() -> None:
    lock = tomllib.loads((ROOT / "harness.lock.toml").read_text())
    problems: list[str] = []

    for kind, folder, reader, pattern in (
        ("skills", "skills", declared_frontmatter, "*/SKILL.md"),
        ("agents", "agents", declared_frontmatter, "*.md"),
    ):
        expected = lock[kind]
        seen = set()
        for path in sorted((ROOT / folder).glob(pattern)):
            name = path.parent.name if pattern.startswith("*/") else path.stem
            seen.add(name)
            if name not in expected:
                problems.append(f"{path.relative_to(ROOT)}: not in harness.lock.toml [{kind}]")
            elif (version := reader(path)) != expected[name]:
                problems.append(
                    f"{path.relative_to(ROOT)}: declares {version}, lock says {expected[name]}"
                )
        for missing in sorted(set(expected) - seen):
            problems.append(f"[{kind}] {missing}: in the lock but not on disk")

    for path in sorted((ROOT / "scripts").glob("*.py")):
        version = declared_header(path)
        if version is None:
            problems.append(f"{path.relative_to(ROOT)}: no `# harness-version:` header")
        elif version != lock["scripts"]["all"]:
            problems.append(
                f"{path.relative_to(ROOT)}: declares {version}, lock says {lock['scripts']['all']}"
            )

    if problems:
        for problem in problems:
            print(f"  {problem}")
        sys.exit(f"{len(problems)} version problem(s)")
    print(f"release {lock['release']}: every component matches the lock")


if __name__ == "__main__":
    main()
