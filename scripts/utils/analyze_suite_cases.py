#!/usr/bin/env python3
"""
TestRail의 특정 테스트 스위트에 포함된 케이스들을 가져와서 내용을 출력하는 스크립트.
"""

import argparse
import sys
import json
import time
from pathlib import Path

import google.generativeai as genai
from google.api_core import exceptions

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.config.config_manager import ConfigManager
from scripts.testrail.testrail import TestRailManager
from scripts.utils.logger import get_logger

logger = get_logger(__name__)

def format_case_for_gemini(case: dict) -> str:
    """Gemini 분석을 위해 테스트 케이스 내용을 하나의 문자열로 포맷팅합니다."""
    title = case.get('title', 'N/A')
    steps = case.get('custom_steps', '스텝 정보 없음')
    expected = case.get('custom_expected', '예상 결과 정보 없음')
    
    return f"제목: {title}\\n---\\n스텝:\\n{steps}\\n---\\n예상 결과:\\n{expected}"

def analyze_with_gemini(model, case: dict) -> dict:
    """Gemini를 사용하여 단일 테스트 케이스를 분석합니다."""
    case_content = format_case_for_gemini(case)
    prompt = f"""
    당신은 모바일 앱 테스트 자동화 전문가입니다. 주어진 테스트 케이스가 Maestro 프레임워크로 자동화 가능한지 분석해주세요.

    [분류 기준]
    - "Maestro": 앱 내의 UI 요소 클릭, 텍스트 입력, 스크롤 등 일반적인 사용자 상호작용으로만 구성된 경우.
    - "Manual": 다음 중 하나라도 포함되면 수동으로 분류하세요.
        - QR 코드 스캔, 결제 시스템 연동, 외부 기기(TV, 웨어러블) 연동
        - OS 시스템 설정 변경 (e.g., WiFi, 블루투스, 알림 권한 설정)
        - 다른 앱과의 상호작용 (e.g., 카카오톡 공유, 외부 브라우저 열기)
        - 디자인, UX, 성능 등 주관적인 판단이나 육안 확인이 필요한 경우
        - SMS/전화 수신, PUSH 알림 확인 등 앱 외부에서 트리거되는 이벤트

    [요청]
    주어진 테스트 케이스 내용을 바탕으로, "Maestro" 또는 "Manual"로 분류하고 그 이유를 간결하게 설명해주세요.
    반드시 다음 JSON 형식으로만 답변해주세요:
    {{
      "classification": "Maestro",
      "reason": "모든 단계가 앱 내 UI 조작으로 이루어져 있어 자동화 가능합니다."
    }}

    ---
    [테스트 케이스 내용]
    {case_content}
    ---
    """
    for _ in range(3): # 재시도 로직
        try:
            response = model.generate_content(prompt)
            # 마크다운 코드 블록 제거
            cleaned_response = response.text.strip().lstrip('```json').rstrip('```')
            return json.loads(cleaned_response)
        except (exceptions.GoogleAPICallError, json.JSONDecodeError) as e:
            logger.warning(f"Gemini 분석 재시도 중... (케이스: C{case.get('id')}, 오류: {e})")
            time.sleep(2)
    
    return {"classification": "Error", "reason": f"API 호출 또는 JSON 파싱에 3회 실패했습니다."}


