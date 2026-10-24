import sys, json, base64, urllib.request
env = {}
for line in open(sys.argv[1], encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
url = env["JIRA_URL"].rstrip("/")
tok = base64.b64encode(f'{env["JIRA_USER"]}:{env["JIRA_API_TOKEN"]}'.encode()).decode()
body = open(sys.argv[3], encoding="utf-8").read().encode("utf-8")
req = urllib.request.Request(url + sys.argv[2], data=body, method="POST",
    headers={"Accept": "application/json", "Content-Type": "application/json", "Authorization": "Basic " + tok})
try:
    r = urllib.request.urlopen(req, timeout=120); code = r.status; text = r.read().decode("utf-8")
except urllib.error.HTTPError as e:
    code = e.code; text = e.read().decode("utf-8")
print(code)
try: out = json.dumps(json.loads(text), indent=1, ensure_ascii=False)
except Exception: out = text
if len(sys.argv) > 4: open(sys.argv[4], "w", encoding="utf-8").write(out)
print(out[:5000])
