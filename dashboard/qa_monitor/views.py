import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from django.shortcuts import render
from scripts.config.config_manager import ConfigManager
from scripts.testrail.testrail import TestRailManager
import logging
import datetime
import pytz
from django.http import JsonResponse
logging.basicConfig(level=logging.WARNING)

def dashboard(request):
    print("[DEBUG] dashboard view 진입")
    config = ConfigManager().get_testrail_config()
    tr_manager = TestRailManager(config)
    try:
        runs = tr_manager.get_test_runs()
        print("[DEBUG] TestRail runs:", runs)
        logging.warning(f"TestRail runs: {runs}")
    except Exception as e:
        print("[DEBUG] get_test_runs 예외:", e)
        logging.warning(f"get_test_runs 예외: {e}")
        runs = []
    if not runs or not isinstance(runs, dict) or not runs.get('runs'):
        status_counts = {'Passed': 0, 'Failed': 0, 'Blocked': 0, 'Untested': 0, 'Retest': 0}
        recent_runs = []
    else:
        run_list = runs['runs'] if isinstance(runs, dict) and 'runs' in runs else []
        # 상태별 통계는 최신 테스트런 기준으로 유지
        latest_run = run_list[0] if run_list else None
        if latest_run:
            run_id = latest_run['id']
            try:
                tests = tr_manager.get_tests(run_id)
                print("[DEBUG] TestRail tests:", tests)
                logging.warning(f"TestRail tests: {tests}")
            except Exception as e:
                print("[DEBUG] get_tests 예외:", e)
                logging.warning(f"get_tests 예외: {e}")
                tests = []
            if isinstance(tests, list) and len(tests) > 0 and 'tests' in tests[0]:
                test_list = tests[0]['tests']
            else:
                test_list = []
            status_map = {1: 'Passed', 2: 'Blocked', 3: 'Untested', 4: 'Retest', 5: 'Failed'}
            status_counts = {'Passed': 0, 'Failed': 0, 'Blocked': 0, 'Untested': 0, 'Retest': 0}
            for t in test_list:
                status_id = t['status_id'] if 'status_id' in t else None
                if isinstance(status_id, int):
                    name = status_map.get(status_id, None)
                else:
                    name = None
                if name:
                    status_counts[name] += 1
        else:
            status_counts = {'Passed': 0, 'Failed': 0, 'Blocked': 0, 'Untested': 0, 'Retest': 0}
        # 최근 실행 이력은 테스트런 기준으로 생성
        recent_runs = []
        for run in run_list:
            # 상태 판정
            if run.get('failed_count', 0) > 0:
                status = 'Failed'
            elif run.get('passed_count', 0) > 0 and run.get('failed_count', 0) == 0 and run.get('untested_count', 0) == 0:
                status = 'Passed'
            elif run.get('is_completed'):
                status = 'Completed'
            else:
                status = 'In Progress'
            # 실행시간 포맷 변환 (KST)
            created_on = run.get('created_on', '')
            if created_on:
                try:
                    kst = pytz.timezone('Asia/Seoul')
                    created_on_str = datetime.datetime.fromtimestamp(int(created_on), tz=pytz.UTC).astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    created_on_str = str(created_on)
            else:
                created_on_str = ''
            # 상태별 카운트 dict 추가
            case_status = {
                'Passed': run.get('passed_count', 0),
                'Failed': run.get('failed_count', 0),
                'Blocked': run.get('blocked_count', 0),
                'Untested': run.get('untested_count', 0),
                'Retest': run.get('retest_count', 0),
            }
            # 대표 테스트케이스 id 추출 (첫 번째 테스트의 case_id)
            case_id = None
            try:
                tests = tr_manager.get_tests(run.get('id'))
                test_list = []
                if isinstance(tests, list) and len(tests) > 0 and 'tests' in tests[0]:
                    test_list = tests[0]['tests']
                if test_list:
                    case_id = test_list[0].get('case_id')
            except Exception:
                case_id = None
            recent_runs.append({
                'id': run.get('id'),
                'case_id': case_id,
                'name': run.get('name', f"Run {run.get('id')}"),
                'status': status,
                'time': created_on_str,
                'case_status': case_status,
            })
    print("[DEBUG] 최종 status_counts:", status_counts)
    print("[DEBUG] 최종 recent_runs:", recent_runs)
    context = {
        'status_counts': status_counts,
        'recent_runs': recent_runs,
        'device_connected': True,
    }
    return render(request, 'qa_monitor/dashboard.html', context)

def test_list(request):
    return render(request, 'qa_monitor/test_list.html')

def test_detail(request, test_id):
    return render(request, 'qa_monitor/test_detail.html', {'test_id': test_id})

