# Mint Linux mitmdump 설치 가이드

## 1. Python pip를 통한 설치 (권장)

### 1.1 시스템 업데이트
```bash
sudo apt update
sudo apt upgrade
```

### 1.2 Python 및 pip 설치 확인
```bash
python3 --version
pip3 --version
```

### 1.3 mitmproxy 설치
```bash
pip3 install mitmproxy
```

### 1.4 설치 확인
```bash
mitmdump --version
```

## 2. 시스템 패키지 매니저를 통한 설치

### 2.1 APT를 통한 설치
```bash
sudo apt update
sudo apt install mitmproxy
```

## 3. 설치 후 설정

### 3.1 mitmdump 실행 테스트
```bash
# 기본 실행 (포트 8080)
mitmdump

# 특정 포트로 실행
mitmdump -p 8081

# 파일로 저장
mitmdump -w output.dump
```

### 3.2 인증서 설정 (HTTPS 트래픽 캡처용)
```bash
# 인증서 생성
mitmdump --set confdir=~/.mitmproxy

# 인증서 위치 확인
ls ~/.mitmproxy/
```

## 4. QA 자동화 프로젝트에서 사용

### 4.1 프로젝트 설정
```bash
# 프로젝트 디렉토리로 이동
cd qa_auto_test_project

# 가상환경 생성 (선택사항)
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 4.2 mitmdump 실행
```bash
# 백그라운드에서 실행
mitmdump -w artifacts/api_dump.dump &

# 또는 특정 포트로 실행
mitmdump -p 8080 -w artifacts/api_dump.dump &
```

## 5. 문제 해결

### 5.1 권한 문제
```bash
# pip 설치 시 권한 문제가 있다면
pip3 install --user mitmproxy

# 또는 sudo 사용 (권장하지 않음)
sudo pip3 install mitmproxy
```

### 5.2 포트 충돌
```bash
# 사용 중인 포트 확인
sudo netstat -tlnp | grep :8080

# 다른 포트 사용
mitmdump -p 8081
```

### 5.3 Python 버전 문제
```bash
# Python 3.7 이상 필요
python3 --version

# 가상환경 사용 권장
python3 -m venv mitmproxy_env
source mitmproxy_env/bin/activate
pip install mitmproxy
```

## 6. 자동화 스크립트 예시

### 6.1 mitmdump 시작 스크립트
```bash
#!/bin/bash
# start_mitmdump.sh

DUMP_FILE="artifacts/api_$(date +%Y%m%d_%H%M%S).dump"
PORT=8080

echo "Starting mitmdump on port $PORT..."
echo "Dump file: $DUMP_FILE"

mitmdump -p $PORT -w "$DUMP_FILE" &
MITM_PID=$!

echo "mitmdump started with PID: $MITM_PID"
echo $MITM_PID > mitmdump.pid
```

### 6.2 mitmdump 종료 스크립트
```bash
#!/bin/bash
# stop_mitmdump.sh

if [ -f mitmdump.pid ]; then
    PID=$(cat mitmdump.pid)
    echo "Stopping mitmdump (PID: $PID)..."
    kill $PID
    rm mitmdump.pid
    echo "mitmdump stopped"
else
    echo "No mitmdump PID file found"
fi
```

## 7. 설정 파일 예시

### 7.1 ~/.mitmproxy/config.yaml
```yaml
# mitmproxy 설정 파일
confdir: ~/.mitmproxy
port: 8080
ssl_insecure: true
```

## 8. 모니터링 및 로그

### 8.1 로그 확인
```bash
# 실시간 로그 확인
tail -f ~/.mitmproxy/mitmproxy.log

# 특정 도메인만 필터링
mitmdump -w output.dump --set "filter=~d tving.com"
```

### 8.2 성능 모니터링
```bash
# 메모리 사용량 확인
ps aux | grep mitmdump

# 네트워크 연결 확인
netstat -an | grep :8080
```

## 9. 보안 고려사항

### 9.1 방화벽 설정
```bash
# 특정 IP만 허용
sudo ufw allow from 192.168.1.0/24 to any port 8080

# 또는 로컬만 허용
sudo ufw allow from 127.0.0.1 to any port 8080
```

### 9.2 인증서 관리
```bash
# 인증서 백업
cp ~/.mitmproxy/mitmproxy-ca-cert.pem ~/backup/

# 인증서 복원
cp ~/backup/mitmproxy-ca-cert.pem ~/.mitmproxy/
```

## 10. 트러블슈팅

### 10.1 일반적인 오류
```bash
# ImportError: No module named 'mitmproxy'
pip3 install --upgrade mitmproxy

# Permission denied
sudo chown -R $USER:$USER ~/.mitmproxy/

# Port already in use
sudo lsof -i :8080
sudo kill -9 <PID>
```

### 10.2 성능 최적화
```bash
# 메모리 제한 설정
mitmdump --set "flow_detail=0" -w output.dump

# 디스크 공간 모니터링
df -h | grep artifacts
```

---

**참고**: 이 가이드는 Mint Linux 20.x 이상을 기준으로 작성되었습니다. 