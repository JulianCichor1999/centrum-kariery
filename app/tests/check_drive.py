"""Real Windows vault and local OAuth callback; Google responses are simulated."""
import asyncio
import copy
import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import urllib.parse
import zipfile

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.drive import Drive,API,AUTH,TOKEN,SCOPE,FOLDER,DOC,MAX_FILE,folder_id,file_id,GoogleTransport,NoRedirect
from app.storage import Store
from app.server import create_app
from app.secret_store import SecretStore
from app.validation import DomainError
from app.materials import MaterialReader

directory=Path(tempfile.mkdtemp(prefix='drive-demo-',dir=ROOT/'.test-data')); checks=[]
def check(name,ok=True):
    assert ok,name; checks.append(name)
def reject(fn,status=None):
    try: fn()
    except DomainError as error:
        if status: assert error.status==status,(error.message,error.status)
        return True
    raise AssertionError('Expected rejection')
CLIENT={'installed':{'client_id':'123456-demo.apps.googleusercontent.com','client_secret':'SECRET-DEMO','auth_uri':AUTH,'token_uri':TOKEN}}
F='folder_demo_123456'; D='doc_demo_123456'; P='pdf_demo_123456'; O='outside_demo_123456'; B='bad_demo_123456'; T='txt_demo_123456'
def meta(key,name,mime,parent=F,size=40): return {'id':key,'name':name,'mimeType':mime,'parents':[parent],'size':str(size),'modifiedTime':'2026-10-13T09:00:00Z','version':'1','capabilities':{'canDownload':True},'webViewLink':'https://drive.google.com/file/d/'+key+'/view','trashed':False}
class FakeGoogle:
    def __init__(self):
        self.calls=[]; self.data={F:meta(F,'Folder DEMO',FOLDER),D:meta(D,'CV DEMO',DOC),P:meta(P,'portfolio-demo.pdf','application/pdf'),O:meta(O,'private.txt','text/plain','other_folder_123'),B:meta(B,'invalid.pdf','application/pdf'),T:meta(T,'notatki-demo.txt','text/plain')}; self.content={D:'Uczę się n8n. Materiał DEMO, nie są to dane Juliana.'.encode(),P:b'%PDF-1.4\nDEMO',B:b'wrong-pdf',T:b'Note DEMO'}; self.broad=False; self.change=False; self.revoke_error=False
    def json(self,url,params=None,token=None,form=None,limit=1024*1024):
        self.calls.append((url,params,token,copy.deepcopy(form)))
        if url==TOKEN: return {'access_token':'ACCESS-DEMO','refresh_token':'REFRESH-DEMO','expires_in':3600,'token_type':'Bearer','scope':SCOPE+(' https://www.googleapis.com/auth/drive' if self.broad else '')}
        assert token=='ACCESS-DEMO'
        if url==API:
            folder=params['q'].split("'")[1]
            assert params['q']=="'"+folder+"' in parents and trashed = false"
            return {'files':[x for x in self.data.values() if x['id']!=folder and folder in x['parents'] and not x['trashed']]}
        key=url.rsplit('/',1)[-1]
        if key not in self.data: raise DomainError('DEMO inaccessible metadata',status=502)
        value=copy.deepcopy(self.data[key])
        if self.change and key==T: value['version']='2'; self.change=False
        return value
    def request(self,url,params=None,token=None,form=None,limit=1024*1024):
        self.calls.append((url,params,token,form))
        if url.endswith('/revoke'):
            if self.revoke_error: raise DomainError('DEMO failure')
            return b''
        key=url.split('/')[-2] if url.endswith('/export') else url.rsplit('/',1)[-1]
        if key==T and self.change=='download': self.change=True
        content=self.content[key]
        if len(content)>limit: raise DomainError('DEMO over limit')
        return content

