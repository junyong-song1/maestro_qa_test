#!/bin/bash

# 가상환경 활성화
source venv/bin/activate

# (추가) PYTHONPATH에 프로젝트 루트 추가
export PYTHONPATH=$(pwd)

# dashboard 디렉토리로 이동
cd dashboard

# Django 마이그레이션
python manage.py makemigrations
python manage.py migrate

# Django 개발 서버 실행
echo "대시보드 서버를 시작합니다..."
python manage.py runserver 0.0.0.0:8000 