import requests
import configparser

# config.ini에서 정보 읽기
config = configparser.ConfigParser()
config.read('config.ini')
tr = config['TestRail']
url = tr['url'].rstrip('/')
username = tr['username']
api_key = tr['api_key']

headers = {'Content-Type': 'application/json'}

def get(endpoint):
    resp = requests.get(f"{url}/index.php?/api/v2/{endpoint}", auth=(username, api_key), headers=headers)
    resp.raise_for_status()
    return resp.json()

# 1. 모든 프로젝트 조회
projects = get("get_projects")
print(projects)  # 실제 구조 확인
if isinstance(projects, dict) and 'projects' in projects:
    projects = projects['projects']

with open("testrail_case_titles.txt", "w", encoding="utf-8") as f:
    for project in projects:
        name = project.get('name', '')
        if name.startswith('(미사용)'):
            continue  # (미사용) 프로젝트는 제외
        suites = get(f"get_suites/{project.get('id','')}")
        if isinstance(suites, dict) and 'suites' in suites:
            suites = suites['suites']
        for suite in suites:
            cases = get(f"get_cases/{project.get('id','')}&suite_id={suite.get('id','')}")
            if isinstance(cases, dict) and 'cases' in cases:
                cases = cases['cases']
            for case in cases:
                title = case.get('title', str(case))
                f.write(f"{title}\n")
