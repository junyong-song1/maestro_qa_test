import argparse
import configparser
import requests
import sys
from datetime import datetime

def create_testrail_run(config, suite_id, name=None, description=None):
    url = config['url'].rstrip('/')
    project_id = config['project_id']
    username = config['username']
    api_key = config['api_key']
    endpoint = f"{url}/index.php?/api/v2/add_run/{project_id}"
    headers = {'Content-Type': 'application/json'}
    if not name:
        name = f"Automated Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    data = {
        'suite_id': int(suite_id),
        'name': name,
        'description': description or '',
        'include_all': True
    }
    resp = requests.post(endpoint, json=data, auth=(username, api_key), headers=headers)
    if resp.status_code != 200:
        print(f"[ERROR] {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    run = resp.json()
    print(run['id'])  # run_id만 출력
    return run['id']

def main():
    parser = argparse.ArgumentParser(description="TestRail에서 새 테스트 Run을 생성하고 run_id를 출력합니다.")
    parser.add_argument('--config', default='config.ini', help='TestRail 설정 파일 경로')
    parser.add_argument('--suite_id', required=True, help='TestRail Suite ID')
    parser.add_argument('--name', help='Run 이름(옵션)')
    parser.add_argument('--description', help='Run 설명(옵션)')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)
    tr = config['TestRail']
    create_testrail_run(tr, args.suite_id, args.name, args.description)

if __name__ == "__main__":
    main()
