from typing import List, Optional
import subprocess
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class DeviceInfo:
    serial: str
    model: str
    os_version: str
    build_id: str
    tving_version: str

class DeviceManager:
    def __init__(self, config=None):
        self.config = config
        self.devices: List[DeviceInfo] = []
        self.adb_path = self._find_adb_path()
        self.current_device = None
    
    def _find_adb_path(self):
        """ADB 경로를 찾습니다."""
        # 일반적인 ADB 경로들
        possible_paths = [
            "adb",
            "/usr/local/bin/adb",
            "/usr/bin/adb",
            "/opt/homebrew/bin/adb",  # macOS Homebrew
            os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),  # Android SDK
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, "version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    logger.info(f"Found ADB at: {path}")
                    return path
            except:
                continue
        
        logger.warning("ADB not found in common paths, using 'adb'")
        return "adb"
    
    def _start_adb_server(self):
        """ADB 서버를 시작합니다."""
        try:
            subprocess.run([self.adb_path, "start-server"], capture_output=True, text=True, timeout=10)
            logger.info("ADB server started")
        except Exception as e:
            logger.error(f"Failed to start ADB server: {e}")
    
    def discover_devices(self) -> List[DeviceInfo]:
        """연결된 디바이스들을 발견하고 정보를 수집"""
        try:
            # ADB 서버 시작
            self._start_adb_server()
            
            logger.info("Discovering devices...")
            result = subprocess.run([self.adb_path, "devices", "-l"], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                logger.error(f"ADB devices command failed: {result.stderr}")
                return []
            
            logger.info(f"ADB devices output: {result.stdout}")
            
            devices = []
            
            for line in result.stdout.split('\n')[1:]:  # 첫 줄은 헤더이므로 건너뜀
                if line.strip() and 'device' in line and not line.startswith('*'):
                    serial = line.split()[0]
                    logger.info(f"Found device: {serial}")
                    
                    # 디바이스 정보 가져오기
                    model = self._get_device_property(serial, 'ro.product.model')
                    os_version = self._get_device_property(serial, 'ro.build.version.release')
                    build_id = self._get_device_property(serial, 'ro.build.display.id')
                    tving_version = self._get_tving_version(serial)
                    
                    device_info = DeviceInfo(serial, model, os_version, build_id, tving_version)
                    devices.append(device_info)
                    logger.info(f"Device info: {device_info}")
            
            self.devices = devices
            return devices
        except Exception as e:
            logger.error(f"Error discovering devices: {e}")
            return []
    
    def _get_device_property(self, serial, prop):
        """디바이스의 특정 속성을 가져옵니다."""
        try:
            result = subprocess.run(
                [self.adb_path, "-s", serial, "shell", "getprop", prop],
                capture_output=True,
                text=True,
                timeout=10
            )
            value = result.stdout.strip()
            logger.info(f"Property {prop} for {serial}: {value}")
            return value if value else "Unknown"
        except Exception as e:
            logger.error(f"Error getting property {prop} for {serial}: {e}")
            return "Unknown"
    
    def _get_tving_version(self, serial: str) -> str:
        """TVING 앱 버전 조회"""
        try:
            result = subprocess.run(
                [self.adb_path, "-s", serial, "shell", "dumpsys", "package", "net.cj.cjhv.gs.tving"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            for line in result.stdout.split('\n'):
                if 'versionName' in line:
                    version = line.split('=')[1].strip()
                    logger.info(f"TVING version for {serial}: {version}")
                    return version
            return "Not installed"
        except Exception as e:
            logger.error(f"Error getting TVING version for {serial}: {e}")
            return "Unknown"
    
    def check_environment(self, serial: str) -> bool:
        """디바이스 환경 체크"""
        try:
            # TVING 앱 설치 여부 확인
            result = subprocess.run(
                [self.adb_path, "-s", serial, "shell", "pm", "list", "packages"],
                capture_output=True,
                text=True,
                timeout=10
            )
            packages = result.stdout
            if 'net.cj.cjhv.gs.tving' not in packages:
                return False
            return True
        except Exception as e:
            logger.error(f"Error checking environment for {serial}: {e}")
            return False
    
    def get_device_by_serial(self, serial: str) -> Optional[DeviceInfo]:
        """시리얼로 디바이스 정보 조회"""
        for device in self.devices:
            if device.serial == serial:
                return device
        return None

    def get_current_device(self):
        """현재 연결된 디바이스 정보를 가져옵니다."""
        try:
            logger.info("Getting current device...")
            devices = self.discover_devices()
            if devices:
                device = devices[0]  # 첫 번째 연결된 디바이스 사용
                device_info = {
                    'serial': device.serial,
                    'model': device.model,
                    'os_version': device.os_version,
                    'status': 'connected'
                }
                logger.info(f"Current device info: {device_info}")
                return device_info
            else:
                logger.warning("No devices found")
                return None
        except Exception as e:
            logger.error(f"Error getting current device: {e}")
            return None 