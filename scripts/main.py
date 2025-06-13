import configparser
import glob
import subprocess
import os
from datetime import datetime
from testrail_maestro_runner import (
    get_connected_devices, get_device_info_by_serial, get_testrail_cases,
    add_result_for_case, add_attachment_to_result, substitute_and_prepare_yaml,
    find_maestro_flow, extract_maestro_error_log, get_tving_app_version,
    main as testrail_main,
    collect_tving_logcat, analyze_playing_state, check_anr_state
)
from reporter import render_dashboard
from rich.live import Live
import time
import re

def load_config():
    config = configparser.ConfigParser()
    config.read("config.ini")
    return config

def run_maestro_realtime(cmd, devices, logs, live, render_args, t0, current_test, suites_status, idx, total_cases):
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    serials = devices  # shard 1 → serials[0], shard 2 → serials[1], ...
    output = []  # 전체 출력 저장
    shard_outputs = {i+1: [] for i in range(len(devices))}  # shard별 출력 저장
    
    if len(devices) == 1:
        # 단말기 1대: 모든 라인을 logs['ALL']에 append
        while True:
            line = process.stdout.readline()
            if not line:
                break
            output.append(line)
            logs['ALL'].append(line.rstrip())
            # 실행시간/진행률 실시간 갱신
            current_test['elapsed'] = f"{time.time() - t0:.1f}s"
            suites_status[0]['progress'] = f"{int(idx/total_cases*100)}%"
            suites_status[0]['time'] = f"{current_test['elapsed']}"
            live.update(render_dashboard(*render_args))
        process.stdout.close()
        retcode = process.wait()
        full_output = ''.join(output)
        # 성공/실패 판정
        if '[Passed]' in full_output or 'Flow Passed' in full_output:
            shard_results = [("1", "Passed")]
        else:
            shard_results = [("1", "Failed")]
        return retcode, shard_results, full_output
    else:
        # 기존 shard 패턴 파싱 로직
        while True:
            line = process.stdout.readline()
            if not line:
                break
            output.append(line)
            m = re.match(r'\[shard (\d+)\]', line)
            if m:
                shard_idx = int(m.group(1))
                shard_outputs[shard_idx].append(line.rstrip())
                if 0 <= shard_idx-1 < len(serials):
                    logs[serials[shard_idx-1]].append(line.rstrip())
            else:
                logs['ALL'].append(line.rstrip())
            # 실행시간/진행률 실시간 갱신
            current_test['elapsed'] = f"{time.time() - t0:.1f}s"
            suites_status[0]['progress'] = f"{int(idx/total_cases*100)}%"
            suites_status[0]['time'] = f"{current_test['elapsed']}"
            live.update(render_dashboard(*render_args))
        process.stdout.close()
        retcode = process.wait()
        # 결과 분석
        full_output = ''.join(output)
        shard_results = []
        for shard_num in range(1, len(devices) + 1):
            shard_output = ''.join(shard_outputs[shard_num])
            if '[Passed]' in shard_output or 'Flow Passed' in shard_output:
                shard_results.append((str(shard_num), 'Passed'))
            else:
                shard_results.append((str(shard_num), 'Failed'))
        return retcode, shard_results, full_output

