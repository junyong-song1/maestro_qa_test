#!/usr/bin/env python3
"""
API 기반 자동 알림 시스템
API 성능 저하나 오류 발생 시 자동으로 알림을 보냅니다.
"""

import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging
from scripts.utils.slack_notifier import SlackNotifier

logger = logging.getLogger(__name__)

class APIAlertSystem:
    """API 기반 자동 알림 시스템"""
    
    def __init__(self, db_path: str = "artifacts/test_log.db"):
        self.db_path = db_path
        self.slack_notifier = SlackNotifier()
        
        # 알림 임계값 설정
        self.thresholds = {
            'error_rate': 0.1,  # 10% 이상 오류율
            'avg_response_time': 2.0,  # 2초 이상 평균 응답시간
            'max_response_time': 5.0,  # 5초 이상 최대 응답시간
            'min_api_calls': 5,  # 5개 미만 API 호출
            'consecutive_failures': 3  # 연속 3회 실패
        }
    
    def check_api_performance(self, test_case_id: str = None) -> List[Dict[str, Any]]:
        """API 성능 체크 및 알림 생성"""
        alerts = []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 최근 1시간간의 API 통계
            one_hour_ago = datetime.now() - timedelta(hours=1)
            
            if test_case_id:
                # 특정 테스트케이스 체크
                alerts.extend(self._check_specific_test_case(cursor, test_case_id, one_hour_ago))
            else:
                # 전체 API 성능 체크
                alerts.extend(self._check_overall_performance(cursor, one_hour_ago))
                alerts.extend(self._check_recent_test_cases(cursor, one_hour_ago))
            
        finally:
            conn.close()
        
        return alerts
    
    def _check_specific_test_case(self, cursor, test_case_id: str, since: datetime) -> List[Dict[str, Any]]:
        """특정 테스트케이스 성능 체크"""
        alerts = []
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_calls,
                AVG(elapsed) as avg_response_time,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count,
                MAX(elapsed) as max_response_time
            FROM test_api 
            WHERE test_case_id = ? AND created_at >= ?
        """, (test_case_id, since))
        
        stats = cursor.fetchone()
        if not stats or stats[0] == 0:
            return alerts
        
        total_calls, avg_response, error_count, max_response = stats
        error_rate = error_count / total_calls if total_calls > 0 else 0
        
        # 오류율 체크
        if error_rate > self.thresholds['error_rate']:
            alerts.append({
                'type': 'high_error_rate',
                'test_case_id': test_case_id,
                'severity': 'high',
                'message': f"테스트케이스 {test_case_id}의 API 오류율이 높습니다: {error_rate:.1%}",
                'details': {
                    'error_rate': error_rate,
                    'total_calls': total_calls,
                    'error_count': error_count
                }
            })
        
        # 응답시간 체크
        if avg_response and avg_response > self.thresholds['avg_response_time']:
            alerts.append({
                'type': 'slow_response',
                'test_case_id': test_case_id,
                'severity': 'medium',
                'message': f"테스트케이스 {test_case_id}의 평균 응답시간이 느립니다: {avg_response:.2f}초",
                'details': {
                    'avg_response_time': avg_response,
                    'max_response_time': max_response
                }
            })
        
        # API 호출 수 체크
        if total_calls < self.thresholds['min_api_calls']:
            alerts.append({
                'type': 'low_api_calls',
                'test_case_id': test_case_id,
                'severity': 'low',
                'message': f"테스트케이스 {test_case_id}의 API 호출 수가 적습니다: {total_calls}건",
                'details': {
                    'total_calls': total_calls,
                    'min_required': self.thresholds['min_api_calls']
                }
            })
        
        return alerts
    
    def _check_overall_performance(self, cursor, since: datetime) -> List[Dict[str, Any]]:
        """전체 API 성능 체크"""
        alerts = []
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_calls,
                AVG(elapsed) as avg_response_time,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count,
                COUNT(DISTINCT test_case_id) as test_cases
            FROM test_api 
            WHERE created_at >= ?
        """, (since,))
        
        stats = cursor.fetchone()
        if not stats or stats[0] == 0:
            return alerts
        
        total_calls, avg_response, error_count, test_cases = stats
        error_rate = error_count / total_calls if total_calls > 0 else 0
        
        # 전체 오류율 체크
        if error_rate > self.thresholds['error_rate']:
            alerts.append({
                'type': 'system_high_error_rate',
                'severity': 'critical',
                'message': f"전체 시스템 API 오류율이 높습니다: {error_rate:.1%}",
                'details': {
                    'error_rate': error_rate,
                    'total_calls': total_calls,
                    'error_count': error_count,
                    'test_cases': test_cases
                }
            })
        
        # 전체 응답시간 체크
        if avg_response and avg_response > self.thresholds['avg_response_time']:
            alerts.append({
                'type': 'system_slow_response',
                'severity': 'high',
                'message': f"전체 시스템 평균 응답시간이 느립니다: {avg_response:.2f}초",
                'details': {
                    'avg_response_time': avg_response,
                    'total_calls': total_calls
                }
            })
        
        return alerts
    
    def _check_recent_test_cases(self, cursor, since: datetime) -> List[Dict[str, Any]]:
        """최근 테스트케이스 연속 실패 체크"""
        alerts = []
        
        # 최근 테스트케이스별 성공/실패 상태
        cursor.execute("""
            SELECT test_case_id, 
                   COUNT(*) as total_calls,
                   COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count
            FROM test_api 
            WHERE created_at >= ?
            GROUP BY test_case_id
            ORDER BY MAX(created_at) DESC
        """, (since,))
        
        recent_tests = cursor.fetchall()
        
        for test_case_id, total_calls, error_count in recent_tests:
            if total_calls > 0:
                error_rate = error_count / total_calls
                if error_rate > self.thresholds['error_rate']:
                    alerts.append({
                        'type': 'recent_test_failure',
                        'test_case_id': test_case_id,
                        'severity': 'medium',
                        'message': f"최근 테스트케이스 {test_case_id}에서 높은 오류율 발생: {error_rate:.1%}",
                        'details': {
                            'error_rate': error_rate,
                            'total_calls': total_calls,
                            'error_count': error_count
                        }
                    })
        
        return alerts
    
    def send_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """알림 전송"""
        if not alerts:
            logger.info("발송할 알림이 없습니다.")
            return
        
        for alert in alerts:
            try:
                # Slack 알림 전송
                if alert['severity'] in ['critical', 'high']:
                    self.slack_notifier.send_api_performance_alert(
                        alert['type'],
                        alert['message'],
                        alert.get('details', {})
                    )
                
                # 로그 출력
                logger.warning(f"API 알림 [{alert['severity'].upper()}]: {alert['message']}")
                
            except Exception as e:
                logger.error(f"알림 전송 실패: {e}")
    
    def run_monitoring(self, interval_minutes: int = 5) -> None:
        """지속적인 모니터링 실행"""
        logger.info(f"API 모니터링 시작 (체크 간격: {interval_minutes}분)")
        
        while True:
            try:
                alerts = self.check_api_performance()
                self.send_alerts(alerts)
                
                logger.info(f"API 모니터링 체크 완료: {len(alerts)}개 알림")
                
                # 대기
                time.sleep(interval_minutes * 60)
                
            except KeyboardInterrupt:
                logger.info("API 모니터링 중단")
                break
            except Exception as e:
                logger.error(f"API 모니터링 오류: {e}")
                time.sleep(60)  # 오류 시 1분 대기

if __name__ == "__main__":
    # 사용 예시
    alert_system = APIAlertSystem()
    
    # 현재 API 성능 체크
    alerts = alert_system.check_api_performance()
    
    print(f"발견된 알림: {len(alerts)}개")
    for alert in alerts:
        print(f"[{alert['severity'].upper()}] {alert['message']}")
    
    # 특정 테스트케이스 체크
    test_alerts = alert_system.check_api_performance("TC314800")
    print(f"TC314800 알림: {len(test_alerts)}개")
    
    # 알림 전송
    alert_system.send_alerts(alerts) 