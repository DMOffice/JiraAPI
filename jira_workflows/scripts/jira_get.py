import sys, json, base64, urllib.request
env = {}
for line in open(sys.argv[1], encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
url = env["JIRA_URL"].rstrip("/")
tok = base64.b64encode(f'{env["JIRA_USER"]}:{env["JIRA_API_TOKEN"]}'.encode()).decode()
req = urllib.request.Request(url + sys.argv[2], headers={"Accept": "application/json", "Authorization": "Basic " + tok})
try:
    resp = urllib.request.urlopen(req, timeout=60); code = resp.status; body = resp.read().decode("utf-8")
except urllib.error.HTTPError as e:
    code = e.code; body = e.read().decode("utf-8")
print(code)
try: out = json.dumps(json.loads(body), indent=1, ensure_ascii=False)
except Exception: out = body
if len(sys.argv) > 3: open(sys.argv[3], "w", encoding="utf-8").write(out)
else: print(out[:6000])
