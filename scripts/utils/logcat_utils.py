import os
import subprocess
import sqlite3

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

# def save_logcat(serial, case_id, timestamp, model=None, os_version=None, tving_version=None, base_dir="artifacts/result"):
#     """
#     디바이스별/케이스별/타임스탬프별로 logcat 전체 로그를 저장합니다.
#     주요 키워드 자동 분석 및 DB 저장도 수행합니다.
#     :param serial: ADB 디바이스 시리얼
#     :param case_id: 테스트 케이스 ID (문자열)
#     :param timestamp: 실행 시각(YYYYMMDD_HHMM 등)
#     :param model, os_version, tving_version: 단말 정보
#     :param base_dir: 로그 저장 루트 디렉토리
#     :return: 저장된 logcat 파일 경로
#     """
#     out_dir = os.path.join(base_dir, serial, timestamp)
#     ensure_dir(out_dir)
#     log_path = os.path.join(out_dir, f"logcat_TC{case_id}.txt")
#     # logcat 버퍼 클리어(선택)
#     subprocess.run(["adb", "-s", serial, "logcat", "-c"])
#     # 전체 로그 저장 (필터 없이)
#     with open(log_path, "w", encoding="utf-8") as f:
#         subprocess.run([
#             "adb", "-s", serial, "logcat", "-v", "time", "-d"
#         ], stdout=f)
#     print(f"[{serial}] 전체 logcat 저장 완료: {log_path}")
#     # 주요 키워드 자동 분석
#     analyze_logcat_keywords(log_path, out_dir, case_id)
#     # DB에 logcat 저장
#     with open(log_path, "r", encoding="utf-8") as f:
#         logcat_text = f.read()
#     conn = sqlite3.connect("artifacts/test_log.db")
#     cursor = conn.cursor()
#     cursor.execute("""
#         CREATE TABLE IF NOT EXISTS test_logcat (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             test_case_id TEXT,
#             serial TEXT,
#             model TEXT,
#             os_version TEXT,
#             tving_version TEXT,
#             timestamp TEXT,
#             logcat_text TEXT,
#             created_at DATETIME DEFAULT CURRENT_TIMESTAMP
#         )
#     """)
#     cursor.execute("""
#         INSERT INTO test_logcat (test_case_id, serial, model, os_version, tving_version, timestamp, logcat_text)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#     """, (case_id, serial, model, os_version, tving_version, timestamp, logcat_text))
#     conn.commit()
#     conn.close()
#     return log_path

# def analyze_logcat_keywords(log_path, out_dir, case_id):
#     keywords = [
#         "FATAL EXCEPTION", "ANR in", "Not responding", "java.lang.Exception",
#         "OMX", "MediaCodec", "NuPlayer", "ExoPlayer", "crash", "error"
#     ]
#     found = []
#     with open(log_path, "r", encoding="utf-8") as f:
#         for line in f:
#             if any(k in line for k in keywords):
#                 found.append(line)
#     if found:
#         result_path = os.path.join(out_dir, f"logcat_TC{case_id}_keywords.txt")
#         with open(result_path, "w", encoding="utf-8") as f:
#             f.writelines(found)
#         print(f"[logcat] 주요 키워드 감지: {result_path}")

# def save_logcat_tail(log_path, out_dir, case_id, tail_lines=200):
#     with open(log_path, "r", encoding="utf-8") as f:
#         lines = f.readlines()
#     tail_path = os.path.join(out_dir, f"logcat_TC{case_id}_tail.txt")
#     with open(tail_path, "w", encoding="utf-8") as f:
#         f.writelines(lines[-tail_lines:])
#     print(f"[logcat] tail 저장: {tail_path}") 