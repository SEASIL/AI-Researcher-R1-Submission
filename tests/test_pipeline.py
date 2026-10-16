"""Mechanics tests with a MOCK model.  They check plumbing (call counts, no
retries, voting, line-level cores, sensitivity to model output).  They say
nothing about how well Granite itself extracts."""
import json, os, random, sys, unittest
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), "candidate_package")
sys.path.insert(0, PKG)

import pipeline as P
from normalizer import normalize_constraint, SCHEMA
from score import score

ITEMS = json.load(open(os.path.join(PKG, "items.json")))
KEY = json.load(open(os.path.join(PKG, "visible_key.json")))
BY_ID = {it["id"]: it for it in ITEMS}


def regex_objects(item):
    _, body, staff, blocks, stations, _ = P.item_context(item)
    out = []
    for i in range(len(body)):
        c = normalize_constraint({"line_no": i + 1}, body, staff, stations, blocks)
        if c:
            o = {"line_no": i + 1, "type": c["type"]}
            o.update({s: c[s] for s in SCHEMA[c["type"]]})
            out.append(o)
    return out


class MockClient:
    """Model stand-in. mode: 'good' | 'blank' | 'fail' | 'noisy'."""
    def __init__(self, mode="good", p_drop=0.0, seed=0):
        self.ledger = P.CallLedger()
        self.mode, self.p_drop, self.rng = mode, p_drop, random.Random(seed)

    def complete(self, messages, item_id, cap, max_tokens=800):
        self.ledger.reserve(item_id, cap)
        if self.mode == "fail":
            return None
        if self.mode == "blank":
            return "[]"
        objs = regex_objects(BY_ID[item_id])
        if self.mode == "noisy":
            objs = [o for o in objs if self.rng.random() > self.p_drop]
        return json.dumps(objs)


def macro(ans):
    return score(KEY, ans, ITEMS)["macro_exact_match"]


class Tests(unittest.TestCase):
    def test_1x_exactly_one_call_per_item(self):
        c = MockClient()
        P.run_pipeline(os.path.join(PKG, "items.json"), "1x", "/tmp/a1.json", client=c, workers=4)
        counts = c.ledger.snapshot()
        self.assertEqual(set(counts.values()), {1})
        self.assertEqual(len(counts), len(ITEMS))

    def test_budgets_within_caps(self):
        for b in ("3x", "10x"):
            c = MockClient()
            P.run_pipeline(os.path.join(PKG, "items.json"), b, f"/tmp/a_{b}.json", client=c, workers=4)
            vals = c.ledger.snapshot().values()
            self.assertTrue(all(1 <= v <= P.BUDGET_CAP[b] for v in vals))

    def test_ledger_blocks_extra_call(self):
        c, iid = MockClient(), ITEMS[0]["id"]
        c.complete([], iid, 1)
        with self.assertRaises(P.BudgetExceeded):
            c.complete([], iid, 1)

    def test_http_client_never_retries(self):
        calls = []
        class R:  # a 429 response
            status_code = 429
            def json(self): return {}
        def fake_post(*a, **k):
            calls.append(k["headers"]["X-Item-Id"]); return R()
        with mock.patch("requests.post", fake_post):
            ans, tr = P.solve_item(ITEMS[0], "1x", client=P.HttpModelClient())
        self.assertEqual(calls, [ITEMS[0]["id"]])           # one attempt, header present

    def test_http_exception_is_one_call(self):
        calls = []
        def boom(*a, **k):
            calls.append(1); raise TimeoutError()
        with mock.patch("requests.post", boom):
            P.solve_item(ITEMS[0], "1x", client=P.HttpModelClient())
        self.assertEqual(len(calls), 1)

    def test_http_payload_settings(self):
        seen = {}
        class R:
            status_code = 200
            def json(self): return {"choices": [{"message": {"content": "[]"}}]}
        def fake_post(url, headers=None, json=None, timeout=None):
            seen.update(json=json, headers=headers); return R()
        with mock.patch("requests.post", fake_post):
            P.solve_item(ITEMS[0], "1x", client=P.HttpModelClient())
        j = seen["json"]
        self.assertEqual((j["temperature"], j["top_p"], j["reasoning"]), (1.0, 0.95, {"enabled": False}))
        self.assertEqual(j["model"], P.MODEL)

    def test_failed_call_is_not_rescued_by_regex(self):
        c = MockClient("fail")
        ans, tr = P.solve_item(ITEMS[0], "1x", client=c)
        self.assertEqual(c.ledger.snapshot()[ITEMS[0]["id"]], 1)
        self.assertEqual(tr["constraints"], 0)               # nothing invented by code

    def test_answers_change_with_model_output(self):
        good, blank = MockClient("good"), MockClient("blank")
        pg = P.run_pipeline(os.path.join(PKG, "items.json"), "1x", "/tmp/g.json", client=good)
        pb = P.run_pipeline(os.path.join(PKG, "items.json"), "1x", "/tmp/b.json", client=blank)
        changed = sum(pg[i] != pb[i] for i in pg)
        self.assertGreater(changed, 0.9 * len(pg))
        self.assertLess(macro(pb), 0.05)

    def test_plumbing_matches_symbolic_floor(self):
        c = MockClient("good")
        ans = P.run_pipeline(os.path.join(PKG, "items.json"), "1x", "/tmp/s.json", client=c)
        self.assertAlmostEqual(macro(ans), 0.7167, places=3)

    def test_conflicts_are_verbatim_lines(self):
        ans = P.run_pipeline(os.path.join(PKG, "items.json"), "1x", "/tmp/v.json", client=MockClient())
        for iid, a in ans.items():
            if a["case"] == "inconsistent":
                lines = set(l.strip() for l in BY_ID[iid]["text"].split("\n"))
                for s in a["conflicts"]:
                    self.assertIn(s, lines)

    def test_grounding_rejects_wrong_name(self):
        it = ITEMS[0]
        _, body, staff, blocks, stations, _ = P.item_context(it)
        from normalizer import LineContext, validate_model_constraint
        ctx = LineContext(body, staff, stations, blocks)
        bad = {"line_no": 1, "type": "assign_block", "person": "Samuel", "block": "09:00"}  # line 1 is about Tomas/11:00
        c, why = validate_model_constraint(bad, ctx)
        self.assertIsNone(c)
        c, why = validate_model_constraint(bad, ctx, ground=False)
        self.assertIsNotNone(c)

    def test_voting_not_worse_than_single_noisy_sample(self):
        scores = {}
        for b in ("1x", "3x", "10x"):
            vals = []
            for seed in range(5):
                c = MockClient("noisy", p_drop=0.15, seed=seed)
                ans = P.run_pipeline(os.path.join(PKG, "items.json"), b, "/tmp/n.json", client=c, workers=1)
                vals.append(macro(ans))
            scores[b] = sum(vals) / len(vals)
        print("\nnoisy-mock macro (mean of 5 seeds):", {k: round(v, 3) for k, v in scores.items()})
        self.assertGreaterEqual(scores["3x"], scores["1x"])
        self.assertGreaterEqual(scores["10x"], scores["3x"] - 0.02)


