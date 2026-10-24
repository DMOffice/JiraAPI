"""Build the /rest/api/3/workflows/update payload for 'Workflow за Барање': Analysis as the first
status, exits gated on Billable Type, and Created removed (its issues migrate to Analysis).
Usage: build_baranje_analysis.py <backup.json> <out.json> <project_ids_csv> <keep|gate>  (internal approval exit)"""
import json, sys, copy

src, out, projects, internal = sys.argv[1], sys.argv[2], sys.argv[3].split(","), sys.argv[4]
d = json.load(open(src, encoding="utf-8"))
wf = copy.deepcopy(d["values"][0])

ANALYSIS, CREATED, WAIT_SUPPORT, REQUEST = "10803", "10462", "10066", "10463"
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

# Analysis takes Created's place on the canvas; Created leaves the workflow.
created = next(s for s in wf["statuses"] if s["statusReference"] == CREATED)
wf["statuses"] = [s for s in wf["statuses"] if s["statusReference"] != CREATED]
wf["statuses"].append({"statusReference": ANALYSIS, "layout": created["layout"], "properties": {}, "deprecated": False})

for t in wf["transitions"]:
    if t["id"] == "1":                       # Create issue -> Analysis (was Created)
        t["toStatusReference"] = ANALYSIS
    elif t["id"] == "4":                     # Analysis -> Estimating, Billable only
        t["name"] = "Start estimating"
        t["links"] = [dict(l, fromStatusReference=ANALYSIS) for l in t["links"]]
        t["conditions"] = gate(BILLABLE)
    elif t["id"] == "9" and internal == "gate":   # Estimating -> Waiting for support only if re-classified Non-Billable
        t["conditions"] = gate(NON_BILLABLE)

wf["transitions"].append({
    "id": "991", "type": "DIRECTED", "name": "Non-Billable request", "description": "",
    "toStatusReference": WAIT_SUPPORT,
    "links": [{"fromStatusReference": ANALYSIS, "fromPort": 7, "toPort": 0}],
    "actions": [], "validators": [], "triggers": [], "properties": {},
    "conditions": gate(NON_BILLABLE),
})

left = [t["id"] for t in wf["transitions"]
        if t.get("toStatusReference") == CREATED or any(l.get("fromStatusReference") == CREATED for l in t["links"])]
assert not left, f"transitions still reference Created: {left}"

# Jira needs the removed status kept in the top-level list, plus a mapping per project.
used = {s["statusReference"] for s in wf["statuses"]} | {CREATED}
statuses = [{k: s[k] for k in ("id", "statusReference", "name", "statusCategory", "description") if k in s}
            for s in d["statuses"] if s["statusReference"] in used]
statuses.append({"id": ANALYSIS, "statusReference": ANALYSIS, "name": "Analysis", "statusCategory": "TODO",
                 "description": "Being analysed to decide whether the work is billable."})

keep = ("id", "version", "name", "description", "startPointLayout", "statuses", "transitions",
        "loopedTransitionContainerLayout")
wf_out = {k: wf[k] for k in keep if k in wf}
wf_out["statusMappings"] = [{"issueTypeId": REQUEST, "projectId": pid,
                             "statusMigrations": [{"oldStatusReference": CREATED, "newStatusReference": ANALYSIS}]}
                            for pid in projects]
payload = {"statuses": statuses, "workflows": [wf_out]}
json.dump(payload, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("version", wf["version"]["versionNumber"], "| internal approval:", internal,
      "| workflow statuses", len(wf["statuses"]), "| transitions", len(wf["transitions"]))
