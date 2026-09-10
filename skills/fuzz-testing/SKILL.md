---
name: fuzz-testing
description: Add coverage-guided fuzz targets with cargo-fuzz to the OOXML crates - where a target is worth it, how to seed and bound it, and how to turn every finding into a stable regression test that CI actually runs. Use for "fuzz X", "add a fuzz target", "why did the fuzzer crash".
version: 1.0.0
---

# Fuzz testing with cargo-fuzz

cargo-fuzz drives libFuzzer: it mutates bytes, watches which branches each input reaches, and keeps
the inputs that reach new ones. That coverage feedback is the whole point. It is what lets a fuzzer
get past a magic number and a length prefix into the code where the bug is — which proptest,
generating random `Vec<u8>`, almost never does.

Use it for bytes you did not author. For structured models and pure functions, use proptest instead
(`.claude/skills/property-testing/SKILL.md`).

## Where it is worth it here

Every one of these reads a file a stranger handed you:

1. **Metafile replay** — `crates/pptx-render/src/metafile.rs`, entry `decode(bytes: &[u8])`. EMF and
   WMF are binary record streams with declared sizes, and three defects this project already shipped
   were a record trusting its own length. The oracle: no input panics, and a record whose declared
   size disagrees with its content yields no drawing rather than a wrong one.
2. **Package parsing** — `crates/pptx-parse/src/package.rs`, `parse_pptx_with_limits`. A zip of XML
   parts. The oracle: no panic, and every allocation stays inside `ParseLimits`. Past defects here
   were resource exhaustion from untrusted input, so run it under `-rss_limit_mb`.
3. **Stored-document deserialisation** — the collaboration `packageJson` a peer sends. It is untrusted
   in exactly the same sense, and it carries hand-written `deserialize_with` code.

A pure function over numbers is **not** a fuzz target, however important. Fuzzing it wastes the
instrumentation and hands back a byte string instead of a shrunk, readable counterexample.

## Setup

Fuzzing needs a nightly toolchain; nothing else in this project does.

    rustup toolchain install nightly
    cargo install cargo-fuzz

`cargo fuzz init` creates `fuzz/` as **its own cargo package with its own `[workspace]`**. Keep it
that way. The root workspace is `members = ["crates/*"]`, so `fuzz/` is outside it, and that is
deliberate: it only builds on nightly.

The consequence is the one that bit `apps/native-viewer`: **`cargo check --workspace` never builds
`fuzz/`**, and no CI job does either. A signature change in a crate it calls breaks every target
silently. Run `cargo +nightly fuzz build` whenever you touch a crate a target depends on.

## A target

    #![no_main]
    use libfuzzer_sys::fuzz_target;

    fuzz_target!(|data: &[u8]| {
        let _ = pptx_render::metafile::decode(data);
    });

Returning without panicking is a pass. A panic, an abort, a timeout or an out-of-memory is a
finding. Assert the oracle inside the target when there is one beyond "does not panic" — for
metafiles, that a record claiming more bytes than remain produces nothing.

### Structured fuzzing

When the interesting behaviour is several layers down, raw bytes spend their budget failing the
outer checks. Derive `arbitrary::Arbitrary` on a **test-only** description of the input — a
`Vec<Record>` with valid and deliberately-corrupted variants — inside the `fuzz/` crate, and
serialise it before calling the entry point. Never derive it on the production model types: they
are owned by their crate and must not grow a fuzzing trait.

`arbitrary` is a dependency of `fuzz/` only. It must not appear in any `crates/*` manifest.

## Seeding, bounding, running

- **Seed from committed fixtures.** Copy the relevant bytes — the EMF stream inside a test `.pptx`,
  one `slide1.xml` — into `fuzz/corpus/<target>/`. A seeded fuzzer starts inside the format; an
  unseeded one spends minutes discovering the header. Never seed from a third-party corpus deck.
- **Add a dictionary for XML targets** (`fuzz/dicts/xml.dict`): element and attribute names the
  parser looks for. It is the difference between mutating tags and mutating random punctuation.
- **Bound every run.** `cargo +nightly fuzz run <target> -- -max_total_time=60 -max_len=65536`.
  `timeout` does not exist on macOS; use `-max_total_time`.
- **Catch exhaustion deliberately.** `-rss_limit_mb=2048 -timeout=10` turn a runaway allocation or
  an unbounded loop into a finding instead of a hung machine.

## A finding

1. Minimise it: `cargo +nightly fuzz tmin <target> <crash-file>`. Commit the small version.
2. **Turn it into a stable test** in the crate that owns the code, feeding those exact bytes through
   the same entry point. CI runs stable and no fuzzer; this test is what actually protects the fix.
3. Keep the minimised input in `fuzz/corpus/<target>/` too, so the fuzzer starts from it next time.
4. `cargo +nightly fuzz cmin <target>` periodically, so the committed corpus stays small.

## Proving a target guards anything

Reintroduce the defect the fix removed, run the target time-boxed, and show it finds it. Then
restore with `git checkout HEAD -- <file>`. A target that cannot rediscover a known bug in a minute
is not reaching the code, and the seed corpus or the target shape is wrong.

## macOS

libFuzzer works on `aarch64-apple-darwin` with nightly. If AddressSanitizer fails to link or
reports spurious leaks at exit, `cargo +nightly fuzz run -s none` drops the sanitizer; say so in the
report, because it narrows what the run can find.
