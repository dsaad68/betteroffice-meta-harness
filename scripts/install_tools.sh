#!/usr/bin/env bash
# Check for the tools this harness needs, and install the ones that are missing.
#
# Prints a plan and changes nothing unless you pass --install. The plan is copy-pasteable, so
# reading it is a fine substitute for running it.
#
#   ./scripts/install_tools.sh            what is missing, and how it would be installed
#   ./scripts/install_tools.sh --install  install the missing ones
#   ./scripts/install_tools.sh --check    exit non-zero if anything required is missing (for CI)
#
# Required versions come from harness.lock.toml [requires]; this script and that file are checked
# against each other on every run, so a bump in one is not silently missed by the other.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="plan"
case "${1:-}" in
  --install) MODE="install" ;;
  --check)   MODE="check" ;;
  "")        ;;
  *)         echo "usage: $0 [--install|--check]" >&2; exit 2 ;;
esac

case "$(uname -s)" in
  Darwin) OS="macos" ;;
  Linux)  OS="linux" ;;
  *)      echo "unsupported platform: $(uname -s). Install the tools below by hand." >&2; OS="other" ;;
esac

missing=0
plan=()

# The lock is the single source of truth for versions. Read it rather than repeating it.
want() {
  sed -n 's/^'"$1"' *= *">=\([0-9.]*\)".*/\1/p' "$ROOT/harness.lock.toml" | head -1
}

# `sort -V` orders versions the way humans do; the smaller of the two sorting first means we are ok.
version_ge() {
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]
}

report() { printf '  %-10s %-9s %-9s %s\n' "$1" "$2" "$3" "$4"; }

need() { # name  required  found  install-command  optional?
  local name="$1" required="$2" found="$3" cmd="$4" optional="${5:-}"
  if [ -z "$found" ]; then
    report "$name" "$required" "-" "MISSING"
    [ -n "$optional" ] || missing=$((missing + 1))
    [ -n "$cmd" ] && plan+=("$cmd")
  elif [ -n "$required" ] && ! version_ge "$found" "$required"; then
    report "$name" "$required" "$found" "TOO OLD"
    [ -n "$optional" ] || missing=$((missing + 1))
    [ -n "$cmd" ] && plan+=("$cmd")
  else
    report "$name" "${required:--}" "$found" "ok"
  fi
}

ver() { command -v "$1" >/dev/null 2>&1 && "$@" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 || true; }

echo "harness tools — $(sed -n 's/^release *= *"\(.*\)"/release \1/p' "$ROOT/harness.lock.toml")"
printf '  %-10s %-9s %-9s %s\n' "tool" "required" "found" ""

PY_REQ="$(want python)"; UV_REQ="$(want uv)"; GH_REQ="$(want gh)"; WT_REQ="$(want wt)"; SEM_REQ="$(want sem)"

case "$OS" in
  macos) UV_CMD="brew install uv"; GH_CMD="brew install gh"; PY_CMD="brew install python@3.12"
         SEM_CMD="brew install sem-cli" ;;
  linux) UV_CMD="curl -LsSf https://astral.sh/uv/install.sh | sh"; GH_CMD="see https://github.com/cli/cli#installation"
         PY_CMD="your package manager, python >= $PY_REQ"
         SEM_CMD="curl -fsSL https://raw.githubusercontent.com/Ataraxy-Labs/sem/main/install.sh | sh" ;;
  *)     UV_CMD=""; GH_CMD=""; PY_CMD=""; SEM_CMD="" ;;
esac

need python "$PY_REQ" "$(ver python3 --version)" "$PY_CMD"
need uv     "$UV_REQ" "$(ver uv --version)"      "$UV_CMD"
need gh     "$GH_REQ" "$(ver gh --version)"      "$GH_CMD"
need cargo  ""        "$(ver cargo --version)"   "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
need wt     "$WT_REQ" "$(ver wt --version)"      "cargo install worktrunk"
need sem    "$SEM_REQ" "$(ver sem --version)"    "$SEM_CMD" optional
# Fuzzing is the only thing here that needs nightly, and nothing fails without it.
need cargo-fuzz "$(want cargo-fuzz)" "$(ver cargo fuzz --version)" \
  "rustup toolchain install nightly && cargo install cargo-fuzz" optional

# pptx-pdf is the reference renderer. It is a git checkout built in place, not a package, and
# common.py looks for the release binary at this exact path.
PPTX_PDF_DIR="$HOME/GitHub/pptx-pdf"
if [ -x "$PPTX_PDF_DIR/target/release/pptx-pdf" ]; then
  report "pptx-pdf" "-" "built" "ok"
else
  report "pptx-pdf" "-" "-" "MISSING — the reference renderer; nothing can be compared without it"
  missing=$((missing + 1))
  plan+=("git clone https://github.com/dsaad68/pptx-pdf '$PPTX_PDF_DIR' 2>/dev/null || git -C '$PPTX_PDF_DIR' pull --ff-only")
  plan+=("cargo build --release --manifest-path '$PPTX_PDF_DIR/Cargo.toml'")
fi

echo
if [ "${#plan[@]}" -eq 0 ]; then
  echo "everything the harness needs is present."
  echo "per-worktree Python deps and the betteroffice_pptx binding come from scripts/setup_worktree.sh."
  exit 0
fi

if [ "$MODE" = "check" ]; then
  echo "$missing required tool(s) missing. Run with --install, or install them by hand."
  exit 1
fi

echo "would run:"
for cmd in "${plan[@]}"; do echo "  $cmd"; done

if [ "$MODE" != "install" ]; then
  echo
  echo "nothing installed. Re-run with --install to execute the above."
  exit 0
fi

echo
for cmd in "${plan[@]}"; do
  case "$cmd" in
    see\ * | your\ *) echo "skipping — install by hand: $cmd"; continue ;;
  esac
  echo "+ $cmd"
  sh -c "$cmd"
done

echo
echo "done. Re-run without --install to confirm, then scripts/setup_worktree.sh in each worktree."
