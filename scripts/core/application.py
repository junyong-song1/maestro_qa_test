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
        self.logger = get_logger("QAApplication")
        self.device_manager = DeviceManager()
        self.testrail_manager = TestRailManager(self.config.testrail)
        self.test_runner = MaestroTestRunner(self.config)
    
    def run(self):
        """메인 애플리케이션 실행"""
        try:
            self.logger.info("QA 자동화 테스트 시작")
            
            # 1. 디바이스 발견
            devices = self.device_manager.discover_devices()
            if not devices:
                self.logger.error("연결된 디바이스가 없습니다.")
                return
            
            self.logger.info(f"{len(devices)}개 디바이스 발견")
            
            # 2. TestRail 런 생성
            suite_id = self.config.get_testrail('suite_id', '1787')
            test_run = self.testrail_manager.create_test_run(suite_id)
            self.logger.info(f"TestRail 런 생성: {test_run.id}")
            
            # 3. 테스트 케이스 조회
            test_cases = self.testrail_manager.get_cases_by_suite(suite_id)
            self.logger.info(f"{len(test_cases)}개 테스트 케이스 조회")
            
            # 4. 테스트 실행
            results = self.test_runner.run_tests(test_cases, devices)
            
            # 5. 결과 업로드
            self._upload_results(test_run.id, results)
            
            self.logger.info("QA 자동화 테스트 완료")
            
        except Exception as e:
            self.logger.error(f"테스트 실행 중 오류 발생: {e}")
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