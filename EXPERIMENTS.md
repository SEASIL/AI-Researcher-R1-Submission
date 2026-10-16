# Experiment Log

## Baseline (Iteration 0)
- **Description**: Initial codebase as provided. Model extraction with basic prompt and 1-shot example; strict grounding check; regex repair when relation types match; per-line plurality voting across samples.
- **Results** (measured over 3 runs on Granite 4.2 8B, 60 visible items):
  - **1x macro**: 22.2% (22% - 23%) [unique: 20.0%, ambiguous: 18.3%, inconsistent: 28.3%]
  - **3x macro**: 23.9% (20% - 28%) [unique: 20.0%, ambiguous: 21.7%, inconsistent: 30.0%]
  - **10x macro**: 24.4% (22% - 27%) [unique: 21.7%, ambiguous: 23.3%, inconsistent: 28.3%]
  - **Symbolic floor** (no model): 71.7% macro
- **Diagnosis**:
  - Model extraction fails systematically in several identifiable ways:
    1. Relation confusion on ordering: Granite emitted `person_before_station` when comparing two people (because one person was mistakenly slotted into `station`) or inverted who works earlier vs later.
    2. Missing `between` relations: Sentences with natural betweenness phrasing ("whichever way round X and Y are, Z is between them", "Z is on after one of X and Y and before the other", "put Z between X and Y, though not necessarily next to either") were completely omitted by the model because the schema and prompt didn't clarify that these phrases express betweenness.
    3. Missing `direct_after`: Sentences like "there is no block between X and Y, in that order" or "X hands straight over to Y" were missed.
    4. Slot values: Model occasionally hallucinated non-entity tokens like `'one_of'`, `'someone'`, or `'null'` into person slots, causing grounding failure.

## Iteration 1 (Prompt & Normalizer Schema Refinement)
- **Description**:
  - Expanded `FEW_SHOT` to include examples of all 9 relation types, particularly ordering pairs (`before_person`, `person_before_station`, `assign_station`).
  - Refined `TYPES_DOC` to clarify slot directions and natural idioms (e.g. "whichever way round X and Y are", "hands straight over to", "done before X starts").
  - Added explicit rule preventing the model from emitting `person_before_station` when comparing two staff members.
  - Enhanced `normalizer.py` (`_canon` and `_in_line`) to strip possessive `'s` (e.g., `Alice's`), strip boundary punctuation, and normalize single-digit hour prefixes (e.g. `9:00` -> `09:00`).
- **Results** (measured over 3 runs on Granite 4.2 8B, 60 visible items):
  - **1x macro**: **28.3%** (27% - 30%) [unique: 23.3%, ambiguous: 21.7%, inconsistent: 40.0%]
  - **3x macro**: **31.1%** (28% - 33%) [unique: 25.0%, ambiguous: 25.0%, inconsistent: 43.3%]
  - **10x macro**: **30.0%** (25% - 33%) [unique: 25.0%, ambiguous: 18.3%, inconsistent: 46.7%]
  - **Symbolic floor** (no model): 71.7% macro
  - **Model output blanked**: 0.0%
- **Before vs After Delta**:
  - **1x macro**: +6.1% (22.2% -> 28.3%)
  - **3x macro**: +7.2% (23.9% -> 31.1%)
  - **10x macro**: +5.6% (24.4% -> 30.0%)
  - **Inconsistent resolution**: +11.7% at 1x (28.3% -> 40.0%), +13.3% at 3x (30.0% -> 43.3%), +18.4% at 10x (28.3% -> 46.7%).
- **Key Insights**:
  - The refined few-shot examples and schema guidance dramatically reduced the model's tendency to flip slot ordering or hallucinate stations for interpersonal comparisons.
  - Because inconsistent items require correctly extracting at least 3 mutually contradictory statements to cite the exact minimal unsat core, improving extraction fidelity had an outsized impact on the inconsistent score.
  - At 10x budget, voting slightly favours high-precision extraction on inconsistent items (46.7%) while occasionally under-calling ambiguous items when noisy samples filter out valid solutions.

## Iteration 2 (Generic Semantics, Invented Few-Shot, Forced Per-Line Enumeration)
- **Description**:
  - Eliminated all visible-set idioms and template-specific phrases ("whichever way round...", "hands straight over to...", "in the old arrangement") from `FEW_SHOT` and `TYPES_DOC`.
  - Replaced few-shot with invented entities: staff names (`Alex, Brooke, Connor, Diana, Ethan`), stations (`assembly, testing, dispatch`), blocks (`08:00, 10:00, 12:00, 14:00, 16:00`). Verified with automated script: 0 substring overlap with `items.json`.
  - Implemented forced per-line enumeration: prompt instructs Granite to output a verdict for every numbered line 1..N (`{"line_no": k, "type": "NONE"}` for non-scheduling lines, or the constraint object).
  - Enhanced `parse_model_json` to flatten nested `"slots"` and map `"name"` -> `"person"`.
  - Increased `MAX_TOKENS = 1200` to prevent truncation under full line enumeration.
