import os
import re

def comment_recording_commands(yaml_path):
    """yaml 파일에서 startRecording 명령어를 주석 처리합니다."""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # startRecording 라인을 찾아서 주석 처리
    pattern = r'^(\s*-)(\s*startRecording:.+)$'
    modified = re.sub(pattern, r'\1 #\2', content, flags=re.MULTILINE)
    
    # 변경사항이 있는 경우에만 파일 저장
    if modified != content:
        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write(modified)
        print(f"수정됨: {yaml_path}")

def main():
    # maestro_flows 디렉토리의 모든 yaml 파일 처리
    flows_dir = "maestro_flows"
    for filename in os.listdir(flows_dir):
        if filename.endswith(".yaml"):
            yaml_path = os.path.join(flows_dir, filename)
            comment_recording_commands(yaml_path)

if __name__ == "__main__":
    main() 