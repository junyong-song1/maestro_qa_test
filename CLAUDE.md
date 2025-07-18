# CLAUDE (QA 자동화 규칙 및 구현)

## 1. 파일명 기반 YAML 매칭
- 테스트케이스 ID와 매칭되는 YAML 파일은 반드시 `TC{case_id}_` 패턴의 파일명으로 저장한다.
- YAML 파일 내 메타데이터(`testrail_case_id`)가 없어도, 파일명만 맞으면 자동으로 매칭되어 실행된다.
- 파일명만 맞추면 별도의 내용 수정 없이 바로 테스트가 가능하다.

## 2. TestRail 연동 및 자동화
- TestRail에서 suite_id, custom_automation_type(2) 필드 기준으로 테스트케이스를 조회한다.
- Automation Type이 Maestro(2)인 케이스만 필터링하여 실행한다.
- 테스트 실행 후 결과는 즉시 TestRail에 업로드된다.
- 테스트 런(run) 생성 및 결과 업로드 시, run_id, status_id 등 TestRail API 규격을 준수한다.

## 3. 스크린샷 자동 저장 (v2.0.0)
- 성공/실패 모든 테스트에서 스크린샷을 자동으로 저장한다.
- 저장 방식: `adb shell screencap + adb pull` 방식으로 안정성 확보
- 저장 위치: `artifacts/images/{YYYYMMDD}/TC{case_id}_{serial}_{status}_{timestamp}.png`
- TestRail 연동: 이미지 파일을 첨부파일로 자동 업로드
- 재시도 로직: 최대 3회 재시도로 안정성 향상

## 4. API 트래픽 캡처 (v2.0.0)
- mitmproxy를 통한 실시간 네트워크 모니터링
- tving.com 도메인만 필터링하여 관련성 확보
- SQLite DB에 요청/응답, 응답시간, 상태코드 저장
- TestRail 코멘트에 API 통계 자동 포함

## 5. SQLite 데이터베이스 관리 (v2.0.0)
- 테스트 로그: 각 테스트 단계별 실행 시간, 상태, 에러 정보
- API 데이터: 네트워크 요청/응답 상세 정보
- 성능 분석: 응답시간 통계, 실패 패턴 분석
- WAL 모드: 동시 접근 시 안정성 확보

## 6. Django 웹 대시보드 (v2.0.0)
- 실시간 테스트 상태 모니터링
- TestRail 결과 통계 표시
- 최근 실행 이력 조회
- 개별 테스트케이스/런 상세 정보

## 7. 실행 및 관리
- main.py를 통해 전체 자동화 테스트를 실행한다.
- 실행 로그에 각 단계별 상세 정보(디바이스, 케이스, 업로드 결과 등)가 기록된다.
- requirements.txt, .gitignore 등 프로젝트 관리 규칙을 준수한다.

## 8. 현업 요구사항 반영
- 현업 QA 자동화 요구사항(파일명만 맞추면 실행, 결과 자동 업로드 등)을 100% 반영한다.
- 스크린샷 자동 저장으로 시각적 증거 확보
- API 트래픽 캡처로 백엔드 검증 가능
- 웹 대시보드로 실시간 모니터링

## Project Overview

This is a test automation project that integrates Maestro (mobile UI testing) with TestRail for test execution and result reporting. The system automatically runs mobile test flows, collects artifacts, and uploads results to TestRail.

## Architecture

The project follows this workflow:
1. **TestRail Integration**: Fetches test cases from TestRail suite
2. **Maestro Flow Execution**: Maps TestRail cases to YAML flow files in `maestro_flows/`
3. **Test Execution**: Runs tests via Maestro with ADB device integration
4. **Result Collection**: Captures logs, screenshots, video recordings, and logcat data
5. **API Traffic Capture**: Captures network requests/responses using mitmproxy
6. **Database Storage**: Stores test logs and API data in SQLite database
7. **Result Upload**: Uploads test results and artifacts back to TestRail
8. **Web Dashboard**: Provides real-time monitoring via Django web interface

### Key Components

