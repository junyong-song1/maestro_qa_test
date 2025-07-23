#!/usr/bin/env python3
"""
API 기반 테스트 최적화 제안 시스템
API 호출 패턴을 분석하여 테스트 효율성을 높이는 방안을 제안합니다.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class APIOptimizationAdvisor:
    """API 기반 테스트 최적화 제안 시스템"""
    
    def __init__(self, db_path: str = "artifacts/test_log.db"):
        self.db_path = db_path
    
    def analyze_test_efficiency(self, test_case_id: str = None) -> Dict[str, Any]:
        """테스트 효율성 분석"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            if test_case_id:
                return self._analyze_specific_test_case(cursor, test_case_id)
            else:
                return self._analyze_all_test_cases(cursor)
        finally:
            conn.close()
    
    def _analyze_specific_test_case(self, cursor, test_case_id: str) -> Dict[str, Any]:
        """특정 테스트케이스 효율성 분석"""
        # API 호출 패턴 분석
        cursor.execute("""
            SELECT url, method, status_code, elapsed, created_at
            FROM test_api 
            WHERE test_case_id = ?
            ORDER BY created_at
        """, (test_case_id,))
        
        api_calls = cursor.fetchall()
        
        if not api_calls:
            return {
                'test_case_id': test_case_id,
                'efficiency_score': 0,
                'optimization_suggestions': ['API 호출이 없습니다. 테스트가 제대로 실행되었는지 확인하세요.']
            }
        
        # 효율성 분석
        efficiency_analysis = self._calculate_efficiency_score(api_calls)
        
        # 중복 API 호출 분석
        duplicate_analysis = self._analyze_duplicate_calls(api_calls)
        
        # 불필요한 API 호출 분석
        unnecessary_analysis = self._analyze_unnecessary_calls(api_calls)
        
        # 최적화 제안
        suggestions = self._generate_optimization_suggestions(
            efficiency_analysis, duplicate_analysis, unnecessary_analysis
        )
        
        return {
            'test_case_id': test_case_id,
            'efficiency_score': efficiency_analysis['score'],
            'api_call_count': len(api_calls),
            'unique_endpoints': efficiency_analysis['unique_endpoints'],
            'duplicate_calls': duplicate_analysis['duplicate_count'],
            'unnecessary_calls': unnecessary_analysis['unnecessary_count'],
            'optimization_suggestions': suggestions,
            'detailed_analysis': {
                'efficiency': efficiency_analysis,
                'duplicates': duplicate_analysis,
                'unnecessary': unnecessary_analysis
            }
        }
    
    def _analyze_all_test_cases(self, cursor) -> Dict[str, Any]:
        """전체 테스트케이스 효율성 분석"""
        # 테스트케이스별 효율성 통계
        cursor.execute("""
            SELECT 
                test_case_id,
                COUNT(*) as total_calls,
                COUNT(DISTINCT url) as unique_endpoints,
                AVG(elapsed) as avg_response_time,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count
            FROM test_api 
            GROUP BY test_case_id
            ORDER BY total_calls DESC
        """)
        
        test_cases = cursor.fetchall()
        
        # 전체 통계
        total_calls = sum(tc[1] for tc in test_cases)
        total_unique_endpoints = len(set(tc[2] for tc in test_cases))
        avg_response_time = sum(tc[3] or 0 for tc in test_cases) / len(test_cases) if test_cases else 0
        total_errors = sum(tc[4] for tc in test_cases)
        
        # 효율성 점수 계산
        efficiency_score = self._calculate_overall_efficiency(
            total_calls, total_unique_endpoints, avg_response_time, total_errors
        )
        
        # 최적화 기회 분석
        optimization_opportunities = self._identify_optimization_opportunities(test_cases)
        
        return {
            'overall_efficiency_score': efficiency_score,
            'total_test_cases': len(test_cases),
            'total_api_calls': total_calls,
            'total_unique_endpoints': total_unique_endpoints,
            'avg_response_time': avg_response_time,
            'total_errors': total_errors,
            'optimization_opportunities': optimization_opportunities,
            'test_case_rankings': [
                {
                    'test_case_id': tc[0],
                    'efficiency_score': self._calculate_test_case_efficiency(tc),
                    'total_calls': tc[1],
                    'unique_endpoints': tc[2],
                    'avg_response_time': tc[3],
                    'error_count': tc[4]
                }
                for tc in test_cases
            ]
        }
    
    def _calculate_efficiency_score(self, api_calls: List[Tuple]) -> Dict[str, Any]:
        """효율성 점수 계산"""
        if not api_calls:
            return {'score': 0, 'unique_endpoints': 0}
        
        urls = [call[0] for call in api_calls]
        response_times = [call[3] for call in api_calls if call[3] is not None]
        status_codes = [call[2] for call in api_calls]
        
        # 고유 엔드포인트 수
        unique_endpoints = len(set(urls))
        
        # 응답 시간 효율성 (빠를수록 높은 점수)
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        response_efficiency = max(0, 1 - (avg_response_time / 5))  # 5초 이상이면 0점
        
        # 오류율 효율성 (오류가 없을수록 높은 점수)
        error_count = sum(1 for code in status_codes if code >= 400)
        error_efficiency = 1 - (error_count / len(status_codes)) if status_codes else 1
        
        # API 다양성 효율성 (적절한 다양성)
        diversity_efficiency = min(1, unique_endpoints / 10)  # 10개 이상이면 만점
        
        # 중복 호출 효율성 (중복이 적을수록 높은 점수)
        duplicate_efficiency = 1 - (len(urls) - unique_endpoints) / len(urls) if urls else 1
        
        # 종합 점수
        total_score = (
            response_efficiency * 0.3 +
            error_efficiency * 0.3 +
            diversity_efficiency * 0.2 +
            duplicate_efficiency * 0.2
        ) * 100
        
        return {
            'score': total_score,
            'unique_endpoints': unique_endpoints,
            'avg_response_time': avg_response_time,
            'error_count': error_count,
            'duplicate_count': len(urls) - unique_endpoints
        }
    
    def _analyze_duplicate_calls(self, api_calls: List[Tuple]) -> Dict[str, Any]:
        """중복 API 호출 분석"""
        url_counts = {}
        for call in api_calls:
            url = call[0]
            url_counts[url] = url_counts.get(url, 0) + 1
        
        duplicate_calls = {url: count for url, count in url_counts.items() if count > 1}
        
        return {
            'duplicate_count': sum(count - 1 for count in duplicate_calls.values()),
            'duplicate_urls': duplicate_calls,
            'potential_savings': len(duplicate_calls)
        }
    
    def _analyze_unnecessary_calls(self, api_calls: List[Tuple]) -> Dict[str, Any]:
        """불필요한 API 호출 분석"""
        unnecessary_calls = []
        
        for i, call in enumerate(api_calls):
            url, method, status_code, elapsed = call[0], call[1], call[2], call[3]
            
            # 4xx, 5xx 오류는 불필요한 호출로 간주
            if status_code >= 400:
                unnecessary_calls.append({
                    'index': i,
                    'url': url,
                    'reason': f'HTTP {status_code} 오류',
                    'status_code': status_code
                })
            
            # 응답시간이 너무 긴 호출
            elif elapsed and elapsed > 3.0:
                unnecessary_calls.append({
                    'index': i,
                    'url': url,
                    'reason': f'응답시간 {elapsed:.2f}초 (3초 초과)',
                    'response_time': elapsed
                })
        
        return {
            'unnecessary_count': len(unnecessary_calls),
            'unnecessary_calls': unnecessary_calls
        }
    
    def _generate_optimization_suggestions(self, efficiency: Dict, duplicates: Dict, unnecessary: Dict) -> List[str]:
        """최적화 제안 생성"""
        suggestions = []
        
        # 효율성 기반 제안
        if efficiency['score'] < 70:
            suggestions.append("전체적인 API 호출 효율성이 낮습니다. 테스트 시나리오를 재검토하세요.")
        
        if efficiency['avg_response_time'] > 2.0:
            suggestions.append(f"평균 응답시간이 느립니다 ({efficiency['avg_response_time']:.2f}초). 네트워크 최적화를 고려하세요.")
        
        # 중복 호출 기반 제안
        if duplicates['duplicate_count'] > 0:
            suggestions.append(f"중복 API 호출이 {duplicates['duplicate_count']}건 있습니다. 캐싱이나 호출 최적화를 고려하세요.")
        
        # 불필요한 호출 기반 제안
        if unnecessary['unnecessary_count'] > 0:
            suggestions.append(f"불필요한 API 호출이 {unnecessary['unnecessary_count']}건 있습니다. 오류 처리와 타임아웃 설정을 개선하세요.")
        
        # 구체적인 제안
        if efficiency['unique_endpoints'] < 3:
            suggestions.append("API 호출 다양성이 낮습니다. 더 많은 엔드포인트를 테스트하세요.")
        
        if efficiency['error_count'] > 0:
            suggestions.append(f"API 오류가 {efficiency['error_count']}건 발생했습니다. 네트워크 상태와 서버 상태를 확인하세요.")
        
        return suggestions
    
    def _calculate_overall_efficiency(self, total_calls: int, unique_endpoints: int, avg_response: float, total_errors: int) -> float:
        """전체 효율성 점수 계산"""
        if total_calls == 0:
            return 0.0
        
        # 호출 수 효율성 (적절한 수)
        call_efficiency = min(1, total_calls / 100)  # 100개 이상이면 만점
        
        # 다양성 효율성
        diversity_efficiency = min(1, unique_endpoints / 20)  # 20개 이상이면 만점
        
        # 응답시간 효율성
        response_efficiency = max(0, 1 - (avg_response / 3))  # 3초 이상이면 0점
        
        # 오류율 효율성
        error_efficiency = 1 - (total_errors / total_calls) if total_calls > 0 else 1
        
        return (call_efficiency * 0.25 + diversity_efficiency * 0.25 + 
                response_efficiency * 0.25 + error_efficiency * 0.25) * 100
    
    def _calculate_test_case_efficiency(self, test_case_data: Tuple) -> float:
        """테스트케이스별 효율성 점수"""
        total_calls, unique_endpoints, avg_response, error_count = test_case_data[1:]
        
        if total_calls == 0:
            return 0.0
        
        # 간단한 효율성 계산
        diversity_score = min(1, unique_endpoints / 10)
        response_score = max(0, 1 - (avg_response or 0) / 3)
        error_score = 1 - (error_count / total_calls)
        
        return (diversity_score * 0.4 + response_score * 0.3 + error_score * 0.3) * 100
    
    def _identify_optimization_opportunities(self, test_cases: List[Tuple]) -> List[Dict[str, Any]]:
        """최적화 기회 식별"""
        opportunities = []
        
        # 효율성이 낮은 테스트케이스
        low_efficiency_cases = []
        for tc in test_cases:
            efficiency = self._calculate_test_case_efficiency(tc)
            if efficiency < 60:
                low_efficiency_cases.append({
                    'test_case_id': tc[0],
                    'efficiency_score': efficiency,
                    'issue': '낮은 효율성'
                })
        
        if low_efficiency_cases:
            opportunities.append({
                'type': 'low_efficiency',
                'description': '효율성이 낮은 테스트케이스들',
                'count': len(low_efficiency_cases),
                'cases': low_efficiency_cases
            })
        
        # API 호출이 많은 테스트케이스
        high_call_cases = [tc for tc in test_cases if tc[1] > 20]
        if high_call_cases:
            opportunities.append({
                'type': 'high_api_calls',
                'description': 'API 호출이 많은 테스트케이스들',
                'count': len(high_call_cases),
                'cases': [{'test_case_id': tc[0], 'call_count': tc[1]} for tc in high_call_cases]
            })
        
        return opportunities
    
    def generate_optimization_report(self, test_case_id: str = None) -> str:
        """최적화 리포트 생성"""
        analysis = self.analyze_test_efficiency(test_case_id)
        
        if test_case_id:
            # 특정 테스트케이스 리포트
            report = f"""
=== API 기반 테스트 최적화 리포트 ===
테스트케이스: {test_case_id}
생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 효율성 점수: {analysis['efficiency_score']:.1f}/100

📈 API 통계:
- 총 API 호출: {analysis['api_call_count']}건
- 고유 엔드포인트: {analysis['unique_endpoints']}개
- 중복 호출: {analysis['duplicate_calls']}건
- 불필요한 호출: {analysis['unnecessary_calls']}건

💡 최적화 제안:
"""
            for i, suggestion in enumerate(analysis['optimization_suggestions'], 1):
                report += f"{i}. {suggestion}\n"
        else:
            # 전체 리포트
            report = f"""
=== 전체 API 기반 테스트 최적화 리포트 ===
생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 전체 효율성 점수: {analysis['overall_efficiency_score']:.1f}/100

📈 전체 통계:
- 테스트케이스 수: {analysis['total_test_cases']}개
- 총 API 호출: {analysis['total_api_calls']}건
- 고유 엔드포인트: {analysis['total_unique_endpoints']}개
- 평균 응답시간: {analysis['avg_response_time']:.3f}초
- 총 오류 수: {analysis['total_errors']}건

🎯 최적화 기회:
"""
            for opp in analysis['optimization_opportunities']:
                report += f"- {opp['description']}: {opp['count']}개\n"
        
        return report

if __name__ == "__main__":
    # 사용 예시
    advisor = APIOptimizationAdvisor()
    
    # 특정 테스트케이스 분석
    test_analysis = advisor.analyze_test_efficiency("TC314800")
    print(f"TC314800 효율성 점수: {test_analysis['efficiency_score']:.1f}/100")
    
    # 전체 분석
    overall_analysis = advisor.analyze_test_efficiency()
    print(f"전체 효율성 점수: {overall_analysis['overall_efficiency_score']:.1f}/100")
    
    # 리포트 생성
    report = advisor.generate_optimization_report("TC314800")
    print(report) 