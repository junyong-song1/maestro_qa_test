from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
import glob
import os
import logging
import sys
from datetime import datetime

from ..device.device_manager import DeviceInfo
from ..utils.logger import get_logger
from ..utils.log_manager import log_manager
from ..testrail import testrail
from scripts.utils.testlog_db import log_step, init_db
from ..utils.slack_notifier import slack_notifier

# 로거 설정 (testrail_maestro_runner.py와 동일한 방식)
logger = logging.getLogger("TestRunner")
logger.setLevel(logging.INFO)

# 기존 핸들러 제거 (중복 방지)
if logger.hasHandlers():
    logger.handlers.clear()

# 콘솔 핸들러
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# 파일 핸들러
file_handler = logging.FileHandler("testrail_maestro_runner.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(console_formatter)
logger.addHandler(file_handler)

@dataclass
class TestFlow:
    """Maestro 테스트 플로우 파일 정보를 담는 데이터 클래스"""
    path: Path
    metadata: Dict[str, Any]
    content: str

@dataclass
class TestResult:
    case_id: str
    title: str
    status: str
    serial: str
    model: str
    os_version: str
    tving_version: str
    log_path: str
    attachments: List[str]
    error_log: str
    elapsed: str

class TestRunner(ABC):
    def __init__(self, config_manager):
        self.config = config_manager
        self.devices: List[DeviceInfo] = []
        self.results: List[TestResult] = []
        self.logger = get_logger("TestRunner")
    
    @abstractmethod
    def run_tests(self, test_cases: List[Any], devices: List[DeviceInfo]) -> List[TestResult]:
        pass
    
    @abstractmethod
    def collect_results(self) -> List[TestResult]:
        pass

class MaestroTestRunner(TestRunner):
    def __init__(self, config_manager, testrail_manager=None):
        super().__init__(config_manager)
        self.maestro_flows: List[TestFlow] = []  # 타입을 TestFlow 리스트로 변경
        self.current_run_id = None
        self.proxy_configured = False  # 프록시 설정 상태 추적
        
        # TestRail Manager 설정
        if testrail_manager:
            self.testrail_config = testrail_manager  # dict 형태로 전달 가능
        else:
            self.testrail_config = {
                'url': config_manager.get('TestRail', 'url'),
                'username': config_manager.get('TestRail', 'username'),
                'api_key': config_manager.get('TestRail', 'api_key'),
                'project_id': config_manager.get('TestRail', 'project_id')
            }
            
        # Maestro 플로우 탐색
        self._discover_maestro_flows()
        init_db()  # 최초 1회 DB 초기화
    
    def _setup_proxy_for_all_devices(self, devices: List[DeviceInfo]):
        """모든 디바이스에 프록시 설정 (테스트 런 시작 시 한 번만)"""
        if self.proxy_configured:
            logger.info("프록시가 이미 설정되어 있습니다.")
            return
            
        logger.info("=== 프록시 설정 시작 ===")
        proxy_start_time = time.time()
        
        # 현재 IP 주소 확인
        local_ip = self._get_local_ip()
        
        for device in devices:
            try:
                logger.info(f"[{device.serial}] 프록시 설정: {local_ip}:8080")
                device_proxy_start = time.time()
                
                # HTTP 프록시 설정 (더 호환성이 좋음)
                subprocess.run([
                    "adb", "-s", device.serial, "shell", "settings", "put", "global", "http_proxy", f"{local_ip}:8080"
                ], check=False, timeout=10)
                
                device_proxy_duration = time.time() - device_proxy_start
                logger.info(f"[{device.serial}] 프록시 설정 완료 (소요시간: {device_proxy_duration:.3f}초)")
                
            except Exception as e:
                logger.warning(f"[{device.serial}] 프록시 설정 실패: {e}")
        
        total_proxy_duration = time.time() - proxy_start_time
        logger.info(f"=== 프록시 설정 완료 (총 소요시간: {total_proxy_duration:.3f}초) ===")
        self.proxy_configured = True
    
    def _cleanup_proxy_for_all_devices(self, devices: List[DeviceInfo]):
        """모든 디바이스에서 프록시 해제"""
        if not self.proxy_configured:
            logger.info("프록시가 설정되지 않았습니다.")
            return
            
        logger.info("=== 프록시 해제 시작 ===")
        cleanup_start_time = time.time()
        
        for device in devices:
            try:
                logger.info(f"[{device.serial}] 프록시 해제 중...")
                device_cleanup_start = time.time()
                
                # HTTP 프록시 해제
                subprocess.run([
                    "adb", "-s", device.serial, "shell", "settings", "put", "global", "http_proxy", ":0"
                ], check=False, timeout=10)
                
                device_cleanup_duration = time.time() - device_cleanup_start
                logger.info(f"[{device.serial}] 프록시 해제 완료 (소요시간: {device_cleanup_duration:.3f}초)")
                
            except Exception as e:
                logger.warning(f"[{device.serial}] 프록시 해제 실패: {e}")
        
        total_cleanup_duration = time.time() - cleanup_start_time
        logger.info(f"=== 프록시 해제 완료 (총 소요시간: {total_cleanup_duration:.3f}초) ===")
        self.proxy_configured = False
    
    def _get_local_ip(self) -> str:
        """현재 IP 주소 확인"""
        try:
            # 방법 1: ifconfig 사용 (macOS/Linux)
            result = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # inet 주소 찾기 (127.0.0.1 제외)
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'inet ' in line and '127.0.0.1' not in line:
                        local_ip = line.split('inet ')[1].split(' ')[0]
                        return local_ip
        except:
            pass
        
        # 방법 2: socket 사용 (백업)
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return "127.0.0.1"  # 기본값
    
    def _discover_maestro_flows(self):
        """maestro_flows 폴더를 스캔하여 모든 테스트 플로우 정보를 로드 (frontmatter 없이 파일 경로만으로 등록)"""
        self.maestro_flows = []
        flow_dir = Path("maestro_flows/qa_flows")
        if not flow_dir.is_dir():
            self.logger.warning(f"'{flow_dir}' 디렉토리를 찾을 수 없습니다.")
            return

        for yaml_path in flow_dir.glob("**/*.yaml"):
            try:
                # frontmatter 없이 파일 경로만으로 TestFlow 추가
                self.maestro_flows.append(TestFlow(
                    path=yaml_path,
                    metadata={},  # 메타데이터는 비워둠
                    content=""    # content도 비워둠(필요시 파일 내용 읽기)
                ))
            except Exception as e:
                self.logger.error(f"{yaml_path} 파일을 파싱하는 중 오류 발생: {e}")

        self.logger.info(f"{len(self.maestro_flows)}개의 유효한 Maestro 플로우를 찾았습니다.")

    def run_tests(self, test_cases: List[Any], devices: List[DeviceInfo]) -> List[TestResult]:
        """Maestro 테스트 실행 - 플로우별 즉시 업로드"""
        self.devices = devices
        self.results = []
        
        try:
            # TestRail에 테스트런 생성
            suite_id = self.config.get('TestRail', 'suite_id', '1798')
            run_name = f"자동화 테스트 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            self.current_run_id = testrail.add_run(self.testrail_config, suite_id, name=run_name)
            logger.info(f"테스트 런 생성 완료 (Run ID: {self.current_run_id})")
            
            # 프록시 설정 (테스트 런 시작 시 한 번만)
            self._setup_proxy_for_all_devices(devices)
            
            # Slack 테스트 시작 알림
            slack_notifier.send_test_start_notification(
                run_name, len(devices), len(test_cases)
            )

            # suite_id가 1784일 때만 앱 시작 테스트 실행
            if str(suite_id) == '1784':
                app_results = self._run_app_start_test()
            
            # 2. 각 테스트 케이스 실행 및 즉시 업로드
            for test_case in test_cases:
                case_results = self._run_single_test(test_case)
                if case_results:
                    # 테스트 완료 확인 후 API 데이터 DB 저장 대기
                    logger.info(f"테스트 완료 확인 후 API 데이터 DB 저장 대기 중...")
                    
                    # 모든 테스트가 완료되었는지 확인
                    all_tests_completed = all(result.status in ["성공", "실패"] for result in case_results)
                    
                    # 실행 중인 테스트가 있는지 확인
                    running_tests = [result for result in case_results if result.status not in ["성공", "실패"]]
                    
                    # 프로세스 상태 확인 (추가)
                    maestro_running = False
                    try:
                        import subprocess
                        ps_result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
                        if ps_result.returncode == 0:
                            # 현재 테스트 케이스 ID로 Maestro 프로세스 확인
                            for result in case_results:
                                if f"TC{result.case_id}" in ps_result.stdout and "maestro" in ps_result.stdout:
                                    maestro_running = True
                                    logger.info(f"Maestro 프로세스 실행 중 감지: TC{result.case_id}")
                                    break
                    except Exception as e:
                        logger.warning(f"프로세스 상태 확인 중 오류: {e}")
                    
                    if running_tests or maestro_running:
                        logger.warning(f"실행 중인 테스트가 있습니다: {[r.case_id for r in running_tests]}")
                        if maestro_running:
                            logger.warning(f"Maestro 프로세스가 실행 중입니다. API 데이터 확인을 건너뜁니다.")
                        else:
                            logger.info(f"테스트 완료를 기다린 후 API 데이터를 확인합니다.")
                    
                    if all_tests_completed and not maestro_running:
                        # API 데이터 DB 저장 완료 확인 및 대기
                        logger.info(f"모든 테스트 완료 확인됨. API 데이터 DB 저장 대기 시작...")
                        max_wait = 10  # 최대 10초 대기
                        wait_count = 0
                        api_data_ready = False
                        
                        while wait_count < max_wait and not api_data_ready:
                            try:
                                import sqlite3
                                conn = sqlite3.connect("artifacts/test_log.db")
                                cursor = conn.cursor()
                                
                                # 모든 결과에 대해 API 데이터 확인
                                all_ready = True
                                for result in case_results:
                                    cursor.execute("""
                                        SELECT COUNT(*) FROM test_api 
                                        WHERE test_case_id = ? AND serial = ?
                                    """, (result.case_id, result.serial))
                                    count = cursor.fetchone()[0]
                                    if count == 0:
                                        all_ready = False
                                        logger.info(f"API 데이터 대기 중: TC{result.case_id} - {count}건")
                                        break
                                    else:
                                        logger.info(f"API 데이터 확인됨: TC{result.case_id} - {count}건")
                                
                                conn.close()
                                
                                if all_ready:
                                    api_data_ready = True
                                    logger.info(f"API 데이터 DB 저장 완료 확인됨")
                                else:
                                    wait_count += 1
                                    time.sleep(1)
                                    logger.info(f"API 데이터 DB 저장 대기 중... ({wait_count}/{max_wait})")
                                    
                            except Exception as e:
                                logger.warning(f"API 데이터 확인 중 오류: {e}")
                                wait_count += 1
                                time.sleep(1)
                        
                        if not api_data_ready:
                            logger.warning(f"API 데이터 DB 저장 완료 확인 실패 (타임아웃)")
                    else:
                        if maestro_running:
                            logger.warning(f"Maestro 프로세스가 실행 중입니다. API 데이터 확인을 건너뜁니다.")
                        else:
                            logger.warning(f"일부 테스트가 아직 실행 중입니다. API 데이터 확인을 건너뜁니다.")
                    
                    # TestRail 업로드 (API 데이터 포함)
                    self._upload_results_to_testrail(case_results, test_case['title'])
            
            # Slack 테스트 완료 알림
            results_summary = {}
            for result in self.results:
                status = result.status
                results_summary[status] = results_summary.get(status, 0) + 1
            
            slack_notifier.send_test_complete_notification(run_name, results_summary)
            
            # 프록시 해제 (테스트 완료 후)
            self._cleanup_proxy_for_all_devices(devices)
            
            return self.results
            
        except Exception as e:
            logger.error(f"테스트 실행 중 오류 발생: {str(e)}")
            raise
    
    def _run_app_start_test(self) -> List[TestResult]:
        """앱 시작 테스트 실행 - 결과 반환 (TestRail 업로드 제외)"""
        logger.info("앱 시작 테스트 실행 중...")
        
        app_start_yaml = self._find_app_start_yaml()
        if not app_start_yaml:
            logger.error("앱 시작 YAML 파일을 찾을 수 없습니다.")
            return []
        
        results = []
        for device in self.devices:
            result = self._run_maestro_test(app_start_yaml, device, "00000", "앱 시작")
            results.append(result)
            if result.status == "실패":
                logger.error(f"앱 시작 실패: {device.serial}")
                return results  # 실패해도 결과는 반환
        
        logger.info("앱 시작 테스트 완료 (TestRail 업로드 제외)")
        return results
    
    def _run_single_test(self, test_case) -> List[TestResult]:
        """단일 테스트 케이스 실행 - 결과 반환"""
        case_id = int(test_case['id'])
        title = test_case['title']
        
        logger.info(f"테스트 실행: {title} (ID: {case_id})")
        
        test_flow = self._find_maestro_flow(case_id)
        if not test_flow:
            logger.warning(f"YAML 파일 없음: TC{case_id}")
            return []
        
        results = []
        for device in self.devices:
            result = self._run_maestro_test(test_flow, device, str(case_id), title)
            results.append(result)
            self.results.append(result)
        
        return results
    
    def _run_maestro_test(self, test_flow: TestFlow, device: DeviceInfo, case_id: str, title: str) -> TestResult:
        # 성능 프로파일링 시작
        total_start_time = time.time()
        proxy_start_time = None
        proxy_end_time = None
        maestro_start_time = None
        maestro_end_time = None
        
        status = "success"
        error_msg = None
        mitmdump_proc = None
        api_dump_path = None
        screenshot_path = None
        logcat_path = None
        start_time = total_start_time  # 기존 코드 호환성
        try:
            # 로그 파일 경로 설정
            today = datetime.now().strftime('%Y%m%d')
            log_dir = Path(f"artifacts/logs/{device.serial}")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"maestro_TC{case_id}.log"
            logcat_path = log_dir / f"logcat_TC{case_id}.txt"  # 로그캣 파일 경로 추가

            # mitmdump 백그라운드 실행 (테스트케이스별) - 명시적 포트 설정
            api_dump_path = log_dir / f"api_TC{case_id}.dump"
            logger.info(f"[{device.serial}] API 캡처 시작: {api_dump_path}")
            mitmdump_proc = subprocess.Popen(
                ["mitmdump", "-p", "8080", "-w", str(api_dump_path), "--ssl-insecure"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2)  # 프록시 준비 대기 (SSL 인증서 처리 시간 고려)
            
            # 프록시는 이미 테스트 런 시작 시 설정됨 (성능 최적화)
            logger.info(f"[{device.serial}] 프록시 설정 완료됨 (테스트 런 시작 시 설정)")

            # Maestro 명령 실행 (YAML 파일 경로 직접 전달)
            cmd = ["maestro", f"--device={device.serial}", "test", str(test_flow.path)]
            logger.info(f"[{device.serial}] [테스트 실행] {' '.join(cmd)}")

            # Maestro 실행 성능 측정 시작
            maestro_start_time = time.time()
            
            # 실시간 API 캡처 모니터링 시작
            logger.info(f"[{device.serial}] 실시간 API 캡처 모니터링 시작")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding='utf-8')
            
            maestro_end_time = time.time()
            maestro_duration = maestro_end_time - maestro_start_time
            logger.info(f"[{device.serial}] Maestro 실행 완료 (소요시간: {maestro_duration:.3f}초)")

            # 상세 로그 출력 (testrail_maestro_runner.py와 동일)
            logger.info(f"[{device.serial}] stdout:\n{result.stdout}")
            logger.info(f"[{device.serial}] stderr:\n{result.stderr}")
            logger.info(f"[{device.serial}] returncode: {result.returncode}")

            # 로그 저장 (새로운 로그 매니저 사용)
            log_content = f"=== Maestro Test Execution Log ===\n"
            log_content += f"Test Case: {title} (ID: {case_id})\n"
            log_content += f"Device: {device.model} ({device.serial})\n"
            log_content += f"Command: {' '.join(cmd)}\n"
            log_content += f"Return Code: {result.returncode}\n"
            log_content += f"Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            log_content += f"\n=== STDOUT ===\n{result.stdout}\n"
            if result.stderr:
                log_content += f"\n=== STDERR ===\n{result.stderr}\n"
            
            # 새로운 로그 매니저로 저장
            log_path = log_manager.save_maestro_log(device.serial, case_id, log_content)

            # 성공 판정 기준 수정: returncode=0이면 성공, [Passed]는 추가 확인용
            output = (result.stdout or "") + (result.stderr or "")
            has_passed_message = "[Passed]" in output or "Flow Passed" in output

            if result.returncode == 0:
                status = "성공"
                if has_passed_message:
                    logger.info(f"[{device.serial}] 테스트 성공 판정 (returncode=0, [Passed] 감지)")
                else:
                    logger.info(f"[{device.serial}] 테스트 성공 판정 (returncode=0, [Passed] 없음 - 정상)")
            else:
                status = "실패"
                logger.error(f"[{device.serial}] 테스트 실패 판정 (returncode={result.returncode})")
                if has_passed_message:
                    logger.warning(f"[{device.serial}] returncode!=0이지만 [Passed]가 있어 경고 처리")

            # --- 오류 로그 상세 분석 ---
            error_log = ""
            if result.returncode != 0 or status == "실패":
                # Maestro 오류 분석
                maestro_errors = []
                if result.stderr:
                    maestro_errors.append(f"Maestro Error: {result.stderr}")
                
                # stdout에서 오류 패턴 찾기
                stdout_lines = result.stdout.split('\n') if result.stdout else []
                for line in stdout_lines:
                    if any(keyword in line.lower() for keyword in ['error', 'failed', 'exception', 'timeout', 'not found', 'element not visible']):
                        maestro_errors.append(f"Maestro Output Error: {line.strip()}")
                
                # 로그캣 수집 (실패 시에만)
                try:
                    logger.info(f"[{device.serial}] 실패 감지 - 로그캣 수집 시작")
                    logcat_result = subprocess.run([
                        "adb", "-s", device.serial, "logcat", "-d", "-v", "time"
                    ], capture_output=True, text=True, timeout=30, encoding='utf-8')
                    
                    if logcat_result.returncode == 0 and logcat_result.stdout:
                        # 로그캣 파일 저장 (새로운 로그 매니저 사용)
                        logcat_content = f"=== Device Logcat (Test Failed) ===\n"
                        logcat_content += f"Test Case: {title} (ID: {case_id})\n"
                        logcat_content += f"Device: {device.model} ({device.serial})\n"
                        logcat_content += f"Collection Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        logcat_content += f"\n{logcat_result.stdout}"
                        
                        logcat_path = log_manager.save_logcat(device.serial, case_id, logcat_content)
                        
                        # 로그캣에서 오류 패턴 찾기
                        logcat_lines = logcat_result.stdout.split('\n')
                        error_patterns = [
                            'fatal', 'error', 'exception', 'crash', 'anr', 'timeout',
                            'tving', 'maestro', 'ui test', 'element', 'not found'
                        ]
                        
                        for line in logcat_lines[-100:]:  # 최근 100줄만 분석
                            if any(pattern in line.lower() for pattern in error_patterns):
                                maestro_errors.append(f"Logcat Error: {line.strip()}")
                        
                        logger.info(f"[{device.serial}] 로그캣 수집 완료: {logcat_path}")
                    else:
                        logger.warning(f"[{device.serial}] 로그캣 수집 실패: returncode={logcat_result.returncode}")
                        
                except Exception as e:
                    logger.error(f"[{device.serial}] 로그캣 수집 중 오류: {e}")
                
                # 오류 로그 구성
                if maestro_errors:
                    error_log = "\n".join(maestro_errors[:10])  # 최대 10개 오류만 포함
                else:
                    error_log = f"테스트 실패 (returncode={result.returncode}) - 상세 오류 정보 없음"
                
                # Slack 실패 알림 전송
                device_info = f"{device.model} ({device.serial})"
                slack_notifier.send_test_failure_notification(
                    case_id, title, error_log, device_info
                )

            # --- 스크린샷 저장 (성공/실패 모두) ---
            screenshot_dir = Path(f"artifacts/images/{today}")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%H%M%S')
            screenshot_filename = f"TC{case_id}_{device.serial}_{status}_{timestamp}.png"
            screenshot_path = screenshot_dir / screenshot_filename
            
            # 스크린샷 저장 (2단계 방식: exec-out 우선, 실패 시 shell+pull)
            max_retries = 3
            screenshot_saved = False
            
            for attempt in range(max_retries):
                if screenshot_saved:
                    break
                    
                try:
                    # 방법 1: adb exec-out (더 빠름, 단일 명령)
                    logger.info(f"[{device.serial}] 스크린샷 저장 시도 {attempt + 1}/{max_retries} - exec-out 방식")
                    proc = subprocess.run([
                        "adb", "-s", device.serial, "exec-out", "screencap -p"
                    ], capture_output=True, timeout=20)
                    
                    if proc.returncode == 0 and proc.stdout:
                        # 바이너리 데이터를 파일로 저장
                        with open(screenshot_path, 'wb') as f:
                            f.write(proc.stdout)
                        
                        # 파일 유효성 검사
                        if screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                            logger.info(f"스크린샷 저장 성공 (exec-out): {screenshot_path}, 파일크기: {screenshot_path.stat().st_size} bytes")
                            screenshot_saved = True
                            break
                        else:
                            logger.warning(f"exec-out 스크린샷 파일 크기 부족: {screenshot_path.stat().st_size if screenshot_path.exists() else 0} bytes")
                    else:
                        logger.warning(f"adb exec-out screencap 실패: returncode={proc.returncode}")
                        
                except subprocess.TimeoutExpired as e:
                    logger.warning(f"exec-out 스크린샷 타임아웃 (시도 {attempt + 1}/{max_retries}): {e}")
                except Exception as e:
                    logger.warning(f"exec-out 스크린샷 오류 (시도 {attempt + 1}/{max_retries}): {e}")
                
                # 방법 2: shell + pull (exec-out 실패 시)
                if not screenshot_saved:
                    try:
                        logger.info(f"[{device.serial}] 스크린샷 저장 시도 {attempt + 1}/{max_retries} - shell+pull 방식")
                        # 1. 디바이스에 임시 파일로 저장
                        temp_path = f"/sdcard/screenshot_{timestamp}.png"
                        proc1 = subprocess.run([
                            "adb", "-s", device.serial, "shell", "screencap", "-p", temp_path
                        ], timeout=30)
                        
                        if proc1.returncode == 0:
                            # 2. 로컬로 파일 가져오기
                            proc2 = subprocess.run([
                                "adb", "-s", device.serial, "pull", temp_path, str(screenshot_path)
                            ], timeout=30)
                            
                            # 3. 임시 파일 삭제
                            subprocess.run([
                                "adb", "-s", device.serial, "shell", "rm", temp_path
                            ], timeout=10)
                            
                            # 파일 유효성 검사
                            if screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                                logger.info(f"스크린샷 저장 성공 (shell+pull): {screenshot_path}, 파일크기: {screenshot_path.stat().st_size} bytes")
                                screenshot_saved = True
                                break
                            else:
                                logger.warning(f"shell+pull 스크린샷 파일 크기 부족: {screenshot_path.stat().st_size if screenshot_path.exists() else 0} bytes")
                        else:
                            logger.warning(f"adb shell screencap 실패: returncode={proc1.returncode}")
                            
                    except subprocess.TimeoutExpired as e:
                        logger.error(f"shell+pull 스크린샷 타임아웃 (시도 {attempt + 1}/{max_retries}): {e}")
                    except Exception as e:
                        logger.error(f"shell+pull 스크린샷 오류 (시도 {attempt + 1}/{max_retries}): {e}")
                
                # 재시도 전 대기
                if attempt < max_retries - 1 and not screenshot_saved:
                    time.sleep(2)
            
            if not screenshot_saved:
                logger.error(f"스크린샷 저장 최종 실패: 모든 방법 시도했으나 성공하지 못함")

            # 첨부파일 수집 (artifacts/result로 변경) + 스크린샷 + 로그캣 추가
            attachments = self._collect_attachments(device.serial, today)
            # 스크린샷이 첨부파일에 없으면 추가 (유효한 파일만)
            if str(screenshot_path) not in attachments and screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                attachments.append(str(screenshot_path))
                logger.info(f"스크린샷을 첨부파일 목록에 추가: {screenshot_path}")
            else:
                logger.warning(f"스크린샷을 첨부파일 목록에 추가하지 않음: 존재={screenshot_path.exists()}, 크기={screenshot_path.stat().st_size if screenshot_path.exists() else 0}")
            
            # 로그캣 파일 추가 (실패 시에만)
            if status == "실패" and logcat_path and logcat_path.exists():
                attachments.append(str(logcat_path))
                logger.info(f"로그캣 파일을 첨부파일 목록에 추가: {logcat_path}")

            elapsed = f"{time.time() - start_time:.2f}s"

            return TestResult(
                case_id=case_id,
                title=title,
                status=status,
                serial=device.serial,
                model=device.model,
                os_version=device.os_version,
                tving_version=device.tving_version,
                log_path=str(log_path),
                attachments=attachments,
                error_log=error_log,
                elapsed=elapsed
            )
        except subprocess.TimeoutExpired:
            status = "실패"
            error_msg = "테스트 타임아웃 (300초 초과)"
            logger.error(f"[{device.serial}] 테스트 타임아웃: {case_id}")
            return TestResult(
                case_id=case_id,
                title=title,
                status="실패",
                serial=device.serial,
                model=device.model,
                os_version=device.os_version,
                tving_version=device.tving_version,
                log_path=str(log_path),
                attachments=[],
                error_log="테스트 타임아웃 (300초 초과) - Maestro 명령이 지정된 시간 내에 완료되지 않았습니다.",
                elapsed=f"{time.time() - start_time:.2f}s"
            )
        except Exception as e:
            status = "실패"
            error_msg = str(e)
            logger.error(f"[{device.serial}] 테스트 실행 중 예외 발생: {e}")
            return TestResult(
                case_id=case_id,
                title=title,
                status="실패",
                serial=device.serial,
                model=device.model,
                os_version=device.os_version,
                tving_version=device.tving_version,
                log_path=str(log_path),
                attachments=[],
                error_log=f"테스트 실행 중 예외 발생: {str(e)}",
                elapsed=f"{time.time() - start_time:.2f}s"
            )
        finally:
            # 프록시는 테스트 런 완료 후 일괄 해제 (개별 테스트에서는 해제하지 않음)
            logger.info(f"[{device.serial}] === FINALLY 블록 시작 ===")
            logger.info(f"[{device.serial}] 개별 테스트 완료 - 프록시는 런 완료 후 해제")
            
            # mitmdump 종료 및 API 분석
            if mitmdump_proc:
                logger.info(f"[{device.serial}] mitmdump 프로세스 존재 - 종료 시작")
                
                # 더 안전한 종료 방식: SIGTERM 먼저, 타임아웃 후 SIGKILL
                try:
                    mitmdump_proc.terminate()
                    mitmdump_proc.wait(timeout=10)  # 10초 대기
                    logger.info(f"[{device.serial}] mitmdump 정상 종료 완료")
                except subprocess.TimeoutExpired:
                    logger.warning(f"[{device.serial}] mitmdump 정상 종료 타임아웃, 강제 종료")
                    mitmdump_proc.kill()
                    mitmdump_proc.wait(timeout=5)
                
                # API 덤프 파일이 완전히 저장될 때까지 잠시 대기
                time.sleep(2)
                
                logger.info(f"[{device.serial}] mitmdump 종료 및 API 분석 시작: {api_dump_path}")
                # API 덤프 파일을 새로운 로그 매니저로 이동
                if api_dump_path and api_dump_path.exists():
                    logger.info(f"[{device.serial}] API 덤프 파일 존재 확인: {api_dump_path}")
                    
                    # 덤프 파일 유효성 검사
                    file_size = api_dump_path.stat().st_size
                    logger.info(f"[{device.serial}] API 덤프 파일 크기: {file_size} bytes")
                    
                    if file_size < 1000:
                        logger.warning(f"[{device.serial}] API 덤프 파일이 너무 작습니다: {file_size} bytes")
                    
                    # 파일 끝 부분 확인 (완전성 검사)
                    try:
                        with open(api_dump_path, 'rb') as f:
                            f.seek(-100, 2)  # 파일 끝에서 100바이트 전
                            end_content = f.read()
                            if not end_content.strip():
                                logger.warning(f"[{device.serial}] API 덤프 파일이 불완전할 수 있습니다")
                    except Exception as e:
                        logger.warning(f"[{device.serial}] API 덤프 파일 검사 중 오류: {e}")
                    
                    try:
                        # mitmdump 덤프 파일 처리 (gzip 압축된 부분 포함)
                        import gzip
                        import re
                        
                        # 바이너리로 읽기
                        with open(api_dump_path, 'rb') as f:
                            binary_content = f.read()
                        
                        # gzip 압축된 부분 찾기 및 해제
                        try:
                            # gzip 매직 바이트 패턴 찾기
                            gzip_pattern = rb'\x1f\x8b\x08'
                            api_content = binary_content.decode('utf-8', errors='ignore')
                            
                            # gzip 압축된 부분이 있으면 로그
                            if gzip_pattern in binary_content:
                                logger.info(f"[{device.serial}] API 덤프에 gzip 압축 데이터 포함됨")
                            
                            logger.info(f"[{device.serial}] API 덤프 처리 성공 (크기: {len(api_content)} 문자)")
                        except Exception as e:
                            logger.warning(f"[{device.serial}] API 덤프 처리 중 오류: {e}")
                            # 오류 시 빈 문자열로 처리
                            api_content = ""
                        
                        new_api_path = log_manager.save_api_dump(device.serial, case_id, api_content)
                        logger.info(f"[{device.serial}] API 덤프 이동: {api_dump_path} -> {new_api_path}")
                        
                        # API 캡처 결과 분석 및 로그
                        if api_content:
                            tving_api_count = api_content.count("tving.com")
                            logger.info(f"[{device.serial}] API 캡처 완료: {tving_api_count}개 tving.com API 호출")
                        else:
                            logger.info(f"[{device.serial}] API 캡처 완료: API 호출 없음 (0 bytes)")
                        
                        # api_capture.py로 분석 및 DB 저장 (가상환경 Python 사용)
                        venv_python = os.path.join(os.getcwd(), "venv", "bin", "python")
                        api_capture_cmd = [
                            venv_python, "scripts/utils/api_capture.py",
                            str(new_api_path), str(case_id), device.serial, device.model, device.os_version, device.tving_version, today
                        ]
                        # run_id가 있으면 추가
                        if self.current_run_id:
                            api_capture_cmd.append(str(self.current_run_id))
                        logger.info(f"[{device.serial}] API 캡처 실행: {' '.join(api_capture_cmd)}")
                        
                        try:
                            api_capture_result = subprocess.run(api_capture_cmd, capture_output=True, text=True, timeout=30)
                            logger.info(f"[{device.serial}] API 캡처 실행 완료: returncode={api_capture_result.returncode}")
                            if api_capture_result.stdout:
                                logger.info(f"[{device.serial}] API 캡처 stdout: {api_capture_result.stdout}")
                            if api_capture_result.stderr:
                                logger.warning(f"[{device.serial}] API 캡처 stderr: {api_capture_result.stderr}")
                        except subprocess.TimeoutExpired:
                            logger.error(f"[{device.serial}] API 캡처 실행 타임아웃 (30초)")
                        except Exception as e:
                            logger.error(f"[{device.serial}] API 캡처 실행 중 오류: {e}")
                        
                        # API 캡처 완료 후 즉시 DB에서 통계 확인
                        try:
                            import sqlite3
                            conn = sqlite3.connect("artifacts/test_log.db")
                            cursor = conn.cursor()
                            cursor.execute("""
                                SELECT COUNT(*) as api_count, 
                                       AVG(CASE WHEN elapsed IS NOT NULL THEN elapsed ELSE 0 END) as avg_response,
                                       COUNT(CASE WHEN status_code >= 400 THEN 1 END) as failed_count
                                FROM test_api 
                                WHERE test_case_id = ? AND serial = ?
                            """, (case_id, device.serial))
                            stats = cursor.fetchone()
                            conn.close()
                            
                            if stats and stats[0] > 0:
                                # None 값 처리 (추가 안전장치)
                                try:
                                    avg_response = float(stats[1]) if stats[1] is not None else 0.0
                                    failed_count = int(stats[2]) if stats[2] is not None else 0
                                    logger.info(f"[{device.serial}] API 통계 - 전체: {stats[0]}건, 평균응답: {avg_response:.3f}초, 실패: {failed_count}건")
                                except (TypeError, ValueError) as e:
                                    logger.warning(f"[{device.serial}] API 통계 포맷 오류: {e}, 기본값 사용")
                                    logger.info(f"[{device.serial}] API 통계 - 전체: {stats[0]}건, 평균응답: 0.000초, 실패: 0건")
                            else:
                                logger.info(f"[{device.serial}] API 통계 - DB에 저장된 데이터 없음")
                        except Exception as e:
                            logger.warning(f"[{device.serial}] API 통계 조회 실패: {e}")
                        
                        # API 검증 실행 (JSON 설정 파일 기반)
                        try:
                            from scripts.utils.maestro_api_validator import validate_maestro_test_with_api
                            from scripts.utils.api_validation_config import APIValidationConfig
                            
                            # API 검증 설정 로드
                            config_manager = APIValidationConfig()
                            api_config = config_manager.load_validation_config(str(case_id))
                            
                            if api_config and api_config.get('enabled', False):
                                logger.info(f"[{device.serial}] API 검증 시작: TC{case_id}")
                                
                                # API 검증 실행
                                validation_result = validate_maestro_test_with_api(str(case_id), api_config['expected_apis'])
                                
                                if validation_result['status'] == 'FAIL':
                                    logger.warning(f"[{device.serial}] API 검증 실패: {validation_result.get('message', 'Unknown error')}")
                                    # API 검증 실패 시 테스트 결과에 반영
                                    if status == 'passed':
                                        status = 'failed'
                                        error_msg = f"API 검증 실패: {validation_result.get('message', 'Unknown error')}"
                                elif validation_result['status'] == 'PASS':
                                    logger.info(f"[{device.serial}] API 검증 성공")
                                else:
                                    logger.info(f"[{device.serial}] API 검증 스킵: {validation_result.get('message', 'No validation config')}")
                            else:
                                logger.info(f"[{device.serial}] API 검증 설정이 없음: TC{case_id}")
                                
                        except Exception as e:
                            logger.warning(f"[{device.serial}] API 검증 실행 실패: {e}")
                        

                    except Exception as e:
                        logger.warning(f"[{device.serial}] API 덤프 처리 실패: {e}")
                else:
                    logger.warning(f"[{device.serial}] API 덤프 파일이 존재하지 않음: {api_dump_path}")
            else:
                logger.warning(f"[{device.serial}] mitmdump 프로세스가 None입니다.")
            # 전체 성능 요약
            total_end_time = time.time()
            total_duration = total_end_time - total_start_time
            
            # 성능 분석 로그
            logger.info(f"[{device.serial}] === 성능 분석 ===")
            if maestro_start_time and maestro_end_time:
                maestro_duration = maestro_end_time - maestro_start_time
                logger.info(f"[{device.serial}] Maestro 실행: {maestro_duration:.3f}초")
            logger.info(f"[{device.serial}] 전체 소요시간: {total_duration:.3f}초")
            
            end_time = total_end_time
            log_step(
                test_case_id=case_id,
                step_name=title,
                status=status,
                start_time=start_time,
                end_time=end_time,
                error_msg=error_msg,
                serial=device.serial,
                model=device.model,
                os_version=device.os_version,
                tving_version=device.tving_version,
                run_id=str(self.current_run_id) if self.current_run_id else None
            )
    
    def _find_app_start_yaml(self) -> Optional[TestFlow]:
        """앱 시작 YAML 파일 찾기 (메타데이터 기반)"""
        for flow in self.maestro_flows:
            if flow.metadata.get("testrail_case_id") == 0:
                self.logger.info(f"앱 시작 플로우 찾음: {flow.path}")
                return flow
        return None
    
    def _find_maestro_flow(self, case_id: int) -> Optional[TestFlow]:
        """Maestro 플로우 YAML 파일 찾기 (파일명 우선, 없으면 메타데이터)"""
        # 1. 파일명에 TC{case_id}_ 패턴이 포함된 파일 우선 매칭
        case_id_str = str(case_id)
        for flow in self.maestro_flows:
            if f"TC{case_id_str}_" in flow.path.name:
                self.logger.info(f"[파일명매칭] Maestro 플로우 찾음: (ID: {case_id}) -> {flow.path}")
                return flow
        # 2. (백업) 메타데이터 기반 매칭
        for flow in self.maestro_flows:
            if flow.metadata.get("testrail_case_id") == case_id:
                self.logger.info(f"[메타데이터] Maestro 플로우 찾음: (ID: {case_id}) -> {flow.path}")
                return flow
        return None
    
    def _collect_attachments(self, serial: str, date: str) -> List[str]:
        """첨부파일 수집 (artifacts/result + logs 포함)"""
        attachments = []
        
        # 1. artifacts/result에서 첨부파일 수집
        result_dir = Path(f"artifacts/result/{serial}/{date}")
        if result_dir.exists():
            for ext in ['*.mp4', '*.png', '*.txt']:
                attachments.extend([str(f) for f in result_dir.glob(ext)])
        
        # 2. artifacts/logs에서 로그캣 파일 수집 (실패한 테스트의 경우)
        logs_dir = Path(f"artifacts/logs/{serial}")
        if logs_dir.exists():
            # 로그캣 파일 추가
            for logcat_file in logs_dir.glob("logcat_TC*.txt"):
                attachments.append(str(logcat_file))
        
        return attachments
    
    def _upload_results_to_testrail(self, results: List[TestResult], test_name: str):
        """테스트 결과를 TestRail에 즉시 업로드 (고도화된 템플릿 적용)"""
        logger.info(f"TestRail 업로드 시작: {test_name}")
        try:
            # 모든 단말의 결과를 종합하여 최종 상태 결정
            overall_status = "성공"
            comment_lines = []
            attachments = []

            # --- 1. 기본 정보 ---
            comment_lines.append(f"[테스트 결과] {test_name}")
            comment_lines.append("")
            comment_lines.append("[디바이스별 결과]")

            # --- 2. 단말별 결과 요약 ---
            for result in results:
                line = f"- [{result.status}] {result.model} (Android {result.os_version}, TVING {result.tving_version}, {result.serial}), 실행 {result.elapsed}"
                comment_lines.append(line)
                if result.status == "실패":
                    overall_status = "실패"
                # 성공/실패와 관계없이 모든 첨부파일 추가
                attachments.extend(result.attachments)
            comment_lines.append("")

            # --- 3. 주요 에러/이슈 ---
            error_details = []
            for r in results:
                if r.status == "실패" and r.error_log:
                    # 오류 타입 분석
                    error_type = "Unknown"
                    if "Maestro Error:" in r.error_log:
                        error_type = "Maestro UI Automation"
                    elif "Logcat Error:" in r.error_log:
                        error_type = "Device Logcat"
                    elif "API" in r.error_log:
                        error_type = "API/Network"
                    elif "timeout" in r.error_log.lower():
                        error_type = "Timeout"
                    elif "exception" in r.error_log.lower():
                        error_type = "Exception"
                    
                    error_details.append(f"- [{error_type}] {r.model} ({r.serial}): {r.error_log[:200]}{'...' if len(r.error_log) > 200 else ''}")
            
            if error_details:
                comment_lines.append("[주요 에러/이슈]")
                comment_lines.extend(error_details)
                comment_lines.append("")

            # --- 4. API 호출 요약/통계 (DB에서 조회) ---
            try:
                import sqlite3
                api_db = "artifacts/test_log.db"
                conn = sqlite3.connect(api_db)
                c = conn.cursor()
                case_ids = tuple(r.case_id for r in results)
                serials = tuple(r.serial for r in results)
                # 단말별 API 통계
                for r in results:
                    c.execute("""
                        SELECT COUNT(*), AVG(elapsed), SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END)
                        FROM test_api WHERE test_case_id=? AND serial=?
                    """, (r.case_id, r.serial))
                    total, avg_elapsed, fail_cnt = c.fetchone()
                    avg_str = f"{avg_elapsed:.2f}s" if avg_elapsed is not None else "N/A"
                    comment_lines.append(f"- [API] {r.model}({r.serial}): 전체 {total}건, 평균응답 {avg_str}, 실패 {fail_cnt}건")
                conn.close()
                comment_lines.append("")
            except Exception as e:
                comment_lines.append(f"[API 통계 조회 오류] {e}")

            # --- 5. 첨부파일 안내 (제거) ---
            # 실제 이미지 파일이 TestRail에 업로드되므로 경로 텍스트는 불필요
            # if attachments:
            #     comment_lines.append("[첨부파일]")
            #     for att in attachments:
            #         comment_lines.append(f"- {att}")
            #     comment_lines.append("")

            # --- 6. 분석/추천 (자동화) ---
            if overall_status == "실패":
                # 실제 실패 API 상세 자동 추출
                try:
                    c = sqlite3.connect("artifacts/test_log.db").cursor()
                    for r in results:
                        c.execute("""
                            SELECT url, status_code, elapsed, response_body
                            FROM test_api
                            WHERE test_case_id=? AND serial=? AND status_code >= 400
                            ORDER BY id DESC LIMIT 5
                        """, (r.case_id, r.serial))
                        fail_apis = c.fetchall()
                        if fail_apis:
                            comment_lines.append(f"[API 실패 상세] ({r.model}/{r.serial})")
                            for url, status_code, elapsed, resp in fail_apis:
                                resp_short = (resp[:200] + "...") if resp and len(resp) > 200 else resp
                                comment_lines.append(f"- {url} (status: {status_code}, {elapsed if elapsed is not None else 'N/A'}s)\n  → {resp_short}")
                except Exception as e:
                    comment_lines.append(f"[API 실패 상세 추출 오류] {e}")
                
                # UI 자동화 에러 로그 상세 분석
                for r in results:
                    if r.status == "실패" and r.error_log:
                        comment_lines.append(f"[UI 자동화 오류 상세] ({r.model}/{r.serial})")
                        
                        # 오류 타입별 분석
                        if "Maestro Error:" in r.error_log:
                            comment_lines.append("🔍 Maestro UI 자동화 오류:")
                            # Maestro 오류에서 핵심 정보 추출
                            maestro_errors = [line for line in r.error_log.split('\n') if 'Maestro Error:' in line]
                            for error in maestro_errors[:3]:  # 최대 3개만 표시
                                comment_lines.append(f"  • {error.replace('Maestro Error:', '').strip()}")
                        
                        if "Logcat Error:" in r.error_log:
                            comment_lines.append("📱 디바이스 로그캣 오류:")
                            # 로그캣 오류에서 핵심 정보 추출
                            logcat_errors = [line for line in r.error_log.split('\n') if 'Logcat Error:' in line]
                            for error in logcat_errors[:3]:  # 최대 3개만 표시
                                comment_lines.append(f"  • {error.replace('Logcat Error:', '').strip()}")
                        
                        if "timeout" in r.error_log.lower():
                            comment_lines.append("⏰ 타임아웃 오류:")
                            comment_lines.append("  • 테스트 실행 시간이 300초를 초과했습니다.")
                            comment_lines.append("  • 네트워크 상태나 디바이스 성능을 확인해주세요.")
                        comment_lines.append("")

            # TestRail status_id 매핑
            status_map = {
                "성공": 1,  # Passed
                "실패": 5,  # Failed
            }
            status_id = status_map.get(overall_status, 3)  # 기본값: Untested(3)

            # TestRail에 통합 결과 업로드
            result_id = testrail.add_result_for_case(
                self.testrail_config,
                self.current_run_id,
                results[0].case_id,
                status_id,
                "\n".join(comment_lines)
            )

            # 디버깅 로그 추가
            logger.info(f"TestRail 결과 업로드 결과: result_id={result_id}")
            logger.info(f"첨부파일 목록: {attachments}")

            # 이미지 파일 첨부파일 업로드 (성공/실패 모두)
            if result_id and attachments:
                logger.info(f"이미지 첨부파일 업로드 시작: {len(attachments)}개")
                for attachment in attachments:
                    if os.path.exists(attachment):
                        # 이미지 파일인지 확인 (.png, .jpg, .jpeg)
                        if attachment.lower().endswith(('.png', '.jpg', '.jpeg')):
                            logger.info(f"이미지 파일 업로드 시도: {attachment}")
                            success = testrail.add_attachment_to_result(self.testrail_config, result_id, attachment)
                            if success:
                                logger.info(f"이미지 첨부파일 업로드 성공: {attachment}")
                            else:
                                logger.warning(f"이미지 첨부파일 업로드 실패: {attachment}")
                        else:
                            logger.info(f"이미지가 아닌 파일 스킵: {attachment}")
                    else:
                        logger.warning(f"첨부파일 없음: {attachment}")
            else:
                if not result_id:
                    logger.warning("TestRail 결과 ID가 없어서 첨부파일 업로드 스킵")
                if not attachments:
                    logger.warning("첨부파일 목록이 비어있어서 업로드 스킵")

            logger.info(f"TestRail 업로드 완료: {test_name}")

        except Exception as e:
            logger.error(f"TestRail 업로드 실패: {test_name} - {str(e)}")

    def collect_results(self) -> List[TestResult]:
        return self.results 