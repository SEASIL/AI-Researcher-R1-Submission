import re

DISTRACTOR_PATTERNS = [
    r"back in the old arrangement",
    r"in the spring",
    r"last month",
    r"on the previous cycle",
    r"would have been",
    r"would have solved",
    r"handover would have been smoother",
    r"had the rota gone the other way",
    r"if .* had taken",
    r"nothing was minuted",
    r"nobody could remember",
    r"there was some disagreement",
    r"left open in the handover",
    r"car-share",
    r"walkaround",
    r"fire-safety",
    r"interview panel",
    r"equipment survey",
    r"emergency contact",
    r"recycling",
    r"break room",
    r"front desk",
    r"supply cupboard",
    r"catering is unchanged",
    r"deliveries continue",
    r"resurfacing runs",
    r"fire drill",
    r"training day",
]

def is_distractor_line(text):
    if not text:
        return False
    t = text.lower()
    for pat in DISTRACTOR_PATTERNS:
        if re.search(pat, t):
            return True
    return False

def find_entities_in_text(text, staff_list, stations_list, blocks_list):
    """Finds all staff, stations, and blocks mentioned in text, in order of appearance."""
    staff_found = []
    for p in staff_list:
        m = re.search(r"\b" + re.escape(p) + r"\b", text)
        if m:
            staff_found.append((m.start(), p))
    staff_found = [p for _, p in sorted(staff_found)]

    stations_found = []
    for s in stations_list:
        m = re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)
        if m:
            stations_found.append((m.start(), s))
    stations_found = [s for _, s in sorted(stations_found)]

    blocks_found = []
    for b in blocks_list:
        m = re.search(r"\b" + re.escape(b) + r"\b", text)
        if m:
            blocks_found.append((m.start(), b))
    blocks_found = [b for _, b in sorted(blocks_found)]

    return staff_found, stations_found, blocks_found

