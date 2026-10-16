#!/usr/bin/env python3
"""Shift-notes pipeline: Granite extracts, code validates and solves.

Division of labour
  model   decides which lines are scheduling statements and what relation each
          one expresses (type + slots) -> JSON.
  code    checks every proposal is well-formed and grounded in the line it
          cites (never invents one), aggregates samples by per-line vote,
          enumerates all 720 schedules, and extracts a line-level minimal
          conflict when none survive.

Budget handling
  Every call is registered in a per-item ledger BEFORE it is sent and is never
  retried.  A failed call (HTTP error, timeout, junk) still counts and yields
  no constraints from that sample.  A hard cap per item is enforced in code:
  1x -> 1 call, 3x -> 3 calls, 10x -> 5 calls (the cap is 10; the 10x tier
  deliberately spends only 5).
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, ".env"))
    load_dotenv()
except Exception:  # dotenv is optional if variables are already exported
    pass

from solver import ScheduleSolver
from normalizer import (LineContext, constraint_key, is_distractor_line,
                        regex_repair, validate_model_constraint)

API_KEY = os.environ.get("OPENROUTER_API_KEY")
BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.environ.get("MODEL", "ibm-granite/granite-4.2-8b")

BUDGET_CAP = {"1x": 1, "3x": 3, "10x": 10}       # hard per-item ceiling
SAMPLES = {"1x": 1, "3x": 3, "10x": 5}           # calls actually spent
MAX_TOKENS = 800
TIMEOUT_S = 60


@dataclass(frozen=True)
class Config:
    """Component switches (each one is an ablation arm)."""
    grounding: bool = True           # reject slots that are not in the cited line
    regex_repair: bool = True        # repair ungrounded slots when regex agrees on the type
    distractor_filter: bool = False  # hand-written phrase list vetoing lines
    aggregate: str = "vote"          # "vote" | "first" | "union"
    line_level_core: bool = True     # conflict filtering per statement, not per constraint


# --------------------------------------------------------------------------- #
# Model client + call ledger
# --------------------------------------------------------------------------- #
class BudgetExceeded(RuntimeError):
    pass


class CallLedger:
    """Thread-safe per-item call counter, incremented before each request."""

    def __init__(self):
        self._n = Counter()
        self._lock = threading.Lock()

    def reserve(self, item_id, cap):
        with self._lock:
            if self._n[item_id] >= cap:
                raise BudgetExceeded(f"{item_id}: call {self._n[item_id] + 1} exceeds cap {cap}")
            self._n[item_id] += 1

    def snapshot(self):
        with self._lock:
            return dict(self._n)


class HttpModelClient:
    """One HTTP attempt per call.  No retries, no sleeps, no fallbacks."""

    def __init__(self, ledger=None):
        self.ledger = ledger or CallLedger()

    def complete(self, messages, item_id, cap, max_tokens=MAX_TOKENS):
        import requests
        self.ledger.reserve(item_id, cap)
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "X-Item-Id": str(item_id),
        }
        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": 1.0,
            "top_p": 0.95,
            "max_tokens": max_tokens,
            "reasoning": {"enabled": False},
        }
        try:
            resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers,
                                 json=payload, timeout=TIMEOUT_S)
            if resp.status_code != 200:
                return None
            return resp.json()["choices"][0]["message"].get("content") or ""
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
FEW_SHOT = """Example
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

TYPES_DOC = """Relation types and their slots:
- assign_block {person, block}: person works that block (e.g. "takes HH:MM", "opens up at HH:MM", "covers HH:MM", "is on HH:MM").
- not_block {person, block}: person does NOT work that block (e.g. "unavailable at HH:MM", "lobbied for HH:MM without success", "wanted HH:MM and did not get it", "definitely not HH:MM", "rules out HH:MM").
- assign_station {person, station}: person is assigned to that station.
- not_station {person, station}: person is NOT assigned to that station ("someone other than", "has not been put on", "not assigned to").
- before_person {person1, person2}: person1 works earlier in the day than person2 (person1 < person2, e.g. "person1 is done before person2 starts", "person1 works earlier than person2", "person1 precedes person2", "person2 comes later than person1", "person1 falls somewhere earlier than person2"). Both slots MUST be persons from staff!
- direct_after {person1, person2}: person1 works immediately after person2 (person1 = person2 + 1 block, e.g. "person1 is on the block directly after person2", "person2 then person1, back to back", "person2 hands straight over to person1", "person1 relieves person2", "there is no block between person2 and person1, in that order"). person1 is the later person, person2 is the earlier person!
- between {person, person1, person2}: person works between person1 and person2 in either order (e.g. "person sits between person1 and person2", "person's block falls between person1's and person2's", "whichever way round person1 and person2 are, person is between them", "person is on after one of person1 and person2 and before the other", "person works at some point between person1 and person2, though not necessarily adjacent to either"). 'person' is the middle person; 'person1' and 'person2' are the outer two persons.
- station_before_person {station, person}: whoever is on station works earlier in the day than person (or person works later than whoever is on station).
- person_before_station {person, station}: person works earlier in the day than whoever is on station (or whoever is on station works later than person)."""


