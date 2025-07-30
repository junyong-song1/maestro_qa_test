#!/usr/bin/env python3
"""
API 패턴 분석 및 이상 감지 시스템
API 호출 패턴 학습 및 비정상 패턴 감지
"""

import sqlite3
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re

logger = logging.getLogger(__name__)

class APIPatternAnalyzer:
    """API 패턴 분석 클래스"""
    
    def __init__(self, db_path: str = "artifacts/test_log.db"):
        self.db_path = db_path
        self.pattern_cache = {}
        self.anomaly_threshold = 0.1  # 10% 이상 차이나면 이상으로 판단
        
    def analyze_api_patterns(self, hours: int = 24) -> Dict:
        """API 호출 패턴 분석"""
        try:
            api_data = self._get_api_data(hours)
            if not api_data:
                return {"status": "no_data", "message": "분석할 데이터가 없습니다."}
            
            # 다양한 패턴 분석
            patterns = {
                "endpoint_frequency": self._analyze_endpoint_frequency(api_data),
                "method_distribution": self._analyze_method_distribution(api_data),
                "status_code_patterns": self._analyze_status_patterns(api_data),
                "timing_patterns": self._analyze_timing_patterns(api_data),
                "request_sequences": self._analyze_request_sequences(api_data),
                "anomalies": self._detect_anomalies(api_data)
            }
            
            return {
                "status": "success",
                "patterns": patterns,
                "analysis_period": f"최근 {hours}시간",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"패턴 분석 실패: {e}")
            return {"status": "error", "message": str(e)}
    
    def _get_api_data(self, hours: int) -> List[Dict]:
        """API 데이터 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            cursor.execute("""
                SELECT url, method, status_code, elapsed, created_at, test_case_id, serial
                FROM test_api 
                WHERE created_at > ?
                ORDER BY created_at ASC
            """, (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'),))
            
            results = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'url': row[0],
                    'method': row[1],
                    'status_code': row[2],
                    'elapsed': row[3],
                    'created_at': row[4],
                    'test_case_id': row[5],
                    'serial': row[6]
                }
                for row in results
            ]
            
        except Exception as e:
            logger.error(f"API 데이터 조회 실패: {e}")
            return []
    
    def _analyze_endpoint_frequency(self, api_data: List[Dict]) -> Dict:
        """엔드포인트 호출 빈도 분석"""
        endpoint_counter = Counter()
        endpoint_methods = defaultdict(set)
        
        for item in api_data:
            url = item.get('url', '')
            method = item.get('method', 'GET')
            
            # URL 정규화 (쿼리 파라미터 제거)
            normalized_url = re.sub(r'\?.*$', '', url)
            endpoint_counter[normalized_url] += 1
            endpoint_methods[normalized_url].add(method)
        
        # 상위 10개 엔드포인트
        top_endpoints = endpoint_counter.most_common(10)
        
        return {
            "total_unique_endpoints": len(endpoint_counter),
            "top_endpoints": [
                {
                    "url": endpoint,
                    "count": count,
                    "percentage": (count / len(api_data)) * 100,
                    "methods": list(endpoint_methods[endpoint])
                }
                for endpoint, count in top_endpoints
            ],
            "endpoint_distribution": dict(endpoint_counter)
        }
    
    def _analyze_method_distribution(self, api_data: List[Dict]) -> Dict:
        """HTTP 메서드 분포 분석"""
        method_counter = Counter()
        
        for item in api_data:
            method = item.get('method', 'GET')
            method_counter[method] += 1
        
        total_requests = len(api_data)
        
        return {
            "total_requests": total_requests,
            "method_distribution": [
                {
                    "method": method,
                    "count": count,
                    "percentage": (count / total_requests) * 100
                }
                for method, count in method_counter.most_common()
            ]
        }
    
    def _analyze_status_patterns(self, api_data: List[Dict]) -> Dict:
        """상태 코드 패턴 분석"""
        status_counter = Counter()
        status_by_endpoint = defaultdict(Counter)
        
        for item in api_data:
            status = item.get('status_code', 200)
            url = re.sub(r'\?.*$', '', item.get('url', ''))
            
            status_counter[status] += 1
            status_by_endpoint[url][status] += 1
        
        # 오류 패턴 분석
        error_patterns = []
        for endpoint, statuses in status_by_endpoint.items():
            error_count = sum(count for status, count in statuses.items() if status >= 400)
            total_count = sum(statuses.values())
            error_rate = (error_count / total_count) * 100 if total_count > 0 else 0
            
            if error_rate > 5:  # 5% 이상 오류율
                error_patterns.append({
                    "endpoint": endpoint,
                    "error_rate": error_rate,
                    "total_requests": total_count,
                    "error_requests": error_count,
                    "status_breakdown": dict(statuses)
                })
        
        return {
            "status_distribution": [
                {
                    "status_code": status,
                    "count": count,
                    "percentage": (count / len(api_data)) * 100
                }
                for status, count in status_counter.most_common()
            ],
            "error_patterns": sorted(error_patterns, key=lambda x: x['error_rate'], reverse=True)
        }
    
    def _analyze_timing_patterns(self, api_data: List[Dict]) -> Dict:
        """타이밍 패턴 분석"""
        timing_data = []
        
        for item in api_data:
            elapsed = item.get('elapsed')
            if elapsed:
                timing_data.append(float(elapsed))
        
        if not timing_data:
            return {"message": "타이밍 데이터가 없습니다."}
        
        # 시간대별 분석
        hourly_timing = defaultdict(list)
        for item in api_data:
            if item.get('elapsed'):
                created_at = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
                hour = created_at.hour
                hourly_timing[hour].append(float(item['elapsed']))
        
        hourly_stats = {}
        for hour, times in hourly_timing.items():
            hourly_stats[hour] = {
                "avg_response_time": sum(times) / len(times),
                "max_response_time": max(times),
                "min_response_time": min(times),
                "request_count": len(times)
            }
        
        return {
            "overall_timing": {
                "avg_response_time": sum(timing_data) / len(timing_data),
                "max_response_time": max(timing_data),
                "min_response_time": min(timing_data),
                "total_requests": len(timing_data)
            },
            "hourly_timing": dict(hourly_stats)
        }
    
    def _analyze_request_sequences(self, api_data: List[Dict]) -> Dict:
        """요청 시퀀스 패턴 분석"""
        # 테스트 케이스별 시퀀스 분석
        test_sequences = defaultdict(list)
        
        for item in api_data:
            test_case_id = item.get('test_case_id')
            if test_case_id:
                url = re.sub(r'\?.*$', '', item.get('url', ''))
                test_sequences[test_case_id].append(url)
        
        # 공통 시퀀스 패턴 찾기
        sequence_patterns = []
        for test_case_id, sequence in test_sequences.items():
            if len(sequence) >= 3:  # 3개 이상의 요청이 있는 시퀀스만
                sequence_patterns.append({
                    "test_case_id": test_case_id,
                    "sequence": sequence,
                    "length": len(sequence)
                })
        
        # 가장 긴 시퀀스 찾기
        longest_sequence = max(sequence_patterns, key=lambda x: x['length']) if sequence_patterns else None
        
        return {
            "total_test_cases": len(test_sequences),
            "sequence_patterns": sequence_patterns,
            "longest_sequence": longest_sequence,
            "avg_sequence_length": sum(len(seq) for seq in test_sequences.values()) / len(test_sequences) if test_sequences else 0
        }
    
    def _detect_anomalies(self, api_data: List[Dict]) -> List[Dict]:
        """이상 패턴 감지"""
        anomalies = []
        
        # 1. 비정상적으로 긴 응답 시간
        response_times = [float(item.get('elapsed', 0)) for item in api_data if item.get('elapsed')]
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            threshold = avg_response_time * 3  # 평균의 3배
            
            for item in api_data:
                if item.get('elapsed') and float(item['elapsed']) > threshold:
                    anomalies.append({
                        "type": "slow_response",
                        "severity": "high",
                        "message": f"비정상적으로 긴 응답 시간: {item['elapsed']}초",
                        "url": item.get('url'),
                        "method": item.get('method'),
                        "value": float(item['elapsed']),
                        "threshold": threshold
                    })
        
        # 2. 높은 오류율 엔드포인트
        endpoint_errors = defaultdict(lambda: {"total": 0, "errors": 0})
        for item in api_data:
            url = re.sub(r'\?.*$', '', item.get('url', ''))
            endpoint_errors[url]["total"] += 1
            if item.get('status_code', 200) >= 400:
                endpoint_errors[url]["errors"] += 1
        
        for url, stats in endpoint_errors.items():
            error_rate = (stats["errors"] / stats["total"]) * 100
            if error_rate > 20:  # 20% 이상 오류율
                anomalies.append({
                    "type": "high_error_rate",
                    "severity": "critical",
                    "message": f"높은 오류율 엔드포인트: {error_rate:.1f}%",
                    "url": url,
                    "error_rate": error_rate,
                    "total_requests": stats["total"],
                    "error_requests": stats["errors"]
                })
        
        # 3. 비정상적인 요청 빈도
        endpoint_frequency = Counter()
        for item in api_data:
            url = re.sub(r'\?.*$', '', item.get('url', ''))
            endpoint_frequency[url] += 1
        
        if endpoint_frequency:
            avg_frequency = sum(endpoint_frequency.values()) / len(endpoint_frequency)
            threshold = avg_frequency * 2  # 평균의 2배
            
            for url, count in endpoint_frequency.items():
                if count > threshold:
                    anomalies.append({
                        "type": "high_frequency",
                        "severity": "medium",
                        "message": f"비정상적으로 높은 호출 빈도: {count}회",
                        "url": url,
                        "count": count,
                        "threshold": threshold
                    })
        
        return anomalies
    
    def generate_pattern_report(self) -> str:
        """패턴 분석 리포트 생성"""
        analysis = self.analyze_api_patterns(24)  # 24시간 분석
        
        if analysis.get('status') != 'success':
            return f"리포트 생성 실패: {analysis.get('message', 'Unknown error')}"
        
        patterns = analysis['patterns']
        
        report = f"""
