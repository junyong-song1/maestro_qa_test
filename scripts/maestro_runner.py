import os
import subprocess
import datetime
import glob

# {{DATE}}, {{TIME}} 치환 및 임시파일 생성
def substitute_and_prepare_yaml(flow_path):
    date_str = datetime.datetime.now().strftime('%Y%m%d')
    time_str = datetime.datetime.now().strftime('%H%M%S')
    tmp_path = flow_path.replace('.yaml', '_tmp.yaml')
    with open(flow_path, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('{{DATE}}', date_str).replace('{{TIME}}', time_str)
    # startRecording 라인에 .mp4 붙이기
    content = content.replace('startRecording: "', 'startRecording: "').replace('"', '.mp4"', 1) if 'startRecording:' in content else content
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return tmp_path, date_str, time_str

# Maestro 실행 래퍼 (shard-all 지원)
def run_maestro(flow_path, device_serial=None, shard_all=False, log_path=None):
    cmd = ["maestro", "test"]
    if shard_all:
        cmd.append("--shard-all")
    if device_serial:
        cmd += ["--device", device_serial]
    cmd.append(flow_path)
    if log_path:
        with open(log_path, 'w', encoding='utf-8') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    else:
        result = subprocess.run(cmd)
    return result.returncode

# Maestro 로그 결과 파싱 (성공/실패, 에러 메시지 등)
def parse_maestro_result(log_path):
    if not os.path.exists(log_path):
        return False, "[NO LOG] 로그 파일 없음"
    with open(log_path, 'r', encoding='utf-8') as f:
        log = f.read()
    if 'Test execution completed successfully' in log or 'All tests passed' in log:
        return True, "SUCCESS"
    # Maestro 에러 메시지 추출
    for line in log.splitlines():
        if 'Exception' in line or 'Error' in line:
            return False, line.strip()
    return False, "[FAIL] 상세 원인 미상"

# *_tmp.yaml 임시파일 삭제
def clean_tmp_yaml():
    pattern = os.path.join("maestro_flows", "**", "*_tmp.yaml")
    tmp_files = glob.glob(pattern, recursive=True)
    for f in tmp_files:
        try:
            os.remove(f)
            print(f"[DELETE] {f}")
        except Exception as e:
            print(f"[ERROR] {f} 삭제 실패: {e}") 