- **Benchmark on Self-Made Proxy Dev Set (`paraphrased_items.json`, 58% lines rewritten, 3 runs at 1x)**:
  - *Context:* Rule-based synonym substitutions test sensitivity to phrasing shifts. Because inconsistent items require verbatim citations of conflicting lines, the answer key is remapped to the rewritten sentences (`paraphrased_key.json`) to accurately grade conflicting citations (scoring without remapping is an artifact of verbatim string mismatch).
  - **With Remapped Answer Key (`paraphrased_key.json`):**
    - **Old Prompt (with visible idioms)**: **23.9% macro** (21.7% - 26.7%) [unique: 16.7%, ambiguous: 6.7%, inconsistent: 48.3%]
    - **New Prompt (generic logic + forced enumeration)**: **33.9% macro** (33.3% - 35.0%) [unique: 33.3%, ambiguous: 30.0%, inconsistent: 38.3%]
    - The new prompt shows a **gain on the proxy set** (33.9% vs 23.9%, run ranges do not overlap: 33.3%-35.0% vs 21.7%-26.7%), primarily from recovering ambiguous items (30.0% vs 6.7%).
  - **Measured Comparison with the Symbolic Floor:**
    - On `items.json`: **71.7% macro** (unique: 80.0%, ambiguous: 75.0%, inconsistent: 60.0%)
    - On `paraphrased_items.json` (remapped key): the regex-only floor falls from **71.7% to 21.7%**, while Granite extraction stays near 30% (30.0% on visible, 33.9% on proxy).
  - **Scope and Limitations of the Proxy:**
    - The proxy set scores higher than the visible set (33.9% vs 30.0%), showing that it is a mild lexical-rewrite proxy, not a harder or unseen-structure test. Real held-out performance on genuinely unseen problem structures remains unknown.
- **Ablation Results on Visible Set (`items.json`, 3 runs on Granite 4.2 8B)**:
  - **1x macro**: **30.0%** (27% - 32%) [unique: 26.7%, ambiguous: 26.7%, inconsistent: 36.7%]
  - **3x macro**: **28.3%** (28% - 28%) [unique: 28.3%, ambiguous: 21.7%, inconsistent: 35.0%]
  - **10x macro**: **30.0%** (27% - 33%) [unique: 28.3%, ambiguous: 26.7%, inconsistent: 35.0%]
  - **Prompt comparison on visible set:** The new prompt shows **no meaningful change on the visible set** (30.0% vs 28.3%, run ranges overlap: 26.7%-31.7% vs 26.7%-30.0%).
  - **Symbolic floor**: 71.7% macro
  - **Model output blanked**: 0.0% (verifies 100% model dependency)
- **Key Empirical Insights**:
  1. **Recall vs. Precision Trade-off:** True `unique` declared `ambiguous` dropped from 34/60 down to 17/60 at 1x. While forced per-line enumeration cut missed constraints in half, errors shifted to precision: true-unique declared inconsistent rose from 9 to 24, and true-ambiguous declared inconsistent rose from 6 to 21 (45 of 120 unique or ambiguous items are now falsely declared inconsistent, up from 15 of 120). Forcing a verdict on every line compels the model to extract spurious constraints from noise lines, making precision an equal bottleneck alongside recall.
  2. **Flat Scaling Curve & Voting vs. First-Sample vs. Union:** The 1x/3x/10x scaling curve is flat (~30/28/30); repeated sampling does not help macro score. At 3x, plurality voting scores 28.3% while the first sample alone scores 30.0%; at 10x, both tie at 30.0%. Voting is therefore not shown to beat using the first sample alone, only to avoid union's severe degradation (collapsing to 23.9% at 3x and 18.9% at 10x as accumulated noisy constraints over-constrain items). Furthermore, regex slot repair and the line-level conflict filter score identically to `full` across all budgets, removing grounding does not reduce score (30.6% at 1x), and adding the distractor filter does not hurt (30.6% at 1x), showing these component differences fall within run noise on 60 items.
  3. **Honest assessment:** Stated plainly, the system scores ~30% macro across budgets, remaining far below the 71.7% visible symbolic floor and the 67.5% frontier reference. While the regex floor of 71.7% is a lower bound on what the solver can do with correct constraints, 8B model extraction precision (false constraints on noise lines, flipped directions) and recall (omitting constraints) are equally limiting bottlenecks.

