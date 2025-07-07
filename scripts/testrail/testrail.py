import requests
from typing import List, Dict, Optional
import sys

class TestRailAPI:
    def __init__(self, url: str, email: str, password: str):
        self.url = url.rstrip('/')
        self.auth = (email, password)
        self.headers = {'Content-Type': 'application/json'}

    def _send_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        api_url = f"{self.url}/index.php?/api/v2/{endpoint}"
        try:
            response = requests.request(method, api_url, headers=self.headers, auth=self.auth, **kwargs)
            response.raise_for_status()
            # GET 요청에 대한 응답이 비어있을 수 있음 (e.g. 204 No Content)
            if response.status_code == 204:
                return {}
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API Error: {e}", file=sys.stderr)
            return None
        except ValueError: # JSON 디코딩 에러
            print(f"API Error: Invalid JSON response from {api_url}", file=sys.stderr)
            return None

    def get_case(self, case_id: int) -> Optional[Dict]:
        """특정 테스트 케이스의 상세 정보를 가져옵니다."""
        return self._send_request('GET', f'get_case/{case_id}')

    def get_cases(self, project_id: int, suite_id: int) -> Optional[List[Dict]]:
        """
        특정 스위트의 모든 테스트 케이스 목록을 가져옵니다.
        TestRail의 기본 케이스 템플릿(steps 포함)을 명시적으로 요청합니다.
        """
        endpoint = f'get_cases/{project_id}&suite_id={suite_id}'
        response = self._send_request('GET', endpoint)
        return response.get('cases', []) if response else None

class TestRailManager:
    """TestRail API를 편리하게 사용하기 위한 관리자 클래스"""
    def __init__(self, config: dict):
        self.client = TestRailAPI(
            url=config['url'],
            email=config['username'],
            password=config['api_key']
        )
        self.project_id = int(config['project_id'])

    def get_case(self, case_id: int) -> Optional[Dict]:
        """ID로 단일 테스트 케이스의 상세 정보를 가져옵니다."""
        return self.client.get_case(case_id)

    def get_test_cases(self, project_id: int, suite_id: int) -> Optional[List[Dict]]:
        """특정 프로젝트와 스위트의 모든 테스트 케이스 목록을 가져옵니다."""
        cases = self.client.get_cases(project_id, suite_id)
        if cases is None:
            print("테스트 케이스를 가져오는데 실패했습니다. API 응답을 확인하세요.", file=sys.stderr)
            return None
        return cases

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

def add_run(config, suite_id, name=None, description=None):
    """
    TestRail에 테스트 런을 생성하고 run_id를 반환합니다.
    """
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/add_run/{project_id}"
    data = {"suite_id": suite_id}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    resp = requests.post(endpoint, json=data, auth=(username, api_key))
    if resp.status_code != 200:
        print(f"[ERROR] add_run {resp.status_code}: {resp.text}", file=sys.stderr)
        return None
    return resp.json().get('id') 