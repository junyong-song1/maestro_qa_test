import requests
import sys

def get_all_suites(config):
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/get_suites/{project_id}"
    resp = requests.get(endpoint, auth=(username, api_key))
    if resp.status_code != 200:
        print(f"[ERROR] {resp.status_code}: {resp.text}", file=sys.stderr)
        return []
    suites = resp.json()
    if isinstance(suites, dict) and 'suites' in suites:
        suites = suites['suites']
    return suites

def get_project_name(config):
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/get_project/{project_id}"
    resp = requests.get(endpoint, auth=(username, api_key))
    if resp.status_code != 200:
        print(f"[ERROR] {resp.status_code}: {resp.text}", file=sys.stderr)
        return f"project_{project_id}"
    project = resp.json()
    return project.get('name', f"project_{project_id}")

def get_cases_by_suite(config, suite_id):
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/get_cases/{project_id}&suite_id={suite_id}"
    resp = requests.get(endpoint, auth=(username, api_key))
    if resp.status_code != 200:
        print(f"[ERROR] {resp.status_code}: {resp.text}", file=sys.stderr)
        return []
    cases = resp.json()
    if isinstance(cases, dict) and 'cases' in cases:
        return cases['cases']
    return cases

def get_suite_id_from_project(config):
    suites = get_all_suites(config)
    if suites:
        return suites[0]['id']
    return None

def get_testrail_cases(config, suite_id=None):
    if not suite_id:
        suite_id = get_suite_id_from_project(config)
        if not suite_id:
            print("[ERROR] suite_id를 찾을 수 없습니다.", file=sys.stderr)
            return []
    return get_cases_by_suite(config, suite_id)

def add_result_for_case(config, run_id, case_id, status, comment):
    url = config['url'].rstrip('/')
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/add_result_for_case/{run_id}/{case_id}"
    data = {"status_id": status, "comment": comment}
    resp = requests.post(endpoint, json=data, auth=(username, api_key))
    if resp.status_code != 200:
        print(f"[ERROR] {resp.status_code}: {resp.text}", file=sys.stderr)
        return None
    return resp.json().get('id')

def add_attachment_to_result(config, result_id, filepath):
    url = config['url'].rstrip('/')
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/add_attachment_to_result/{result_id}"
    with open(filepath, 'rb') as f:
        files = {'attachment': f}
        resp = requests.post(endpoint, files=files, auth=(username, api_key))
    if resp.status_code != 200:
        print(f"[ERROR] 첨부 실패: {resp.status_code}: {resp.text}", file=sys.stderr)
        return False
    return True 