# Round 1 — what the round taught

Carried forward from `render-improvement-harness/fixes/current/LEARNING.md` and extended with what
this round cost to discover. Ordered by how expensive the lesson was, not by topic.

## Measurement

**Isolate the change, in one tree, with the binding rebuilt on both sides.** Every false result this
round came from breaking that rule. The tint fix was prioritised as "high impact" on figures taken
from a branch that already carried the table layout; measured properly on `main` it changed
*nothing*, because the fills it corrects were not being painted yet. A stale compiled binding in a
baseline worktree separately produced deltas up to −5.14 that were not real.

**A "verification" that runs nothing reports success.** `timeout` does not exist on macOS, so
`timeout 900 cargo check … | grep -E "^error"` fails as command-not-found and the grep then exits 0
on empty input. Two checks this round passed that way before being caught. Check the exit status of
the thing you meant to run, not of the pipeline.

**The metric is a triage signal, not a gate.** A correct fix can raise it — text at its proper size
diverges more from a reference whose line breaking differs than wrong-sized text did. Eleven slides
"regressed" on the table layout and every one was a correct table in the wrong shade, from a
one-line colour bug that predated the work.

**When a report and the corpus disagree, re-derive the number.** Three figures this round were
wrong: explicit cell fills (5 → 46, a regex artefact), unresolvable style ids (6 of 23 → 2 of 13),
and a text-budget "risk" that had four orders of magnitude of headroom.

## Shared branches

**Fetching inside the same command as the push does not make a lease safe.** A force-push with
`--force-with-lease` computed from a just-completed fetch destroyed a maintainer's commits: they had
pushed their own versions of two review fixes plus a merge of `main`. The lease was satisfied
because the fetch had already moved the ref. Restored from the SHA, but the guard had been defeated
mechanically while looking correct.

**Check what an "Update branch" merge actually contains before replacing it.** Three appeared on
these branches. Compare the merge's tree against the automatic merge of its two parents: identical
means a mechanical button click carrying no hand resolution, and it is safe to supersede. One of
them merged a commit that predated the conflict it appeared to address.

**A conflict under a shared attribute silently deletes coverage.** Twice, a `deck.rs` conflict sat
directly beneath a shared `#[test]`, so "take both sides" produced one test with two bodies
concatenated and dropped a sibling's case. `main` had accumulated two such tests by the second
occurrence. Always confirm each test still *runs* by name after resolving.

**The set of files that conflict is not the set that needs changing.** A schema renumber conflicted
in six files and needed a seventh — `run_spacing.rs` asserted the current version but merged cleanly.

## Schema and serialization

**Do not chase an unreleased version number.** Two branches were renumbered five times between them
as `main` moved 15 → 17 → 18 → 20 → 21. Upstream then collapsed the whole unreleased chain to 2.1
and folded later work *into* it. The pattern to follow: while a version is unreleased, extend it
rather than adding another.

**One writer per schema bump.** Parallel agents were explicitly forbidden from bumping it, with new
fields carried as `#[serde(default)]` riding the one branch that owned the version. Two bumps
collide, and that collision is what cost the five renumbers.

**A hand-written "is this default?" guard is a data-loss bug waiting for its next field.** A
serializer kept an older wire encoding for a row holding nothing but text, guarded by an enumerated
field list. Rewritten as `*self == Self::from_text(self.text.clone())`, so a field added later
cannot be silently dropped on save.

**Reattaching a source replaces the in-memory package outright.** A test asserting styles came back
after reattachment passed *without* the fix. The loss is in what gets persisted: reattach,
re-encode, reopen with no source, and assert there.

## The build

**A display-list variant has four backends, not two.** `apps/native-viewer` is `exclude`d from the
workspace, so `cargo check --workspace`, `clippy --workspace` and `test --workspace` all stay green
while it fails to compile — and `macos-app.yml` triggers only on `apps/native-viewer/**`, so CI
catches nothing either. Check it by hand:

    cargo check --manifest-path apps/native-viewer/Cargo.toml --no-default-features --features pptx

**`packages/pptx/src/render/canvas.ts` switches on `primitive.kind` with no `default:`**, and
`SlidePrimitive` is a hand-maintained union. A kind added in Rust and not in TypeScript type-checks
clean and draws nothing. Nothing reads `contractVersion`, so bumping it warns no one.

**The seed gate needs all three wasm builds first.** `build:pptx-wasm`, `build:docx-wasm`,
`build:xlsx-wasm`, then `build:seeds` and `check:seeds`. Two pull requests looked broken on a
failing "Package gate" when the code was fine and the committed demo seed had simply gone stale.

**The local wasm rebuild reorders an export** in `packages/docx/src/wasm/generated/*.d.ts` on every
run. Toolchain noise, not a change; revert it rather than committing the churn. It recurred on four
branches.

**Read `origin/main`, never `fork/main`.** The fork trails badly. A `LEARNING.md` entry claiming
`pptx-raster` was not on `main` was stale for exactly this reason, and it was passed to an agent as
fact.

## Tests

**Test at the point where two implementations would disagree.** The inverted tint formula survived
because its only test sat at 50% — the single point on the curve where the wrong and right formulas
produce the same answer. Pick the coordinates an error would move.

**Prefer an external oracle to a self-consistent one.** The replacement test asserts `accent1` at
tint `0x66` resolves to `#B4C7E7`, the swatch Office publishes for "Accent 1, Lighter 60%". It fails
against Microsoft rather than against a snapshot of our own past behaviour. Name the constant so the
next reader can see that.

**A test that pins nothing is worse than no test.** One written this round asserted only that a
height existed; it was deleted rather than left as false assurance.

**Prove the test bites.** Every fix this round was checked by reverting it and confirming the test
fails. Two "fixes" were caught this way as no-ops.

## Working with agents

**Give the agent the current state, not the written record.** Investigation reports went stale
within a day: one described work already done, in crates the round had since decided against. Every
brief carried "verify this against the code; the report predates the decision".

**Say what is out of scope by file, not by intent.** Three agents ran concurrently on one crate
without collision because each was told which files it did not own, and one of them found it could
avoid the contested file entirely by reusing existing `pub(crate)` helpers.

**Agents produce; the session publishes.** No `gh`, no push, no rebase. Held for the whole round and
prevented the failure it exists to prevent: branches cut at different times conflicting the moment
one merges.

**Agents correct the dispatcher, and that is the point.** They overturned the cell-fill measurement,
found the workspace-excluded backend the base commit had broken, and identified the tint inversion
from a metric that merely looked like noise. Each was verified before acceptance, and one CI claim —
that `macos-app.yml` builds on `crates/**` — was wrong and corrected.

**A declined suggestion needs a number, not a preference.** The `def` style fallback was implemented
as specified, then declined once measured: every unresolvable id in the corpus asks for "No Style,
No Grid" while `def` is an accent style. The reply carried the count, the ids and the deck.

## Evidence

**Check a publishable deck exists before promising a before/after.** Of nine decks with tables, one
is publishable — and the same deck ships an empty `tblStyleLst`, so it cannot demonstrate the style
cascade at all. Its cells carry direct formatting, so it still shows the layout work.

**Renders of third-party decks stay local, and their names stay out of issue bodies.** Deck ids
appear in `ORDER.toml` and in local notes, never upstream.
