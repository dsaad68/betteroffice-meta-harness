#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click>=8.1"]
# ///
# harness-component: scripts
# harness-version: 1.3.0
"""Query a fix run's ORDER.toml: dependencies, what is ready, the merge order, the issue body."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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
    scope: str = ""
    commit: str = ""

    @property
    def hard(self) -> list[str]:
        return [*self.needs, *self.repairs]

    @property
    def edges(self) -> list[str]:
        """Everything that should come before this one, hard or advisory."""
        return [*self.needs, *self.repairs, *self.after]

    def label(self) -> str:
        """The PR's name: the conventional-commit title when the run declares a scope."""
        pr = self.meta.get("pr")
        name = self.title or self.id
        if self.scope and self.title:
            kind = self.commit or ("feat" if self.kind == "feature" else "fix")
            name = f"`{kind}({self.scope}): {name}`"
        return f"{name}{f' — #{pr}' if pr else ''}"


def load(path: Path) -> tuple[dict, dict[str, Entry]]:
    if not path.exists():
        sys.exit(f"{path} not found")
    raw = tomllib.loads(path.read_text())
    entries: dict[str, Entry] = {}
    scope = raw.get("scope", "")
    for kind in ("fix", "feature"):
        for item in raw.get(kind, []):
            item = dict(item)
            ident = item.pop("id", None)
            if ident is None:
                sys.exit(f"an [[{kind}]] entry has no id")
            if ident in entries:
                sys.exit(f"duplicate id {ident!r}: ids are unique across [[fix]] and [[feature]]")
            meta = item.pop("meta", {})
            fields = {k: v for k, v in item.items()
                      if k in Entry.__annotations__ and k != "scope"}
            entries[ident] = Entry(id=ident, kind=kind, meta=meta, scope=scope, **fields)
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


def set_status(path: Path, ident: str, status: str) -> None:
    """Rewrite one entry's status line in place.

    Line-based on purpose: tomllib cannot write, and a round trip through a TOML writer would
    reflow the file and drop every comment in it — and the reasons are the point of this file.
    """
    lines = path.read_text().split("\n")
    current = None
    for index, line in enumerate(lines):
        if match := re.match(r'^id = "(.+)"$', line):
            current = match.group(1)
        elif current == ident and re.match(r"^status = ", line):
            lines[index] = f'status = "{status}"'
            path.write_text("\n".join(lines))
            return
    sys.exit(f"{ident}: no status line found to update")


def gh_states(repo: str) -> dict[int, str]:
    if not shutil.which("gh"):
        sys.exit("gh not on PATH; install it or reconcile by hand")
    result = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--state", "all", "--limit", "200",
         "--json", "number,state"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"gh pr list failed: {result.stderr.strip()}")
    return {pr["number"]: pr["state"] for pr in json.loads(result.stdout)}


@main.command(help="Reconcile statuses against GitHub, and reclaim merged worktrees.")
@click.option("--repo", required=True, help="owner/name to ask about the pull requests")
@click.option("--remove-worktrees", is_flag=True, help="run `wt remove` on merged branches")
@opt
def sync(repo: str, remove_worktrees: bool, path: Path | None) -> None:
    """The plan records what this session did; GitHub records what happened. They diverge the
    moment a maintainer merges something, and `ready` then hides work that is already unblocked."""
    order = order_file(path)
    _, entries = load(order)
    states = gh_states(repo)

    merged, closed, worktrees = [], [], []
    seen_branches: set[str] = set()
    for entry in entries.values():
        pr = entry.meta.get("pr")
        if not pr or pr not in states:
            continue
        state = states[pr]
        if state == "MERGED" and entry.status != "merged":
            set_status(order, entry.id, "merged")
            merged.append((entry, pr))
        elif state == "CLOSED" and entry.status not in ("blocked", "merged"):
            # Closed without merging is a decision, not a status change: superseded, rejected,
            # or split. Report it and let a person say which.
            closed.append((entry, pr))
        # Two entries can share a pull request when one change closes both, so dedupe.
        if state == "MERGED" and entry.branch and entry.branch not in seen_branches:
            seen_branches.add(entry.branch)
            worktrees.append((entry.branch, pr))

    for entry, pr in merged:
        print(f"  merged   {entry.id} (#{pr})")
    for entry, pr in closed:
        print(f"  CLOSED   {entry.id} (#{pr}) — closed unmerged, still `{entry.status}`; decide by hand")
    if not merged and not closed:
        print("  nothing to reconcile")

    if not worktrees:
        return
    print()
    for branch, pr in worktrees:
        if remove_worktrees:
            result = subprocess.run(["wt", "remove", branch], capture_output=True, text=True)
            ok = result.returncode == 0
            # wt prints the reason first and a "try this" hint after; the reason is what matters.
            said = (result.stderr or result.stdout).strip().splitlines()
            why = next((line.lstrip("✗ ").strip() for line in said if not line.startswith("↳")), "")
            print(f"  {'removed ' if ok else 'kept    '} {branch} (#{pr})"
                  + ("" if ok else f" — {why or 'wt remove failed'}"))
        else:
            print(f"  wt remove {branch}   # merged as #{pr}")
    if not remove_worktrees:
        print("\n  each worktree holds 15-20 GB of build cache; --remove-worktrees to reclaim them")


@main.command(help="The merge-order issue body, rendered.")
@opt
def issue(path: Path | None) -> None:
    raw, entries = load(order_file(path))
    # Only what is actually open: an entry with no pull request is backlog, not a merge step.
    sequence = [e for e in ordered(entries)
                if e.status not in ("blocked", "merged") and e.meta.get("pr")]
    print(f"{len(sequence)} pull requests are open against this run and several of them interact. "
          "This is the order I would merge them in and why.\n")
    print("Generated from `ORDER.toml`; edit that rather than this issue.\n")
    if base := raw.get("base"):
        print(f"Every branch cuts from `{base[:12]}` unless a step below names something "
              "it depends on, in which case it is stacked on that branch instead.\n")
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
