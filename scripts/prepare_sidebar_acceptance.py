"""Create explicitly synthetic UI fixtures in a separate, credential-free database."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service.core import FinanceService
from service.store import utcnow

root = Path(__file__).resolve().parents[1]
destination = root / 'data' / 'sidebar-acceptance'
if (destination / 'finance.sqlite').exists():
    raise SystemExit('Fixture database already exists; reuse it without overwriting.')
service = FinanceService(destination)
for project_id, name, titles in [
    ('ui-manufacturing', '制造业研究 · 界面验收', ['年度财报对比', '现金流核对']),
    ('ui-consumer', '消费行业 · 界面验收', ['收入结构分析']),
    ('ui-empty', '空项目 · 界面验收', []),
]:
    service.create_project(project_id, name)
    for index, title in enumerate(titles):
        chat_id = f'{project_id}-{index}'
        stamp = utcnow()
        chat = dict(id=chat_id, projectId=project_id, title=title, createdAt=stamp, updatedAt=stamp,
                    messages=[dict(id=chat_id+'-message', role='assistant',
                                   content=f'界面验收样例：{name} / {title}。仅用于检查项目与会话归属，没有调用模型。',
                                   status='completed', createdAt=stamp)])
        service.put_app_state(project_id, 'conversations', chat_id, chat)
print(destination)
