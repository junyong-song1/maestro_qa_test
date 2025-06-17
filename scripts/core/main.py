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

def main():
    """메인 함수"""
    logger = get_logger("Main")
    
    try:
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