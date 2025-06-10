import subprocess
import time
import os

PACKAGE_NAME = "net.cj.cjhv.gs.tving"
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