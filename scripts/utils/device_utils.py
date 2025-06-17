import subprocess
import configparser

def get_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

# 연결된 단말기 serial 리스트 반환
def get_connected_devices():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()[1:]
    serials = [line.split()[0] for line in lines if 'device' in line and not line.startswith('*')]
    return serials

# 단말기 정보(모델명, OS, 빌드 등) 반환
def get_device_info(serial):
    def adb_shell(cmd):
        result = subprocess.run(["adb", "-s", serial, "shell"] + cmd, capture_output=True, text=True)
        return result.stdout.strip()
    model = adb_shell(["getprop", "ro.product.model"])
    os_version = adb_shell(["getprop", "ro.build.version.release"])
    build = adb_shell(["getprop", "ro.build.display.id"])
    return {
        "serial": serial,
        "model": model,
        "os_version": os_version,
        "build": build
    }

# 여러 단말기 정보 리스트 반환
def get_all_device_infos():
    serials = get_connected_devices()
    return [get_device_info(s) for s in serials]

# 단말기 환경 체크(ADB 연결, 앱 설치/버전 등)
def check_environment(serial):
    config = get_config()
    package_name = config['App']['package_name']
    
    def adb_shell(cmd):
        result = subprocess.run(["adb", "-s", serial, "shell"] + cmd, capture_output=True, text=True)
        return result.stdout.strip()
    # 앱 설치 여부
    packages = adb_shell(["pm", "list", "packages"])
    if package_name not in packages:
        return False, f"[ERROR] {serial}: 앱 미설치"
    # 앱 버전
    version = adb_shell(["dumpsys", "package", package_name, "|", "grep", "versionName"])
    return True, version 