import os
import glob
import subprocess
import configparser
import requests
from datetime import datetime
import shutil
import time
import yaml
from pathlib import Path
from multiprocessing import Process

# --- 단말기/OS 정보 자동 추출 ---
def get_connected_devices():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    devices = []
    for line in lines[1:]:
        if line.strip() == "":
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices

def get_device_info(serial):
    def adb(cmd):
        return subprocess.check_output(f'adb -s {serial} shell {cmd}', shell=True).decode().strip()
    model = adb('getprop ro.product.model')
    os_version = adb('getprop ro.build.version.release')
    build_id = adb('getprop ro.build.display.id')
    return model, os_version, build_id, serial

def check_environment(serial):
    # adb 연결 체크
    try:
        version = subprocess.check_output(
            f"adb -s {serial} shell dumpsys package net.cj.cjhv.gs.tving | grep versionName", shell=True
        ).decode().strip()
        print(f"[{serial}] TVING 앱 버전: {version}")
    except Exception:
        print(f"[{serial}] TVING 앱이 설치되어 있지 않거나 버전 정보를 가져올 수 없습니다.")
        return False
    return True

# --- TestRail API ---
def get_testrail_cases(config, suite_id):
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/get_cases/{project_id}&suite_id={suite_id}"
    resp = requests.get(endpoint, auth=(username, api_key))
    resp.raise_for_status()
    return resp.json()

def add_result_for_case(config, run_id, case_id, status, comment):
    url = config['url'].rstrip('/')
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/add_result_for_case/{run_id}/{case_id}"
    data = {'status_id': 1 if status == 'pass' else 5, 'comment': comment}
    resp = requests.post(endpoint, json=data, auth=(username, api_key))
    resp.raise_for_status()
    return resp.json()['id']

def add_attachment_to_result(config, result_id, filepath):
    url = config['url'].rstrip('/')
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/add_attachment_to_result/{result_id}"
    with open(filepath, 'rb') as f:
        files = {'attachment': (os.path.basename(filepath), f)}
        try:
            resp = requests.post(endpoint, files=files, auth=(username, api_key))
            resp.raise_for_status()
            print(f"[첨부 성공] {filepath}")
        except Exception as e:
            print(f"[첨부 실패] {filepath}: {e}")

# --- Maestro 실행 및 결과 처리 ---
def substitute_and_prepare_yaml(flow_path):
    """
    치환된 임시 YAML 파일 경로를 반환. {{DATE}}, {{TIME}} 치환 및 폴더 생성.
    """
    with open(flow_path, 'r', encoding='utf-8') as f:
        content = f.read()
    now = datetime.now()
    date_str = now.strftime('%Y%m%d')
    time_str = now.strftime('%H%M%S')
    content = content.replace('{{DATE}}', date_str).replace('{{TIME}}', time_str)
    # startRecording 경로 추출 및 폴더 생성
    import re
    m = re.search(r'startRecording:\s*"([^"]+)"', content)
    if m:
        rec_path = m.group(1)
        rec_dir = os.path.dirname(rec_path)
        if rec_dir and not os.path.exists(rec_dir):
            os.makedirs(rec_dir, exist_ok=True)
    # 임시 파일명
    tmp_path = flow_path.replace('.yaml', '_tmp.yaml')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return tmp_path

def run_maestro(serial, flow_path, log_path):
    today = datetime.now().strftime('%Y%m%d')
    result_today = os.path.join('result', serial, today)
    os.makedirs(result_today, exist_ok=True)
    before = set(glob.glob(os.path.join(result_today, '*.mp4')))
    # 임시 YAML 치환 등 기존 로직 유지
    if '{{DATE}}' in open(flow_path, encoding='utf-8').read() or '{{TIME}}' in open(flow_path, encoding='utf-8').read():
        tmp_path = substitute_and_prepare_yaml(flow_path)
        run_path = tmp_path
    else:
        run_path = flow_path
        tmp_path = None
    try:
        cmd = ["maestro", f"--device={serial}", "test", run_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout + '\n' + result.stderr)
        ok = result.returncode == 0
        output = result.stdout + result.stderr
    except Exception as e:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(str(e))
        ok = False
        output = str(e)
    after = set(glob.glob(os.path.join(result_today, '*.mp4')))
    new_mp4s = list(after - before)
    if tmp_path and os.path.exists(tmp_path):
        os.remove(tmp_path)
    return ok, output, new_mp4s

