#!/usr/bin/env python3
# Copied from the paper's experiment (demo_v2/ground_truth/map_defensible.py) as a worked example. Only the
# path set-up changed: set ZHANG_DEMO_ROOT to the experiment folder. Outputs are written there, as in
# the experiment; copy the folder first if you want to keep the original results untouched.
"""
Mapping under the "defensible" rule: a code maps to every one of Zhang et al.'s categories that a thread
carrying the code could defensibly be coded with under that category's definition (neighbouring
categories that describe the same problem from another angle both count). Same machinery as
map_debate.py (two mappers, debate, judge); definitions only, no thread and no label is seen.
Mappers: Claude Opus 5 and GPT-5.6 Sol; GPT-5.6 Sol judges disputed cells.
  python3 map_defensible.py <codebook.json> <out.json>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_debate as md  # the copy next to this file

RULE_OLD = ("For each team-1 code, list every team-2 category that a thread carrying the team-1 code would\n"
            "also carry, under team 2's definition, in at least a typical case.")
RULE_NEW = ("For each team-1 code, list every team-2 category that a thread carrying the team-1 code could\n"
            "defensibly be coded with under team 2's definition: a careful coder applying team 2's scheme to such\n"
            "a thread might reasonably choose that category. Team 2 often gives a thread only one category per\n"
            "question, so where two neighbouring categories describe the same problem from different angles,\n"
            "list both. Do not list a category that the code's definition or exclude clause rules out.")
assert RULE_OLD in md.BRIEF
md.BRIEF = md.BRIEF.replace(RULE_OLD, RULE_NEW)
md.DEBATE = md.DEBATE.replace("would typically also carry the category under team 2's definition",
                              "could defensibly be coded with the category under team 2's definition "
                              "(neighbouring categories describing the same problem from another angle both count)")
md.JUDGE_BRIEF = md.JUDGE_BRIEF.replace("map it\nwhen a thread carrying the code would typically also carry the category under the category's\ndefinition",
                                        "map it\nwhen a thread carrying the code could defensibly be coded with the category under the category's\n"
                                        "definition (neighbouring categories describing the same problem from another angle both count)")
md.MAPPERS = {"claude": "claude-opus-5", "gpt": "gpt-5.6-sol"}
md.JUDGE = "gpt-5.6-sol"

if __name__ == "__main__":
    md.main()
