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
from django.db.models import Avg, Count, Q
from .models import TestCase, TestRun, TestAPI
import json
from datetime import datetime, timedelta
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

def api_dashboard(request):
    """API 성능 모니터링 대시보드"""
    from scripts.utils.testlog_db import get_db_connection
    
    # 최근 7일간의 API 통계
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # API 호출 통계
        cursor.execute("""
            SELECT 
                COUNT(*) as total_calls,
                AVG(elapsed) as avg_response_time,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as failed_calls
            FROM test_api 
            WHERE created_at BETWEEN ? AND ?
        """, (start_date.isoformat(), end_date.isoformat()))
        
        api_stats_row = cursor.fetchone()
        api_stats = {
            'total_calls': api_stats_row[0] or 0,
            'avg_response_time': api_stats_row[1] or 0,
            'failed_calls': api_stats_row[2] or 0
        }
        
        # 성공률 계산
        if api_stats['total_calls'] > 0:
            api_stats['success_rate'] = ((api_stats['total_calls'] - api_stats['failed_calls']) / api_stats['total_calls']) * 100
        else:
            api_stats['success_rate'] = 0
        
        # 테스트케이스별 API 호출 수
        cursor.execute("""
            SELECT 
                test_case_id,
                COUNT(*) as api_count,
                AVG(elapsed) as avg_response_time
            FROM test_api 
            WHERE created_at BETWEEN ? AND ?
            GROUP BY test_case_id
            ORDER BY api_count DESC
            LIMIT 10
        """, (start_date.isoformat(), end_date.isoformat()))
        
        test_case_api_stats = []
        for row in cursor.fetchall():
            test_case_api_stats.append({
                'test_case_id': row[0],
                'api_count': row[1],
                'avg_response_time': row[2] or 0
            })
        
        # 시간대별 API 호출 분포
        hourly_stats = []
        for hour in range(24):
            cursor.execute("""
                SELECT COUNT(*) FROM test_api 
                WHERE created_at BETWEEN ? AND ?
                AND strftime('%H', created_at) = ?
            """, (start_date.isoformat(), end_date.isoformat(), f"{hour:02d}"))
            
            hour_count = cursor.fetchone()[0]
            hourly_stats.append({
                'hour': hour,
                'call_count': hour_count
            })
        
        # URL별 API 호출 통계
        cursor.execute("""
            SELECT 
                url,
                COUNT(*) as call_count,
                AVG(elapsed) as avg_response,
                (COUNT(CASE WHEN status_code >= 400 THEN 1 END) * 100.0 / COUNT(*)) as error_rate
            FROM test_api 
            WHERE created_at BETWEEN ? AND ?
            GROUP BY url
            ORDER BY call_count DESC
            LIMIT 20
        """, (start_date.isoformat(), end_date.isoformat()))
        
        url_stats = []
        for row in cursor.fetchall():
            url_stats.append({
                'url': row[0],
                'call_count': row[1],
                'avg_response': row[2] or 0,
                'error_rate': row[3] or 0
            })
        
        conn.close()
        
    except Exception as e:
        # 오류 발생 시 빈 데이터 반환
        api_stats = {'total_calls': 0, 'avg_response_time': 0, 'failed_calls': 0, 'success_rate': 0}
        test_case_api_stats = []
        hourly_stats = []
        url_stats = []
    
    context = {
        'api_stats': api_stats,
        'test_case_api_stats': test_case_api_stats,
        'hourly_stats': hourly_stats,
        'url_stats': url_stats,
        'date_range': {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d')
        }
    }
    
    return render(request, 'qa_monitor/api_dashboard_new.html', context)

def api_performance_chart(request):
    """API 성능 차트 데이터 (AJAX)"""
    days = int(request.GET.get('days', 7))
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 일별 API 성능 통계 (간단한 방식으로 변경)
    daily_stats = []
    current_date = start_date.date()
    end_date_only = end_date.date()
    
    while current_date <= end_date_only:
        day_start = datetime.combine(current_date, datetime.min.time())
        day_end = datetime.combine(current_date, datetime.max.time())
        
        day_data = TestAPI.objects.filter(
            created_at__range=(day_start, day_end)
        ).aggregate(
            total_calls=Count('id'),
            avg_response_time=Avg('elapsed'),
            error_count=Count('id', filter=Q(status_code__gte=400))
        )
        
        daily_stats.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'total_calls': day_data['total_calls'] or 0,
            'avg_response_time': day_data['avg_response_time'] or 0,
            'error_count': day_data['error_count'] or 0
        })
        
        current_date += timedelta(days=1)
    
    return JsonResponse({
        'daily_stats': daily_stats
    })

