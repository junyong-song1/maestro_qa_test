"""
API 검증 설정 관리 시스템
Maestro YAML과 분리된 API 검증 설정을 관리
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class APIValidationConfig:
    """API 검증 설정 관리 클래스"""
    
    def __init__(self, config_dir: str = "config/api_validation"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def create_validation_config(self, test_case_id: str, expected_apis: List[Dict[str, Any]]) -> str:
        """테스트케이스별 API 검증 설정 생성"""
        config = {
            "test_case_id": test_case_id,
            "enabled": True,
            "expected_apis": expected_apis,
            "created_at": str(Path().cwd()),
            "description": f"API 검증 설정 for {test_case_id}"
        }
        
        config_file = self.config_dir / f"{test_case_id}_api_validation.json"
        
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"API 검증 설정 생성: {config_file}")
            return str(config_file)
            
        except Exception as e:
            logger.error(f"API 검증 설정 생성 실패: {e}")
            return None
    
    def load_validation_config(self, test_case_id: str) -> Optional[Dict[str, Any]]:
        """테스트케이스별 API 검증 설정 로드"""
        config_file = self.config_dir / f"{test_case_id}_api_validation.json"
        
        if not config_file.exists():
            return None
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            logger.info(f"API 검증 설정 로드: {config_file}")
            return config
            
        except Exception as e:
            logger.error(f"API 검증 설정 로드 실패: {e}")
            return None
    
    def get_all_configs(self) -> List[Dict[str, Any]]:
        """모든 API 검증 설정 조회"""
        configs = []
        
        for config_file in self.config_dir.glob("*_api_validation.json"):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    configs.append(config)
            except Exception as e:
                logger.error(f"설정 파일 로드 실패 {config_file}: {e}")
        
        return configs
    
    def delete_validation_config(self, test_case_id: str) -> bool:
        """API 검증 설정 삭제"""
        config_file = self.config_dir / f"{test_case_id}_api_validation.json"
        
        if config_file.exists():
            try:
                config_file.unlink()
                logger.info(f"API 검증 설정 삭제: {config_file}")
                return True
            except Exception as e:
                logger.error(f"API 검증 설정 삭제 실패: {e}")
                return False
        
        return False

def create_default_api_configs():
    """기본 API 검증 설정 생성"""
    config_manager = APIValidationConfig()
    
    # 로그인 관련 API 검증 설정
    login_apis = [
        {
            "name": "로그인 API",
            "pattern": "/api/auth/login",
            "method": "POST",
            "expected_status": 200,
            "required": True
        },
        {
            "name": "사용자 프로필 API",
            "pattern": "/api/user/profile",
            "method": "GET",
            "expected_status": 200,
            "required": False
        }
    ]
    
    # 콘텐츠 관련 API 검증 설정
    content_apis = [
        {
            "name": "콘텐츠 목록 API",
            "pattern": "/api/content/list",
            "method": "GET",
            "expected_status": 200,
            "required": True
        },
        {
            "name": "콘텐츠 상세 API",
            "pattern": "/api/content/detail",
            "method": "GET",
            "expected_status": 200,
            "required": True
        }
    ]
    
    # 재생 관련 API 검증 설정
    play_apis = [
        {
            "name": "재생 시작 API",
            "pattern": "/api/play/start",
            "method": "POST",
            "expected_status": 200,
            "required": True
        },
        {
            "name": "재생 상태 API",
            "pattern": "/api/play/status",
            "method": "GET",
            "expected_status": 200,
            "required": False
        }
    ]
    
    # 기본 설정 생성
    configs = [
        ("TC314789", login_apis + content_apis),
        ("TC314790", content_apis),
        ("TC314791", content_apis + play_apis),
        ("TC314792", content_apis),
        ("TC314798", play_apis),
        ("TC314799", play_apis),
        ("TC314800", login_apis),
        ("TC314801", login_apis),
        ("TC314802", login_apis),
        ("TC314803", login_apis),
    ]
    
    created_files = []
    for test_case_id, apis in configs:
        config_file = config_manager.create_validation_config(test_case_id, apis)
        if config_file:
            created_files.append(config_file)
    
    logger.info(f"기본 API 검증 설정 {len(created_files)}개 생성 완료")
    return created_files

if __name__ == "__main__":
    # 기본 설정 생성 테스트
    create_default_api_configs() 