- **Main Runner**: `scripts/core/main.py` - System entry point
- **Application**: `scripts/core/application.py` - Orchestrates the entire testing workflow
- **Test Runner**: `scripts/core/test_runner.py` - Maestro-based test execution engine
- **TestRail API**: `scripts/testrail/testrail.py` - Creates test runs in TestRail
- **Device Manager**: `scripts/device/device_manager.py` - Android device discovery and management
- **Config Manager**: `scripts/config/config_manager.py` - Centralized configuration management
- **API Capture**: `scripts/utils/api_capture.py` - Network traffic capture and analysis
- **Database**: `scripts/utils/testlog_db.py` - SQLite database management
- **Maestro Flows**: `maestro_flows/*.yaml` - Test case definitions mapped by TestRail case IDs
- **Django Dashboard**: `dashboard/` - Web-based monitoring system
- **Configuration**: `config.ini` - TestRail credentials and project settings (excluded from git)

## Essential Commands

### Setup and Installation
```bash
# Complete setup (creates venv, installs dependencies, runs tests)
bash install_and_run.sh

# Manual setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration
```bash
# Copy example config (required before first run)
cp config/config.ini.example config/config.ini
# Edit config.ini with your TestRail credentials

# Setup mitmproxy for API capture
mitmdump --set confdir=~/.mitmproxy
```

### Running Tests
```bash
# Full automated test suite
python3 scripts/core/main.py

# Specific suite test execution
python3 scripts/core/main.py --suite_id 1798

# Create TestRail run only
python3 scripts/create_testrail_run.py --suite_id 1787

# Individual Maestro flow
maestro test maestro_flows/qa_flows/TC314789_채널명&카테고리.yaml

# Multi-device test
python3 multi_device_test.py
```

### Web Dashboard
```bash
# Start Django dashboard
bash run_dashboard.sh

# Or manual execution
cd dashboard
python3 manage.py runserver 0.0.0.0:8000
```

### Device Requirements
- Android device connected via ADB
- TVING app installed (package: net.cj.cjhv.gs.tving)
- ADB debugging enabled
- mitmproxy certificate installed (for API capture)

## Flow Naming Convention

Maestro flows must follow the pattern: `TC{case_id}_{description}.yaml`
- Example: `TC314789_채널명&카테고리.yaml` maps to TestRail case ID 314789
- `TC00000_앱시작.yaml` is always executed first as app initialization

## Special Features

### Dynamic YAML Substitution
Flows can use placeholders:
- `{{DATE}}` - Replaced with YYYYMMDD
- `{{TIME}}` - Replaced with HHMMSS

### Screenshot Automation (v2.0.0)
- Automatic screenshot capture for all tests (success/failure)
- Storage location: `artifacts/images/{YYYYMMDD}/TC{case_id}_{serial}_{status}_{timestamp}.png`
- TestRail integration: Images automatically uploaded as attachments
- Retry logic: Up to 3 retries for stability

### API Traffic Capture (v2.0.0)
- Real-time network monitoring using mitmproxy
- Domain filtering: Only tving.com requests captured
- SQLite storage: Request/response, timing, status codes
- TestRail integration: API statistics included in comments

### Logcat Integration
For video playback test cases (TC313859, TC313889), the system:
- Captures MediaStateObserver logcat during execution
- Analyzes for "IS PLAYING (FINAL_STATE:3)" to determine playback success

### Database Management (v2.0.0)
- Test logs: Step-by-step execution details
- API data: Network request/response details
- Performance analysis: Response time statistics
- WAL mode: Concurrent access stability

### Web Dashboard (v2.0.0)
- Real-time test status monitoring
- TestRail result statistics
- Recent execution history
- Individual test case/run details

## Artifact Management
- Screenshots/videos saved to `artifacts/images/{YYYYMMDD}/`
- Logcat files automatically collected and attached to failed tests
- API data stored in `artifacts/test_log.db`
- Large files (mp4) automatically excluded from git via .gitignore

## Security Notes

- Never commit `config.ini` - contains TestRail API credentials
- Use `config.ini.example` as template
- All sensitive data is gitignored automatically
- mitmproxy certificates should be properly configured
- API capture data filtered to relevant domains only

## Version History

### v2.0.0 (2024-12-17)
- ✅ Screenshot auto-save for all tests (success/failure)
- ✅ API traffic capture with mitmproxy + SQLite DB
- ✅ TestRail image attachment auto-upload
- ✅ Django web dashboard
- ✅ Class-based architecture refactoring
- ✅ SQLite database integration

### v1.0.0 (2024-12-01)
- ✅ Basic Maestro test automation
- ✅ TestRail integration
- ✅ Multi-device support