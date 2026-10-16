#!/usr/bin/env python3
"""Compares old prompt vs new prompt on the paraphrased dev set (1x budget, 3 runs).
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "candidate_package")
sys.path.insert(0, PKG)

import pipeline as P
from score import score

OLD_FEW_SHOT = """Example
Header: "Shift notes, Bay 1. 5 staff on the rota: Alice, Bob, Charlie, David, Eve. Blocks run 07:00, 09:00, 11:00, 13:00, 15:00. Stations: intake, calibration, packing (Alice, Bob, Eve)."
Notes:
1: Deliveries continue to arrive through north gate.
2: Alice is not on calibration.
3: Bob takes 11:00, as things stand.
4: Charlie lobbied for 07:00 without success.
5: Eve is on the block directly after Alice.
6: Whoever is on packing works earlier in the day than David.
7: Whichever way round Bob and Eve are, Charlie is between them.
8: Alice then Bob, back to back.
9: Calibration is covered earlier in the day than Eve's block.
10: In the old arrangement, Alice took packing.
11: Alice is confirmed on intake.
12: David is done before Eve starts.
13: Charlie works earlier than whoever has packing.
14: There is no block between Bob's and Charlie's, in that order.
15: Nothing was minuted about David.

Output:
[
  {"line_no": 2, "type": "not_station", "person": "Alice", "station": "calibration"},
  {"line_no": 3, "type": "assign_block", "person": "Bob", "block": "11:00"},
  {"line_no": 4, "type": "not_block", "person": "Charlie", "block": "07:00"},
  {"line_no": 5, "type": "direct_after", "person1": "Eve", "person2": "Alice"},
  {"line_no": 6, "type": "station_before_person", "station": "packing", "person": "David"},
  {"line_no": 7, "type": "between", "person": "Charlie", "person1": "Bob", "person2": "Eve"},
  {"line_no": 8, "type": "direct_after", "person1": "Bob", "person2": "Alice"},
  {"line_no": 9, "type": "station_before_person", "station": "calibration", "person": "Eve"},
  {"line_no": 11, "type": "assign_station", "person": "Alice", "station": "intake"},
  {"line_no": 12, "type": "before_person", "person1": "David", "person2": "Eve"},
  {"line_no": 13, "type": "person_before_station", "person": "Charlie", "station": "packing"},
  {"line_no": 14, "type": "direct_after", "person1": "Charlie", "person2": "Bob"}
]"""

OLD_TYPES_DOC = """Relation types and their slots:
- assign_block {person, block}: person works that block (e.g. "takes HH:MM", "opens up at HH:MM", "covers HH:MM", "is on HH:MM").
- not_block {person, block}: person does NOT work that block (e.g. "unavailable at HH:MM", "lobbied for HH:MM without success", "wanted HH:MM and did not get it", "definitely not HH:MM", "rules out HH:MM").
- assign_station {person, station}: person is assigned to that station.
- not_station {person, station}: person is NOT assigned to that station ("someone other than", "has not been put on", "not assigned to").
- before_person {person1, person2}: person1 works earlier in the day than person2 (person1 < person2, e.g. "person1 is done before person2 starts", "person1 works earlier than person2", "person1 precedes person2", "person2 comes later than person1", "person1 falls somewhere earlier than person2"). Both slots MUST be persons from staff!
- direct_after {person1, person2}: person1 works immediately after person2 (person1 = person2 + 1 block, e.g. "person1 is on the block directly after person2", "person2 then person1, back to back", "person2 hands straight over to person1", "person1 relieves person2", "there is no block between person2 and person1, in that order"). person1 is the later person, person2 is the earlier person!
- between {person, person1, person2}: person works between person1 and person2 in either order (e.g. "person sits between person1 and person2", "person's block falls between person1's and person2's", "whichever way round person1 and person2 are, person is between them", "person is on after one of person1 and person2 and before the other", "person works at some point between person1 and person2, though not necessarily adjacent to either"). 'person' is the middle person; 'person1' and 'person2' are the outer two persons.
- station_before_person {station, person}: whoever is on station works earlier in the day than person (or person works later than whoever is on station).
- person_before_station {person, station}: person works earlier in the day than whoever is on station (or whoever is on station works later than person)."""


def build_old_prompt(header, body_lines):
    notes = "\n".join(f"{i + 1}: {l}" for i, l in enumerate(body_lines))
    return (
        "You turn facility shift notes into formal scheduling constraints.\n\n"
        f"{OLD_TYPES_DOC}\n\n{OLD_FEW_SHOT}\n\n"
        "Rules:\n"
        "1. Output ONLY a valid JSON array of objects. One object per scheduling statement (a line may contain more than one).\n"
        "2. line_no MUST be the integer line number shown before the colon.\n"
        "3. Every slot must use the exact names, station words, or HH:MM times from that line:\n"
        "   - 'person', 'person1', 'person2' MUST be actual names from the staff list. Never put placeholder strings (like 'one_of', 'someone', 'null') or station names in person slots.\n"
        "   - 'station' MUST be a station name from the stations list.\n"
        "   - 'block' MUST be an HH:MM time from the blocks list.\n"
        "4. If a statement compares two staff members (e.g., 'X is done before Y starts'), use before_person or direct_after, NEVER person_before_station!\n"
        "5. Hedges ('as far as I know', 'speaking from memory', 'going off the roster', 'it bears repeating', 'my recollection is', 'worth restating') do not weaken a statement; extract it in full.\n"
        "6. Skip lines that are office chatter, breaks, deliveries, walkarounds, fire drills, past arrangements ('in the old arrangement', 'last month'), or hypotheticals ('would have been').\n"
        f'Header: "{header}"\nNotes:\n{notes}\n\nOutput:'
    )


def run_eval(items, prompt_fn, prompt_name, cache_dir, runs=3, workers=4, key_file="paraphrased_key.json"):
    os.makedirs(cache_dir, exist_ok=True)
    key_path = os.path.join(ROOT, key_file)
    if not os.path.exists(key_path):
        key_path = os.path.join(PKG, "visible_key.json")
    with open(key_path, "r", encoding="utf-8") as f:
        key = json.load(f)
    scores = []

    print(f"\n--- Evaluating {prompt_name} on {len(items)} items ({runs} runs at 1x, key: {os.path.basename(key_path)}) ---")
    for r in range(runs):
        cache_path = os.path.join(cache_dir, f"run{r}.json")
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                raws = json.load(f)
        else:
            client = P.HttpModelClient()
            t0 = time.time()
            def sample_item(it):
                h, b, *_ = P.item_context(it)
                msg = [{"role": "user", "content": prompt_fn(h, b)}]
                resp = client.complete(msg, it["id"], 1, max_tokens=1200)
                return it["id"], resp
            with ThreadPoolExecutor(max_workers=workers) as ex:
                res = list(ex.map(sample_item, items))
            raws = dict(res)
            with open(cache_path, "w") as f:
                json.dump(raws, f)
            print(f"  Run {r} sampled in {time.time() - t0:.1f}s")

        ans = {}
        for it in items:
            raw = raws[it["id"]]
            a, _ = P.answer_from_samples(it, [raw], P.Config())
            ans[it["id"]] = a

        sc = score(key, ans, items)
        m = sc["macro_exact_match"]
        pk = sc["per_case_rate"]
        scores.append(m)
        print(f"  Run {r}: Macro = {m:.1%} (U: {pk['unique']:.1%}, A: {pk['ambiguous']:.1%}, I: {pk['inconsistent']:.1%})")

    mean_sc = sum(scores) / len(scores)
    min_sc, max_sc = min(scores), max(scores)
    print(f"==> {prompt_name} 1x Macro: {mean_sc:.1%} ({min_sc:.1%}-{max_sc:.1%}) across {runs} runs")
    return mean_sc, min_sc, max_sc, scores


if __name__ == "__main__":
    p_items = json.load(open(os.path.join(ROOT, "paraphrased_items.json")))

    # 1. Old prompt on paraphrased set
    run_eval(p_items, build_old_prompt, "OLD PROMPT on Paraphrased Set",
             os.path.join(ROOT, "scratch", "cache_para_old"), runs=3, key_file="paraphrased_key.json")

    # 2. New prompt on paraphrased set
    run_eval(p_items, P.build_prompt, "NEW PROMPT on Paraphrased Set",
             os.path.join(ROOT, "scratch", "cache_para_new"), runs=3, key_file="paraphrased_key.json")

