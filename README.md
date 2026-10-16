# AI Researcher - R1 Submission: architecture under a fixed, weak model

**Candidate:** Sekh Asif Sohal

**Run (Python 3.11+, `pip install -r requirements.txt`; put the provided `.env` in `candidate_package/`, never commit it):**
```bash
./run <items.json> --budget <1x|3x|10x> --out <answers.json>
python3 candidate_package/score.py candidate_package/visible_key.json answers.json candidate_package/items.json
python run_ablations.py --runs 3        # reproduces the ablation table below
python -m unittest tests.test_pipeline  # 17 offline tests: mechanics, budget ledger, no retries (NO network)
python -m unittest discover tests       # 21 offline tests: full test suite (NO network)
```

*(Note: `tests/eval_comparison.py` is the only test/eval script that can make live API calls when re-sampling; all unit tests in `tests/test_pipeline.py` and `tests/test_generalization.py` use local mocks and make zero network calls).*

---

Sampling on every call: temperature 1.0, top_p 0.95, reasoning off, `X-Item-Id` set. Python 3.11+ (tested on 3.11.9 and 3.12.3).
Calls per item: 1x = 1, 3x = 3, 10x = 5 (cap 10). Numbers below are measured over 3 runs using `python run_ablations.py --runs 3` against the live endpoint (mean across runs, min-max shown in parentheses).

## 1. Characterising the model before designing around it
The brief reports 0.0% macro exact match for one-shot answers without a harness. The failure is structural: a correct answer requires searching over 5! x 3! = 720 joint schedules (unique/ambiguous) or isolating a minimal unsatisfiable subset (inconsistent), which an 8B model without reasoning cannot do reliably, and "all 2-4 assignments" or "exactly the minimal conflict" offers no partial credit. What it can attempt is local: reading one sentence and extracting which relation it expresses and between whom. The design asks the model only for that, delegating all search to deterministic code.

An honesty baseline fixes the ceiling: running template regexes over every line with no model scores **71.7% macro** (unique 80%, ambiguous 75%, inconsistent 60%) on the visible set, and Claude Sonnet 5 scored **67.5%**. Our architecture scores **30.0% macro** (27%-32%) at 1x, **28.3%** at 3x, and **30.0%** at 10x. The 1x/3x/10x scaling curve is flat (~30/28/30); repeated sampling does not help macro score. This points to systematic model misreadings (such as relation blind spots or flipped slot directions shared across draws) rather than random slips that could be averaged out. Stated plainly: the regex floor of 71.7% is a lower bound on what the solver can do with correct constraints. The bottleneck is the 8B model's extraction: while forced enumeration cut true-unique items declared ambiguous from 34 to 17 of 60, true-unique items declared inconsistent rose from 9 to 24 and true-ambiguous items declared inconsistent rose from 6 to 21 (45 of 120 unique or ambiguous items are now falsely declared inconsistent, up from 15 of 120 before). Extraction PRECISION (false constraints, likely from forcing the model to evaluate noise lines, and flipped directions) is now as limiting as recall.

## 2. What the system is, and why each part exists
1. **Model extraction (the only model use).** One JSON array per call. The model must address every numbered line (forced per-line enumeration: `{"line_no": k, "type": "NONE"}` or the constraint object) over nine relation types. Forced enumeration cuts missed lines by compelling the model to evaluate every statement. Hedges carry full force.
2. **Grounding check.** A proposal is accepted only if its type and line exist and every name, station, and time appears verbatim in the cited line. This converts temperature-1.0 hallucinations (names from adjacent lines or placeholder tokens) into dropped constraints rather than corrupting the solver. The code never invents constraints.
3. **Regex slot repair (narrow).** If slots fail grounding but the template regex detects the exact same relation type on that line, regex slots are used. The model's semantic reading remains binding; empty or failed model outputs are never rescued.
4. **Per-line vote across samples (3x, 10x).** Each sample votes per line; plurality wins, and skipping a line votes "no constraint". This acts as a precision filter against single-sample noise, avoiding the catastrophic over-constraining of additive aggregation (section 4).
5. **Exhaustive solver.** All 720 schedules are filtered by the accepted constraints: 1 remaining -> unique, 2-4 -> ambiguous (all returned), 0 -> inconsistent.
6. **Line-level deletion filter.** Dropping whole statements one at a time extracts a contradictory subset that is minimal at the statement level; statements are quoted whole and verbatim.
**Budget integrity & tests.** Each call is pre-reserved in a thread-safe `CallLedger` before dispatch and never retried (failures yield zero constraints), with calls over the cap raising `BudgetExceeded`. **21 unit and generalization tests** verify budget adherence, plumbing, paraphrase extraction, and boundary conditions with mock models and offline tests.

