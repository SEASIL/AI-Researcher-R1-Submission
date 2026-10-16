# AI Researcher - R1 Submission: architecture under a fixed, weak model

**Candidate:** Sekh Asif Sohal

**Run (Python 3.11+, `pip install -r requirements.txt`; put the provided `.env` in `candidate_package/`, never commit it):**
```
./run <items.json> --budget <1x|3x|10x> --out <answers.json>
python3 candidate_package/score.py candidate_package/visible_key.json answers.json candidate_package/items.json
python run_ablations.py --runs 3        # reproduces the ablation table below
python -m unittest tests.test_pipeline  # plumbing tests with a mock model, no network
```

---


Sampling on every call: temperature 1.0, top_p 0.95, reasoning off, `X-Item-Id` set. Python 3.11+ (tested on 3.12.3).
Calls per item: 1x = 1, 3x = 3, 10x = 5 (cap 10). Numbers below are measured over 3 runs using `python run_ablations.py --runs 3` against the live endpoint (mean across runs, min-max shown in parentheses).

## 1. Characterising the model before designing around it
The brief reports 0.0% macro exact match for one-shot answers. The failure is structural, not a matter of prompting: a correct answer needs a search over 5! x 3! = 720 joint schedules (unique/ambiguous) or a minimal unsatisfiable subset (inconsistent), which an 8B model without reasoning cannot do reliably, and "all 2-4 assignments" or "exactly the minimal conflict" offers no partial credit. What it should do well is local: read one sentence and say which relation it expresses and between whom. So the design asks the model only for that, and does all search in code.
A second measurement fixed my baseline for honesty: running only my template regexes over every line, with no model at all, scores **71.7% macro** (unique 80%, ambiguous 75%, inconsistent 60%) on the visible set. Any claim that the model adds value has to be measured against that floor, and any system that mostly reproduces it is symbolic, not model-based.

## 2. What the system is, and why each part exists
1. **Model extraction (the only model use).** One JSON array of `{line_no, type, slots}` over nine relation types; the prompt defines each slot's direction. The model decides which lines are statements and what they mean. Hedges are told to carry full force.
2. **Grounding check.** A proposal is kept only if its type and line exist and every name, station and time is real and appears in the cited line. This turns a temperature-1.0 slip (a name from a neighbouring line) into a dropped constraint instead of a wrong one. The code never creates a constraint.
3. **Regex slot repair (narrow).** If slots fail grounding but the template regex finds the same relation type on that line, regex slots are used. The model's reading of the sentence stays binding; a failed or empty model response is not rescued.
4. **Per-line vote across samples (3x, 10x).** Each sample proposes a reading per line; the plurality reading wins, and a sample that skips a line votes "no constraint". This replaced an additive repair loop (section 4).
5. **Exhaustive solver.** All 720 schedules filtered by the constraints: 1 left -> unique, 2-4 -> ambiguous (all given), 0 -> inconsistent.
6. **Line-level deletion filter.** Dropping whole statements one at a time gives a set that is contradictory and minimal at the unit the scorer checks; statements are quoted whole and verbatim.
**Budget integrity.** Each call is counted in a per-item ledger before it is sent, never retried (a failed call still counts and contributes nothing), and a call over the cap raises. 17 tests cover this with a mock model; they check plumbing, not extraction quality.

## 3. Ablation (macro exact match, 60 visible items)
Each arm is a deterministic replay of the same cached model samples, so differences come from the component. 1x/3x/10x share draws within a run.

| Arm | 1x | 3x | 10x |
| :--- | :--- | :--- | :--- |
| full | 28.3% (27%-30%) | 31.1% (28%-33%) | 30.0% (25%-33%) |
| - regex slot repair | 28.3% (27%-30%) | 31.1% (28%-33%) | 29.4% (25%-33%) |
| - grounding check | 24.4% (23%-25%) | 25.6% (23%-28%) | 27.8% (23%-30%) |
| + distractor filter | 28.3% (27%-30%) | 31.1% (28%-33%) | 30.0% (25%-33%) |
| aggregate = first sample | 28.3% (27%-30%) | 28.3% (27%-30%) | 28.3% (27%-30%) |
| aggregate = union of samples | 28.3% (27%-30%) | 31.1% (30%-32%) | 33.3% (32%-35%) |
| - line-level conflict filter | 28.3% (27%-30%) | 31.1% (28%-33%) | 30.0% (25%-33%) |
| model output blanked | 0.0% (0%-0%) | 0.0% (0%-0%) | 0.0% (0%-0%) |
| symbolic only, no model | 71.7% (measured, no calls) | - | - |

