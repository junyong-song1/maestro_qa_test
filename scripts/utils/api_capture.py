import os
import sqlite3
from mitmproxy import io
from mitmproxy.exceptions import FlowReadException

DB_PATH = "artifacts/test_log.db"
API_TABLE = "test_api"

def ensure_api_table():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        cur = conn.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0]
        if mode.lower() != "wal":
            try:
                conn.execute('PRAGMA journal_mode=WAL;')
            except sqlite3.OperationalError:
                pass  # locked 등 오류 발생 시 무시
    except Exception:
        pass
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {API_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_case_id TEXT,
            serial TEXT,
            model TEXT,
            os_version TEXT,
            tving_version TEXT,
            timestamp TEXT,
            url TEXT,
            method TEXT,
            status_code INTEGER,
            elapsed REAL,
            request_body TEXT,
            response_body TEXT,
            run_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def parse_mitmproxy_dump(dump_path, test_case_id, serial, model, os_version, tving_version, timestamp, run_id=None):
    ensure_api_table()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    # WAL 모드 재설정은 생략 (ensure_api_table에서만 시도)
    cursor = conn.cursor()
    
    processed_count = 0
    error_count = 0
    
    # 방법 1: mitmproxy io.FlowReader 사용
    try:
        with open(dump_path, "rb") as logfile:
            freader = io.FlowReader(logfile)
            try:
                for flow in freader.stream():
                    if flow.request and flow.response:
                        url = flow.request.pretty_url
                        # tving.com 도메인만 저장
                        if "tving.com" not in url:
                            continue
                        method = flow.request.method
                        status_code = flow.response.status_code
                        # timestamp_end 또는 timestamp_start가 None이면 None 처리
                        if flow.response.timestamp_end is not None and flow.request.timestamp_start is not None:
                            elapsed = flow.response.timestamp_end - flow.request.timestamp_start
                        else:
                            elapsed = None
                        request_body = flow.request.get_text(strict=False)
                        response_body = flow.response.get_text(strict=False)
                        # 인코딩 에러 방지: 유니코드 치환 및 예외 처리
                        try:
                            if request_body is not None:
                                request_body = request_body.encode('utf-8', 'replace').decode('utf-8', 'replace')
                        except Exception:
                            request_body = '[ENCODING ERROR]'
                        try:
                            if response_body is not None:
                                response_body = response_body.encode('utf-8', 'replace').decode('utf-8', 'replace')
                        except Exception:
                            response_body = '[ENCODING ERROR]'
                        
                        try:
                            cursor.execute(f"""
                                INSERT INTO {API_TABLE} (test_case_id, serial, model, os_version, tving_version, timestamp, url, method, status_code, elapsed, request_body, response_body, run_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (test_case_id, serial, model, os_version, tving_version, timestamp, url, method, status_code, elapsed, request_body, response_body, run_id))
                            processed_count += 1
                        except Exception as e:
                            error_count += 1
                            print(f"DB 저장 오류 (URL: {url}): {e}")
                            
            except FlowReadException as e:
                print(f"[mitmproxy] FlowReadException: {e}")
                print(f"방법 1 실패 - 방법 2 시도 중...")
                # 방법 1 실패 시 방법 2로 전환
                raise e
            except Exception as e:
                print(f"예상치 못한 오류: {e}")
                print(f"방법 1 실패 - 방법 2 시도 중...")
                raise e
    except Exception as e:
        print(f"방법 1 실패: {e}")
        # 방법 2: 텍스트 기반 파싱 (대체 방법)
        print(f"방법 2: 텍스트 기반 파싱 시작...")
        try:
            with open(dump_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # tving.com URL 패턴 찾기
            import re
            tving_urls = re.findall(r'https?://[^,\s]+tving\.com[^,\s]*', content)
            
            for url in tving_urls:
                try:
                    # 간단한 정보 추출
                    method_match = re.search(r'method;(\d+):([A-Z]+)', content)
                    method = method_match.group(2) if method_match else "GET"
                    
                    status_match = re.search(r'status_code;(\d+):(\d+)', content)
                    status_code = int(status_match.group(2)) if status_match else 200
                    
                    cursor.execute(f"""
                        INSERT INTO {API_TABLE} (test_case_id, serial, model, os_version, tving_version, timestamp, url, method, status_code, elapsed, request_body, response_body, run_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (test_case_id, serial, model, os_version, tving_version, timestamp, url, method, status_code, None, None, None, run_id))
                    processed_count += 1
                except Exception as e:
                    error_count += 1
                    print(f"방법 2 DB 저장 오류 (URL: {url}): {e}")
                    
        except Exception as e:
            print(f"방법 2도 실패: {e}")
    
    conn.commit()
    conn.close()
    print(f"API 캡처 완료: 총 {processed_count}건 저장, {error_count}건 오류")

if __name__ == "__main__":
    # 예시 실행: python api_capture.py dump_file test_case_id serial model os_version tving_version timestamp [run_id]
    import sys
    if len(sys.argv) < 8:
        print("Usage: python api_capture.py <mitmproxy_dump_file> <test_case_id> <serial> <model> <os_version> <tving_version> <timestamp> [run_id]")
        exit(1)
    
    # run_id는 선택적 매개변수
    run_id = sys.argv[8] if len(sys.argv) > 8 else None
    parse_mitmproxy_dump(*sys.argv[1:8], run_id) 