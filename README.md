# QA 자동화 테스트 프로젝트

## 개요
- 멀티 디바이스 병렬 테스트, Maestro, TestRail 연동, 실시간 대시보드 지원
- 실전 운영/협업/보안/오픈소스 환경에 최적화

## 설치 방법

```bash
git clone https://github.com/your-org/qa_auto_test_project.git
cd qa_auto_test_project
bash install_and_run.sh
```

## 주요 파일 구조
- `scripts/` : 주요 자동화 스크립트
- `maestro_flows/` : 테스트 케이스 YAML
- `config.ini` : 환경설정 (민감정보는 .gitignore 필수)
- `requirements.txt` : Python 의존성
- `install_and_run.sh` : 설치 및 실행 자동화

## 사용법

```bash
bash install_and_run.sh
```
- 설치 및 환경설정, 테스트 자동 실행

## TestRail 연동
- 환경설정: `config.ini`에 TestRail 정보 입력
- 결과 업로드/코멘트/첨부파일 정책: README 내 상세 기술

## 보안/협업
- `config.ini` 등 민감정보는 `.gitignore`에 반드시 추가
- PR/이슈/기여 가이드 포함

## 자주 발생하는 오류/FAQ
- YAML 문법 오류: `---`는 반드시 한 번만, 들여쓰기/인코딩(UTF-8) 주의
- Maestro 명령 미지원: 공식 명령어(`assertVisible` 등)만 사용
- pip 설치 오류: 가상환경(venv) 활성화 후 설치 권장
- shard-all 오류: 포트 충돌, 자원 경합 시 딜레이/순차 실행 등 우회
- TestRail 업로드 실패: API Key, 네트워크, 케이스 ID 매핑 확인

## 라이선스
MIT License

## 기타
- 불필요한 로그, 결과, 임시 파일 등은 .gitignore로 자동 제외됩니다.
- mp4 등 대용량 파일은 직접 삭제해 주세요.