def normalize_constraint(c, body_lines, staff_list, stations_list, blocks_list):
    """
    Normalizes a dictionary constraint emitted by the LLM into a canonical
    form that ScheduleSolver understands, with strict entity grounding.
    """
    if not isinstance(c, dict):
        return None

    line_no = c.get("line_no")
    raw_line = c.get("raw_line")
    if line_no and isinstance(line_no, int) and 1 <= line_no <= len(body_lines):
        raw_line = body_lines[line_no - 1]
    elif not raw_line and line_no:
        try:
            l_idx = int(line_no)
            if 1 <= l_idx <= len(body_lines):
                raw_line = body_lines[l_idx - 1]
        except Exception:
            pass

    # Reject if the underlying line is a known distractor
    if is_distractor_line(raw_line):
        return None

    if not raw_line:
        return None

    staff_in_line, stations_in_line, blocks_in_line = find_entities_in_text(raw_line, staff_list, stations_list, blocks_list)
    
    ctype = str(c.get("type", "")).lower().strip()
    out = {"raw_line": raw_line, "line_no": line_no}
    line_lower = raw_line.lower()

    # 1. Betweenness
    if "between" in line_lower or "after one of" in line_lower:
        if len(staff_in_line) == 3:
            # Pattern A: "Whichever way round Y and Z are, X is between them"
            m_rev = re.search(r"\b([A-Za-z]+)\b\s+is between them", raw_line, re.IGNORECASE)
            if m_rev:
                mid_cand = [p for p in staff_list if p.lower() == m_rev.group(1).lower()]
                if mid_cand:
                    mid = mid_cand[0]
                    sides = [p for p in staff_in_line if p != mid]
                    if len(sides) == 2:
                        out["type"] = "between"
                        out["person"] = mid
                        out["person1"] = sides[0]
                        out["person2"] = sides[1]
                        return out

            # Pattern B: "Put X between Y and Z", "X sits between Y and Z", "X's block falls between Y and Z", "X is on after one of Y and Z and before the other"
            m = re.search(r"(?:put\s+)?([A-Za-z]+).*?(?:between|after one of)\s+([A-Za-z]+).*?(?:and|'s and)\s+([A-Za-z]+)", raw_line, re.IGNORECASE)
            if m:
                p_cand = [p for p in staff_list if p.lower() == m.group(1).lower()]
                s1_cand = [p for p in staff_list if p.lower() == m.group(2).lower()]
                s2_cand = [p for p in staff_list if p.lower() == m.group(3).lower()]
                if p_cand and s1_cand and s2_cand:
                    out["type"] = "between"
                    out["person"] = p_cand[0]
                    out["person1"] = s1_cand[0]
                    out["person2"] = s2_cand[0]
                    return out
            # Default order fallback if regex didn't catch prefix
            out["type"] = "between"
            out["person"] = staff_in_line[0]
            out["person1"] = staff_in_line[1]
            out["person2"] = staff_in_line[2]
            return out

    # 2. Station before / after person
    if stations_in_line and staff_in_line:
        st = stations_in_line[0]
        p = staff_in_line[0]
        
        # Check direction in line
        if re.search(r"(?:covered earlier|precedes|done before|works earlier|covered before|earlier in the day than)\s+.*?\b" + re.escape(p), raw_line, re.IGNORECASE) or \
           re.search(r"\b" + re.escape(p) + r"\b.*?(?:comes later|is on later)", raw_line, re.IGNORECASE):
            out["type"] = "station_before_person"
            out["station"] = st
            out["person"] = p
            return out
        elif re.search(r"\b" + re.escape(p) + r"\b.*?(?:works earlier|is done before|precedes)", raw_line, re.IGNORECASE):
            out["type"] = "person_before_station"
            out["person"] = p
            out["station"] = st
            return out

    # 3. Direct adjacency (A then B, back to back; A hands straight over to B; A immediately before B)
    if len(staff_in_line) >= 2:
        p_first = staff_in_line[0]
        p_second = staff_in_line[1]
        
        if "then" in line_lower and "back to back" in line_lower:
            # "A then B, back to back" -> B directly after A
            out["type"] = "direct_after"
            out["person1"] = p_second
            out["person2"] = p_first
            return out
        elif "hands straight over to" in line_lower or "immediately before" in line_lower:
            # "A hands straight over to B" -> B directly after A
            out["type"] = "direct_after"
            out["person1"] = p_second
            out["person2"] = p_first
            return out
        elif "directly after" in line_lower or "immediately after" in line_lower or "relieves" in line_lower:
            # "A is directly after B" -> A directly after B
            out["type"] = "direct_after"
            out["person1"] = p_first
            out["person2"] = p_second
            return out
        elif "done before" in line_lower or "earlier in the day" in line_lower or "works earlier" in line_lower or "precedes" in line_lower:
            # "A is done before B starts" -> A < B
            out["type"] = "before_person"
            out["person1"] = p_first
            out["person2"] = p_second
            return out
        elif "later" in line_lower or "comes later" in line_lower or "after" in line_lower:
            # "A comes later than B" -> B < A
            out["type"] = "before_person"
            out["person1"] = p_second
            out["person2"] = p_first
            return out

    # 4. Station assignment or negation
    if stations_in_line and staff_in_line:
        st = stations_in_line[0]
        p = staff_in_line[0]
        
        # Negation checks
        if any(neg in line_lower for neg in ["not", "someone other than", "rule", "isn't", "hasn't"]):
            out["type"] = "not_station"
            out["person"] = p
            out["station"] = st
            return out
        else:
            out["type"] = "assign_station"
            out["person"] = p
            out["station"] = st
            return out

    # 5. Block assignment or negation
    if blocks_in_line and staff_in_line:
        bk = blocks_in_line[0]
        p = staff_in_line[0]
        
        if any(neg in line_lower for neg in ["not", "unavailable", "rules out", "lobbied", "wanted", "without success", "turned down", "definitely not"]):
            out["type"] = "not_block"
            out["person"] = p
            out["block"] = bk
            return out
        else:
            out["type"] = "assign_block"
            out["person"] = p
            out["block"] = bk
            return out

    return None


# ---------------------------------------------------------------------------
# Model-first validation
#
# The model decides WHICH lines are constraints and WHAT relation each one is
# (type + slots).  Code in this section never invents a constraint: it only
# checks that what the model proposed is well-formed and grounded in the text
# of the line the model pointed at, and rejects it otherwise.
# ---------------------------------------------------------------------------