def validate_yaml_file(filepath):
    """
    YAML 파일 유효성 검증 (여러 문서 허용)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            list(yaml.safe_load_all(f))  # 여러 문서 허용
        return True
    except Exception as e:
        print(f"[YAML 검증 실패] {filepath}: {e}")
        return False

def find_maestro_flow(case_id):
    """
    Maestro 실행 대상 YAML 파일 매칭 로직 (sub_flows는 직접 실행 대상에서 제외)
    - 메인 폴더(maestro_flows/)만 탐색
    - 파일 중복 시 최신 파일 선택
    - YAML 유효성 검증
    - 상세 로깅
    """
    # sub_flows는 직접 실행 대상에서 제외
    search_patterns = [
        f"maestro_flows/TC{case_id}_*.yaml",           # 메인 폴더
        f"maestro_flows/TC{case_id:0>6}_*.yaml"        # 패딩된 케이스 ID
    ]
    all_matches = []
    for pattern in search_patterns:
        matches = glob.glob(pattern, recursive=True)
        # sub_flows 경로는 제외
        matches = [m for m in matches if '/sub_flows/' not in m and '\\sub_flows\\' not in m]
        all_matches.extend(matches)
    if not all_matches:
        print(f"[매칭 실패] TC{case_id}에 해당하는 YAML 파일이 없습니다.")
        return None
    # 중복 제거 및 정렬 (최신 파일 우선)
    unique_matches = list(set(all_matches))
    unique_matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    if len(unique_matches) > 1:
        print(f"[중복 파일 경고] TC{case_id}: {len(unique_matches)}개 파일 발견, 최신 파일 선택: {unique_matches[0]}")
        for i, f in enumerate(unique_matches):
            print(f"  {i+1}. {f} (수정시간: {datetime.fromtimestamp(os.path.getmtime(f))})")
    # 선택된 파일 YAML 검증
    selected_file = unique_matches[0]
    if not validate_yaml_file(selected_file):
        print(f"[YAML 검증 실패] {selected_file} - 다음 파일 시도")
        for alternative in unique_matches[1:]:
            if validate_yaml_file(alternative):
                print(f"[대체 파일 선택] {alternative}")
                return alternative
        print(f"[매칭 실패] TC{case_id} - 유효한 YAML 파일이 없습니다.")
        return None
    print(f"[매칭 성공] TC{case_id} -> {selected_file}")
    return selected_file

def find_latest_maestro_artifacts():
    base = os.path.expanduser('~/.maestro/tests')
    result_dir = 'result'
    artifacts = []
    if os.path.exists(base):
        latest = max([os.path.join(base, d) for d in os.listdir(base)], key=os.path.getmtime)
        artifacts += glob.glob(os.path.join(latest, '*.png')) + glob.glob(os.path.join(latest, '*.mp4'))
    # result 하위의 오늘 날짜 폴더 mp4도 추가
    if os.path.exists(result_dir):
        today = datetime.now().strftime('%Y%m%d')
        result_today = os.path.join(result_dir, today)
        if os.path.exists(result_today):
            artifacts += glob.glob(os.path.join(result_today, '*.mp4'))
    return artifacts

def collect_tving_logcat(duration=5):
    import time
    import os
    import subprocess
    from datetime import datetime

    os.system('adb logcat -c')
    # 날짜별 상위 폴더 생성
    today = datetime.now().strftime("%Y%m%d")
    device_name = os.popen("adb shell getprop ro.product.model").read().strip().replace(' ', '_')
    result_dir = f"result/{today}"
    os.makedirs(result_dir, exist_ok=True)
    logcat_path = f"{result_dir}/adb_{device_name}_log.txt"

    # 실시간으로 adb logcat을 읽으면서 'MediaStateObserver' 로그만 저장
    with open(logcat_path, 'w') as f:
        proc = subprocess.Popen(['adb', 'logcat'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        start_time = time.time()
        try:
            while time.time() - start_time < duration:
                line = proc.stdout.readline()
                if not line:
                    break
                if 'MediaStateObserver' in line:
                    f.write(line)
        finally:
            proc.terminate()
            proc.wait()
    return logcat_path

# 플레이어 상태 분석 함수
# 'IS PLAYING (FINAL_STATE:3)' 문자열이 있으면 OK, 없으면 FAIL로 판단
def analyze_playing_state(logcat_path):
    with open(logcat_path, 'r') as f:
        lines = f.readlines()
    if lines and 'IS PLAYING (FINAL_STATE:3)' in lines[-1].strip():
        result = 'OK'
    else:
        result = 'FAIL'
    with open('result/playing_check.txt', 'w') as f:
        f.write(result)
    return result

# 2. 리포트 자동화 함수 추가

def generate_report(results, output_path="result/test_report.md"):
    total = len(results)
    passed = sum(1 for r in results if r['status'] == 'pass')
    failed = total - passed
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 테스트 리포트\n\n")
        f.write(f"- 전체: {total}\n- 성공: {passed}\n- 실패: {failed}\n\n")
        f.write("## 상세 결과\n")
        for r in results:
            f.write(f"- [{r['status'].upper()}] {r['case_id']} : {r['title']}\n")
            if r['status'] == 'fail':
                if r['artifact']:
                    f.write(f"    - [첨부]({r['artifact']})\n")
                if r['log']:
                    f.write(f"    - [로그]({r['log']})\n")

# --- 메인 자동화 ---
def run_tests_on_device(serial, cases):
    if not check_environment(serial):
        return
    config = configparser.ConfigParser()
    config.read('config.ini')
    tr = config['TestRail']
    suite_id = tr.get('suite_id', '1787')
    run_id = subprocess.check_output('python3 scripts/create_testrail_run.py --suite_id ' + suite_id, shell=True).decode().strip()
    model, os_version, build_id, serial = get_device_info(serial)
    today = datetime.now().strftime('%Y%m%d')
    os.makedirs(f'result/{serial}/{today}', exist_ok=True)
    os.makedirs(f'logs/{serial}', exist_ok=True)
    results = []
    # 1. TC00000_앱시작.yaml 먼저 실행
    app_start_yaml = None
    for f in glob.glob('maestro_flows/TC00000_앱시작*.yaml'):
        app_start_yaml = f
        break
    if app_start_yaml:
        cmd = ["maestro", f"--device={serial}", "test", app_start_yaml]
        print(f"[{serial}] [앱시작] {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr)
        status = 'fail'
        if '[Passed]' in result.stdout + result.stderr or result.returncode == 0:
            status = 'pass'
        add_result_for_case(tr, run_id, '00000', status, f"[{'성공' if status == 'pass' else '실패'}] 단말기: {serial}")
        if status == 'fail':
            print(f"[{serial}] [중단] 앱시작 실패. 이후 케이스 실행 중단.")
            return
    else:
        print(f"[{serial}] [오류] TC00000_앱시작.yaml 파일을 찾을 수 없습니다.")
        return
    # 2. TestRail 케이스 순차 실행
    for case in cases:
        case_id = case['id']
        title = case.get('title', '')
        yaml_path = find_maestro_flow(case_id)
        if not yaml_path:
            print(f"[{serial}] [스킵] Maestro 스크립트 파일이 없습니다: TC{case_id}")
            continue
        cmd = ["maestro", f"--device={serial}", "test", yaml_path]
        print(f"[{serial}] [실행] TC{case_id} {title} : {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr)
        status = 'fail'
        if '[Passed]' in result.stdout + result.stderr or result.returncode == 0:
            status = 'pass'
        add_result_for_case(tr, run_id, case_id, status, f"[{'성공' if status == 'pass' else '실패'}] 단말기: {serial}")
        if status == 'fail':
            print(f"[{serial}] [중단] TC{case_id} 실패. 이후 케이스 실행 중단.")
            return
    print(f"[{serial}] [INFO] 모든 케이스 순차 실행 및 결과 업로드 완료.")

def get_device_info_by_serial(serial):
    def adb(cmd):
        return subprocess.check_output(f'adb -s {serial} shell {cmd}', shell=True).decode().strip()
    model = adb('getprop ro.product.model')
    os_version = adb('getprop ro.build.version.release')
    build_id = adb('getprop ro.build.display.id')
    build_code = adb('dumpsys package net.cj.cjhv.gs.tving | grep versionCode | awk -F"=" \'{print $2}\'')
    return model, os_version, build_id, build_code, serial

def get_tving_app_version(serial):
    try:
        version = subprocess.check_output(
            f"adb -s {serial} shell dumpsys package net.cj.cjhv.gs.tving | grep versionName",
            shell=True
        ).decode().strip()
        # versionName=25.23.01
        if 'versionName=' in version:
            return version.split('versionName=')[-1]
        return version
    except Exception:
        return 'unknown'

def extract_maestro_error_log(serial, case_id):
    today = datetime.now().strftime('%Y%m%d')
    log_path = os.path.join('logs', serial, f'maestro_TC{case_id}.log')
    if not os.path.exists(log_path):
        return ''
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    error_lines = [l.strip() for l in lines if 'FAILED' in l or 'Error' in l]
    if error_lines:
        return '\n'.join(error_lines)
    # fallback: 마지막 10줄
    return ''.join(lines[-10:]).strip()

def main():
    devices = get_connected_devices()
    N = len(devices)
    if N < 1:
        print("연결된 단말기가 없습니다.")
        return
    # TestRail 케이스 리스트
    config = configparser.ConfigParser()
    config.read('config.ini')
    tr = config['TestRail']
    suite_id = tr.get('suite_id', '1787')
    # run_id를 한 번만 생성
    run_id = subprocess.check_output('python3 scripts/create_testrail_run.py --suite_id ' + suite_id, shell=True).decode().strip()
    testrail_cases = get_testrail_cases(tr, suite_id)
    if isinstance(testrail_cases, dict) and 'cases' in testrail_cases:
        testrail_cases = testrail_cases['cases']
    # 1. TC00000_앱시작.yaml을 항상 shard-all로 먼저 실행 (TestRail 업로드 X)
    app_start_yaml = None
    for f in glob.glob('maestro_flows/TC00000_앱시작*.yaml'):
        app_start_yaml = f
        break
    if app_start_yaml:
        # 템플릿 치환
        with open(app_start_yaml, encoding='utf-8') as f:
            content = f.read()
        if '{{DATE}}' in content or '{{TIME}}' in content:
            app_start_yaml = substitute_and_prepare_yaml(app_start_yaml)
        cmd = ["maestro", "test", "--shard-all", str(N), app_start_yaml]
        print(f"[앱시작] {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr)
        import re
        shard_results = re.findall(r'\[shard (\d+)\] \[(Passed|Failed)\]', result.stdout + result.stderr)
        serials = devices
        failed = False
        for i, serial in enumerate(serials):
            status = 'fail'
            for shard_num, res in shard_results:
                if int(shard_num) == i+1:
                    status = 'pass' if res == 'Passed' else 'fail'
            if status == 'fail':
                print(f"[중단] {serial}에서 앱시작 실패. 이후 케이스 실행 중단.")
                failed = True
        if failed:
            return
    else:
        print("[오류] TC00000_앱시작.yaml 파일을 찾을 수 없습니다.")
        return
    # 2. TestRail 케이스들을 shard-all로 실행 및 결과 업로드 (코멘트에 단말기별 결과 모두 남기기, 실패시 첨부)
    for case in testrail_cases:
        case_id = case['id']
        title = case.get('title', '')
        yaml_path = find_maestro_flow(case_id)
        if not yaml_path:
            print(f"[스킵] Maestro 스크립트 파일이 없습니다: TC{case_id}")
            continue
        # 템플릿 치환
        with open(yaml_path, encoding='utf-8') as f:
            content = f.read()
        if '{{DATE}}' in content or '{{TIME}}' in content:
            yaml_path = substitute_and_prepare_yaml(yaml_path)
        cmd = ["maestro", "test", "--shard-all", str(N), yaml_path]
        print(f"[실행] TC{case_id} {title} : {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr)
        import re
        # shard별 결과 및 로그 분리
        shard_results = re.findall(r'\[shard (\d+)\] \[(Passed|Failed)\](.*)', result.stdout + result.stderr)
        # shard별 로그 분리 (shard 헤더 기준으로 분리)
        shard_log_splits = re.split(r'(\[shard \d+\] \[(?:Passed|Failed)\])', result.stdout + result.stderr)
        # shard_log_splits: ['', '[shard 1] [Passed]', ' ...log... ', '[shard 2] [Failed]', ' ...log... ', ...]
        # => (헤더, 로그) 쌍으로 묶기
        shard_logs = []
        for i in range(1, len(shard_log_splits), 2):
            header = shard_log_splits[i]
            log = shard_log_splits[i+1] if i+1 < len(shard_log_splits) else ''
            shard_logs.append(header + '\n' + log)
        serials = devices
        comment_lines = []
        overall_status = 'pass'
        attachments = []
        today = datetime.now().strftime('%Y%m%d')
        for i, serial in enumerate(serials):
            model, os_version, build_id, _, serial = get_device_info_by_serial(serial)
            tving_version = get_tving_app_version(serial)
            status = 'fail'
            result_dir = os.path.join('result', serial, today)
            os.makedirs(result_dir, exist_ok=True)
            # 1. 실행 전 파일 목록
            before_files = set(os.listdir(result_dir)) if os.path.exists(result_dir) else set()
            for shard_num, res, extra in shard_results:
                if int(shard_num) == i+1:
                    status = 'pass' if res == 'Passed' else 'fail'
            # shard별 로그 저장
            log_dir = os.path.join('logs', serial)
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f'maestro_TC{case_id}.log')
            if i < len(shard_logs):
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(shard_logs[i].strip())
            # 2. 실행 후 파일 목록
            after_files = set(os.listdir(result_dir)) if os.path.exists(result_dir) else set()
            new_files = after_files - before_files
            if status == 'pass':
                comment_lines.append(f"[성공] 단말기: {model} ({serial}), OS: {os_version}, 빌드: {tving_version}")
            else:
                error_log = extract_maestro_error_log(serial, case_id)
                comment_lines.append(f"[실패] 단말기: {model} ({serial}), OS: {os_version}, 빌드: {tving_version}, 오류코드: {error_log}")
                # 실패시 첨부파일(mp4, png) - 새로 생성된 파일만 첨부
                for f in new_files:
                    if f.endswith('.mp4') or f.endswith('.png'):
                        attachments.append(os.path.join(result_dir, f))
            if status == 'fail':
                overall_status = 'fail'
        comment = '\n'.join(comment_lines)
        result_id = add_result_for_case(tr, run_id, case_id, overall_status, comment)
        # 실패시 첨부파일 업로드
        for filepath in attachments:
            add_attachment_to_result(tr, result_id, filepath)
    print("[INFO] 모든 케이스 shard-all 병렬 실행 및 결과 업로드 완료.")

if __name__ == '__main__':
    main() 