#!/usr/bin/env python3
"""
LLM 기반 테스트 결과 요약기
간단한 Ollama 통합으로 테스트 결과를 자연어로 요약
"""

import requests
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class LLMSummarizer:
    """LLM을 사용한 테스트 결과 요약 클래스"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.model = "llama3.2"  # 기본 모델
        
    def test_ollama_connection(self) -> bool:
        """Ollama 연결 테스트"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama 연결 실패: {e}")
            return False
    
    def generate_summary(self, test_results: List[Dict]) -> str:
        """테스트 결과 요약 생성"""
        if not self.test_ollama_connection():
            return "LLM 서비스가 사용할 수 없습니다."
        
        # 테스트 결과 데이터 준비
        summary_data = {
            "total_tests": len(test_results),
            "passed": len([r for r in test_results if r.get('status') == 'passed']),
            "failed": len([r for r in test_results if r.get('status') == 'failed']),
            "skipped": len([r for r in test_results if r.get('status') == 'skipped']),
            "execution_time": sum(float(r.get('elapsed', 0)) for r in test_results),
            "test_cases": [r.get('title', 'Unknown') for r in test_results[:5]]  # 상위 5개만
        }
        
        # 프롬프트 생성
        prompt = self._create_summary_prompt(summary_data)
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '요약 생성 실패')
            else:
                return f"LLM 요청 실패: {response.status_code}"
                
        except Exception as e:
            logger.error(f"LLM 요약 생성 오류: {e}")
            return f"요약 생성 중 오류 발생: {e}"
    
    def _create_summary_prompt(self, data: Dict) -> str:
        """요약 프롬프트 생성"""
        return f"""
다음 QA 테스트 결과를 간단하고 명확하게 요약해주세요:

테스트 통계:
- 전체 테스트 수: {data['total_tests']}개
- 성공: {data['passed']}개
- 실패: {data['failed']}개
- 건너뜀: {data['skipped']}개
- 총 실행 시간: {data['execution_time']:.2f}초

주요 테스트 케이스:
{', '.join(data['test_cases'])}

요약 요청사항:
1. 전체적인 테스트 결과 상태
2. 주요 문제점이나 개선사항
3. 다음 단계 권장사항

한국어로 간결하게 작성해주세요.
"""
    
    def analyze_api_performance(self, api_data: List[Dict]) -> str:
        """API 성능 데이터 분석"""
        if not api_data:
            return "분석할 API 데이터가 없습니다."
        
        # API 성능 통계 계산
        response_times = [float(item.get('elapsed', 0)) for item in api_data if item.get('elapsed')]
        error_count = len([item for item in api_data if item.get('status_code', 200) >= 400])
        
        if not response_times:
            return "응답 시간 데이터가 없습니다."
        
        stats = {
            "total_requests": len(api_data),
            "avg_response_time": sum(response_times) / len(response_times),
            "max_response_time": max(response_times),
            "min_response_time": min(response_times),
            "error_rate": (error_count / len(api_data)) * 100
        }
        
        prompt = f"""
다음 API 성능 데이터를 분석해주세요:

API 통계:
- 총 요청 수: {stats['total_requests']}개
- 평균 응답 시간: {stats['avg_response_time']:.3f}초
- 최대 응답 시간: {stats['max_response_time']:.3f}초
- 최소 응답 시간: {stats['min_response_time']:.3f}초
- 오류율: {stats['error_rate']:.1f}%

분석 요청사항:
1. 성능 상태 평가
2. 잠재적 문제점
3. 개선 권장사항

한국어로 간결하게 작성해주세요.
"""
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', 'API 성능 분석 실패')
            else:
                return f"LLM 요청 실패: {response.status_code}"
                
        except Exception as e:
            logger.error(f"API 성능 분석 오류: {e}")
            return f"분석 중 오류 발생: {e}"

def create_test_summary(test_results: List[Dict], api_data: Optional[List[Dict]] = None) -> Dict[str, str]:
    """테스트 결과 요약 생성 (편의 함수)"""
    summarizer = LLMSummarizer()
    
    summary = {
        "test_summary": summarizer.generate_summary(test_results),
        "api_analysis": summarizer.analyze_api_performance(api_data) if api_data else "API 데이터 없음"
    }
    
    return summary

if __name__ == "__main__":
    # 테스트용 샘플 데이터
    sample_results = [
        {"title": "로그인 테스트", "status": "passed", "elapsed": "5.2"},
        {"title": "프로필 전환", "status": "failed", "elapsed": "3.1"},
        {"title": "콘텐츠 재생", "status": "passed", "elapsed": "8.7"}
    ]
    
    sample_api_data = [
        {"url": "/api/login", "status_code": 200, "elapsed": 0.5},
        {"url": "/api/profile", "status_code": 200, "elapsed": 0.3},
        {"url": "/api/content", "status_code": 500, "elapsed": 2.1}
    ]
    
    summary = create_test_summary(sample_results, sample_api_data)
    print("=== 테스트 결과 요약 ===")
    print(summary["test_summary"])
    print("\n=== API 성능 분석 ===")
    print(summary["api_analysis"]) 