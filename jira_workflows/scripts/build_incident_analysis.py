"""Build the /rest/api/3/workflows/update payload that adds Analysis + Billable Type gating
to 'Workflow за Bug - со approval'. Reads the saved current definition; writes the payload."""
import json, sys, copy

src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding="utf-8"))
wf = copy.deepcopy(d["values"][0])

ANALYSIS_REF = "5f0c7f4e-2a51-4c1e-9d8b-6a1d3b7e9a01"   # temp reference for the new status
CREATED, ESTIMATING, WAIT_SUPPORT = "10462", "10496", "10066"
BILLABLE_FIELD, BILLABLE, NON_BILLABLE = "customfield_10421", "10449", "10450"
AUTOMATION_USER = "557058:f58131cb-b67d-43c7-b30d-6b58d40bd077"   # Automation for Jira (DMS <-> clone sync)

def gate(option_id):
    """Allow when Billable Type = option, OR when the sync automation is doing the move."""
    return {
        "operation": "ANY",
        "conditionGroups": [],
        "conditions": [
            {"ruleKey": "system:check-field-value",
             "parameters": {"fieldId": BILLABLE_FIELD, "fieldValue": json.dumps([option_id]),
                            "comparator": "=", "comparisonType": "OPTIONID"}},
            {"ruleKey": "system:restrict-issue-transition",
             "parameters": {"accountIds": AUTOMATION_USER, "roleIds": "", "groupIds": "", "permissionKeys": "",
                            "groupCustomFields": "", "allowUserCustomFields": "", "denyUserCustomFields": ""}},
        ],
    }

statuses = [{k: s[k] for k in ("id", "statusReference", "name", "statusCategory", "description") if k in s}
            for s in d["statuses"]]
statuses.append({"statusReference": ANALYSIS_REF, "name": "Analysis", "statusCategory": "TODO",
                 "description": "The incident is being analysed to decide whether it is billable."})

wf["statuses"].append({"statusReference": ANALYSIS_REF, "layout": {"x": -401.36, "y": -580.0},
                       "properties": {}, "deprecated": False})
created = next(s for s in wf["statuses"] if s["statusReference"] == CREATED)
created["layout"] = {"x": -130.0, "y": -700.0}

for t in wf["transitions"]:
    if t["id"] == "1":                       # Create issue -> Analysis (was Created)
        t["toStatusReference"] = ANALYSIS_REF
    elif t["id"] == "2":                     # Analysis -> Waiting for support, Non-Billable only
        t["links"] = [{"fromStatusReference": ANALYSIS_REF, "fromPort": 7, "toPort": 0}]
        t["conditions"] = gate(NON_BILLABLE)
    elif t["id"] == "4":                     # Analysis -> Estimating, Billable only
        t["name"] = "Start estimating"
        t["links"] = [{"fromStatusReference": ANALYSIS_REF, "fromPort": 5, "toPort": 1}]
        t["conditions"] = gate(BILLABLE)
    elif t["id"] == "7":                     # Estimating -> Waiting for support only if re-classified Non-Billable
        t["conditions"] = gate(NON_BILLABLE)

# Created stays for the 6 issues already in it; give them a way into Analysis.
wf["transitions"].append({
    "id": "991", "type": "DIRECTED", "name": "Start analysis", "description": "",
    "toStatusReference": ANALYSIS_REF,
    "links": [{"fromStatusReference": CREATED, "fromPort": 6, "toPort": 2}],
    "actions": [], "validators": [], "triggers": [], "properties": {},
    "conditions": {"operation": "ALL", "conditions": [], "conditionGroups": []},
})

keep = ("id", "version", "name", "description", "startPointLayout", "statuses", "transitions",
        "loopedTransitionContainerLayout")
used = {s["statusReference"] for s in wf["statuses"]}
payload = {"statuses": [s for s in statuses if s["statusReference"] in used], "workflows": [{k: wf[k] for k in keep if k in wf}]}
json.dump(payload, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", out, "| statuses", len(statuses), "| transitions", len(wf["transitions"]))