def api_error_analysis(request):
    """API 오류 분석"""
    from scripts.utils.testlog_db import get_db_connection
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # HTTP 상태 코드별 오류 분석
        cursor.execute("""
            SELECT 
                status_code,
                COUNT(*) as count,
                AVG(elapsed) as avg_response_time
            FROM test_api 
            WHERE status_code >= 400
            GROUP BY status_code
            ORDER BY count DESC
        """)
        
        error_stats = []
        for row in cursor.fetchall():
            error_stats.append({
                'status_code': row[0],
                'count': row[1],
                'avg_response_time': row[2] or 0
            })
        
        # 오류가 발생한 URL 분석
        cursor.execute("""
            SELECT 
                url,
                status_code,
                COUNT(*) as count
            FROM test_api 
            WHERE status_code >= 400
            GROUP BY url, status_code
            ORDER BY count DESC
            LIMIT 20
        """)
        
        error_urls = []
        for row in cursor.fetchall():
            error_urls.append({
                'url': row[0],
                'status_code': row[1],
                'count': row[2]
            })
        
        # 테스트케이스별 오류율
        cursor.execute("""
            SELECT 
                test_case_id,
                COUNT(*) as total_calls,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_calls,
                (COUNT(CASE WHEN status_code >= 400 THEN 1 END) * 100.0 / COUNT(*)) as error_rate
            FROM test_api 
            GROUP BY test_case_id
            HAVING error_rate > 0
            ORDER BY error_rate DESC
            LIMIT 10
        """)
        
        test_case_errors = []
        for row in cursor.fetchall():
            test_case_errors.append({
                'test_case_id': row[0],
                'total_calls': row[1],
                'error_calls': row[2],
                'error_rate': row[3]
            })
        
        conn.close()
        
    except Exception as e:
        error_stats = []
        error_urls = []
        test_case_errors = []
    
    context = {
        'error_stats': error_stats,
        'error_urls': error_urls,
        'test_case_errors': test_case_errors
    }
    
    return render(request, 'qa_monitor/api_error_analysis.html', context)

def menu_api_logs(request):
    """메뉴별 API 로그 대시보드"""
    from scripts.utils.testlog_db import get_db_connection
    
    # 메뉴별 API 호출 통계
    menu_api_stats = {}
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 테스트케이스별 API 호출 데이터 조회
        cursor.execute("""
            SELECT 
                ta.test_case_id,
                ta.url,
                ta.method,
                ta.status_code,
                ta.elapsed,
                ta.created_at,
                tl.title as test_title
            FROM test_api ta
            LEFT JOIN test_log tl ON ta.test_case_id = tl.case_id
            ORDER BY ta.created_at DESC
            LIMIT 1000
        """)
        
        api_calls = cursor.fetchall()
        
        # 메뉴별로 API 호출 그룹화
        for call in api_calls:
            test_case_id, url, method, status_code, elapsed, created_at, test_title = call
            
            # 테스트 제목에서 메뉴 추출
            menu_name = extract_menu_from_title(test_title) if test_title else f"TC{test_case_id}"
            
            if menu_name not in menu_api_stats:
                menu_api_stats[menu_name] = {
                    'total_calls': 0,
                    'success_calls': 0,
                    'error_calls': 0,
                    'avg_response_time': 0,
                    'api_calls': [],
                    'unique_apis': set()
                }
            
            menu_api_stats[menu_name]['total_calls'] += 1
            menu_api_stats[menu_name]['api_calls'].append({
                'url': url,
                'method': method,
                'status_code': status_code,
                'elapsed': elapsed,
                'created_at': created_at
            })
            menu_api_stats[menu_name]['unique_apis'].add(f"{method} {url}")
            
            if status_code < 400:
                menu_api_stats[menu_name]['success_calls'] += 1
            else:
                menu_api_stats[menu_name]['error_calls'] += 1
        
        # 평균 응답 시간 계산
        for menu_name, stats in menu_api_stats.items():
            if stats['api_calls']:
                total_time = sum(call['elapsed'] for call in stats['api_calls'])
                stats['avg_response_time'] = total_time / len(stats['api_calls'])
                stats['unique_apis'] = len(stats['unique_apis'])
        
        conn.close()
        
    except Exception as e:
        logger.error(f"메뉴별 API 로그 조회 실패: {e}")
        menu_api_stats = {}
    
    context = {
        'menu_api_stats': menu_api_stats,
        'total_menus': len(menu_api_stats)
    }
    
    return render(request, 'qa_monitor/menu_api_logs.html', context)

