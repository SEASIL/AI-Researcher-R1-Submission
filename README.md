# AI Researcher - R1 Submission: Architecture Under a Fixed, Weak Model

**Candidate:** Sekh Asif Sohal

**Run (Python 3.11+, `pip install -r requirements.txt`; place `.env` in `candidate_package/`, never commit it):**
```bash
./run <items.json> --budget <1x|3x|10x> --out <answers.json>
python3 candidate_package/score.py candidate_package/visible_key.json answers.json candidate_package/items.json
python run_ablations.py --runs 3        # reproduces ablation table below via live endpoint
python -m unittest tests.test_pipeline  # 17 offline tests: mechanics, budget ledger, no retries
python -m unittest discover tests       # 21 offline tests: full test suite (NO network calls)
```
*Note: If `./run` gives `Permission denied`, use `python run <items.json> --budget 1x --out answers.json` or `chmod +x run`. `run_ablations.py --reuse` requires `ablation_cache/`, which is populated after a live run and omitted from the ZIP archive.*
*`answers/` holds the answers from the final live runs (one run per budget, scored 31.7% / 30.0% / 30.0%).*

---

Sampling: `temperature=1.0`, `top_p=0.95`, reasoning off (`extra_body={"reasoning": {"enabled": False}}`), `X-Item-Id` header passed on all calls. Tested on Python 3.11.9 and 3.12.3. Calls per item: 1x = 1, 3x = 3, 10x = 5 (ceiling 10). Evaluated over 3 runs with `run_ablations.py --runs 3` against the live endpoint (mean, min-max in parentheses).

## 1. Characterising the Model Before Designing Around It
Without a harness, zero-shot answers score **0.0% macro exact match**. The bottleneck is structural: solving requires searching 5! × 3! = 720 joint schedules (unique/ambiguous) or isolating a minimal unsatisfiable subset (inconsistent)—tasks an 8B non-reasoning model cannot reliably perform under all-or-nothing scoring. However, the model can perform local extraction: classifying whether an isolated clue line imposes a constraint, identifying its relation type, and extracting its arguments.

Our architecture restricts the model strictly to local extraction, offloading combinatorial search, consistency verification, and conflict isolation to deterministic algorithms. A symbolic regex baseline with no model achieves **71.7% macro** (unique 80%, ambiguous 75%, inconsistent 60%), while Claude Sonnet 5 scored **67.5%**. Our architecture scores **30.0% macro** (27%–32%) at 1x, **28.3%** at 3x, and **30.0%** at 10x. The flat scaling curve (~30/28/30) indicates systematic model misreadings across draws rather than random slips that vote out. Precision and recall are both limiting: at 1x, 24/60 true-unique and 21/60 true-ambiguous items are declared inconsistent due to spurious noise extraction or inverted relational directions, while 17/60 true-unique items are under-constrained as ambiguous due to missed constraints (counts summed over 3 runs of 20 items each).

## 2. System Architecture & Component Rationale
1. **Model Extraction (Sole Model Use):** The model processes lines 1..N and returns a single JSON array classifying each line as `NONE` or mapping it to one of nine relation schemas. Forcing explicit verdicts across all lines cuts missed constraints; hedges carry full semantic force.
2. **Grounding Verification:** Constraint proposals are dropped unless all names, stations, and times appear verbatim in the cited line. This converts temperature-1.0 hallucinations into dropped constraints.
3. **Regex Slot Repair (Narrow Fallback):** If slot names fail verbatim grounding but a strict regex matches the identical relation type on that line, regex slots repair the proposal while keeping the model's semantic verdict binding.
4. **Per-Line Plurality Voting (3x, 10x):** Multi-sample budgets vote per line; plurality wins. A NONE verdict counts as a vote for no constraint; ties go to the extracted constraint.
5. **Exhaustive Constraint Solver:** Filters all 720 candidate schedules: 1 remaining → `unique`, 2–4 → `ambiguous` (returning all), 0 → `inconsistent`.
6. **Line-Level Conflict Minimizer:** Iteratively drops statements one-by-one to extract a minimal contradictory subset, quoted whole and verbatim.
7. **Budget Ledger & Verification:** Calls are pre-reserved in a thread-safe `CallLedger` before dispatch and never retried; exceeding the cap raises `BudgetExceeded`. 21 offline unit tests (17 in `test_pipeline`, 4 in `test_generalization`) verify plumbing, budget ledger enforcement, and mechanics without network calls, saying nothing about Granite's extraction quality.

## 3. Ablation Table (Macro Exact Match, 60 Visible Items, 3 Runs)
Each arm deterministically replays identical paired model samples. Detailed per-kind breakdowns and confusion matrices are in [EXPERIMENTS.md](EXPERIMENTS.md).

