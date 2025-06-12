# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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