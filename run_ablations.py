#!/usr/bin/env python3
"""Ablation harness.

    python run_ablations.py --runs 3                 # real model, 60 visible items
    python run_ablations.py --runs 3 --reuse         # replay cached samples only (no calls)
    python run_ablations.py --mock                   # offline harness check (NOT a result)

How it stays cheap and paired
  The model is called once per (run, item) for 5 samples (the most any budget
  uses) and the raw text is cached in ablation_cache/.  Every arm below is then a
  deterministic replay of the same cached text through a different Config, so
  differences between arms come from the component, not from sampling luck.
  Budget b uses the first SAMPLES[b] cached samples (1x -> 1, 3x -> 3, 10x -> 5).
  Caveat: the 1x/3x/10x columns therefore share draws within a run.

Arms
  full                    default Config
  - regex slot repair     ungrounded slots are dropped instead of repaired
  - grounding check       slots are not required to appear in the cited line
  + distractor filter     hand-written phrase list may veto lines
  aggregate = first       use only the first valid sample      (3x/10x == 1x)
  aggregate = union       union of all samples' constraints    (the failure mode
                          of the old additive repair loop)
  - line-level core       conflict filtering per constraint, not per statement
  symbolic only           regex normalizer on every line, NO model (floor)
  model output blanked    every sample "[]" (answers must collapse)
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(ROOT, "candidate_package")
sys.path.insert(0, PKG)

import pipeline as P
from normalizer import normalize_constraint
from solver import ScheduleSolver
from score import score

N_MAX = max(P.SAMPLES.values())
BUDGETS = ["1x", "3x", "10x"]
BASE = P.Config()

ARMS = [
    ("full", BASE),
    ("- regex slot repair", replace(BASE, regex_repair=False)),
    ("- grounding check", replace(BASE, grounding=False, regex_repair=False)),
    ("+ distractor filter", replace(BASE, distractor_filter=True)),
    ("aggregate = first", replace(BASE, aggregate="first")),
    ("aggregate = union", replace(BASE, aggregate="union")),
    ("- line-level core", replace(BASE, line_level_core=False)),
]


def symbolic_only(items):
    out = {}
    for it in items:
        _, body, staff, blocks, stations, ss = P.item_context(it)
        s = ScheduleSolver(staff, ss, blocks, stations)
        cs = [c for c in (normalize_constraint({"line_no": i + 1}, body, staff, stations, blocks)
                          for i in range(len(body))) if c]
        case, v = s.solve(cs)
        if case == "unique":
            out[it["id"]] = {"case": "unique", "assignment": s.format_assignment(v[0])}
        elif case == "ambiguous":
            out[it["id"]] = {"case": "ambiguous", "assignments": [s.format_assignment(c) for c in v[:5]]}
        else:
            out[it["id"]] = {"case": "inconsistent", "conflicts": s.find_minimal_unsat_core(cs)}
    return out


def collect(items, run, cache_dir, reuse, mock, workers):
    path = os.path.join(cache_dir, f"run{run}.json")
    if reuse:                      # replay only when explicitly asked; default re-samples
        if not os.path.exists(path):
            sys.exit(f"--reuse given but {path} does not exist")
        with open(path) as f:
            return json.load(f)
    if mock:
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        from test_pipeline import MockClient
        client = MockClient("noisy", p_drop=0.15, seed=run)
    else:
        client = P.HttpModelClient()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(lambda it: (it["id"], P.extract_raw_samples(it, N_MAX, client, P.BUDGET_CAP["10x"])), items))
    raws = dict(res)
    if not mock:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump(raws, f)
    return raws


def grade(key, items, answers):
    r = score(key, answers, items)
    return {"macro": r["macro_exact_match"], **r["per_case_rate"], "confusion": r["confusion"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default=os.path.join(PKG, "items.json"))
    ap.add_argument("--key", default=os.path.join(PKG, "visible_key.json"))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cache", default=os.path.join(ROOT, "ablation_cache"))
    ap.add_argument("--reuse", action="store_true", help="only replay cached samples")
    ap.add_argument("--mock", action="store_true", help="offline harness check with a mock model")
    ap.add_argument("--out", default=os.path.join(ROOT, "ablation_results"))
    a = ap.parse_args()

    items = json.load(open(a.items))
    key = json.load(open(a.key))
    t0 = time.time()
    results = {}   # (arm, budget) -> list of per-run grade dicts

    for run in range(a.runs):
        raws = collect(items, run, a.cache, a.reuse, a.mock, a.workers)
        print(f"run {run}: samples ready ({time.time() - t0:.0f}s)", flush=True)
        for name, cfg in ARMS:
            for b in BUDGETS:
                n = P.SAMPLES[b]
                ans = {it["id"]: P.answer_from_samples(it, raws[it["id"]][:n], cfg)[0] for it in items}
                results.setdefault((name, b), []).append(grade(key, items, ans))
        for b in BUDGETS:
            n = P.SAMPLES[b]
            ans = {it["id"]: P.answer_from_samples(it, ["[]"] * n, BASE)[0] for it in items}
            results.setdefault(("model output blanked", b), []).append(grade(key, items, ans))

    sym = grade(key, items, symbolic_only(items))

    def cell(vals):
        m = sum(vals) / len(vals)
        return f"{m:.1%}" + (f" ({min(vals):.0%}-{max(vals):.0%})" if len(vals) > 1 else "")

    lines = [f"Ablation on {len(items)} items, {a.runs} run(s) per cell; macro exact match, "
             "mean (min-max across runs). Calls per item: 1x=1, 3x=3, 10x=5.\n",
             "| Arm | 1x | 3x | 10x |", "| :--- | :--- | :--- | :--- |"]
    for name in [n for n, _ in ARMS] + ["model output blanked"]:
        lines.append(f"| {name} | " + " | ".join(cell([r["macro"] for r in results[(name, b)]]) for b in BUDGETS) + " |")
    lines.append(f"| symbolic only (no model) | {sym['macro']:.1%} | - | - |")
    lines += ["", "Per-kind rates for `full` (mean over runs):", "",
              "| Budget | unique | ambiguous | inconsistent |", "| :--- | :--- | :--- | :--- |"]
    for b in BUDGETS:
        rs = results[("full", b)]
        lines.append(f"| {b} | " + " | ".join(cell([r[k] for r in rs]) for k in ("unique", "ambiguous", "inconsistent")) + " |")
    kinds, cols = ("unique", "ambiguous", "inconsistent"), ("unique", "ambiguous", "inconsistent", "unparsed")
    for b in BUDGETS:
        lines += ["", f"Declared kind (columns) vs true kind (rows), `full`, {b}, summed over {a.runs} run(s):", "",
                  "| true \\ declared | " + " | ".join(cols) + " |", "| :--- | " + " | ".join(":---" for _ in cols) + " |"]
        for t in kinds:
            row = [sum(r["confusion"][t].get(c, 0) for r in results[("full", b)]) for c in cols]
            lines.append(f"| {t} | " + " | ".join(map(str, row)) + " |")
    text = "\n".join(lines)
    print("\n" + text)
    open(a.out + ".md", "w").write(text + "\n")
    out = {f"{k[0]}|{k[1]}": v for k, v in results.items()}
    out["symbolic only"] = sym
    json.dump(out, open(a.out + ".json", "w"), indent=1)
    if a.mock:
        print("\n(mock model: harness check only, not a result)")


if __name__ == "__main__":
    main()
