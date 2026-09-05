# `ORDER.toml`

The plan for a fix run: what to do, in what order, and why that order. Hand-authored, one writer —
the dispatching session. Subagents read it and write to `TODO.md` instead.

It holds the **whole backlog**, not only what is in flight: every cluster the harness has found and
investigated gets an entry, at `status = "todo"` until someone picks it up. That is what makes
`order.py backlog` and `order.py ready` worth having — the plan can answer "what should I do next"
rather than only "what is the merge order".

It is deliberately **not** called a lock. `harness.lock.toml` is a lock: generated, recording what is
known to work together. This file is intent, and intent is argued about rather than resolved.

```toml
version = 1
base = "b21db5fc95efb7c4530e8f1e397351ad6ac8c5f6"   # every branch in the run cuts from this

[[fix]]
id = "text-bullets-autonum-not-drawn"      # unique across [[fix]] and [[feature]] both
title = "draw buAutoNum list numbers"
status = "filed"                            # todo claimed drafted filed merged blocked
branch = "pr/pptx-autonum-bullets"

needs = ["text-inheritance-layout-lststyle-ignored"]
after = []
repairs = []
reason = "reuses the marker-emission path; merged first there is nothing to emit through"

[fix.meta]
issue = 298                 # once filed
pr = 300                    # once opened
impact = "medium"
effort = "medium"
findings = 5
decks = 1
report = "render-improvement-harness/issues/<id>/report.md"
solution = "render-improvement-harness/issues/<id>/possible-solution.md"
evidence = ["render-improvement-harness/issues/<id>/evidence-1.png"]
```

`report`, `solution` and `evidence` are paths in the betteroffice working repo, so an agent handed
only a cluster id can find the investigation without searching for it. The evidence images are
renders of third-party decks: they stay local and are never published.

## The four edge kinds

They are separate because they answer different questions, and only the first two are about
correctness.

| field | means | example |
|---|---|---|
| `needs` | does nothing, or the wrong thing, until the other has merged | arrowheads need connectors parsed, or there is nothing to decorate |
| `repairs` | the named entry makes something worse, and this puts it right | resolving `grpFill` paints custom-geometry icons as rectangles until the geometry parser lands |
| `after` | correct either way; sequenced to avoid contending on the same code | two changes editing the same function, ordered so one does not rebase three times |
| `supersedes` | the named entry should be closed, not merged | a broader change covering a narrower one |

`needs` and `repairs` are hard: a plan that violates them is wrong. `after` is advice, and the
ordering tool says so.

## Status

`todo` → `claimed` (an agent has it) → `drafted` (agent finished, nothing published) → `filed`
(issue and pull request open) → `merged`. `blocked` for anything waiting on something outside the
run, with `reason` saying what.

## Querying it

`scripts/order.py` reads this file:

    order.py list                 what is in the run, and where each entry stands
    order.py backlog              found and investigated, not yet worked on, ranked
    order.py report <id>          where an entry's investigation and evidence live
    order.py deps <id>            what an entry needs, directly and transitively
    order.py blocked-by <id>      what is waiting on this entry
    order.py ready                entries whose hard dependencies have all merged
    order.py plan                 the merge order, topologically sorted
    order.py check                cycles, unknown ids, duplicate ids, bad statuses
    order.py issue                the merge-order issue body, rendered

`order.py issue` covers only entries that actually have a pull request; an entry without one is
backlog, not a merge step. It is the point of the format. That body was hand-written and hand-edited three times
before this existed, and it drifted every time.