store=Store(directory); google=FakeGoogle(); drive=Drive(store,google)
check('Nowa konfiguracja nie twierdzi, że ma dostęp do Drive',not drive.status()['configured'] and not drive.status()['authorized'] and not google.calls)
check('Wymagany JSON Desktop, nie web',reject(lambda:drive.configure(json.dumps({'web':CLIENT['installed']}).encode())))
bad=copy.deepcopy(CLIENT); bad['installed']['token_uri']='https://evil.example/'
check('Nie można podstawić adresu wymiany sekretu',reject(lambda:drive.configure(json.dumps(bad).encode())))
drive.configure(json.dumps(CLIENT).encode())
legacy=copy.deepcopy(CLIENT); legacy['installed']['auth_uri']='https://accounts.google.com/o/oauth2/auth'; drive.configure(json.dumps(legacy).encode(),True)
check('Oryginalny JSON Google ze starszym adresem auth jest obsługiwany',drive.status()['configured'])
encrypted=(directory/'.secrets/client.dpapi').read_bytes()
check('Rzeczywiste Windows DPAPI szyfruje sekret',b'SECRET-DEMO' not in encrypted and drive.vault.read('client')['client_secret']=='SECRET-DEMO')
check('Zastąpienie konfiguracji wymaga potwierdzenia',reject(lambda:drive.configure(json.dumps(CLIENT).encode())))
check('Login wymaga potwierdzenia zakresu',reject(lambda:drive.connect('owner',False)))
auth=drive.connect('owner',True); params=urllib.parse.parse_qs(urllib.parse.urlsplit(auth['url']).query)
check('OAuth zawiera tylko odczyt oraz PKCE S256',params['scope']==[SCOPE] and params['code_challenge_method']==['S256'] and 'code_verifier' not in auth['url'] and 'SECRET-DEMO' not in auth['url'])
callback=urllib.parse.urlsplit(params['redirect_uri'][0])
def callback_get(query,host=None):
    conn=http.client.HTTPConnection(callback.hostname,callback.port,timeout=5)
    conn.request('GET','/?'+urllib.parse.urlencode(query),headers={'Host':host or callback.netloc}); response=conn.getresponse(); status=response.status; response.read(); conn.close(); return status
