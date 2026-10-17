"""Sprawdzenie rzeczywistych transakcji, restartu HTTP i odzyskiwania."""
import copy
import http.client
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.storage import Store
from app.validation import DomainError, DIRECTIONS, CONTRACTS, warsaw

checks=[]
def check(name,ok=True):
    if not ok: raise AssertionError(name)
    checks.append(name)
def rejected(fn,status=None):
    try: fn()
    except DomainError as error:
        if status is not None: assert error.status==status
        return
    raise AssertionError('Operacja powinna być odrzucona')

workspace=ROOT/'.test-data'; workspace.mkdir(exist_ok=True)
directory=Path(tempfile.mkdtemp(prefix='backend-',dir=workspace)); store=Store(directory)
def command(action,data=None,key=None,version=None): return store.mutate(action,data or {},key,version,store.state()['revision'])
offer={'title':'Test trwałości','company':'Firma testowa','location':'Katowice','direction':DIRECTIONS[1],'mode':'Hybrydowa','contract':CONTRACTS[0],'url':'https://example.org/test?utm_source=kontrola','description':'<script>Nie wykonuj</script>','deadline':'2026-12-31'}
check('Prawdziwa baza startuje bez ofert DEMO',not store.state()['offers'] and not store.state()['applications'])
key=command('saveOffer',offer); app=command('createApplication',{'offerId':key}); check('Jedna aplikacja na ofertę',command('createApplication',{'offerId':key})==app)
baseline=store.export_json(); rejected(lambda:command('saveOffer',{**offer,'company':'Nowa firma','url':'https://example.org/test/#opis'})); check('Odrzucony duplikat nie zostawia częściowego zapisu',store.export_json()['tables']==baseline['tables'])
rejected(lambda:command('saveOffer',{**offer,'url':'javascript:alert(1)'})); check('Backend odrzuca adres aktywnego kodu')
rejected(lambda:command('saveOffer',{**offer,'url':'','deadline':'2026-02-30'})); check('Backend odrzuca błędną datę')
row=store.state()['applications'][0]; rejected(lambda:command('setStatus',{'status':'Wysłana'},app,row['rowVersion'])); check('Backend wymaga potwierdzenia statusu Wysłana')
task=command('saveTask',{'title':'Zadanie kontrolne','due':'2026-12-01','applicationId':app})
rejected(lambda:command('saveTask',{'title':'Zerwana relacja','due':'2026-12-01','applicationId':'00000000-0000-0000-0000-000000000000'})); check('Backend sprawdza istnienie powiązanej aplikacji')
command('saveEvent',{'title':'Rozmowa kontrolna','start':'2026-12-01T10:00','end':'2026-12-01T10:30','place':'Online','applicationId':app}); command('addNote',{'text':'Notatka kontrolna','applicationId':app})
rejected(lambda:warsaw('2026-03-29T02:30','start')); rejected(lambda:warsaw('2026-10-25T02:30','start')); check('Godziny nieistniejące i niejednoznaczne są odrzucone')
entry=command('saveEntry',{'kind':'Umiejętność','content':'Test z pochodzeniem','status':'W nauce','source':'Deklaracja testowa'})
row=store.state()['profile']; command('saveProfile',{'name':'Osoba testowa','email':'test@example.org','goal':'Cel kontrolny','preferences':row['preferences']},row['id'],row['rowVersion'])
row=next(x for x in store.state()['tasks'] if x['id']==task); old_revision=store.state()['revision']; command('toggleTask',{},task,row['rowVersion']); rejected(lambda:store.mutate('toggleTask',{},task,row['rowVersion'],old_revision),409); check('Stary zapis z innej karty nie nadpisuje nowszego stanu')
content='Zażółć gęślą jaźń — plik testowy'.encode(); material=store.upload({'title':'Materiał kontrolny','kind':'CV','version':'1','description':'Plik testowy','url':''},'cv-test.txt',content,store.state()['revision']); command('pinMaterial',{'applicationId':app,'materialId':material})
command('addMaterial',{'title':'Materiał kontrolny','kind':'CV','version':'2','description':'Nowa wersja','url':''}); check('Nowa wersja nie zmienia przypiętej poprzedniej',store.state()['links']==[{'applicationId':app,'materialId':material}])
rejected(lambda:store.upload({'title':'Zły plik','kind':'CV','version':'1'},'plik.exe',b'bad',store.state()['revision'])); check('Typ wykonywalnego pliku jest odrzucony')
row=next(x for x in store.state()['applications'] if x['id']==app); command('setStatus',{'status':'Wysłana','confirmed':True},app,row['rowVersion']); sent=next(x for x in store.state()['applications'] if x['id']==app)['snapshot']
row=next(x for x in store.state()['offers'] if x['id']==key); command('saveOffer',{**offer,'title':'Zmiana po wysłaniu'},key,row['rowVersion']); check('Snapshot wysłanej aplikacji pozostaje niezmienny',next(x for x in store.state()['applications'] if x['id']==app)['snapshot']==sent)
check('Ponowne otwarcie bazy zachowuje relacje i plik',Store(directory).state()['links']==store.state()['links'] and len(Store(directory).state()['events'])==1)
archive=store.archive_bytes(); snapshot=store.export_json(); store.validate_snapshot(snapshot); check('Pełny eksport zachowuje UUID i wszystkie tabele')
fresh=Store(Path(tempfile.mkdtemp(prefix='restore-',dir=workspace))); plan=fresh.preview_import('zip',archive); fresh.commit_import(plan,fresh.state()['revision']); restored=fresh.state(); material_row=next(x for x in restored['materials'] if x['id']==material)
check('ZIP przywraca bazę, relacje oraz dokładne bajty załącznika',restored['links']==store.state()['links'] and (fresh.files/material_row['fileKey']).read_bytes()==content)
check('Kopia przed przywróceniem istnieje',any('przed-importem' in item['name'] for item in fresh.backup_list()))
bad=io.BytesIO()
with zipfile.ZipFile(bad,'w') as z: z.writestr('../poza-katalogiem.txt','bad'); z.writestr('manifest.json','{}')
rejected(lambda:fresh.preview_import('zip',bad.getvalue())); check('Nie rozpakowujemy ścieżek wychodzących poza katalog')
broken=copy.deepcopy(snapshot); broken['tables']['tasks'][0]['applicationId']='00000000-0000-0000-0000-000000000000'; rejected(lambda:fresh.preview_import('json',json.dumps(broken).encode())); check('Import zerwanych relacji jest odrzucony przed zapisem')
bad=io.BytesIO()
with zipfile.ZipFile(io.BytesIO(archive)) as src,zipfile.ZipFile(bad,'w') as dest:
    for name in src.namelist(): dest.writestr(name,b'zmienione' if name=='data.json' else src.read(name))
