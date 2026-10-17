# Project State & Revision Log

**Date & Time:** October 17, 2026
**Workspace Root:** `c:\Users\Asif\Downloads\AI_Researcher_R1_Submission`
**Virtual Environment:** `.venv\` (Python 3.11.9, dependencies installed from `requirements.txt`)
**Credentials:** `candidate_package/.env` (present locally, confirmed NEVER committed or tracked in Git)

---

## Current Status & Verification Summary

| Item | Status | Details |
| :--- | :--- | :--- |
| **Offline Unit Tests** | **PASS (21/21)** | `python -m unittest discover tests` completed in 8.3s, zero network calls. |
| **Mock Ablation Harness** | **PASS** | `python run_ablations.py --mock` verified harness logic and report generation. |
| **Ablation Replay** | **PASS** | `python run_ablations.py --runs 3 --reuse` perfectly reproduces 30.0% (1x), 28.3% (3x), 30.0% (10x). |
| **Live OpenRouter API** | **ACTIVE** | Endpoint reachable, key active with remaining balance. |
| **Security & Privacy** | **VERIFIED** | Zero `.env` or API key references in Git history, zip, or commits. |
| **Submission Package** | **READY** | `AI_Researcher_R1_Submission.zip` cleanly packaged and verified. |

---

## Chronological Task Log

### 1. Task A: Security & Privacy Audit (PASSED)
- Ran `git ls-files` and `git log --all --stat`: `.env` was never tracked in Git history.
- Performed programmatic in-memory scan of all working tree files, all git commit history (`git log -p --all`), and the submission zip.
- **Result: PASS.** The API key string is NOT present anywhere in Git or archives.
- Untracked `AI_Researcher_R1_Submission.zip` from Git and added `*.zip` to `.gitignore`.

### 2. Task B: Generalization & Forced Per-Line Enumeration
- Eliminated all visible-set phrasing idioms from prompt and few-shot examples.
- Invented novel entities for `FEW_SHOT`: staff (`Alex, Brooke, Connor, Diana, Ethan`), stations (`assembly, testing, dispatch`), blocks (`08:00`–`16:00`). Verified 0 substring overlap with `items.json`.
- Prompt mandates forced per-line enumeration: lines 1..N must be addressed with either `{"line_no": k, "type": "NONE"}` or the constraint object.
- Enhanced `parse_model_json` to flatten nested `"slots"` and map `"name"` -> `"person"`.
- Increased `MAX_TOKENS = 1200`.

### 3. Task C: Generalization Measurement on Paraphrased Dev Set
- Created `tests/make_paraphrase_set.py` (rewriting 58.0% of lines with generic synonyms and clause structures) and `paraphrased_key.json` (remapped citation key for verbatim scoring).
- Created `tests/eval_comparison.py` and benchmarked 3 runs at 1x:
  - **Old Prompt (with visible idioms)**: **23.9% macro** (21.7%–26.7%)
  - **New Prompt (generic logic + forced enumeration)**: **33.9% macro** (33.3%–35.0%)
  - **Result**: +10.0% generalization gain on the remapped proxy set (recovering ambiguous items: 30.0% vs 6.7%). On this set, the regex baseline collapses from 71.7% to 21.7%, confirming model reliance.

### 4. Task D: Final Full 3-Run Ablation on Visible Set
- Executed `python run_ablations.py --runs 3` on `ibm-granite/granite-4.2-8b`:
  - **1x macro**: **30.0%** (27%–32%)
  - **3x macro**: **28.3%** (28%–28%)
  - **10x macro**: **30.0%** (27%–33%)
- True unique misclassified as ambiguous dropped from 34/60 down to 17/60 (recall doubled).
- Precision and recall are both limiting (at 1x, 24/60 true-unique and 21/60 true-ambiguous are declared inconsistent due to spurious noise constraints or inverted directions).
- Conclusively reproduced union degradation: `aggregate = union` plummets from **30.0% (1x) -> 23.9% (3x) -> 18.9% (10x)**, while plurality voting maintains stability (**30.0% at 10x**, +11.1% over union).

### 5. Task E: Report Update (`README.md`)
- Updated all tables, per-kind rates, and confusion matrices with final measured data.
- Addressed the gap honestly: compared our ~30% score to the 71.7% symbolic floor and 67.5% frontier reference, establishing that precision and recall are both limiting bottlenecks (24/60 true-unique and 21/60 true-ambiguous are declared inconsistent at 1x).
- Analyzed voting vs. union based on empirical evidence.
- Disclosed earlier template overfitting and documented the paraphrased dev set results (33.9%).
- Updated test count to 21 tests.

### 6. Task F: Local PC Verification (October 17, 2026)
- Re-tested offline suite on local Windows environment: all 21 unit tests passed with code 0 (`tests.test_pipeline` and `tests.test_generalization`).
- Verified `run.bat` launcher for Windows command prompt and PowerShell compatibility.
- Confirmed cached ablation reproduction via `python run_ablations.py --runs 3 --reuse`.
- Checked `results/answers_1x.json` vs final ablation cache: documented that earlier interim results scored ~16.7% while the final pipeline achieves ~30.0% macro exact match across 3 runs.

### 7. Task G: Clean Packaging & Submission Readiness
- Verified `AI_Researcher_R1_Submission.zip` is built and clean:
  - Contains: `candidate_package/`, `tests/`, `run`, `run.bat`, `run_ablations.py`, `README.md`, `EXPERIMENTS.md`, `CHANGES.md`, `requirements.txt`.
  - Excluded: `.env`, `.git/`, `.venv/`, `scratch/`, `__pycache__/`, `*.pyc`.
- Ready to send as an email attachment or repository archive.
