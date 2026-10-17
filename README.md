# AI Researcher - R1 Submission: architecture under a fixed, weak model

**Candidate:** Sekh Asif Sohal

**Run (Python 3.11+, `pip install -r requirements.txt`; put `.env` in `candidate_package/`, never commit it):**
```bash
./run <items.json> --budget <1x|3x|10x> --out <answers.json>
python3 candidate_package/score.py candidate_package/visible_key.json answers.json candidate_package/items.json
python run_ablations.py --runs 3        # reproduces ablation table below
python -m unittest tests.test_pipeline  # 17 offline tests: mechanics, budget ledger, no retries
python -m unittest discover tests       # 21 offline tests: full test suite (NO network calls)
```

*(Note: `tests/eval_comparison.py` is the only script that can call the live API; all unit tests use local mocks with zero network calls).*

---

Sampling: temp 1.0, top_p 0.95, reasoning off, `X-Item-Id` set. Python 3.11+ (tested on Python 3.11.9 and 3.12.3).
Calls per item: 1x = 1, 3x = 3, 10x = 5 (cap 10). Evaluated over 3 runs with `run_ablations.py --runs 3` against live endpoint (mean, min-max in parentheses).

## 1. Characterising the model before designing around it
Without a harness, one-shot answers score 0.0% macro exact match. The failure is structural: solving requires searching 5! x 3! = 720 joint schedules (unique/ambiguous) or isolating a minimal unsatisfiable subset (inconsistent)—tasks an 8B model without reasoning cannot perform reliably under all-or-nothing scoring. It can, however, attempt local extraction: identifying a single clue's relation and arguments. Our design restricts the model strictly to local extraction, delegating all combinatorial search to deterministic code.

A template regex baseline with no model scores **71.7% macro** (unique 80%, ambiguous 75%, inconsistent 60%), and Claude Sonnet 5 scored **67.5%**. Our architecture scores **30.0% macro** (27%-32%) at 1x, **28.3%** at 3x, and **30.0%** at 10x. The flat scaling curve (~30/28/30) reveals systematic model misreadings across draws rather than random slips that vote out. The 71.7% floor proves solver capability under correct constraints. While forced enumeration halved missed constraints (true `unique` called `ambiguous` fell from 34 to 17/60), false contradictions rose from 15 to 45 of 120. Extraction precision (spurious constraints, likely from noise lines, and flipped directions) is now as limiting as recall.

## 2. What the system is, and why each part exists
1. **Model extraction (only model use).** One JSON array per call. The model evaluates every numbered line (`{"line_no": k, "type": "NONE"}` or constraint object) across nine relation types. Compelling evaluation cuts missed constraints; hedges carry full force.
2. **Grounding check.** Proposals are dropped unless type and line exist and all names, stations, and times appear verbatim in that line. Converts temperature-1.0 hallucinations into dropped constraints. The code never invents constraints.
3. **Regex slot repair (narrow).** If slots fail grounding but a template regex matches the identical relation type on that line, regex slots are used. The model's semantic reading remains binding.
4. **Per-line vote across samples (3x, 10x).** Samples vote per line; plurality wins, skipping votes "no constraint", filtering single-sample noise.
5. **Exhaustive solver.** Evaluates all 720 candidate schedules: 1 remaining -> unique, 2-4 -> ambiguous (all returned), 0 -> inconsistent.
6. **Line-level deletion filter.** Drops statements one-by-one to extract a minimal contradictory subset, quoted whole and verbatim.
**Budget integrity & tests.** Calls are pre-reserved in a thread-safe `CallLedger` before dispatch and never retried; calls over the cap raise `BudgetExceeded`. **21 offline unit tests** verify budget adherence and mechanics without network calls.

## 3. Ablation (macro exact match, 60 visible items, 3 runs)
Each arm deterministically replays cached model samples. 1x/3x/10x share draws within each run. Detailed per-kind tables, confusion matrices, and prompt comparisons are in [EXPERIMENTS.md](EXPERIMENTS.md).

| Arm | 1x | 3x | 10x |
| :--- | :--- | :--- | :--- |
| full | 30.0% (27%-32%) | 28.3% (28%-28%) | 30.0% (27%-33%) |
| - regex slot repair | 30.0% (27%-32%) | 28.3% (28%-28%) | 30.0% (27%-33%) |
| - grounding check | 30.6% (27%-33%) | 27.8% (27%-30%) | 28.9% (23%-33%) |
| + distractor filter | 30.6% (27%-33%) | 28.9% (28%-30%) | 30.0% (27%-33%) |
| aggregate = first sample | 30.0% (27%-32%) | 30.0% (27%-32%) | 30.0% (27%-32%) |
| aggregate = union of samples | 30.0% (27%-32%) | 23.9% (22%-25%) | 18.9% (18%-20%) |
| - line-level conflict filter | 30.0% (27%-32%) | 28.3% (28%-28%) | 30.0% (27%-33%) |
| model output blanked | 0.0% (0%-0%) | 0.0% (0%-0%) | 0.0% (0%-0%) |
| symbolic only, no model | 71.7% (measured, no calls) | - | - |

