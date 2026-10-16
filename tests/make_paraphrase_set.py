#!/usr/bin/env python3
"""Generates a self-made paraphrased dev set from items.json using rule-based rewriting.

Preserves the exact entities (staff, stations, blocks) and semantic truth value
so that ground-truth answers in visible_key.json remain 100% valid.
Contains no per-item logic.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "candidate_package")

PARAPHRASE_RULES = [
    # Hedges
    (r"\bAs far as I know,\b", "To the best of my knowledge,"),
    (r"\bSpeaking from memory,\b", "If memory serves,"),
    (r"\bMy recollection is that\b", "As I recall,"),
    (r"\bGoing off the roster,\b", "According to the schedule,"),
    (r"\bIt bears repeating:\b", "To reiterate:"),
    (r"\bWorth restating, since it came up twice in handover:\b", "Reiterated from shift handover:"),
    (r"\bNoted twice in the handover:\b", "Twice noted in shift notes:"),
    (r"\bThis came up more than once, so:\b", "Mentioned multiple times:"),
    (r"\bI'm fairly sure\b", "I believe"),

    # Direct after / adjacency
    (r"is on the block directly after", "works the block immediately following"),
    (r"is on the block immediately before", "is scheduled immediately prior to"),
    (r", back to back\.", ", consecutively back-to-back."),
    (r"hands straight over to", "hands off directly to"),
    (r"There is no block between ([^'\s]+)'s and ([^'\s]+)'s, in that order\.",
     r"No intervening block separates \1 and \2, in that exact order."),

    # Before / after (person or station)
    (r"is done before ([^.\s]+) starts\.", r"finishes up before \1 begins."),
    (r"comes later in the day than", "is rostered later than"),
    (r"works earlier in the day than", "is on earlier than"),
    (r"works earlier than", "is scheduled earlier than"),
    (r"is on later than", "works later than"),
    (r"The person on ([a-z]+) precedes ([^.\s]+)\.", r"Whoever covers \1 works prior to \2."),
    (r"The ([a-z]+) station is covered earlier in the day than ([^'\s]+)'s block\.",
     r"The \1 post is covered earlier in the day than the block of \2."),

    # Between
    (r"Whichever way round ([^,\s]+) and ([^,\s]+) are, ([^,\s]+) is between them\.",
     r"Regardless of whether \1 or \2 is earlier, \3 is positioned between them."),
    (r"Put ([^,\s]+) between ([^,\s]+) and ([^,\s]+), though not necessarily next to either\.",
     r"Position \1 somewhere between \2 and \3, not necessarily adjacent to either."),
    (r"sits between ([^,\s]+) and ([^,\s]+) on the rota\.", r"falls between \1 and \2 on the duty rota."),
    (r"is on after one of ([^,\s]+) and ([^,\s]+) and before the other\.",
     r"works after one of \1 and \2 and prior to the other."),
    (r"([^'\s]+)'s block falls between ([^'\s]+)'s and ([^'\s]+)'s, in one order or the other\.",
     r"In one sequence or the other, \1's block comes between \2's and \3's."),
    (r"works at some point between ([^,\s]+) and ([^,\s]+), not necessarily adjacent to either\.",
     r"is scheduled at some point between \1 and \2, though not necessarily adjacent to either."),

    # Assignments & exclusions
    (r"takes (\d{2}:\d{2}), as things stand\.", r"is currently slated for \1."),
    (r"Whoever drew the (\d{2}:\d{2}) block, it was ([^.\s]+)\.", r"\2 drew the \1 block."),
    (r"is the one who opens up at (\d{2}:\d{2})\.", r"covers the opening \1 shift."),
    (r"asked to move to the (\d{2}:\d{2}) block; the request was declined\.",
     r"requested the \1 block, but the request was turned down."),
    (r"lobbied for (\d{2}:\d{2}) without success\.", r"pushed for \1 without success."),
    (r"wanted (\d{2}:\d{2}) and did not get it\.", r"sought \1 and did not receive it."),
    (r"is unavailable at (\d{2}:\d{2})\.", r"cannot take \1."),
    (r"has a standing commitment that rules out the (\d{2}:\d{2}) block entirely\.",
     r"has a recurring commitment entirely ruling out the \1 block."),
    (r"The (\d{2}:\d{2}) block is not ([^'\s]+)'s\.", r"\2 is definitely not assigned to the \1 block."),
    (r"is confirmed on ([a-z]+)\.", r"has been confirmed for \1."),
    (r"is assigned to ([a-z]+)\.", r"is allocated to \1."),
    (r"the ([a-z]+) station is down to ([^.\s]+)\.", r"\2 is rostered for \1."),
    (r"is not assigned to ([a-z]+)\.", r"is not posted on \1."),
    (r"has not been put on ([a-z]+)\.", r"was not placed on \1."),
    (r"([A-Z][a-z]+) is covered by someone other than ([^.\s]+)\.",
     r"Someone other than \2 covers \1."),

    # Distractors
    (r"Deliveries continue to arrive through the north gate\.",
     r"Inbound shipments are still arriving via the north gate."),
    (r"Nobody has claimed the jacket left in the break room\.",
     r"The jacket left behind in the break room is still unclaimed."),
    (r"The visitor log was moved to the front desk in March\.",
     r"In March, the visitor register was relocated to the front reception desk."),
    (r"completed the fire-safety refresher last quarter\.",
     r"finished the quarterly fire safety briefing."),
    (r"car-share when their shifts allow\.", r"carpool whenever their shifts line up."),
    (r"has the spare key to the supply cupboard\.", r"holds the backup key for the supplies locker."),
    (r"filled in the equipment survey\.", r"submitted the facility equipment survey."),
    (r"sat on the interview panel in February\.", r"took part in the February hiring panel."),
]


def paraphrase_line(line):
    res = line
    for pat, repl in PARAPHRASE_RULES:
        res = re.sub(pat, repl, res)
    return res


def build_paraphrase_set(src_items_path, dst_items_path, src_key_path=None, dst_key_path=None):
    with open(src_items_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    out = []
    total_lines = 0
    rewritten_lines = 0

    for it in items:
        lines = [l for l in it["text"].split("\n") if l.strip()]
        header = lines[0]
        body = lines[1:]

        new_body = []
        for l in body:
            total_lines += 1
            pl = paraphrase_line(l)
            if pl != l:
                rewritten_lines += 1
            new_body.append(pl)

        new_text = header + "\n\n" + "\n".join(new_body)
        new_it = dict(it)
        new_it["text"] = new_text
        out.append(new_it)

    with open(dst_items_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"Generated {len(out)} paraphrased items in {dst_items_path}")
    print(f"Rewrote {rewritten_lines} of {total_lines} lines ({rewritten_lines / total_lines:.1%})")

    if src_key_path and dst_key_path:
        with open(src_key_path, "r", encoding="utf-8") as f:
            key = json.load(f)
        out_key = {}
        for item_id, k in key.items():
            pk = dict(k)
            if "conflict_line_sets" in k and k["conflict_line_sets"]:
                new_sets = []
                for cset in k["conflict_line_sets"]:
                    new_set = [paraphrase_line(line) for line in cset]
                    new_sets.append(new_set)
                pk["conflict_line_sets"] = new_sets
            out_key[item_id] = pk
        with open(dst_key_path, "w", encoding="utf-8") as f:
            json.dump(out_key, f, indent=2)
        print(f"Generated remapped answer key in {dst_key_path}")


if __name__ == "__main__":
    src_i = os.path.join(PKG, "items.json")
    dst_i = os.path.join(ROOT, "paraphrased_items.json")
    src_k = os.path.join(PKG, "visible_key.json")
    dst_k = os.path.join(ROOT, "paraphrased_key.json")
    build_paraphrase_set(src_i, dst_i, src_k, dst_k)

