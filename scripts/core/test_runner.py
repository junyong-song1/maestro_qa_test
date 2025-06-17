from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
import glob
import os
from datetime import datetime

from ..device.device_manager import DeviceInfo
from ..utils.logger import get_logger

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
    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.maestro_flows = []
    
    def run_tests(self, test_cases: List[Any], devices: List[DeviceInfo]) -> List[TestResult]:
        """Maestro 테스트 실행"""
        self.devices = devices
        self.results = []
        
        # 앱 시작 테스트 먼저 실행
        self._run_app_start_test()
        
        # 각 테스트 케이스 실행
        for test_case in test_cases:
            self._run_single_test(test_case)
        
        return self.results
    
    def _run_app_start_test(self):
        """앱 시작 테스트 실행"""
        self.logger.info("앱 시작 테스트 실행 중...")
        
        app_start_yaml = self._find_app_start_yaml()
        if not app_start_yaml:
            self.logger.error("앱 시작 YAML 파일을 찾을 수 없습니다.")
            return
        
        for device in self.devices:
            result = self._run_maestro_test(app_start_yaml, device, "00000", "앱 시작")
            if result.status == "실패":
                self.logger.error(f"앱 시작 실패: {device.serial}")
                return
    
    def _run_single_test(self, test_case):
        """단일 테스트 케이스 실행"""
        case_id = str(test_case.id)
        title = test_case.title
        
        self.logger.info(f"테스트 실행: {title} (ID: {case_id})")
        
        yaml_path = self._find_maestro_flow(case_id)
        if not yaml_path:
            self.logger.warning(f"YAML 파일 없음: TC{case_id}")
            return
        
        for device in self.devices:
            result = self._run_maestro_test(yaml_path, device, case_id, title)
            self.results.append(result)
    
    def _run_maestro_test(self, yaml_path: str, device: DeviceInfo, case_id: str, title: str) -> TestResult:
        """Maestro 테스트 실행"""
        start_time = time.time()
        
        # 로그 파일 경로 설정 (artifacts/logs로 변경)
        today = datetime.now().strftime('%Y%m%d')
        log_dir = Path(f"artifacts/logs/{device.serial}")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"maestro_TC{case_id}.log"
        
        # Maestro 명령 실행
        cmd = ["maestro", f"--device={device.serial}", "test", yaml_path]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # 로그 저장
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
                if result.stderr:
                    f.write(f"\nSTDERR:\n{result.stderr}")
            
            # 결과 분석
            status = "성공" if self._is_test_passed(result.stdout) else "실패"
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
            self.logger.error(f"테스트 타임아웃: {case_id}")
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
    
    def _is_test_passed(self, output: str) -> bool:
        """테스트 성공 여부 판단"""
        return '[Passed]' in output or 'Flow Passed' in output
    
    def _collect_attachments(self, serial: str, date: str) -> List[str]:
        """첨부파일 수집 (artifacts/result로 변경)"""
        result_dir = Path(f"artifacts/result/{serial}/{date}")
        if not result_dir.exists():
            return []
        
        attachments = []
        for ext in ['*.mp4', '*.png', '*.txt']:
            attachments.extend([str(f) for f in result_dir.glob(ext)])
        
        return attachments
    
    def collect_results(self) -> List[TestResult]:
        return self.results 