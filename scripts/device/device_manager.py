from typing import List, Optional
import subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass
class DeviceInfo:
    serial: str
    model: str
    os_version: str
    build_id: str
    tving_version: str

class DeviceManager:
    def __init__(self):
        self.devices: List[DeviceInfo] = []
    
    def discover_devices(self) -> List[DeviceInfo]:
        """연결된 디바이스들을 발견하고 정보를 수집"""
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        devices = []
        
        for line in result.stdout.strip().splitlines()[1:]:
            if 'device' in line and not line.startswith('*'):
                serial = line.split()[0]
                device_info = self._get_device_info(serial)
                if device_info:
                    devices.append(device_info)
        
        self.devices = devices
        return devices
    
    def _get_device_info(self, serial: str) -> Optional[DeviceInfo]:
        """개별 디바이스 정보 수집"""
        try:
            model = self._adb_shell(serial, 'getprop ro.product.model')
            os_version = self._adb_shell(serial, 'getprop ro.build.version.release')
            build_id = self._adb_shell(serial, 'getprop ro.build.display.id')
            tving_version = self._get_tving_version(serial)
            
            return DeviceInfo(serial, model, os_version, build_id, tving_version)
        except Exception as e:
            print(f"디바이스 정보 수집 실패: {serial} - {e}")
            return None
    
    def _adb_shell(self, serial: str, command: str) -> str:
        """ADB shell 명령 실행"""
        return subprocess.check_output(
            f'adb -s {serial} shell {command}', 
            shell=True
        ).decode().strip()
    
    def _get_tving_version(self, serial: str) -> str:
        """TVING 앱 버전 조회"""
        try:
            version = subprocess.check_output(
                f"adb -s {serial} shell dumpsys package net.cj.cjhv.gs.tving | grep versionName",
                shell=True
            ).decode().strip()
            return version
        except:
            return "Unknown"
    
    def check_environment(self, serial: str) -> bool:
        """디바이스 환경 체크"""
        try:
            # TVING 앱 설치 여부 확인
            packages = self._adb_shell(serial, 'pm list packages')
            if 'net.cj.cjhv.gs.tving' not in packages:
                return False
            return True
        except:
            return False
    
    def get_device_by_serial(self, serial: str) -> Optional[DeviceInfo]:
        """시리얼로 디바이스 정보 조회"""
        for device in self.devices:
            if device.serial == serial:
                return device
        return None 