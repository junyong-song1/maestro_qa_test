#!/usr/bin/env python3
"""
API 성능 모니터링 및 알림 시스템
실시간 API 성능 추적 및 임계값 기반 알림
"""

import sqlite3
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class PerformanceThreshold:
    """성능 임계값 설정"""
    response_time_warning: float = 2.0  # 2초 이상 시 경고
    response_time_critical: float = 5.0  # 5초 이상 시 심각
    error_rate_warning: float = 5.0  # 5% 이상 시 경고
    error_rate_critical: float = 10.0  # 10% 이상 시 심각
    request_rate_warning: int = 100  # 분당 100개 이상 시 경고

class APIPerformanceMonitor:
    """API 성능 모니터링 클래스"""
    
    def __init__(self, db_path: str = "artifacts/test_log.db"):
        self.db_path = db_path
        self.threshold = PerformanceThreshold()
        self.alert_history = []
        
    def get_recent_api_data(self, minutes: int = 10) -> List[Dict]:
        """최근 API 데이터 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 최근 N분간의 API 데이터 조회
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            
            cursor.execute("""
                SELECT url, method, status_code, elapsed, created_at
                FROM test_api 
                WHERE created_at > ?
                ORDER BY created_at DESC
            """, (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'),))
            
            results = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'url': row[0],
                    'method': row[1],
                    'status_code': row[2],
                    'elapsed': row[3],
                    'created_at': row[4]
                }
                for row in results
            ]
            
        except Exception as e:
            logger.error(f"API 데이터 조회 실패: {e}")
            return []
    
    def analyze_performance(self, api_data: List[Dict]) -> Dict:
        """API 성능 분석"""
        if not api_data:
            return {"status": "no_data", "message": "분석할 데이터가 없습니다."}
        
        # 기본 통계 계산
        total_requests = len(api_data)
        response_times = [float(item.get('elapsed', 0)) for item in api_data if item.get('elapsed')]
        error_requests = [item for item in api_data if item.get('status_code', 200) >= 400]
        
        if not response_times:
            return {"status": "no_timing_data", "message": "응답 시간 데이터가 없습니다."}
        
        # 성능 지표 계산
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        min_response_time = min(response_times)
        error_rate = (len(error_requests) / total_requests) * 100
        
        # 엔드포인트별 분석
        endpoint_stats = self._analyze_by_endpoint(api_data)
        
        # 임계값 체크
        alerts = self._check_thresholds(avg_response_time, max_response_time, error_rate)
        
        return {
            "status": "success",
            "total_requests": total_requests,
            "avg_response_time": avg_response_time,
            "max_response_time": max_response_time,
            "min_response_time": min_response_time,
            "error_rate": error_rate,
            "endpoint_stats": endpoint_stats,
            "alerts": alerts,
            "timestamp": datetime.now().isoformat()
        }
    
    def _analyze_by_endpoint(self, api_data: List[Dict]) -> Dict:
        """엔드포인트별 성능 분석"""
        endpoint_stats = {}
        
        for item in api_data:
            url = item.get('url', 'unknown')
            method = item.get('method', 'GET')
            key = f"{method} {url}"
            
            if key not in endpoint_stats:
                endpoint_stats[key] = {
                    'count': 0,
                    'response_times': [],
                    'errors': 0,
                    'methods': set()
                }
            
            endpoint_stats[key]['count'] += 1
            endpoint_stats[key]['methods'].add(method)
            
            if item.get('elapsed'):
                endpoint_stats[key]['response_times'].append(float(item['elapsed']))
            
            if item.get('status_code', 200) >= 400:
                endpoint_stats[key]['errors'] += 1
        
        # 통계 계산
        for key, stats in endpoint_stats.items():
            if stats['response_times']:
                stats['avg_response_time'] = sum(stats['response_times']) / len(stats['response_times'])
                stats['max_response_time'] = max(stats['response_times'])
                stats['error_rate'] = (stats['errors'] / stats['count']) * 100
            else:
                stats['avg_response_time'] = 0
                stats['max_response_time'] = 0
                stats['error_rate'] = 0
            
            # 불필요한 데이터 제거
            del stats['response_times']
            stats['methods'] = list(stats['methods'])
        
        return endpoint_stats
    
    def _check_thresholds(self, avg_response_time: float, max_response_time: float, error_rate: float) -> List[Dict]:
        """임계값 체크 및 알림 생성"""
        alerts = []
        
        # 응답 시간 체크
        if avg_response_time > self.threshold.response_time_critical:
            alerts.append({
                "level": "critical",
                "type": "response_time",
                "message": f"평균 응답 시간이 임계값을 초과했습니다: {avg_response_time:.2f}초 (임계값: {self.threshold.response_time_critical}초)",
                "value": avg_response_time,
                "threshold": self.threshold.response_time_critical
            })
        elif avg_response_time > self.threshold.response_time_warning:
            alerts.append({
                "level": "warning",
                "type": "response_time",
                "message": f"평균 응답 시간이 경고 임계값을 초과했습니다: {avg_response_time:.2f}초 (임계값: {self.threshold.response_time_warning}초)",
                "value": avg_response_time,
                "threshold": self.threshold.response_time_warning
            })
        
        # 최대 응답 시간 체크
        if max_response_time > self.threshold.response_time_critical * 2:
            alerts.append({
                "level": "critical",
                "type": "max_response_time",
                "message": f"최대 응답 시간이 매우 높습니다: {max_response_time:.2f}초",
                "value": max_response_time,
                "threshold": self.threshold.response_time_critical * 2
            })
        
        # 오류율 체크
        if error_rate > self.threshold.error_rate_critical:
            alerts.append({
                "level": "critical",
                "type": "error_rate",
                "message": f"오류율이 심각한 수준입니다: {error_rate:.1f}% (임계값: {self.threshold.error_rate_critical}%)",
                "value": error_rate,
                "threshold": self.threshold.error_rate_critical
            })
        elif error_rate > self.threshold.error_rate_warning:
            alerts.append({
                "level": "warning",
                "type": "error_rate",
                "message": f"오류율이 경고 수준입니다: {error_rate:.1f}% (임계값: {self.threshold.error_rate_warning}%)",
                "value": error_rate,
                "threshold": self.threshold.error_rate_warning
            })
        
        return alerts
    
    def get_performance_trends(self, hours: int = 24) -> Dict:
        """성능 트렌드 분석"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 시간별 성능 데이터 조회
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            cursor.execute("""
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                    COUNT(*) as request_count,
                    AVG(elapsed) as avg_response_time,
                    MAX(elapsed) as max_response_time,
                    COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count
                FROM test_api 
                WHERE created_at > ?
                GROUP BY strftime('%Y-%m-%d %H:00:00', created_at)
                ORDER BY hour
            """, (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'),))
            
            results = cursor.fetchall()
            conn.close()
            
            trends = []
            for row in results:
                hour, request_count, avg_response_time, max_response_time, error_count = row
                error_rate = (error_count / request_count * 100) if request_count > 0 else 0
                
                trends.append({
                    'hour': hour,
                    'request_count': request_count,
                    'avg_response_time': avg_response_time or 0,
                    'max_response_time': max_response_time or 0,
                    'error_rate': error_rate
                })
            
            return {"status": "success", "trends": trends}
            
        except Exception as e:
            logger.error(f"트렌드 분석 실패: {e}")
            return {"status": "error", "message": str(e)}
    
    def generate_performance_report(self) -> str:
        """성능 리포트 생성"""
        # 최근 데이터 분석
        recent_data = self.get_recent_api_data(30)  # 30분간
        analysis = self.analyze_performance(recent_data)
        
        if analysis.get('status') != 'success':
            return f"리포트 생성 실패: {analysis.get('message', 'Unknown error')}"
        
        # 트렌드 분석
        trends = self.get_performance_trends(6)  # 6시간간
        
        # 리포트 생성
        report = f"""
=== API 성능 모니터링 리포트 ===
생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 최근 30분 성능 지표:
- 총 요청 수: {analysis['total_requests']:,}개
- 평균 응답 시간: {analysis['avg_response_time']:.3f}초
- 최대 응답 시간: {analysis['max_response_time']:.3f}초
- 오류율: {analysis['error_rate']:.1f}%

🚨 알림 상태:
"""
        
        if analysis['alerts']:
            for alert in analysis['alerts']:
                level_icon = "🔴" if alert['level'] == 'critical' else "🟡"
                report += f"{level_icon} {alert['message']}\n"
        else:
            report += "✅ 모든 지표가 정상 범위입니다.\n"
        
        # 엔드포인트별 성능
        report += "\n📈 엔드포인트별 성능 (상위 5개):\n"
        endpoint_stats = analysis['endpoint_stats']
        sorted_endpoints = sorted(endpoint_stats.items(), 
                                key=lambda x: x[1]['avg_response_time'], 
                                reverse=True)[:5]
        
        for endpoint, stats in sorted_endpoints:
            report += f"- {endpoint}\n"
            report += f"  요청 수: {stats['count']}개, "
            report += f"평균 응답: {stats['avg_response_time']:.3f}초, "
            report += f"오류율: {stats['error_rate']:.1f}%\n"
        
        return report

def main():
    """테스트 실행"""
    monitor = APIPerformanceMonitor()
    
    # 성능 분석
    recent_data = monitor.get_recent_api_data(10)
    analysis = monitor.analyze_performance(recent_data)
    
    print("=== API 성능 분석 결과 ===")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
    
    # 리포트 생성
    report = monitor.generate_performance_report()
    print("\n" + report)

if __name__ == "__main__":
    main() 