| Arm | 1x | 3x | 10x |
| :--- | :--- | :--- | :--- |
| full | 30.0% (27%-32%) | 28.3% (28%-28%) | 30.0% (27%-33%) |
| - regex slot repair | 30.0% (27%-32%) | 28.3% (28%-28%) | 30.0% (27%-33%) |
| - grounding check | 30.6% (27%-33%) | 27.8% (27%-30%) | 28.9% (23%-33%) |
| + distractor filter | 30.6% (27%-33%) | 28.9% (28%-30%) | 30.0% (27%-33%) |
| aggregate = first | 30.0% (27%-32%) | 30.0% (27%-32%) | 30.0% (27%-32%) |
| aggregate = union | 30.0% (27%-32%) | 23.9% (22%-25%) | 18.9% (18%-20%) |
| - line-level core | 30.0% (27%-32%) | 28.3% (28%-28%) | 30.0% (27%-33%) |
| model output blanked | 0.0% (0%-0%) | 0.0% (0%-0%) | 0.0% (0%-0%) |
| symbolic only (no model) | 71.7% | - | - |

`full` and `first sample` are within run-to-run noise on 60 items; I do not claim voting beats a single sample. Union is the least stable arm: 18.9% at 10x in this 3-run set, but highest at 10x (33.3%) in an earlier independent 3-run set with the same code and different draws. I treat 'additive union over-constrains the solver' as a hypothesis, not a finding. Removing grounding or adding the distractor filter shifts scores within noise. Blanking model output gives 0.0%, so answers depend on the model.

## 4. What Was Built and Removed
- **Regex Re-Derivation of Constraints:** Bypassed model extraction and collapsed on phrasing shifts; removed to ensure the model genuinely performs extraction.
- **Additive Union Across Multi-Sample Draws:** Dropped because accumulated noisy proposals across draws tend to over-constrain the solver into false contradictions (18.9% at 10x in one 3-run set; unstable across runs, so a hypothesis).
- **HTTP Retry Loops:** Removed to guarantee strict budget ledger adherence; failed calls consume their reserved budget slot without retrying.
- **Hand-Written Distractor List:** Excluded from the default pipeline (`+ distractor filter` arm) because fixed phrase lists overfit to the visible prompt distribution.

## 5. Model-Based vs. Symbolic Extraction & Generalization
Extraction is **model-based**: Granite's emitted relation types and slots directly determine solver constraints. Symbolic code handles header parsing, grounding validation, schedule search, and minimal conflict isolation.

**Generalization & Author Variance:**
To evaluate sensitivity beyond the 60 visible items, we benchmarked on a proxy dev set (`paraphrased_items.json`, 58% of clue lines rewritten with rule-based synonyms) scored against a remapped citation key (`paraphrased_key.json`). On this proxy set, the template regex baseline falls from **71.7% to 21.7%**, whereas our model architecture scores **33.9% macro** at 1x. This benchmark demonstrates robustness to mild synonym rewrites, not generalization to a different author, phrasing pool, or structural template; real performance on unseen problem logic remains unknown (see [EXPERIMENTS.md](EXPERIMENTS.md)).

*Brittleness Points:* (a) A closed 9-relation schema cannot represent non-standard constraints ("at least two blocks apart", disjunctions). (b) Grounding requires exact verbatim tokens, failing on pronouns, nicknames, or colloquial timestamps. (c) Plurality voting cannot correct correlated misreadings across draws.

## 6. Where It Breaks & A One-Month Roadmap
**Failure Modes:** Precision and recall are both limiting bottlenecks (24/60 true-unique and 21/60 true-ambiguous items declared inconsistent at 1x, summed over 3 runs of 20 items each). Missed constraints leave items under-constrained (`unique` → `ambiguous`), while spurious constraints from noise lines or inverted directions (`direct_after` vs. `before_person`) turn 45/120 unique or ambiguous items into false contradictions (`unique`/`ambiguous` → `inconsistent`).

**With a Month:**
1. *Disjoint Paraphrase Benchmark:* Construct a phrasing-disjoint evaluation suite to trace per-relation precision and recall line-by-line.
2. *Calibrated Noise Filter:* Implement confidence gating or a second-pass verifier to discard weak proposals on non-scheduling lines.
3. *Soft Grounding & Entity Resolution:* Add an alias resolver to bind pronouns and colloquial times to rota entities under consistency constraints.
4. *Targeted Differential Querying:* Rather than re-sampling full pages at 3x/10x, direct extra calls to specific ambiguous slots in surviving schedules.
5. *Directional Self-Verification:* Explicitly prompt the model to check ordering polarity before passing constraints to the solver.
