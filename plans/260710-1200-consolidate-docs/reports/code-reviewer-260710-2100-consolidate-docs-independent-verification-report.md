# Independent Implementation Verification — Consolidate Docs Plan

Verified directly against live repo state (not against implementer self-reports).

## Results

1. **Structure** — PASS. `docs/hoc/` has 10 files, `docs/eval/` has `rubric.md` + `results.md`,
   `docs/BAOCAO_DOAN.md` and `docs/BAOCAO_DANHGIA.md` exist. Old locations (`hoc/`,
   `eval/rubric.md`, `eval/results.md`, `BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md`) confirmed gone
   (`ls` errors "No such file or directory" for all). `git status --short` shows `RM`/`R` for
   every move (rename detected, not separate D+??).

2. **`.repomixignore` / `release-manifest.json`** — PASS. `.repomixignore` still present
   (`ls -la .repomixignore` succeeds, last touched 2026-07-09, tracked since commit `527bd6b`).
   `release-manifest.json` confirmed deleted (`ls` fails; `git status` shows `D`).

3. **`eval/evaluate.py` RESULTS_PATH** — PASS. `RESULTS_PATH = os.path.join(ROOT, "docs",
   "eval", "results.md")` reuses the existing `ROOT` var (line 32). Docstring line 13 now reads
   "ghi vào docs/eval/results.md". Ran `python3.10 eval/evaluate.py` live: `docs/eval/results.md`
   mtime updated (20:56 → 21:00), and `eval/results.md` (old location) does not exist
   afterward.

4. **Link depth fixes in 7 `hoc/*.md` files** — PASS. Extracted actual link targets via
   `grep -oE ']\([^)]+\)'` from all 7 files (01,02,04,05,06,07,08) and resolved every one with
   `test -f` from `docs/hoc/`: all 7 `../../app/*.py` links and `08`'s
   `../database-storage-guide.md` resolve OK. No MISSING.

5. **`hoc/00,01,03,09` shell/prose fixes** — PASS. `grep -n "hoc/" docs/hoc/{00,01,03,09}...`
   shows every remaining `hoc/` occurrence already carries the `docs/` prefix (e.g.
   `touch docs/hoc/triage_demo.py`, `docs/hoc/audit_demo.jsonl`). No bare `hoc/` references
   left in these 4 files.

6. **`BAOCAO_DOAN.md` tree diagram + `evaluate.py` prose** — PASS. Directory tree (lines
   264–301) now shows `docs/hoc/`, `docs/eval/{results.md,rubric.md}` as children of `docs/`,
   and `eval/` (root) only lists `dataset.jsonl`, `dataset_complex.jsonl`, `evaluate.py`. Prose
   at line 466 reads `../eval/evaluate.py` (ghi ra `eval/results.md`) — evaluate.py path
   correctly walks out of `docs/`, results.md bare reference correctly stays (coincidentally
   resolves to `docs/eval/results.md`). `docs/BAOCAO_DANHGIA.md` lines 7–8 show the same
   `../eval/evaluate.py` fix.

7. **`README.md`** — **FAIL (partial)**. Mixed command+comment line 87 is correctly fixed
   (`./.venv/bin/python eval/evaluate.py   # ... → ghi docs/eval/results.md`; command
   untouched, comment path updated). However, line 43's prose table row was **missed**:
   `| **Đánh giá AI** | \`eval/\` | \`dataset.jsonl\` + \`evaluate.py\` (...) + \`rubric.md\`; ... |`
   still implies `rubric.md` lives directly under `eval/`, but it moved to
   `docs/eval/rubric.md`. This is a stale reference not caught because the phase's grep
   pattern (`eval/rubric`) only matches the prefixed form, not the bare `rubric.md` mention.
   No other stale `hoc/`/`BAOCAO_*`/`eval/results.md` references found elsewhere in the file.

8. **`docs/codebase-summary.md`** — **FAIL (partial)**. Line 54: `` | `eval/evaluate.py` |
   Accuracy/Macro-F1, v1 vs v2 → `results.md` | `` — the arrow target `results.md` is a bare
   reference with no `eval/` prefix. Since this file lives in `docs/`, a bare `results.md`
   would resolve to `docs/results.md`, which is wrong; it needed to become `eval/results.md`
   (coincidentally-correct bare form) or `docs/eval/results.md` explicitly. The very next row
   (line 55) correctly uses the full `docs/eval/rubric.md`, showing inconsistent treatment of
   sibling rows. No `../hoc/` or `../BAOCAO_*` stale exits-`docs/` references found otherwise.

9. **`project-roadmap.md` / `project-overview-pdr.md`** — PASS. All 3 occurrences of
   `BAOCAO_DANHGIA.md` links confirmed bare (no `../`): roadmap.md:43,
   overview-pdr.md:9, overview-pdr.md:54.

10. **`getting-started-guide.md`** — PASS. Exactly 2 `hoc/triage_demo.py` mentions found
    (lines 285, 395), both now `docs/hoc/triage_demo.py`. `eval/results.md` prose (line 225)
    fixed to `docs/eval/results.md`. 9 bare `hoc/*.md` markdown links found; all resolved with
    `test -f` from `docs/` — all OK (coincidentally-correct bare links, untouched as intended).

11. **No content rewrites beyond paths** — PASS (spot-checked). `git diff HEAD -M` on
    `docs/hoc/02-data.md` shows only the link-depth change (98% similarity, 1 line changed).
    `docs/BAOCAO_DOAN.md` diff shows only tree-diagram/path edits (10 insertions/5 deletions,
    all path-related). `docs/BAOCAO_DANHGIA.md` diff is a single 1-line path change.

12. **Full test suite** — PASS. `python3.10 -m pytest tests/ -v` → `92 passed, 1 skipped`.

13. **`git status --short` cleanliness** — PASS (after cleanup). Running `evaluate.py` and
    `pytest` during verification dirtied `app/audit_log.jsonl` and
    `app/outbox/push_outbox.jsonl`; both reverted via `git checkout --`. Remaining `git status`
    output contains only the expected renames/modifications from the 3 phases plus the
    untracked `plans/260710-1200-consolidate-docs/` directory.

## Fact-check on plan claims

- Plan's Red Team finding #7 (README mixed command+comment line) — verified genuinely applied
  correctly at line 87.
- Plan's Red Team finding #8 (Phase 3 undercounted `triage_demo.py` mentions, should be 2 not
  1) — verified: both occurrences now fixed.
- Plan's Red Team finding #6/#2 (BAOCAO prose `evaluate.py` categorization, tree diagram
  staleness) — verified genuinely applied.
- Despite the plan explicitly calling out (finding #10) "verify link only tests hardcoded
  list... may miss typos", the actual verification performed by whichever implementer executed
  Phase 2 did **not** catch the bare `rubric.md` mention in README.md line 43, nor the bare
  `results.md` in codebase-summary.md line 54 — both are exactly the class of miss that
  finding #10 warned about, and both slipped through despite the warning being explicitly
  written into the phase file.

## Summary of failures

- `README.md:43` — stale `rubric.md` prose reference (implies file still lives in `eval/`).
- `docs/codebase-summary.md:54` — stale bare `results.md` reference (implies file lives
  directly in `docs/`, not `docs/eval/`).

Both are prose/table-cell references, not markdown links, so they don't break `test -f`
resolution checks, but they are factually wrong about where the files now live and will
mislead readers.
