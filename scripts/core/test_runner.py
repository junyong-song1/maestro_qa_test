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
from ..testrail.testrail_manager import TestRailManager

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
        self.maestro_flows = []
        self.current_run_id = None  # 현재 테스트 런 ID 저장
        
        # testrail_manager가 전달되면 사용, 아니면 새로 생성
        if testrail_manager:
            self.testrail_manager = testrail_manager
        else:
            # TestRail 설정을 올바른 형태로 전달
            testrail_config = {
                'url': config_manager['TestRail']['url'],
                'username': config_manager['TestRail']['username'],
                'api_key': config_manager['TestRail']['api_key'],
                'project_id': config_manager['TestRail']['project_id']
            }
            self.testrail_manager = TestRailManager(testrail_config)
    
    def run_tests(self, test_cases: List[Any], devices: List[DeviceInfo]) -> List[TestResult]:
        """Maestro 테스트 실행 - 플로우별 즉시 업로드"""
        self.devices = devices
        self.results = []
        
        try:
            # 테스트 시작 시 하나의 테스트 런 생성
            suite_id = self.config.get('TestRail', 'suite_id', '1787')
            test_run = self.testrail_manager.create_test_run(
                suite_id=suite_id,
                name=f"자동화 테스트 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.current_run_id = test_run.id
            logger.info(f"테스트 런 생성 완료 (Run ID: {self.current_run_id})")
            
            # 1. 앱 시작 테스트 실행 (TestRail 업로드 제외)
            app_results = self._run_app_start_test()
            
            # 2. 각 테스트 케이스 실행 및 즉시 업로드
            for test_case in test_cases:
                case_results = self._run_single_test(test_case)
                if case_results:
                    self._upload_results_to_testrail(case_results, test_case.title)
            
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
        case_id = str(test_case.id)
        title = test_case.title
        
        logger.info(f"테스트 실행: {title} (ID: {case_id})")
        
        yaml_path = self._find_maestro_flow(case_id)
        if not yaml_path:
            logger.warning(f"YAML 파일 없음: TC{case_id}")
            return []
        
        results = []
        for device in self.devices:
            result = self._run_maestro_test(yaml_path, device, case_id, title)
            results.append(result)
            self.results.append(result)
        
        return results
    
    def _run_maestro_test(self, yaml_path: str, device: DeviceInfo, case_id: str, title: str) -> TestResult:
        """Maestro 테스트 실행 (testrail_maestro_runner.py와 동일한 기준 적용)"""
        start_time = time.time()
        
        # 로그 파일 경로 설정 (artifacts/logs로 변경)
        today = datetime.now().strftime('%Y%m%d')
        log_dir = Path(f"artifacts/logs/{device.serial}")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"maestro_TC{case_id}.log"
        
        # Maestro 명령 실행
        cmd = ["maestro", f"--device={device.serial}", "test", yaml_path]
        logger.info(f"[{device.serial}] [테스트 실행] {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # 상세 로그 출력 (testrail_maestro_runner.py와 동일)
            logger.info(f"[{device.serial}] stdout:\n{result.stdout}")
            logger.info(f"[{device.serial}] stderr:\n{result.stderr}")
            logger.info(f"[{device.serial}] returncode: {result.returncode}")
            
            # 로그 저장
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
                if result.stderr:
                    f.write(f"\nSTDERR:\n{result.stderr}")
            
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
            
            error_log = result.stderr if result.stderr else ""
            
            # 첨부파일 수집 (artifacts/result로 변경)
            attachments = self._collect_attachments(device.serial, today)
            
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
                error_log="테스트 타임아웃",
                elapsed=f"{time.time() - start_time:.2f}s"
            )
    
    def _find_app_start_yaml(self) -> Optional[str]:
        """앱 시작 YAML 파일 찾기"""
        for f in glob.glob('maestro_flows/TC00000_앱시작*.yaml'):
            return f
        return None
    
    def _find_maestro_flow(self, case_id: str) -> Optional[str]:
        """Maestro 플로우 YAML 파일 찾기"""
        search_patterns = [
            f"maestro_flows/TC{case_id}_*.yaml",
            f"maestro_flows/TC{case_id:0>6}_*.yaml"
        ]
        
        for pattern in search_patterns:
            matches = glob.glob(pattern, recursive=True)
            matches = [m for m in matches if '/sub_flows/' not in m]
            
            if matches:
                # 최신 파일 선택
                matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                return matches[0]
        
        return None
    
    def _collect_attachments(self, serial: str, date: str) -> List[str]:
        """첨부파일 수집 (artifacts/result로 변경)"""
        result_dir = Path(f"artifacts/result/{serial}/{date}")
        if not result_dir.exists():
            return []
        
        attachments = []
        for ext in ['*.mp4', '*.png', '*.txt']:
            attachments.extend([str(f) for f in result_dir.glob(ext)])
        
        return attachments
    
    def _upload_results_to_testrail(self, results: List[TestResult], test_name: str):
        """테스트 결과를 TestRail에 즉시 업로드"""
        logger.info(f"TestRail 업로드 시작: {test_name}")
        
        try:
            # 모든 단말의 결과를 종합하여 최종 상태 결정
            overall_status = "성공"
            comment_lines = []
            attachments = []
            
            # 각 단말의 결과를 확인하고 하나라도 실패면 전체 실패 처리
            for result in results:
                if result.status == "실패":
                    overall_status = "실패"
                
                comment_lines.append(
                    f"[{result.status}] 디바이스: {result.serial}\n"
                    f"모델: {result.model}\n"
                    f"OS: {result.os_version}\n"
                    f"TVING: {result.tving_version}\n"
                    f"실행 시간: {result.elapsed}"
                )
                
                # 실패한 경우 첨부파일 수집
                if result.status == "실패":
                    attachments.extend(result.attachments)
            
            # TestRail에 통합 결과 업로드
            result_id = self.testrail_manager.add_result(
                run_id=self.current_run_id,
                case_id=results[0].case_id,  # 모든 결과의 case_id는 동일
                status=overall_status,
                comment="\n\n".join(comment_lines)
            )
            
            # 실패한 경우에만 첨부파일 업로드
            if overall_status == "실패" and attachments and result_id:
                logger.info(f"실패 케이스 첨부파일 업로드 시작: {len(attachments)}개")
                for attachment in attachments:
                    if os.path.exists(attachment):
                        success = self.testrail_manager.add_attachment(result_id, attachment)
                        if success:
                            logger.info(f"첨부파일 업로드 성공: {attachment}")
                        else:
                            logger.warning(f"첨부파일 업로드 실패: {attachment}")
                    else:
                        logger.warning(f"첨부파일 없음: {attachment}")
            
            logger.info(f"TestRail 업로드 완료: {test_name}")
            
        except Exception as e:
            logger.error(f"TestRail 업로드 실패: {test_name} - {str(e)}")

    def collect_results(self) -> List[TestResult]:
        return self.results 