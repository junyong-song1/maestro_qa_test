import os
import time
import shutil

TARGET_DIRS = ["logs", "result"]
DAYS = 7  # 7일 이상 지난 파일/폴더 삭제
now = time.time()

for base_dir in TARGET_DIRS:
    if not os.path.exists(base_dir):
        continue
    for root, dirs, files in os.walk(base_dir):
        # 파일 삭제
        for f in files:
            path = os.path.join(root, f)
            try:
                # 빈 파일이거나, 7일 이상 경과
                if os.path.getsize(path) == 0 or now - os.path.getmtime(path) > DAYS * 86400:
                    os.remove(path)
                    print(f"[DELETE] {path}")
            except Exception as e:
                print(f"[ERROR] 파일 삭제 실패: {path} - {e}")
        # 빈 폴더 삭제 (하위 파일/폴더 삭제 후에만)
        for d in dirs:
            dir_path = os.path.join(root, d)
            try:
                if not os.listdir(dir_path):
                    shutil.rmtree(dir_path)
                    print(f"[DELETE] 빈 폴더: {dir_path}")
            except Exception as e:
                print(f"[ERROR] 폴더 삭제 실패: {dir_path} - {e}") 