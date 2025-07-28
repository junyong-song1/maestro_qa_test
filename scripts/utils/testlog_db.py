import sqlite3
import time
from datetime import datetime
from typing import Optional

DB_PATH = "artifacts/test_log.db"

def get_db_connection(db_path: str = DB_PATH):
    """데이터베이스 연결을 반환합니다."""
    return sqlite3.connect(db_path)

def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS test_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_case_id TEXT,
        step_name TEXT,
        start_time DATETIME,
        end_time DATETIME,
        elapsed REAL,
        status TEXT,
        error_msg TEXT,
        serial TEXT,
        model TEXT,
        os_version TEXT,
        tving_version TEXT
    )
    """)
    conn.commit()
    conn.close()

def log_step(
    test_case_id: str,
    step_name: str,
    status: str,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    error_msg: Optional[str] = None,
    serial: Optional[str] = None,
    model: Optional[str] = None,
    os_version: Optional[str] = None,
    tving_version: Optional[str] = None,
    db_path: str = DB_PATH
):
    if start_time is None:
        start_time = time.time()
    if end_time is None:
        end_time = time.time()
    elapsed = end_time - start_time
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO test_log (test_case_id, step_name, start_time, end_time, elapsed, status, error_msg, serial, model, os_version, tving_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            test_case_id,
            step_name,
            datetime.fromtimestamp(start_time),
            datetime.fromtimestamp(end_time),
            elapsed,
            status,
            error_msg,
            serial,
            model,
            os_version,
            tving_version
        )
    )
    conn.commit()
    conn.close()

def get_step_stats(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT step_name, COUNT(*), AVG(elapsed) FROM test_log GROUP BY step_name")
    rows = c.fetchall()
    conn.close()
    return rows

def get_longest_steps(limit: int = 10, db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT * FROM test_log ORDER BY elapsed DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_failures(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT * FROM test_log WHERE status='fail'")
    rows = c.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    # 예시: DB 초기화 및 샘플 로그 기록
    init_db()
    log_step("TC00001", "로그인", "success", serial="emulator-5554", model="Pixel 5", os_version="12", tving_version="7.0.0")
    log_step("TC00001", "프로필 전환", "fail", error_msg="Element not found", serial="emulator-5554", model="Pixel 5", os_version="12", tving_version="7.0.0")
    print("단계별 통계:", get_step_stats())
    print("가장 오래 걸린 단계:", get_longest_steps())
    print("실패 단계:", get_failures()) 