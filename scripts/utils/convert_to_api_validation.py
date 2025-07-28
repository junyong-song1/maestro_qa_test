#!/usr/bin/env python3
"""
기존 Maestro YAML을 API 검증 버전으로 변환하는 스크립트
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Any

class MaestroYAMLConverter:
    """Maestro YAML을 API 검증 버전으로 변환"""
    
    def __init__(self, flows_dir: str = "maestro_flows/qa_flows"):
        self.flows_dir = flows_dir
        self.api_templates = {
            'login': {
                'name': "로그인 API",
                'pattern': "/api/auth/login",
                'method': "POST",
                'expectedStatus': 200,
                'required': True
            },
            'content': {
                'name': "콘텐츠 로드 API",
                'pattern': "/api/content",
                'method': "GET",
                'expectedStatus': 200,
                'required': True
            },
            'profile': {
                'name': "사용자 프로필 API",
                'pattern': "/api/user/profile",
                'method': "GET",
                'expectedStatus': 200,
                'required': False
            },
            'play': {
                'name': "재생 API",
                'pattern': "/api/play",
                'method': "POST",
                'expectedStatus': 200,
                'required': True
            }
        }
    
    def detect_test_type(self, yaml_content: str) -> List[str]:
        """YAML 내용을 분석하여 테스트 타입 감지"""
        test_types = []
        
        # 로그인 관련 키워드
        if any(keyword in yaml_content for keyword in ["로그인", "login", "아이디", "비밀번호"]):
            test_types.append('login')
        
        # 콘텐츠 관련 키워드
        if any(keyword in yaml_content for keyword in ["뉴스", "영화", "시리즈", "콘텐츠", "content"]):
            test_types.append('content')
        
        # 재생 관련 키워드
        if any(keyword in yaml_content for keyword in ["재생", "play", "surface_view", "플레이어"]):
            test_types.append('play')
        
        # 프로필 관련 키워드
        if any(keyword in yaml_content for keyword in ["프로필", "profile", "사용자", "user"]):
            test_types.append('profile')
        
        return test_types
    
    def generate_api_validation_config(self, test_types: List[str]) -> str:
        """테스트 타입에 따른 API 검증 설정 생성"""
        config_lines = [
            "# API 검증 설정",
            "apiValidation:",
            "  enabled: true",
            "  expectedApis:"
        ]
        
        for test_type in test_types:
            if test_type in self.api_templates:
                template = self.api_templates[test_type]
                config_lines.extend([
                    f"    - name: \"{template['name']}\"",
                    f"      pattern: \"{template['pattern']}\"",
                    f"      method: \"{template['method']}\"",
                    f"      expectedStatus: {template['expectedStatus']}",
                    f"      required: {str(template['required']).lower()}"
                ])
        
        return "\n".join(config_lines)
    
    def convert_yaml_file(self, yaml_path: str) -> str:
        """단일 YAML 파일을 API 검증 버전으로 변환"""
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 이미 API 검증이 포함된 파일인지 확인
            if 'apiValidation:' in content:
                print(f"이미 API 검증이 포함된 파일입니다: {yaml_path}")
                return yaml_path
            
            # 테스트 타입 감지
            test_types = self.detect_test_type(content)
            print(f"감지된 테스트 타입: {test_types}")
            
            # API 검증 설정 생성
            api_config = self.generate_api_validation_config(test_types)
            
            # 새로운 파일명 생성
            base_name = os.path.splitext(yaml_path)[0]
            new_path = f"{base_name}_with_API_validation.yaml"
            
            # 새로운 내용 생성
            new_content = content.replace(
                "#ㆍ 상단에 스페셜관 배경 이미지 노출",
                "#ㆍ 상단에 스페셜관 배경 이미지 노출\n#ㆍ API 검증: " + ", ".join(test_types) + " API 호출 확인\n\n" + api_config
            )
            
            # 새 파일 저장
            with open(new_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"변환 완료: {yaml_path} → {new_path}")
            return new_path
            
        except Exception as e:
            print(f"변환 실패: {yaml_path} - {e}")
            return None
    
    def convert_all_yaml_files(self) -> List[str]:
        """모든 YAML 파일을 API 검증 버전으로 변환"""
        converted_files = []
        
        flows_path = Path(self.flows_dir)
        if not flows_path.exists():
            print(f"디렉토리가 존재하지 않습니다: {self.flows_dir}")
            return converted_files
        
        # YAML 파일들 찾기
        yaml_files = list(flows_path.glob("*.yaml"))
        yaml_files = [f for f in yaml_files if not f.name.endswith('_with_API_validation.yaml')]
        
        print(f"변환할 YAML 파일 {len(yaml_files)}개 발견")
        
        for yaml_file in yaml_files:
            converted_path = self.convert_yaml_file(str(yaml_file))
            if converted_path:
                converted_files.append(converted_path)
        
        return converted_files
    
    def create_conversion_report(self, converted_files: List[str]) -> str:
        """변환 결과 리포트 생성"""
        report = [
            "=" * 60,
            "Maestro YAML API 검증 변환 리포트",
            "=" * 60,
            f"변환 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"변환된 파일 수: {len(converted_files)}",
            ""
        ]
        
        if converted_files:
            report.append("✅ 변환된 파일들:")
            for file_path in converted_files:
                report.append(f"  - {file_path}")
        else:
            report.append("❌ 변환된 파일이 없습니다.")
        
        report.append("")
        report.append("📋 사용 방법:")
        report.append("1. 변환된 파일로 테스트 실행:")
        report.append("   python scripts/core/main.py")
        report.append("")
        report.append("2. API 검증 결과 확인:")
        report.append("   artifacts/api_validation_*.json")
        
        return "\n".join(report)

def main():
    """메인 실행 함수"""
    converter = MaestroYAMLConverter()
    
    print("🔄 Maestro YAML API 검증 변환 시작...")
    
    # 모든 YAML 파일 변환
    converted_files = converter.convert_all_yaml_files()
    
    # 결과 리포트 생성
    report = converter.create_conversion_report(converted_files)
    print("\n" + report)
    
    # 리포트 파일 저장
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = f"artifacts/conversion_report_{timestamp}.txt"
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n📄 리포트 저장: {report_path}")
    except Exception as e:
        print(f"리포트 저장 실패: {e}")

if __name__ == "__main__":
    from datetime import datetime
    main() 