"""
Maestro Hierarchy 캡처 및 저장 유틸리티
UI 구조 데이터를 수집하여 분석에 활용
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class MaestroHierarchyCapture:
    """Maestro UI Hierarchy 캡처 및 저장 클래스"""
    
    def __init__(self, db_path: str = "artifacts/test_log.db"):
        self.db_path = db_path
        self._init_hierarchy_table()
    
    def _init_hierarchy_table(self):
        """Hierarchy 데이터 저장을 위한 테이블 초기화"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_hierarchy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_case_id INTEGER,
                    screen_name TEXT,
                    hierarchy_data TEXT,
                    element_count INTEGER,
                    clickable_elements INTEGER,
                    text_elements INTEGER,
                    image_elements INTEGER,
                    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    device_serial TEXT,
                    app_version TEXT,
                    screen_resolution TEXT
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("Hierarchy 테이블 초기화 완료")
            
        except Exception as e:
            logger.error(f"Hierarchy 테이블 초기화 실패: {e}")
    
    def capture_hierarchy(self, device_serial: str, test_case_id: int, 
                         screen_name: str = None) -> Dict[str, Any]:
        """현재 화면의 UI Hierarchy 캡처"""
        try:
            # Maestro hierarchy 명령 실행
            import subprocess
            
            cmd = f"maestro hierarchy --device {device_serial}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Hierarchy 캡처 실패: {result.stderr}")
                return None
            
            hierarchy_data = result.stdout
            
            # Hierarchy 데이터 파싱 및 분석
            parsed_data = self._parse_hierarchy_data(hierarchy_data)
            
            # 데이터베이스에 저장
            self._save_hierarchy_data(
                test_case_id=test_case_id,
                screen_name=screen_name or f"Screen_{int(time.time())}",
                hierarchy_data=hierarchy_data,
                parsed_data=parsed_data,
                device_serial=device_serial
            )
            
            logger.info(f"[{device_serial}] Hierarchy 캡처 완료: {len(parsed_data.get('elements', []))}개 요소")
            return parsed_data
            
        except subprocess.TimeoutExpired:
            logger.error(f"[{device_serial}] Hierarchy 캡처 타임아웃")
            return None
        except Exception as e:
            logger.error(f"[{device_serial}] Hierarchy 캡처 실패: {e}")
            return None
    
    def _parse_hierarchy_data(self, hierarchy_data: str) -> Dict[str, Any]:
        """Hierarchy 데이터 파싱 및 분석"""
        try:
            # JSON 형태로 파싱 시도
            if hierarchy_data.strip().startswith('{'):
                data = json.loads(hierarchy_data)
            else:
                # 텍스트 형태의 hierarchy 데이터 파싱
                data = self._parse_text_hierarchy(hierarchy_data)
            
            # 요소 통계 계산
            elements = data.get('elements', [])
            stats = self._calculate_element_stats(elements)
            
            return {
                'elements': elements,
                'stats': stats,
                'raw_data': hierarchy_data[:1000] + "..." if len(hierarchy_data) > 1000 else hierarchy_data
            }
            
        except Exception as e:
            logger.error(f"Hierarchy 데이터 파싱 실패: {e}")
            return {
                'elements': [],
                'stats': {},
                'raw_data': hierarchy_data[:1000] + "..." if len(hierarchy_data) > 1000 else hierarchy_data
            }
    
    def _parse_text_hierarchy(self, text_data: str) -> Dict[str, Any]:
        """텍스트 형태의 hierarchy 데이터 파싱"""
        elements = []
        lines = text_data.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 간단한 요소 정보 추출
            element_info = {
                'type': 'unknown',
                'text': '',
                'id': '',
                'clickable': False,
                'visible': True
            }
            
            # 텍스트 요소 감지
            if '"' in line:
                element_info['type'] = 'text'
                element_info['text'] = line.split('"')[1] if len(line.split('"')) > 1 else ''
            
            # ID 요소 감지
            if 'id=' in line:
                element_info['id'] = line.split('id=')[1].split()[0] if 'id=' in line else ''
            
            # 클릭 가능한 요소 감지
            if 'clickable' in line.lower() or 'button' in line.lower():
                element_info['clickable'] = True
                element_info['type'] = 'button'
            
            elements.append(element_info)
        
        return {'elements': elements}
    
    def _calculate_element_stats(self, elements: List[Dict]) -> Dict[str, int]:
        """요소 통계 계산"""
        stats = {
            'total': len(elements),
            'clickable': 0,
            'text': 0,
            'image': 0,
            'input': 0,
            'other': 0
        }
        
        for element in elements:
            element_type = element.get('type', '').lower()
            
            if element.get('clickable', False):
                stats['clickable'] += 1
            
            if 'text' in element_type:
                stats['text'] += 1
            elif 'image' in element_type or 'img' in element_type:
                stats['image'] += 1
            elif 'input' in element_type or 'edit' in element_type:
                stats['input'] += 1
            else:
                stats['other'] += 1
        
        return stats
    
    def _save_hierarchy_data(self, test_case_id: int, screen_name: str, 
                           hierarchy_data: str, parsed_data: Dict[str, Any], 
                           device_serial: str):
        """Hierarchy 데이터를 데이터베이스에 저장"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            stats = parsed_data.get('stats', {})
            
            cursor.execute("""
                INSERT INTO test_hierarchy (
                    test_case_id, screen_name, hierarchy_data, element_count,
                    clickable_elements, text_elements, image_elements,
                    device_serial, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_case_id,
                screen_name,
                hierarchy_data,
                stats.get('total', 0),
                stats.get('clickable', 0),
                stats.get('text', 0),
                stats.get('image', 0),
                device_serial,
                datetime.now()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Hierarchy 데이터 저장 실패: {e}")
    
    def get_hierarchy_history(self, test_case_id: int = None, 
                            limit: int = 100) -> List[Dict[str, Any]]:
        """Hierarchy 데이터 히스토리 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if test_case_id:
                cursor.execute("""
                    SELECT * FROM test_hierarchy 
                    WHERE test_case_id = ? 
                    ORDER BY captured_at DESC 
                    LIMIT ?
                """, (test_case_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM test_hierarchy 
                    ORDER BY captured_at DESC 
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            # 컬럼명 매핑
            columns = ['id', 'test_case_id', 'screen_name', 'hierarchy_data', 
                      'element_count', 'clickable_elements', 'text_elements', 
                      'image_elements', 'captured_at', 'device_serial', 
                      'app_version', 'screen_resolution']
            
            result = []
            for row in rows:
                result.append(dict(zip(columns, row)))
            
            return result
            
        except Exception as e:
            logger.error(f"Hierarchy 히스토리 조회 실패: {e}")
            return []
    
    def analyze_ui_changes(self, test_case_id: int) -> Dict[str, Any]:
        """UI 변화 분석"""
        try:
            hierarchies = self.get_hierarchy_history(test_case_id)
            
            if len(hierarchies) < 2:
                return {'message': '분석할 데이터가 부족합니다'}
            
            # 최신 2개 데이터 비교
            latest = hierarchies[0]
            previous = hierarchies[1]
            
            changes = {
                'element_count_change': latest['element_count'] - previous['element_count'],
                'clickable_change': latest['clickable_elements'] - previous['clickable_elements'],
                'text_change': latest['text_elements'] - previous['text_elements'],
                'image_change': latest['image_elements'] - previous['image_elements'],
                'time_diff': (datetime.fromisoformat(latest['captured_at']) - 
                            datetime.fromisoformat(previous['captured_at'])).total_seconds()
            }
            
            return {
                'latest_screen': latest['screen_name'],
                'previous_screen': previous['screen_name'],
                'changes': changes,
                'stability_score': self._calculate_stability_score(changes)
            }
            
        except Exception as e:
            logger.error(f"UI 변화 분석 실패: {e}")
            return {'error': str(e)}
    
    def _calculate_stability_score(self, changes: Dict[str, Any]) -> float:
        """UI 안정성 점수 계산"""
        # 변화가 적을수록 높은 점수
        total_change = abs(changes['element_count_change']) + \
                      abs(changes['clickable_change']) + \
                      abs(changes['text_change']) + \
                      abs(changes['image_change'])
        
        # 0-100 점수로 변환 (변화가 적을수록 높은 점수)
        if total_change == 0:
            return 100.0
        elif total_change > 50:
            return 0.0
        else:
            return max(0, 100 - (total_change * 2))

def capture_hierarchy_for_test(device_serial: str, test_case_id: int, 
                              screen_name: str = None) -> Dict[str, Any]:
    """테스트 실행 중 Hierarchy 캡처 헬퍼 함수"""
    capture = MaestroHierarchyCapture()
    return capture.capture_hierarchy(device_serial, test_case_id, screen_name)

if __name__ == "__main__":
    # 테스트 실행
    capture = MaestroHierarchyCapture()
    
    # 히스토리 조회 테스트
    history = capture.get_hierarchy_history(limit=5)
    print(f"최근 Hierarchy 데이터: {len(history)}개")
    
    for item in history:
        print(f"TC{item['test_case_id']} - {item['screen_name']} - {item['element_count']}개 요소") 