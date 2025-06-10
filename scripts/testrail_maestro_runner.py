import os
import glob
import subprocess
import configparser
import requests
from datetime import datetime
import shutil
import time

# --- 단말기/OS 정보 자동 추출 ---
def get_device_info():
    def adb(cmd):
        return subprocess.check_output(cmd, shell=True).decode().strip()
    model = adb('adb shell getprop ro.product.model')
    os_version = adb('adb shell getprop ro.build.version.release')
    build_id = adb('adb shell getprop ro.build.display.id')
    serial = adb("adb devices -l | grep 'device ' | awk '{print $1}'")
    return model, os_version, build_id, serial

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

def run_maestro(flow_path, log_path):
    # 실행 전 result/오늘날짜 mp4 목록
    today = datetime.now().strftime('%Y%m%d')
    result_today = os.path.join('result', today)
    before = set(glob.glob(os.path.join(result_today, '*.mp4')))
    # --- 추가: YAML 치환 및 폴더 생성 ---
    if '{{DATE}}' in open(flow_path, encoding='utf-8').read() or '{{TIME}}' in open(flow_path, encoding='utf-8').read():
        tmp_path = substitute_and_prepare_yaml(flow_path)
        run_path = tmp_path
    else:
        run_path = flow_path
        tmp_path = None
    try:
        result = subprocess.run(["maestro", "test", run_path], capture_output=True, text=True, timeout=300)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout + '\n' + result.stderr)
        ok = result.returncode == 0
        output = result.stdout + result.stderr
    except Exception as e:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(str(e))
        ok = False
        output = str(e)
    # 실행 후 mp4 목록
    after = set(glob.glob(os.path.join(result_today, '*.mp4')))
    new_mp4s = list(after - before)
    # 임시 파일 삭제
    if tmp_path and os.path.exists(tmp_path):
        os.remove(tmp_path)
    return ok, output, new_mp4s

def find_maestro_flow(case_id):
    files = glob.glob(f"maestro_flows/TC{case_id}_*.yaml")
    return files[0] if files else None

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

# --- 메인 자동화 ---
def main():
    config = configparser.ConfigParser()
    config.read('config.ini')
    tr = config['TestRail']
    suite_id = tr.get('suite_id', '1787')
    run_id = subprocess.check_output('python3 scripts/create_testrail_run.py --suite_id ' + suite_id, shell=True).decode().strip()
    model, os_version, build_id, serial = get_device_info()
    cases = get_testrail_cases(tr, suite_id)
    # result/오늘날짜 폴더 생성
    today = datetime.now().strftime('%Y%m%d')
    os.makedirs(f'result/{today}', exist_ok=True)
    if isinstance(cases, dict) and 'cases' in cases:
        cases = cases['cases']

    # 1. Always run TC00000_앱시작.yaml first (if exists)
    app_start_path = None
    for f in glob.glob('maestro_flows/TC00000_앱시작*.yaml'):
        app_start_path = f
        break
    already_run_ids = set()
    if app_start_path:
        print(f"[실행] {app_start_path} (앱시작)")
        ok, output, new_mp4s = run_maestro(app_start_path, 'logs/maestro_TC00000_앱시작.log')
        already_run_ids.add('00000')
        if not ok:
            print(f"[실패] {app_start_path} (앱시작)")
            # 앱시작 실패 시 전체 중단
            return
        else:
            print(f"[성공] {app_start_path} (앱시작)")

    # 2. Then run TestRail suite cases in order, skipping TC00000 if present
    for case in cases:
        case_id = str(case['id'])
        if case_id == '00000' or case_id in already_run_ids:
            continue
        flow_path = find_maestro_flow(case_id)
        log_path = f'logs/maestro_TC{case_id}.log'
        
        
        if flow_path:
            print(f"[실행] {flow_path}")
            ok, output, new_mp4s = run_maestro(flow_path, log_path)

            # TC313859, TC313889일 경우 플레이어 상태 분석
            if case_id in ['313859', '313889']:
                # 모든 케이스에서 logcat 체크 및 로그 저장
                logcat_path = collect_tving_logcat()
                analyze_playing_state(logcat_path)

            # --- 빌드 정보 추출 ---
            def get_app_build_info(package_name):
                output = subprocess.check_output(
                    f"adb shell dumpsys package {package_name} | grep version", shell=True
                ).decode()
                version_code = None
                version_name = None
                for line in output.splitlines():
                    if "versionCode" in line:
                        version_code = line.split('=')[1].split()[0]
                    if "versionName" in line:
                        version_name = line.split('=')[1].strip()
                return version_code, version_name
            version_code, version_name = get_app_build_info("net.cj.cjhv.gs.tving")
            build_info = f"빌드: {version_name} (code: {version_code})"

            if ok:
                print(f"[성공] {flow_path}")
                comment = f"[성공] 단말기: {model} ({serial}), OS: {os_version}, {build_info}"
                add_result_for_case(tr, run_id, case_id, 'pass', comment)
            else:
                print(f"[실패] {flow_path}")
                error_code = next((line for line in output.splitlines() if 'FAILED' in line or 'Error' in line), 'Unknown')
                comment = f"[실패] 단말기: {model} ({serial}), OS: {os_version}, {build_info}, 오류코드: {error_code}"
                result_id = add_result_for_case(tr, run_id, case_id, 'fail', comment)
                artifacts = find_latest_maestro_artifacts()
                # 새로 생성된 mp4만 첨부
                for artifact in artifacts:
                    if artifact.endswith('.mp4') and artifact not in new_mp4s:
                        continue
                    add_attachment_to_result(tr, result_id, artifact)
                break  # 실패 시 루프 종료
        else:
            print(f"[스킵] Maestro 스크립트 파일이 없습니다: TC{case_id}")
            comment = f"[실패] Maestro 스크립트 파일이 없습니다. (TC{case_id})"
            add_result_for_case(tr, run_id, case_id, 'fail', comment)

if __name__ == '__main__':
    main() 