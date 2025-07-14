from typing import List
from pathlib import Path
import datetime

from ..config.config_manager import ConfigManager
from ..device.device_manager import DeviceManager
from ..testrail import testrail
from ..utils.logger import get_logger
from .test_runner import MaestroTestRunner, TestResult
from ..utils.logcat_utils import save_logcat, extract_api_log_for_case  # logcat 저장 유틸리티 import

class QAApplication:
    def __init__(self):
        self.config = ConfigManager()
        self.testrail_config = {
            'url': self.config['TestRail']['url'],
            'username': self.config['TestRail']['username'],
            'api_key': self.config['TestRail']['api_key'],
            'project_id': self.config['TestRail']['project_id']
        }
        self.device_manager = DeviceManager()
        self.test_runner = MaestroTestRunner(self.config)
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
            suite_id = self.config.get('TestRail', 'suite_id', '1798')
            test_cases = testrail.get_cases_by_suite(self.testrail_config, suite_id)
            if not isinstance(test_cases, list):
                test_cases = []
            
            if not test_cases:
                self.logger.error("테스트 케이스를 찾을 수 없습니다.")
                return
            
            self.logger.info(f"{len(test_cases)}개 테스트 케이스 조회")
            
            # 각 테스트케이스의 key와 Automation Type 로그 출력
            for case in test_cases:
                self.logger.info(f"TestCase keys: {list(case.keys())}, AutomationType: {case.get('custom_automation_type')}")
            
            # Automation Type이 2(Maestro)인 케이스만 필터링
            maestro_cases = [case for case in test_cases if case.get('custom_automation_type') == 2]
            self.logger.info(f"Automation Type=2(Maestro) 케이스만 실행: {len(maestro_cases)}개")

            # 타임스탬프 생성 (테스트 실행 시작 시각)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            serial = devices[0].serial  # 예시: 첫 번째 디바이스 사용, 멀티 디바이스면 반복문 등으로 처리
            log_path = f"artifacts/result/{serial}/{timestamp}/api_log.mitm"

            # 1. mitmproxy 실행
            start_mitmproxy(log_path, port=8080)

            try:
                # 테스트 실행
                results = self.test_runner.run_tests(maestro_cases, devices)
                self.logger.info(f"테스트 완료: {len(results)}개 결과")
            finally:
                # 2. mitmproxy 종료 (예외 발생 시에도 안전하게)
                stop_mitmproxy()

            # 3. 로그 분석 (에러 API만 추출)
            errors = extract_api_errors_from_mitmflow(log_path)

            # 4. 테스트 실행 후 logcat 저장 및 TestRail 업로드
            for result in results:
                save_logcat(result.serial, result.case_id, timestamp)
                # mitmproxy.log가 있으면 케이스별로 복사
                mitmproxy_log_path = "mitmproxy.log"
                import os
                if os.path.exists(mitmproxy_log_path):
                    extract_api_log_for_case(mitmproxy_log_path, result.serial, result.case_id, timestamp)
                # API 상태 체크 자동화 (예시)
                self.check_api_status(result.serial, result.case_id, timestamp)
                # TestRail 업로드 (API 오류 코멘트 포함)
                comment = "API 오류 발생:\n" + "\n".join(errors) if errors else "API 오류 없음"
                run_id = getattr(self, 'current_run_id', None) or self.config.get('TestRail', 'run_id', None)
                if run_id:
                    result_id = testrail.add_result_for_case(self.testrail_config, run_id, result.case_id, 5 if errors else 1, comment)
                    if errors and result_id:
                        testrail.add_attachment_to_result(self.testrail_config, result_id, log_path)
            
        except Exception as e:
            self.logger.error(f"테스트 실행 중 오류 발생: {str(e)}")
            raise
    
    def _upload_results(self, run_id: str, results: List[TestResult]):
        """테스트 결과를 TestRail에 업로드"""
        for result in results:
            comment = self._format_result_comment(result)
            result_id = testrail.add_result_for_case(self.testrail_config, run_id, result.case_id, result.status, comment)
            
            if result_id:
                # 첨부파일 업로드
                for attachment in result.attachments:
                    if Path(attachment).exists():
                        testrail.add_attachment_to_result(self.testrail_config, result_id, attachment)
    
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

    def check_api_status(self, serial, case_id, timestamp, base_dir="artifacts/result"):
        """
        API 상태(정상/실패/지연 등) 자동 분석 예시 함수
        - mitmproxy 로그, 네트워크 캡처, requests 결과 등 활용 가능
        - 실제 환경에 맞게 구현 필요
        """
        import os
        api_log_path = os.path.join(base_dir, serial, timestamp, f"api_TC{case_id}.txt")
        # 예시: mitmproxy 로그 파일이 있다면 분석
        if os.path.exists(api_log_path):
            with open(api_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # 간단 예시: HTTP 4xx/5xx, timeout, error 등 키워드 탐지
            keywords = [" 40", " 50", "timeout", "error", "fail", "502", "504", "connection refused"]
            found = [line for line in lines if any(k in line for k in keywords)]
            if found:
                result_path = os.path.join(base_dir, serial, timestamp, f"api_TC{case_id}_errors.txt")
                with open(result_path, "w", encoding="utf-8") as f:
                    f.writelines(found)
                print(f"[API] 오류/이상 감지: {result_path}")
        else:
            # mitmproxy 등 네트워크 프록시 로그가 없는 경우, 향후 확장 가능
            pass 