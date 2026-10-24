"""Build the /rest/api/3/workflows/update payload that drops the unused Created status and its
Start analysis transition from 'Workflow за Bug - со approval'."""
import json, sys, copy

src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding="utf-8"))
wf = copy.deepcopy(d["values"][0])
CREATED = "10462"

wf["statuses"] = [s for s in wf["statuses"] if s["statusReference"] != CREATED]
wf["transitions"] = [t for t in wf["transitions"] if t["id"] != "991"]

left = [t["id"] for t in wf["transitions"]
        if t.get("toStatusReference") == CREATED or any(l.get("fromStatusReference") == CREATED for l in t["links"])]
assert not left, f"transitions still reference Created: {left}"

used = {s["statusReference"] for s in wf["statuses"]}
statuses = [{k: s[k] for k in ("id", "statusReference", "name", "statusCategory", "description") if k in s}
            for s in d["statuses"] if s["statusReference"] in used]

keep = ("id", "version", "name", "description", "startPointLayout", "statuses", "transitions",
        "loopedTransitionContainerLayout")
# Jira requires an entry per project; no incident is in Created, so there is nothing to migrate.
INCIDENT = "10067"
projects = sys.argv[3].split(",")
wf_out = {k: wf[k] for k in keep if k in wf}
wf_out["statusMappings"] = [{"issueTypeId": INCIDENT, "projectId": pid,
                             "statusMigrations": []}
                            for pid in projects]
payload = {"statuses": statuses, "workflows": [wf_out]}
json.dump(payload, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("version", wf["version"]["versionNumber"], "| statuses", len(statuses), [s["name"] for s in statuses])
print("transitions", len(wf["transitions"]))