class BriefCompliance(unittest.TestCase):
    """Rules taken straight from CANDIDATE_BRIEF.md."""

    def _answers(self):
        c = MockClient("good")
        return P.run_pipeline(os.path.join(PKG, "items.json"), "1x", "/tmp/c.json", client=c)

    def test_output_forms_and_completeness(self):
        for iid, a in self._answers().items():
            _, body, staff, blocks, stations, station_staff = P.item_context(BY_ID[iid])
            self.assertIn(a["case"], ("unique", "ambiguous", "inconsistent"))
            if a["case"] == "inconsistent":
                continue
            asg = [a["assignment"]] if a["case"] == "unique" else a["assignments"]
            for x in asg:
                self.assertEqual(set(x), set(staff), "every person on the rota must be named")
                for name, v in x.items():
                    self.assertIn(v["block"], blocks)
                    # station only for the people the header puts on a station
                    self.assertEqual("station" in v, name in station_staff)
                    if "station" in v:
                        self.assertIn(v["station"], stations)

    def test_assignments_are_blocks_exclusive(self):
        for iid, a in self._answers().items():
            if a["case"] == "unique":
                blocks = [v["block"] for v in a["assignment"].values()]
                self.assertEqual(len(set(blocks)), len(blocks))

    def test_citations_one_statement_each_verbatim(self):
        for iid, a in self._answers().items():
            if a["case"] != "inconsistent":
                continue
            lines = [l.strip() for l in BY_ID[iid]["text"].split("\n")]
            self.assertEqual(len(set(a["conflicts"])), len(a["conflicts"]))
            for s in a["conflicts"]:
                self.assertIn(s, lines)            # whole line, not trimmed, not run-on
                self.assertNotIn("\n", s)

    def test_documented_entrypoint_runs_directly(self):
        """`./run <items> --budget 1x --out <file>` must execute (exec bit + shebang)."""
        import subprocess, tempfile
        root = os.path.dirname(PKG)
        items3 = os.path.join(tempfile.mkdtemp(), "three.json")
        with open(items3, "w") as f:
            json.dump(ITEMS[:3], f)
        out = items3.replace("three.json", "out.json")
        env = dict(os.environ, OPENROUTER_BASE_URL="http://127.0.0.1:9", OPENROUTER_API_KEY="x")
        run_cmd = [os.path.join(root, "run.bat" if sys.platform == "win32" else "run")]
        r = subprocess.run(run_cmd + [items3, "--budget", "1x", "--out", out],
                           env=env, capture_output=True, text=True, shell=(sys.platform == "win32"))
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as f:
            got = json.load(f)
        self.assertEqual(set(got), {i["id"] for i in ITEMS[:3]})
        self.assertFalse(os.path.exists(out + ".trace.json"))   # no stray files by default

    def test_header_parses_for_every_visible_item(self):
        for it in ITEMS:
            _, _, staff, blocks, stations, ss = P.item_context(it)
            self.assertEqual((len(staff), len(blocks)), (it["n_staff"], it["n_staff"]))
            self.assertEqual((len(ss), len(stations)), (it["n_stations"], it["n_stations"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
