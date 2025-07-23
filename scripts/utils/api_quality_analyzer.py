#!/usr/bin/env python3
"""
API 기반 테스트 품질 분석기
테스트 실행 시 API 호출 패턴을 분석하여 테스트 품질을 평가합니다.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

class APIQualityAnalyzer:
    """API 기반 테스트 품질 분석기"""
    
    def __init__(self, db_path: str = "artifacts/test_log.db"):
        self.db_path = db_path
    
    def analyze_test_case_quality(self, test_case_id: str) -> Dict[str, Any]:
        """특정 테스트케이스의 품질 분석"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # API 호출 통계
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_calls,
                    AVG(elapsed) as avg_response_time,
                    COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count,
                    COUNT(DISTINCT url) as unique_endpoints,
                    MIN(elapsed) as min_response_time,
                    MAX(elapsed) as max_response_time
                FROM test_api 
                WHERE test_case_id = ?
            """, (test_case_id,))
            
            stats = cursor.fetchone()
            
            # API 호출 패턴 분석
            cursor.execute("""
                SELECT url, method, status_code, elapsed
                FROM test_api 
                WHERE test_case_id = ?
                ORDER BY created_at
            """, (test_case_id,))
            
            api_calls = cursor.fetchall()
            
            # 품질 점수 계산
            quality_score = self._calculate_quality_score(stats, api_calls)
            
            # API 호출 시퀀스 분석
            sequence_analysis = self._analyze_api_sequence(api_calls)
            
            # 성능 분석
            performance_analysis = self._analyze_performance(stats, api_calls)
            
            return {
                'test_case_id': test_case_id,
                'quality_score': quality_score,
                'api_stats': {
                    'total_calls': stats[0],
                    'avg_response_time': stats[1],
                    'error_count': stats[2],
                    'unique_endpoints': stats[3],
                    'min_response_time': stats[4],
                    'max_response_time': stats[5]
                },
                'sequence_analysis': sequence_analysis,
                'performance_analysis': performance_analysis,
                'recommendations': self._generate_recommendations(stats, api_calls)
            }
            
        finally:
            conn.close()
    
    def _calculate_quality_score(self, stats: tuple, api_calls: List[tuple]) -> float:
        """테스트 품질 점수 계산 (0-100)"""
        total_calls, avg_response, error_count, unique_endpoints, min_response, max_response = stats
        
        if total_calls == 0:
            return 0.0
        
        # 1. API 호출 수 점수 (20점)
        call_score = min(20, total_calls / 10)  # 10개 이상이면 만점
        
        # 2. 오류율 점수 (30점)
        error_rate = error_count / total_calls if total_calls > 0 else 1.0
        error_score = 30 * (1 - error_rate)  # 오류가 없을수록 높은 점수
        
        # 3. 응답 시간 점수 (25점)
        if avg_response is None or avg_response == 0:
            response_score = 0
        else:
            response_score = 25 * max(0, 1 - (avg_response / 5))  # 5초 이상이면 0점
        
        # 4. API 다양성 점수 (15점)
        diversity_score = min(15, unique_endpoints * 3)  # 5개 이상 엔드포인트면 만점
        
        # 5. 일관성 점수 (10점)
        consistency_score = 10 if len(set(call[0] for call in api_calls)) > 1 else 5
        
        total_score = call_score + error_score + response_score + diversity_score + consistency_score
        return min(100, total_score)
    
    def _analyze_api_sequence(self, api_calls: List[tuple]) -> Dict[str, Any]:
        """API 호출 시퀀스 분석"""
        if not api_calls:
            return {'pattern': 'no_calls', 'complexity': 'low'}
        
        urls = [call[0] for call in api_calls]
        methods = [call[1] for call in api_calls]
        
        # 패턴 분석
        unique_urls = len(set(urls))
        unique_methods = len(set(methods))
        
        # 복잡도 계산
        complexity = 'low'
        if unique_urls > 5:
            complexity = 'high'
        elif unique_urls > 2:
            complexity = 'medium'
        
        # 시퀀스 패턴
        if len(urls) == 1:
            pattern = 'single_endpoint'
        elif len(set(urls)) == len(urls):
            pattern = 'unique_sequence'
        else:
            pattern = 'repeated_sequence'
        
        return {
            'pattern': pattern,
            'complexity': complexity,
            'unique_urls': unique_urls,
            'unique_methods': unique_methods,
            'total_calls': len(api_calls)
        }
    
    def _analyze_performance(self, stats: tuple, api_calls: List[tuple]) -> Dict[str, Any]:
        """성능 분석"""
        total_calls, avg_response, error_count, unique_endpoints, min_response, max_response = stats
        
        # 응답 시간 분포
        response_times = [call[3] for call in api_calls if call[3] is not None]
        
        if not response_times:
            return {'status': 'no_data'}
        
        # 성능 등급
        if avg_response is None:
            performance_grade = 'unknown'
        elif avg_response < 0.5:
            performance_grade = 'excellent'
        elif avg_response < 1.0:
            performance_grade = 'good'
        elif avg_response < 2.0:
            performance_grade = 'fair'
        else:
            performance_grade = 'poor'
        
        return {
            'performance_grade': performance_grade,
            'avg_response_time': avg_response,
            'min_response_time': min_response,
            'max_response_time': max_response,
            'response_time_distribution': {
                'fast': len([rt for rt in response_times if rt < 0.5]),
                'normal': len([rt for rt in response_times if 0.5 <= rt < 2.0]),
                'slow': len([rt for rt in response_times if rt >= 2.0])
            }
        }
    
    def _generate_recommendations(self, stats: tuple, api_calls: List[tuple]) -> List[str]:
        """개선 권장사항 생성"""
        recommendations = []
        total_calls, avg_response, error_count, unique_endpoints, min_response, max_response = stats
        
        if total_calls == 0:
            recommendations.append("API 호출이 없습니다. 테스트가 제대로 실행되었는지 확인하세요.")
            return recommendations
        
        # 오류율 관련 권장사항
        error_rate = error_count / total_calls if total_calls > 0 else 0
        if error_rate > 0.1:
            recommendations.append(f"API 오류율이 높습니다 ({error_rate:.1%}). 네트워크 상태와 서버 상태를 확인하세요.")
        
        # 응답 시간 관련 권장사항
        if avg_response and avg_response > 2.0:
            recommendations.append(f"평균 응답 시간이 느립니다 ({avg_response:.2f}초). 성능 최적화가 필요합니다.")
        
        # API 다양성 관련 권장사항
        if unique_endpoints < 2:
            recommendations.append("API 호출 다양성이 낮습니다. 더 많은 엔드포인트를 테스트하세요.")
        
        # 호출 수 관련 권장사항
        if total_calls < 5:
            recommendations.append("API 호출 수가 적습니다. 더 포괄적인 테스트가 필요합니다.")
        
        return recommendations
    
    def generate_test_report(self, test_case_id: str) -> str:
        """테스트 리포트 생성"""
        analysis = self.analyze_test_case_quality(test_case_id)
        
        report = f"""
