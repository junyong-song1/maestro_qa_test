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
    
    # 로컬 데이터베이스에서 데이터 가져오기
    try:
        import sqlite3
        import os
        from datetime import datetime, timedelta
        
        # 데이터베이스 연결
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'artifacts', 'test_log.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 기준일 설정
        now = datetime.now()
        recent_7_days = now - timedelta(days=7)  # 최근 실행 이력용
        recent_30_days = now - timedelta(days=30)  # 상태별 통계용
        
        print(f"[DEBUG] 기준일 - 최근 7일: {recent_7_days.strftime('%Y-%m-%d')}, 최근 30일: {recent_30_days.strftime('%Y-%m-%d')}")
        
        # run_id 기준으로 그룹핑하여 최근 테스트런 정보 가져오기 (최근 7일)
        cursor.execute("""
            SELECT 
                run_id,
                COUNT(*) as total_tests,
                COUNT(CASE WHEN status = '성공' THEN 1 END) as passed_tests,
                COUNT(CASE WHEN status = '실패' THEN 1 END) as failed_tests,
                COUNT(CASE WHEN status = '차단' THEN 1 END) as blocked_tests,
                COUNT(CASE WHEN status = '미테스트' THEN 1 END) as untested_tests,
                COUNT(CASE WHEN status = '재테스트' THEN 1 END) as retest_tests,
                MIN(start_time) as run_start_time,
                MAX(end_time) as run_end_time,
                AVG(elapsed) as avg_elapsed
            FROM test_log 
            WHERE run_id IS NOT NULL 
            AND start_time >= ?
            GROUP BY run_id
            ORDER BY run_start_time DESC 
            LIMIT 10
        """, (recent_7_days.strftime('%Y-%m-%d %H:%M:%S'),))
        run_groups = cursor.fetchall()
        
        # 테스트런 기준 상태별 통계 (최근 7일)
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN failed_tests = 0 AND total_tests > 0 THEN 'Completed'
                    WHEN failed_tests > 0 AND passed_tests > 0 THEN 'Partial'
                    WHEN passed_tests = 0 AND total_tests > 0 THEN 'Failed'
                    ELSE 'Unknown'
                END as run_status,
                COUNT(*) as run_count,
                SUM(total_tests) as total_test_count,
                SUM(passed_tests) as total_passed,
                SUM(failed_tests) as total_failed,
                AVG(avg_elapsed) as avg_duration
            FROM (
                SELECT 
                    run_id,
                    COUNT(*) as total_tests,
                    COUNT(CASE WHEN status = '성공' THEN 1 END) as passed_tests,
                    COUNT(CASE WHEN status = '실패' THEN 1 END) as failed_tests,
                    AVG(elapsed) as avg_elapsed
                FROM test_log 
                WHERE run_id IS NOT NULL 
                AND start_time >= ?
                GROUP BY run_id
            ) run_summary
            GROUP BY run_status
        """, (recent_7_days.strftime('%Y-%m-%d %H:%M:%S'),))
        run_status_data = cursor.fetchall()
        
        conn.close()
        
        # 테스트런 기준 상태별 통계 딕셔너리 생성
        status_counts = {'Completed': 0, 'Partial': 0, 'Failed': 0, 'Unknown': 0}
        total_runs = 0
        total_tests = 0
        total_passed = 0
        total_failed = 0
        avg_duration = 0
        
        for run_status, run_count, test_count, passed, failed, duration in run_status_data:
            status_counts[run_status] = run_count
            total_runs += run_count
            total_tests += test_count or 0
            total_passed += passed or 0
            total_failed += failed or 0
            if duration:
                avg_duration = duration
        
        # 테스트런 단위로 데이터 포맷팅
        recent_runs = []
        for run_group in run_groups:
            run_id, total_tests, passed_tests, failed_tests, blocked_tests, untested_tests, retest_tests, run_start_time, run_end_time, avg_elapsed = run_group
            
            # 실행시간 포맷팅
            try:
                start_dt = datetime.fromisoformat(run_start_time.replace('Z', '+00:00'))
                execution_time = start_dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                execution_time = run_start_time
            
            # 상태 결정 (대부분의 테스트가 성공하면 성공)
            if passed_tests > failed_tests:
                display_status = 'Completed'
            elif failed_tests > 0:
                display_status = 'Failed'
            else:
                display_status = 'Running'
            
            # 상태별 카운트
            status_counts_detail = {
                'passed': passed_tests,
                'failed': failed_tests,
                'blocked': blocked_tests,
                'untested': untested_tests,
                'retest': retest_tests
            }
            
            recent_runs.append({
                'id': run_id,
                'name': f'테스트런 {run_id}',
                'status': display_status,
                'time': execution_time,
                'elapsed': f"{avg_elapsed:.1f}s" if avg_elapsed else "N/A",
                'total_tests': total_tests,
                'status_counts': status_counts_detail
            })
        
        print(f"[DEBUG] 런 단위 데이터: {len(run_groups)}개 런, 상태별 통계: {status_counts}")
        
    except Exception as e:
        print(f"[DEBUG] 로컬 데이터베이스 조회 실패: {e}")
        status_counts = {'Completed': 0, 'Partial': 0, 'Failed': 0, 'Unknown': 0}
        recent_runs = []
        total_runs = 0
        total_tests = 0
        total_passed = 0
        total_failed = 0
        avg_duration = 0
    
    context = {
        'status_counts': status_counts,
        'recent_runs': recent_runs,
        'device_connected': True,
        'recent_7_days': recent_7_days.strftime('%Y-%m-%d'),
        'recent_30_days': recent_30_days.strftime('%Y-%m-%d'),
        'current_date': now.strftime('%Y-%m-%d'),
        'total_runs': total_runs,
        'total_tests': total_tests,
        'total_passed': total_passed,
        'total_failed': total_failed,
        'avg_duration': f"{avg_duration:.1f}s" if avg_duration else "N/A",
        'success_rate': f"{((total_passed / total_tests) * 100):.1f}%" if total_tests > 0 else "0%"
    }
    return render(request, 'qa_monitor/dashboard.html', context)

def test_list(request):
    """테스트케이스 목록 - TestRail 연동"""
    import os
    from scripts.config.config_manager import ConfigManager
    from scripts.testrail.testrail import TestRailManager
    
    try:
        # TestRail 연결 시도 (임시로 비활성화)
        test_cases = []
        try:
            config = ConfigManager()
            testrail_config = config.get_testrail_config()
            testrail = TestRailManager(testrail_config)
            
            # 모든 테스트케이스 가져오기
            test_cases = testrail.get_test_cases()
        except Exception as e:
            print(f"[WARNING] TestRail 연결 실패, 로컬 데이터만 사용: {e}")
            test_cases = []
        
        # TestRail에서 데이터를 가져오지 못한 경우 로컬 데이터베이스에서 가져오기
        if not test_cases:
            try:
                import sqlite3
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'artifacts', 'test_log.db')
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # 로컬 DB에서 테스트케이스 정보 가져오기 (중복 제거)
                cursor.execute("""
                    SELECT test_case_id, 
                           MAX(step_name) as step_name, 
                           MAX(status) as status, 
                           MAX(start_time) as start_time
                    FROM test_log 
                    WHERE test_case_id IS NOT NULL
                    GROUP BY test_case_id
                    ORDER BY MAX(start_time) DESC
                """)
                local_cases = cursor.fetchall()
                conn.close()
                
                # 로컬 데이터를 TestRail 형식으로 변환
                for case_data in local_cases:
                    test_case_id, step_name, status, start_time = case_data
                    test_cases.append({
                        'id': test_case_id,
                        'title': f'TC{test_case_id} - {step_name}',
                        'custom_automation_type': 2,  # Maestro로 가정
                        'priority_id': 1,
                        'section_id': 1,
                        'created_on': start_time,
                        'updated_on': start_time
                    })
            except Exception as e:
                print(f"[ERROR] 로컬 데이터베이스 조회 실패: {e}")
                test_cases = []
        
        # 검색 및 필터링
        search_query = request.GET.get('search', '')
        automation_filter = request.GET.get('automation', 'all')
        
        filtered_cases = []
        for case in test_cases:
            # 검색 필터
            if search_query and search_query.lower() not in case.get('title', '').lower():
                continue
                
            # 자동화 상태 필터
            automation_type = case.get('custom_automation_type', 0)
            if automation_filter == 'automated' and automation_type != 2:  # 2 = Maestro
                continue
            elif automation_filter == 'manual' and automation_type != 0:  # 0 = Manual
                continue
            elif automation_filter == 'maestro' and automation_type != 2:
                continue
            
            # 자동화 상태 텍스트 변환
            automation_status = {
                0: '수동',
                1: '자동화',
                2: 'Maestro'
            }.get(automation_type, '미정')
            
            filtered_cases.append({
                'id': case.get('id'),
                'title': case.get('title'),
                'automation_type': automation_type,
                'automation_status': automation_status,
                'priority': case.get('priority_id'),
                'section_id': case.get('section_id'),
                'created_on': case.get('created_on'),
                'updated_on': case.get('updated_on')
            })
        
        # 정렬 (최신 업데이트 순)
        filtered_cases.sort(key=lambda x: x['updated_on'] or x['created_on'], reverse=True)
        
        # 통계 계산
        total_cases = len(test_cases)
        automated_cases = len([c for c in test_cases if c.get('custom_automation_type') == 2])
        manual_cases = len([c for c in test_cases if c.get('custom_automation_type') == 0])
        automation_rate = (automated_cases / total_cases * 100) if total_cases > 0 else 0
        
        context = {
            'test_cases': filtered_cases,
            'total_cases': total_cases,
            'automated_cases': automated_cases,
            'manual_cases': manual_cases,
            'automation_rate': f"{automation_rate:.1f}%",
            'search_query': search_query,
            'automation_filter': automation_filter,
            'filtered_count': len(filtered_cases)
        }
        
    except Exception as e:
        print(f"[ERROR] TestRail 테스트케이스 조회 실패: {e}")
        context = {
            'test_cases': [],
            'total_cases': 0,
            'automated_cases': 0,
            'manual_cases': 0,
            'automation_rate': "0%",
            'search_query': '',
            'automation_filter': 'all',
            'filtered_count': 0,
            'error': f'TestRail 연결 실패: {str(e)}'
        }
    
    return render(request, 'qa_monitor/test_list.html', context)

def test_detail(request, test_id):
    """테스트케이스 상세 정보 - TestRail 연동"""
    from scripts.config.config_manager import ConfigManager
    from scripts.testrail.testrail import TestRailManager
    from scripts.utils.testlog_db import get_db_connection
    import os
    
    try:
        # TestRail 연결 시도
        test_case = None
        try:
            config = ConfigManager()
            testrail_config = config.get_testrail_config()
            testrail = TestRailManager(testrail_config)
            
            # 테스트케이스 상세 정보 가져오기
            test_case = testrail.get_test_case(test_id)
        except Exception as e:
            print(f"[WARNING] TestRail 연결 실패: {e}")
            test_case = None
        
        if not test_case:
            context = {
                'test_id': test_id,
                'error': '해당 테스트케이스를 찾을 수 없습니다.'
            }
            return render(request, 'qa_monitor/test_detail.html', context)
        
        # 자동화 상태 텍스트 변환
        automation_type = test_case.get('custom_automation_type', 0)
        automation_status = {
            0: '수동',
            1: '자동화',
            2: 'Maestro'
        }.get(automation_type, '미정')
        
        # Maestro 스크립트 파일 경로 확인
        maestro_file = None
        if automation_type == 2:
            maestro_file = f"maestro_flows/qa_flows/TC{test_id}_{test_case.get('title', '').replace(' ', '_')}.yaml"
            if not os.path.exists(maestro_file):
                maestro_file = None
        
        # 로컬 DB에서 실행 이력 가져오기
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(project_root, "artifacts", "test_log.db")
        
        execution_history = []
        performance_stats = {
            'total_runs': 0,
            'success_rate': 0,
            'avg_duration': 0,
            'last_execution': None
        }
        
        try:
            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            
            # 최근 10회 실행 이력
            cursor.execute("""
                SELECT 
                    run_id,
                    status,
                    start_time,
                    end_time,
                    elapsed,
                    error_msg,
                    serial,
                    model
                FROM test_log 
                WHERE test_case_id = ?
                ORDER BY start_time DESC
                LIMIT 10
            """, (test_id,))
            
            history_rows = cursor.fetchall()
            for row in history_rows:
                execution_history.append({
                    'run_id': row[0],
                    'status': row[1],
                    'start_time': row[2],
                    'end_time': row[3],
                    'elapsed': row[4],
                    'error_msg': row[5],
                    'device': f"{row[6]} ({row[7]})"
                })
            
            # 성능 통계
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_runs,
                    COUNT(CASE WHEN status = '성공' THEN 1 END) as success_runs,
                    AVG(elapsed) as avg_duration,
                    MAX(start_time) as last_execution
                FROM test_log 
                WHERE test_case_id = ?
            """, (test_id,))
            
            stats_row = cursor.fetchone()
            if stats_row and stats_row[0] > 0:
                performance_stats = {
                    'total_runs': stats_row[0],
                    'success_rate': (stats_row[1] / stats_row[0]) * 100,
                    'avg_duration': stats_row[2] or 0,
                    'last_execution': stats_row[3]
                }
            
            # API 호출 통계
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_calls,
                    AVG(elapsed) as avg_response_time,
                    COUNT(CASE WHEN status_code >= 400 THEN 1 END) as failed_calls
                FROM test_api 
                WHERE test_case_id = ?
            """, (test_id,))
            
            api_stats_row = cursor.fetchone()
            api_stats = {
                'total_calls': api_stats_row[0] if api_stats_row else 0,
                'avg_response_time': api_stats_row[1] if api_stats_row else 0,
                'failed_calls': api_stats_row[2] if api_stats_row else 0
            }
            
            conn.close()
            
        except Exception as e:
            print(f"[WARNING] 로컬 DB 조회 실패: {e}")
            api_stats = {'total_calls': 0, 'avg_response_time': 0, 'failed_calls': 0}
        
        context = {
            'test_case': test_case,
            'test_id': test_id,
            'automation_status': automation_status,
            'automation_type': automation_type,
            'maestro_file': maestro_file,
            'execution_history': execution_history,
            'performance_stats': performance_stats,
            'api_stats': api_stats
        }
        
    except Exception as e:
        print(f"[ERROR] 테스트케이스 상세 정보 조회 실패: {e}")
        context = {
            'test_id': test_id,
            'error': f'데이터 조회 중 오류가 발생했습니다: {str(e)}'
        }
    
    return render(request, 'qa_monitor/test_detail.html', context)

def testcase_detail(request, testcase_id):
    # 간단한 테스트케이스 상세 정보
    context = {
        'testcase': {
            'id': testcase_id,
            'title': f'테스트케이스 {testcase_id}',
            'custom_steps': '',
            'custom_expected': '',
            'priority_id': '',
            'type_id': ''
        },
        'recent_tests': []
    }
    return render(request, 'qa_monitor/testcase_detail.html', context)

def testrun_detail(request, run_id):
    """테스트런 상세 정보 - 실제 데이터 활용"""
    from scripts.utils.testlog_db import get_db_connection
    import os
    
    # 프로젝트 루트 디렉토리 경로 설정
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(project_root, "artifacts", "test_log.db")
    
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # 1. 테스트런 기본 정보 조회
        cursor.execute("""
            SELECT 
                run_id,
                COUNT(*) as total_tests,
                COUNT(CASE WHEN status = '성공' THEN 1 END) as passed_tests,
                COUNT(CASE WHEN status = '실패' THEN 1 END) as failed_tests,
                COUNT(CASE WHEN status = '차단' THEN 1 END) as blocked_tests,
                COUNT(CASE WHEN status = '미테스트' THEN 1 END) as untested_tests,
                COUNT(CASE WHEN status = '재테스트' THEN 1 END) as retest_tests,
                MIN(start_time) as run_start_time,
                MAX(end_time) as run_end_time,
                AVG(elapsed) as avg_elapsed,
                SUM(elapsed) as total_elapsed
            FROM test_log 
            WHERE run_id = ?
            GROUP BY run_id
        """, (run_id,))
        
        run_info = cursor.fetchone()
        
        if not run_info:
            context = {
                'run_id': run_id,
                'run_name': f'테스트런 {run_id}',
                'error': '해당 테스트런을 찾을 수 없습니다.',
                'testcases': []
            }
            return render(request, 'qa_monitor/testrun_detail.html', context)
        
        # 2. 테스트케이스별 상세 정보 조회
        cursor.execute("""
            SELECT 
                test_case_id,
                step_name,
                status,
                start_time,
                end_time,
                elapsed,
                error_msg,
                serial,
                model,
                os_version,
                tving_version
            FROM test_log 
            WHERE run_id = ?
            ORDER BY start_time ASC
        """, (run_id,))
        
        testcases = cursor.fetchall()
        
        # 3. API 호출 정보 조회
        cursor.execute("""
            SELECT 
                test_case_id,
                COUNT(*) as api_calls,
                AVG(elapsed) as avg_response_time,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as failed_apis
            FROM test_api 
            WHERE run_id = ?
            GROUP BY test_case_id
        """, (run_id,))
        
        api_stats = {row[0]: {'calls': row[1], 'avg_time': row[2], 'failed': row[3]} for row in cursor.fetchall()}
        
        conn.close()
        
        # 4. 데이터 가공
        run_data = {
            'id': run_info[0],
            'total_tests': run_info[1],
            'passed': run_info[2],
            'failed': run_info[3],
            'blocked': run_info[4],
            'untested': run_info[5],
            'retest': run_info[6],
            'start_time': run_info[7],
            'end_time': run_info[8],
            'avg_elapsed': run_info[9],
            'total_elapsed': run_info[10]
        }
        
        # 성공률 계산
        if run_data['total_tests'] > 0:
            run_data['success_rate'] = (run_data['passed'] / run_data['total_tests']) * 100
        else:
            run_data['success_rate'] = 0
        
        # 테스트케이스 데이터 가공
        processed_testcases = []
        for tc in testcases:
            tc_data = {
                'id': tc[0],
                'step_name': tc[1],
                'status': tc[2],
                'start_time': tc[3],
                'end_time': tc[4],
                'elapsed': tc[5],
                'error_msg': tc[6],
                'serial': tc[7],
                'model': tc[8],
                'os_version': tc[9],
                'tving_version': tc[10],
                'api_stats': api_stats.get(tc[0], {'calls': 0, 'avg_time': 0, 'failed': 0})
            }
            processed_testcases.append(tc_data)
        
        context = {
            'run_id': run_id,
            'run_name': f'테스트런 {run_id}',
            'run_data': run_data,
            'testcases': processed_testcases,
            'total_testcases': len(processed_testcases)
        }
        
    except Exception as e:
        print(f"[ERROR] 테스트런 상세 정보 조회 실패: {e}")
        context = {
            'run_id': run_id,
            'run_name': f'테스트런 {run_id}',
            'error': f'데이터 조회 중 오류가 발생했습니다: {str(e)}',
            'testcases': []
        }
    
    return render(request, 'qa_monitor/testrun_detail.html', context)

def test_result_test(request):
    return JsonResponse({"results": []}, safe=False)

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
        
        testcase_api_stats = cursor.fetchall()
        
        # 시간대별 API 호출 분포
        cursor.execute("""
            SELECT 
                strftime('%H', created_at) as hour,
                COUNT(*) as call_count
            FROM test_api 
            WHERE created_at BETWEEN ? AND ?
            GROUP BY hour
            ORDER BY hour
        """, (start_date.isoformat(), end_date.isoformat()))
        
        hourly_stats = cursor.fetchall()
        
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] API 대시보드 데이터 조회 실패: {e}")
        api_stats = {
            'total_calls': 0,
            'avg_response_time': 0,
            'failed_calls': 0,
            'success_rate': 0
        }
        testcase_api_stats = []
        hourly_stats = []
    
    context = {
        'api_stats': api_stats,
        'testcase_api_stats': testcase_api_stats,
        'hourly_stats': hourly_stats,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    }
    
    return render(request, 'qa_monitor/api_dashboard.html', context)

def api_performance_chart(request):
    """API 성능 차트 데이터"""
    from scripts.utils.testlog_db import get_db_connection
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 최근 24시간 API 응답시간 데이터
        cursor.execute("""
            SELECT 
                strftime('%H:%M', created_at) as time_slot,
                AVG(elapsed) as avg_response_time,
                COUNT(*) as call_count
            FROM test_api 
            WHERE created_at >= datetime('now', '-24 hours')
            GROUP BY strftime('%H', created_at)
            ORDER BY time_slot
        """)
        
        performance_data = cursor.fetchall()
        conn.close()
        
        chart_data = {
            'labels': [row[0] for row in performance_data],
            'response_times': [float(row[1]) if row[1] else 0 for row in performance_data],
            'call_counts': [row[2] for row in performance_data]
        }
        
    except Exception as e:
        chart_data = {
            'labels': [],
            'response_times': [],
            'call_counts': []
        }
    
    return JsonResponse(chart_data)

def api_error_analysis(request):
    """API 오류 분석"""
    from scripts.utils.testlog_db import get_db_connection
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 오류별 통계
        cursor.execute("""
            SELECT 
                status_code,
                COUNT(*) as error_count,
                AVG(elapsed) as avg_response_time
            FROM test_api 
            WHERE status_code >= 400
            GROUP BY status_code
            ORDER BY error_count DESC
        """)
        
        error_stats = cursor.fetchall()
        
        # 엔드포인트별 오류율
        cursor.execute("""
            SELECT 
                endpoint,
                COUNT(*) as total_calls,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_calls,
                AVG(elapsed) as avg_response_time
            FROM test_api 
            GROUP BY endpoint
            HAVING error_calls > 0
            ORDER BY (CAST(error_calls AS FLOAT) / total_calls) DESC
            LIMIT 10
        """)
        
        endpoint_errors = cursor.fetchall()
        
        conn.close()
        
    except Exception as e:
        error_stats = []
        endpoint_errors = []
    
    context = {
        'error_stats': error_stats,
        'endpoint_errors': endpoint_errors
    }
    
    return render(request, 'qa_monitor/api_error_analysis.html', context)

def menu_api_logs(request):
    """메뉴별 API 로그"""
    from scripts.utils.testlog_db import get_db_connection
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 메뉴별 API 호출 통계
        cursor.execute("""
            SELECT 
                test_case_id,
                COUNT(*) as api_count,
                AVG(elapsed) as avg_response_time,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count
            FROM test_api 
            GROUP BY test_case_id
            ORDER BY api_count DESC
            LIMIT 20
        """)
        
        menu_api_stats = cursor.fetchall()
        
        conn.close()
        
    except Exception as e:
        menu_api_stats = []
    
    context = {
        'menu_api_stats': menu_api_stats
    }
    
    return render(request, 'qa_monitor/menu_api_logs.html', context)

def extract_menu_from_title(title):
    """제목에서 메뉴명 추출"""
    if not title:
        return "Unknown"
    
    # 간단한 메뉴 추출 로직
    menu_keywords = ['로그인', '회원가입', '프로필', '검색', '시청', '다운로드', '설정']
    
    for keyword in menu_keywords:
        if keyword in title:
            return keyword
    
    return title.split('_')[0] if '_' in title else title