## 3. Ablation (macro exact match, 60 visible items, 3 runs)
Each arm is a deterministic replay of the same cached model samples, isolating component contributions. 1x/3x/10x share draws within each run.

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

### Per-kind rates for `full` (mean over 3 runs):

| Budget | unique | ambiguous | inconsistent |
| :--- | :--- | :--- | :--- |
| 1x | 26.7% (20%-30%) | 26.7% (25%-30%) | 36.7% (35%-40%) |
| 3x | 28.3% (25%-30%) | 21.7% (20%-25%) | 35.0% (35%-35%) |
| 10x | 28.3% (25%-35%) | 26.7% (25%-30%) | 35.0% (30%-40%) |

### Confusion matrices: Declared kind (columns) vs true kind (rows), `full`, summed over 3 runs:

**1x:**
| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 17 | 24 | 0 |
| ambiguous | 3 | 36 | 21 | 0 |
| inconsistent | 10 | 8 | 42 | 0 |

**3x:**
| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 18 | 19 | 23 | 0 |
| ambiguous | 4 | 34 | 22 | 0 |
| inconsistent | 9 | 7 | 44 | 0 |

**10x:**
| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 17 | 24 | 0 |
| ambiguous | 4 | 31 | 25 | 0 |
| inconsistent | 9 | 4 | 47 | 0 |

The confusion matrices show the impact of forced enumeration: true `unique` items misdeclared as `ambiguous` dropped from 34/60 (baseline) to 17/60, cutting missed constraints in half. However, errors shifted to precision: true-unique declared inconsistent rose from 9 to 24, and true-ambiguous declared inconsistent rose from 6 to 21 (45 of 120 unique or ambiguous items are now falsely declared inconsistent, up from 15 of 120). Forcing the model to output a verdict on every line compels it to extract spurious constraints from noise lines, making precision an equal failure mode alongside recall.

Regarding multi-sample aggregation: at 3x, plurality voting scores 28.3% while the first sample alone scores 30.0%; at 10x, both tie at 30.0%. Voting is not shown to beat using the first sample alone; its only role is avoiding the severe degradation of additive union, which collapses to 23.9% at 3x and **18.9% at 10x** as accumulated noisy constraints over-constrain items into false contradictions. Furthermore, several ablation arms show no measurable effect on this visible set: regex slot repair and the line-level conflict filter score identically to `full` across all budgets (30.0% / 28.3% / 30.0%), removing grounding does not reduce the score (30.6% at 1x), and adding the distractor filter does not hurt (30.6% at 1x). On 60 items, these differences fall within run-to-run noise. Blanking model output collapses macro exact match to 0.0%, confirming strict model dependence.

## 4. Built, then removed
- **Regex re-derivation of constraints with model choosing lines.** Removed: it bypassed the model (scoring the 71.7% floor) and broke on any wording shift.
- **Additive union across multi-sample budgets.** Removed as default: `aggregate = union` plummets to 18.9% at 10x because accumulating noisy constraint proposals across 5 samples rapidly creates false contradictions. Plurality voting avoids this degradation (30.0% at 10x), but is not shown to beat using the first sample alone (which also scores 30.0%).
- **Retry loops in the HTTP client.** Removed: retries violate the per-item proxy budget at 1x.
- **Hand-written distractor phrase list.** Excluded from default (`+ distractor filter` ablation arm): it is tuned to visible phrasing and does not generalize.

## 5. Model-based or symbolic, and generalization disclosure
Extraction is **model-based**: the type and slots emitted by Granite are what enter the solver. Symbolic code handles header parsing, grounding validation, search, and minimal conflict extraction.

