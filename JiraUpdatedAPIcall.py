import os
from atlassian import Jira
import pandas as pd
from dotenv import load_dotenv
load_dotenv()



JIRA_INSTANCES =  {
        "url": os.environ.get("JIRA_URL"),
        "username": os.environ.get("JIRA_USER"),
        "api_token":os.getenv("JIRA_API_TOKEN")
    }




def process_issue_batch(jira, issues):
    
    issue_batch = []
    worklog_ids  =[]

    for issue in issues:
        
        # print(issue['key'])
        # Get the first page of worklogs (comes with the issue search)
        worklog_data = issue['fields'].get('worklog')
        all_worklogs = []
        
        if worklog_data:
            all_worklogs.extend(worklog_data.get('worklogs', []))

            total_worklogs = worklog_data.get('total', 0)
            fetched_count = len(all_worklogs)

            # --- START: Nested loop to fetch all worklog pages ---
            if total_worklogs > fetched_count:
                # We need to fetch the remaining pages
                worklog_start_at = fetched_count
                worklog_page_size = 50 # Page size for worklog endpoint

                while worklog_start_at < total_worklogs:
                    worklog_path = f"rest/api/3/issue/{issue['key']}/worklog"
                    worklog_params = {
                        'startAt': worklog_start_at,
                        'maxResults': worklog_page_size
                    }
                    worklog_results = jira.get(worklog_path, params=worklog_params)

                    new_worklogs = worklog_results.get('worklogs', [])
                    if not new_worklogs:
                        break 

                    all_worklogs.extend(new_worklogs)
                    worklog_start_at += len(new_worklogs)



            # --- END: Nested loop ---

            # Replace the partial 'worklogs' list with the complete one
            issue['fields']['worklog']['worklogs'] = all_worklogs
            issue['fields']['worklog']['total'] = len(all_worklogs)
            issue['fields']['worklog']['maxResults'] = len(all_worklogs)

        issue_batch.append(issue)

    return issue_batch




