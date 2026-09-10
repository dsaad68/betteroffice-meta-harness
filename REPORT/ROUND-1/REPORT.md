# Round 1 — the differential render run

A record of what the harness produced, what it got wrong, and what the numbers actually support.
Written at the end of the round; every figure here was measured rather than recalled.

## The shape of it

| | |
|---|---|
| Corpus | 48 decks |
| Plan entries (`ORDER.toml`) | **71** |
| Merged | **50** |
| Filed, awaiting review | 2 |
| Not started | 17 |
| Closed as *not a defect* | 2 |
| Issues filed upstream | **49** |
| Pull requests opened | **51** — 49 merged, 2 open |

Two entries are marked `blocked`, and both are closures rather than deferrals: their own
investigation reports disprove them. `transform-group-child-rotation-scale-wrong` turned out to be a
`custGeom` shape drawn as its bounding box, and `text-shape-lststyle-not-modelled` was already
modelled end to end by an earlier merge. They should be closed, not fixed.

## What shipped in this round

Fifteen pull requests, of which thirteen have merged.

### The batch that cleared the backlog

| PR | Issue | What it fixed |
|---|---|---|
| #344 | #343 | `mc:AlternateContent` in a shape tree — a fallback-wrapped shape was dropped silently |
| #346 | #345 | `eaVert`, `mongolianVert` and `wordArtVert` laid out horizontally |
| #348 | #347 | `a:pPr/@marR` never parsed, so text wrapped at the full box width |
| #350 | #349 | chart series always stroked at 2 px whatever `c:spPr` asked for |
| #352 | #351 | `a:lum` brightness and contrast dropped from recoloured pictures |
| #354 | #353 | `spcBef` / `spcAft` never parsed — every paragraph sat directly under the last |
| #357 | #356 | one unhandled EMF record discarded the whole picture |
| #359 | #358 | chart text dropped its `c:txPr` family, slant and tracking |
| #361 | #360 | a picture never cast its `a:outerShdw` |

### Tables — the largest defect in the corpus

DrawingML tables did not render at all. Not badly: absent. **61 tables across 52 slides in 9 decks**,
every one drawing as a dashed placeholder. It was the only `high` impact entry from the original
clustering pass still standing, and it had been parked for weeks behind a scoping question.

Delivered as five pieces, four merged:

| PR | Issue | What it did |
|---|---|---|
| #375 | #374 | stopped a table frame painting its first cell as loose slide text; added the synthetic fixture |
| #379 | #376 | `Primitive::Table` container, painted in **all four** display-list backends |
| #380 | #377 | parsed `a:tbl` into a real model — grid, row heights, spans, cell fills, borders |
| #381 | #378 | parsed `ppt/tableStyles.xml` and resolved the cell cascade |
| #385 | #384 | **open** — the layout arm: `render_table`, the piece that draws pixels |

The scoping question that had held it — *does the table primitive belong in a shared crate?* — was
answered by measurement rather than argument. `ooxml-drawingml` has no table module and `a:tbl` is
DrawingML, which argued for putting the model there. But a cell holds an `a:txBody`, `TextBody`
lives in `pptx-parse`, and `pptx-parse` depends on `ooxml-drawingml` rather than the reverse. Moving
the cell model would have needed a generic parameter existing purely for a second consumer that did
not want it: `docx-layout` has its own mature table implementation and will not switch. Settled
split: **cell model in `pptx-parse`, style model in `ooxml-drawingml`**, sharing exactly one
function — `normalize_table_column_widths`, the only format-neutral piece of docx's 689 lines of
table code.

### Found while fixing tables

| PR | Issue | What |
|---|---|---|
| #387 | #386 | **open** — `a:tint` and `w:themeTint` applied inverted |

`resolve_color_value_to_hex_with_theme` kept `1 - tint` of the colour instead of `tint`, so a 100%
tint returned pure white. The two formulas are equal at exactly 50%, and the single test covering
tint used `0x80` — 128/255, or 50.2%. It is the one point on the curve where an inverted
implementation is indistinguishable from a correct one.

## What the numbers actually say

Measured in isolation: same tree, the one line on and off, binding rebuilt each time.

**On `main` the tint fix changes nothing.** Every corpus slide is identical with it and without it,
because tables draw as a placeholder until #385 lands and the tinted fills are never painted.

Stacked on #385:

| slide | tables only | with the tint fix |
|---|---|---|
| 12 | 69.58 | **41.06** |
| 10 | 34.94 | **7.94** |
| 04 | 52.95 | **31.57** |
| 07 | 23.32 | **6.60** |
| 03 | 50.38 | **38.38** |
| 05 | 13.71 | **10.82** |

Six improve, thirteen unchanged to two decimal places, none regress. All six are in one deck, which
follows: its tables carry almost no direct cell formatting, so every fill comes from a table style
built on tinted theme colours.

This correction matters more than the number. The round's own prioritisation had this as "high
impact, easy" on the strength of figures taken from a *different branch* — a build that already had
the table layout. Measuring it properly on `main` produced `IDENTICAL`. The fix is right and worth
having; its payoff is entirely conditional on another pull request merging first.

## Corpus measurements that changed decisions

Numbers that were re-derived during the round and overturned an earlier claim:

- **Explicit cell fills: 46 of 61 tables**, 940 of 1955 cells — not the 5 recorded earlier. That
  figure came from a regex anchored to the `a:tcPr` open tag, but `tcPr` starts with border
  elements that each contain their *own* `a:solidFill` for the stroke colour. The correction
  inverted the sequencing argument: most tables look substantially right from the cell model alone,
  and only **14** are wholly style-dependent.
- **Table style resolution: only 2 of 13 distinct style ids fail to resolve**, against an earlier
  claim of 6 of 23. The built-in-GUID fallback table that the original solution document worried
  about was not worth building.
- **Unresolvable style ids all name "No Style, No Grid" or "No Style, Table Grid"**, while `def` in
  those decks is Medium Style 2 – Accent 1. The spec-shaped fallback would have painted accent
  banding onto precisely the tables whose authors asked for none. Declined on that basis.
- **Column banding: 1 of 61 tables** sets `bandCol="1"`, and it lives in the deck whose
  `tableStyles.xml` is an empty `<a:tblStyleLst def="…"/>` with zero definitions. Implementing
  `band1V`/`band2V` would change zero pixels.
- **Vertical cells: 0 of 61.** Rotated or flipped table frames: **0 of 61.**
- **`MAX_TEXT_LINES` is 100 000**, so the 1204-cell deck flagged as a resource risk would need ~83
  lines per cell to trip it. Not a risk.

## Review

Roughly twenty review threads were worked across the round. The split held up: a little over half
described real defects, and the rest were accurate readings that the corpus did not support.

Real, and fixed:

- **#344** — deleting the only shape in an `mc:Fallback` left the wrapper behind, so the shapes came
  back on save. Written as a failing test first. No corpus deck reached it.
- **#359** — an unmeasured legend label's width inverted on negative tracking.
- **#381** — a document stored before table styles existed never recovered them. The first test
  written for this *passed without the fix*, because reattaching a source replaces the in-memory
  package outright; the loss is in what gets persisted.
- **#385** — a table that grows past its frame moved the pivot for a rotation or flip, because the
  pivot is the centre of the emitted bounds.

Declined, with the measurement attached rather than a preference:

- Contract-version validation — refusing a display list is a behaviour change for every embedder.
- The `def` style fallback, column banding, and vertical-cell measurement, all on the corpus figures
  above.
- Gouraud mesh gradients — every corpus `GRADIENTFILL` is a two-triangle rectangle varying along one
  axis, which bands reproduce exactly.

## Still open

Two pull requests await review: **#385** (table layout) and **#387** (tint). #385 should merge first
or #387's value is invisible.

Of the 17 unstarted entries, **none are `high` impact** — the tint fix was the last one. Two are
`medium`, both hard:

- `chart-axpos-edge-not-honoured` — `PlotAxis::position` is still dead data, so a right or top axis
  draws over the legend
- `metafile-clip-and-text-records-reject` — the EMF records the replayer still refuses

The remaining 15 are low impact, and three of those would change nothing today: column banding and
vertical-cell growth are measured no-ops, and `chart-clustered-bar-lane-order` is unconfirmed — no
corpus deck is a clustered `barDir="bar"`, so there is no evidence either way. It needs a deck
before it needs a fix.

**Nine of the nineteen remaining entries were found while fixing something else.** That is the
harness working as designed — each fix opens the file far enough to see the next defect — but it
also means the tail is now self-generated. Nothing from the original clustering pass is left
standing except the table layout, which is written and in review.