def hierarchy_analysis(request):
    """UI Hierarchy 분석 대시보드"""
    from scripts.utils.maestro_hierarchy_capture import MaestroHierarchyCapture
    
    capture = MaestroHierarchyCapture()
    
    # 최근 Hierarchy 데이터 조회
    recent_hierarchies = capture.get_hierarchy_history(limit=50)
    
    # 테스트케이스별 통계
    test_case_stats = {}
    for hierarchy in recent_hierarchies:
        test_case_id = hierarchy['test_case_id']
        if test_case_id not in test_case_stats:
            test_case_stats[test_case_id] = {
                'total_screens': 0,
                'total_elements': 0,
                'avg_clickable': 0,
                'avg_text_elements': 0,
                'screens': []
            }
        
        test_case_stats[test_case_id]['total_screens'] += 1
        test_case_stats[test_case_id]['total_elements'] += hierarchy['element_count']
        test_case_stats[test_case_id]['screens'].append({
            'screen_name': hierarchy['screen_name'],
            'element_count': hierarchy['element_count'],
            'clickable_elements': hierarchy['clickable_elements'],
            'text_elements': hierarchy['text_elements'],
            'captured_at': hierarchy['captured_at']
        })
    
    # 평균 계산
    for test_case_id, stats in test_case_stats.items():
        if stats['total_screens'] > 0:
            stats['avg_clickable'] = sum(s['clickable_elements'] for s in stats['screens']) / stats['total_screens']
            stats['avg_text_elements'] = sum(s['text_elements'] for s in stats['screens']) / stats['total_screens']
    
    # UI 안정성 분석
    ui_stability_analysis = {}
    for test_case_id in test_case_stats.keys():
        stability = capture.analyze_ui_changes(test_case_id)
        if 'stability_score' in stability:
            ui_stability_analysis[test_case_id] = stability
    
    context = {
        'recent_hierarchies': recent_hierarchies,
        'test_case_stats': test_case_stats,
        'ui_stability_analysis': ui_stability_analysis,
        'total_hierarchies': len(recent_hierarchies)
    }
    
    return render(request, 'qa_monitor/hierarchy_analysis.html', context)

def hierarchy_detail(request, test_case_id):
    """특정 테스트케이스의 Hierarchy 상세 분석"""
    from scripts.utils.maestro_hierarchy_capture import MaestroHierarchyCapture
    
    capture = MaestroHierarchyCapture()
    
    # 해당 테스트케이스의 모든 Hierarchy 데이터
    hierarchies = capture.get_hierarchy_history(test_case_id, limit=100)
    
    # UI 변화 분석
    ui_changes = capture.analyze_ui_changes(test_case_id)
    
    # 화면별 통계
    screen_stats = {}
    for hierarchy in hierarchies:
        screen_name = hierarchy['screen_name']
        if screen_name not in screen_stats:
            screen_stats[screen_name] = {
                'count': 0,
                'total_elements': 0,
                'total_clickable': 0,
                'total_text': 0,
                'avg_elements': 0,
                'captures': []
            }
        
        screen_stats[screen_name]['count'] += 1
        screen_stats[screen_name]['total_elements'] += hierarchy['element_count']
        screen_stats[screen_name]['total_clickable'] += hierarchy['clickable_elements']
        screen_stats[screen_name]['total_text'] += hierarchy['text_elements']
        screen_stats[screen_name]['captures'].append({
            'element_count': hierarchy['element_count'],
            'clickable_elements': hierarchy['clickable_elements'],
            'text_elements': hierarchy['text_elements'],
            'captured_at': hierarchy['captured_at']
        })
    
    # 평균 계산
    for screen_name, stats in screen_stats.items():
        if stats['count'] > 0:
            stats['avg_elements'] = stats['total_elements'] / stats['count']
    
    context = {
        'test_case_id': test_case_id,
        'hierarchies': hierarchies,
        'ui_changes': ui_changes,
        'screen_stats': screen_stats,
        'total_screens': len(screen_stats)
    }
    
    return render(request, 'qa_monitor/hierarchy_detail.html', context)

def extract_menu_from_title(title):
    """테스트 제목에서 메뉴명 추출"""
    if not title:
        return "Unknown"
    
    # 메뉴 키워드 매핑
    menu_keywords = {
        '로그인': '로그인/인증',
        '회원가입': '로그인/인증',
        '프로필': '프로필 관리',
        '검색': '검색',
        '시청': '콘텐츠 시청',
        '다운로드': '콘텐츠 다운로드',
        '예약': '시청 예약',
        '티빙톡': '티빙톡',
        '뉴스': '뉴스',
        '스포츠': '스포츠',
        '영화': '영화',
        '시리즈': '시리즈',
        '라이브': '라이브',
        '스페셜관': '스페셜관',
        '메인': '메인 화면',
        '탭': '탭 네비게이션'
    }
    
    for keyword, menu_name in menu_keywords.items():
        if keyword in title:
            return menu_name
    
    return "기타"