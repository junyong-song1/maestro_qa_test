from typing import List
from pathlib import Path

from ..config.config_manager import ConfigManager
from ..device.device_manager import DeviceManager
from ..testrail.testrail_manager import TestRailManager
from ..utils.logger import get_logger
from .test_runner import MaestroTestRunner, TestResult

class QAApplication:
    def __init__(self):
        self.config = ConfigManager()
        # api_key 사용 (password가 아님)
        testrail_config = {
            'url': self.config['TestRail']['url'],
            'username': self.config['TestRail']['username'],
            'api_key': self.config['TestRail']['api_key'],  # password → api_key로 수정
            'project_id': self.config['TestRail']['project_id']
        }
        self.testrail_manager = TestRailManager(testrail_config)
        self.device_manager = DeviceManager()
        # testrail_manager를 전달
        self.test_runner = MaestroTestRunner(self.config, self.testrail_manager)
        self.logger = get_logger("QAApplication")
    
    def run(self):
        """QA 애플리케이션 실행"""
        try:
            self.logger.info("QA 자동화 테스트 시작")
            
            # 디바이스 발견
            devices = self.device_manager.discover_devices()
            if not devices:
                self.logger.error("연결된 디바이스가 없습니다.")
                return
            
            self.logger.info(f"{len(devices)}개 디바이스 발견")
            
            # TestRail에서 테스트 케이스 가져오기
            # get_testrail 대신 get 사용
            suite_id = self.config.get('TestRail', 'suite_id', '1798')
            test_cases = self.testrail_manager.get_cases_by_suite(suite_id)
            
            if not test_cases:
                self.logger.error("테스트 케이스를 찾을 수 없습니다.")
                return
            
            self.logger.info(f"{len(test_cases)}개 테스트 케이스 조회")
            
            # 테스트 실행
            results = self.test_runner.run_tests(test_cases, devices)
            
            self.logger.info(f"테스트 완료: {len(results)}개 결과")
            
        except Exception as e:
            self.logger.error(f"테스트 실행 중 오류 발생: {str(e)}")
            raise
    
    def _upload_results(self, run_id: str, results: List[TestResult]):
        """테스트 결과를 TestRail에 업로드"""
        for result in results:
            comment = self._format_result_comment(result)
            result_id = self.testrail_manager.add_result(
                run_id, result.case_id, result.status, comment
            )
            
            if result_id:
                # 첨부파일 업로드
                for attachment in result.attachments:
                    if Path(attachment).exists():
                        self.testrail_manager.add_attachment(result_id, attachment)
    
    def _format_result_comment(self, result: TestResult) -> str:
        """결과 코멘트 포맷팅"""
        return f"""
디바이스 정보:
- 모델: {result.model}
- 안드로이드: {result.os_version}
- TVING 버전: {result.tving_version}

실행 결과: {result.status}
실행 시간: {result.elapsed}

로그 파일: {result.log_path}
""" 