def main():
    config = load_config()
    tr_config = config['TestRail']
    app_config = config['App']
    
    devices = get_connected_devices()
    N = len(devices)
    if N < 1:
        print("연결된 단말기가 없습니다.")
        return
    
    suite_id = tr_config.get('suite_id', '1787')
    project_name = tr_config.get('project', 'QA Project')
    start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    run_id = subprocess.check_output(f'python3 scripts/create_testrail_run.py --suite_id {suite_id}', shell=True).decode().strip()
    testrail_cases = get_testrail_cases(tr_config, suite_id)
    if isinstance(testrail_cases, dict) and 'cases' in testrail_cases:
        testrail_cases = testrail_cases['cases']
    # 상태 변수 초기화
    logs = {serial: [] for serial in devices}
    logs['ALL'] = [f"[INFO] QA 자동화 테스트 시작 ({project_name}) - {start_time}"]
    suites_status = []
    for suite_name in ['전체']:
        suites_status.append({'name': suite_name, 'progress': '0%', 'status': '대기', 'time': '-'})
    current_test = {'name': '-', 'desc': '-', 'id': '-', 'devices': {serial: '-' for serial in devices}, 'elapsed': '-'}
    device_infos = []
    for serial in devices:
        model, os_version, build_id, _, serial = get_device_info_by_serial(serial)
        device_infos.append({'model': model, 'os_version': os_version, 'build': build_id, 'serial': serial})
    with Live(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs), refresh_per_second=2, screen=True) as live:
        # TC00000_앱시작 실행 메시지 개선
        if N == 1:
            logs['ALL'].append(f"[INFO] 단말기 1대: TC00000_앱시작 실행 중...")
        else:
            logs['ALL'].append(f"[INFO] {N}대 단말기 shard-all로 TC00000_앱시작 실행 중...")
        app_start_yaml = None
        for f in glob.glob('maestro_flows/TC00000_앱시작*.yaml'):
            app_start_yaml = f
            break
        if app_start_yaml:
            with open(app_start_yaml, encoding='utf-8') as f:
                content = f.read()
            if '{{DATE}}' in content or '{{TIME}}' in content:
                app_start_yaml = substitute_and_prepare_yaml(app_start_yaml)
            if N == 1:
                cmd = ["maestro", "test", app_start_yaml]
            else:
                cmd = ["maestro", "test", "--shard-all", str(N), app_start_yaml]
            live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
            result = subprocess.run(cmd, capture_output=True, text=True)
            shard_results = re.findall(r'\[shard (\d+)\] \[(Passed|Failed)\]', result.stdout + result.stderr)
            serials = devices
            failed = False
            # shard 로그 분리
            shard_log_splits = re.split(r'(\[shard \d+\] \[(?:Passed|Failed)\])', result.stdout + result.stderr)
            shard_logs = []
            for i in range(1, len(shard_log_splits), 2):
                header = shard_log_splits[i]
                log = shard_log_splits[i+1] if i+1 < len(shard_log_splits) else ''
                shard_logs.append(header + '\n' + log)
            for i, serial in enumerate(serials):
                status = 'fail'
                for shard_num, res in shard_results:
                    if int(shard_num) == i+1:
                        status = 'pass' if res == 'Passed' else 'fail'
                if not shard_results:
                    if '[Passed]' in result.stdout + result.stderr or 'Flow Passed' in result.stdout + result.stderr or result.returncode == 0:
                        status = 'pass'
                # 단말별 로그
                if i < len(shard_logs):
                    logs[serial].append(shard_logs[i].strip())
                else:
                    logs[serial].append(result.stdout + result.stderr)
                if status == 'fail':
                    logs[serial].append(f"[중단] {serial}에서 앱시작 실패. 이후 케이스 실행 중단.")
                    logs['ALL'].append(f"[중단] {serial}에서 앱시작 실패. 이후 케이스 실행 중단.")
                    live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
                    failed = True
            live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
            if failed:
                return
        else:
            logs['ALL'].append("[오류] TC00000_앱시작.yaml 파일을 찾을 수 없습니다.")
            live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
            return
        # TestRail 케이스 shard-all 실행 및 결과/첨부/업로드
        all_results = []
        total_cases = len(testrail_cases)
        for idx, case in enumerate(testrail_cases, 1):
            t0 = time.time()
            case_id = case['id']
            title = case.get('title', '')
            current_test = {
                'name': title,
                'desc': case.get('custom_description', '-') or '-',
                'id': case_id,
                'devices': {serial: '진행중' for serial in devices},
                'elapsed': '-'
            }
            logs['ALL'].append(f"[INFO] 테스트 시작: {title} ({case_id})")
            suites_status[0]['progress'] = f"{int(idx/total_cases*100)}%"
            suites_status[0]['status'] = '실행중'
            live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
            yaml_path = find_maestro_flow(case_id)
            if not yaml_path:
                logs['ALL'].append(f"[ERROR] TC{case_id}: 해당 케이스에 maestro flow yaml 파일이 없습니다.")
                for serial in devices:
                    logs[serial].append(f"[스킵] TC{case_id}: maestro flow yaml 없음")
                    current_test['devices'][serial] = '스킵'
                suites_status[0]['progress'] = f"{int(idx/total_cases*100)}%"
                suites_status[0]['status'] = '실행중'
                live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
                continue
            with open(yaml_path, encoding='utf-8') as f:
                content = f.read()
            if '{{DATE}}' in content or '{{TIME}}' in content:
                yaml_path = substitute_and_prepare_yaml(yaml_path)
            if N == 1:
                # 단말기 1대: returncode만으로 성공/실패 판정
                cmd = ["maestro", "test", yaml_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                logs['ALL'].append(result.stdout)
                logs['ALL'].append(result.stderr)
                status = '성공' if result.returncode == 0 else '실패'
                for serial in devices:
                    current_test['devices'][serial] = status
                    logs[serial].append(f"[{status}] TC{case_id} 완료")
                # TestRail 업로드
                for serial in devices:
                    model, os_version, build_id, _, serial = get_device_info_by_serial(serial)
                    tving_version = get_tving_app_version(serial)
                    comment = f"""
디바이스 정보:
- 모델: {model}
- 안드로이드: {os_version}
- 빌드: {build_id}
- TVING 버전: {tving_version}

실행 결과: {status}
"""
                    result_id = add_result_for_case(tr_config, run_id, case_id, status.lower(), comment)
                elapsed = f"{time.time() - t0:.2f}s"
                current_test['elapsed'] = elapsed
                all_results.append({
                    'case_id': case_id,
                    'title': title,
                    'serial': serial,
                    'model': model,
                    'os_version': os_version,
                    'build_id': build_id,
                    'tving_version': tving_version,
                    'status': 'pass' if status == '성공' else 'fail',
                    'log_path': '',
                    'attachments': [],
                    'error_log': '',
                    'elapsed': elapsed
                })
                suites_status[0]['progress'] = f"{int(idx/total_cases*100)}%"
                suites_status[0]['status'] = '실행중'
                live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
                continue
            else:
                # 2대 이상: 기존 로직 유지
                cmd = ["maestro", "test", "--shard-all", str(N), yaml_path]
                render_args = (project_name, start_time, suites_status, current_test, device_infos, logs)
                retcode, shard_results, full_output = run_maestro_realtime(cmd, devices, logs, live, render_args, t0, current_test, suites_status, idx, total_cases)
                
                if retcode != 0 and not shard_results:  # 완전한 실패인 경우
                    logs['ALL'].append(f"[ERROR] TC{case_id}: Maestro shard-all 실행 실패. 오류코드: {retcode}")
                    for serial in devices:
                        logs[serial].append(f"[실패] TC{case_id}: Maestro shard-all 실행 실패. 오류코드: {retcode}")
                        current_test['devices'][serial] = '실패'
                    suites_status[0]['progress'] = f"{int(idx/total_cases*100)}%"
                    suites_status[0]['status'] = '실행중'
                    live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
                    continue
                print("devices:", devices)
                print("shard_results:", shard_results)
                today = datetime.now().strftime('%Y%m%d')
                overall_status = 'pass'
                for i, serial in enumerate(devices):
                    model, os_version, build_id, _, serial = get_device_info_by_serial(serial)
                    tving_version = get_tving_app_version(serial)
                    result_dir = os.path.join('result', serial, today)
                    os.makedirs(result_dir, exist_ok=True)
                    before_files = set(os.listdir(result_dir)) if os.path.exists(result_dir) else set()
                    
                    # 상태 판단 로직 개선
                    status = '실패'  # 기본값은 실패
                    
                    # 1. shard 결과 확인
                    for shard_num, res in shard_results:
                        if int(shard_num) == i+1:
                            status = '성공' if res == 'Passed' else '실패'
                            break  # 명시적으로 break 추가
                    
                    # 2. 플레이어 TC인 경우 추가 검증
                    if 'player' in yaml_path.lower() or '플레이어' in yaml_path:
                        logcat_path = collect_tving_logcat(serial)
                        if os.path.exists(logcat_path):
                            with open(logcat_path, 'r', encoding='utf-8') as f:
                                logcat_content = f.read()
                            player_status = analyze_playing_state(logcat_content, serial)
                            if player_status == 'error':
                                status = '실패'
                                logs[serial].append(f"[실패] TC{case_id}: 플레이어 에러 발생")
                            
                            # ANR 상태 체크 추가
                            is_anr, anr_log = check_anr_state(logcat_content)
                            if is_anr:
                                logs[serial].append(f"[경고] TC{case_id}: ANR 발생 - {anr_log}")
                                # ANR이 발생했지만 앱이 살아있다면 경고만 표시
                                if status == '성공':
                                    logs[serial].append(f"[정보] TC{case_id}: ANR이 발생했으나 테스트는 계속 진행됨")
                    
                    # 3. 결과 기록 및 첨부파일 처리
                    try:
                        after_files = set(os.listdir(result_dir))
                        new_files = after_files - before_files
                        attachments = []
                        
                        # 로그캣 파일 첨부
                        logcat_files = [f for f in new_files if 'logcat' in f.lower()]
                        for log_file in logcat_files:
                            log_path = os.path.join(result_dir, log_file)
                            attachments.append(log_path)
                        
                        # 스크린샷 첨부
                        screenshot_files = [f for f in new_files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                        for img_file in screenshot_files:
                            img_path = os.path.join(result_dir, img_file)
                            attachments.append(img_path)
                        
                        # 테스트레일에 결과 업로드
                        comment = f"""
디바이스 정보:
- 모델: {model}
- 안드로이드: {os_version}
- 빌드: {build_id}
- TVING 버전: {tving_version}

실행 결과: {status}
"""
                        result_id = add_result_for_case(tr_config, run_id, case_id, status.lower(), comment)
                        
                        # 첨부파일 업로드
                        for attachment in attachments:
                            try:
                                add_attachment_to_result(tr_config, result_id, attachment)
                            except Exception as e:
                                logs[serial].append(f"[경고] TC{case_id}: 첨부파일 업로드 실패 - {attachment}")
                                logs['ALL'].append(f"[경고] TC{case_id}: 첨부파일 업로드 실패 - {attachment}")
                    
                    except Exception as e:
                        logs[serial].append(f"[경고] TC{case_id}: 테스트레일 결과 업로드 실패 - {str(e)}")
                        logs['ALL'].append(f"[경고] TC{case_id}: 테스트레일 결과 업로드 실패 - {str(e)}")
                    
                    # 4. UI 업데이트
                    current_test['devices'][serial] = status
                    if status == '실패':
                        overall_status = 'fail'
                    
                    # 5. 로그 업데이트
                    logs[serial].append(f"[{status}] TC{case_id} 완료")
                    elapsed = f"{time.time() - t0:.2f}s"
                    current_test['elapsed'] = elapsed
                    all_results.append({
                        'case_id': case_id,
                        'title': title,
                        'serial': serial,
                        'model': model,
                        'os_version': os_version,
                        'build_id': build_id,
                        'tving_version': tving_version,
                        'status': 'pass' if status == '성공' else 'fail',
                        'log_path': '',
                        'attachments': [],
                        'error_log': '',
                        'elapsed': elapsed
                    })
                print("all_results:", all_results)
                suites_status[0]['progress'] = f"{int(idx/total_cases*100)}%"
                suites_status[0]['status'] = '실행중'
                live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
                # 플레이어 TC(313859, 313889) 실행 후 logcat/playing_check.txt 남기기
                if str(case_id) in ['313859', '313889']:
                    for serial in devices:
                        logcat_path = collect_tving_logcat(serial, duration=5)
                        analyze_playing_state(logcat_path, serial)
        suites_status[0]['progress'] = '100%'
        suites_status[0]['status'] = '완료'
        suites_status[0]['time'] = f"{datetime.now().strftime('%H:%M:%S')}"
        live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))
        logs['ALL'].append("[INFO] 모든 테스트 실행 완료. 결과/첨부 일괄 업로드 시작.")
        for case in testrail_cases:
            case_id = case['id']
            case_results = {serial: [r for r in all_results if r['case_id'] == case_id] for serial in devices}
            overall_status = process_test_results(case_id, yaml_path, case_results, logs)
            print("case_id:", case_id, "overall_status:", overall_status)
            comment = f"전체 테스트 결과: {overall_status}"
            print("comment:", comment)
            result_id = add_result_for_case(tr_config, run_id, case_id, overall_status, comment)
            if result_id:
                print(f"TestRail 결과 보고 성공 (ID: {result_id})")
                
                # 로그 파일 첨부
                for serial, results in case_results.items():
                    for r in results:
                        if 'log_path' in r and os.path.exists(r['log_path']):
                            add_attachment_to_result(tr_config, result_id, r['log_path'])
            else:
                print("TestRail 결과 보고 실패")
        logs['ALL'].append("[INFO] 모든 케이스 결과/첨부 일괄 업로드 완료.")
        live.update(render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs))