=== API 패턴 분석 리포트 ===
분석 기간: {analysis['analysis_period']}
생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 엔드포인트 호출 빈도 (상위 5개):
"""
        
        if patterns.get('endpoint_frequency', {}).get('top_endpoints'):
            for endpoint in patterns['endpoint_frequency']['top_endpoints'][:5]:
                report += f"- {endpoint['url']}\n"
                report += f"  호출 수: {endpoint['count']}회 ({endpoint['percentage']:.1f}%)\n"
                report += f"  메서드: {', '.join(endpoint['methods'])}\n"
        else:
            report += "- 데이터가 없습니다.\n"
        
        report += f"\n🔍 HTTP 메서드 분포:\n"
        method_dist = patterns.get('method_distribution')
        if isinstance(method_dist, dict) and 'method_distribution' in method_dist:
            method_list = method_dist['method_distribution']
        elif isinstance(method_dist, list):
            method_list = method_dist
        else:
            method_list = []

        if method_list:
            for method_info in method_list:
                if isinstance(method_info, dict):
                    report += f"- {method_info.get('method', 'Unknown')}: {method_info.get('count', 0)}회 ({method_info.get('percentage', 0):.1f}%)\n"
        else:
            report += "- 데이터가 없습니다.\n"
        
        # 오류 패턴
        error_patterns = patterns.get('status_patterns', {}).get('error_patterns', [])
        if error_patterns:
            report += f"\n🚨 오류율이 높은 엔드포인트:\n"
            for error in error_patterns[:3]:
                report += f"- {error['endpoint']}: {error['error_rate']:.1f}% ({error['error_requests']}/{error['total_requests']})\n"
        
        # 이상 감지
        anomalies = patterns.get('anomalies', [])
        if anomalies:
            report += f"\n⚠️ 감지된 이상 패턴:\n"
            for anomaly in anomalies[:5]:
                severity_icon = "🔴" if anomaly.get('severity') == 'critical' else "🟡" if anomaly.get('severity') == 'high' else "🟢"
                report += f"{severity_icon} {anomaly.get('message', '')}\n"
        else:
            report += f"\n✅ 이상 패턴이 감지되지 않았습니다.\n"
        
        return report

def main():
    """테스트 실행"""
    analyzer = APIPatternAnalyzer()
    
    # 패턴 분석
    analysis = analyzer.analyze_api_patterns(6)  # 6시간 분석
    
    print("=== API 패턴 분석 결과 ===")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
    
    # 리포트 생성
    report = analyzer.generate_pattern_report()
    print("\n" + report)

if __name__ == "__main__":
    main() 