Ablation on 60 items, 3 run(s) per cell; macro exact match, mean (min-max across runs). Calls per item: 1x=1, 3x=3, 10x=5.

| Arm | 1x | 3x | 10x |
| :--- | :--- | :--- | :--- |
| full | 28.3% (27%-30%) | 31.1% (28%-33%) | 30.0% (25%-33%) |
| - regex slot repair | 28.3% (27%-30%) | 31.1% (28%-33%) | 29.4% (25%-33%) |
| - grounding check | 24.4% (23%-25%) | 25.6% (23%-28%) | 27.8% (23%-30%) |
| + distractor filter | 28.3% (27%-30%) | 31.1% (28%-33%) | 30.0% (25%-33%) |
| aggregate = first | 28.3% (27%-30%) | 28.3% (27%-30%) | 28.3% (27%-30%) |
| aggregate = union | 28.3% (27%-30%) | 31.1% (30%-32%) | 33.3% (32%-35%) |
| - line-level core | 28.3% (27%-30%) | 31.1% (28%-33%) | 30.0% (25%-33%) |
| model output blanked | 0.0% (0%-0%) | 0.0% (0%-0%) | 0.0% (0%-0%) |
| symbolic only (no model) | 71.7% | - | - |

Per-kind rates for `full` (mean over runs):

| Budget | unique | ambiguous | inconsistent |
| :--- | :--- | :--- | :--- |
| 1x | 23.3% (20%-25%) | 21.7% (20%-25%) | 40.0% (35%-45%) |
| 3x | 25.0% (20%-30%) | 25.0% (15%-30%) | 43.3% (35%-50%) |
| 10x | 25.0% (20%-30%) | 18.3% (5%-25%) | 46.7% (40%-50%) |

Declared kind (columns) vs true kind (rows), `full`, 1x, summed over 3 run(s):

| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 17 | 34 | 9 | 0 |
| ambiguous | 3 | 51 | 6 | 0 |
| inconsistent | 7 | 17 | 36 | 0 |

Declared kind (columns) vs true kind (rows), `full`, 3x, summed over 3 run(s):

| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 33 | 8 | 0 |
| ambiguous | 2 | 51 | 7 | 0 |
| inconsistent | 11 | 14 | 35 | 0 |

Declared kind (columns) vs true kind (rows), `full`, 10x, summed over 3 run(s):

| true \ declared | unique | ambiguous | inconsistent | unparsed |
| :--- | :--- | :--- | :--- | :--- |
| unique | 19 | 34 | 7 | 0 |
| ambiguous | 3 | 51 | 6 | 0 |
| inconsistent | 11 | 12 | 37 | 0 |
