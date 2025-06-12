import subprocess
from multiprocessing import Process

# adb devices 명령어로 연결된 단말기 serial 자동 추출
def get_connected_devices():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    devices = []
    for line in lines[1:]:  # 첫 줄은 헤더
        if line.strip() == "":
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices

# 테스트할 Maestro YAML 파일 경로
YAML_PATH = "maestro_flows/TC00000_앱시작.yaml"  # 필요시 경로/파일명 수정


def run_maestro(device_serial, yaml_path):
    # 기본 사용자(user 0)로 전환
    try:
        subprocess.run(["adb", "-s", device_serial, "shell", "am", "switch-user", "0"], check=True)
        print(f"[INFO] {device_serial} 기본 사용자(user 0)로 전환 완료.")
    except Exception as e:
        print(f"[WARN] {device_serial} 사용자 전환 실패: {e}")
    cmd = [
        "maestro", f"--device={device_serial}", "test", yaml_path
    ]
    print(f"[INFO] {device_serial}에서 테스트 시작...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"[RESULT] {device_serial} 결과:")
    print(result.stdout)
    if result.stderr:
        print(f"[ERROR] {device_serial} stderr:")
        print(result.stderr)


def main():
    devices = get_connected_devices()
    if not devices:
        print("[ERROR] 연결된 단말기가 없습니다. adb devices로 연결 상태를 확인하세요.")
        return
    print(f"[INFO] 연결된 단말기: {devices}")
    procs = []
    for serial in devices:
        p = Process(target=run_maestro, args=(serial, YAML_PATH))
        p.start()
        procs.append(p)
    for p in procs:
        p.join()
    print("[INFO] 모든 단말기 테스트 완료.")


if __name__ == "__main__":
    main() 