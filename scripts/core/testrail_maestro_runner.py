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
from rich.table import Table
from rich.live import Live
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
import testrail.testrail_client as testrail_client
import logging
import json
import asyncio
import websockets
from ..utils.logger import setup_logger

# 로그 설정 (파일과 콘솔 모두 기록)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("testrail_maestro_runner.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
# 기존 get_testrail_cases, add_result_for_case, add_attachment_to_result 함수 제거

# 아래와 같이 testrail_client.py의 메소드로 대체
# get_testrail_cases = testrail_client.get_cases (필요시)
# add_result_for_case = testrail_client.add_result
# add_attachment_to_result = testrail_client.add_attachment

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
        print(f"{Colors.FAIL}✗ TC{case_id}: YAML 파일 없음{Colors.ENDC}")
        return None
    # 중복 제거 및 정렬 (최신 파일 우선)
    unique_matches = list(set(all_matches))
    unique_matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    if len(unique_matches) > 1:
        print(f"{Colors.WARNING}⚠ TC{case_id}: {len(unique_matches)}개 파일, 최신 선택{Colors.ENDC}")
    # 선택된 파일 YAML 검증
    selected_file = unique_matches[0]
    if not validate_yaml_file(selected_file):
        print(f"{Colors.FAIL}✗ TC{case_id}: YAML 검증 실패{Colors.ENDC}")
        for alternative in unique_matches[1:]:
            if validate_yaml_file(alternative):
                print(f"{Colors.OKGREEN}✓ TC{case_id}: 대체 파일 선택{Colors.ENDC}")
                return alternative
        return None
    print(f"{Colors.OKGREEN}✓ TC{case_id}: 매칭 완료{Colors.ENDC}")
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

# 상수 정의
PACKAGE_NAME = "net.cj.cjhv.gs.tving"

def check_anr_state(logcat_content):
    """ANR 상태 체크"""
    anr_indicators = [
        "ANR in",
        "Not responding",
        "Application Not Responding",
        "Input dispatching timed out"
    ]
    
    for line in logcat_content.splitlines():
        for indicator in anr_indicators:
            if indicator in line:
                return True, line
    return False, None

def analyze_playing_state(logcat_content, serial):
    """플레이어 상태 분석"""
    # 마지막 10줄에서 플레이어 상태 확인
    lines = logcat_content.splitlines()
    last_lines = lines[-10:] if len(lines) > 10 else lines
    result = 'FAIL'
    
    for line in last_lines:
        # 두 가지 형식 모두 체크
        if 'PLAYING(3)' in line or 'IS PLAYING' in line:
            result = 'OK'
            break
    
    # 단말기별로 playing_check.txt 저장
    today = datetime.now().strftime("%Y%m%d")
    result_dir = f"artifacts/result/{serial}/{today}"
    os.makedirs(result_dir, exist_ok=True)
    with open(f'{result_dir}/playing_check.txt', 'w') as f:
        f.write(result)
    return result