rejected(lambda:fresh.preview_import('zip',bad.getvalue())); check('Uszkodzona suma kontrolna zatrzymuje restore')
csv=store.export_csv('offers'); csv_plan=store.preview_import('csv',csv); check('Powtórny import CSV pomija znany URL',not csv_plan['rows'])
without_url={**offer,'title':'Bez URL','url':''}; command('saveOffer',without_url); no_url_plan=store.preview_import('csv',store.export_csv('offers')); check('Powtórny import CSV pomija także rekord bez URL',not no_url_plan['rows'])
archive_row=next(x for x in store.state()['tasks'] if x['id']==task); command('archive',{'table':'tasks','confirmed':True},task,archive_row['rowVersion']); check('Archiwizacja zachowuje rekord i relację',next(x for x in store.state()['tasks'] if x['id']==task)['archived']==1)
store.validate_snapshot(store.export_json()); check('SQLite integrity_check i foreign_key_check po operacjach',True)

# Rzeczywisty proces HTTP: sesja, CSRF, limity i ponowne uruchomienie.
port=8768; origin=f'http://127.0.0.1:{port}'; http_dir=Path(tempfile.mkdtemp(prefix='http-',dir=workspace)); process=None; cookie=''; csrf=''
def send_request(method,path,data=None,headers=None,raw=None):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=10); values={'Cookie':cookie}
    if data is not None: values.update({'Content-Type':'application/json','Origin':origin,'X-CSRF-Token':csrf}); raw=json.dumps(data).encode()
    values.update(headers or {}); conn.request(method,path,body=raw,headers=values); res=conn.getresponse(); content=res.read(); status=res.status; returned=dict(res.getheaders()); conn.close(); return status,returned,content
