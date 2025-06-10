#!/bin/bash
# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt

# config.ini 체크
if [ ! -f config.ini ]; then
  echo "config.ini 파일이 없습니다. config.ini.example을 복사해서 config.ini를 만드세요."
  cp config.ini.example config.ini
  exit 1
fi

# 메인 자동화 스크립트 실행 (필요에 따라 수정)
python3 scripts/testrail_maestro_runner.py