check('Callback odrzuca obcy Host',callback_get({'state':params['state'][0],'code':'CODE-DEMO'},'evil.example')==400 and not drive.status()['authorized'])
check('Callback odrzuca nieprawidłowy state',callback_get({'state':'wrong','code':'CODE-DEMO'})==400 and not drive.status()['authorized'])
check('Prawidłowy callback wymienia kod i zapisuje autoryzację',callback_get({'state':params['state'][0],'code':'CODE-DEMO'})==200 and drive.status()['authorized'])
token_call=next(x for x in google.calls if x[0]==TOKEN)
check('Wymiana kodu używa serwerowego sekretu i weryfikatora',token_call[3]['client_secret']=='SECRET-DEMO' and len(token_call[3]['code_verifier'])>=43)
check('Status nigdy nie ujawnia tokenu lub sekretu',all(s not in json.dumps(drive.status()) for s in ('ACCESS-DEMO','REFRESH-DEMO','SECRET-DEMO')))
check('Szerszy zakres autoryzacji jest odrzucony',reject(lambda:drive.save_token({'access_token':'x','refresh_token':'y','expires_in':3600,'token_type':'Bearer','scope':SCOPE+' https://www.googleapis.com/auth/drive'})))
check('Folder URL jest normalizowany',folder_id('https://drive.google.com/drive/u/0/folders/'+F+'?usp=sharing')==F)
check('Id folderu nie pozwala wstrzyknąć zapytania',reject(lambda:file_id("abc' or 1=1")))
check('Link do pliku nie jest folderem',reject(lambda:folder_id('https://drive.google.com/file/d/'+D+'/view')))
drive.set_folder('https://drive.google.com/drive/folders/'+F)
files=drive.files(); check('Lista pobiera tylko bezpośrednią zawartość bieżącego folderu',files['folder']['id']==F and len(files['items'])==4)
check('Folder i Arkusze nie są importowane',bool(drive.supported(meta('sheets_demo_123','Sheet','application/vnd.google-apps.spreadsheet'))) and bool(drive.supported(meta('folder_sub_123','Folder',FOLDER))))
before=store.export_json()['tables']; oldfiles=list(store.files.iterdir())
check('Import spoza wybranego folderu odrzucony',reject(lambda:drive.preview('owner',[{'id':O,'kind':'Inny'}])))
check('Fałszywy PDF odrzucony przed zapisem',reject(lambda:drive.preview('owner',[{'id':B,'kind':'Inny'}])))
check('Maksymalnie pięć zaznaczonych plików',reject(lambda:drive.preview('owner',[{'id':D,'kind':'CV'}]*6)))
plan=drive.preview('owner',[{'id':D,'kind':'CV'},{'id':P,'kind':'Portfolio'},{'id':O,'kind':'Inny'}])
check('Podgląd pokazuje pliki i jawnie pomija niedostępny',len(plan['items'])==2 and len(plan['skipped'])==1)
check('Podgląd nie zapisuje rekordów ani plików',store.export_json()['tables']==before and list(store.files.iterdir())==oldfiles)
check('Podgląd nie ujawnia treści dokumentu',b'Ucz' not in json.dumps(plan).encode() and 'content' not in json.dumps(plan))
check('Import wymaga potwierdzenia',reject(lambda:drive.commit('owner',plan['token'],plan['revision'],False)))
check('Inna sesja nie zatwierdzi podglądu',reject(lambda:drive.commit('other',plan['token'],plan['revision'],True),409))
ids=drive.commit('owner',plan['token'],plan['revision'],True)
check('Potwierdzenie zapisuje powiązane lokalne kopie',len(ids)==2 and len(store.state()['materials'])==2)
native=next(x for x in store.state()['materials'] if x['kind']=='CV')
check('Dokument Google jest eksportowany jako TXT ze źródłem',native['fileName']=='CV DEMO.txt' and native['url'].startswith('https://drive.google.com/') and (store.files/native['fileKey']).read_bytes()==google.content[D])
check('Integralność kopii ma SHA256',native['sha256']==hashlib.sha256(google.content[D]).hexdigest())
parts,_,_,_=MaterialReader(store.files).read(native)
check('AI odczytuje lokalną kopię mimo linku źródłowego Drive',any('n8n' in part['text'] for part in parts))
check('Ponowne zatwierdzenie nie tworzy duplikatów',reject(lambda:drive.commit('owner',plan['token'],plan['revision'],True),409))
check('Import tej samej wersji nie tworzy duplikatu',reject(lambda:drive.preview('owner',[{'id':D,'kind':'CV'}])))
archive=store.archive_bytes()
check('Pełna kopia nie zawiera sekretów ani autoryzacji',all(x not in archive for x in (b'SECRET-DEMO',b'ACCESS-DEMO',b'REFRESH-DEMO')) and not any('.secrets' in n for n in zipfile.ZipFile(io.BytesIO(archive)).namelist()))
check('Kopia z nowymi materiałami zachowuje walidację',bool(store.validate_snapshot(store.export_json())))
plan=drive.preview('owner',[{'id':T,'kind':'Inny'}]); store.mutate('saveTask',{'title':'DEMO zmiana bazy','due':'2026-10-14','applicationId':''},None,None,store.state()['revision'])
check('Zmiana bazy blokuje stary podgląd',reject(lambda:drive.commit('owner',plan['token'],plan['revision'],True),409))
saved=store.export_json()['tables']; existing=set(store.files.iterdir()); row={'data':{'title':'DEMO duplicate','kind':'Inny','version':'1','url':'','description':''},'name':'a.txt','content':b'DEMO'}
check('Błąd drugiego rekordu wycofuje cały import',reject(lambda:store.import_materials([row,row],store.state()['revision'])) and store.export_json()['tables']==saved and set(store.files.iterdir())==existing)
google.change='download'
check('Zmiana pliku podczas pobierania jest odrzucona',reject(lambda:drive.preview('owner',[{'id':T,'kind':'Inny'}])))
old=drive.vault.read('token'); old['expires']=0; drive.vault.write('token',old); drive.files()
check('Wygasły token jest odświeżany po stronie serwera',any(x[3] and x[3].get('grant_type')=='refresh_token' for x in google.calls))
check('Transport nie przenosi tokenu przez przekierowania',NoRedirect().redirect_request(None,None,None,None,None,None) is None)
check('Transport odrzuca dowolne adresy',reject(lambda:GoogleTransport().request('https://evil.example/',token='ACCESS-DEMO')))

# Exercise actual ASGI routes, multipart parser, session and CSRF boundary.
boundary=create_app(directory,8778); webdrive=boundary.app.state.drive
webdrive.transport=google
async def http(method,path,body=b'',headers=None):
    outgoing=[]; delivered=False
    parsed=urllib.parse.urlsplit(path)
    async def receive():
        nonlocal delivered
        if not delivered: delivered=True; return {'type':'http.request','body':body,'more_body':False}
        return {'type':'http.disconnect'}
    async def send(message): outgoing.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':parsed.path,'raw_path':parsed.path.encode(),'query_string':parsed.query.encode(),'root_path':'','headers':[(k.lower().encode(),v.encode()) for k,v in {'Host':'127.0.0.1:8778',**(headers or {})}.items()],'server':('127.0.0.1',8778),'client':('127.0.0.1',12345)}
    await boundary(scope,receive,send)
    start=next(x for x in outgoing if x['type']=='http.response.start'); payload=b''.join(x.get('body',b'') for x in outgoing if x['type']=='http.response.body'); return start,payload
