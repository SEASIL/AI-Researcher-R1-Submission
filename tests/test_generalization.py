"""Generalization and paraphrase diagnostic tests.

Tests model schema validation, grounding robustness, and solver integration
against diverse paraphrase templates and linguistic variations (without
accessing private keys or held-out test sets).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), "candidate_package")
sys.path.insert(0, PKG)

from normalizer import LineContext, SCHEMA, validate_model_constraint
from solver import ScheduleSolver


class TestParaphraseGeneralization(unittest.TestCase):
    def setUp(self):
        self.staff = ["Alice", "Bob", "Charlie", "David", "Eve"]
        self.stations = ["intake", "calibration", "packing"]
        self.blocks = ["07:00", "09:00", "11:00", "13:00", "15:00"]
        self.station_staff = ["Alice", "Bob", "Eve"]

    def test_all_nine_relation_types_validated_on_paraphrases(self):
        """Verify that all 9 relation types validate when expressed via natural paraphrases."""
        paraphrase_lines = [
            "Alice opens up the facility at 07:00 sharp.",
            "Bob was adamant that 09:00 would not work for his schedule.",
            "The intake desk is manned by Alice for this shift.",
            "Under no circumstances is Bob assigned to calibration.",
            "Charlie wraps up his duties well before David starts his day.",
            "Eve hands over directly to Alice with no intervening gap.",
            "Regardless of who is earlier between Bob and Eve, Charlie is situated between them.",
            "Whoever is assigned to calibration works earlier in the morning than David.",
            "Alice is on duty earlier in the sequence than whichever staff member has packing.",
        ]
        ctx = LineContext(paraphrase_lines, self.staff, self.stations, self.blocks)

        proposals = [
            {"line_no": 1, "type": "assign_block", "person": "Alice", "block": "07:00"},
            {"line_no": 2, "type": "not_block", "person": "Bob", "block": "09:00"},
            {"line_no": 3, "type": "assign_station", "person": "Alice", "station": "intake"},
            {"line_no": 4, "type": "not_station", "person": "Bob", "station": "calibration"},
            {"line_no": 5, "type": "before_person", "person1": "Charlie", "person2": "David"},
            {"line_no": 6, "type": "direct_after", "person1": "Alice", "person2": "Eve"},
            {"line_no": 7, "type": "between", "person": "Charlie", "person1": "Bob", "person2": "Eve"},
            {"line_no": 8, "type": "station_before_person", "station": "calibration", "person": "David"},
            {"line_no": 9, "type": "person_before_station", "person": "Alice", "station": "packing"},
        ]

        for p in proposals:
            c, reason = validate_model_constraint(p, ctx, ground=True)
            self.assertEqual(reason, "ok", f"Failed for proposal: {p}")
            self.assertIsNotNone(c)
            self.assertEqual(c["type"], p["type"])

    def test_possessive_and_punctuation_handling(self):
        """Punctuation and possessives (e.g., Alice's, 9:00) should be normalized cleanly."""
        lines = [
            "Alice's shift is confirmed at 09:00.",
            "Bob's post is packing, according to the manager.",
            "Charlie precedes David's block.",
        ]
        ctx = LineContext(lines, self.staff, self.stations, self.blocks)

        # Model emits with possessive or unstripped punctuation
        p1 = {"line_no": 1, "type": "assign_block", "person": "Alice's", "block": "9:00"}
        c1, r1 = validate_model_constraint(p1, ctx, ground=True)
        self.assertEqual(r1, "ok")
        self.assertEqual(c1["person"], "Alice")
        self.assertEqual(c1["block"], "09:00")

        p2 = {"line_no": 2, "type": "assign_station", "person": "Bob's", "station": "packing"}
        c2, r2 = validate_model_constraint(p2, ctx, ground=True)
        self.assertEqual(r2, "ok")
        self.assertEqual(c2["person"], "Bob")
        self.assertEqual(c2["station"], "packing")

    def test_brittle_failure_modes_documented_in_report(self):
        """Assert the known failure modes documented in README.md Section 5."""
        lines = [
            "She is assigned to intake at 11:00.",  # Pronoun 'She' instead of name
            "Dave is on packing.",                 # Nickname 'Dave' instead of 'David'
            "Alice and Bob are at least two blocks apart.",  # Relation outside 9-relation schema
            "Charlie starts at noon.",             # Time without HH:MM
            "Someone other than staff takes packing.",  # Non-entity placeholder
        ]
        ctx = LineContext(lines, self.staff, self.stations, self.blocks)

        # Pronoun fails grounding because 'Alice' is not in the line
        p_pronoun = {"line_no": 1, "type": "assign_station", "person": "Alice", "station": "intake"}
        c, reason = validate_model_constraint(p_pronoun, ctx, ground=True)
        self.assertIsNone(c)
        self.assertEqual(reason, "slots")

        # Nickname fails grounding because 'David' is not verbatim in line
        p_nick = {"line_no": 2, "type": "assign_station", "person": "David", "station": "packing"}
        c, reason = validate_model_constraint(p_nick, ctx, ground=True)
        self.assertIsNone(c)
        self.assertEqual(reason, "slots")

        # Unsupported relation outside closed schema is rejected as bad shape
        p_unsupported = {"line_no": 3, "type": "min_distance_two", "person1": "Alice", "person2": "Bob"}
        c, reason = validate_model_constraint(p_unsupported, ctx, ground=True)
        self.assertIsNone(c)
        self.assertEqual(reason, "shape")

        # Placeholder string in person slot is rejected
        p_placeholder = {"line_no": 5, "type": "assign_station", "person": "someone", "station": "packing"}
        c, reason = validate_model_constraint(p_placeholder, ctx, ground=True)
        self.assertIsNone(c)
        self.assertEqual(reason, "slots")

    def test_paraphrased_constraints_solve_to_valid_schedule(self):
        """End-to-end solve on a set of paraphrased constraints."""
        solver = ScheduleSolver(self.staff, self.station_staff, self.blocks, self.stations)
        
        # Build constraints that define a unique schedule:
        # Alice: 07:00, intake
        # Bob: 09:00, calibration
        # Charlie: 11:00
        # David: 13:00
        # Eve: 15:00, packing
        constraints = [
            {"type": "assign_block", "person": "Alice", "block": "07:00", "line_no": 1, "raw_line": "L1"},
            {"type": "assign_station", "person": "Alice", "station": "intake", "line_no": 2, "raw_line": "L2"},
            {"type": "direct_after", "person1": "Bob", "person2": "Alice", "line_no": 3, "raw_line": "L3"},
            {"type": "assign_station", "person": "Bob", "station": "calibration", "line_no": 4, "raw_line": "L4"},
            {"type": "direct_after", "person1": "Charlie", "person2": "Bob", "line_no": 5, "raw_line": "L5"},
            {"type": "direct_after", "person1": "David", "person2": "Charlie", "line_no": 6, "raw_line": "L6"},
            {"type": "direct_after", "person1": "Eve", "person2": "David", "line_no": 7, "raw_line": "L7"},
            {"type": "assign_station", "person": "Eve", "station": "packing", "line_no": 8, "raw_line": "L8"},
        ]
        
        case, valid = solver.solve(constraints)
        self.assertEqual(case, "unique")
        self.assertEqual(len(valid), 1)
        asg = solver.format_assignment(valid[0])
        self.assertEqual(asg["Alice"]["block"], "07:00")
        self.assertEqual(asg["Alice"]["station"], "intake")
        self.assertEqual(asg["Bob"]["block"], "09:00")
        self.assertEqual(asg["Bob"]["station"], "calibration")
        self.assertEqual(asg["Charlie"]["block"], "11:00")
        self.assertNotIn("station", asg["Charlie"])
        self.assertEqual(asg["Eve"]["block"], "15:00")
        self.assertEqual(asg["Eve"]["station"], "packing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
