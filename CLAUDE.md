# CLAUDE (QA 자동화 규칙 및 구현)

## 1. 파일명 기반 YAML 매칭
- 테스트케이스 ID와 매칭되는 YAML 파일은 반드시 `TC{case_id}_` 패턴의 파일명으로 저장한다.
- YAML 파일 내 메타데이터(`testrail_case_id`)가 없어도, 파일명만 맞으면 자동으로 매칭되어 실행된다.
- 파일명만 맞추면 별도의 내용 수정 없이 바로 테스트가 가능하다.

## 2. TestRail 연동 및 자동화
- TestRail에서 suite_id, custom_automation_type(2: Maestro) 필드 기준으로 테스트케이스를 조회한다.
- Automation Type이 Maestro(2)인 케이스만 필터링하여 실행한다.
- 테스트 실행 후 결과는 즉시 TestRail에 업로드된다.
- 테스트 런(run) 생성 및 결과 업로드 시, run_id, status_id 등 TestRail API 규격을 준수한다.

## 3. 실행 및 관리
- main.py를 통해 전체 자동화 테스트를 실행한다.
- 실행 로그에 각 단계별 상세 정보(디바이스, 케이스, 업로드 결과 등)가 기록된다.
- requirements.txt, .gitignore 등 프로젝트 관리 규칙을 준수한다.

## 4. 현업 요구사항 반영
- 현업 QA 자동화 요구사항(파일명만 맞추면 실행, 결과 자동 업로드 등)을 100% 반영한다.

## Project Overview

This is a test automation project that integrates Maestro (mobile UI testing) with TestRail for test execution and result reporting. The system automatically runs mobile test flows, collects artifacts, and uploads results to TestRail.

## Architecture

The project follows this workflow:
1. **TestRail Integration**: Fetches test cases from TestRail suite
2. **Maestro Flow Execution**: Maps TestRail cases to YAML flow files in `maestro_flows/`
3. **Test Execution**: Runs tests via Maestro with ADB device integration
4. **Result Collection**: Captures logs, screenshots, video recordings, and logcat data
5. **Result Upload**: Uploads test results and artifacts back to TestRail

### Key Components

- **Main Runner**: `scripts/testrail_maestro_runner.py` - Orchestrates the entire testing workflow
- **TestRail API**: `scripts/create_testrail_run.py` - Creates test runs in TestRail
- **Maestro Flows**: `maestro_flows/*.yaml` - Test case definitions mapped by TestRail case IDs
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
cp config.ini.example config.ini
# Edit config.ini with your TestRail credentials
```

### Running Tests
```bash
# Full automated test suite
python3 scripts/testrail_maestro_runner.py

# Create TestRail run only
python3 scripts/create_testrail_run.py --suite_id 1787

# Individual Maestro flow
maestro test maestro_flows/TC00000_앱시작.yaml

# Multi-device test
python3 multi_device_test.py
```

### Device Requirements
- Android device connected via ADB
- TVING app installed (package: net.cj.cjhv.gs.tving)
- ADB debugging enabled

## Flow Naming Convention

Maestro flows must follow the pattern: `TC{case_id}_{description}.yaml`
- Example: `TC313762_프로필_전환.yaml` maps to TestRail case ID 313762
- `TC00000_앱시작.yaml` is always executed first as app initialization

## Special Features

### Dynamic YAML Substitution
Flows can use placeholders:
- `{{DATE}}` - Replaced with YYYYMMDD
- `{{TIME}}` - Replaced with HHMMSS

### Logcat Integration
For video playback test cases (TC313859, TC313889), the system:
- Captures MediaStateObserver logcat during execution
- Analyzes for "IS PLAYING (FINAL_STATE:3)" to determine playback success

### Artifact Management
- Screenshots/videos saved to `result/{YYYYMMDD}/`
- Logcat files automatically collected and attached to failed tests
- Large files (mp4) automatically excluded from git via .gitignore

## Security Notes

- Never commit `config.ini` - contains TestRail API credentials
- Use `config.ini.example` as template
- All sensitive data is gitignored automatically