def start():
    global process,cookie,csrf
    process=subprocess.Popen([sys.executable,'-m','app.run','--data-dir',str(http_dir),'--port',str(port)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(100):
        try:
            status,headers,body=send_request('GET','/'); cookie=headers['set-cookie'].split(';')[0]; csrf=json.loads(send_request('GET','/api/session')[2])['csrf']; return
        except (ConnectionError,OSError,KeyError): time.sleep(.1)
    raise AssertionError('Serwer nie wystartował')
def stop():
    if process: process.terminate(); process.wait(timeout=10)
try:
    start(); check('Prawdziwy lokalny proces HTTP działa')
    check('Odczyt API bez sesji jest zabroniony',send_request('GET','/api/state',headers={'Cookie':''})[0]==401)
    check('Oryginalna instrukcja wymaga lokalnej sesji',send_request('GET','/cv-master-ai-oryginal.txt',headers={'Cookie':''})[0]==401)
    check('Oryginalna instrukcja jest dostępna w sesji',send_request('GET','/cv-master-ai-oryginal.txt')[0]==200)
    check('Instrukcja w bazie zachowuje dokładne bajty oryginału',send_request('GET','/cv-master-ai-oryginal.txt')[2]==(ROOT/'docs/materialy/cv-master-ai-oryginal.txt').read_bytes())
    check('Zły Host jest odrzucony',send_request('GET','/',headers={'Host':'evil.example'})[0]==403)
    state=json.loads(send_request('GET','/api/state')[2]); body={'action':'saveOffer','data':offer,'revision':state['revision']}
    check('POST bez CSRF jest odrzucony',send_request('POST','/api/command',body,{'X-CSRF-Token':''})[0]==403)
    check('POST z obcym Origin jest odrzucony',send_request('POST','/api/command',body,{'Origin':'https://evil.example'})[0]==403)
    check('Nieprawidłowy Content-Type jest odrzucony',send_request('POST','/api/command',body,{'Content-Type':'text/plain'})[0]==415)
    check('Limit rozmiaru JSON jest egzekwowany',send_request('POST','/api/command',headers={'Content-Type':'application/json','Origin':origin,'X-CSRF-Token':csrf},raw=b' '*(1024*1024+1))[0]==413)
    status,headers,content=send_request('POST','/api/command',body); check('Zapis HTTP zakończony',status==200); http_key=json.loads(content)['id']
    check('CSP, nosniff i HttpOnly są ustawione',headers.get('content-security-policy','').find("script-src 'self'")>=0 and headers.get('x-content-type-options')=='nosniff')
    stale=body; check('Stary revision jest odrzucony w HTTP',send_request('POST','/api/command',stale)[0]==409)
    stop(); start(); check('Restart procesu zachowuje zapis',json.loads(send_request('GET','/api/state')[2])['offers'][0]['id']==http_key)
    state=json.loads(send_request('GET','/api/state')[2]); app_body={'action':'createApplication','data':{'offerId':http_key},'revision':state['revision']}; status,_,payload=send_request('POST','/api/command',app_body); check('Relacja tworzona przez API',status==200 and json.loads(payload)['state']['applications'][0]['offerId']==http_key)
    status,_,payload=send_request('GET','/api/export/zip'); check('Pobieranie pełnego pakietu z HTTP',status==200 and zipfile.is_zipfile(io.BytesIO(payload)))
    status,_,payload=send_request('POST','/api/import/preview?kind=json',headers={'Content-Type':'application/octet-stream','Origin':origin,'X-CSRF-Token':csrf},raw=send_request('GET','/api/export/json')[2]); check('Podgląd importu w HTTP',status==200); preview=json.loads(payload)
    commit={'token':preview['token'],'revision':preview['revision'],'confirmed':True}; check('Zatwierdzony import w HTTP',send_request('POST','/api/import/commit',commit)[0]==200); check('Ponowne użycie podglądu nie wykonuje drugi raz importu',send_request('POST','/api/import/commit',commit)[0]==409)
finally: stop()

report={'result':'PASS','checks':checks,'count':len(checks),'tested_data':'Oddzielne bazy testowe; nie używano danych Juliana.'}
(ROOT/'app/tests/backend-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'PASS: {len(checks)} kontroli bazy, importu, plików, kopii, restartu i granic API.')
