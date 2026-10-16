import itertools

class ScheduleSolver:
    def __init__(self, staff, station_staff, blocks=None, stations=None):
        self.staff = staff
        self.station_staff = station_staff
        self.blocks = blocks or ["07:00", "09:00", "11:00", "13:00", "15:00"]
        self.stations = stations or ["intake", "calibration", "packing"]
        self.block_to_idx = {b: i for i, b in enumerate(self.blocks)}
        self.station_to_idx = {s: i for i, s in enumerate(self.stations)}
        
        # Precompute all 720 candidate schedules
        self.candidates = []
        time_perms = list(itertools.permutations(range(len(self.blocks))))
        st_perms = list(itertools.permutations(range(len(self.stations))))
        
        for tp in time_perms:
            t_map = {person: tp[i] for i, person in enumerate(self.staff)}
            for sp in st_perms:
                s_map = {person: self.stations[sp[i]] for i, person in enumerate(self.station_staff)}
                self.candidates.append((t_map, s_map))

    def check_candidate(self, cand, constraint):
        """Returns True if candidate satisfies constraint."""
        t_map, s_map = cand
        ctype = constraint["type"]
        
        if ctype == "assign_block":
            p = constraint["person"]
            b_idx = self.block_to_idx[constraint["block"]]
            return t_map.get(p) == b_idx
            
        elif ctype == "not_block":
            p = constraint["person"]
            b_idx = self.block_to_idx[constraint["block"]]
            return t_map.get(p) != b_idx
            
        elif ctype == "assign_station":
            p = constraint["person"]
            st = constraint["station"]
            return s_map.get(p) == st
            
        elif ctype == "not_station":
            p = constraint["person"]
            st = constraint["station"]
            return s_map.get(p) != st
            
        elif ctype == "before_person":
            p1 = constraint["person1"]
            p2 = constraint["person2"]
            return t_map[p1] < t_map[p2]
            
        elif ctype == "direct_after":
            p1 = constraint["person1"]
            p2 = constraint["person2"]
            return t_map[p1] == t_map[p2] + 1
            
        elif ctype == "between":
            p = constraint["person"]
            p1 = constraint["person1"]
            p2 = constraint["person2"]
            return min(t_map[p1], t_map[p2]) < t_map[p] < max(t_map[p1], t_map[p2])
            
        elif ctype == "station_before_person":
            st = constraint["station"]
            p = constraint["person"]
            st_holder = next((k for k, v in s_map.items() if v == st), None)
            if st_holder is None:
                return False
            return t_map[st_holder] < t_map[p]
            
        elif ctype == "person_before_station":
            p = constraint["person"]
            st = constraint["station"]
            st_holder = next((k for k, v in s_map.items() if v == st), None)
            if st_holder is None:
                return False
            return t_map[p] < t_map[st_holder]
            
        return True

    def count_valid(self, candidate_subset, constraints):
        valid = candidate_subset
        for c in constraints:
            valid = [cand for cand in valid if self.check_candidate(cand, c)]
            if not valid:
                return 0
        return len(valid)

    def solve(self, constraints):
        """
        Filters candidates through all constraints.
        Returns:
          case: "unique" | "ambiguous" | "inconsistent"
          valid_cands: list of (t_map, s_map)
        """
        valid = self.candidates
        for c in constraints:
            valid = [cand for cand in valid if self.check_candidate(cand, c)]
            if not valid:
                break
        
        if len(valid) == 1:
            return "unique", valid
        elif len(valid) > 1:
            return "ambiguous", valid
        else:
            return "inconsistent", []

    def find_minimal_unsat_core(self, constraints, by_line=True):
        """Deletion-filter a minimal unsatisfiable core.

        The scorer's unit is a *statement* (a line of the notes), so with
        by_line=True the filter removes whole lines at a time: every constraint
        extracted from one line is kept or dropped together.  That guarantees
        the cited set is minimal at the level the scorer checks.  by_line=False
        filters individual constraints (ablation arm).

        Returns the verbatim raw_line strings of the core, in note order.
        """
        if self.count_valid(self.candidates, constraints) > 0:
            return []

        groups = {}
        for c in constraints:
            gid = c.get("line_no") if by_line else id(c)
            if by_line and gid is None:
                gid = c.get("raw_line")
            groups.setdefault(gid, []).append(c)
        order = list(groups)

        def flat(ids):
            return [c for g in ids for c in groups[g]]

        core = list(order)
        i = 0
        while i < len(core):
            trial = core[:i] + core[i + 1:]
            if self.count_valid(self.candidates, flat(trial)) == 0:
                core.pop(i)      # still contradictory without it: not needed
            else:
                i += 1           # needed for the contradiction

        seen, result = set(), []
        for c in flat(core):
            line = c.get("raw_line")
            if line and line not in seen:
                seen.add(line)
                result.append(line)
        return result

    def format_assignment(self, cand):
        t_map, s_map = cand
        ans = {}
        for p in self.staff:
            entry = {"block": self.blocks[t_map[p]]}
            if p in s_map:
                entry["station"] = s_map[p]
            ans[p] = entry
        return ans