def run_analysis(suite_id: int, use_gemini: bool):
    """메인 분석 로직을 실행합니다."""
    try:
        config = ConfigManager()
        testrail_config = config.get_testrail_config()
        testrail = TestRailManager(testrail_config)
        project_id = int(testrail_config['project_id'])

        summaries = testrail.get_test_cases(project_id, suite_id)
        if not summaries:
            logger.warning("분석할 테스트 케이스가 없습니다.")
            return

        maestro_cases, manual_cases = [], []
        
        gemini_api_key = config.get('Gemini', 'api_key')
        if not use_gemini or not gemini_api_key or "YOUR" in gemini_api_key:
             logger.error("Gemini 분석이 비활성화되었거나 API 키가 유효하지 않습니다. 모든 케이스를 수동으로 분류합니다.")
             use_gemini = False # 강제로 비활성화
             # 모든 케이스를 상세 정보와 함께 수동 리스트에 추가
             for summary in summaries:
                 case = testrail.get_case(int(summary['id']))
                 if case:
                     manual_cases.append({
                         'id': case['id'], 
                         'title': case['title'], 
                         'reason': 'Gemini 분석 비활성화됨'
                     })
        
        if use_gemini:
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info(f"총 {len(summaries)}개 케이스에 대해 Gemini 분석을 시작합니다...")

            for i, summary in enumerate(summaries):
                case = testrail.get_case(int(summary['id']))
                if not case:
                    logger.warning(f"C{summary['id']} 상세 정보 로딩 실패. 건너뜁니다.")
                    continue
                
                print(f"  - 분석 중 [{i+1}/{len(summaries)}] C{case['id']}", end='\\r')
                result = analyze_with_gemini(model, case)
                case_info = {'id': case['id'], 'title': case['title'], 'reason': result.get('reason')}
                
                if result.get('classification') == 'Maestro':
                    maestro_cases.append(case_info)
                else: # Manual 또는 Error
                    manual_cases.append(case_info)
            print("\\nGemini 분석 완료.                                  ")

        # 최종 결과 출력
        total_cases = len(manual_cases) + len(maestro_cases)
        manual_percent = (len(manual_cases) / total_cases * 100) if total_cases > 0 else 0
        maestro_percent = (len(maestro_cases) / total_cases * 100) if total_cases > 0 else 0

        print("\\n" + "="*50)
        print(f"🔬 최종 분석 요약 (Suite ID: {suite_id}, Gemini: {'사용' if use_gemini else '미사용'})")
        print("="*50)
        print(f"  - 🤖 Maestro 자동화 추천: {len(maestro_cases):>4} 건 ({maestro_percent:>5.1f}%)")
        print(f"  - 🙋 수동 테스트 필요:  {len(manual_cases):>4} 건 ({manual_percent:>5.1f}%)")
        print(f"  - ✨ 총합:              {total_cases:>4} 건")
        print("="*50)

        # 상세 보고서 저장
        output_dir = project_root / "artifacts" / "analysis"
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"analysis_suite_{suite_id}_gemini.json"

        report = {
            "suite_id": suite_id,
            "analysis_type": "Gemini" if use_gemini else "Keyword-Fallback",
            "summary": {
                "total": total_cases,
                "maestro_cases": len(maestro_cases),
                "manual_cases": len(manual_cases),
                "maestro_percent": maestro_percent,
                "manual_percent": manual_percent
            },
            "maestro_cases_list": sorted(maestro_cases, key=lambda x: x['id']),
            "manual_cases_list": sorted(manual_cases, key=lambda x: x['id'])
        }

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
        
        print(f"💡 상세 보고서가 다음 경로에 저장되었습니다:\\n   {report_path}")

    except Exception as e:
        logger.error(f"스크립트 실행 중 오류 발생: {e}")


def main():
    parser = argparse.ArgumentParser(description="TestRail 스위트의 테스트 케이스를 분석하여 자동화 가능성을 분류합니다.")
    parser.add_argument("suite_id", type=int, help="분석할 TestRail 스위트의 ID")
    parser.add_argument("--gemini", action="store_true", help="Gemini AI 분석을 사용합니다. 이 옵션이 없으면 실행되지 않습니다.")
    args = parser.parse_args()

    if not args.gemini:
        logger.error("Gemini 분석을 사용하려면 --gemini 플래그를 추가해야 합니다.")
        logger.info("예: python3 scripts/utils/analyze_suite_cases.py 1798 --gemini")
        return

    run_analysis(args.suite_id, args.gemini)

if __name__ == "__main__":
    main()