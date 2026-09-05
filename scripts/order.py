#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click>=8.1"]
# ///
# harness-component: scripts
# harness-version: 1.0.0
"""Query a fix run's ORDER.toml: dependencies, what is ready, the merge order, the issue body."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import click

STATUSES = ("todo", "claimed", "drafted", "filed", "merged", "blocked")
HARD = ("needs", "repairs")


@dataclass
class Entry:
    id: str
    kind: str
    title: str = ""
    status: str = "todo"
    branch: str = ""
    reason: str = ""
    needs: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def hard(self) -> list[str]:
        return [*self.needs, *self.repairs]

    @property
    def edges(self) -> list[str]:
        """Everything that should come before this one, hard or advisory."""
        return [*self.needs, *self.repairs, *self.after]

    def label(self) -> str:
        pr = self.meta.get("pr")
        return f"{self.title or self.id}{f' — #{pr}' if pr else ''}"


def load(path: Path) -> tuple[dict, dict[str, Entry]]:
    if not path.exists():
        sys.exit(f"{path} not found")
    raw = tomllib.loads(path.read_text())
    entries: dict[str, Entry] = {}
    for kind in ("fix", "feature"):
        for item in raw.get(kind, []):
            item = dict(item)
            ident = item.pop("id", None)
            if ident is None:
                sys.exit(f"an [[{kind}]] entry has no id")
            if ident in entries:
                sys.exit(f"duplicate id {ident!r}: ids are unique across [[fix]] and [[feature]]")
            meta = item.pop("meta", {})
            entries[ident] = Entry(id=ident, kind=kind, meta=meta,
                                   **{k: v for k, v in item.items() if k in Entry.__annotations__})
    return raw, entries


def problems(entries: dict[str, Entry]) -> list[str]:
    found: list[str] = []
    for entry in entries.values():
        if entry.status not in STATUSES:
            found.append(f"{entry.id}: status {entry.status!r} is not one of {', '.join(STATUSES)}")
        for name in (*entry.edges, *entry.supersedes):
            if name not in entries:
                found.append(f"{entry.id}: refers to unknown id {name!r}")
        if entry.status == "blocked" and not entry.reason:
            found.append(f"{entry.id}: blocked without a reason")
    found.extend(f"dependency cycle: {' -> '.join(cycle)}" for cycle in cycles(entries))
    return found


def cycles(entries: dict[str, Entry]) -> list[list[str]]:
    seen: dict[str, int] = {}
    out: list[list[str]] = []

    def walk(ident: str, trail: list[str]) -> None:
        if seen.get(ident) == 1:
            out.append([*trail[trail.index(ident):], ident])
            return
        if seen.get(ident) == 2:
            return
        seen[ident] = 1
        for name in entries[ident].edges:
            if name in entries:
                walk(name, [*trail, ident])
        seen[ident] = 2

    for ident in entries:
        walk(ident, [])
    return out


def ordered(entries: dict[str, Entry]) -> list[Entry]:
    """Topological order, ties broken by hard-dependency count then id, so it is stable."""
    done: list[Entry] = []
    placed: set[str] = set()
    remaining = dict(entries)
    while remaining:
        free = [e for e in remaining.values()
                if all(n in placed or n not in entries for n in e.edges)]
        if not free:  # a cycle; emit the rest in a stable order so output is still useful
            free = sorted(remaining.values(), key=lambda e: e.id)[:1]
        free.sort(key=lambda e: (len(e.hard), e.id))
        for entry in free:
            done.append(entry)
            placed.add(entry.id)
            remaining.pop(entry.id)
    return done


def transitive(entries: dict[str, Entry], ident: str, fields: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    stack = [n for f in fields for n in getattr(entries[ident], f)]
    while stack:
        name = stack.pop(0)
        if name in out or name not in entries:
            continue
        out.append(name)
        stack.extend(n for f in fields for n in getattr(entries[name], f))
    return out


def order_file(path: Path | None) -> Path:
    return path or Path("ORDER.toml")


opt = click.option("--file", "path", type=click.Path(path_type=Path), default=None,
                   help="ORDER.toml to read (default: ./ORDER.toml)")


@click.group(help=__doc__)
def main() -> None: ...


@main.command("list", help="What is in the run, and where each entry stands.")
@opt
def list_(path: Path | None) -> None:
    _, entries = load(order_file(path))
    width = max((len(e.id) for e in entries.values()), default=0)
    for entry in ordered(entries):
        marks = " ".join(x for x in (f"#{entry.meta['pr']}" if entry.meta.get("pr") else "",
                                     entry.branch) if x)
        print(f"  {entry.status:8} {entry.id:{width}}  {marks}")
    print(f"\n{len(entries)} entr(ies)")


@main.command(help="What an entry needs, directly and transitively.")
@click.argument("ident")
@opt
def deps(ident: str, path: Path | None) -> None:
    _, entries = load(order_file(path))
    if ident not in entries:
        sys.exit(f"unknown id {ident!r}")
    entry = entries[ident]
    for name, values in (("needs", entry.needs), ("repairs", entry.repairs),
                         ("after", entry.after), ("supersedes", entry.supersedes)):
        if values:
            print(f"  {name:11} {', '.join(values)}")
    indirect = [n for n in transitive(entries, ident, HARD) if n not in entry.hard]
    if indirect:
        print(f"  {'via those':11} {', '.join(indirect)}")
    if not entry.edges and not entry.supersedes:
        print("  nothing: this can merge on its own")


@main.command("blocked-by", help="What is waiting on this entry.")
@click.argument("ident")
@opt
def blocked_by(ident: str, path: Path | None) -> None:
    _, entries = load(order_file(path))
    if ident not in entries:
        sys.exit(f"unknown id {ident!r}")
    for entry in ordered(entries):
        why = [f for f in ("needs", "repairs", "after") if ident in getattr(entry, f)]
        if why:
            print(f"  {entry.id}  ({', '.join(why)})")


@main.command(help="Entries whose hard dependencies have all merged.")
@opt
def ready(path: Path | None) -> None:
    _, entries = load(order_file(path))
    for entry in ordered(entries):
        if entry.status in ("merged", "blocked"):
            continue
        if all(entries[n].status == "merged" for n in entry.hard if n in entries):
            print(f"  {entry.status:8} {entry.id}")


@main.command(help="The merge order, topologically sorted.")
@opt
def plan(path: Path | None) -> None:
    _, entries = load(order_file(path))
    sequence = [e for e in ordered(entries) if e.status != "blocked"]
    for step, entry in enumerate(sequence, 1):
        print(f"{step:3}. {entry.id}  [{entry.status}]")
        for name, values in (("needs", entry.needs), ("repairs", entry.repairs), ("after", entry.after)):
            if values:
                print(f"       {name}: {', '.join(values)}")
    for entry in ordered(entries):
        if entry.status == "blocked":
            print(f"     - {entry.id}  [blocked] {entry.reason}")


@main.command(help="Found and investigated, not yet worked on.")
@opt
def backlog(path: Path | None) -> None:
    _, entries = load(order_file(path))
    rank = {"high": 0, "medium": 1, "low": 2}
    todo = [e for e in entries.values() if e.status == "todo"]
    todo.sort(key=lambda e: (rank.get(e.meta.get("impact"), 3), rank.get(e.meta.get("effort"), 3)))
    width = max((len(e.id) for e in todo), default=0)
    for entry in todo:
        meta = entry.meta
        blockers = [n for n in entry.hard if n in entries and entries[n].status != "merged"]
        note = f"  waits on {', '.join(blockers)}" if blockers else ""
        print(f"  {entry.id:{width}}  {meta.get('impact','?'):6} {meta.get('effort','?'):6} "
              f"{meta.get('findings','?'):>3} finding(s){note}")
    print(f"\n{len(todo)} not yet worked on")


@main.command(help="Where an entry's investigation lives.")
@click.argument("ident")
@opt
def report(ident: str, path: Path | None) -> None:
    _, entries = load(order_file(path))
    if ident not in entries:
        sys.exit(f"unknown id {ident!r}")
    meta = entries[ident].meta
    for key in ("report", "solution"):
        if meta.get(key):
            print(f"  {key:9} {meta[key]}")
    for image in meta.get("evidence", []):
        print(f"  evidence  {image}")
    if not any(meta.get(k) for k in ("report", "solution", "evidence")):
        print("  no investigation recorded")


@main.command(help="Cycles, unknown ids, duplicate ids, bad statuses.")
@opt
def check(path: Path | None) -> None:
    _, entries = load(order_file(path))
    found = problems(entries)
    if found:
        for problem in found:
            print(f"  {problem}")
        sys.exit(f"{len(found)} problem(s)")
    print(f"{len(entries)} entr(ies), no problems")


@main.command(help="The merge-order issue body, rendered.")
@opt
def issue(path: Path | None) -> None:
    raw, entries = load(order_file(path))
    # Only what is actually open: an entry with no pull request is backlog, not a merge step.
    sequence = [e for e in ordered(entries) if e.status != "blocked" and e.meta.get("pr")]
    print(f"{len(sequence)} pull requests are open against this run and several of them interact. "
          "This is the order I would merge them in and why.\n")
    print("Generated from `ORDER.toml`; edit that rather than this issue.\n")
    if base := raw.get("base"):
        print(f"Every branch cuts from `{base[:12]}`.\n")
    print("---\n")
    for step, entry in enumerate(sequence, 1):
        print(f"### Step {step}. {entry.label()}\n")
        issue_no = entry.meta.get("issue")
        print(f"* **Issue:** {'#' + str(issue_no) if issue_no else '—'}")
        if entry.reason:
            print(f"* **Why here:** {entry.reason}")
        for name, values, phrase in (
            ("needs", entry.needs, "Depends on"),
            ("repairs", entry.repairs, "Repairs a regression from"),
            ("after", entry.after, "Sequenced after (no correctness link)"),
        ):
            if values:
                print(f"* **{phrase}:** " + ", ".join(
                    f"#{entries[v].meta['pr']}" if entries.get(v) and entries[v].meta.get("pr") else v
                    for v in values))
        if not entry.edges:
            print("* **Depends on:** nothing.")
        print()
    superseded = [(e, s) for e in ordered(entries) for s in e.supersedes]
    blocked = [e for e in ordered(entries) if e.status == "blocked" and not any(
        e.id == name for _, name in superseded)]
    if superseded or blocked:
        print("---\n\n### To close rather than merge\n")
        for entry, name in superseded:
            other = entries.get(name)
            ref = f"#{other.meta['pr']}" if other and other.meta.get("pr") else name
            note = f" {other.reason}" if other and other.reason else ""
            print(f"* **{ref}** — superseded by {entry.label()}.{note}")
        for entry in blocked:
            pr = entry.meta.get("pr")
            print(f"* **{f'#{pr}' if pr else entry.id}** — blocked: {entry.reason}")


if __name__ == "__main__":
    main()
