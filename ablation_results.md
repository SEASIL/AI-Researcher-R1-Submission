Ablation on 60 items, 3 run(s) per cell; macro exact match, mean (min-max across runs). Calls per item: 1x=1, 3x=3, 10x=5.

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

Per-kind rates for `full` (mean over runs):

| Budget | unique | ambiguous | inconsistent |
| :--- | :--- | :--- | :--- |
| 1x | 26.7% (20%-30%) | 26.7% (25%-30%) | 36.7% (35%-40%) |
| 3x | 28.3% (25%-30%) | 21.7% (20%-25%) | 35.0% (35%-35%) |
| 10x | 28.3% (25%-35%) | 26.7% (25%-30%) | 35.0% (30%-40%) |

Declared kind (columns) vs true kind (rows), `full`, 1x, summed over 3 run(s):

| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 17 | 24 | 0 |
| ambiguous | 3 | 36 | 21 | 0 |
| inconsistent | 10 | 8 | 42 | 0 |

Declared kind (columns) vs true kind (rows), `full`, 3x, summed over 3 run(s):

| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 18 | 19 | 23 | 0 |
| ambiguous | 4 | 34 | 22 | 0 |
| inconsistent | 9 | 7 | 44 | 0 |

Declared kind (columns) vs true kind (rows), `full`, 10x, summed over 3 run(s):

| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 17 | 24 | 0 |
| ambiguous | 4 | 31 | 25 | 0 |
| inconsistent | 9 | 4 | 47 | 0 |