While forced enumeration halved missed constraints (true `unique` called `ambiguous` fell from 34 to 17/60), 45 of 120 unique or ambiguous items are now falsely declared inconsistent (up from 15). A plausible hypothesis—not yet checked against per-line traces—is that forcing verdicts on every line compels the model to pull spurious constraints out of noise lines, alongside flipped relational directions (`direct_after` / `before_person`). Precision and recall are now equally limiting bottlenecks.

At 3x, plurality voting scores 28.3% vs 30.0% for the first sample; at 10x, both tie at 30.0%. Voting does not beat the first sample alone, but prevents the severe collapse of additive union, which drops to 23.9% at 3x and **18.9% at 10x** as accumulated noisy proposals over-constrain the solver. Several ablation arms show no measurable effect: regex slot repair and the line-level conflict filter score identically to `full` across all budgets (30.0% / 28.3% / 30.0%), removing grounding does not reduce score (30.6% at 1x), and adding the distractor filter does not hurt (30.6% at 1x), falling within run noise on 60 items. Blanking model output collapses score to 0.0%, confirming strict model dependence.

## 4. Built, then removed
- **Regex re-derivation of constraints with model choosing lines.** Removed: bypassed the model (scoring the 71.7% floor) and broke on wording shifts.
- **Additive union across multi-sample budgets.** Removed: collapses to 18.9% at 10x from accumulating noisy constraints. Plurality voting avoids this (30.0% at 10x), though ties the first sample alone (30.0%).
- **Retry loops in HTTP client.** Removed: retries violate the per-item budget at 1x.
- **Hand-written distractor phrase list.** Excluded from default (`+ distractor filter` arm): overfitted to visible phrasing.

## 5. Model-based or symbolic, and generalization disclosure
Extraction is **model-based**: Granite's emitted types and slots directly govern solver constraints. Symbolic code handles header parsing, grounding validation, search, and minimal conflict extraction.

**Generalization & Self-Made Proxy Dev Set:**
To test sensitivity beyond the 60 visible items, we evaluated a self-made proxy dev set (`paraphrased_items.json`) where 58% of clue lines were rewritten with rule-based synonyms, evaluated against a remapped citation key (`paraphrased_key.json`). On this proxy, the regex baseline collapses from 71.7% to 21.7%, whereas our model architecture scores 33.9% macro at 1x (recovering ambiguous items compared to 23.9% under visible-idiom prompting). Because the proxy scores higher than the visible set (33.9% vs 30.0%), it functions as a mild lexical-rewrite probe rather than an out-of-distribution structural test; real performance on unseen problem logic remains unknown (see [EXPERIMENTS.md](EXPERIMENTS.md)).

Stated plainly: our ~30% macro score remains far below the 71.7% visible symbolic floor and 67.5% frontier reference. While the regex floor proves solver capability, 8B extraction precision and recall remain equal bottlenecks.

Known points of brittleness: (a) Closed 9-relation schema cannot represent non-standard constraints ("at least two blocks apart", disjunctions). (b) Grounding requires exact verbatim tokens; nicknames, pronouns, and colloquial times fail grounding. (c) Rigid bay header parsing. (d) Plurality voting cannot correct correlated model misreadings across draws.

## 6. Where it breaks, and a month
Failure directions: Precision is as limiting as recall. Missed constraints leave items under-constrained (`unique` -> `ambiguous`), while spurious constraints (hypothesized from noise lines, or flipped relational directions) turn 45/120 unique or ambiguous items into false contradictions (`unique`/`ambiguous` -> `inconsistent`).
With a month: (1) Construct a paraphrase-disjoint benchmark and trace per-relation precision and recall line-by-line. (2) Implement a calibrated noise-line filter to drop weak constraint proposals before solving. (3) Soften grounding with an entity alias resolver (handling pronouns and colloquial times) constrained by consistency checks. (4) Differential querying: rather than re-sampling the entire page at 3x/10x, direct extra calls to targeted questions about divergent slots of surviving ambiguous schedules. (5) Directional self-verification: check extracted ordering relations to catch flipped pairs before solving.
