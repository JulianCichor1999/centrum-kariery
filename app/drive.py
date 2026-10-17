"""Read-only Drive import. OAuth is separate from the protected local app boundary."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .secret_store import SecretStore
from .validation import DomainError, fold, material_values
from .transfer import MAX_ARCHIVE

SCOPE='https://www.googleapis.com/auth/drive.readonly'
AUTH='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN='https://oauth2.googleapis.com/token'
API='https://www.googleapis.com/drive/v3/files'
FOLDER='application/vnd.google-apps.folder'
DOC='application/vnd.google-apps.document'
MAX_FILE=5*1024*1024
MAX_BULK_FILE=100*1024*1024
MAX_BULK_BYTES=200*1024*1024
EXPORTS={DOC:('application/vnd.openxmlformats-officedocument.wordprocessingml.document','.docx'),
 'application/vnd.google-apps.spreadsheet':('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.xlsx'),
 'application/vnd.google-apps.presentation':('application/vnd.openxmlformats-officedocument.presentationml.presentation','.pptx'),
 'application/vnd.google-apps.drawing':('application/pdf','.pdf'),
 'application/vnd.google-apps.script':('application/vnd.google-apps.script+json','.json')}
LOGIN_EXPIRED='Sesja logowania Google wygasła. Zamknij starą kartę Google i kliknij ponownie „Połącz Google Drive”, aby otrzymać nowy link.'
FIELDS='id,name,mimeType,size,modifiedTime,version,webViewLink,parents,trashed,capabilities(canDownload)'

def file_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',value): raise DomainError('Nieprawidłowy identyfikator pliku lub folderu.')
    return value

def folder_id(value):
    if isinstance(value,str) and value.startswith('https://'):
        url=urllib.parse.urlsplit(value)
        match=re.fullmatch(r'/drive(?:/u/\d+)?/folders/([A-Za-z0-9_-]+)',url.path.rstrip('/'))
        if url.hostname!='drive.google.com' or url.port or url.username or not match: raise DomainError('Wklej link do folderu Google Drive, nie do pojedynczego pliku.')
        value=match[1]
    return file_id(value)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class GoogleTransport:
    def __init__(self): self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def request(self,url,params=None,token=None,form=None,limit=1024*1024):
        if not (url in (TOKEN,'https://oauth2.googleapis.com/revoke') or url==API or url.startswith(API+'/')): raise DomainError('Niedozwolony adres integracji.')
        if params: url+='?'+urllib.parse.urlencode(params)
        headers={'Accept-Encoding':'identity'}
        if token: headers['Authorization']='Bearer '+token
        data=None
        if form is not None: data=urllib.parse.urlencode(form).encode(); headers['Content-Type']='application/x-www-form-urlencoded'
        try:
            with self.opener.open(urllib.request.Request(url,data=data,headers=headers),timeout=15) as response:
                content=response.read(limit+1)
                if len(content)>limit: raise DomainError('Plik lub odpowiedź Google przekracza dozwolony rozmiar ('+str(limit//1024//1024)+' MB).')
                return content
        except urllib.error.HTTPError as error:
            if error.code in (400,401): raise DomainError('Google odrzucił autoryzację lub żądanie. Sprawdź konfigurację; w razie wygaśnięcia połącz konto ponownie.',status=502)
            if error.code==403: raise DomainError('Google odmówił dostępu. Sprawdź zgodę, włączenie Drive API i możliwość pobierania pliku.',status=502)
            if error.code==404: raise DomainError('Google nie udostępnia wskazanego pliku lub folderu temu kontu.',status=502)
            raise DomainError('Google nie zakończył operacji. Spróbuj ponownie później.',status=502)
        except (urllib.error.URLError,TimeoutError,OSError): raise DomainError('Nie udało się połączyć z Google. Sprawdź internet i spróbuj ponownie.',status=502)
    def json(self,*args,**kwargs):
        try:
            value=json.loads(self.request(*args,**kwargs))
            if not isinstance(value,dict): raise ValueError()
            return value
        except (ValueError,UnicodeError): raise DomainError('Nieprawidłowa odpowiedź Google.',status=502)

class Drive:
    def __init__(self,store,transport=None,vault=None):
        self.store=store; self.transport=transport or GoogleTransport(); self.vault=vault or SecretStore(store.directory)
        self.lock=threading.RLock(); self.auth=None; self.pending={}; self.last_error=''
    def status(self):
        with self.lock:
            if self.auth and self.auth['expires']<=time.monotonic():
                self.auth['stop'].set(); self.auth=None; self.last_error=LOGIN_EXPIRED
            try:
                return {'configured':bool(self.vault.read('client')),'authorized':bool(self.vault.read('token')),'folder':self.vault.read('folder'),
                        'pending':bool(self.auth and self.auth['expires']>time.monotonic()),'error':self.last_error,'scope':SCOPE,'unreadable':False}
            except DomainError as error:
                return {'configured':True,'authorized':False,'folder':None,'pending':False,'error':error.message,'scope':SCOPE,'unreadable':True}
    def cancel(self):
        if self.auth: self.auth['stop'].set(); self.auth=None
        self.pending.clear()
    def configure(self,content,confirmed=False):
        if not content or len(content)>64000: raise DomainError('Wybierz plik JSON klienta OAuth, do 64 KB.')
        try:
            data=json.loads(content); client=data['installed']
            if not isinstance(client,dict) or 'web' in data or not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',client['client_id']) or not isinstance(client['client_secret'],str) or not 1<=len(client['client_secret'])<=500: raise ValueError()
            if client.get('auth_uri',AUTH) not in (AUTH,'https://accounts.google.com/o/oauth2/auth') or client.get('token_uri',TOKEN)!=TOKEN: raise ValueError()
        except (ValueError,TypeError,KeyError,UnicodeError): raise DomainError('Potrzebny jest oryginalny JSON klienta OAuth typu „Aplikacja komputerowa” pobrany z Google Cloud.')
        with self.lock:
            try: existing=self.vault.read('client')
            except DomainError: existing=True
            if existing and confirmed is not True: raise DomainError('Potwierdź zastąpienie konfiguracji. Bieżąca autoryzacja zostanie usunięta lokalnie.')
            self.vault.write('client',{'client_id':client['client_id'],'client_secret':client['client_secret']})
            self.vault.remove('token'); self.vault.remove('folder'); self.cancel(); self.last_error=''
            return self.status()
    def connect(self,owner,confirmed):
        if confirmed is not True: raise DomainError('Potwierdź zakres odczytu Google Drive przed logowaniem.')
        with self.lock:
            client=self.vault.read('client')
            if not client: raise DomainError('Najpierw dodaj plik JSON klienta OAuth.')
            self.cancel(); self.vault.remove('token'); self.vault.remove('folder'); self.last_error=''
            item={'owner':owner,'state':secrets.token_urlsafe(32),'verifier':secrets.token_urlsafe(64),'expires':time.monotonic()+600,'stop':threading.Event()}
            integration=self
            class Callback(BaseHTTPRequestHandler):
                def log_message(self,*args): pass
                def do_GET(self):
                    message='Nieprawidłowa odpowiedź logowania.'; status=400
                    url=urllib.parse.urlsplit(self.path)
                    params=urllib.parse.parse_qs(url.query,keep_blank_values=True)
                    if self.headers.get('Host')==item['host'] and len(self.headers.get_all('Host',[]))==1 and url.path=='/' and len(params.get('state',[]))==1 and all(len(v)==1 for v in params.values()) and secrets.compare_digest(params['state'][0],item['state']):
                        try:
                            integration.finish(item,params); message='Połączono Google Drive. Wróć do Ustawień i kliknij „Sprawdź stan”, następnie ustaw folder.'; status=200
                        except DomainError as error: message=error.message
                    content=message.encode('utf-8'); self.send_response(status); self.send_header('Content-Type','text/plain; charset=utf-8'); self.send_header('Content-Length',str(len(content))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'"); self.end_headers(); self.wfile.write(content)
            class LocalServer(HTTPServer):
                def get_request(self):
                    socket,address=super().get_request(); socket.settimeout(3); return socket,address
                def handle_error(self,*args): pass
            server=LocalServer(('127.0.0.1',0),Callback); server.timeout=.5
            item['host']=f'127.0.0.1:{server.server_port}'; item['redirect']='http://'+item['host']+'/'
            self.auth=item
            def listen():
                try:
                    while not item['stop'].is_set() and time.monotonic()<item['expires']: server.handle_request()
                finally:
                    server.server_close()
                    with integration.lock:
                        if integration.auth is item:
                            integration.auth=None
                            if time.monotonic()>=item['expires']: integration.last_error=LOGIN_EXPIRED
            threading.Thread(target=listen,daemon=True).start()
            challenge=base64.urlsafe_b64encode(hashlib.sha256(item['verifier'].encode()).digest()).rstrip(b'=').decode()
            return {'url':AUTH+'?'+urllib.parse.urlencode({'client_id':client['client_id'],'redirect_uri':item['redirect'],'response_type':'code','scope':SCOPE,'state':item['state'],'code_challenge':challenge,'code_challenge_method':'S256','access_type':'offline','prompt':'consent'})}
    def finish(self,item,params):
        with self.lock:
            if self.auth is not item or item['expires']<time.monotonic() or item['stop'].is_set(): raise DomainError('Logowanie wygasło. Rozpocznij je ponownie.')
            item['stop'].set(); self.auth=None
            try:
                if 'error' in params: raise DomainError('Nie udzielono zgody Google. Możesz rozpocząć logowanie ponownie.')
                code=params.get('code',[''])[0]
                if not code or len(code)>4000: raise DomainError('Brak poprawnego potwierdzenia Google.')
                client=self.vault.read('client')
                result=self.transport.json(TOKEN,form={**client,'code':code,'code_verifier':item['verifier'],'redirect_uri':item['redirect'],'grant_type':'authorization_code'})
                self.save_token(result)
            except DomainError as error: self.last_error=error.message; raise
    def save_token(self,result,previous=None):
        refresh=result.get('refresh_token') or (previous or {}).get('refresh_token')
        access=result.get('access_token'); expiry=result.get('expires_in')
        if result.get('token_type','').lower()!='bearer' or not isinstance(access,str) or not 1<=len(access)<=8000 or not isinstance(refresh,str) or not 1<=len(refresh)<=8000 or type(expiry) is not int or not 0<expiry<=86400 or set(result.get('scope',SCOPE).split())!={SCOPE}: raise DomainError('Google nie zwrócił wymaganej autoryzacji odczytu. Połącz konto ponownie.')
        self.vault.write('token',{'access_token':access,'refresh_token':refresh,'expires':time.time()+expiry})
    def access(self):
        token=self.vault.read('token')
        if not token: raise DomainError('Połącz konto Google przed odczytem folderu.')
        if token['expires']<time.time()+60:
            client=self.vault.read('client')
            self.save_token(self.transport.json(TOKEN,form={**client,'refresh_token':token['refresh_token'],'grant_type':'refresh_token'}),token)
            token=self.vault.read('token')
        return token['access_token']
    def disconnect(self,confirmed):
        if confirmed is not True: raise DomainError('Potwierdź odłączenie Google Drive.')
        with self.lock:
            token=self.vault.read('token'); warning=''
            if token:
                try: self.transport.request('https://oauth2.googleapis.com/revoke',form={'token':token['refresh_token']})
                except DomainError: warning='Usunięto lokalną autoryzację. Nie potwierdzono cofnięcia zgody w Google — usuń dostęp także w ustawieniach konta Google.'
            self.cancel(); self.vault.remove('token'); self.vault.remove('folder'); self.last_error=warning
            return self.status()
    def metadata(self,key,access): return self.transport.json(API+'/'+file_id(key),params={'fields':FIELDS,'supportsAllDrives':'true'},token=access)
    def set_folder(self,value):
        with self.lock:
            key=folder_id(value); meta=self.metadata(key,self.access())
            if meta.get('id')!=key or meta.get('mimeType')!=FOLDER or meta.get('trashed'): raise DomainError('Wskaż istniejący folder Google Drive.')
            self.vault.write('folder',{'id':key,'name':str(meta.get('name','Folder'))[:180]}); self.pending.clear()
            return self.status()
    @staticmethod
    def supported(meta):
        if meta.get('trashed'): return 'Plik znajduje się w koszu.'
        if meta.get('capabilities',{}).get('canDownload') is False: return 'Właściciel zablokował pobieranie.'
        if meta.get('mimeType')==DOC: return ''
        if meta.get('mimeType')==FOLDER: return 'Otwórz folder, aby wybrać jego dokumenty.'
        if meta.get('mimeType','').startswith('application/vnd.google-apps.'): return 'Obsługujemy Dokumenty Google; skróty, Arkusze i Prezentacje są pomijane.'
        if Path(str(meta.get('name',''))).suffix.lower() not in ('.pdf','.docx','.txt','.md','.json'): return 'Obsługiwane pliki: PDF, DOCX, TXT, MD, JSON.'
        try:
            if int(meta.get('size',MAX_FILE+1))>MAX_FILE: return 'Plik przekracza 5 MB.'
        except (ValueError,TypeError): return 'Nieznany rozmiar pliku.'
        return ''
    def folder_chain(self,key,root,access,cache=None):
        """Prove ancestry before browsing or downloading; shortcuts are not followed."""
        key=file_id(key)
        if key==root['id']: return [root]
        chain=[]; seen=set()
        for _ in range(8):
            if key in seen: break
            seen.add(key); meta=cache[key] if cache is not None and key in cache else self.metadata(key,access)
            if meta.get('id')!=key or meta.get('mimeType')!=FOLDER or meta.get('trashed'): break
            chain.append({'id':key,'name':str(meta.get('name','Folder'))[:180]})
            parents=meta.get('parents',[])
            if root['id'] in parents: return [root,*reversed(chain)]
            if len(parents)!=1: break
            key=file_id(parents[0])
        raise DomainError('Folder nie należy do wybranego portfolio albo przekracza limit 8 poziomów podfolderów.')
    def material_chain(self,meta,root,access,cache=None):
        parents=meta.get('parents',[])
        if root['id'] in parents: return [root]
        if len(parents)==1: return self.folder_chain(parents[0],root,access,cache)
        raise DomainError('Plik nie należy do wybranego folderu portfolio ani jego podfolderów.')
    def list_metadata(self,key,access):
        items=[]; page=''; partial=False
        for _ in range(2):
            params={'q':"'"+file_id(key)+"' in parents and trashed = false",'pageSize':100,'fields':'nextPageToken,incompleteSearch,files('+FIELDS+')','supportsAllDrives':'true','includeItemsFromAllDrives':'true','orderBy':'name'}
            if page: params['pageToken']=page
            result=self.transport.json(API,params=params,token=access); items.extend(result.get('files',[])[:100]); page=result.get('nextPageToken',''); partial=partial or bool(result.get('incompleteSearch'))
            if not page: break
        return [m for m in items if key in m.get('parents',[]) and not m.get('trashed')],bool(page or partial)
    def files(self,key=''):
        with self.lock:
            root=self.vault.read('folder')
            if not root: raise DomainError('Najpierw ustaw folder materiałów.')
            access=self.access(); chain=self.folder_chain(key or root['id'],root,access); folder=chain[-1]
            items,partial=self.list_metadata(folder['id'],access)
            return {'folder':folder,'breadcrumbs':chain,'partial':partial,'items':[{'id':file_id(m['id']),'name':str(m.get('name','Plik'))[:180],'isFolder':m.get('mimeType')==FOLDER,'reason':self.supported(m),'modifiedTime':str(m.get('modifiedTime',''))[:60]} for m in items]}
    def preview(self,owner,selection):
        if not isinstance(selection,list) or not 1<=len(selection)<=5 or any(not isinstance(x,dict) or set(x)!={'id','kind'} or x['kind'] not in ('CV','Portfolio','List','Wiadomość','Inny') for x in selection): raise DomainError('Wybierz od 1 do 5 plików i ich typy.')
        with self.lock: return self.prepare(owner,selection)
    def preview_all(self,owner):
        with self.lock:
            root=self.vault.read('folder')
            if not root: raise DomainError('Najpierw ustaw główny folder Portfolio.')
            access=self.access(); deadline=time.monotonic()+600; queue=[(root['id'],[root])]; visited=set(); folder_cache={}; files={}; warnings=[]
            while queue:
                key,path=queue.pop(0)
                if key in visited: continue
                if len(visited)>=50 or time.monotonic()>=deadline:
                    warnings.append('Nie przeskanowano całego drzewa: limit 50 folderów lub 10 minut.'); break
                visited.add(key)
                try:
                    items,partial=self.list_metadata(key,access)
                    if partial: warnings.append('Niepełna lista w folderze: '+' / '.join(x['name'] for x in path))
                    for meta in items:
                        identifier=file_id(meta['id'])
                        if meta.get('mimeType')==FOLDER:
                            if len(path)>8:
                                warnings.append('Pominięto głębszy folder (limit 8 poziomów): '+str(meta.get('name','Folder'))); continue
                            folder_cache[identifier]=meta
                            queue.append((identifier,path+[{'id':identifier,'name':str(meta.get('name','Folder'))[:180]}]))
                        elif identifier not in files:
                            if len(files)>=200:
                                warnings.append('Nie przeskanowano wszystkich plików: limit 200.'); queue.clear(); break
                            files[identifier]={'id':identifier,'kind':'Portfolio','name':str(meta.get('name','Plik'))[:180]}
                except DomainError as error: warnings.append('Folder '+' / '.join(x['name'] for x in path)+': '+error.message)
            return self.prepare(owner,list(files.values()),whole=True,folder_cache=folder_cache,warnings=warnings,folder_count=len(visited),deadline=deadline)
    def prepare(self,owner,selection,whole=False,folder_cache=None,warnings=None,folder_count=0,deadline=None):
        keys=[file_id(x['id']) for x in selection]
        if len(set(keys))!=len(keys): raise DomainError('Wybierz każdy plik tylko raz.')
        folder=self.vault.read('folder')
        if not folder: raise DomainError('Najpierw ustaw folder materiałów.')
        access=self.access(); state=self.store.state(); rows=[]; skipped=[]; warnings=list(warnings or []); total=0
        capacity=MAX_BULK_BYTES
        if whole:
            snapshot_size=len(json.dumps(self.store.export_json(),ensure_ascii=False).encode('utf-8'))
            capacity=min(capacity,MAX_ARCHIVE-snapshot_size-sum(x['size'] for x in state['materials'])-2*1024*1024)
        for choice in selection:
            name=choice.get('name',choice['id'])
            try:
                if deadline is not None and time.monotonic()>=deadline: raise DomainError('Przekroczono czas przygotowania importu (10 minut).')
                meta=self.metadata(choice['id'],access)
                if meta.get('id')!=choice['id']: raise DomainError('Nieprawidłowy identyfikator materiału Google.')
                chain=self.material_chain(meta,folder,access,folder_cache)
                name=Path(str(meta['name']).replace('\\','/')).name[:180]
                mime=meta.get('mimeType',''); export=None
                if whole:
                    if meta.get('trashed') or meta.get('capabilities',{}).get('canDownload') is False: raise DomainError('Google nie zezwala na pobranie tego pliku.')
                    if mime.startswith('application/vnd.google-apps.'):
                        export=EXPORTS.get(mime)
                        if not export: raise DomainError('Google nie udostępnia obsługiwanego eksportu tego typu pliku lub skrótu.')
                    else:
                        try:
                            if int(meta.get('size',MAX_BULK_FILE+1))>MAX_BULK_FILE: raise DomainError('Plik przekracza limit 100 MB.')
                        except (ValueError,TypeError): raise DomainError('Google nie udostępnia poprawnego rozmiaru pliku.')
                else:
                    reason=self.supported(meta)
                    if reason: raise DomainError(reason)
                    if mime==DOC: export=('text/plain','.txt')
                if export: name=name[:160]+export[1]
                title=name[:180]
                identity=choice['id']+'|'+str(meta.get('version',''))+'|'+str(meta.get('modifiedTime',''))
                if whole and export: identity+='|'+export[1]
                version='Drive-'+hashlib.sha256(identity.encode()).hexdigest()[:16]
                if any(fold(x['title'])==fold(title) and x['version']==version for x in state['materials']): raise DomainError('Ta wersja została już zaimportowana.')
                url=meta.get('webViewLink') or 'https://drive.google.com/file/d/'+choice['id']+'/view'
                parsed=urllib.parse.urlsplit(url)
                if parsed.scheme!='https' or parsed.hostname not in ('drive.google.com','docs.google.com') or parsed.username or parsed.port: raise DomainError('Nieprawidłowy link źródła Google.')
                path=' / '.join(x['name'] for x in chain)
                provenance=('Eksport Google do '+export[1][1:].upper()+'. ') if export else 'Plik pobrany bez zmiany treści. '
                data={'title':title,'kind':choice['kind'],'version':version,'url':url,'description':'Import z Google Drive; '+provenance+'Folder: '+path+'. Zmiana w Drive: '+str(meta.get('modifiedTime',''))}
                material_values(data)
                content=self.transport.request(API+'/'+choice['id']+('/export' if export else ''),params={'mimeType':export[0]} if export else {'alt':'media','supportsAllDrives':'true'},token=access,limit=MAX_BULK_FILE if whole else MAX_FILE)
                if whole and total+len(content)>capacity: raise DomainError('Brak miejsca w limicie importu 200 MB lub pełnej kopii 300 MB. Ten plik pominięto.')
                after=self.metadata(choice['id'],access)
                if any(meta.get(k)!=after.get(k) for k in ('version','modifiedTime','parents','trashed')): raise DomainError('Plik zmienił się podczas pobierania. Przygotuj podgląd ponownie.')
                if not whole and [x['id'] for x in chain]!=[x['id'] for x in self.material_chain(after,folder,access)]: raise DomainError('Folder przeniesiono podczas pobierania. Przygotuj podgląd ponownie.')
                extension=Path(name).suffix.lower()
                stored_name=name if extension in ('.pdf','.docx','.txt','.md','.json','.png','.jpg','.jpeg') and len(content)<=20*1024*1024 else name[:175]+'.bin'
                self.store.validate_upload(stored_name,content)
                readable=extension in ('.pdf','.docx','.txt','.md','.json') and len(content)<=MAX_FILE
                rows.append({'data':data,'name':stored_name,'downloadName':name,'content':content,'path':path,'readable':readable,'meta':after,'chain':[x['id'] for x in chain]}); total+=len(content)
            except DomainError as error: skipped.append({'id':choice['id'],'name':name,'reason':error.message})
        if whole and rows:
            # Re-read every relevant ancestor after downloads; do not trust a moved subtree.
            checked={}
            for key in {key for row in rows for key in row['chain'] if key!=folder['id']}:
                try: checked[key]=self.metadata(key,access)
                except DomainError: checked[key]={'id':key,'mimeType':'unavailable'}
            valid=[]
            for row in rows:
                try:
                    if row['chain']!=[x['id'] for x in self.material_chain(row['meta'],folder,access,checked)]: raise DomainError('Folder przeniesiono podczas pobierania. Przygotuj podgląd ponownie.')
                    valid.append(row)
                except DomainError as error: skipped.append({'id':row['meta']['id'],'name':row['downloadName'],'reason':error.message})
            rows=valid
        if not rows and not whole: raise DomainError('Nie przygotowano plików do importu. '+ ' '.join(x['reason'] for x in skipped))
        current=time.monotonic()
        for token in list(self.pending):
            if self.pending[token]['owner']==owner or self.pending[token]['expires']<current: self.pending.pop(token)
        if len(self.pending)>=3: raise DomainError('Za dużo oczekujących importów. Spróbuj później.')
        token=secrets.token_urlsafe(32) if rows else None
        if token: self.pending[token]={'owner':owner,'expires':current+900,'revision':state['revision'],'rows':rows}
        return {'token':token,'revision':state['revision'],'wholeFolder':whole,'folder':folder,'foldersScanned':folder_count,'filesFound':len(selection),'warnings':warnings,'items':[{'title':r['data']['title'],'kind':r['data']['kind'],'version':r['data']['version'],'size':len(r['content']),'path':r['path'],'readable':r['readable']} for r in rows],'skipped':skipped}
    def commit(self,owner,token,revision,confirmed):
        with self.lock:
            item=self.pending.get(token)
            if not item or item['owner']!=owner or item['expires']<time.monotonic(): raise DomainError('Podgląd importu wygasł lub został użyty.',status=409)
            if confirmed is not True or revision!=item['revision']: raise DomainError('Potwierdź aktualny podgląd importu.')
            ids=self.store.import_materials(item['rows'],revision)
            self.pending.pop(token); return ids