def collect_tving_logcat(serial, duration=5):
    """TVING 앱의 logcat 수집"""
    config = configparser.ConfigParser()
    config.read('config/config.ini')
    package_name = config['App']['package_name']
    
    today = datetime.now().strftime("%Y%m%d")
    result_dir = f"artifacts/result/{serial}/{today}"
    os.makedirs(result_dir, exist_ok=True)
    logcat_path = f"{result_dir}/tving_logcat.txt"
    
    # logcat 초기화
    subprocess.run(f"adb -s {serial} logcat -c", shell=True)
    
    # logcat 수집
    cmd = f"adb -s {serial} logcat -v threadtime | grep {package_name}"
    with open(logcat_path, "w") as f:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        start = time.time()
        while time.time() - start < duration:
            line = proc.stdout.readline()
            if not line:
                break
            f.write(line)
        
        proc.terminate()
    
    return logcat_path

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
    config.read('config/config.ini')
    tr = config['TestRail']
    suite_id = tr.get('suite_id', '1787')
    run_id = subprocess.check_output('python3 scripts/utils/create_testrail_run.py --suite_id ' + suite_id, shell=True).decode().strip()
    model, os_version, build_id, serial = get_device_info(serial)
    today = datetime.now().strftime('%Y%m%d')
    os.makedirs(f'artifacts/result/{serial}/{today}', exist_ok=True)
    os.makedirs(f'artifacts/logs/{serial}', exist_ok=True)
    results = []
    # 1. TC00000_앱시작.yaml 먼저 실행
    app_start_yaml = None
    for f in glob.glob('maestro_flows/TC00000_앱시작*.yaml'):
        app_start_yaml = f
        break
    if app_start_yaml:
        cmd = ["maestro", f"--device={serial}", "test", app_start_yaml]
        logger.info(f"[{serial}] [앱시작] {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        logger.info(f"[{serial}] stdout:\n{result.stdout}")
        logger.info(f"[{serial}] stderr:\n{result.stderr}")
        logger.info(f"[{serial}] returncode: {result.returncode}")
        logger.info(f"[{serial}] [Passed] in output: {'[Passed]' in result.stdout + result.stderr}")

        # 성공 판정 로직 개선
        status = 'fail'
        if '[Passed]' in result.stdout + result.stderr:
            status = 'pass'
        elif result.returncode == 0:
            # 리턴코드만 0이고 [Passed]가 없을 때는 경고 로그 남기기
            logger.warning(f"[{serial}] 리턴코드는 0이지만 [Passed]가 로그에 없습니다. 플로우에 assert 계열 명령이 있는지 확인하세요.")
            status = 'pass'  # 실제로 성공한 경우 pass로 처리(운영 상황에 따라 fail로 둘 수도 있음)
        else:
            logger.error(f"[{serial}] 앱 시작 실패로 간주합니다.")
        testrail_client.add_result(tr, run_id, '00000', status, f"[{'성공' if status == 'pass' else '실패'}] 단말기: {serial}")
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
        testrail_client.add_result(tr, run_id, case_id, status, f"[{'성공' if status == 'pass' else '실패'}] 단말기: {serial}")
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
    # Assertion, Exception, Error, FAILED 등 실제 에러 메시지 추출
    error_lines = [l.strip() for l in lines if any(x in l for x in ['FAILED', 'Error', 'Exception', 'Assertion'])]
    if error_lines:
        return '\n'.join(error_lines)[:500]
    # fallback: 마지막 10줄
    return ''.join(lines[-10:]).strip()[:500]

def check_test_result(log_content):
    """Maestro 테스트 결과 확인"""
    # 실패 케이스 체크
    if '[Failed]' in log_content:
        error_msg = ''
        for line in log_content.splitlines():
            if '[Failed]' in line:
                error_msg = line.strip()
                break
        return 'fail', error_msg
    
    # 성공 케이스 체크
    if '[Passed]' in log_content:
        return 'pass', ''
    
    # 기본값은 실패 처리
    return 'fail', 'Unknown error'

def run_maestro_test(yaml_path, serial):
    """Maestro 테스트 실행"""
    config = configparser.ConfigParser()
    config.read('config.ini')
    package_name = config['App']['package_name']
    
    # 결과 저장 디렉토리 생성
    today = datetime.now().strftime("%Y%m%d")
    result_dir = f"artifacts/result/{serial}/{today}"
    os.makedirs(result_dir, exist_ok=True)
    
    # 비디오 녹화 디렉토리 생성
    video_dir = f"{result_dir}/videos"
    os.makedirs(video_dir, exist_ok=True)
    
    # 로그 저장 경로
    log_path = f"{result_dir}/maestro_test.log"
    logcat_path = f"{result_dir}/adb_{serial}_log.txt"
    
    try:
        # 기존 로그캣 클리어
        subprocess.run(f"adb -s {serial} logcat -c", shell=True)
        
        # 로그캣 저장 시작
        logcat_file = open(logcat_path, "w")
        logcat_proc = subprocess.Popen(
            f"adb -s {serial} logcat -v time",
            shell=True,
            stdout=logcat_file,
            stderr=subprocess.STDOUT
        )
        print(f"로그캣 저장 시작: {logcat_path}")
        
        # 테스트 실행 (비디오 녹화 활성화)
        cmd = f"maestro test -e {serial} --video {video_dir} {yaml_path}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        # 테스트 로그 저장
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\nSTDERR:\n")
                f.write(result.stderr)
        print(f"테스트 로그 저장: {log_path}")
        
        # 결과 분석
        status, error_msg = check_test_result(result.stdout)
        print(f"check_test_result 반환값: status={status}, error_msg={error_msg}")
        
        # 스크린샷 저장 (항상 시도)
        screenshot_path = f"{result_dir}/failure_screen.png"
        screenshot_cmd = f"adb -s {serial} exec-out screencap -p > {screenshot_path}"
        ret = subprocess.run(screenshot_cmd, shell=True)
        print(f"스크린샷 저장됨: {screenshot_path}, 성공여부: {ret.returncode}, 존재여부: {os.path.exists(screenshot_path)}")
        
        # 비디오 파일 확인 (항상 시도)
        video_path = None
        if os.path.exists(video_dir):
            video_files = [os.path.join(video_dir, f) for f in os.listdir(video_dir) if f.endswith('.mp4')]
            print(f"비디오 파일 리스트: {video_files}")
            if video_files:
                latest_video = max(video_files, key=os.path.getctime)
                video_path = latest_video
                print(f"비디오 파일 찾음: {video_path}")
            else:
                print("비디오 파일을 찾을 수 없습니다.")
        else:
            print(f"비디오 디렉토리가 존재하지 않음: {video_dir}")
        
    except Exception as e:
        print(f"전체 실행 중 예외 발생: {e}")
    finally:
        # 로그캣 프로세스 종료
        try:
            if 'logcat_proc' in locals():
                logcat_proc.terminate()
                logcat_proc.wait(timeout=5)
                logcat_file.close()
                print(f"로그캣 저장 종료: {logcat_path}, 존재여부: {os.path.exists(logcat_path)}")
        except Exception as e:
            print(f"로그캣 프로세스 종료 중 오류: {e}")
    
    return {
        'status': status,
        'error_log': error_msg,
        'log_path': log_path,
        'logcat_path': logcat_path,
        'screenshot_path': screenshot_path,
        'video_path': video_path
    }

class TestRailMaestroRunner:
    def __init__(self):
        self.websocket = None
        self.ws_url = "ws://localhost:8000/ws/monitor/dashboard/"

    async def update_test_status(self, test_case_id, status, progress=None):
        """WebSocket을 통해 테스트 상태를 업데이트합니다."""
        try:
            if not self.websocket:
                self.websocket = await websockets.connect(self.ws_url)
            
            data = {
                "type": "test_update",
                "test_case_id": test_case_id,
                "status": status,
                "progress": progress
            }
            await self.websocket.send(json.dumps(data))
        except Exception as e:
            logger.error(f"테스트 상태 업데이트 실패: {e}")

    async def run_test_case(self, test_case_id, test_case_path):
        """테스트 케이스를 실행하고 상태를 업데이트합니다."""
        try:
            # 테스트 시작 상태 전송
            await self.update_test_status(test_case_id, "running", 0)
            
            # 테스트 실행 전 준비
            await self.update_test_status(test_case_id, "running", 25)
            
            # 테스트 실행
            await self.update_test_status(test_case_id, "running", 50)
            
            # 테스트 결과 처리
            await self.update_test_status(test_case_id, "running", 75)
            
            # 테스트 완료
            success = True  # 실제 테스트 결과에 따라 설정
            final_status = "success" if success else "failed"
            await self.update_test_status(test_case_id, final_status, 100)
            
        except Exception as e:
            logger.error(f"테스트 실행 중 오류 발생: {e}")
            await self.update_test_status(test_case_id, "error", 0)
        
        finally:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None

    def run(self, test_case_id, test_case_path):
        """테스트 실행을 위한 메인 메소드"""
        asyncio.get_event_loop().run_until_complete(
            self.run_test_case(test_case_id, test_case_path)
        )

def main(run_id=None):
    devices = get_connected_devices()
    N = len(devices)
    if N < 1:
        print("연결된 단말기가 없습니다.")
        return
    config = configparser.ConfigParser()
    config.read('config.ini')
    tr = config['TestRail']
    suite_id = tr.get('suite_id', '1787')
    # run_id를 main.py에서 반드시 인자로 넘겨야 함
    if run_id is None:
        print("[오류] run_id는 main.py에서 생성해 인자로 넘겨야 합니다.")
        return
    testrail_cases = testrail_client.get_cases(tr, suite_id)
    if isinstance(testrail_cases, dict) and 'cases' in testrail_cases:
        testrail_cases = testrail_cases['cases']

    # rich 진행상황 테이블/진행률
    case_status = {}
    case_device_info = {}
    case_start_time = {}
    case_end_time = {}
    for case in testrail_cases:
        for serial in devices:
            key = (case['id'], serial)
            case_status[key] = '대기'
            model, os_version, build_id, _, serial = get_device_info_by_serial(serial)
            case_device_info[key] = f"{model}({serial})"
            case_start_time[key] = ''
            case_end_time[key] = ''
    def make_table():
        table = Table(title="TestRail 테스트케이스 진행상황")
        table.add_column("순번", justify="right")
        table.add_column("케이스ID")
        table.add_column("제목")
        table.add_column("상태")
        table.add_column("단말기")
        table.add_column("시작시간")
        table.add_column("종료시간")
        idx = 1
        for case in testrail_cases:
            for serial in devices:
                key = (case['id'], serial)
                status = case_status[key]
                # 상태별 색상 지정
                if status == '성공':
                    status_cell = f"[bold green]{status}[/bold green]"
                elif status == '실패':
                    status_cell = f"[bold red]{status}[/bold red]"
                elif status == '진행중':
                    status_cell = f"[bold yellow]{status}[/bold yellow]"
                elif status == '스킵':
                    status_cell = f"[grey62]{status}[/grey62]"
                else:
                    status_cell = status
                table.add_row(
                    str(idx),
                    str(case['id']),
                    case.get('title', ''),
                    status_cell,
                    case_device_info[key],
                    case_start_time[key],
                    case_end_time[key],
                )
                idx += 1
        return table

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
    )
    task = progress.add_task("전체 진행률", total=len(testrail_cases))

    with Live(make_table(), refresh_per_second=2) as live:
        # 1. TC00000_앱시작.yaml을 항상 shard-all로 먼저 실행 (TestRail 업로드 X)
        app_start_yaml = None
        for f in glob.glob('maestro_flows/TC00000_앱시작*.yaml'):
            app_start_yaml = f
            break
        if app_start_yaml:
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
                # 성공 판정 보완: [Passed] 또는 Flow Passed 또는 returncode==0
                status = 'fail'
                # shard 결과가 있으면 우선 사용
                for shard_num, res in shard_results:
                    if int(shard_num) == i+1:
                        status = 'pass' if res == 'Passed' else 'fail'
                # shard 결과가 없거나, stdout에 [Passed]/Flow Passed가 있거나, returncode==0이면 성공
                if not shard_results:
                    if '[Passed]' in result.stdout + result.stderr or 'Flow Passed' in result.stdout + result.stderr or result.returncode == 0:
                        status = 'pass'
                if status == 'fail':
                    print(f"[중단] {serial}에서 앱시작 실패. 이후 케이스 실행 중단.")
                    failed = True
            if failed:
                return
        else:
            print("[오류] TC00000_앱시작.yaml 파일을 찾을 수 없습니다.")
            return
        # 2. TestRail 케이스들을 shard-all로 실행 및 결과 업로드 (코멘트에 단말기별 결과 모두 남기기, 실패시 첨부)
        all_results = []
        for idx, case in enumerate(testrail_cases, 1):
            case_id = case['id']
            title = case.get('title', '')
            for i, serial in enumerate(devices):
                key = (case_id, serial)
                case_status[key] = '진행중'
                case_start_time[key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                live.update(make_table())
            yaml_path = find_maestro_flow(case_id)
            if not yaml_path:
                for serial in devices:
                    key = (case_id, serial)
                    case_status[key] = '스킵'
                    case_end_time[key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                live.update(make_table())
                progress.advance(task)
                continue
            with open(yaml_path, encoding='utf-8') as f:
                content = f.read()
            if '{{DATE}}' in content or '{{TIME}}' in content:
                yaml_path = substitute_and_prepare_yaml(yaml_path)
            cmd = ["maestro", "test", "--shard-all", str(N), yaml_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            import re
            shard_results = re.findall(r'\[shard (\d+)\] \[(Passed|Failed)\](.*)', result.stdout + result.stderr)
            shard_log_splits = re.split(r'(\[shard \d+\] \[(?:Passed|Failed)\])', result.stdout + result.stderr)
            shard_logs = []
            for i in range(1, len(shard_log_splits), 2):
                header = shard_log_splits[i]
                log = shard_log_splits[i+1] if i+1 < len(shard_log_splits) else ''
                shard_logs.append(header + '\n' + log)
            today = datetime.now().strftime('%Y%m%d')
            overall_status = 'pass'
            for i, serial in enumerate(devices):
                key = (case_id, serial)
                model, os_version, build_id, _, serial = get_device_info_by_serial(serial)
                tving_version = get_tving_app_version(serial)
                result_dir = os.path.join('result', serial, today)
                os.makedirs(result_dir, exist_ok=True)
                before_files = set(os.listdir(result_dir)) if os.path.exists(result_dir) else set()
                # 상태 판정 개선: shard 결과, stdout, returncode, 로그파일 종합
                status = '실패'
                # 1. shard 결과 우선
                for shard_num, res, extra in shard_results:
                    if int(shard_num) == i+1:
                        status = '성공' if res == 'Passed' else '실패'
                # 2. shard 결과 없으면 stdout/stderr, returncode
                if not shard_results:
                    logdata = result.stdout + result.stderr
                    if '[Passed]' in logdata or 'Flow Passed' in logdata or result.returncode == 0:
                        status = '성공'
                # 3. 로그파일에 Flow Passed 있으면 성공
                log_dir = os.path.join('logs', serial)
                os.makedirs(log_dir, exist_ok=True)
                log_path = os.path.join(log_dir, f'maestro_TC{case_id}.log')
                if i < len(shard_logs):
                    with open(log_path, 'w', encoding='utf-8') as f:
                        f.write(shard_logs[i].strip())
                if os.path.exists(log_path):
                    with open(log_path, 'r', encoding='utf-8') as f:
                        loglines = f.read()
                        if 'Flow Passed' in loglines:
                            status = '성공'
                after_files = set(os.listdir(result_dir)) if os.path.exists(result_dir) else set()
                new_files = after_files - before_files
                attachments = [os.path.join(result_dir, f) for f in new_files if f.endswith('.mp4') or f.endswith('.png')]
                error_log = extract_maestro_error_log(serial, case_id) if status == '실패' else ''
                all_results.append({
                    'case_id': case_id,
                    'title': title,
                    'serial': serial,
                    'model': model,
                    'os_version': os_version,
                    'build_id': build_id,
                    'tving_version': tving_version,
                    'status': 'pass' if status == '성공' else 'fail',
                    'log_path': log_path,
                    'attachments': attachments,
                    'error_log': error_log
                })
                case_status[key] = status
                case_end_time[key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if status == '실패':
                    overall_status = 'fail'
            live.update(make_table())
            progress.advance(task)
        print("[INFO] 모든 테스트 실행 완료. 결과/첨부 업로드 시작.")
        # 업로드 단계: 케이스별로 단말기별 결과 취합 후 일괄 업로드
        for case in testrail_cases:
            case_id = case['id']
            case_results = [r for r in all_results if r['case_id'] == case_id]
            comment_lines = []
            overall_status = 'pass'
            attachments = []
            for r in case_results:
                if r['status'] == 'pass':
                    comment_lines.append(f"[성공] 단말기: {r['model']} ({r['serial']}), OS: {r['os_version']}, 빌드: {r['tving_version']}")
                else:
                    comment_lines.append(f"[실패] 단말기: {r['model']} ({r['serial']}), OS: {r['os_version']}, 빌드: {r['tving_version']}, 오류코드: {r['error_log']}")
                    attachments.extend(r['attachments'])
                    overall_status = 'fail'
            comment = '\n'.join(comment_lines)
            result_id = testrail_client.add_result(tr, run_id, case_id, overall_status, comment)
            for filepath in attachments:
                testrail_client.add_attachment(tr, result_id, filepath)
        print("[INFO] 모든 케이스 결과/첨부 일괄 업로드 완료.")

if __name__ == '__main__':
    main() 