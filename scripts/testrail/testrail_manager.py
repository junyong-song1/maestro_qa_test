from typing import List, Dict, Any, Optional
import requests
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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
    def __init__(self, config: Dict[str, str]):
        self.config = config
        self.base_url = config['url'].rstrip('/')
        self.auth = (config['username'], config['api_key'])
        self.project_id = config['project_id']
    
    def create_test_run(self, suite_id: str, name: str = None) -> TestRun:
        """새 테스트 런 생성"""
        endpoint = f"{self.base_url}/index.php?/api/v2/add_run/{self.project_id}"
        
        if not name:
            name = f"Automated Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        data = {
            'suite_id': int(suite_id),
            'name': name,
            'include_all': True
        }
        
        response = requests.post(endpoint, json=data, auth=self.auth)
        response.raise_for_status()
        
        run_data = response.json()
        return TestRun(run_data['id'], name, suite_id)
    
    def get_cases_by_suite(self, suite_id: str) -> List[TestCase]:
        """스위트의 테스트 케이스 목록 조회"""
        endpoint = f"{self.base_url}/index.php?/api/v2/get_cases/{self.project_id}&suite_id={suite_id}"
        
        response = requests.get(endpoint, auth=self.auth)
        response.raise_for_status()
        
        cases_data = response.json()
        if isinstance(cases_data, dict) and 'cases' in cases_data:
            cases_data = cases_data['cases']
        
        return [TestCase(str(c['id']), c.get('title', ''), c.get('custom_description', '')) 
                for c in cases_data]
    
    def add_result(self, run_id: str, case_id: str, status: str, comment: str) -> Optional[str]:
        """테스트 결과 추가"""
        endpoint = f"{self.base_url}/index.php?/api/v2/add_result_for_case/{run_id}/{case_id}"
        
        status_map = {'성공': 1, 'pass': 1, 'OK': 1, '실패': 5, 'fail': 5, 'FAIL': 5}
        status_id = status_map.get(status, 5)
        
        data = {"status_id": status_id, "comment": comment}
        
        try:
            response = requests.post(endpoint, json=data, auth=self.auth)
            response.raise_for_status()
            return response.json().get('id')
        except Exception as e:
            print(f"TestRail 결과 업로드 실패: {e}")
            return None
    
    def add_attachment(self, result_id: str, filepath: str) -> bool:
        """첨부파일 업로드"""
        endpoint = f"{self.base_url}/index.php?/api/v2/add_attachment_to_result/{result_id}"
        
        try:
            with open(filepath, 'rb') as f:
                files = {'attachment': f}
                response = requests.post(endpoint, files=files, auth=self.auth)
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"첨부파일 업로드 실패: {filepath} - {e}")
            return False
    
    def get_all_suites(self) -> List[Dict[str, Any]]:
        """모든 스위트 조회"""
        endpoint = f"{self.base_url}/index.php?/api/v2/get_suites/{self.project_id}"
        
        response = requests.get(endpoint, auth=self.auth)
        response.raise_for_status()
        
        suites_data = response.json()
        if isinstance(suites_data, dict) and 'suites' in suites_data:
            return suites_data['suites']
        return suites_data 