"""Zapis nowego kierunku i zgodność istniejących profili/kopii; tylko bazy DEMO."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.runtime/python'))
from app.storage import Store
from app.validation import DIRECTIONS, DomainError

workspace = ROOT / '.test-data'
workspace.mkdir(exist_ok=True)
def fresh(): return Store(Path(tempfile.mkdtemp(prefix='direction-', dir=workspace)))
store = fresh()
old_snapshot = store.export_json()
offer = dict(title='Oferta Inne DEMO', company='Firma DEMO', location='Polska',
             direction='Inne', mode='Zdalna', contract='Umowa o pracę',
             url='', description='', deadline='')
key = store.mutate('saveOffer', offer, None, None, store.state()['revision'])
row = store.state()['offers'][0]
assert row['direction'] == 'Inne'
store.mutate('saveOffer', {**offer, 'title': 'Zmieniona oferta DEMO'}, key,
             row['rowVersion'], store.state()['revision'])
assert Store(store.directory).state()['offers'][0]['direction'] == 'Inne'
profile = store.state()['profile']
assert profile['preferences']['directions'] == DIRECTIONS and 'Inne' not in DIRECTIONS
store.mutate('saveProfile', {k: profile[k] for k in ('name', 'email', 'goal', 'preferences')},
             profile['id'], profile['rowVersion'], store.state()['revision'])
store.validate_snapshot(old_snapshot)
for kind, content in [('zip', store.archive_bytes()), ('csv', store.export_csv('offers'))]:
    restored = fresh()
    restored.commit_import(restored.preview_import(kind, content), restored.state()['revision'])
    assert restored.state()['offers'][0]['direction'] == 'Inne'
try:
    store.mutate('saveOffer', {**offer, 'direction': 'Nieznany kierunek'}, None, None,
                 store.state()['revision'])
except DomainError: pass
else: raise AssertionError('Nieznana opcja została zaakceptowana')
print('PASS: Inne — zapis, edycja, ponowne otwarcie bazy, profil, stare kopie, ZIP, CSV i walidacja.')
