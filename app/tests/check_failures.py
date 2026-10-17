"""Kontrolowane awarie na osobnych danych DEMO, bez wyłączania realnego Ollama."""
from pathlib import Path
import json
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / '.runtime/python'))
from app.storage import Store
from app.ai import Assistant, OllamaProvider
from app.validation import DomainError

checks = []
def check(name, ok):
    assert ok, name
    checks.append(name)
def rejected(fn, status):
    try: fn()
    except DomainError as error: assert error.status == status
    else: raise AssertionError('Operacja powinna być odrzucona')

for malformed in ([], None, 'tekst', 42, {'done': True, 'model': 'qwen3:1.7b', 'message': []}):
    provider = OllamaProvider()
    provider.request = lambda *args, value=malformed, **kwargs: value
    rejected(lambda: provider.generate('qwen3:1.7b', 'DEMO', {}, {}), 502)
check('Nieprawidłowe odpowiedzi modelu mają kontrolowany błąd 502', True)

directory = Path(tempfile.mkdtemp(prefix='failure-', dir=ROOT / '.test-data'))
store = Store(directory)
def cmd(action, data): return store.mutate(action, data, None, None, store.state()['revision'])
fact = cmd('saveEntry', {'kind': 'Umiejętność', 'content': 'Testuję n8n DEMO.', 'source': 'Test DEMO', 'status': 'W nauce'})
offer = cmd('saveOffer', {'title': 'Oferta DEMO', 'company': 'Firma DEMO', 'location': 'Polska', 'direction': 'Inne', 'mode': 'Zdalna', 'contract': 'Umowa o pracę', 'description': 'Wymagane n8n.', 'url': '', 'deadline': ''})
application = cmd('createApplication', {'offerId': offer})
class Working:
    def models(self): return ['qwen3:1.7b']
    def generate(self, *args): return {'factIds': [fact]}
assistant = Assistant(store, Working())
assistant.configure('qwen3:1.7b', True, store.state()['revision'])
class Offline(Working):
    def models(self): raise DomainError('Kontrolowana awaria DEMO.', status=503)
offline = Assistant(store, Offline()); before = store.export_json()['tables']
rejected(lambda: offline.prepare('test', 'cv', application, ''), 503)
check('Niedostępne AI nie zapisuje danych', store.export_json()['tables'] == before and not offline.status()['available'])

preview = assistant.prepare('test', 'cv', application, '')
original_write = Path.write_bytes
def fail_docx(path, content):
    if path.suffix == '.docx': raise OSError('Kontrolowana awaria zapisu DEMO')
    return original_write(path, content)
with patch.object(Path, 'write_bytes', fail_docx):
    try: assistant.commit('test', preview['token'], preview['revision'], True)
    except OSError: pass
    else: raise AssertionError('Awaria pliku powinna zatrzymać transakcję')
check('Awaria DOCX wycofuje wszystkie rekordy i wcześniejsze pliki', store.export_json()['tables'] == before and not list(store.files.iterdir()))
assistant.commit('test', preview['token'], preview['revision'], True)
check('Ponowienie po awarii zapisuje dokładnie jeden zestaw', len(store.state()['materials']) == 4 and len(store.state()['links']) == 4)
backup = store.make_backup
with patch.object(store, 'make_backup', side_effect=OSError('Kontrolowany brak miejsca DEMO')):
    cmd('saveTask', {'title': 'Zadanie DEMO', 'due': '2026-12-01', 'applicationId': application})
check('Błąd kopii nie ukrywa poprawnego zapisu i daje ostrzeżenie', len(store.state()['tasks']) == 1 and bool(store.state()['backupError']))
store.daily_backup()
check('Udana kolejna kopia usuwa ostrzeżenie', not store.state()['backupError'])
report = {'result': 'PASS', 'count': len(checks), 'checks': checks, 'data': 'Oddzielne bazy DEMO; awarie symulowane.'}
(ROOT / 'app/tests/failure-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('PASS:', len(checks), 'kontroli awarii i ponowień.')
