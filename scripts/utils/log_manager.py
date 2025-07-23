import logging
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json
import gzip
import subprocess

class LogManager:
    """체계적인 로그 관리를 위한 클래스"""
    
    def __init__(self, base_dir: Path = Path("artifacts/logs")):
        self.base_dir = base_dir
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.log_dir = self.base_dir / self.today
        
        # 로그 디렉토리 생성
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 로그 설정
        self._setup_logging()
        
        # 로그 정리 설정
        self.max_log_days = 7  # 7일 이상 된 로그 삭제
        self.max_logcat_size = 10 * 1024 * 1024  # 10MB
        
    def _setup_logging(self):
        """로깅 설정"""
        # 메인 로거 설정
        self.logger = logging.getLogger("LogManager")
        self.logger.setLevel(logging.DEBUG)
        
        # 기존 핸들러 제거
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # 파일 핸들러 (일별)
        log_file = self.log_dir / "application.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(console_formatter)
        self.logger.addHandler(file_handler)
        
        # 에러 로그 파일 (에러만 별도 저장)
        error_log_file = self.log_dir / "errors.log"
        error_handler = logging.FileHandler(error_log_file, encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(console_formatter)
        self.logger.addHandler(error_handler)
    
    def get_test_log_path(self, device_serial: str, case_id: str, log_type: str) -> Path:
        """테스트별 로그 경로 생성"""
        device_dir = self.log_dir / device_serial
        device_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%H%M%S")
        return device_dir / f"{log_type}_TC{case_id}_{timestamp}.log"
    
    def save_maestro_log(self, device_serial: str, case_id: str, content: str) -> Path:
        """Maestro 로그 저장"""
        log_path = self.get_test_log_path(device_serial, case_id, "maestro")
        log_path.write_text(content, encoding="utf-8")
        self.logger.info(f"Maestro 로그 저장: {log_path}")
        return log_path
    
    def save_logcat(self, device_serial: str, case_id: str, content: str) -> Path:
        """로그캣 저장 (압축 포함)"""
        log_path = self.get_test_log_path(device_serial, case_id, "logcat")
        
        # 로그캣 크기가 크면 압축
        if len(content.encode('utf-8')) > self.max_logcat_size:
            compressed_path = log_path.with_suffix('.log.gz')
            with gzip.open(compressed_path, 'wt', encoding='utf-8') as f:
                f.write(content)
            self.logger.info(f"로그캣 압축 저장: {compressed_path}")
            return compressed_path
        else:
            log_path.write_text(content, encoding="utf-8")
            self.logger.info(f"로그캣 저장: {log_path}")
            return log_path
    
    def save_api_dump(self, device_serial: str, case_id: str, content: str) -> Path:
        """API 덤프 저장"""
        log_path = self.get_test_log_path(device_serial, case_id, "api")
        log_path.write_text(content, encoding="utf-8")
        self.logger.info(f"API 덤프 저장: {log_path}")
        return log_path
    
    def save_test_summary(self, device_serial: str, case_id: str, summary: Dict[str, Any]) -> Path:
        """테스트 요약 정보 저장"""
        summary_path = self.get_test_log_path(device_serial, case_id, "summary")
        summary['timestamp'] = datetime.now().isoformat()
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self.logger.info(f"테스트 요약 저장: {summary_path}")
        return summary_path
    
    def cleanup_old_logs(self):
        """오래된 로그 정리"""
        cutoff_date = datetime.now() - timedelta(days=self.max_log_days)
        
        for log_dir in self.base_dir.iterdir():
            if not log_dir.is_dir():
                continue
                
            try:
                dir_date = datetime.strptime(log_dir.name, "%Y-%m-%d")
                if dir_date < cutoff_date:
                    shutil.rmtree(log_dir)
                    self.logger.info(f"오래된 로그 삭제: {log_dir}")
            except ValueError:
                # 날짜 형식이 아닌 디렉토리는 건너뛰기
                continue
    
    def get_log_stats(self) -> Dict[str, Any]:
        """로그 통계 정보"""
        stats = {
            'total_size': 0,
            'file_count': 0,
            'oldest_log': None,
            'newest_log': None,
            'largest_file': None,
            'device_dirs': []
        }
        
        for log_dir in self.base_dir.iterdir():
            if not log_dir.is_dir():
                continue
                
            try:
                datetime.strptime(log_dir.name, "%Y-%m-%d")
                device_count = len(list(log_dir.glob("*")))
                stats['device_dirs'].append({
                    'date': log_dir.name,
                    'device_count': device_count
                })
                
                for file_path in log_dir.rglob("*"):
                    if file_path.is_file():
                        stats['total_size'] += file_path.stat().st_size
                        stats['file_count'] += 1
                        
                        if not stats['largest_file'] or file_path.stat().st_size > stats['largest_file']['size']:
                            stats['largest_file'] = {
                                'path': str(file_path),
                                'size': file_path.stat().st_size
                            }
            except ValueError:
                continue
        
        return stats
    
    def compress_large_logs(self):
        """큰 로그 파일 압축"""
        for log_dir in self.base_dir.iterdir():
            if not log_dir.is_dir():
                continue
                
            for file_path in log_dir.rglob("*.log"):
                if file_path.stat().st_size > self.max_logcat_size:
                    compressed_path = file_path.with_suffix('.log.gz')
                    if not compressed_path.exists():
                        with gzip.open(compressed_path, 'wt', encoding='utf-8') as f:
                            f.write(file_path.read_text(encoding='utf-8'))
                        file_path.unlink()  # 원본 파일 삭제
                        self.logger.info(f"로그 압축: {file_path} -> {compressed_path}")

# 전역 로그 매니저 인스턴스
log_manager = LogManager() 