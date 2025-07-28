#!/usr/bin/env python3
"""
Maestro API 검증 유틸리티 (JSON 설정 기반)
API 호출 데이터를 검증하여 테스트 품질을 향상
"""

import sqlite3
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class MaestroAPIValidator:
    """Maestro API 검증 클래스 (JSON 설정 기반)"""
    
    def __init__(self, db_path: str = "artifacts/test_log.db"):
        self.db_path = db_path
    
    def validate_api_calls(self, test_case_id: str, expected_apis: List[Dict[str, Any]]) -> Dict[str, Any]:
        """API 호출 데이터 검증"""
        try:
            # 해당 테스트케이스의 API 호출 데이터 조회
            api_calls = self._get_api_calls_for_test_case(test_case_id)
            
            if not api_calls:
                return {
                    'status': 'SKIP',
                    'message': 'API 호출 데이터가 없습니다',
                    'test_case_id': test_case_id,
                    'validation_results': {}
                }
            
            # 각 예상 API에 대해 검증 수행
            validation_results = {}
            passed_count = 0
            failed_count = 0
            
            for expected_api in expected_apis:
                result = self._validate_single_api(expected_api, api_calls, test_case_id)
                validation_results[expected_api['name']] = result
                
                if result['status'] == 'PASS':
                    passed_count += 1
                else:
                    failed_count += 1
            
            # 예상하지 못한 API 호출 찾기
            unexpected_apis = self._find_unexpected_apis(expected_apis, api_calls)
            
            # 성능 이슈 체크
            performance_issues = self._check_performance_issues(api_calls)
            
            # 전체 상태 결정
            overall_status = 'PASS' if failed_count == 0 else 'FAIL'
            
            return {
                'status': overall_status,
                'test_case_id': test_case_id,
                'total_expected': len(expected_apis),
                'passed': passed_count,
                'failed': failed_count,
                'validation_results': validation_results,
                'unexpected_apis': unexpected_apis,
                'performance_issues': performance_issues,
                'api_calls_count': len(api_calls)
            }
            
        except Exception as e:
            logger.error(f"API 검증 실패: {e}")
            return {
                'status': 'ERROR',
                'message': str(e),
                'test_case_id': test_case_id
            }
    
    def _get_api_calls_for_test_case(self, test_case_id: str) -> List[tuple]:
        """테스트케이스별 API 호출 데이터 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 최근 30분 내의 API 호출 데이터 조회
            cutoff_time = datetime.now() - timedelta(minutes=30)
            
            cursor.execute("""
                SELECT url, method, status_code, elapsed, created_at
                FROM test_api 
                WHERE test_case_id = ? AND created_at > ?
                ORDER BY created_at DESC
            """, (test_case_id, cutoff_time.isoformat()))
            
            api_calls = cursor.fetchall()
            conn.close()
            
            return api_calls
            
        except Exception as e:
            logger.error(f"API 호출 데이터 조회 실패: {e}")
            return []
    
    def _validate_single_api(self, expected_api: Dict[str, Any], api_calls: List[tuple], test_case_id: str) -> Dict[str, Any]:
        """단일 API 검증"""
        pattern = expected_api.get('pattern', '')
        method = expected_api.get('method', 'GET')
        expected_status = expected_api.get('expected_status', 200)
        required = expected_api.get('required', True)
        
        # 패턴 매칭으로 API 호출 찾기
        matching_calls = []
        for call in api_calls:
            url, call_method, status_code, elapsed, created_at = call
            
            if (re.search(pattern, url, re.IGNORECASE) and 
                call_method.upper() == method.upper()):
                matching_calls.append({
                    'url': url,
                    'method': call_method,
                    'status_code': status_code,
                    'elapsed': elapsed,
                    'created_at': created_at
                })
        
        if not matching_calls:
            if required:
                return {
                    'status': 'FAIL',
                    'message': f'필수 API 호출이 없습니다: {pattern}',
                    'expected': expected_api,
                    'found': []
                }
            else:
                return {
                    'status': 'SKIP',
                    'message': f'선택적 API 호출이 없습니다: {pattern}',
                    'expected': expected_api,
                    'found': []
                }
        
        # 상태 코드 검증
        failed_calls = [call for call in matching_calls if call['status_code'] != expected_status]
        
        if failed_calls:
            return {
                'status': 'FAIL',
                'message': f'상태 코드 불일치: 예상 {expected_status}, 실제 {failed_calls[0]["status_code"]}',
                'expected': expected_api,
                'found': matching_calls,
                'failed_calls': failed_calls
            }
        
        # 성능 검증 (선택적)
        slow_calls = [call for call in matching_calls if call['elapsed'] > 5.0]  # 5초 이상
        
        if slow_calls:
            return {
                'status': 'WARN',
                'message': f'느린 응답 시간: {slow_calls[0]["elapsed"]:.2f}초',
                'expected': expected_api,
                'found': matching_calls,
                'slow_calls': slow_calls
            }
        
        return {
            'status': 'PASS',
            'message': f'검증 성공: {len(matching_calls)}개 호출',
            'expected': expected_api,
            'found': matching_calls
        }
    
    def _find_unexpected_apis(self, expected_apis: List[Dict[str, Any]], api_calls: List[tuple]) -> List[Dict[str, Any]]:
        """예상하지 못한 API 호출 찾기"""
        expected_patterns = [api['pattern'] for api in expected_apis]
        unexpected = []
        
        for call in api_calls:
            url, method, status_code, elapsed, created_at = call
            
            # 예상 패턴과 매칭되지 않는 API 호출
            is_expected = any(re.search(pattern, url, re.IGNORECASE) for pattern in expected_patterns)
            
            if not is_expected:
                unexpected.append({
                    'url': url,
                    'method': method,
                    'status_code': status_code,
                    'elapsed': elapsed,
                    'created_at': created_at
                })
        
        return unexpected
    
    def _check_performance_issues(self, api_calls: List[tuple]) -> List[Dict[str, Any]]:
        """성능 이슈 체크"""
        issues = []
        
        for call in api_calls:
            url, method, status_code, elapsed, created_at = call
            
            if elapsed > 10.0:  # 10초 이상
                issues.append({
                    'type': 'SLOW_RESPONSE',
                    'url': url,
                    'method': method,
                    'elapsed': elapsed,
                    'message': f'매우 느린 응답: {elapsed:.2f}초'
                })
            elif status_code >= 500:
                issues.append({
                    'type': 'SERVER_ERROR',
                    'url': url,
                    'method': method,
                    'status_code': status_code,
                    'message': f'서버 오류: {status_code}'
                })
        
        return issues
    
    def generate_validation_report(self, validation_results: Dict[str, Any]) -> str:
        """검증 결과 리포트 생성"""
        report = []
        report.append("=" * 60)
        report.append(f"API 검증 리포트 - TC{validation_results['test_case_id']}")
        report.append("=" * 60)
        report.append(f"전체 상태: {validation_results['status']}")
        report.append(f"통과: {validation_results['passed']}/{validation_results['total_expected']}")
        report.append(f"실패: {validation_results['failed']}")
        report.append(f"API 호출 수: {validation_results['api_calls_count']}")
        report.append("")
        
        # 개별 API 검증 결과
        report.append("개별 API 검증 결과:")
        report.append("-" * 40)
        
        for api_name, result in validation_results['validation_results'].items():
            status_icon = "✅" if result['status'] == 'PASS' else "❌" if result['status'] == 'FAIL' else "⚠️"
            report.append(f"{status_icon} {api_name}: {result['message']}")
        
        # 예상하지 못한 API
        if validation_results['unexpected_apis']:
            report.append("")
            report.append("예상하지 못한 API 호출:")
            report.append("-" * 40)
            for api in validation_results['unexpected_apis'][:5]:  # 상위 5개만
                report.append(f"  {api['method']} {api['url']} ({api['status_code']})")
        
        # 성능 이슈
        if validation_results['performance_issues']:
            report.append("")
            report.append("성능 이슈:")
            report.append("-" * 40)
            for issue in validation_results['performance_issues']:
                report.append(f"  {issue['message']}")
        
        report.append("=" * 60)
        return "\n".join(report)
    
    def save_validation_result(self, validation_results: Dict[str, Any], output_path: str = None) -> str:
        """검증 결과를 JSON 파일로 저장"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"artifacts/api_validation_TC{validation_results['test_case_id']}_{timestamp}.json"
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(validation_results, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"API 검증 결과 저장: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"API 검증 결과 저장 실패: {e}")
            return None

def validate_maestro_test_with_api(test_case_id: str, expected_apis: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Maestro 테스트와 API 검증 통합 실행"""
    validator = MaestroAPIValidator()
    validation_results = validator.validate_api_calls(test_case_id, expected_apis)
    report = validator.generate_validation_report(validation_results)
    print(report)
    output_path = validator.save_validation_result(validation_results)
    return {
        'status': validation_results['status'],
        'validation_results': validation_results,
        'report': report,
        'output_path': output_path
    }

if __name__ == "__main__":
    # 테스트 실행
    test_apis = [
        {
            "name": "로그인 API",
            "pattern": "/api/auth/login",
            "method": "POST",
            "expected_status": 200,
            "required": True
        },
        {
            "name": "콘텐츠 API",
            "pattern": "/api/content",
            "method": "GET",
            "expected_status": 200,
            "required": True
        }
    ]
    
    result = validate_maestro_test_with_api("TC314789", test_apis)
    print(f"검증 결과: {result['status']}") 