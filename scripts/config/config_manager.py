import logging
import configparser
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger('scripts.config')

class ConfigManager:
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        logger.info("Initializing ConfigManager")
        self._config = configparser.ConfigParser()
        config_path = Path(__file__).parent.parent.parent / 'config' / 'config.ini'
        
        if not config_path.exists():
            logger.error(f"설정 파일을 찾을 수 없습니다: {config_path}")
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
        
        logger.info(f"Loading config from: {config_path}")
        self._config.read(config_path)
    
    def __getitem__(self, key: str) -> configparser.SectionProxy:
        """딕셔너리 스타일 접근 지원"""
        return self._config[key]
    
    def get(self, section: str, key: str, fallback: Any = None) -> str:
        """설정값 가져오기"""
        try:
            value = self._config.get(section, key, fallback=fallback)
            logger.debug(f"Got config value for {section}.{key}")
            return value
        except Exception as e:
            logger.error(f"Error getting config value for {section}.{key}: {str(e)}")
            return None
    
    def get_testrail(self, key: str, fallback: str = None) -> str:
        """TestRail 설정값 가져오기"""
        return self.get('TestRail', key, fallback=fallback)
    
    def get_app(self, key: str, fallback: str = None) -> str:
        """App 설정값 가져오기"""
        return self.get('App', key, fallback=fallback)
    
    def get_testrail_config(self) -> dict:
        """TestRail 설정 가져오기"""
        config = {
            'url': self.get('TestRail', 'url'),
            'username': self.get('TestRail', 'username'),
            'api_key': self.get('TestRail', 'api_key'),
            'project_id': self.get('TestRail', 'project_id')
        }
        
        # None 값이 있는지 확인
        for key, value in config.items():
            if value is None:
                logger.error(f"TestRail 설정에서 {key} 값이 None입니다.")
                raise ValueError(f"TestRail 설정에서 {key} 값이 None입니다.")
        
        return config
    
    def get_app_config(self) -> dict:
        """앱 설정 가져오기"""
        return {
            'package_name': self.get('App', 'package_name'),
            'activity_name': self.get('App', 'activity_name')
        } 