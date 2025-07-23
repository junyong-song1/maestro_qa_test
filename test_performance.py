#!/usr/bin/env python3
"""
성능 개선 효과 테스트 스크립트
"""

import sys
import time
import subprocess
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_proxy_performance():
    """프록시 설정 성능 테스트"""
    print("🚀 프록시 설정 성능 테스트 시작...")
    
    # 1. 기존 방식 (매 테스트마다 프록시 설정)
    print("\n1. 기존 방식 테스트 (매 테스트마다 프록시 설정)...")
    start_time = time.time()
    
    for i in range(3):  # 3번 반복 테스트
        test_start = time.time()
        
        # 프록시 설정
        proxy_start = time.time()
        subprocess.run([
            "adb", "shell", "settings", "put", "global", "wifi_proxy_host", "192.168.50.49:8080"
        ], check=False, timeout=10)
        proxy_duration = time.time() - proxy_start
        
        # 프록시 해제
        cleanup_start = time.time()
        subprocess.run([
            "adb", "shell", "settings", "put", "global", "wifi_proxy_host", ":0"
        ], check=False, timeout=10)
        cleanup_duration = time.time() - cleanup_start
        
        total_duration = time.time() - test_start
        print(f"   테스트 {i+1}: 프록시 설정 {proxy_duration:.3f}초, 해제 {cleanup_duration:.3f}초, 총 {total_duration:.3f}초")
    
    old_total_time = time.time() - start_time
    print(f"   기존 방식 총 소요시간: {old_total_time:.3f}초")
    
    # 2. 개선된 방식 (한 번만 프록시 설정)
    print("\n2. 개선된 방식 테스트 (한 번만 프록시 설정)...")
    start_time = time.time()
    
    # 프록시 설정 (한 번만)
    proxy_start = time.time()
    subprocess.run([
        "adb", "shell", "settings", "put", "global", "wifi_proxy_host", "192.168.50.49:8080"
    ], check=False, timeout=10)
    proxy_duration = time.time() - proxy_start
    print(f"   프록시 설정: {proxy_duration:.3f}초")
    
    # 3번 테스트 시뮬레이션 (프록시 설정 없이)
    for i in range(3):
        test_start = time.time()
        # 실제 테스트 실행 시뮬레이션
        time.sleep(0.1)  # 100ms 시뮬레이션
        test_duration = time.time() - test_start
        print(f"   테스트 {i+1}: {test_duration:.3f}초 (프록시 설정 없음)")
    
    # 프록시 해제 (한 번만)
    cleanup_start = time.time()
    subprocess.run([
        "adb", "shell", "settings", "put", "global", "wifi_proxy_host", ":0"
    ], check=False, timeout=10)
    cleanup_duration = time.time() - cleanup_start
    print(f"   프록시 해제: {cleanup_duration:.3f}초")
    
    new_total_time = time.time() - start_time
    print(f"   개선된 방식 총 소요시간: {new_total_time:.3f}초")
    
    # 3. 성능 개선 효과 분석
    print("\n3. 성능 개선 효과 분석...")
    improvement = old_total_time - new_total_time
    improvement_percent = (improvement / old_total_time) * 100
    
    print(f"   절약된 시간: {improvement:.3f}초")
    print(f"   성능 개선률: {improvement_percent:.1f}%")
    
    if improvement > 0:
        print(f"   ✅ 성능 개선 효과: {improvement_percent:.1f}% 향상")
    else:
        print(f"   ⚠️ 성능 개선 효과 없음")

def test_maestro_performance():
    """Maestro 실행 성능 테스트"""
    print("\n🎯 Maestro 실행 성능 테스트...")
    
    # 간단한 Maestro 테스트 실행
    test_flow = "maestro_flows/qa_flows/TC314800_앱_접근권한_안내.yaml"
    
    if not Path(test_flow).exists():
        print(f"   ⚠️ 테스트 파일이 없습니다: {test_flow}")
        return
    
    print(f"   테스트 파일: {test_flow}")
    
    # 디바이스 확인
    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        if "device" not in result.stdout:
            print("   ⚠️ 연결된 디바이스가 없습니다.")
            return
        
        device_serial = result.stdout.split('\n')[1].split('\t')[0]
        print(f"   디바이스: {device_serial}")
        
    except Exception as e:
        print(f"   ⚠️ 디바이스 확인 실패: {e}")
        return
    
    # Maestro 실행 성능 측정
    print("   Maestro 실행 중...")
    start_time = time.time()
    
    try:
        result = subprocess.run([
            "maestro", f"--device={device_serial}", "test", test_flow
        ], capture_output=True, text=True, timeout=60)
        
        duration = time.time() - start_time
        print(f"   Maestro 실행 완료: {duration:.3f}초")
        print(f"   Return Code: {result.returncode}")
        
        if result.returncode == 0:
            print("   ✅ 테스트 성공")
        else:
            print("   ❌ 테스트 실패")
            
    except subprocess.TimeoutExpired:
        print("   ⏰ 테스트 타임아웃 (60초)")
    except Exception as e:
        print(f"   ❌ 테스트 실행 오류: {e}")

if __name__ == "__main__":
    print("🔧 QA 자동화 성능 테스트")
    print("=" * 50)
    
    test_proxy_performance()
    test_maestro_performance()
    
    print("\n✅ 성능 테스트 완료!") 