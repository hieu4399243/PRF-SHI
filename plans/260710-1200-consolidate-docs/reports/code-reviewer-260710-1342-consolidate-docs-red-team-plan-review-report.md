# Red Team Review: consolidate-docs plan (Assumption Destroyer / Scope Auditor)

## Finding 1: `hoc/00`, `hoc/03`, `hoc/09` scratch-file convention breaks after `hoc/` is deleted — not covered by any phase
- **Severity:** Critical
- **Location:** Phase 1, "Bước 1 — git mv" / "Related Code Files" (only lists 7 of 10 hoc files as needing edits); plan.md, "Link nội bộ trong file bị dời cần tính lại độ sâu tương đối" (only addresses app/*.py links and the DATABASE.md link)
- **Flaw:** Three of the ten `hoc/*.md` files instruct students to create scratch/practice files directly inside the `hoc/` directory as a documented convention ("để không đụng file thật"). Phase 1 deletes the root `hoc/` directory entirely (`rmdir hoc` after `git mv`) but never edits `hoc/00-muc-luc.md`, `hoc/03-safety.md`, or `hoc/09-admin.md` — the plan's own file list in Phase 1 "Bước 3" and "Related Code Files" only names 01, 02, 04, 05, 06, 07, 08.
- **Failure scenario:** A student follows `docs/hoc/03-safety.md` verbatim and runs `touch hoc/safety_demo.py` and later `python3.10` code that does `open("hoc/audit_demo.jsonl", "a", ...)` — but `hoc/` no longer exists at repo root (Phase 1 explicitly removes it). The command fails with `FileNotFoundError`/shell error, and the same happens for `hoc/00-muc-luc.md` line 38 (`./.venv/bin/python hoc/<file_ban_tao>.py`) and `hoc/09-admin.md` line 12 (`touch hoc/admin_demo.py`).
- **Evidence:**
  - `hoc/00-muc-luc.md:38`: `./.venv/bin/python hoc/<file_ban_tao>.py     # chạy file tập`
  - `hoc/00-muc-luc.md:42`: `` > Quy ước: các file tập bạn tự tạo trong `hoc/` (vd `hoc/triage_demo.py`) ``
  - `hoc/03-safety.md:8`: `touch hoc/safety_demo.py`
  - `hoc/03-safety.md:93`: `with open("hoc/audit_demo.jsonl", "a", encoding="utf-8") as f:`
  - `hoc/03-safety.md:97`: `print("đã ghi log, mở hoc/audit_demo.jsonl xem")`
  - `hoc/09-admin.md:12`: `touch hoc/admin_demo.py`
  - Phase 1 file list (`phase-01-move-docs-and-fix-internal-links.md:97-103`) omits 00, 03, 09 from "Modify" entries — only 01,02,04,05,06,07,08 are listed for content edits.
- **Suggested fix:** Add an explicit step in Phase 1 (or a new phase) to grep all 10 moved files for bare `hoc/` mentions (not just `.py](../app/` link patterns) and decide a real target directory for student scratch files (e.g., keep a `hoc/` scratch dir at repo root that is NOT deleted, or repoint the convention to a name that won't collide with `docs/hoc/`'s lesson markdown).

## Finding 2: Directory-tree diagram inside `BAOCAO_DOAN.md` goes stale, but plan explicitly forbids touching it — same class of bug the prior plan's own red-team already caught and fixed
- **Severity:** Critical
- **Location:** plan.md, "Bên trong BAOCAO_DOAN.md/BAOCAO_DANHGIA.md" bullet (lines 78-82): "GIỮ NGUYÊN text ... KHÔNG cần sửa các mention này — chỉ VERIFY lại bằng mắt sau khi dời, không sửa mù."
- **Flaw:** The plan's "coincidental non-change" reasoning is correct ONLY for relative-path prose like `eval/results.md` mentioned from inside `BAOCAO_DOAN.md` (both move into `docs/` together, so the relative path is unchanged). It does NOT hold for the full repo-root ASCII directory tree embedded in `BAOCAO_DOAN.md`, which explicitly depicts `eval/` at the repo root containing `results.md` and `rubric.md` as children — this becomes factually wrong once Phase 1 moves those two files into `docs/eval/`. The plan's blanket "keep unchanged, don't blindly edit" instruction sweeps this diagram in with the safe prose mentions, without distinguishing "relative reference" from "absolute structural diagram."
- **Failure scenario:** After the plan executes, `BAOCAO_DOAN.md` (an academic submission report) still shows a project tree with `├── eval/ ... ├── results.md ... └── rubric.md` at repo root — inaccurate documentation shipped in the graded report, visible to whoever reviews the submission.
- **Evidence:** `BAOCAO_DOAN.md:286-291`:
  ```
  ├── eval/                  # Đánh giá AI
  │   ├── dataset.jsonl      #   90 câu đơn-ý gán nhãn
  │   ├── dataset_complex.jsonl  # 20 câu ghép nhiều ý (label chính + accept)
  │   ├── evaluate.py        #   tính Precision/Recall/F1, top-1/top-2, v1 vs v2
  │   ├── results.md         #   kết quả
  │   └── rubric.md          #   tiêu chí định tính
  ```
  This is the EXACT bug class the sibling plan `plans/260710-1059-restructure-app-package/plan.md:96` already identified and fixed: `"BAOCAO_DOAN.md/BAOCAO_DANHGIA.md có sơ đồ thư mục/đường dẫn gốc, không thuộc phạm vi phase nào | High | Accept | Phase 4"`. This plan repeats the same class of miss without applying that precedent.
- **Suggested fix:** Add explicit scope to a phase (likely Phase 1 or 2) to check for and update directory-tree/ASCII diagrams inside `BAOCAO_DOAN.md`/`BAOCAO_DANHGIA.md`, not just prose relative-path mentions.

## Finding 3: Phase 3 undercounts `hoc/triage_demo.py` convention mentions in `docs/getting-started-guide.md` — says "1 câu", actual file has 2
- **Severity:** Medium
- **Location:** Phase 3, "Architecture" → `docs/getting-started-guide.md` section: "có 1 câu mention quy ước `hoc/triage_demo.py`"
- **Flaw:** The plan asserts there is exactly one sentence referencing the `hoc/triage_demo.py` scratch-file convention that needs a prefix update. Grep shows two distinct occurrences: one in a runnable code block and one in prose.
- **Failure scenario:** An implementer following the plan literally, expecting "1 câu", fixes the prose mention (~line 395) and stops, leaving the code-block command (line 285) unpatched — inconsistent doc where one instruction says `hoc/triage_demo.py` and the other says `docs/hoc/triage_demo.py`.
- **Evidence:**
  - `docs/getting-started-guide.md:285`: `./.venv/bin/python hoc/triage_demo.py`
  - `docs/getting-started-guide.md:395`: `` > Quy ước khi học: tạo file tập trong `hoc/` (vd `hoc/triage_demo.py`) để **không đụng ``
  - `grep -c "hoc/triage_demo" docs/getting-started-guide.md` → `2`
- **Suggested fix:** Correct the plan text to "2 occurrences" and require both to be checked/updated consistently — and resolve the same underlying ambiguity as Finding 1 (is `hoc/` or `docs/hoc/` actually a valid scratch directory after the move?).

## Finding 4: Phase 3's proposed fix for the scratch-file convention (`hoc/` → `docs/hoc/`) directs students to drop practice `.py` files inside the docs folder, contradicting the plan's own "docs are documentation, not code" boundary
- **Severity:** Medium
- **Location:** Phase 3, lines 56-58: "...nếu là ví dụ minh hoạ chung chung... thì CHỈ cần đổi tiền tố thư mục nhắc tới trong câu (`hoc/` → `docs/hoc/`) cho nhất quán, không cần tạo file thật."
- **Flaw:** This directly conflicts with the plan's own rationale for excluding `mobile/README.md` ("đây là README riêng của package mobile... không phải tài liệu chung của dự án") and with treating `docs/` purely as a documentation destination. Redirecting the scratch-code convention into `docs/hoc/` means practice `.py`/`.jsonl` files a student creates while following the tutorial would land inside the markdown documentation tree, mixed with the 10 lesson files — a scope/purpose collision the plan never flags as a design decision requiring user confirmation.
- **Failure scenario:** Student creates `docs/hoc/triage_demo.py`, `docs/hoc/audit_demo.jsonl`, etc. per the tutorial's own instructions, permanently polluting the `docs/` folder with generated code artifacts, and a future `git status` shows untracked junk inside what's supposed to be a pure documentation directory.
- **Evidence:** `docs/getting-started-guide.md:395` (target of the proposed edit) and the general project convention implied by `docs/codebase-summary.md:58` (`hoc/` listed as "Tài liệu tự học" — documentation, not scratch code space).
- **Suggested fix:** This is a real scope decision (where should tutorial scratch files live post-move?) that should be surfaced to the user per the "User Decisions" rule, not resolved unilaterally inside a phase file as a mechanical prefix swap.

## Finding 5: Deleting `.repomixignore` is asserted as safe based only on an in-repo grep, but the file is a config for an external CLI tool (repomix) that isn't necessarily invoked from any script in this repo
- **Severity:** Medium
- **Location:** plan.md, "Quyết định đã chốt với user" point 2: "`.repomixignore` (config repomix, không có config chính kèm theo)"
- **Flaw:** The plan's justification for "no accompanying main config" is based on `find` not finding a `repomix.config.json`. But `.repomixignore` is picked up automatically by the `repomix` CLI (via `npx repomix` or similar) even with zero project-local config file — a developer could still run it ad hoc against this repo (evidenced by `release-manifest.json`, a 366KB repomix-generated manifest, already existing in the repo — meaning the tool WAS used here before, contradicting the "unused" framing even though the manifest itself is being deleted too).
- **Failure scenario:** A future contributor runs `npx repomix` for a fresh manifest/context bundle without `.repomixignore`; the tool now includes `node_modules`, `dist`, `.venv`, `.claude`, etc. that were previously excluded, producing a bloated/noisy manifest — not a functional break, but silently regresses a previously-working workflow the plan writer characterized as fully "unused."
- **Evidence:** `release-manifest.json:9347` lists `.repomixignore` as a manifest entry, proving `.repomixignore` was actively used to produce `release-manifest.json` at some point. `find . -maxdepth 1 -iname "*repomix*"` returns only `./.repomixignore` (no config, confirming plan's narrow claim but not the broader "unused" claim).
- **Suggested fix:** Downgrade the claim from "không dùng" (unused) to "no longer needed since `release-manifest.json` is also being deleted and no automation depends on it" — accurate framing — or ask the user to confirm before deleting a tool config that has evidence of prior manual use.

## Finding 6: `eval/evaluate.py` docstring example path (`eval/dataset.jsonl`, line 4) is left unaddressed but is technically consistent — however plan's phase-1 edit list for evaluate.py doesn't grep the WHOLE file for `results.md`/`eval/` mentions beyond the two called out
- **Severity:** Medium
- **Location:** Phase 1, "Bước 2 — sửa eval/evaluate.py" (lines 43-66)
- **Flaw:** The phase file identifies exactly two spots to edit (`RESULTS_PATH` constant and the docstring's `ghi vào eval/results.md` line) via manual reading, but provides no grep/verification step to confirm these are the ONLY two `results.md`/output-path mentions in the file. `evaluate.py` is 10KB (per earlier `ls -la`), and the plan's confidence ("CẢ 2 chỗ này tự động in đúng...") rests on having read the whole file once during scouting, not on a repeatable grep check baked into the phase's verification steps.
- **Failure scenario:** If `evaluate.py` has a third mention (e.g., an error message, a `--help` string, or a comment further down not shown in the plan's excerpt) referencing `eval/results.md` literally, it would go unnoticed since Phase 1's "Green" verification only checks that `docs/eval/results.md` gets written and tests pass — it never re-greps `evaluate.py` for stray old-path string literals.
- **Evidence:** Phase 1 "Green — verify" step 6 (lines 118-133) checks file existence and pytest, but has no `grep -n "eval/results\|eval/rubric" eval/evaluate.py` post-edit verification step, unlike Phase 2/3 which DO include such greps for the markdown files.
- **Suggested fix:** Add a grep-based post-edit check to Phase 1 Step 6: `grep -n "eval/results\.md\|eval/rubric\.md" eval/evaluate.py` and manually confirm any remaining literal old-path mentions are intentional (e.g., referring to the input dataset which does NOT move) vs. stale.

## Scope Auditor Verification Results

Verified 10+ scope claims against a repo-wide grep (not limited to the 3 files the plan enumerates):

1. **"hoc/*.md 10 files" list** — confirmed exact match via `ls hoc/` (00–09, 10 files) against Phase 1's `git mv` command list. ✅ Accurate.
2. **"eval/rubric.md + eval/results.md only, evaluate.py/dataset.jsonl/dataset_complex.jsonl stay"** — confirmed via `ls eval/` (5 files: dataset.jsonl, dataset_complex.jsonl, evaluate.py, results.md, rubric.md). ✅ Accurate.
3. **"mobile/README.md GIỮ NGUYÊN, không tham chiếu hoc/eval/BAOCAO"** — confirmed via `grep -n "hoc/\|eval/\|BAOCAO" mobile/README.md` → zero matches. ✅ Correct exclusion.
4. **"README.md GIỮ NGUYÊN vị trí gốc"** — confirmed plan never lists README.md under `git mv`; Phase 2 only edits content in place. ✅ Consistent.
5. **"plans/*.md KHÔNG bị đụng"** — confirmed; the plan's own file lists across all 3 phases never touch `plans/`. Repo-wide grep shows two OTHER plan directories (`plans/260709-1718-docs-consolidation/`, `plans/260710-1059-restructure-app-package/`) also mention `hoc/`, but these are historical/completed plan records, correctly out of scope. ✅ Correct exclusion, no conflict (restructure-app-package plan status is `completed`, its hoc/app changes are already reflected in current file content).
6. **"6 bài hoc/*.md có link tới app/*.py"** — confirmed via `grep -n "\.py\](" hoc/*.md`: exactly 01, 02, 04, 05, 06, 07 match `../app/X.py` pattern, matching plan's Bước 3 list exactly. ✅ Accurate.
7. **"hoc/08 có link ../docs/database-storage-guide.md"** — confirmed at `hoc/08-storage-calendar-reminder.md:42`. ✅ Accurate.
8. **"docs/project-roadmap.md and docs/project-overview-pdr.md have `../BAOCAO_DANHGIA.md`"** — confirmed: `docs/project-roadmap.md:43` and `docs/project-overview-pdr.md:9,54` (plan said "~dòng 9, ~54" — exact match, both occurrences found). ✅ Accurate.
9. **"docs/getting-started-guide.md ~9-10 hoc/ links, all bare (no `../`)"** — confirmed 9 bare `hoc/...` link occurrences (lines 260, 279, 290, 291, 302, 319, 383, 384) plus 1 `BAOCAO_DANHGIA.md` bare link (387); none use `../`. ✅ Accurate — but plan's "coincidentally already correct, no edit needed" framing for these masks Finding 3/4's separate scratch-convention problem in the SAME file.
10. **Cross-repo grep for any additional `.md` link/reference to `hoc/`, `eval/`, `BAOCAO_` the plan's 3 phases might have missed** — full repo grep found matches only in: `BAOCAO_DOAN.md` (self, tree diagram — Finding 2), `docs/codebase-summary.md` (covered by Phase 2's grep), `docs/getting-started-guide.md` (covered by Phase 3, but incompletely — Findings 3/4), `hoc/*.md` (self-references — Finding 1), and the 3 plan directories (correctly excluded). No stray reference was found in `ISSUES.md`, `docs/database-storage-guide.md`, `docs/code-standards.md`, `.claude/`, or `scripts/` requiring a fix that the plan's 3 phases don't already cover (their `eval/` mentions refer to `evaluate.py`/dataset files, which do not move).
11. **`.repomixignore` "unused" claim** — partially contradicted; see Finding 5.

## Summary
6 findings: 2 Critical, 3 Medium (one borderline High-leaning but kept Medium since it's a design-decision gap, not a broken link), 1 Medium. The two Critical findings (scratch-file convention breakage in `hoc/00`/`03`/`09`, and the stale directory-tree diagram in `BAOCAO_DOAN.md`) both represent classes of bug that this project's OWN prior plan (`restructure-app-package`) already hit and had to add dedicated fixes for — this plan does not apply that precedent and reproduces the same gap.
