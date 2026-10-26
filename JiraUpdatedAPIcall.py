import os
import urllib.parse

import pandas as pd
import sqlalchemy as sa
from atlassian import Jira
from dotenv import load_dotenv
from sqlalchemy import Text
from sqlalchemy.dialects.mssql import DATETIME2, FLOAT, NVARCHAR

load_dotenv()


JIRA_INSTANCES = {
    "url": os.environ.get("JIRA_URL"),
    "username": os.environ.get("JIRA_USER"),
    "api_token": os.getenv("JIRA_API_TOKEN")
}


def normalize_custom_field(value):
    """
    Safely normalize Jira custom field values into a string-friendly format.
    Handles scalars, dicts, lists, and None.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        if "value" in value:
            return value.get("value")
        if "displayName" in value:
            return value.get("displayName")
        if "name" in value:
            return value.get("name")
        return str(value)

    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(
                    item.get("value")
                    or item.get("displayName")
                    or item.get("name")
                    or str(item)
                )
            else:
                normalized.append(str(item))
        return ", ".join([str(x) for x in normalized if x is not None])

    return value


def get_linked_issue_keys(issue_links):
    """
    Returns the keys of all issues linked to this one (any link type, either
    direction) as a sorted, comma-separated string, or None when there are none.
    """
    keys = set()
    for link in issue_links or []:
        linked_issue = link.get("outwardIssue") or link.get("inwardIssue") or {}
        if linked_issue.get("key"):
            keys.add(linked_issue["key"])
    return ", ".join(sorted(keys)) or None


def get_sprint_data(sprints):
    """
    Returns the issue's current sprint (the active one, else the one that started
    last) plus the names of every sprint the issue has been in, oldest first.
    Dates are returned as YYYY-MM-DD strings; all values are None without sprints.
    """
    sprints = [s for s in sprints or [] if isinstance(s, dict)]
    if not sprints:
        return {"sprint_name": None, "sprint_state": None, "sprint_start": None,
                "sprint_end": None, "sprint_names": None}

    def start_of(sprint):
        return sprint.get("startDate") or ""

    ordered = sorted(sprints, key=lambda s: (start_of(s), s.get("id") or 0))
    active = [s for s in ordered if s.get("state") == "active"]
    current = active[-1] if active else ordered[-1]

    return {
        "sprint_name": current.get("name"),
        "sprint_state": current.get("state"),
        "sprint_start": (current.get("startDate") or "")[:10] or None,
        "sprint_end": (current.get("endDate") or "")[:10] or None,
        "sprint_names": ", ".join(s.get("name") or "" for s in ordered),
    }


def process_issue_batch(jira, issues):
    issue_batch = []

    for issue in issues:
        worklog_data = issue["fields"].get("worklog")
        all_worklogs = []

        if worklog_data:
            all_worklogs.extend(worklog_data.get("worklogs", []))

            total_worklogs = worklog_data.get("total", 0)
            fetched_count = len(all_worklogs)

            if total_worklogs > fetched_count:
                # The search embeds the first 20 worklogs sorted by start date, but the
                # worklog endpoint pages them in creation order. Continuing from item 21
                # would skip backdated worklogs, so fetch the full list from the start.
                all_worklogs = []
                worklog_start_at = 0
                worklog_page_size = 50

                while worklog_start_at < total_worklogs:
                    worklog_path = f"rest/api/3/issue/{issue['key']}/worklog"
                    worklog_params = {
                        "startAt": worklog_start_at,
                        "maxResults": worklog_page_size
                    }
                    worklog_results = jira.get(worklog_path, params=worklog_params)

                    new_worklogs = worklog_results.get("worklogs", [])
                    if not new_worklogs:
                        break

                    all_worklogs.extend(new_worklogs)
                    worklog_start_at += len(new_worklogs)
                    total_worklogs = worklog_results.get("total", total_worklogs)

            issue["fields"]["worklog"]["worklogs"] = all_worklogs
            issue["fields"]["worklog"]["total"] = len(all_worklogs)
            issue["fields"]["worklog"]["maxResults"] = len(all_worklogs)

        issue_batch.append(issue)

    return issue_batch


def fetch_issues_for_instance(instance_config):
    """
    Connects to a Jira instance and fetches all issues and all their worklogs
    using nested pagination.
    """
    jira_url = instance_config["url"]
    jira_username = instance_config["username"]
    jira_api_token = instance_config["api_token"]

    try:
        jira = Jira(
            url=jira_url,
            username=jira_username,
            password=jira_api_token,
            cloud=True
        )
    except Exception as e:
        print(f"Error connecting to {jira_url}: {e}")
        return []

    all_instance_issues = []

    try:
        projects = jira.get_all_projects()
        print(f"Found {len(projects)} projects.")
    except Exception as e:
        print(f"Error fetching projects: {e}")
        return []

    for project in projects:
        project_key = project["key"]

        project_issues_batch = []
        project_issues_batch_keys = []

        page_size = 100
        search_path = "rest/api/3/search/jql"
        jql_query = f'project = "{project_key}"'

        fields_list = (
            "summary, status, issuetype, created, project, worklog, "
            "customfield_10421, customfield_10355, labels, assignee, "
            "reporter, description, priority, timetracking, creator, parent, "
            "duedate, timeoriginalestimate, customfield_10015, customfield_10777, issuelinks, resolution, "
            "customfield_10020"
        )

        params = {
            "jql": jql_query,
            "maxResults": page_size,
            "fields": fields_list
        }

        results = jira.get(search_path, params=params)
        issues = results.get("issues", [])
        project_issues_batch += process_issue_batch(jira, issues)
        project_issues_batch_keys += [issue.get("key") for issue in issues]

        while results.get("nextPageToken", 0) != 0:
            params = {
                "jql": jql_query,
                "maxResults": page_size,
                "nextPageToken": results.get("nextPageToken"),
                "fields": fields_list
            }

            results = jira.get(search_path, params=params)
            issues = results.get("issues", [])

            if not issues:
                break

            project_issues_batch += process_issue_batch(jira, issues)
            project_issues_batch_keys += [issue.get("key") for issue in issues]

        all_instance_issues.extend(project_issues_batch)

    print(len(project_issues_batch), len(set(project_issues_batch_keys)))
    print(f"\nTotal issues fetched from {jira_url}: {len(all_instance_issues)}")
    return all_instance_issues


def get_timetracking_data_by_person_date_project_and_source(issues_list):
    """
    Processes a list of issues and aggregates time spent per user, date,
    project, and source URL.
    """
    timetracking_data = {}
    processed_worklog_ids = set()
    timetrack_list = []

    for issue in issues_list:
        project_name = issue.get("fields", {}).get("project", {}).get("name", "Unknown Project")
        issue_key = issue.get("key")
        worklogs = issue.get("fields", {}).get("worklog", {}).get("worklogs", [])
        billable_type = (issue.get("fields", {}).get("customfield_10421", {}) or {}).get("value")
        source_url = issue.get("source_url", "Unknown Source")

        for worklog in worklogs:
            worklog_id = worklog.get("id")
            if worklog_id in processed_worklog_ids:
                continue

            processed_worklog_ids.add(worklog_id)

            author_name = worklog.get("author", {}).get("emailAddress", "Unknown")
            started_date = worklog.get("started", "").split("T")[0]
            time_spent_seconds = worklog.get("timeSpentSeconds", 0)
            time_spent_minutes = time_spent_seconds / 60
            time_spent_hours = time_spent_minutes / 60

            if author_name not in timetracking_data:
                timetracking_data[author_name] = {}

            if started_date not in timetracking_data[author_name]:
                timetracking_data[author_name][started_date] = {}

            project_source_key = (project_name, source_url)
            if project_source_key not in timetracking_data[author_name][started_date]:
                timetracking_data[author_name][started_date][project_source_key] = 0

            time_entry = {
                "employee": author_name,
                "date": started_date,
                "project": project_name,
                "issue_key": issue_key,
                "hours": time_spent_hours,
                "source_url": source_url,
                "billable_type": billable_type
            }

            timetracking_data[author_name][started_date][project_source_key] += time_spent_hours
            timetrack_list.append(time_entry)

    return pd.DataFrame(timetrack_list)


def get_issue_data(issues_list):
    """
    Processes a list of issues and gets their data.
    """
    issues_data = []

    for issue in issues_list:
        fields = issue.get("fields", {})

        try:
            work_description = fields.get("description", {}).get("content", "Unknown Reporter")
        except Exception:
            work_description = "No Description"

        value_dict = {
            "project": fields.get("project", {}).get("name", "Unknown Project"),
            "creator": fields.get("creator", {}).get("displayName", "Unknown Creator"),
            "assignee": (fields.get("assignee") or {}).get("displayName", "Unknown Assignee"),
            "reporter": (fields.get("reporter", {}) or {}).get("displayName", "Unknown Reporter"),
            "work_description": work_description,
            "issue_summary": fields.get("summary", {}),
            "issue_key": issue.get("key"),
            "issue_type": fields.get("issuetype", {}).get("name", {}),
            "issue_status": fields.get("status", {}).get("name", {}),
            "status_category": ((fields.get("status") or {}).get("statusCategory") or {}).get("name"),
            "resolution": (fields.get("resolution") or {}).get("name"),
            "issue_priority": fields.get("priority", {}).get("name"),
            "billable_type": (fields.get("customfield_10421", {}) or {}).get("value"),
            "company": (fields.get("customfield_10777", {}) or {}).get("value"),
            "client_contact": normalize_custom_field(fields.get("customfield_10355")),
            "parent_key": (fields.get("parent", {}) or {}).get("key"),
            "parent_summary": ((fields.get("parent", {}) or {}).get("fields") or {}).get("summary"),
            "labels": " , ".join(fields.get("labels", [])),
            "epic_name": ((fields.get("parent", {}) or {}).get("fields") or {}).get("summary"),
            "startdate": fields.get("customfield_10015", None),
            "due_date": fields.get("duedate", None),
            "original_estimate_minutes": fields.get("timeoriginalestimate", None),
            "linked_issue_keys": get_linked_issue_keys(fields.get("issuelinks")),
            **get_sprint_data(fields.get("customfield_10020")),
        }

        val = value_dict.get("original_estimate_minutes")
        value_dict["original_estimate_minutes"] = val / 60 if val is not None else None

        issues_data.append(value_dict)

    return issues_data


load_time = pd.Timestamp.now().floor("s")

issues_from_instance = fetch_issues_for_instance(JIRA_INSTANCES)

df_timetracking = get_timetracking_data_by_person_date_project_and_source(issues_from_instance)
df_timetracking = df_timetracking.drop("source_url", axis=1)
df_timetracking["load_time"] = load_time

issues_data = get_issue_data(issues_from_instance)
issues_data = pd.DataFrame(issues_data)
issues_data["load_time"] = load_time


driver = os.environ.get("SQL_DRIVER")
server = os.environ.get("SQL_SERVER")
database = os.environ.get("SQL_DATABASE")

odbc_str = (
    f"DRIVER={{{driver}}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    "Trusted_Connection=Yes;"
    "TrustServerCertificate=Yes;"
)

params = urllib.parse.quote_plus(odbc_str)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}", echo=False)


timetracking_dtype_mapping = {
    "date": NVARCHAR(50),
    "employee": Text,
    "project": NVARCHAR(1000),
    "issue_key": NVARCHAR(1000),
    "billable_type": NVARCHAR(1000),
    "hours": FLOAT,
    "load_time": DATETIME2
}

df_timetracking.to_sql(
    "JiraWorklog",
    con=engine,
    schema="dbo",
    if_exists="replace",
    index=False,
    dtype=timetracking_dtype_mapping
)


issues_dtype_mapping = {
    "project": NVARCHAR(1000),
    "creator": NVARCHAR(1000),
    "assignee": NVARCHAR(1000),
    "reporter": NVARCHAR(1000),
    "work_description": NVARCHAR(1000),
    "issue_summary": NVARCHAR(1000),
    "issue_key": NVARCHAR(1000),
    "issue_type": NVARCHAR(1000),
    "issue_status": NVARCHAR(1000),
    "status_category": NVARCHAR(1000),
    "resolution": NVARCHAR(1000),
    "issue_priority": NVARCHAR(1000),
    "billable_type": NVARCHAR(1000),
    "company": NVARCHAR(1000),
    "client_contact": NVARCHAR(1000),
    "parent_key": NVARCHAR(1000),
    "parent_summary": NVARCHAR(1000),
    "labels": NVARCHAR(1000),
    "epic_name": NVARCHAR(1000),
    "startdate": NVARCHAR(50),
    "due_date": NVARCHAR(50),
    "original_estimate_minutes": FLOAT,
    "linked_issue_keys": NVARCHAR(4000),
    "sprint_name": NVARCHAR(1000),
    "sprint_state": NVARCHAR(50),
    "sprint_start": NVARCHAR(50),
    "sprint_end": NVARCHAR(50),
    "sprint_names": NVARCHAR(4000),
    "load_time": DATETIME2
}

issues_data.to_sql(
    "JiraIssuesData",
    con=engine,
    schema="dbo",
    if_exists="replace",
    index=False,
    dtype=issues_dtype_mapping
)