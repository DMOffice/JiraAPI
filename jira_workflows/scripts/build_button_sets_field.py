"""Build a /rest/api/3/workflows/update payload where both exits out of Analysis are always shown and
each one sets Billable Type to match its path (so the field is never empty or inconsistent).
Usage: build_button_sets_field.py <backup.json> <out.json> <non_billable_transition_id> <billable_transition_id>"""
import json, sys, copy

src, out, non_billable_tid, billable_tid = sys.argv[1:5]
d = json.load(open(src, encoding="utf-8"))
wf = copy.deepcopy(d["values"][0])
ANALYSIS, BILLABLE_FIELD = "10803", "customfield_10421"
SETS = {non_billable_tid: "10450", billable_tid: "10449"}   # Non-Billable / Billable option ids

for t in wf["transitions"]:
    if t["id"] in SETS:
        assert [l["fromStatusReference"] for l in t["links"]] == [ANALYSIS], f"T{t['id']} is not an Analysis exit"
        t["conditions"] = {"operation": "ALL", "conditions": [], "conditionGroups": []}
        t["actions"] = [a for a in t.get("actions", []) if a["ruleKey"] != "system:update-field"
                        or a["parameters"].get("field") != BILLABLE_FIELD]
        t["actions"].append({"ruleKey": "system:update-field",
                             "parameters": {"field": BILLABLE_FIELD, "value": SETS[t["id"]], "mode": "replace"}})
        print(f"T{t['id']} '{t['name']}': no condition, sets Billable Type = {SETS[t['id']]}")

used = {s["statusReference"] for s in wf["statuses"]}
statuses = [{k: s[k] for k in ("id", "statusReference", "name", "statusCategory", "description") if k in s}
            for s in d["statuses"] if s["statusReference"] in used]
keep = ("id", "version", "name", "description", "startPointLayout", "statuses", "transitions",
        "loopedTransitionContainerLayout")
json.dump({"statuses": statuses, "workflows": [{k: wf[k] for k in keep if k in wf}]},
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
