# Project Continuation State

**Date & Time:** October 16, 2026
**Workspace Root:** `c:\Users\Asif\Downloads\AI_Researcher_R1_Submission`
**Virtual Environment:** `.venv\` (Python 3.11.9, dependencies installed from `requirements.txt`)
**Credentials:** `candidate_package/.env` (present, ignored in `.gitignore`)

---

## Tasks Completed

1. **Task 1: Setup & Tests**
   - Moved project files from temporary `pkg/` folder to repo root.
   - Initialized `.venv` and installed `requirements.txt`.
   - Verified `candidate_package/.env`.
   - Ran `python -m unittest tests.test_pipeline` -> **All 17 tests passed**.

2. **Task 2: Smoke Test**
   - Ran `./run` on 3 items with `TRACE=1` at 1x budget.
   - Verified exactly 1 model call per item (`model_calls: 1`), JSON format valid, accepted by `score.py`.

3. **Task 3: Real Results**
   - Ran full 60 items at 1x, 3x, and 10x budgets using `./run` with `TRACE=1`.
   - Output files saved to `results/answers_1x.json`, `answers_3x.json`, `answers_10x.json`.
   - Scored with `candidate_package/score.py`:
     - **1x**: Macro 16.7% (Unique: 20%, Ambiguous: 15%, Inconsistent: 15%)
     - **3x**: Macro 18.3% (Unique: 20%, Ambiguous: 15%, Inconsistent: 20%)
     - **10x**: Macro 23.3% (Unique: 20%, Ambiguous: 30%, Inconsistent: 20%)

4. **Task 4: Baseline Ablation (3 Runs)**
   - Ran `python run_ablations.py --runs 3`.
   - Generated `ablation_results.md` and `ablation_results.json`.
   - Results:
     - **Full**: 1x = 22.2% (22%-23%), 3x = 23.9% (20%-28%), 10x = 24.4% (22%-27%)
     - **Symbolic Floor**: 71.7%
   - Raw model samples cached in `ablation_cache/run0.json`, `run1.json`, `run2.json`.

5. **Task 5 (Iteration 1 - Improved Ablation 3-Run Evaluation)**
   - Ran `python run_ablations.py --runs 3` on live Granite 4.2 8B endpoint.
   - Updated `ablation_results.md` and `ablation_results.json`:
     - **1x macro**: **28.3%** (27%-30%) [unique: 23.3%, ambiguous: 21.7%, inconsistent: 40.0%]
     - **3x macro**: **31.1%** (28%-33%) [unique: 25.0%, ambiguous: 25.0%, inconsistent: 43.3%]
     - **10x macro**: **30.0%** (25%-33%) [unique: 25.0%, ambiguous: 18.3%, inconsistent: 46.7%]
   - Macro jumped from baseline 22.2% -> 28.3% at 1x (+6.1%) and 23.9% -> 31.1% at 3x (+7.2%).
   - Inconsistent resolution improved dramatically (+11.7% at 1x, +18.4% at 10x) due to improved multi-constraint extraction fidelity.
   - Documented before/after in `EXPERIMENTS.md`.

6. **Task 6: Generalization Check**
   - Implemented `tests/test_generalization.py` covering:
     - All 9 relation types against natural paraphrase templates.
     - Punctuation, possessive `'s` stripping, and single-digit time normalization (`9:00` -> `09:00`).
     - Documented brittle boundary conditions (pronouns, nicknames, non-standard times, relations outside closed schema).
     - End-to-end schedule solving using `ScheduleSolver` on paraphrased constraints.
   - Ran `python -m unittest discover tests` -> **All 21 tests passed**.

7. **Task 7: Final Write-Up & [FILL] Resolution**
   - Populated all `[FILL]` markers in `README.md` with exact values from 3-run live ablation.
   - Documented full ablation table, per-kind rates, 3x3 confusion matrices, and analytical discussion matching empirical results.

8. **Task 8: Brief Compliance Verification**
   - Verified all auto-fail criteria and hard rules from `CANDIDATE_BRIEF.md`:
     - One documented entrypoint `./run` (and `run.bat` on Windows).
     - Correct model payload (`ibm-granite/granite-4.2-8b`, `temperature=1.0`, `top_p=0.95`, reasoning disabled, `X-Item-Id` header).
     - Strict budget integrity via thread-safe `CallLedger`, exactly 1 call at 1x, bounded at 3x and 10x, zero retries.
     - Minimal unsat core statement citations verbatim from text.
     - Model dependence verified (`model output blanked` scores 0.0%).
     - All 21 tests passing.

9. **Task 9: Clean Submission Packaging**
   - Built `AI_Researcher_R1_Submission.zip` cleanly excluding `.env`, `ablation_cache/`, `__pycache__`, and `.venv/`.

