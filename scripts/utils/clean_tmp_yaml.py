import os
import glob

# 삭제 대상 경로
TARGET_DIR = "maestro_flows"

# *_tmp.yaml 파일 모두 찾기
pattern = os.path.join(TARGET_DIR, "**", "*_tmp.yaml")
tmp_files = glob.glob(pattern, recursive=True)

if not tmp_files:
    print("[INFO] 삭제할 임시파일이 없습니다.")
else:
    for f in tmp_files:
        try:
            os.remove(f)
            print(f"[DELETE] {f}")
        except Exception as e:
            print(f"[ERROR] {f} 삭제 실패: {e}")
    print(f"[INFO] 총 {len(tmp_files)}개 임시파일 삭제 완료.") 