# QA 자동화 테스트 프로젝트

## 📋 개요
TVING 모바일 앱을 위한 고도화된 QA 자동화 테스트 시스템입니다.

### 🚀 주요 기능
- **멀티 디바이스 병렬 테스트**: 여러 Android 디바이스에서 동시 테스트 실행
- **Maestro 기반 UI 자동화**: 직관적인 YAML 기반 테스트 플로우
- **TestRail 완전 연동**: 테스트 결과 자동 업로드 및 첨부파일 관리
- **실시간 대시보드**: Django 기반 웹 모니터링 시스템
- **API 트래픽 캡처**: mitmproxy를 통한 네트워크 요청/응답 분석
- **스크린샷 자동 저장**: 성공/실패 모든 테스트의 시각적 증거
- **SQLite 데이터베이스**: 테스트 로그 및 API 데이터 체계적 관리

### 🎯 테스트 대상
- **앱**: TVING Android 앱 (Package: `net.cj.cjhv.gs.tving`)
- **플랫폼**: Android 디바이스 (ADB 연결 지원)
- **테스트 유형**: UI 자동화, API 검증, 성능 모니터링

---

## 🛠 설치 및 설정

### 1. 저장소 클론
```bash
git clone https://github.com/junyong-song1/maestro_qa_test.git
cd maestro_qa_test
```

### 2. 자동 설치 및 실행
```bash
bash install_and_run.sh
```
- Python 가상환경 생성
- 의존성 패키지 설치
- 설정 파일 초기화
- 테스트 자동 실행

### 3. 수동 설치
```bash
# 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 설정 파일 복사 및 편집
cp config/config.ini.example config/config.ini
# config.ini 파일을 편집하여 TestRail 정보 입력
```

---

## 📁 프로젝트 구조

```
qa_auto_test_project/
├── scripts/                          # 핵심 자동화 스크립트
│   ├── core/                         # 메인 애플리케이션
│   │   ├── main.py                   # 진입점
│   │   ├── application.py            # 전체 워크플로우 오케스트레이션
│   │   └── test_runner.py            # Maestro 테스트 실행 엔진
│   ├── config/                       # 설정 관리
│   │   └── config_manager.py         # 중앙화된 설정 관리 (싱글톤)
│   ├── device/                       # 디바이스 관리
│   │   └── device_manager.py         # Android 디바이스 발견 및 관리
│   ├── testrail/                     # TestRail 연동
│   │   └── testrail.py               # TestRail API 통합 관리
│   └── utils/                        # 유틸리티
│       ├── api_capture.py            # API 트래픽 캡처 및 DB 저장
│       ├── testlog_db.py             # SQLite 데이터베이스 관리
│       └── logger.py                 # 구조화된 로깅 시스템
├── maestro_flows/                    # Maestro 테스트 플로우
│   ├── qa_flows/                     # 메인 테스트 케이스
│   │   ├── TC314789_채널명&카테고리.yaml
│   │   ├── TC314790_클립타이틀.yaml
│   │   └── ...                       # 80+ 테스트 케이스
│   └── sub_flows/                    # 공통 플로우 모듈
├── dashboard/                        # Django 웹 대시보드
│   ├── qa_monitor/                   # QA 모니터링 앱
│   └── manage.py                     # Django 관리
├── artifacts/                        # 테스트 결과 및 로그
│   ├── logs/                         # 디바이스별 로그
│   ├── images/                       # 스크린샷 저장소
│   ├── result/                       # 테스트 결과 파일
│   └── test_log.db                   # SQLite 데이터베이스
├── config/                           # 설정 파일
│   ├── config.ini.example            # 설정 예시
│   └── config.ini                    # 실제 설정 (git 제외)
└── requirements.txt                  # Python 의존성
```

---

## 🚀 사용법

### 1. 기본 테스트 실행
```bash
# 전체 자동화 테스트 실행
python3 scripts/core/main.py

# 특정 스위트 테스트 실행
python3 scripts/core/main.py --suite_id 1798
```

### 2. 웹 대시보드 실행
```bash
# Django 대시보드 시작
bash run_dashboard.sh

# 또는 수동 실행
cd dashboard
python3 manage.py runserver 0.0.0.0:8000
```

### 3. 개별 Maestro 플로우 실행
```bash
# 특정 테스트 케이스 실행
maestro test maestro_flows/qa_flows/TC314789_채널명&카테고리.yaml

# 특정 디바이스에서 실행
maestro --device=emulator-5554 test maestro_flows/qa_flows/TC314789_채널명&카테고리.yaml
```

---

## 🔧 핵심 기능 상세

### 1. 스크린샷 자동 저장
- **저장 방식**: `adb shell screencap + adb pull` 방식으로 안정성 확보
- **저장 위치**: `artifacts/images/{YYYYMMDD}/TC{case_id}_{serial}_{status}_{timestamp}.png`
- **저장 조건**: 성공/실패 모든 테스트에서 자동 저장
- **TestRail 연동**: 이미지 파일을 첨부파일로 자동 업로드

### 2. API 트래픽 캡처
- **캡처 도구**: mitmproxy를 통한 실시간 네트워크 모니터링
- **필터링**: tving.com 도메인만 저장하여 관련성 확보
- **데이터 저장**: SQLite DB에 요청/응답, 응답시간, 상태코드 저장
- **분석 기능**: TestRail 코멘트에 API 통계 자동 포함

