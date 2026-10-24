"""Poll clone issues until they reach the target status, then list available transitions."""
import sys, json, base64, time, urllib.request
env = {}
for line in open(sys.argv[1], encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
url = env["JIRA_URL"].rstrip("/")
tok = base64.b64encode(f'{env["JIRA_USER"]}:{env["JIRA_API_TOKEN"]}'.encode()).decode()
def get(path):
    req = urllib.request.Request(url + path, headers={"Accept": "application/json", "Authorization": "Basic " + tok})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())
target, keys = sys.argv[2], sys.argv[3].split(",")
check = sys.argv[4].split(",") if len(sys.argv) > 4 else keys
pending, start = set(keys), time.time()
while pending and time.time() - start < 120:
    for k in list(pending):
        s = get(f"/rest/api/3/issue/{k}?fields=status")["fields"]["status"]["name"]
        if s == target:
            print(f"{k} reached {target} after {time.time() - start:.0f}s"); pending.discard(k)
    if pending: time.sleep(5)
for k in pending: print(f"{k} did NOT reach {target} within 120s")
for k in check:
    f = get(f"/rest/api/3/issue/{k}?fields=status,customfield_10421")["fields"]
    tr = get(f"/rest/api/3/issue/{k}/transitions")["transitions"]
    print(f"{k}: status={f['status']['name']} billable={(f.get('customfield_10421') or {}).get('value')} exits={[(t['name'], t['to']['name']) for t in tr]}")
