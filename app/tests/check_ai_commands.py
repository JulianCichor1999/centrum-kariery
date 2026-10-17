from pathlib import Path
import json,sys
root=Path.cwd(); sys.path.insert(0,str(root)); sys.path.insert(0,str(root/'.runtime/python'))
from app.ai import Assistant,OllamaProvider
from app.storage import Store
from app.validation import DomainError
report=json.loads((root/'app/tests/ai-report.json').read_text(encoding='utf-8')); store=Store(report['directory']); assistant=Assistant(store,OllamaProvider()); application=store.state()['applications'][0]['id']
preview=assistant.prepare('final-note','command',application,'Dodaj notatkę: omówiliśmy portfolio. Dodaj zadanie: przygotować linki na 2026-12-03.')
assert len(preview['operations'])==2 and {x['action'] for x in preview['operations']}=={'saveTask','addNote'},preview
assert next(x for x in preview['operations'] if x['action']=='saveTask')['data']['due']=='2026-12-03',preview
before=store.state(); assistant.commit('final-note',preview['token'],preview['revision'],True); after=store.state(); assert len(after['tasks'])==len(before['tasks'])+1 and len(after['notes'])==len(before['notes'])+1
rev,data=assistant.context(application,'Dodaj zadanie: przejrzeć oferty w piątek za 2 tygodnie')
result=assistant.validate_result('command',{'intent':'add','tasks':[{'title':'Zadanie','due':'2026-12-03'}],'note':''},data); assert result['clarification'] and not result['operations']
check={'result':'PASS','realModel':'qwen3:1.7b','checks':['Rzeczywisty model zaproponował zadanie i notatkę w jednym poleceniu','Zapis obu operacji w jednej transakcji','Złożony względny termin wymaga daty YYYY-MM-DD'],'count':3}
(root/'app/tests/ai-final-report.json').write_text(json.dumps(check,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(check,ensure_ascii=False))