### 3. TestRail 완전 연동
- **자동 런 생성**: 테스트 실행 시 자동으로 TestRail 런 생성
- **결과 업로드**: 각 테스트 완료 후 즉시 결과 업로드
- **첨부파일 관리**: 스크린샷, 로그, 영상 파일 자동 첨부
- **상세 코멘트**: 디바이스별 결과, API 통계, 에러 상세 정보 포함

### 4. SQLite 데이터베이스 관리
- **테스트 로그**: 각 테스트 단계별 실행 시간, 상태, 에러 정보
- **API 데이터**: 네트워크 요청/응답 상세 정보
- **성능 분석**: 응답시간 통계, 실패 패턴 분석
- **WAL 모드**: 동시 접근 시 안정성 확보

---

## 📊 모니터링 및 대시보드

### 웹 대시보드 기능
- **실시간 상태**: 현재 테스트 실행 상태 모니터링
- **결과 통계**: 성공/실패/차단/미테스트 케이스 통계
- **최근 실행 이력**: 최근 테스트 런 목록 및 결과
- **상세 정보**: 개별 테스트케이스 및 테스트런 상세 정보

### 접속 방법
```
URL: http://localhost:8000
기본 페이지: /qa_monitor/dashboard/
```

---

## ⚙️ 설정

### TestRail 설정 (config/config.ini)
```ini
[TestRail]
url = https://your-instance.testrail.io/
username = your-email@company.com
api_key = your-api-key
project_id = 29
suite_id = 1798
```

### 앱 설정
```ini
[App]
package_name = net.cj.cjhv.gs.tving
```

---

## 🔍 자주 발생하는 오류 및 해결방법

### 1. YAML 문법 오류
**증상**: Maestro 플로우 실행 시 파싱 오류
**해결방법**:
- `---` 구분자는 반드시 한 번만 사용
- 들여쓰기는 스페이스 2개 사용
- 파일 인코딩을 UTF-8로 설정

### 2. Maestro 명령 미지원
**증상**: 특정 Maestro 명령어 실행 실패
**해결방법**:
- 공식 Maestro 명령어만 사용 (`assertVisible`, `tapOn` 등)
- 최신 Maestro 버전으로 업데이트

### 3. TestRail 업로드 실패
**증상**: 테스트 결과 업로드 시 오류
**해결방법**:
- API Key 유효성 확인
- 네트워크 연결 상태 확인
- TestRail 케이스 ID 매핑 확인

### 4. 스크린샷 저장 실패
**증상**: 스크린샷 파일이 깨지거나 저장되지 않음
**해결방법**:
- `adb exec-out` 방식에서 `adb shell screencap + adb pull` 방식으로 변경됨
- 디바이스 연결 상태 확인
- 저장소 공간 확인

### 5. pip 설치 오류
**증상**: 의존성 패키지 설치 실패
**해결방법**:
- 가상환경(venv) 활성화 후 설치
- Python 버전 확인 (3.8 이상 권장)
- 네트워크 프록시 설정 확인

---

## 🛡️ 보안 및 협업

### 민감 정보 관리
- `config.ini` 파일은 `.gitignore`에 포함되어 버전 관리에서 제외
- API Key, 비밀번호 등은 환경변수 또는 별도 보안 저장소 사용 권장
- `config.ini.example` 파일을 템플릿으로 사용

### Git 관리
- 로그, 결과, 임시 파일은 `.gitignore`로 자동 제외
- 대용량 파일(mp4 등)은 수동으로 정리 필요
- 커밋 전 민감 정보 노출 여부 확인

---

## 📈 성능 최적화

### 병렬 처리
- 멀티 디바이스 동시 테스트 실행
- 비동기 로그 수집 및 업로드
- 메모리 효율적인 스트리밍 처리

### 리소스 관리
- 테스트 실행 시간 제한 (300초)
- 임시 파일 자동 정리
- 메모리 사용량 최적화

---

## 🔄 업데이트 및 유지보수

### 정기 정리 작업
```bash
# 오래된 로그 및 결과 파일 정리
python3 scripts/utils/clean_old_logs_and_results.py

# 임시 YAML 파일 정리
python3 scripts/utils/clean_tmp_yaml.py
```

### 데이터베이스 관리
```bash
# 테스트 로그 통계 확인
python3 scripts/utils/testlog_db.py
```

---

## 📄 라이선스
MIT License

---

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📞 지원 및 문의

- **이슈 리포트**: GitHub Issues 사용
- **기능 요청**: GitHub Discussions 활용
- **문서 개선**: Pull Request로 기여

---

## 📝 변경 이력

### v2.0.0 (2024-12-17)
- ✅ 스크린샷 자동 저장 기능 추가 (성공/실패 모두)
- ✅ API 트래픽 캡처 및 SQLite DB 저장
- ✅ TestRail 이미지 첨부파일 자동 업로드
- ✅ Django 웹 대시보드 추가
- ✅ 클래스 기반 아키텍처로 리팩토링
- ✅ SQLite 데이터베이스 통합 관리

### v1.0.0 (2024-12-01)
- ✅ 기본 Maestro 테스트 자동화
- ✅ TestRail 연동
- ✅ 멀티 디바이스 지원
