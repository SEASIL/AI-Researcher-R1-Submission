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

