# Project State & Revision Log

**Date & Time:** October 16, 2026
**Workspace Root:** `c:\Users\Asif\Downloads\AI_Researcher_R1_Submission`
**Virtual Environment:** `.venv\` (Python 3.11.9, dependencies installed from `requirements.txt`)
**Credentials:** `candidate_package/.env` (present locally, confirmed NEVER committed or tracked in Git)

---

## Completed Tasks

1. **Task A: Security & Privacy Audit (PASSED)**
   - Ran `git ls-files` and `git log --all --stat`: `.env` was never tracked in Git history.
   - Performed programmatic in-memory scan of all working tree files, all git commit history (`git log -p --all`), and the submission zip.
   - **Result: PASS.** The API key string is NOT present anywhere in Git or archives.
   - Untracked `AI_Researcher_R1_Submission.zip` from Git and added `*.zip` to `.gitignore`.

2. **Task B: Generalization & Forced Per-Line Enumeration**
   - Eliminated all visible-set phrasing idioms from prompt and few-shot examples.
   - Invented novel entities for `FEW_SHOT`: staff (`Alex, Brooke, Connor, Diana, Ethan`), stations (`assembly, testing, dispatch`), blocks (`08:00`–`16:00`). Verified 0 substring overlap with `items.json`.
   - Prompt mandates forced per-line enumeration: lines 1..N must be addressed with either `{"line_no": k, "type": "NONE"}` or the constraint object.
   - Enhanced `parse_model_json` to flatten nested `"slots"` and map `"name"` -> `"person"`.
   - Increased `MAX_TOKENS = 1200`.

3. **Task C: Generalization Measurement on Paraphrased Dev Set**
   - Created `tests/make_paraphrase_set.py` (rewriting 58.0% of lines with generic synonyms and clause structures).
   - Created `tests/eval_comparison.py` and benchmarked 3 runs at 1x:
     - **Old Prompt (with visible idioms)**: **7.8%** (6.7%–10.0%)
     - **New Prompt (generic logic + forced enumeration)**: **22.2%** (20.0%–23.3%)
     - **Result**: +14.4% generalization gain (nearly 3x improvement on unseen phrasing).

4. **Task D: Final Full 3-Run Ablation on Visible Set**
   - Executed `python run_ablations.py --runs 3` on `ibm-granite/granite-4.2-8b`:
     - **1x macro**: **30.0%** (27%–32%)
     - **3x macro**: **28.3%** (28%–28%)
     - **10x macro**: **30.0%** (27%–33%)
   - True unique misclassified as ambiguous dropped from 34/60 down to 17/60 (recall doubled).
   - Conclusively reproduced union degradation: `aggregate = union` plummets from **30.0% (1x) -> 23.9% (3x) -> 18.9% (10x)**, while plurality voting maintains stability (**30.0% at 10x**, +11.1% over union).

5. **Task E: Report Update (`README.md`)**
   - Updated all tables, per-kind rates, and confusion matrices with final measured data.
   - Addressed the gap honestly: compared our ~30% score to the 71.7% symbolic floor and 67.5% frontier reference, establishing that model extraction recall is the primary bottleneck.
   - Analyzed voting vs. union based on the new empirical evidence.
   - Disclosed earlier template overfitting and documented the paraphrased dev set results (22.2%).
   - Updated test count to 21 tests.

6. **Task F: Brief Compliance & Rule Verification**
   - All auto-fails and hard rules verified and satisfied.
   - Full 21-test suite passing (`python -m unittest discover tests`).

7. **Task G: Clean Packaging**
   - Built clean `AI_Researcher_R1_Submission.zip` excluding `.env`, cache, and pycache.
   - Stopped before pushing to Git, awaiting user instructions.