**Generalization & Self-Made Proxy Dev Set:**
To test sensitivity to phrasing beyond the 60 visible items, we generated a self-made proxy dev set (`paraphrased_items.json`, generated by `tests/make_paraphrase_set.py`) where 58.0% of clue lines were rewritten using rule-based synonym substitutions while preserving semantic truth. Because inconsistent items require verbatim citations of conflicting lines, the answer key is remapped to the rewritten sentences (`paraphrased_key.json`) so citation checks evaluate the actual text rather than failing on string mismatches (evaluating without remapping is a scoring artifact that drops citation credit).

Measured across 3 runs at 1x budget:
- **Visible Set (`items.json`):**
  - Old prompt (template idioms): **28.3% macro** (26.7%-30.0%) [unique: 23.3%, ambiguous: 21.7%, inconsistent: 40.0%]
  - New prompt (generic logic + forced enumeration): **30.0% macro** (26.7%-31.7%) [unique: 26.7%, ambiguous: 26.7%, inconsistent: 36.7%]
  - The new prompt shows **no meaningful change on the visible set** (30.0% vs 28.3%, run ranges overlap: 26.7%-31.7% vs 26.7%-30.0%).
- **Self-Made Proxy Dev Set (`paraphrased_items.json` with remapped key):**
  - Old prompt: **23.9% macro** (21.7%-26.7%) [unique: 16.7%, ambiguous: 6.7%, inconsistent: 48.3%]
  - New prompt: **33.9% macro** (33.3%-35.0%) [unique: 33.3%, ambiguous: 30.0%, inconsistent: 38.3%]
  - The new prompt shows a **gain on the proxy set** (33.9% vs 23.9%, run ranges do not overlap: 33.3%-35.0% vs 21.7%-26.7%), primarily by recovering ambiguous items (30.0% vs 6.7%).
- **Comparison with the Symbolic Floor:**
  - On the visible set, the regex baseline scores **71.7% macro**.
  - On the paraphrased proxy, the regex-only floor falls from **71.7% to 21.7%**, while Granite extraction stays near 30% (30.0% on visible, 33.9% on proxy).
- **Scope and Limitations of the Proxy:**
  - The proxy set scores higher than the visible set (33.9% vs 30.0%), showing that it is a mild lexical-rewrite proxy, not a harder or unseen-structure test.
  - Real held-out performance on genuinely unseen problem structures or out-of-distribution phrasing remains unknown.

Stated plainly: the system at ~30% macro remains far below the 71.7% visible symbolic floor and the 67.5% frontier reference. While the regex floor of 71.7% is a lower bound on what the solver can do with correct constraints, 8B model extraction precision (false constraints on noise lines, flipped directions) and recall (omitting constraints) are equally limiting bottlenecks.

Known points of brittleness: (a) The 9-relation schema is closed: statements expressing non-standard relations ("at least two blocks apart", "either X or Y") are unrepresented. (b) Grounding requires exact names, stations, or `HH:MM`; nicknames ("Dave"), pronouns ("she"), or non-standard times ("noon") fail grounding. (c) Header parsing relies on the standard bay header format. (d) Plurality voting cannot correct systematic model misreadings across draws.

## 6. Where it breaks, and a month
Failure directions: extraction precision is now as limiting as recall. While missed constraints leave items under-constrained (`unique` -> `ambiguous`), forced enumeration induces false constraints from noise lines or flipped directions (`direct_after` / `before_person`), turning 45/120 unique or ambiguous items into false contradictions (`unique`/`ambiguous` -> `inconsistent`).
With a month: (1) Construct a paraphrase-disjoint benchmark set and measure per-relation extraction precision and recall. (2) Implement a noise-line classifier or precision filter to drop weak constraint proposals before solving. (3) Soften grounding with an entity alias resolver (mapping pronouns and non-standard times) constrained by strict consistency checks. (4) Differential querying: rather than re-sampling the entire page at 3x/10x, direct extra calls to targeted questions about the specific divergent slots of surviving ambiguous schedules. (5) Directional self-verification: add a secondary check on extracted ordering relations to catch flipped pairs before solving.
