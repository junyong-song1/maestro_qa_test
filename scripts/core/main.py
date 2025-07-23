#!/usr/bin/env python3
"""
QA 자동화 테스트 메인 실행 파일
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.core.application import QAApplication
from scripts.utils.logger import get_logger
from scripts.utils.log_manager import log_manager

def main():
    """메인 함수"""
    logger = get_logger("Main")
    
    try:
        # 로그 정리 수행
        logger.info("로그 정리 시작...")
        log_manager.cleanup_old_logs()
        log_manager.compress_large_logs()
        
        # 로그 통계 출력
        stats = log_manager.get_log_stats()
        logger.info(f"로그 통계: {stats['file_count']}개 파일, {stats['total_size'] / (1024*1024):.1f}MB")
        
        # QA 애플리케이션 실행
        app = QAApplication()
        app.run()
        
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"예상치 못한 오류가 발생했습니다: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 