#!/bin/bash

# Redis 서버 실행 확인
redis-cli ping > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Redis 서버를 시작합니다..."
    brew services start redis
fi

# 가상환경 활성화
source venv/bin/activate

# Django 마이그레이션
cd dashboard
python manage.py makemigrations
python manage.py migrate

# QA 자동화 테스트 프로세스 백그라운드로 실행
echo "QA 자동화 테스트 프로세스를 시작합니다..."
cd ..
python scripts/core/main.py &

# 개발 서버 실행
cd dashboard
echo "대시보드 서버를 시작합니다..."
python manage.py runserver 0.0.0.0:8000 