def fetch_issues_for_instance(instance_config):
    """
    Connects to a Jira instance and fetches all issues and *all* their
    worklogs using nested pagination.
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
        
        
        project_key = project['key']
    

        # print(f"  - Fetching issues for project: {project_key}...")

        # --- START: Manual 100-by-100 Pagination Workaround ---
        project_issues_batch = []
        project_issues_batch_keys = []
        start_at = 0
        page_size = 100  # Fetch 100 issues at a time

        search_path = 'rest/api/3/search/jql'
        jql_query = f'project = "{project_key}"'
        
        params = {
                    'jql': jql_query,
                    'maxResults': page_size,
                    'fields': """summary, status, issuetype, created, project, worklog, customfield_10421, labels, assignee,
                    reporter, description, priority, timetracking, creator, parent, duedate, timeoriginalestimate, startdate""" # <-- ADDED FIELDS
                }

        results = jira.get(search_path, params=params)
        issues = results.get('issues', [])  
        project_issues_batch += process_issue_batch(jira, issues)
        
        
        
            
        while results.get("nextPageToken",0) != 0:

                params = {
                            'jql': jql_query,
                            'maxResults': page_size,
                            'nextPageToken':results.get("nextPageToken"),
                            'fields': """summary, status, issuetype, created, project, worklog, customfield_10421, labels, assignee,
                            reporter, description, priority, timetracking, creator, parent""" # <-- ADDED FIELDS
                        }

                results = jira.get(search_path, params=params)
                issues = results.get('issues', [])
            
                if not issues:
                    break

                # --- CHANGE 2: Process issues to get all worklogs ---
                
                project_issues_batch += process_issue_batch(jira, issues)
                # --- END OF CHANGES ---

                # Prepare for the next page
                
                

        
        # print(f"    -> Found {len(project_issues_batch)} issues for {project_key}.")
        all_instance_issues.extend(project_issues_batch)
        
        
    # --- END: Manual Pagination Workaround ---
    print(len(project_issues_batch),len(set(project_issues_batch_keys)))
    print(f"\nTotal issues fetched from {jira_url}: {len(all_instance_issues)}")
    return all_instance_issues

def get_timetracking_data_by_person_date_project_and_source(issues_list):
    """
    Processes a list of issues and aggregates time spent per user, date, project, and source URL.
    """
    timetracking_data = {}
    processed_worklog_ids = set()
    timetrack_list = []
    for issue in issues_list:
        project_name = issue.get('fields', {}).get('project', {}).get('name', 'Unknown Project')
        issue_key = issue.get('key')
        worklogs = issue.get('fields', {}).get('worklog', {}).get('worklogs', [])
        billable_type = (issue.get('fields',{}).get('customfield_10421', {})or {}).get('value')
        source_url = issue.get('source_url', 'Unknown Source')
        
        for worklog in worklogs:
            
            worklog_id = worklog.get('id')
            if worklog_id in processed_worklog_ids:
                continue
            
            processed_worklog_ids.add(worklog_id)

            author_name = worklog.get('author', {}).get('emailAddress', 'Unknown')
            started_date = worklog.get('started', '').split('T')[0]
            time_spent_seconds = worklog.get('timeSpentSeconds', 0)
            time_spent_minutes = time_spent_seconds / 60
            time_spent_hours = time_spent_minutes / 60
            

            if author_name not in timetracking_data:
                timetracking_data[author_name] = {}
            
            if started_date not in timetracking_data[author_name]:
                timetracking_data[author_name][started_date] = {}
            
            # Using a tuple as key to handle different projects from different sources
            project_source_key = (project_name, source_url)
            if project_source_key not in timetracking_data[author_name][started_date]:
                timetracking_data[author_name][started_date][project_source_key] = 0
            
            
            time_entry = {'employee':author_name,
                          'date':started_date,
                          'project':project_name,
                          'issue_key':issue_key,
                          'hours':time_spent_hours,
                          'source_url':source_url,
                          'billable_type':billable_type}
            
            timetracking_data[author_name][started_date][project_source_key] += time_spent_hours
            timetrack_list.append(time_entry)
    return pd.DataFrame(timetrack_list)


def get_issue_data(issues_list):
    """
    Processes a list of issues and get their data
    """
    issues_data =[]
    
    for issue in issues_list:
        fields = issue.get('fields', {})
  
    
        try:
           work_description =  fields.get('description', {}).get('content', 'Unknown Reporter')
        except:
           work_description = 'No Description'
           
           

     
        blank = 'BLANK'
        value_dict = {'project':fields.get('project', {}).get('name', 'Unknown Project'),
                      'creator':fields.get('creator', {}).get('displayName', 'Unknown Creator'),
                      'assignee':(fields.get('assignee') or {}).get('displayName', 'Unknown Asignee'),
                      'reporter':(fields.get('reporter', {})or {}).get('displayName', 'Unknown Reporter'),
                      'work_description':work_description,
                      'issue_summary':fields.get('summary', {}),
                      'issue_key':issue.get('key'),
                      'issue_type':fields.get('issuetype', {}).get('name', {}),
                      'issue_status':fields.get('status', {}).get('name', {}),
                      'issue_priority':fields.get('priority', {}).get('name'),
                      'billable_type':(fields.get('customfield_10421', {})or {}).get('value'),
                      'parent_key':(fields.get('parent', {})or {}).get('key'),
                      'parent_summary':((fields.get('parent', {})or {}).get('fields')or {}).get('summary'),
                    
          
                      'labels': ' , '.join(fields.get('labels', [])),
                      'epic_name': ((fields.get('parent', {})or {}).get('fields')or {}).get('summary'),
                      'startdate':  fields.get('startdate', None) , 
                      'due_date': fields.get('duedate', None) , 
                      'original_estimate_minutes':  fields.get('timeoriginalestimate', None),
                      
                      }
        
        val = value_dict.get('original_estimate_minutes')
        value_dict['original_estimate_minutes'] = val / 60 if val is not None else None
        
        issues_data.append(value_dict)
    return issues_data


# if __name__ == "__main__":
    
    
load_time = pd.Timestamp.now().floor("s")
issues_from_instance = fetch_issues_for_instance(JIRA_INSTANCES)
df_timetracking = get_timetracking_data_by_person_date_project_and_source(issues_from_instance)
df_timetracking = df_timetracking.drop("source_url", axis = 1)
df_timetracking['load_time'] = load_time
issues_data = get_issue_data(issues_from_instance)
issues_data = pd.DataFrame(issues_data)
issues_data['load_time'] = load_time



import urllib.parse
import sqlalchemy as sa
import pandas as pd

driver   = os.environ.get("SQL_DRIVER")
server   = os.environ.get("SQL_SERVER")
database = os.environ.get("SQL_DATABASE")

odbc_str = (
    f"DRIVER={{{driver}}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    "Trusted_Connection=Yes;"   # Windows auth
    "TrustServerCertificate=Yes;"  # drop this if you have proper TLS certs
)

params = urllib.parse.quote_plus(odbc_str)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}", echo=False)

from sqlalchemy.dialects.mssql import NVARCHAR, FLOAT, DATETIME2
from sqlalchemy import Text

dtype_mapping = {
    "date": NVARCHAR(50),
    "employee": Text,   # instead of NVARCHAR(MAX)
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
    dtype=dtype_mapping
)

from sqlalchemy.dialects.mssql import NVARCHAR, FLOAT, DATETIME2
from sqlalchemy import Text

dtype_mapping = {
    "project": NVARCHAR(1000),
    "creator": NVARCHAR(1000),
    "assignee": NVARCHAR(1000),
    "reporter": NVARCHAR(1000),
    "work_description": NVARCHAR(1000),
    "issue_summary": NVARCHAR(1000),
    "issue_key": NVARCHAR(1000),
    "issue_type": NVARCHAR(1000),
    "issue_status": NVARCHAR(1000),
    "issue_priority": NVARCHAR(1000),
    "billable_type": NVARCHAR(1000),
    "parent_key": NVARCHAR(1000),
    "parent_summary": NVARCHAR(1000),
    "labels": NVARCHAR(1000),
    "epic_name": NVARCHAR(1000),
    "startdate": NVARCHAR(50),
    "due_date": NVARCHAR(50),
    "original_estimate_minutes": FLOAT,
    "load_time": DATETIME2
}

issues_data.to_sql(
    "JiraIssuesData",
    con=engine,
    schema="dbo",
    if_exists="replace",
    index=False,
    dtype=dtype_mapping
)