### Per-kind rates for `full` (mean over 3 runs):

| Budget | unique | ambiguous | inconsistent |
| :--- | :--- | :--- | :--- |
| 1x | 23.3% (20%-25%) | 21.7% (20%-25%) | 40.0% (35%-45%) |
| 3x | 25.0% (20%-30%) | 25.0% (15%-30%) | 43.3% (35%-50%) |
| 10x | 25.0% (20%-30%) | 18.3% (5%-25%) | 46.7% (40%-50%) |

### Confusion matrices: Declared kind (columns) vs true kind (rows), `full`, summed over 3 runs:

**1x:**
| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 17 | 34 | 9 | 0 |
| ambiguous | 3 | 51 | 6 | 0 |
| inconsistent | 7 | 17 | 36 | 0 |

**3x:**
| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 33 | 8 | 0 |
| ambiguous | 2 | 51 | 7 | 0 |
| inconsistent | 11 | 14 | 35 | 0 |

**10x:**
| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 34 | 7 | 0 |
| ambiguous | 3 | 51 | 6 | 0 |
| inconsistent | 11 | 12 | 37 | 0 |

The confusion matrices show the system's honest failure mode: true `unique` items are predominantly declared `ambiguous` (34/60 times at 1x, 33/60 at 3x, 34/60 at 10x) because a missed constraint leaves multiple consistent schedules, rather than hallucinating false constraints that would turn them into false contradictions. Furthermore, grounding filtering is essential: removing grounding drops performance by ~4% across budgets (24.4% vs 28.3% at 1x) by allowing off-target tokens into constraints. Blanking model output collapses macro exact match to 0.0%, confirming that correct answers strictly depend on model extraction.

## 4. Built, then removed
- **Regex re-derivation of every constraint, with the model only choosing lines.** Removed: it made the model nearly irrelevant (the 71.7% floor above) and would break on new wording.
- **Additive "repair" and "rescan" passes at 3x/10x.** Removed: they can only add constraints, so one hallucinated constraint turns an ambiguous item into a false contradiction. The previous version reported 71.1 / 72.8 / 50.6% at 1x / 3x / 10x with this loop; I treat the 10x drop as a hypothesis until the `union` arm reproduces it.
- **Retry loop in the HTTP client.** Removed: every retry is a call at the proxy and breaks "exactly one call" at 1x.
- **Hand-written distractor phrase list.** Kept only as an ablation arm: it is tuned to this set's wording.

## 5. Model-based or symbolic, and notes written by other people
Extraction is **model-based**: the type and slots the model emits are what reach the solver. Symbolic code does header parsing, grounding, repair on same-type agreement, the solver and the conflict filter. The regexes are a floor and a narrow repair, not the extractor.
I have not tested other phrasings, so the honest answer is a list of what I expect to break. (a) The nine-relation schema is closed: "not adjacent", "at least two blocks apart", "either X or Y" have no representation and would be dropped, giving under-constrained (ambiguous) answers. (b) Grounding requires the exact name, station word or `HH:MM` in the line; nicknames, pronouns ("she"), "the eleven o'clock" or "the morning slot" are rejected, again silently dropping a constraint. (c) Header parsing is a regex for this header wording. (d) Votes cannot fix a systematic misreading, only random slips. The model's paraphrase tolerance is the reason to use it; the schema and grounding strictness are where this design is brittle.

## 6. Where it breaks, and a month
Failure directions: a missed constraint makes `unique` look `ambiguous` (the honest direction); a wrong-but-grounded constraint (usually a flipped `direct_after` / `before_person`) makes an item falsely `inconsistent` or `unique` with the wrong schedule; a contradiction is only cited if both of its statements were extracted.
With a month: (1) build a paraphrase-disjoint dev set and report accuracy by relation type and by phrasing, since the held-out set is graded that way; (2) per-relation confusion matrices to find which relations the model flips; (3) widen the schema and soften grounding (normalised times, name aliases) and measure each against false constraints; (4) a targeted, accepted-only-if-grounded check on the specific cell where two surviving schedules differ, using the 3x/10x budget on items that are still ambiguous rather than on everything.
