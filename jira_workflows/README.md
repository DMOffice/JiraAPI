# Jira workflow changes: System Incident and Барање

These scripts and backups record the changes made on 2026-10-24 to the two workflows that DMS and its client-project clones share. They are here so the changes can be reviewed and, if needed, rolled back.

| Workflow | Issue type | Workflow id |
| --- | --- | --- |
| Workflow за Bug - со approval | [System] Incident (10067) | 895673cf-772c-4a32-ad0f-c2449bf88e6b |
| Workflow за Барање | Барање (10463) | 7943bd55-b4bf-4028-927d-79d0d7e6aa85 |

Both workflows are used by two workflow schemes (10067 for DMS/MAIN, 10134 for the client projects), so 13 projects in total. The DMS ↔ clone automation matches statuses **by name**, so DMS and the clones must stay on the same workflow.

## What changed

| Workflow | Version | Change | Script |
| --- | --- | --- | --- |
| Incident | 30 → 31 | New first status **Analysis** (id 10803). Non-Billable / Billable exits gated on Billable Type. Created kept, with a "Start analysis" transition | `build_incident_analysis.py` |
| Incident | 31 → 33 | Created and "Start analysis" removed (no incident was in Created) | `build_remove_created.py` |
| Барање | 45 → 47 | Analysis first. New "Non-Billable request" exit. "Start estimating" gated on Billable. "Continue with internal approval" allowed only when Non-Billable. Created removed, and its 6 issues migrated to Analysis | `build_baranje_analysis.py ... gate` |
| Incident, Барање | 33 → 34, 47 → 48 | Both Analysis exits always shown. Each sets Billable Type to match its path (update-field post-function) | `build_button_sets_field.py` |

The two "→ 33" and "→ 47" steps went up by two versions because the status migration publishes again.

Billable Type is `customfield_10421`: Billable = 10449, Non-Billable = 10450. Every Billable Type gate is an ANY group that also lets the "Automation for Jira" user (`557058:f58131cb-b67d-43c7-b30d-6b58d40bd077`) through, so the sync automation can mirror a move.

## Files

- `backups/<incident|baranje>_v<N>.json`: each workflow as returned by `GET /rest/api/3/workflows/search?expand=values.transitions`, keeping only its own statuses. `incident_v34.json` and `baranje_v48.json` are the versions live at the time of this commit.
- `scripts/jira_get.py`, `scripts/jira_post.py`: minimal REST helpers. They read `JIRA_URL`, `JIRA_USER` and `JIRA_API_TOKEN` from the `.env` path you pass in. The credentials are never stored here.
- `scripts/wait_for_sync.py`: waits for issues to reach a status, then prints each issue's Billable Type and available transitions.
- `scripts/build_*.py`: each turns a backup into the `POST /rest/api/3/workflows/update` payload for one step above.

## Running them

Run from the repo root in Git Bash. `MSYS_NO_PATHCONV=1` stops Git Bash rewriting `/rest/...` into a Windows path.

```bash
export MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8
python jira_workflows/scripts/jira_get.py .env "/rest/api/3/workflows/search?queryString=<url-encoded name>&expand=values.transitions" current.json
```

Always validate before updating. Wrap the payload as `{"payload": <payload>, "validationOptions": {"levels": ["ERROR", "WARNING"]}}`:

```bash
python jira_workflows/scripts/jira_post.py .env /rest/api/3/workflows/update/validation validate_body.json
```

```bash
python jira_workflows/scripts/jira_post.py .env /rest/api/3/workflows/update payload.json result.json
```

If the update returns a `taskId`, poll `GET /rest/api/3/task/<taskId>` until it reports `COMPLETE`.

## Rolling back

An update must carry the workflow's **current** version, so a backup can't be posted as it is. To roll back:

1. Fetch the live workflow.
2. Take `statuses` and `transitions` from the backup, and the `id` and `version` from the live copy.
3. Validate, then update.

If the rollback removes a status, Jira needs two extra things:

- A `statusMappings` entry for every one of the 13 projects (with the issue type id), each with a non-empty old → new migration.
- The removed status still listed in the payload's top-level `statuses`. Without it, validation fails with `OLD_STATUS_MISSING_IN_ORIGINAL_WORKFLOW`.

`build_remove_created.py` shows both.

These changes were applied with the ETL's Jira login (Marko Pajkovski), so they appear under that account in Jira's audit log.
