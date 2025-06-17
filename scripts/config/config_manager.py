import configparser
import os
from pathlib import Path
from typing import Any, Optional

class ConfigManager:
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """설정 파일 로드"""
        config = configparser.ConfigParser()
        config_path = Path(__file__).parent.parent.parent / 'config' / 'config.ini'
        
        if not config_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
        
        config.read(config_path)
        self._config = config
    
    @property
    def testrail(self) -> dict:
        """TestRail 설정 반환"""
        return dict(self._config['TestRail'])
    
    @property
    def app(self) -> dict:
        """앱 설정 반환"""
        return dict(self._config['App'])
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """설정값 조회"""
        return self._config.get(section, key, fallback=default)
    
    def get_testrail(self, key: str, default: Any = None) -> Any:
        """TestRail 설정값 조회"""
        return self._config.get('TestRail', key, fallback=default)
    
    def get_app(self, key: str, default: Any = None) -> Any:
        """앱 설정값 조회"""
        return self._config.get('App', key, fallback=default) 