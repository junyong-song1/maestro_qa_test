from testrail_api import TestRailAPI

def get_api(config):
    return TestRailAPI(
        config['url'],
        config['username'],
        config['api_key']
    )

def get_cases(config, run_id):
    api = get_api(config)
    resp = api.tests.get_tests(run_id)
    return resp['tests']

def get_cases_by_suite(config, suite_id):
    import requests
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/get_cases/{project_id}&suite_id={suite_id}"
    resp = requests.get(endpoint, auth=(username, api_key))
    resp.raise_for_status()
    cases = resp.json()
    if isinstance(cases, dict) and 'cases' in cases:
        return cases['cases']
    return cases

def add_result(config, run_id, case_id, status, comment):
    api = get_api(config)
    status_map = {'성공': 1, 'pass': 1, 'OK': 1, '실패': 5, 'fail': 5, 'FAIL': 5}
    status_id = status_map.get(status, 5)
    data = {'status_id': status_id, 'comment': comment}
    try:
        resp = api.results.add_result_for_case(run_id, case_id, **data)
        return resp['id']
    except Exception as e:
        print(f"TestRail 결과 보고 실패: {e}")
        return None

def add_attachment(config, result_id, filepath):
    api = get_api(config)
    try:
        api.attachments.add_attachment_to_result(result_id, filepath)
        print(f"[첨부 성공] {filepath}")
        return True
    except Exception as e:
        print(f"[첨부 실패] {filepath}: {e}")
        return False 