def testcase_detail(request, testcase_id):
    config = ConfigManager().get_testrail_config()
    tr_manager = TestRailManager(config)
    # 최신 테스트런에서 suite_id 추출
    try:
        runs = tr_manager.get_test_runs()
        run_list = runs['runs'] if isinstance(runs, dict) and 'runs' in runs else []
        latest_run = run_list[0] if run_list else None
        suite_id = latest_run['suite_id'] if latest_run and 'suite_id' in latest_run else None
    except Exception as e:
        suite_id = None
    # suite_id로 케이스 목록 조회 후, 해당 case_id와 일치하는 케이스 정의 찾기
    case = None
    if suite_id:
        try:
            cases = tr_manager.get_cases_by_suite(str(suite_id))
            for c in cases:
                if str(c.id) == str(testcase_id):
                    case = c
                    break
        except Exception as e:
            case = None
    if not case:
        case = {'id': testcase_id, 'title': f'테스트케이스 {testcase_id}', 'custom_steps': '', 'custom_expected': '', 'priority_id': '', 'type_id': ''}
    # 최근 실행 이력(이 케이스가 포함된 테스트런들)
    try:
        recent_tests = []
        for run in run_list:
            run_id = run.get('id')
            tests = tr_manager.get_tests(run_id)
            test_list = []
            if isinstance(tests, list) and len(tests) > 0 and 'tests' in tests[0]:
                test_list = tests[0]['tests']
            for t in test_list:
                print("[DEBUG] testcase_detail test item:", t)
                logging.warning(f"[DEBUG] testcase_detail test item: {t}")
                if str(t.get('case_id')) == str(testcase_id):
                    # 실행시간 포맷 변환 (KST)
                    created_on = t.get('created_on', '')
                    if created_on:
                        try:
                            kst = pytz.timezone('Asia/Seoul')
                            created_on_str = datetime.datetime.fromtimestamp(int(created_on), tz=pytz.UTC).astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            created_on_str = str(created_on)
                    else:
                        created_on_str = ''
                    status_map = {1: 'Passed', 2: 'Blocked', 3: 'Untested', 4: 'Retest', 5: 'Failed'}
                    status = status_map.get(t.get('status_id'), 'Untested')
                    recent_tests.append({
                        'run_id': run_id,
                        'run_name': run.get('name', f"Run {run_id}"),
                        'status': status,
                        'time': created_on_str,
                    })
    except Exception as e:
        recent_tests = []
    context = {
        'testcase': case,
        'recent_tests': recent_tests,
    }
    return render(request, 'qa_monitor/testcase_detail.html', context)

def testrun_detail(request, run_id):
    config = ConfigManager().get_testrail_config()
    tr_manager = TestRailManager(config)
    # 테스트런 정보 및 테스트케이스 리스트 가져오기
    try:
        run = tr_manager.get_test_run(run_id)
        print(f"[DEBUG] testrun_detail run: {run}")
        logging.warning(f"[DEBUG] testrun_detail run: {run}")
        testcases = []
        status_map = {1: 'passed', 2: 'blocked', 3: 'untested', 4: 'retest', 5: 'failed'}
        if run and 'test_cases' in run and 'tests' in run['test_cases']:
            print(f"[DEBUG] testrun_detail run['test_cases']['tests']: {run['test_cases']['tests']}")
            logging.warning(f"[DEBUG] testrun_detail run['test_cases']['tests']: {run['test_cases']['tests']}")
            for idx, t in enumerate(run['test_cases']['tests'], start=1):
                print(f"[DEBUG] test dict: {t}")
                status = status_map.get(t.get('status_id'), 'untested')
                case_id = t.get('case_id')
                test_id = t.get('id')
                print(f"[DEBUG] test_id to query: {test_id}")
                comments = []
                try:
                    results = tr_manager.get_results_for_test(str(test_id)) or []
                    print(f"[DEBUG] results for test_id {test_id}: {results}")
                    # API 응답이 [{..., 'results': [...] }] 구조일 때 내부 results로 한 번 더 풀기
                    if results and isinstance(results, list) and 'results' in results[0]:
                        results = results[0]['results']
                    if isinstance(results, dict):
                        results = [results]
                    results = sorted(results, key=lambda r: r.get('created_on', 0), reverse=True)
                    comments = [r.get('comment', '') for r in results if r.get('comment')]
                except Exception as e:
                    print(f"[ERROR] get_results_for_test({test_id}) 실패: {e}")
                    comments = []
                testcases.append({
                    'id': case_id,
                    'title': t.get('title', f"케이스 {case_id}") or f"케이스 {case_id}",
                    'status': status,
                    'order': idx,
                    'description': t.get('description', ''),
                    'comments': comments,
                })
    except Exception as e:
        testcases = []
    context = {
        'run_id': run_id,
        'run_name': run.get('name', f'테스트런 {run_id}') if run else f'테스트런 {run_id}',
        'testcases': testcases,
    }
    return render(request, 'qa_monitor/testrun_detail.html', context)

def test_result_test(request):
    config = ConfigManager().get_testrail_config()
    tr_manager = TestRailManager(config)
    test_id = "392701"
    try:
        results = tr_manager.get_results_for_test(test_id)
    except Exception as e:
        return JsonResponse({"error": str(e)})
    return JsonResponse({"results": results}, safe=False)