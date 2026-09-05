---
name: fix-loop
description: Fix clustered renderer issues in parallel - build a dependency-ordered plan, fan out issue-fixer subagents that investigate, fix, test and draft the issue and pull request, then file and push them serially and update the merge-order issue. Use for "fix the next N issues", "work the fix loop", "fix cluster X".
version: 1.0.0
---

# Fix loop

Turns investigated clusters into merged-ready pull requests. Investigation happens in parallel;
anything with a side effect outside the working tree happens serially, in this session.

Scripts are self-contained uv scripts: run them directly or with `uv run --script`, never with a
bare `python`. `./scripts/check_versions.py` confirms the skills, agents and scripts on disk match
`harness.lock.toml` — run it if anything behaves unexpectedly after an update.

## Why the split

Subagents may not call `gh`, may not push, and may not rebase. Three things go wrong when they do:

- Branches cut at different times conflict the moment one merges.
- Two agents writing issues for clusters that share a root cause duplicate each other's analysis.
- Agents editing the same function pick approaches that do not compose.

So an agent produces work; this session publishes it.

## 1. Set up the run

Create `fixes/<run-name>/` with:

**`ORDER.toml`** — the plan and the state, machine-readable. One `[[fix]]` or `[[feature]]` per
entry, with `needs` / `repairs` / `after` / `supersedes` saying *how* one depends on another, and
`[fix.meta]` carrying the issue and pull request numbers once they exist. The schema is in
`docs/ORDER-SCHEMA.md`.

Build it from `docs/FIX-PLAN.md` and each cluster's `report.md`. **Pin one `base` SHA for the whole
run**; every agent branches from it and nobody rebases until publish time.

Query it with `scripts/order.py` rather than reading it by eye:

    order.py check      cycles, unknown ids, duplicate ids   — run this after every edit
    order.py ready      what can be worked on now
    order.py plan       the merge order, topologically sorted
    order.py deps <id>  what one entry waits on, and why

`ORDER.toml` is **yours alone**. It is the plan, and a plan with two writers is not a plan. Subagents
read it and never write to it.

**`TODO.md`** — the shared working surface. Subagents write here: what they have started, what they
found that changes the shape of the work, what they could not finish and why. You reconcile it into
`ORDER.toml` when you publish. Expect it to be messy; that is what it is for.

**`LEARNING.md`** — appended to, never rewritten. What the codebase does that was not obvious, where
a `report.md` was wrong, which tools bite. Read it before dispatching agents, and pass anything
relevant into their prompts.

## 2. Dispatch

Launch `issue-fixer` agents, at most 3 at once, one cluster each. Never two clusters that edit the
same function — check the `files:` frontmatter in each `report.md` for overlap and sequence those.

Set the entry's `status` to `claimed` in `ORDER.toml` before dispatching, so a re-entry does not double-dispatch.

Each agent cuts its own worktree with `wt`, from the run's pinned base SHA. Do not create them
yourself — the project's `wt` hooks provision the build cache, the Python environment and the decks,
and an agent that inherited a worktree it did not make will not know what state it is in.

Prompt shape:

```
Fix cluster <cluster-id>. Base: <base SHA>. Create your own worktree: fix/pptx-<slug>.
Relevant learnings: <paste from LEARNING.md, or "none">.
```

Give each agent a distinct slug. Two agents cutting the same branch name will collide.

## 3. Publish (serial, this session)

For each agent that reports back, in `order.py plan` order:

1. Read its `issue.md`, `pr.md` and diff. Check the claim in `pr.md` against what the diff does.
2. File the issue with `gh issue create`. Record the number.
3. Create the `main`-based branch, apply the fix, **run the tests yourself**, push. The agent's
   worktree is on the run's pinned base, which is usually not `main`: expect to drop files for
   crates the target branch does not have, and to re-apply anything the base has moved under.
4. Open the pull request, referencing the issue.
5. Set `status = "filed"`, write the issue and pull request numbers into `[fix.meta]`, and fold
   anything the agent left in `TODO.md` into `ORDER.toml` — a discovered dependency, a cluster that
   turned out to be two, a blocker. Re-run `order.py check`.

Do not batch a push with a test run in one command — gate the push on the tests passing.

## 4. Close the run

Clear the entries you have reconciled out of `TODO.md`, then regenerate the merge-order issue body
with `order.py issue` and post it. Do not hand-write that body: it was hand-edited three times before
this existed and drifted every time. Then append to `LEARNING.md`.

## Rules that keep this honest

- **The metric is not the gate.** A correct fix can raise the per-pixel difference; small correct
  fixes barely move it. Judge against the issue's verification section and the render, and say so in
  the pull request when the number goes the wrong way.
- **A report is a strong prior, not a fact.** Verify its central claim against the code before
  building on it. When it is wrong, fix the work and record it in `LEARNING.md`.
- **Evidence must be publishable.** Renders of third-party decks are not. Only decks whose slides
  carry placeholder content, and never a slide showing a person's name or contact details.
- **Split what cannot ship together.** A change touching a crate that is not on the target branch
  ships in the part that can, and says what is missing and why.
