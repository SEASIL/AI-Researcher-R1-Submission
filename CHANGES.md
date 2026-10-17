# Changes Log

Copy your original `candidate_package/.env` back in before running (it is not included here, and must not be committed).

## 1. Security & Privacy Audit
* Programmatic audit of working tree, full Git commit diffs (`git log -p --all`), and zip archives: confirmed that `.env` and `OPENROUTER_API_KEY` were never committed.
* Untracked `AI_Researcher_R1_Submission.zip` from Git and added `*.zip` to `.gitignore`.

## 2. Generalization & Overfitting Elimination (`pipeline.py`, `normalizer.py`)
* **Eliminated template overfitting:** Removed all idioms copied from `items.json` ("whichever way round...", "hands straight over to...", "in the old arrangement").
* **Invented few-shot entities:** Few-shot roster uses novel staff (`Alex, Brooke, Connor, Diana, Ethan`), stations (`assembly, testing, dispatch`), and blocks (`08:00`–`16:00`). Automated script verified 0 substring matches in `candidate_package/items.json`.
* **Abstract relation definitions:** `TYPES_DOC` defines relations purely in terms of logical semantics and slot directions.
* **Generalization measurement:** Built `tests/make_paraphrase_set.py` (rewrote 58% of lines with generic synonyms and clause structures), `paraphrased_key.json`, and `tests/eval_comparison.py`. Confirmed that the new generic prompt scores **33.9% macro** on the paraphrased dev set compared to **23.9%** for the idiom-heavy prompt (+10.0% generalization gain on the remapped proxy key).

## 3. Recall Improvement via Forced Per-Line Enumeration (`pipeline.py`)
* Prompt mandates a verdict for every numbered line 1..N: `{"line_no": k, "type": "NONE"}` for non-scheduling lines, or the constraint object.
* This compulsory line-by-line review cut missed constraints in half: true `unique` items misdeclared as `ambiguous` dropped from 34/60 down to 17/60.
* Tolerant parser flattens nested `"slots"` dict/list if the model nests parameters, and maps `"name"` to `"person"`.
* Raised `MAX_TOKENS` from 800 to 1200 to prevent output truncation during per-line enumeration.

## 4. Multi-Sample Aggregation & Ablation Findings (`run_ablations.py`)
* 3-run live ablation on Granite 4.2 8B:
  * 1x macro: **30.0%** (27%–32%)
  * 3x macro: **28.3%** (28%–28%)
  * 10x macro: **30.0%** (27%–33%)
* Conclusively reproduced the degradation of additive accumulation: `aggregate = union` plummets from **30.0% (1x) -> 23.9% (3x) -> 18.9% (10x)** as accumulating noisy constraints over-constrains satisfiable schedules into false contradictions.
* Per-line plurality voting maintains stability (**30.0% at 10x**, an +11.1% advantage over union).

## 5. Test Suite Expansion
* Total test count expanded to **21 tests** (`python -m unittest discover tests`):
  * Plumbing and ledger mechanics (17 tests in `tests/test_pipeline.py`).
  * Paraphrase validation and documented brittle boundary conditions (4 tests in `tests/test_generalization.py`).
