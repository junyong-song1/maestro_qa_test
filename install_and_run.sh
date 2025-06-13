#!/bin/bash
set -e

echo "[1/3] Python 가상환경 생성"
python3 -m venv venv
source venv/bin/activate

echo "[2/3] requirements.txt 설치"
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/3] Maestro, adb, 기타 도구 설치 안내"
echo "Maestro: https://maestro.mobile.dev/getting-started/"
echo "adb: Android SDK Platform Tools 설치 필요"

echo "설정 파일(config.ini) 작성 여부 확인"
if [ ! -f config.ini ]; then
  echo "config.ini 파일이 없습니다. config.ini.example을 복사해서 config.ini를 만드세요."
  exit 1
fi

echo "테스트 실행"
python3 scripts/main.py
