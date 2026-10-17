"""Rzeczywista ścieżka Polecenie do bazy -> lokalny model -> podgląd -> potwierdzenie."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.storage import Store
from app.ai import Assistant

directory=Path(tempfile.mkdtemp(prefix='materials-http-',dir=ROOT/'.test-data')); store=Store(directory)
def cmd(action,data): return store.mutate(action,data,None,None,store.state()['revision'])
material=store.upload({'title':'CV DEMO','kind':'CV','version':'1','description':'','url':''},'cv-demo.txt','Przygotowałem instrukcje do zajęć z narzędzi cyfrowych. Uczę się automatyzacji n8n.'.encode(),store.state()['revision'])
cmd('addMaterial',{'title':'Drive DEMO','kind':'Portfolio','version':'1','description':'','url':'https://drive.google.com/drive/folders/demo'})
offer=cmd('saveOffer',{'title':'Animator KRC DEMO','company':'Firma DEMO','location':'Polska','direction':'Inne','mode':'Stacjonarna','contract':'Umowa o pracę','url':'','description':'','deadline':''})
application=cmd('createApplication',{'offerId':offer}); Assistant(store).configure('qwen3:1.7b',True,store.state()['revision'])
port=8773; base=f'http://127.0.0.1:{port}'; cookie=''; csrf=''; checks=[]
def request(method,path,data=None,extra=None):
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=180)
    headers={'Cookie':cookie}; payload=None
    if data is not None: headers.update({'Content-Type':'application/json','Origin':base,'X-CSRF-Token':csrf}); payload=json.dumps(data).encode()
    headers.update(extra or {}); connection.request(method,path,body=payload,headers=headers)
    response=connection.getresponse(); content=response.read(); status=response.status; returned=dict(response.getheaders()); connection.close()
    return status,returned,json.loads(content) if 'json' in returned.get('content-type','') else content
def check(name,ok=True):
    assert ok,name
    checks.append(name)
process=subprocess.Popen([sys.executable,'-m','app.run','--data-dir',str(directory),'--port',str(port)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
try:
    for _ in range(100):
        try:
            status,headers,_=request('GET','/'); cookie=headers['set-cookie'].split(';')[0]; break
        except OSError: time.sleep(.1)
    else: raise AssertionError('Serwer DEMO nie wystartował')
    csrf=request('GET','/api/session')[2]['csrf']; before=store.export_json()['tables']
    body={'mode':'command','applicationId':application,'query':'Przejrzyj wszystkie moje materiały pod kątem aplikacji na animatora KRC.'}
    check('Odczyt materiałów bez CSRF jest odrzucony',request('POST','/api/ai/prepare',body,{'X-CSRF-Token':''})[0]==403)
    status,_,preview=request('POST','/api/ai/prepare',body)
    check('Polecenie przez HTTP uruchamia przegląd materiałów',status==200 and preview['mode']=='materials')
    check('Lokalny model otrzymuje tekst pliku',preview['modelCalled'] and preview['coverage']['analysedFragments']==1)
    check('Brak treści ogłoszenia jest jawny',any('Brak treści ogłoszenia' in x for x in preview['warnings']))
    check('Drive pozostaje nieodczytany',next(x for x in preview['inventory'] if x['title']=='Drive DEMO')['status']=='Nieodczytany')
    check('Podgląd przez API nie zmienia bazy',store.export_json()['tables']==before)
    commit={'token':preview['token'],'revision':preview['revision'],'confirmed':False}
    check('Brak potwierdzenia nie zapisuje raportu',request('POST','/api/ai/commit',commit)[0]==422 and store.export_json()['tables']==before)
    commit['confirmed']=True; status,_,saved=request('POST','/api/ai/commit',commit)
    check('Potwierdzenie zapisuje raport przy właściwej aplikacji',status==200 and len(saved['ids'])==1 and any(x['materialId']==saved['ids'][0] and x['applicationId']==application for x in saved['state']['links']))
    check('Oryginalny plik i profil pozostają bez zmian',len(saved['state']['entries'])==0 and any(x['id']==material for x in saved['state']['materials']))
    check('Powtórne potwierdzenie nie powiela zapisu',request('POST','/api/ai/commit',commit)[0]==409)
    (directory/'preview-demo.json').write_text(json.dumps(preview,ensure_ascii=False),encoding='utf-8')
    (ROOT/'app/tests/materials-http-report.json').write_text(json.dumps({'result':'PASS','count':len(checks),'checks':checks,'directory':str(directory),'realModel':preview['model'],'data':'Oddzielna baza DEMO; rzeczywisty lokalny model.'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS:',len(checks),'kontroli HTTP przeglądu materiałów.')
finally:
    process.terminate(); process.wait(timeout=10)
