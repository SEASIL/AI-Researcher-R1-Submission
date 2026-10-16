# Changes in this revision

Copy your original `candidate_package/.env` back in before running (it is not included here, and must not be committed).

## 1. Model-first extraction (`pipeline.py`, `normalizer.py`)
* The model's `type` and slots are now what enter the solver. Before, `normalize_constraint` re-derived
  type/direction from regexes and the model only chose line numbers; a no-model run of that regex path alone scored 71.7% macro on the visible set.
* `validate_model_constraint` only accepts a proposal if the type is known, the line exists, every slot is a real name/station/block,
  slots are distinct, and each appears in the cited line. It never creates constraints.
* `regex_repair` is a narrow fallback: if slots fail grounding, regex slots are used only when the regex relation type equals the model's type.
* Lines the model skipped stay skipped. A failed or empty model response is NOT rescued by regexes (so answers depend on the model).
* The hand-written distractor list is off by default (`Config.distractor_filter`); it is an ablation arm.
* Prompt now defines each relation type's slots and direction; max_tokens 600 -> 800; truncated JSON is salvaged object by object.

## 2. Budget integrity (`pipeline.py`)
* `HttpModelClient`: one HTTP attempt per call, no retries, no sleeps. Every call is reserved in a per-item `CallLedger` BEFORE sending,
  so failures count and a call over the cap raises `BudgetExceeded`.
* 1x = 1 call, 3x = 3 calls, 10x = 5 calls (cap 10). Samples are combined by per-line plurality vote (`aggregate="vote"`), replacing the additive repair loop.
* `X-Item-Id`, temperature 1.0, top_p 0.95 and `reasoning: {enabled: false}` are on every call (tested).
* Items run in parallel (`CONCURRENCY` env, default 4); a `<out>.trace.json` records calls and rejects per item.

## 3. Conflicts (`solver.py`)
* Deletion filtering now works per statement (line), the scorer's unit, instead of per constraint.

## 4. Ablation (`run_ablations.py`)
* Samples the model once per run (5 draws/item), caches raw text, replays every arm on the same text. `--reuse` re-scores with no calls.
* Arms: full, - regex repair, - grounding, + distractor filter, aggregate first/union, - line-level core, model output blanked, symbolic-only floor.

## 5. Brief-compliance fixes (second pass)
* `run` and `candidate_package/run` had no execute bit, so the documented `./run ...` would fail with "Permission denied"; fixed and tested by executing `./run` directly.
* `run_ablations.py` replayed a stale cache by default; it now re-samples unless `--reuse` is given (the grader re-runs it).
* The `<out>.trace.json` side file is now opt-in (`TRACE=1`), so a graded run writes only the answers file.
* `BASE_URL` trailing slash stripped; Python version stated in `requirements.txt`.
* `README.md` is now the write-up (was REPORT.md), rewritten to the brief's required contents. Cells marked `[FILL]` need the real-endpoint ablation; the report is about two pages and may need trimming once filled.

## Tests
`python -m unittest tests.test_pipeline` (mock model: checks plumbing only, not extraction quality).

## Not done / unverified
No real-endpoint run was possible in the sandbox: no number in this revision has been measured against Granite.
`README.md` still has [FILL] cells; it previously described the old design and numbers; update it from `python run_ablations.py --runs 3`.