=== API 기반 테스트 품질 리포트 ===
테스트케이스: {test_case_id}
생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 품질 점수: {analysis['quality_score']:.1f}/100

📈 API 통계:
- 총 API 호출: {analysis['api_stats']['total_calls']}건
- 평균 응답시간: {analysis['api_stats']['avg_response_time']:.3f}초
- 오류 수: {analysis['api_stats']['error_count']}건
- 고유 엔드포인트: {analysis['api_stats']['unique_endpoints']}개

🔍 시퀀스 분석:
- 패턴: {analysis['sequence_analysis']['pattern']}
- 복잡도: {analysis['sequence_analysis']['complexity']}
- 고유 URL: {analysis['sequence_analysis']['unique_urls']}개

⚡ 성능 분석:
- 등급: {analysis['performance_analysis']['performance_grade']}
- 최소 응답시간: {analysis['performance_analysis']['min_response_time']:.3f}초
- 최대 응답시간: {analysis['performance_analysis']['max_response_time']:.3f}초

💡 개선 권장사항:
"""
        
        for i, rec in enumerate(analysis['recommendations'], 1):
            report += f"{i}. {rec}\n"
        
        return report

if __name__ == "__main__":
    # 사용 예시
    analyzer = APIQualityAnalyzer()
    
    # 특정 테스트케이스 분석
    test_case_id = "TC314800"
    analysis = analyzer.analyze_test_case_quality(test_case_id)
    
    print(f"테스트케이스 {test_case_id} 품질 점수: {analysis['quality_score']:.1f}/100")
    print(f"API 호출 수: {analysis['api_stats']['total_calls']}건")
    print(f"평균 응답시간: {analysis['api_stats']['avg_response_time']:.3f}초")
    
    # 리포트 생성
    report = analyzer.generate_test_report(test_case_id)
    print(report) 