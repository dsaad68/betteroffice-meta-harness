---
name: property-testing
description: Add property-based tests with proptest to the OOXML crates - round-trip, invariant and malformed-input properties, custom Strategy design, and shrink tuning. Use for "add property tests", "proptest for X", "why did this property fail".
version: 1.0.0
---

# Property testing with proptest

No skill or script in the render harness calls this one, and no `[compatibility]` block lists it —
it is versioned in `harness.lock.toml` only because `check_versions.py` fails on any component it
finds on disk and cannot account for. Use it on its own.

## Read this before writing a single test

Property testing pays for itself where **the input space is large and structured** and where a bug
class keeps recurring in shapes nobody thought to write an example for. It is a poor trade for a
one-line conditional, where the property test is the example test plus machinery.

On this codebase there are exactly three places that clear that bar.

### 1. Round-trip — by far the highest value

The recurring defect in this repo is *model → XML → model loses data*. Two confirmed (a writer that
deletes modelled attributes left unset; an edit crossing a run boundary taking a different writer
path) and four more claimed in review. Every one of them is one attribute that someone threaded
through the parser and forgot in the writer, which no example test catches because the example is
written by the same person who forgot.

The property that catches all of them at once:

```rust
// parse(write(m)) == m, for any m the parser can produce
```

**Get the direction right.** `write(parse(bytes)) == bytes` is the wrong property: OOXML
serialization is not canonical — attribute order, namespace prefixes, whitespace and defaulted
attributes all vary without changing meaning. Compare **models**, not bytes. Where a field is
genuinely lossy by design, assert the normalized form rather than weakening the property to nothing.

### 2. Invariants on pure geometry

`preset_geometry_to_path` takes an adjust value and an aspect ratio and returns a path. A real bug
this run was a `.min(0.5)` that silently truncated any adjust above 0.5. The property that would
have caught the class: for **any** adjust in range and **any** finite positive aspect ratio, every
emitted coordinate is finite and inside the shape box.

Non-finite output is the one to hunt. `f32`/`f64` paths in a renderer reach NaN through division by
a zero extent, and a NaN coordinate propagates silently to a blank shape.

### 3. Malformed binary input

`crates/pptx-render/src/metafile.rs` interprets EMF/WMF records from a file the user did not author.
The property is: no input panics, and a record whose declared size disagrees with its content
produces **no geometry** rather than wrong geometry.

**But consider `cargo-fuzz` first for this one.** proptest generating `Vec<u8>` explores a binary
record format badly — it has no coverage feedback, so it rarely gets past the header. Coverage-
guided fuzzing is the right tool for raw bytes. proptest is the right tool one level up: generate a
*structured* record sequence (a `Vec<Record>` with valid and deliberately-corrupted variants) and
serialize it. Say which you are doing and why.

## The parts of proptest that matter here

`Strategy` is the core abstraction: how to generate a value, and how to shrink it. `Arbitrary` picks
a canonical `Strategy` for a type. proptest keeps strategies **separate from the type**, which is
why it suits this codebase better than quickcheck — the model types are owned by the crate and
should not grow test-only trait impls.

Composition, in rough order of how often you will reach for it:

- `prop_map` — transform a generated value. `any::<u128>().prop_map(Uuid::from_u128)`.
- `prop_oneof![...]` — pick one of several strategies; the `enum` case. Takes weights.
- `Just(v)` — always this value. The other arm of most `prop_oneof!`.
- `collection::vec(elem, size_range(0..10))` — **always bound the size.** An unbounded `Vec` is
  slower and shrinks worse, and a 5000-element case tells you nothing a 3-element one does not.
- `prop_compose!` — build a struct from several strategies without hand-writing `prop_map` chains.
- `prop_filter` — reject values. Use sparingly; it burns generation budget and can abort the run via
  `max_local_rejects`. Prefer generating only valid values.
- `prop_assume!` — same idea inside the test body.

`test-strategy` gives `#[proptest]` as a plain attribute macro plus a nicer `Arbitrary` derive. It
is a second dependency; do not reach for it unless the `proptest!` macro is actually in the way.

### Shrinking is the whole value, and it needs help

A failing case you cannot read is barely better than no failure. Two levers, in this order:

1. **Shrink the search space, not the output.** Narrow strategies find bugs faster *and* shrink
   better. Generate 1–10 elements, not 1–100. Use a small alphabet (`"[a-f]{5}"`) where the exact
   characters are irrelevant.
2. `PROPTEST_MAX_SHRINK_ITERS` — the default is `u32::MAX`, which means four times the case count,
   and that is often not enough on structured data. Raising it to ~10000 rescues an unreadable
   counterexample. `max_shrink_time` (ms) caps it the other way.

Deriving `Arbitrary` over a whole `PptxPackage` and hoping is the classic failure: it shrinks badly
and hands you a 40-node counterexample. Write narrow strategies for the part under test.

### Config worth setting deliberately

`ProptestConfig`, all overridable by environment variable:

| Field | Default | Note |
|---|---|---|
| `cases` | 256 | `PROPTEST_CASES`. Lower it for an expensive property, do not raise it to compensate for a bad strategy. |
| `max_shrink_iters` | `u32::MAX` (= 4× cases) | Raise for structured input. |
| `max_shrink_time` | 0 (unlimited) | Milliseconds. |
| `max_local_rejects` | 65536 | Hit this and your `prop_filter` is wrong. |
| `timeout` | 0 | Milliseconds; **implies forking**, needs the `timeout` feature. |
| `fork` | false | Survives aborts and segfaults; requires a deterministic strategy and test. |

### Failure persistence — commit the file

On failure proptest writes the seed to `proptest-regressions/<path>.txt` alongside the crate
(`FileFailurePersistence::SourceParallel`). Those seeds are replayed **before** new cases on every
later run.

**Commit them.** An uncommitted regression file means the bug is only caught on the machine that
first found it. This is the single most-missed step when adopting proptest.

## Writing one

1. Name the property in one sentence of prose before writing code. If you cannot, you do not have a
   property — you have an example.
2. Write the narrowest strategy that can express the bug.
3. Check it fails against the pre-fix code. **A property test that never failed proves nothing**;
   run it against the parent commit and see red.
4. Bound the runtime. `cargo test --workspace` is already in the review loop for every PR here.
5. Commit `proptest-regressions/` with it.

## The dependency question

There is **no proptest, quickcheck, arbitrary or fuzz target anywhere in this project's own crates**
— the only proptest in the tree is inside vendored `yrs` under `apps/native-viewer/vendor/`. Crate
dev-dependencies are `png`, `serde_json`, `ooxml-opc`, `wasm-bindgen-test`, and nothing else. That
is a deliberately narrow surface.

Adding proptest as a workspace dev-dependency is therefore an architectural decision belonging to
the maintainers, in its own pull request, argued on the round-trip bug class. Do not add it as a
side effect of a fix PR, and do not add it to several branches at once.
