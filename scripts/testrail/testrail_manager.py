from typing import List, Dict, Any, Optional, Union
import requests
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from . import testrail
import logging

# 로거 가져오기
logger = logging.getLogger('dashboard.monitor')

@dataclass
class TestCase:
    id: str
    title: str
    description: str

@dataclass
class TestRun:
    id: str
    name: str
    suite_id: str

class TestRailManager:
    def __init__(self, config):
        """
        TestRail API 매니저 초기화
        
        Args:
            config (ConfigManager): 설정 매니저 인스턴스
        """
        try:
            testrail_config = config.get_testrail_config()
            self.url = testrail_config['url'].rstrip('/')
            self.username = testrail_config['username']
            self.api_key = testrail_config['api_key']
            self.project_id = testrail_config['project_id']
            
            if not all([self.url, self.username, self.api_key, self.project_id]):
                raise ValueError("TestRail 설정이 올바르지 않습니다. config.ini 파일을 확인해주세요.")
            
            logger.info(f"TestRail API 초기화 완료 (URL: {self.url}, Project ID: {self.project_id})")
        except Exception as e:
            logger.error(f"TestRail API 초기화 실패: {str(e)}")
            raise

    def _make_request(self, method, endpoint, data=None, files=None):
        """
        TestRail API 요청을 보내는 헬퍼 메서드
        """
        url = f"{self.url}/index.php?/api/v2/{endpoint}"
        try:
            if method.lower() == 'get':
                response = requests.get(url, auth=(self.username, self.api_key))
            elif method.lower() == 'post':
                response = requests.post(url, json=data, files=files, auth=(self.username, self.api_key))
            
            if response.status_code != 200:
                logger.error(f"TestRail API error: {response.status_code} - {response.text}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return None

    def get_test_runs(self, project_id=None):
        """
        프로젝트의 테스트 실행 목록을 가져옵니다.
        """
        if project_id is None:
            project_id = self.project_id
            
        return self._make_request('get', f'get_runs/{project_id}')

    def get_test_run(self, run_id):
        """
        특정 테스트 실행의 상세 정보를 가져옵니다.
        """
        try:
            # 테스트 실행 정보 가져오기
            test_run = self._make_request('get', f'get_run/{run_id}')
            if not test_run:
                return None
                
            # 테스트 케이스 결과 가져오기
            test_cases = self._make_request('get', f'get_tests/{run_id}')
            if test_cases:
                test_run['test_cases'] = test_cases
            else:
                test_run['test_cases'] = []
            
            return test_run
            
        except Exception as e:
            logger.error(f"Error getting test run {run_id}: {str(e)}")
            return None

    def add_result_for_case(self, run_id, case_id, status, comment):
        """
        테스트 케이스에 결과를 추가합니다.
        """
        data = {
            "status_id": status,
            "comment": comment
        }
        return self._make_request('post', f'add_result_for_case/{run_id}/{case_id}', data=data)

    def add_attachment_to_result(self, result_id, filepath):
        """
        테스트 결과에 첨부파일을 추가합니다.
        """
        try:
            with open(filepath, 'rb') as f:
                files = {'attachment': f}
                return self._make_request('post', f'add_attachment_to_result/{result_id}', files=files)
        except Exception as e:
            logger.error(f"Error adding attachment: {str(e)}")
            return None

    def create_test_run(self, suite_id: str, name: str = None) -> TestRun:
        """새 테스트 런 생성"""
        endpoint = f"{self.url}/index.php?/api/v2/add_run/{self.project_id}"
        
        if not name:
            name = f"Automated Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        data = {
            'suite_id': int(suite_id),
            'name': name,
            'include_all': True
        }
        
        response = requests.post(endpoint, json=data, auth=(self.username, self.api_key))
        response.raise_for_status()
        
        run_data = response.json()
        return TestRun(run_data['id'], name, suite_id)
    
    def get_cases_by_suite(self, suite_id: str) -> List[TestCase]:
        """스위트의 테스트 케이스 목록 조회"""
        endpoint = f"{self.url}/index.php?/api/v2/get_cases/{self.project_id}&suite_id={suite_id}"
        
        response = requests.get(endpoint, auth=(self.username, self.api_key))
        response.raise_for_status()
        
        cases_data = response.json()
        if isinstance(cases_data, dict) and 'cases' in cases_data:
            cases_data = cases_data['cases']
        
        return [TestCase(str(c['id']), c.get('title', ''), c.get('custom_description', '')) 
                for c in cases_data]
    
    def add_result(self, run_id: str, case_id: str, status: str, comment: str) -> Optional[str]:
        """테스트 결과 추가"""
        endpoint = f"{self.url}/index.php?/api/v2/add_result_for_case/{run_id}/{case_id}"
        
        status_map = {'성공': 1, 'pass': 1, 'OK': 1, '실패': 5, 'fail': 5, 'FAIL': 5}
        status_id = status_map.get(status, 5)
        
        data = {"status_id": status_id, "comment": comment}
        
        try:
            response = requests.post(endpoint, json=data, auth=(self.username, self.api_key))
            response.raise_for_status()
            return response.json().get('id')
        except Exception as e:
            print(f"TestRail 결과 업로드 실패: {e}")
            return None
    
    def add_attachment(self, result_id: str, filepath: str) -> bool:
        """첨부파일 업로드"""
        endpoint = f"{self.url}/index.php?/api/v2/add_attachment_to_result/{result_id}"
        
        try:
            with open(filepath, 'rb') as f:
                files = {'attachment': f}
                response = requests.post(endpoint, files=files, auth=(self.username, self.api_key))
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"첨부파일 업로드 실패: {filepath} - {e}")
            return False
    
    def get_all_suites(self) -> List[Dict[str, Any]]:
        """모든 스위트 조회"""
        endpoint = f"{self.url}/index.php?/api/v2/get_suites/{self.project_id}"
        
        response = requests.get(endpoint, auth=(self.username, self.api_key))
        response.raise_for_status()
        
        suites_data = response.json()
        if isinstance(suites_data, dict) and 'suites' in suites_data:
            return suites_data['suites']
        return suites_data

    def get_projects(self) -> List[Dict[str, Any]]:
        """모든 프로젝트 조회"""
        endpoint = f"{self.url}/index.php?/api/v2/get_projects"
        
        response = requests.get(endpoint, auth=(self.username, self.api_key))
        response.raise_for_status()
        
        return response.json()

    def get_suites(self, project_id: str) -> List[Dict]:
        """프로젝트의 테스트 스위트 목록을 가져옵니다."""
        response = self._make_request('GET', f'get_suites/{project_id}')
        return response if isinstance(response, list) else []

    def get_cases(self, project_id: str, suite_id: str) -> List[Dict[str, Any]]:
        """스위트의 모든 테스트 케이스 조회"""
        endpoint = f"{self.url}/index.php?/api/v2/get_cases/{project_id}&suite_id={suite_id}"
        
        response = requests.get(endpoint, auth=(self.username, self.api_key))
        response.raise_for_status()
        
        cases_data = response.json()
        if isinstance(cases_data, dict) and 'cases' in cases_data:
            return cases_data['cases']
        return cases_data

    def get_project(self, project_id: str) -> Optional[Dict]:
        """프로젝트 정보를 가져옵니다."""
        return self._make_request('GET', f'get_project/{project_id}')

    def get_test_suite(self, suite_id):
        """테스트 스위트 정보를 가져옵니다."""
        try:
            return self._make_request('GET', f'suites/{suite_id}')
        except Exception as e:
            print(f"Error getting test suite: {e}")
            return {}

    def get_results_for_run(self, run_id: str) -> Optional[Dict]:
        """특정 테스트 실행의 결과를 가져옵니다."""
        return self._make_request('GET', f'get_results_for_run/{run_id}')

    def get_test_cases(self, project_id: str, suite_id: str) -> List[Dict]:
        """특정 스위트의 테스트 케이스 목록을 가져옵니다."""
        response = self._make_request('GET', f'get_cases/{project_id}&suite_id={suite_id}')
        if not response or not isinstance(response, dict):
            return []
        return response.get('cases', [])

    def update_test_result(self, run_id, case_id, status_id, comment=None):
        """테스트 결과를 업데이트합니다."""
        try:
            data = {
                'status_id': status_id,
                'comment': comment or ''
            }
            return self._make_request('POST', f'add_result_for_case/{run_id}/{case_id}', data=data)
        except Exception as e:
            print(f"Error updating test result: {e}")
            return None

    def get_test_cases_for_run(self, run_id):
        """
        테스트 실행에 포함된 테스트 케이스 목록을 가져옵니다.
        
        Args:
            run_id (int): 테스트 실행 ID
            
        Returns:
            list: 테스트 케이스 목록
        """
        try:
            test_cases = self._make_request('get', f'get_tests/{run_id}')
            if not test_cases:
                return []
            elif isinstance(test_cases, dict):
                return [test_cases]
            elif isinstance(test_cases, list):
                return test_cases
            else:
                return []
        except Exception as e:
            logger.error(f"테스트 케이스 정보를 가져오는 중 오류 발생: {str(e)}")
            return []

    def get_tests(self, run_id):
        """
        테스트 실행에 포함된 테스트 목록을 가져옵니다.
        
        Args:
            run_id (int): 테스트 실행 ID
            
        Returns:
            list: 테스트 목록
        """
        try:
            tests = self._make_request('get', f'get_tests/{run_id}')
            if not tests:
                return []
            elif isinstance(tests, dict):
                return [tests]
            elif isinstance(tests, list):
                return tests
            else:
                return []
        except Exception as e:
            logger.error(f"테스트 목록을 가져오는 중 오류 발생: {str(e)}")
            return []

    def get_results_for_test(self, test_id: str) -> Optional[List[Dict[str, Any]]]:
        """특정 테스트(test_id)의 모든 실행 이력(모든 result)을 가져옵니다."""
        results = self._make_request('GET', f'get_results/{test_id}')
        if not results:
            return []
        if isinstance(results, dict):
            return [results]
        return results

    def get_results_for_case(self, run_id: str, case_id: str) -> Optional[List[Dict[str, Any]]]:
        """특정 테스트런(run_id)에서 특정 케이스(case_id)의 모든 실행 이력(모든 result)을 가져옵니다."""
        results = self._make_request('GET', f'get_results_for_case/{run_id}/{case_id}')
        if not results:
            return []
        if isinstance(results, dict):
            return [results]
        return results 