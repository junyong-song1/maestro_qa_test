import configparser
import requests
import os
import re

SUITE_ID = 1787  # 생성할 suite_id
FLOW_DIR = "maestro_flows"

# Maestro flow YAML 템플릿
FLOW_TEMPLATE = '''appId: com.tving.app
---
# {title}
# TestRail Case ID: {case_id}
# {url}
{steps}
'''

def sanitize_filename(s):
    s = re.sub(r'[^\w\d_\-]', '_', s)
    return s[:40]

def testrail_get_cases(config, suite_id):
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/get_cases/{project_id}&suite_id={suite_id}"
    print(f"[INFO] 요청: {endpoint}")
    resp = requests.get(endpoint, auth=(username, api_key), headers={'Content-Type': 'application/json'})
    print(f"[INFO] 응답 코드: {resp.status_code}")
    if resp.status_code != 200:
        print(f"[ERROR] 응답 본문: {resp.text}")
    resp.raise_for_status()
    return resp.json()

def convert_steps_to_maestro(steps):
    lines = []
    for step in steps:
        content = step.get('content', '').strip()
        if content:
            if '로그인' in content:
                lines.append('- tapOn: "로그인"')
            elif '검색' in content:
                lines.append('- tapOn: "검색"')
            elif '입력' in content:
                lines.append('- inputText: "입력란", text: "..."')
            elif '확인' in content or '보인다' in content:
                lines.append('- assertVisible: "..."')
            else:
                lines.append(f'# {content}')
    if not lines:
        lines.append('# (수동 변환 필요)')
    return '\n'.join(lines)

def main():
    config = configparser.ConfigParser()
    config.read('config.ini')
    tr = config['TestRail']
    cases = testrail_get_cases(tr, SUITE_ID)
    # 응답이 딕셔너리면 'cases' 키로 리스트 추출
    if isinstance(cases, dict) and 'cases' in cases:
        cases = cases['cases']
    print(f"[INFO] 케이스 개수: {len(cases)}")
    if not os.path.exists(FLOW_DIR):
        os.makedirs(FLOW_DIR)
    for case in cases:
        case_id = case['id']
        title = case['title']
        url = f"{tr['url'].rstrip('/')}/index.php?/cases/view/{case_id}"
        steps = case.get('custom_steps_separated') or []
        maestro_steps = convert_steps_to_maestro(steps)
        fname = f"TC{case_id}_{sanitize_filename(title)}.yaml"
        fpath = os.path.join(FLOW_DIR, fname)
        if os.path.exists(fpath):
            print(f"[건너뜀] {fpath} (이미 존재)")
            continue
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(FLOW_TEMPLATE.format(title=title, case_id=case_id, url=url, steps=maestro_steps))
        print(f"[생성] {fpath}")

if __name__ == "__main__":
    main()
