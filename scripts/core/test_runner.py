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
from ..testrail import testrail
from scripts.utils.testlog_db import log_step, init_db

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

            # suite_id가 1784일 때만 앱 시작 테스트 실행
            if str(suite_id) == '1784':
                app_results = self._run_app_start_test()
            
            # 2. 각 테스트 케이스 실행 및 즉시 업로드
            for test_case in test_cases:
                case_results = self._run_single_test(test_case)
                if case_results:
                    self._upload_results_to_testrail(case_results, test_case['title'])
            
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
        start_time = time.time()
        status = "success"
        error_msg = None
        mitmdump_proc = None
        api_dump_path = None
        screenshot_path = None  # 스크린샷 경로 변수 추가
        logcat_path = None  # 로그캣 경로 변수 추가
        try:
            # 로그 파일 경로 설정
            today = datetime.now().strftime('%Y%m%d')
            log_dir = Path(f"artifacts/logs/{device.serial}")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"maestro_TC{case_id}.log"
            logcat_path = log_dir / f"logcat_TC{case_id}.txt"  # 로그캣 파일 경로 추가

            # mitmdump 백그라운드 실행 (테스트케이스별)
            api_dump_path = log_dir / f"api_TC{case_id}.dump"
            mitmdump_proc = subprocess.Popen(
                ["mitmdump", "-w", str(api_dump_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1)  # 프록시 준비 대기 (필요시 조정)

            # Maestro 명령 실행 (YAML 파일 경로 직접 전달)
            cmd = ["maestro", f"--device={device.serial}", "test", str(test_flow.path)]
            logger.info(f"[{device.serial}] [테스트 실행] {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding='utf-8')

            # 상세 로그 출력 (testrail_maestro_runner.py와 동일)
            logger.info(f"[{device.serial}] stdout:\n{result.stdout}")
            logger.info(f"[{device.serial}] stderr:\n{result.stderr}")
            logger.info(f"[{device.serial}] returncode: {result.returncode}")

            # 로그 저장
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"=== Maestro Test Execution Log ===\n")
                f.write(f"Test Case: {title} (ID: {case_id})\n")
                f.write(f"Device: {device.model} ({device.serial})\n")
                f.write(f"Command: {' '.join(cmd)}\n")
                f.write(f"Return Code: {result.returncode}\n")
                f.write(f"Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"\n=== STDOUT ===\n{result.stdout}\n")
                if result.stderr:
                    f.write(f"\n=== STDERR ===\n{result.stderr}\n")

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
                        # 로그캣 파일 저장
                        with open(logcat_path, 'w', encoding='utf-8') as f:
                            f.write(f"=== Device Logcat (Test Failed) ===\n")
                            f.write(f"Test Case: {title} (ID: {case_id})\n")
                            f.write(f"Device: {device.model} ({device.serial})\n")
                            f.write(f"Collection Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write(f"\n{logcat_result.stdout}")
                        
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

            # --- 스크린샷 저장 (성공/실패 모두) ---
            screenshot_dir = Path(f"artifacts/images/{today}")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%H%M%S')
            screenshot_filename = f"TC{case_id}_{device.serial}_{status}_{timestamp}.png"
            screenshot_path = screenshot_dir / screenshot_filename
            
            # 스크린샷 저장 (adb shell screencap + adb pull 방식)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # 1. 디바이스에 임시 파일로 저장
                    temp_path = f"/sdcard/screenshot_{timestamp}.png"
                    proc1 = subprocess.run([
                        "adb", "-s", device.serial, "shell", "screencap", "-p", temp_path
                    ], timeout=10)
                    
                    if proc1.returncode == 0:
                        # 2. 로컬로 파일 가져오기
                        proc2 = subprocess.run([
                            "adb", "-s", device.serial, "pull", temp_path, str(screenshot_path)
                        ], timeout=10)
                        
                        # 3. 임시 파일 삭제
                        subprocess.run([
                            "adb", "-s", device.serial, "shell", "rm", temp_path
                        ], timeout=5)
                        
                        # 파일 유효성 검사
                        if screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                            logger.info(f"스크린샷 저장 성공: {screenshot_path}, 파일크기: {screenshot_path.stat().st_size} bytes")
                            break
                        else:
                            logger.warning(f"스크린샷 저장 실패 (시도 {attempt + 1}/{max_retries}): 파일크기 {screenshot_path.stat().st_size if screenshot_path.exists() else 0} bytes")
                    else:
                        logger.warning(f"adb shell screencap 실패 (시도 {attempt + 1}/{max_retries}): returncode={proc1.returncode}")
                    
                    if attempt < max_retries - 1:
                        time.sleep(1)  # 재시도 전 대기
                    else:
                        logger.error(f"스크린샷 저장 최종 실패: {screenshot_path}")
                        
                except Exception as e:
                    logger.error(f"스크린샷 저장 중 오류 (시도 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                    else:
                        logger.error(f"스크린샷 저장 최종 실패: {e}")

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
            # mitmdump 종료 및 API 분석
            if mitmdump_proc:
                mitmdump_proc.terminate()
                mitmdump_proc.wait(timeout=5)
                logger.info(f"[{device.serial}] mitmdump 종료 및 API 분석 시작: {api_dump_path}")
                # api_capture.py로 분석 및 DB 저장
                if api_dump_path and api_dump_path.exists():
                    subprocess.run([
                        sys.executable, "scripts/utils/api_capture.py",
                        str(api_dump_path), str(case_id), device.serial, device.model, device.os_version, device.tving_version, today
                    ], check=False)
            end_time = time.time()
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
                tving_version=device.tving_version
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
                        
                        # 일반적인 해결 방안 제시
                        comment_lines.append("💡 해결 방안:")
                        comment_lines.append("  • 디바이스 재부팅 후 재시도")
                        comment_lines.append("  • 네트워크 연결 상태 확인")
                        comment_lines.append("  • TVING 앱 재설치 또는 캐시 클리어")
                        comment_lines.append("  • 첨부된 로그캣 파일 확인")
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