SCHEMA = {
    "assign_block": ("person", "block"),
    "not_block": ("person", "block"),
    "assign_station": ("person", "station"),
    "not_station": ("person", "station"),
    "before_person": ("person1", "person2"),     # person1 earlier than person2
    "direct_after": ("person1", "person2"),      # person1 directly after person2
    "between": ("person", "person1", "person2"),
    "station_before_person": ("station", "person"),
    "person_before_station": ("person", "station"),
}
PERSON_SLOTS = {"person", "person1", "person2"}


class LineContext:
    """Everything the validator needs to know about one item."""

    def __init__(self, body_lines, staff, stations, blocks):
        self.body_lines = body_lines
        self.staff = staff
        self.stations = stations
        self.blocks = blocks


def constraint_key(c):
    """Hashable identity of a canonical constraint (line + type + slots)."""
    slots = SCHEMA[c["type"]]
    return (c["line_no"], c["type"]) + tuple(c[s] for s in slots)


def _canon(value, options, ignore_case):
    if not isinstance(value, str):
        return None
    v = " ".join(value.split()).strip(".,;:\"' \t\n")
    v_clean = re.sub(r"['’]s$", "", v)
    # Normalize time like 9:00 -> 09:00
    if re.match(r"^\d:\d{2}$", v):
        v = "0" + v
    if re.match(r"^\d:\d{2}$", v_clean):
        v_clean = "0" + v_clean
    for o in options:
        if v == o or (ignore_case and v.lower() == o.lower()):
            return o
        if v_clean == o or (ignore_case and v_clean.lower() == o.lower()):
            return o
    return None


def _in_line(token, line, ignore_case):
    flags = re.IGNORECASE if ignore_case else 0
    # Also allow matching without leading zero for times, e.g. 09:00 matching 9:00
    patterns = [r"(?<![\w:])" + re.escape(token) + r"(?![\w:])"]
    if re.match(r"^0\d:\d{2}$", token):
        patterns.append(r"(?<![\w:])" + re.escape(token[1:]) + r"(?![\w:])")
    return any(re.search(p, line, flags) is not None for p in patterns)


def validate_model_constraint(obj, ctx, ground=True):
    """Check one model-proposed constraint.

    Returns (constraint_dict | None, reason).  reason is "ok", "shape"
    (not a usable object / unknown type / bad line_no), or "slots" (the type
    and line are fine but a slot is unknown, repeated, or not present in the
    line the model cited).  With ground=False the 'present in the line' test is
    skipped (ablation arm).
    """
    if not isinstance(obj, dict):
        return None, "shape"
    ctype = str(obj.get("type", "")).strip().lower()
    if ctype in ("none", "null", ""):
        return None, "none"
    if ctype not in SCHEMA:
        return None, "shape"

    try:
        line_no = int(obj.get("line_no"))
    except (TypeError, ValueError):
        return None, "shape"
    if not 1 <= line_no <= len(ctx.body_lines):
        return None, "shape"
    line = ctx.body_lines[line_no - 1]

    out = {"type": ctype, "line_no": line_no, "raw_line": line}
    people = []
    for slot in SCHEMA[ctype]:
        raw = obj.get(slot)
        if slot in PERSON_SLOTS:
            val = _canon(raw, ctx.staff, ignore_case=True)
            ic = False
        elif slot == "station":
            val = _canon(raw, ctx.stations, ignore_case=True)
            ic = True
        else:  # block
            val = _canon(raw, ctx.blocks, ignore_case=False)
            ic = False
        if val is None:
            return None, "slots"
        if ground and not _in_line(val, line, ic):
            return None, "slots"
        if slot in PERSON_SLOTS:
            people.append(val)
        out[slot] = val
    if len(set(people)) != len(people):
        return None, "slots"
    return out, "ok"


def regex_repair(obj, ctx):
    """Slot repair for a model proposal that failed grounding.

    Runs the template regexes on the cited line and accepts the result ONLY if
    it has the same relation type the model chose, so the model's decision
    about what the sentence means stays binding.  Returns a constraint or None.
    """
    try:
        line_no = int(obj.get("line_no"))
    except (TypeError, ValueError):
        return None
    if not 1 <= line_no <= len(ctx.body_lines):
        return None
    rc = normalize_constraint({"line_no": line_no}, ctx.body_lines, ctx.staff, ctx.stations, ctx.blocks)
    if rc is None or rc.get("type") != str(obj.get("type", "")).strip().lower():
        return None
    rc = dict(rc)
    rc["line_no"] = line_no
    return rc