def process_test_results(case_id, yaml_path, case_results, logs):
    """테스트 결과 처리 및 TestRail 보고"""
    config = load_config()
    tr_config = config['TestRail']
    
    # 결과 분석
    overall_status = '성공'  # 기본값
    comment_lines = []
    has_failure = False
    
    # 모든 단말기 결과 처리
    for serial, results in case_results.items():
        for r in results:
            # 기본 정보 로그
            device_info = f"단말기: {r['model']} ({r['serial']}), OS: {r['os_version']}, TVING 버전: {r['tving_version']}"
            
            if r['status'] == 'pass':
                comment_lines.append(f"[성공] {device_info}")
            else:
                has_failure = True
                error_msg = r['error_log'] if r['error_log'] else 'Unknown error'
                comment_lines.append(f"[실패] {device_info}\n오류: {error_msg}")
    
    # 하나라도 실패가 있으면 전체 상태를 실패로 설정
    if has_failure:
        overall_status = '실패'
    
    # TestRail에 결과 보고
    comment = "\n".join(comment_lines)
    try:
        result_id = add_result_for_case(tr_config, tr_config['run_id'], case_id, overall_status, comment)
        if result_id:
            print(f"TestRail 결과 보고 성공 (ID: {result_id})")
            
            # 로그 파일 첨부
            for serial, results in case_results.items():
                for r in results:
                    try:
                        # Maestro 테스트 로그 첨부
                        if 'log_path' in r and os.path.exists(r['log_path']):
                            print(f"Maestro 로그 첨부 중: {r['log_path']}")
                            add_attachment_to_result(tr_config, result_id, r['log_path'])
                        
                        # 실패한 경우 스크린샷과 비디오 첨부
                        if r['status'] == 'fail':
                            if 'screenshot_path' in r and r['screenshot_path'] and os.path.exists(r['screenshot_path']):
                                print(f"스크린샷 첨부 중: {r['screenshot_path']}")
                                add_attachment_to_result(tr_config, result_id, r['screenshot_path'])
                            if 'video_path' in r and r['video_path'] and os.path.exists(r['video_path']):
                                print(f"비디오 첨부 중: {r['video_path']}")
                                add_attachment_to_result(tr_config, result_id, r['video_path'])
                        
                        # 로그캣 파일 첨부
                        if 'logcat_path' in r and os.path.exists(r['logcat_path']):
                            print(f"로그캣 첨부 중: {r['logcat_path']}")
                            add_attachment_to_result(tr_config, result_id, r['logcat_path'])
                    except Exception as e:
                        print(f"파일 첨부 중 오류 발생: {e}")
        else:
            print("TestRail 결과 보고 실패")
    except Exception as e:
        print(f"TestRail 결과 보고 중 오류 발생: {e}")
    
    return overall_status

if __name__ == "__main__":
    main() 