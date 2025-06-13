import subprocess
import time
import os
import configparser
import sys
from datetime import datetime

def get_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

config = get_config()
PACKAGE_NAME = config['App']['package_name']
LOG_FILE = "result/tving_logcat.txt"

# result 폴더가 없으면 생성
os.makedirs("result", exist_ok=True)

# logcat 초기화
subprocess.run("adb logcat -c", shell=True)

# 10초간 logcat 수집 (tving 패키지 로그만)
with open(LOG_FILE, "w") as f:
    proc = subprocess.Popen(
        f'adb logcat | grep "{PACKAGE_NAME}"',
        shell=True,
        stdout=subprocess.PIPE,
        text=True
    )
    start = time.time()
    while time.time() - start < 10:
        line = proc.stdout.readline()
        if not line:
            break
        f.write(line)
    proc.terminate()

def get_tving_pid(serial):
    """TVING 앱의 현재 프로세스 ID 조회"""
    cmd = f"adb -s {serial} shell ps | grep net.cj.cjhv.gs.tving"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        # ps 출력에서 PID 추출 (두 번째 컬럼)
        pid = result.stdout.split()[1]
        return pid
    return None

def save_tving_logcat(serial, output_dir=None):
    """TVING 앱의 로그캣 저장"""
    if output_dir is None:
        today = datetime.now().strftime("%Y%m%d")
        output_dir = f"result/{serial}/{today}"
    
    os.makedirs(output_dir, exist_ok=True)
    output_file = f"{output_dir}/adb_{serial}_log.txt"
    
    # TVING 프로세스 ID 조회
    pid = get_tving_pid(serial)
    if not pid:
        print(f"TVING 프로세스를 찾을 수 없습니다 (serial: {serial})")
        return None
    
    # 이전 로그 클리어
    subprocess.run(f"adb -s {serial} logcat -c", shell=True)
    
    # 로그캣 수집 (TVING 프로세스의 로그만)
    cmd = f"adb -s {serial} logcat --pid={pid} *:I > {output_file}"
    
    try:
        # 백그라운드에서 로그캣 수집 시작
        process = subprocess.Popen(cmd, shell=True)
        
        # 10초 동안 로그 수집
        time.sleep(10)
        
        # 프로세스 종료
        process.terminate()
        process.wait()
        
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            print(f"로그캣 저장 완료: {output_file}")
            return output_file
        else:
            print(f"로그캣 파일이 비어있습니다: {output_file}")
            return None
            
    except Exception as e:
        print(f"로그캣 수집 중 오류 발생: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python save_tving_log.py <serial>")
        sys.exit(1)
    
    serial = sys.argv[1]
    save_tving_logcat(serial)