def build_prompt(header, body_lines):
    notes = "\n".join(f"{i + 1}: {l}" for i, l in enumerate(body_lines))
    return (
        "You turn facility shift notes into formal scheduling constraints.\n\n"
        f"{TYPES_DOC}\n\n{FEW_SHOT}\n\n"
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


# --------------------------------------------------------------------------- #
# Parsing a model response
# --------------------------------------------------------------------------- #
def parse_model_json(raw):
    """Return a list of dicts, or None if nothing usable could be recovered."""
    if raw is None:
        return None
    text = re.sub(r"```(?:json)?", "", raw.strip()).strip()
    text = re.sub(r",\s*([\]}])", r"\1", text)
    lo, hi = text.find("["), text.rfind("]")
    if lo != -1 and hi > lo:
        try:
            data = json.loads(text[lo:hi + 1])
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except Exception:
            pass
    # Truncated / slightly malformed array: salvage whole objects.
    objs = []
    for m in re.finditer(r"\{[^{}]*\}", text):
        clean_m = re.sub(r",\s*\}", "}", m.group(0))
        try:
            d = json.loads(clean_m)
            if isinstance(d, dict):
                objs.append(d)
        except Exception:
            continue
    return objs if objs else None


# --------------------------------------------------------------------------- #
# Item context
# --------------------------------------------------------------------------- #
def parse_header(header_text):
    staff_m = re.search(r"staff on the rota:\s*([^.]+)\.", header_text)
    staff = [s.strip() for s in staff_m.group(1).split(",")] if staff_m else []
    blocks = re.findall(r"\b\d{2}:\d{2}\b", header_text) or ["07:00", "09:00", "11:00", "13:00", "15:00"]
    st_m = re.search(r"There are \d+ stations, one person on each:\s*([^.]+)\.", header_text)
    stations = [s.strip() for s in st_m.group(1).split(",")] if st_m else ["intake", "calibration", "packing"]
    sp_m = re.search(r"The people on a station are\s*([^;]+);", header_text)
    station_staff = [s.strip() for s in sp_m.group(1).split(",")] if sp_m else []
    return staff, blocks, stations, station_staff


def item_context(item):
    lines = [l.strip() for l in item["text"].split("\n") if l.strip()]
    header, body = lines[0], lines[1:]
    staff, blocks, stations, station_staff = parse_header(header)
    return header, body, staff, blocks, stations, station_staff


# --------------------------------------------------------------------------- #
# Sampling (the only place the model is called)
# --------------------------------------------------------------------------- #
def extract_raw_samples(item, n, client, cap):
    header, body, *_ = item_context(item)
    messages = [{"role": "user", "content": build_prompt(header, body)}]
    return [client.complete(messages, item["id"], cap) for _ in range(n)]


# --------------------------------------------------------------------------- #
# Samples -> constraints
# --------------------------------------------------------------------------- #
def interpret_sample(raw, ctx, cfg):
    """One raw response -> ({line_no: frozenset(keys)}, {key: constraint}, stats) or None."""
    objs = parse_model_json(raw)
    if objs is None:
        return None
    per_line, by_key = {}, {}
    stats = Counter()
    for obj in objs:
        c, why = validate_model_constraint(obj, ctx, ground=cfg.grounding)
        if c is None and why == "slots" and cfg.regex_repair:
            c = regex_repair(obj, ctx)
            if c is not None:
                stats["repaired"] += 1
        if c is None:
            stats["rejected"] += 1
            continue
        if cfg.distractor_filter and is_distractor_line(c["raw_line"]):
            stats["distractor_vetoed"] += 1
            continue
        k = constraint_key(c)
        by_key[k] = c
        per_line.setdefault(c["line_no"], set()).add(k)
        stats["accepted"] += 1
    return {ln: frozenset(ks) for ln, ks in per_line.items()}, by_key, stats


def aggregate(interps, cfg):
    """Combine valid samples into one constraint list."""
    if not interps:
        return []
    by_key = {}
    for _, bk, _ in interps:
        by_key.update(bk)

    if cfg.aggregate == "first":
        chosen = list(interps[0][0].values())
    elif cfg.aggregate == "union":
        chosen = [ks for pl, _, _ in interps for ks in pl.values()]
    else:  # per-line plurality vote; a sample that skips a line votes "no constraint"
        lines = sorted({ln for pl, _, _ in interps for ln in pl})
        chosen = []
        for ln in lines:
            votes = Counter(pl.get(ln, frozenset()) for pl, _, _ in interps)
            best = max(votes, key=lambda ks: (votes[ks], len(ks) > 0, sorted(map(repr, ks))))
            chosen.append(best)

    keys, seen = [], set()
    for ks in chosen:
        for k in ks:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return [by_key[k] for k in sorted(keys, key=lambda k: (k[0], repr(k)))]


def answer_from_samples(item, raw_samples, cfg=Config()):
    """Deterministic: raw model responses in, (answer, trace) out."""
    header, body, staff, blocks, stations, station_staff = item_context(item)
    ctx = LineContext(body, staff, stations, blocks)
    solver = ScheduleSolver(staff, station_staff, blocks, stations)

    interps, stats = [], Counter()
    for raw in raw_samples:
        r = interpret_sample(raw, ctx, cfg)
        if r is None:
            stats["unparseable_samples"] += 1
            continue
        interps.append(r)
        stats.update(r[2])
    constraints = aggregate(interps, cfg)

    case, valid = solver.solve(constraints)
    if case == "unique":
        ans = {"case": "unique", "assignment": solver.format_assignment(valid[0])}
    elif case == "ambiguous":
        ans = {"case": "ambiguous",
               "assignments": [solver.format_assignment(c) for c in valid[:5]]}
    else:
        conflicts = solver.find_minimal_unsat_core(constraints, by_line=cfg.line_level_core)
        ans = {"case": "inconsistent", "conflicts": conflicts}

    trace = {"samples": len(raw_samples), "valid_samples": len(interps),
             "constraints": len(constraints), "candidates_left": len(valid), **stats}
    return ans, trace


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def solve_item(item, budget="1x", cfg=Config(), client=None):
    client = client or HttpModelClient()
    raws = extract_raw_samples(item, SAMPLES[budget], client, BUDGET_CAP[budget])
    return answer_from_samples(item, raws, cfg)


def run_pipeline(items_path, budget, out_path, cfg=Config(), client=None, workers=None):
    with open(items_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    client = client or HttpModelClient()
    workers = workers or int(os.environ.get("CONCURRENCY", "4"))
    print(f"Running {len(items)} items, budget {budget}, {workers} workers...", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda it: (it["id"], solve_item(it, budget, cfg, client)), items))
    answers = {iid: ans for iid, (ans, _) in results}
    traces = {iid: tr for iid, (_, tr) in results}

    ledger = getattr(client, "ledger", None)
    if ledger is not None:
        counts = ledger.snapshot()
        cap = BUDGET_CAP[budget]
        for it in items:
            traces[it["id"]]["model_calls"] = counts.get(it["id"], 0)
        bad = [i for i, c in counts.items() if c > cap]
        none = [it["id"] for it in items if counts.get(it["id"], 0) < 1]
        if bad or none:
            print(f"WARNING budget check failed: over cap={bad} no call={none}", flush=True)
    print(f"Completed in {time.time() - t0:.1f}s", flush=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answers, f, indent=2)
    if os.environ.get("TRACE") == "1":       # opt-in diagnostics; off for graded runs
        with open(out_path + ".trace.json", "w", encoding="utf-8") as f:
            json.dump(traces, f, indent=2)
    return answers


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("items", nargs="?", default="items.json")
    ap.add_argument("--budget", choices=["1x", "3x", "10x"], default="1x")
    ap.add_argument("--out", default="answers.json")
    a = ap.parse_args()
    run_pipeline(a.items, a.budget, a.out)