def req(*args,**kwargs): return asyncio.run(http(*args,**kwargs))
check('Drive API nie udostępnia statusu bez sesji',req('GET','/api/drive/status')[0]['status']==401)
start,_=req('GET','/'); cookie=next(v.decode().split(';')[0] for k,v in start['headers'] if k==b'set-cookie')
csrf=json.loads(req('GET','/api/session',headers={'Cookie':cookie})[1])['csrf']
headers={'Cookie':cookie,'Origin':'http://127.0.0.1:8778','Content-Type':'application/json','X-CSRF-Token':csrf}
check('Połączenie wymaga CSRF',req('POST','/api/drive/connect',b'{"confirmed":true}',{**headers,'X-CSRF-Token':''})[0]['status']==403)
check('Połączenie wymaga własnego Origin',req('POST','/api/drive/connect',b'{"confirmed":true}',{**headers,'Origin':'https://evil.example'})[0]['status']==403)
check('API odrzuca brak zgody',req('POST','/api/drive/connect',b'{"confirmed":false}',headers)[0]['status']==422)
check('API status nie ujawnia sekretów',all(x not in req('GET','/api/drive/status',headers={'Cookie':cookie})[1] for x in (b'ACCESS-DEMO',b'SECRET-DEMO')))
multipart=b'--DEMO\r\nContent-Disposition: form-data; name="file"; filename="client.json"\r\nContent-Type: application/json\r\n\r\n'+json.dumps(CLIENT).encode()+b'\r\n--DEMO\r\nContent-Disposition: form-data; name="confirmed"\r\n\r\ntrue\r\n--DEMO--\r\n'
start,payload=req('POST','/api/drive/client',multipart,{**headers,'Content-Type':'multipart/form-data; boundary=DEMO'})
check('Upload JSON przez chroniony multipart działa',start['status']==200 and json.loads(payload)['configured'] and not json.loads(payload)['authorized'])
check('Brak autoryzacji blokuje odczyt plików przez API',req('GET','/api/drive/files',headers={'Cookie':cookie})[0]['status']==422)
webdrive.save_token({'access_token':'ACCESS-DEMO','refresh_token':'REFRESH-DEMO','expires_in':3600,'token_type':'Bearer','scope':SCOPE}); webdrive.set_folder(F)
start,payload=req('POST','/api/drive/preview',json.dumps({'selection':[{'id':T,'kind':'Inny'}]}).encode(),headers); webplan=json.loads(payload)
check('Rzeczywisty endpoint przygotowuje podgląd',start['status']==200 and webplan['items'][0]['title']=='notatki-demo.txt')
start,payload=req('POST','/api/drive/commit',json.dumps({'token':webplan['token'],'revision':webplan['revision'],'confirmed':True}).encode(),headers)
check('Rzeczywisty endpoint zapisuje potwierdzony import',start['status']==200 and len(json.loads(payload)['ids'])==1)
google.revoke_error=True; before=store.state()['materials']; status=webdrive.disconnect(True)
check('Odłączenie czyści autoryzację nawet przy błędzie Google',not status['authorized'] and bool(status['error']) and store.state()['materials']==before)
check('Restart nie deklaruje połączenia po odłączeniu',not Drive(store,google).status()['authorized'])
webdrive.vault.path('client').write_bytes(b'CORRUPT DEMO')
check('Uszkodzona konfiguracja pozwala otworzyć ustawienia odzyskiwania',webdrive.status()['unreadable'] and not webdrive.status()['authorized'])
webdrive.configure(json.dumps(CLIENT).encode(),True)
check('Potwierdzone dodanie JSON naprawia nieczytelny sekret',webdrive.status()['configured'] and not webdrive.status()['unreadable'])
webdrive.connect('owner',True); expired_item=webdrive.auth; webdrive.auth['expires']=time.monotonic()-1
expired=webdrive.status()
check('Wygaśnięcie odbiornika wskazuje potrzebę nowego logowania',not expired['pending'] and not expired['authorized'] and 'wygas' in expired['error'])
check('Spóźniony kod nie zostaje wymieniony po wygaśnięciu',reject(lambda:webdrive.finish(expired_item,{'code':['LATE-DEMO']})) and not webdrive.status()['authorized'])
webdrive.connect('owner',True)
check('Nowe logowanie usuwa błąd wygaśnięcia i otwiera odbiornik',webdrive.status()['pending'] and not webdrive.status()['error'])
webdrive.cancel(); webdrive.save_token({'access_token':'ACCESS-DEMO','refresh_token':'REFRESH-DEMO','expires_in':3600,'token_type':'Bearer','scope':SCOPE}); webdrive.set_folder(F)
S='subfolder_demo_123'; N='nested_txt_demo_123'; X='other_folder_123'; Y='cycle_folder_demo_123'
google.data[S]=meta(S,'1. Automatyzacja',FOLDER); google.data[N]=meta(N,'projekt-n8n-demo.txt','text/plain',S); google.content[N]=b'DEMO: automation project, source text.'
google.data[X]=meta(X,'Outside folder DEMO',FOLDER,'unknown_root_123')
root_listing=webdrive.files()
check('Lista pokazuje podfolder jako folder do otwarcia',any(x['id']==S and x['isFolder'] for x in root_listing['items']))
sub_listing=webdrive.files(S)
check('Podfolder pokazuje własne dokumenty i ścieżkę powrotu',sub_listing['folder']['id']==S and sub_listing['items'][0]['id']==N and [x['id'] for x in sub_listing['breadcrumbs']]==[F,S])
check('Przeglądanie podfolderu zachowuje wybrany folder główny',webdrive.status()['folder']['id']==F)
check('Nawigacja poza główne portfolio jest odrzucona',reject(lambda:webdrive.files(X)))
google.data[Y]=meta(Y,'Cycle DEMO',FOLDER,Y)
check('Cykliczna hierarchia folderów jest odrzucona',reject(lambda:webdrive.files(Y)))
parent=F
for n in range(1,10):
    key=f'depth_demo_folder_{n:02}'; google.data[key]=meta(key,'Depth DEMO '+str(n),FOLDER,parent); parent=key
