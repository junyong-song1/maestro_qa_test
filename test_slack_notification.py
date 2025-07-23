#!/usr/bin/env python3
"""
Slack 알림 시스템 테스트 스크립트
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scripts.utils.slack_notifier import slack_notifier, SlackMessage

def test_slack_notifications():
    """Slack 알림 시스템 테스트"""
    print("🚀 Slack 알림 시스템 테스트 시작...")
    
    # 1. 기본 메시지 테스트
    print("1. 기본 메시지 전송 테스트...")
    basic_message = SlackMessage(
        text="🧪 *Slack 알림 시스템 테스트*\n이것은 테스트 메시지입니다.",
        icon_emoji=":test_tube:"
    )
    success = slack_notifier.send_message(basic_message)
    print(f"   결과: {'성공' if success else '실패'}")
    
    # 2. 테스트 시작 알림 테스트
    print("2. 테스트 시작 알림 테스트...")
    success = slack_notifier.send_test_start_notification(
        "테스트 런 - 2025-07-21", 2, 10
    )
    print(f"   결과: {'성공' if success else '실패'}")
    
    # 3. 테스트 완료 알림 테스트 (성공)
    print("3. 테스트 완료 알림 테스트 (성공)...")
    success = slack_notifier.send_test_complete_notification(
        "테스트 런 - 2025-07-21", {"성공": 8, "실패": 2}
    )
    print(f"   결과: {'성공' if success else '실패'}")
    
    # 4. 테스트 완료 알림 테스트 (실패)
    print("4. 테스트 완료 알림 테스트 (실패)...")
    success = slack_notifier.send_test_complete_notification(
        "테스트 런 - 2025-07-21", {"성공": 2, "실패": 8}
    )
    print(f"   결과: {'성공' if success else '실패'}")
    
    # 5. 테스트 실패 알림 테스트
    print("5. 테스트 실패 알림 테스트...")
    success = slack_notifier.send_test_failure_notification(
        "314800", "앱 접근권한 안내", 
        "Element not found: id=permission_button", 
        "SM-F711N (216875cb28037ece)"
    )
    print(f"   결과: {'성공' if success else '실패'}")
    
    # 6. 성능 경고 알림 테스트
    print("6. 성능 경고 알림 테스트...")
    success = slack_notifier.send_performance_alert(
        "314860", "구매내역", 15, 2.5
    )
    print(f"   결과: {'성공' if success else '실패'}")
    
    # 7. API 에러 알림 테스트
    print("7. API 에러 알림 테스트...")
    success = slack_notifier.send_api_error_alert(
        "314865", "https://api.tving.com/v2/user/profile/info", 500, 3
    )
    print(f"   결과: {'성공' if success else '실패'}")
    
    print("\n✅ Slack 알림 시스템 테스트 완료!")

if __name__ == "__main__":
    test_slack_notifications() 