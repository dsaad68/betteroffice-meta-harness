#!/usr/bin/env bash
# Take a fresh clone of this repo to a working harness.
#
# Does four things: checks the tools, makes sure the three checkouts exist, installs the skills and
# agents where the agent runtime looks for them, and verifies nothing drifted.
#
#   ./scripts/bootstrap.sh                              what it would do, changing nothing
#   ./scripts/bootstrap.sh --install                    do it
#   ./scripts/bootstrap.sh --install --fork <url|path>  point at your fork
#
# Safe to re-run: it skips what is already in place and never overwrites a modified skill or agent
# without saying so. Decks are not part of this — they are third-party files, and you supply them.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="plan"
FORK="${BETTEROFFICE_FORK:-$HOME/GitHub/fork/betteroffice}"
PPTX_PDF="$HOME/GitHub/pptx-pdf"

while [ $# -gt 0 ]; do
  case "$1" in
    --install) MODE="install"; shift ;;
    --fork)    FORK="$2"; shift 2 ;;
    *) echo "usage: $0 [--install] [--fork <url|path>]" >&2; exit 2 ;;
  esac
done

step() { printf '\n== %s\n' "$1"; }
do_or_show() {
  if [ "$MODE" = "install" ]; then echo "+ $*"; sh -c "$*"
  else echo "  would run: $*"; fi
}

echo "bootstrap — $(sed -n 's/^release *= *"\(.*\)"/release \1/p' "$ROOT/harness.lock.toml")"
[ "$MODE" = "install" ] || echo "(plan only — re-run with --install to make changes)"

# ---------------------------------------------------------------- 1. tools
step "1. Tools"
if "$ROOT/scripts/install_tools.sh" --check >/dev/null 2>&1; then
  "$ROOT/scripts/install_tools.sh" | sed -n '2,$p' | grep -v '^$' || true
else
  if [ "$MODE" = "install" ]; then "$ROOT/scripts/install_tools.sh" --install
  else "$ROOT/scripts/install_tools.sh"; fi
fi

# ---------------------------------------------------------------- 2. checkouts
step "2. Checkouts"
# A URL needs cloning; a path is expected to be there already.
case "$FORK" in
  *://*|git@*)
    dest="$HOME/GitHub/fork/betteroffice"
    if [ -d "$dest/.git" ]; then echo "  betteroffice   $dest (already cloned)"
    else do_or_show "git clone '$FORK' '$dest'"; fi
    FORK="$dest" ;;
  *)
    if [ -d "$FORK/.git" ]; then echo "  betteroffice   $FORK"
    else
      echo "  betteroffice   $FORK — NOT FOUND"
      echo "                 pass --fork <url> to clone it, or --fork <path> to point at yours"
      [ "$MODE" = "install" ] && exit 1
    fi ;;
esac

if [ -x "$PPTX_PDF/target/release/pptx-pdf" ]; then
  echo "  pptx-pdf       $PPTX_PDF (built)"
else
  echo "  pptx-pdf       $PPTX_PDF — the reference renderer, not built"
  do_or_show "git clone https://github.com/dsaad68/pptx-pdf '$PPTX_PDF' 2>/dev/null || true"
  do_or_show "cargo build --release --manifest-path '$PPTX_PDF/Cargo.toml'"
fi

# ---------------------------------------------------------------- 3. skills and agents
step "3. Skills and agents -> $FORK/.claude"
# Copying is the install step: the agent runtime reads .claude, not this repo. Re-running replaces
# an unmodified copy silently and warns about one you have edited, so local changes are not lost.
if [ -d "$FORK" ]; then
  do_or_show "mkdir -p '$FORK/.claude/skills' '$FORK/.claude/agents'"
  for d in "$ROOT"/skills/*/; do
    name="$(basename "$d")"; target="$FORK/.claude/skills/$name"
    if [ -d "$target" ] && ! diff -rq "$d" "$target" >/dev/null 2>&1; then
      echo "  ! $name differs from the copy in .claude — installing would overwrite your edits"
      echo "    diff -ru '$target' '$d'"
    fi
    do_or_show "cp -R '$d' '$FORK/.claude/skills/'"
  done
  for f in "$ROOT"/agents/*.md; do
    name="$(basename "$f")"; target="$FORK/.claude/agents/$name"
    if [ -f "$target" ] && ! diff -q "$f" "$target" >/dev/null 2>&1; then
      echo "  ! $name differs from the copy in .claude — installing would overwrite your edits"
    fi
    do_or_show "cp '$f' '$FORK/.claude/agents/'"
  done
  # The pipeline itself runs from the fork, so the scripts have to be there too.
  do_or_show "mkdir -p '$FORK/render-improvement-harness'"
  do_or_show "cp -R '$ROOT/scripts' '$FORK/render-improvement-harness/'"
fi

# ---------------------------------------------------------------- 4. verify
step "4. Verify"
if [ "$MODE" = "install" ]; then
  "$ROOT/scripts/check_versions.py"
else
  echo "  would run: ./scripts/check_versions.py"
fi

step "Next"
cat <<EOF
  gh auth status                       # the harness files issues and pull requests as you
  cd '$FORK' && ../betteroffice-meta-harness/scripts/setup_worktree.sh "\$PWD"
                                       # builds betteroffice_pptx for this worktree
  ./scripts/pipeline.py <deck.pptx> --id <name>
                                       # register, render both sides, diff

Decks are yours to supply: this repo carries none, and renders of third-party decks stay on the
machine that made them. Read llm.txt next — it is the operating guide.
EOF