check('Nawigacja do ośmiu poziomów jest dozwolona',len(webdrive.files('depth_demo_folder_08')['breadcrumbs'])==9)
check('Przekroczenie ośmiu poziomów jest odrzucone',reject(lambda:webdrive.files('depth_demo_folder_09')))
tables_before=store.export_json()['tables']; before_files=set(store.files.iterdir())
sub_plan=webdrive.preview('owner',[{'id':N,'kind':'Portfolio'}])
check('Podgląd dokumentu w podfolderze nie zapisuje danych',len(sub_plan['items'])==1 and store.export_json()['tables']==tables_before and set(store.files.iterdir())==before_files)
saved_ids=webdrive.commit('owner',sub_plan['token'],sub_plan['revision'],True); saved_material=next(x for x in store.state()['materials'] if x['id']==saved_ids[0])
check('Potwierdzony import podfolderu zachowuje pochodzenie i typ','Folder DEMO / 1. Automatyzacja' in saved_material['description'] and saved_material['kind']=='Portfolio')
parts,_,_,_=MaterialReader(store.files).read(saved_material)
check('AI może odczytać zaimportowany dokument podfolderu',any('automation project' in x['text'] for x in parts))
google.data[N]['version']='2'; google.data[S]['parents']=[X]
check('Przeniesiony poza portfolio podfolder blokuje import',reject(lambda:webdrive.preview('owner',[{'id':N,'kind':'Portfolio'}])))
google.data[S]['parents']=[F]
root_listing=webdrive.files()
check('Powrót do głównego folderu przywraca jego listę',root_listing['folder']['id']==F and any(x['id']==S for x in root_listing['items']))
start,payload=req('GET','/api/drive/files?folder='+S,headers={'Cookie':cookie})
check('Chroniony endpoint otwiera wskazany podfolder',start['status']==200 and json.loads(payload)['folder']['id']==S)
check('Chroniony endpoint odrzuca obcy folder',req('GET','/api/drive/files?folder='+X,headers={'Cookie':cookie})[0]['status']!=200)
check('Cały folder wymaga CSRF',req('POST','/api/drive/preview-all',b'{}',{**headers,'X-CSRF-Token':''})[0]['status']==403)
tables_before=store.export_json()['tables'];start,payload=req('POST','/api/drive/preview-all',b'{}',headers)
check('Chroniony endpoint przygotowuje import całego folderu',start['status']==200 and json.loads(payload)['wholeFolder'])
check('Podgląd całego folderu przez API nie zmienia bazy',store.export_json()['tables']==tables_before)
drive.cancel(); webdrive.cancel()
report={'result':'PASS','count':len(checks),'checks':checks,'directory':str(directory),'scope':'Rzeczywiste Windows DPAPI, lokalny callback OAuth i chronione API ASGI. Odpowiedzi Google: symulowane. Bez połączenia z kontem użytkownika.'}
(ROOT/'app/tests/drive-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:',len(checks),'kontroli integracji Drive (Google DEMO).')
