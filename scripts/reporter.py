from rich.console import Console, Group
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
import datetime

console = Console()

def print_progress_table(status_list):
    table = Table(title="테스트 진행상황", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("케이스ID")
    table.add_column("단말기")
    table.add_column("상태", style="bold")
    table.add_column("시작시간")
    table.add_column("종료시간")
    for idx, s in enumerate(status_list, 1):
        table.add_row(
            str(idx),
            s.get('case_id', ''),
            s.get('device', ''),
            s.get('status', ''),
            s.get('start', ''),
            s.get('end', '')
        )
    console.clear()
    console.print(table)

def print_progress_bar(current, total):
    with Progress() as progress:
        task = progress.add_task("진행률", total=total)
        progress.update(task, completed=current)

def generate_report(results, output_path="result/test_report.md"):
    lines = ["# 테스트 결과 리포트", f"생성일: {datetime.datetime.now()}\n"]
    for r in results:
        lines.append(f"- 케이스: {r.get('case_id','')} | 단말기: {r.get('device','')} | 상태: {r.get('status','')} | 시작: {r.get('start','')} | 종료: {r.get('end','')}")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"[INFO] 리포트 저장: {output_path}")

# 대시보드 렌더링 함수
def render_dashboard(project_name, start_time, suites_status, current_test, device_infos, logs):
    layout = Layout()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    header = Panel(f"🎯 {project_name} QA 자동화 테스트 ─ 실행 시간: {start_time} → {now}", style="bold cyan")
    layout.split_column(
        Layout(header, name="header", size=3),
        Layout(name="body", size=8),
        Layout(name="logs", size=20)
    )
    suite_table = Table(title="테스트 스위트 현황", show_lines=True, box=None)
    suite_table.add_column("스위트", justify="center")
    suite_table.add_column("진행률", justify="center")
    suite_table.add_column("상태", justify="center")
    suite_table.add_column("시간", justify="center")
    for s in suites_status:
        suite_table.add_row(s['name'], s['progress'], s['status'], s['time'])
    current_panel = Panel(
        f"🔄 현재 실행:  {current_test.get('name','-')}\n"
        f"📝 설명:      {current_test.get('desc','-')}\n"
        f"🆔 TestRail ID: {current_test.get('id','-')}\n"
        + ("\n".join([f"{k}: {v}" for k, v in current_test.get('devices', {}).items()]) if 'devices' in current_test else ''),
        title="현재 테스트", border_style="cyan"
    )
    device_table = Table(title="연결된 단말기 정보", show_lines=True, box=None)
    device_table.add_column("모델명", justify="center")
    device_table.add_column("OS", justify="center")
    device_table.add_column("빌드", justify="center")
    device_table.add_column("Serial", justify="center")
    for d in device_infos:
        device_table.add_row(d['model'], d['os_version'], d['build'], d['serial'])
    layout["body"].split_row(
        Layout(suite_table, name="suite", ratio=1),
        Layout(current_panel, name="current", ratio=1),
        Layout(device_table, name="devices", ratio=1)
    )
    layout["logs"].update(
        Panel("\n".join(logs.get('ALL', [])[-20:]), title="실시간 Maestro 전체 로그", style="dim")
    )
    return layout 