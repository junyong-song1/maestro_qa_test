import requests
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SlackMessage:
    """Slack 메시지 데이터 클래스"""
    text: str
    channel: str = "#qa-automation"
    username: str = "QA Auto Bot"
    icon_emoji: str = ":robot_face:"
    attachments: Optional[List[Dict]] = None

class SlackNotifier:
    """Slack 알림 시스템 클래스"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or self._get_webhook_url()
        self.logger = logging.getLogger("SlackNotifier")
        
    def _get_webhook_url(self) -> str:
        """설정 파일에서 Slack Webhook URL 가져오기"""
        try:
            from ..config.config_manager import ConfigManager
            config = ConfigManager()
            return config.get("Slack", "webhook_url", fallback="")
        except Exception as e:
            self.logger.warning(f"Slack Webhook URL을 가져올 수 없습니다: {e}")
            return ""
    
    def send_message(self, message: SlackMessage) -> bool:
        """Slack 메시지 전송"""
        if not self.webhook_url:
            self.logger.warning("Slack Webhook URL이 설정되지 않았습니다.")
            return False
            
        payload: Dict[str, Any] = {
            "text": message.text,
            "channel": message.channel,
            "username": message.username,
            "icon_emoji": message.icon_emoji
        }
        
        if message.attachments:
            payload["attachments"] = message.attachments
            
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            self.logger.info(f"Slack 메시지 전송 성공: {message.text[:50]}...")
            return True
        except Exception as e:
            self.logger.error(f"Slack 메시지 전송 실패: {e}")
            return False
    
    def send_test_start_notification(self, test_run_name: str, device_count: int, test_count: int) -> bool:
        """테스트 시작 알림"""
        message = SlackMessage(
            text=f"🚀 *QA 자동화 테스트 시작*\n"
                 f"• 테스트 런: {test_run_name}\n"
                 f"• 디바이스: {device_count}개\n"
                 f"• 테스트 케이스: {test_count}개\n"
                 f"• 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_emoji=":rocket:"
        )
        return self.send_message(message)
    
    def send_test_complete_notification(self, test_run_name: str, results: Dict[str, int]) -> bool:
        """테스트 완료 알림"""
        success_count = results.get("성공", 0)
        fail_count = results.get("실패", 0)
        total_count = success_count + fail_count
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0
        
        # 성공률에 따른 이모지 선택
        if success_rate >= 90:
            emoji = ":white_check_mark:"
            color = "good"
        elif success_rate >= 70:
            emoji = ":warning:"
            color = "warning"
        else:
            emoji = ":x:"
            color = "danger"
            
        attachments = [{
            "color": color,
            "fields": [
                {"title": "성공", "value": str(success_count), "short": True},
                {"title": "실패", "value": str(fail_count), "short": True},
                {"title": "성공률", "value": f"{success_rate:.1f}%", "short": True}
            ]
        }]
        
        message = SlackMessage(
            text=f"{emoji} *QA 자동화 테스트 완료*\n"
                 f"• 테스트 런: {test_run_name}\n"
                 f"• 총 테스트: {total_count}개\n"
                 f"• 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            attachments=attachments,
            icon_emoji=":checkered_flag:"
        )
        return self.send_message(message)
    
    def send_test_failure_notification(self, test_case_id: str, test_name: str, error_msg: str, device_info: str) -> bool:
        """테스트 실패 알림"""
        attachments = [{
            "color": "danger",
            "fields": [
                {"title": "테스트 케이스", "value": f"TC{test_case_id}", "short": True},
                {"title": "디바이스", "value": device_info, "short": True},
                {"title": "에러 메시지", "value": error_msg[:200] + "..." if len(error_msg) > 200 else error_msg, "short": False}
            ]
        }]
        
        message = SlackMessage(
            text=f"❌ *테스트 실패 알림*\n"
                 f"• 테스트: {test_name}\n"
                 f"• 실패 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            attachments=attachments,
            icon_emoji=":x:"
        )
        return self.send_message(message)
    
    def send_performance_alert(self, test_case_id: str, test_name: str, api_count: int, avg_response_time: float) -> bool:
        """성능 경고 알림"""
        if avg_response_time > 2.0:  # 2초 이상이면 경고
            attachments = [{
                "color": "warning",
                "fields": [
                    {"title": "테스트 케이스", "value": f"TC{test_case_id}", "short": True},
                    {"title": "API 호출 수", "value": str(api_count), "short": True},
                    {"title": "평균 응답시간", "value": f"{avg_response_time:.2f}초", "short": True}
                ]
            }]
            
            message = SlackMessage(
                text=f"⚠️ *성능 경고*\n"
                     f"• 테스트: {test_name}\n"
                     f"• 평균 응답시간이 2초를 초과했습니다.",
                attachments=attachments,
                icon_emoji=":warning:"
            )
            return self.send_message(message)
        return True
    
    def send_api_error_alert(self, test_case_id: str, api_url: str, status_code: int, error_count: int) -> bool:
        """API 에러 알림"""
        if status_code >= 400:
            attachments = [{
                "color": "danger",
                "fields": [
                    {"title": "테스트 케이스", "value": f"TC{test_case_id}", "short": True},
                    {"title": "API URL", "value": api_url[:100] + "..." if len(api_url) > 100 else api_url, "short": False},
                    {"title": "상태 코드", "value": str(status_code), "short": True},
                    {"title": "에러 횟수", "value": str(error_count), "short": True}
                ]
            }]
            
            message = SlackMessage(
                text=f"🚨 *API 에러 발생*\n"
                     f"• API 호출 중 에러가 발생했습니다.",
                attachments=attachments,
                icon_emoji=":rotating_light:"
            )
            return self.send_message(message)
        return True

# 전역 인스턴스
slack_notifier = SlackNotifier() 