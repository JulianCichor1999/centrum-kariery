"""Lokalny HTTP/API; sesja, CSRF i ograniczenia dostępu na jednym brzegu."""
from pathlib import Path
import json
import secrets
import sqlite3
import time
from typing import Any
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from .storage import Store
from .transfer import MAX_ARCHIVE, digest
from .validation import DomainError, check_uuid
from .ai import Assistant
from .drive import Drive
from .offer_import import OfferImport

STATIC=Path(__file__).with_name('static')
class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str=Field(max_length=40)
    data:dict[str,Any]=Field(default_factory=dict)
    key:str|None=None
    version:int|None=Field(default=None,ge=1)
    revision:int=Field(ge=0)
class Commit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=30,max_length=100)
    revision:int=Field(ge=0)
    confirmed:bool

class AIRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode:str=Field(max_length=20)
    applicationId:str=Field(default='',max_length=36)
    query:str=Field(default='',max_length=2500)
    baseMaterialId:str=Field(default='',max_length=36)
    materialIds:list[str]=Field(default_factory=list,max_length=5)
class AICommit(Commit):
    draft:str|None=Field(default=None,min_length=1,max_length=24000)
class AIConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model:str=Field(max_length=120)
    enabled:bool
    revision:int=Field(ge=0)
class OfferTextCommit(Commit):
    text:str=Field(min_length=1,max_length=10000)

def create_app(directory,port=8766):
    store=Store(directory); api=FastAPI(debug=False,docs_url=None,redoc_url=None,openapi_url=None); pending={}
    api.state.store=store
    assistant=Assistant(store); api.state.assistant=assistant
    drive=Drive(store); api.state.drive=drive
    offer_import=OfferImport(store);api.state.offer_import=offer_import

    @api.post('/api/offers/{key}/read-link')
    def offer_link_preview(key:str,request:Request):return offer_import.preview(request.scope['career_session'],key)
    @api.post('/api/offers/read-link/commit')
    def offer_link_commit(body:OfferTextCommit,request:Request):return {'state':offer_import.commit(request.scope['career_session'],body.token,body.revision,body.confirmed,body.text)}

    @api.get('/api/drive/status')
    def drive_status(): return drive.status()
    @api.post('/api/drive/client')
    async def drive_client(request:Request):
        async with request.form(max_files=1,max_fields=2,max_part_size=64000) as form:
            file=form.get('file')
            if not file or not hasattr(file,'read'): raise DomainError('Wybierz plik JSON klienta OAuth.')
            return drive.configure(await file.read(64001),form.get('confirmed')=='true')
    @api.post('/api/drive/connect')
    def drive_connect(body:dict,request:Request): return drive.connect(request.scope['career_session'],body.get('confirmed'))
    @api.post('/api/drive/disconnect')
    def drive_disconnect(body:dict): return drive.disconnect(body.get('confirmed'))
    @api.post('/api/drive/folder')
    def drive_folder(body:dict): return drive.set_folder(body.get('url'))
    @api.get('/api/drive/files')
    def drive_files(folder:str=''): return drive.files(folder)
    @api.post('/api/drive/preview')
    def drive_preview(body:dict,request:Request): return drive.preview(request.scope['career_session'],body.get('selection'))
    @api.post('/api/drive/preview-all')
    def drive_preview_all(request:Request): return drive.preview_all(request.scope['career_session'])
    @api.post('/api/drive/commit')
    def drive_commit(body:Commit,request:Request):
        ids=drive.commit(request.scope['career_session'],body.token,body.revision,body.confirmed)
        return {'ids':ids,'state':store.state()}

    @api.get('/api/ai/status')
    def ai_status(): return assistant.status()
    @api.post('/api/ai/config')
    def ai_config(body:AIConfig):
        status=assistant.configure(body.model,body.enabled,body.revision)
        return {'status':status,'state':store.state()}
    @api.post('/api/ai/prepare')
    def ai_prepare(body:AIRequest,request:Request): return assistant.prepare(request.scope['career_session'],body.mode,body.applicationId,body.query,body.baseMaterialId,body.materialIds)
    @api.post('/api/ai/commit')
    def ai_commit(body:AICommit,request:Request):
        keys=assistant.commit(request.scope['career_session'],body.token,body.revision,body.confirmed,body.draft)
        return {'ids':keys,'state':store.state()}

    @api.exception_handler(DomainError)
    async def domain_error(request,error): return JSONResponse({'message':error.message,'errors':error.errors},status_code=error.status)
    @api.exception_handler(RequestValidationError)
    async def invalid_body(request,error): return JSONResponse({'message':'Nieprawidłowe żądanie. Sprawdź pola formularza.','errors':{}},status_code=422)
    @api.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request,error): return JSONResponse({'message':'Nie udało się zapisać: duplikat albo nieprawidłowe powiązanie. Odśwież widok.','errors':{}},status_code=409)
    @api.exception_handler(Exception)
    async def unexpected(request,error): return JSONResponse({'message':'Operacja nie została zakończona. Sprawdź miejsce na dysku i dostęp do katalogu danych.','errors':{}},status_code=500)

    @api.get('/')
    def index(): return FileResponse(STATIC/'index.html')
    @api.get('/health')
    def health(): return {'app':'centrum-kariery','schema_version':2}
    @api.get('/static/{name}')
    def asset(name:str):
        if name not in {'app.js','model.js','styles.css'}: raise DomainError('Plik nie istnieje.',status=404)
        return FileResponse(STATIC/name)
    @api.get('/cv-master-ai-oryginal.txt')
    def instructions():
        with store.lock,store.connection() as db:
            row=db.execute("SELECT value FROM settings WHERE key='cvMasterInstruction'").fetchone()
            if not row: raise DomainError('Instrukcja asystenta nie jest zaimportowana.',status=404)
            return Response(row['value'].encode('utf-8'),media_type='text/plain; charset=utf-8')
    @api.get('/api/session')
    def session(request:Request): return {'csrf':request.scope['career_csrf']}
    @api.get('/api/state')
    def state(): return store.state()
    @api.post('/api/command')
    def command(body:Command):
        key=store.mutate(body.action,body.data,body.key,body.version,body.revision)
        return {'id':key,'state':store.state()}
    @api.post('/api/materials/upload')
    async def upload(request:Request):
        async with request.form(max_files=1,max_fields=10,max_part_size=21*1024*1024) as form:
            file=form.get('file')
            if not file or not hasattr(file,'read'): raise DomainError('Wybierz plik.')
            try:
                revision=int(form.get('revision','-1')); data=json.loads(form.get('data','{}'))
                if not isinstance(data,dict) or set(data)-{'title','kind','version','description','url'}: raise ValueError()
            except (ValueError,TypeError): raise DomainError('Nieprawidłowe dane materiału.')
            content=await file.read(20*1024*1024+1)
            key=store.upload(data,file.filename or '',content,revision)
        return {'id':key,'state':store.state()}
    @api.get('/api/materials/{key}/download')
    def download(key:str):
        check_uuid(key)
        with store.lock,store.connection() as db:
            row=store.record(db,'materials',key)
            if not row['fileKey']: raise DomainError('Materiał nie ma lokalnego pliku.',status=404)
            path=store.files/row['fileKey']
            if not path.is_file() or digest(path.read_bytes())!=row['sha256']: raise DomainError('Plik jest brakujący lub zmieniony. Sprawdź kopię zapasową.')
            return FileResponse(path,media_type='application/octet-stream',filename=row['fileName'],content_disposition_type='attachment')
    @api.get('/api/export/{kind}')
    def export(kind:str):
        if kind=='json': content=json.dumps(store.export_json(),ensure_ascii=False,indent=2).encode('utf-8'); filename='centrum-kariery.json'; media='application/json'
        elif kind=='zip': content=store.archive_bytes(); filename='centrum-kariery-pelny.zip'; media='application/zip'
        elif kind in ('offers','applications'): content=store.export_csv(kind); filename=f'{kind}.csv'; media='text/csv; charset=utf-8'
        elif kind=='profile':
            data=store.state(); lines=['# MASTER PROFILE',data['profile']['name'],data['profile']['goal'],'','## Wpisy ze źródłami']
            for row in data['entries']:
                if not row['archived']: lines.extend([f"### {row['kind']} · {row['status']}",row['content'],f"Źródło: {row['source']}",''])
            content='\n'.join(lines).encode('utf-8'); filename='master-profile.md'; media='text/markdown; charset=utf-8'
        else: raise DomainError('Nieobsługiwany eksport.',status=404)
        return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="{filename}"'})

    def stage(request,plan):
        # Jeden oczekujący import na sesję; podgląd ma 15 minut i jest związany z wersją bazy.
        owner=request.scope['career_session']; current=time.monotonic()
        for key in list(pending):
            if pending[key]['owner']==owner or pending[key]['expires']<current: pending.pop(key)
        if len(pending)>=3: raise DomainError('Za dużo oczekujących importów. Zamknij inne karty i spróbuj później.')
        token=secrets.token_urlsafe(32); revision=store.state()['revision']
        pending[token]={'owner':owner,'expires':current+900,'revision':revision,'plan':plan}
        package=plan.get('package'); counts={key:len(value) for key,value in package['tables'].items()} if package else {'offers':len(plan['rows'])}
        return {'token':token,'revision':revision,'summary':plan['summary'],'counts':counts,'preview':[{key:row.get(key,'') for key in ['title','company','location','url']} for row in plan.get('rows',[])[:10]]}
    @api.post('/api/import/preview')
    async def preview(request:Request,kind:str):
        content=await request.body()
        if not content: raise DomainError('Plik jest pusty.')
        with store.lock: return stage(request,store.preview_import(kind,content))
    @api.post('/api/import/commit')
    def commit(body:Commit,request:Request):
        with store.lock:
            item=pending.get(body.token)
            if not item or item['owner']!=request.scope['career_session'] or item['expires']<time.monotonic(): raise DomainError('Podgląd wygasł lub został już użyty. Przygotuj go ponownie.',status=409)
            if body.confirmed is not True or body.revision!=item['revision']: raise DomainError('Wymagane potwierdzenie aktualnego podglądu.')
            store.commit_import(item['plan'],item['revision']); pending.pop(body.token,None); return {'state':store.state()}
    @api.get('/api/backups')
    def backups(): return {'items':store.backup_list(),'error':store.backup_error}
    @api.post('/api/backups/create')
    def backup(): return {'name':store.make_backup()}
    @api.post('/api/backups/preview')
    async def restore_preview(request:Request):
        try:
            data=await request.json()
            if not isinstance(data,dict) or set(data)!={'name'} or not isinstance(data['name'],str): raise ValueError()
        except (ValueError,TypeError): raise DomainError('Wybierz kopię.')
        with store.lock: return stage(request,store.backup_plan(data['name']))

    return LocalBoundary(api,port)

class LocalBoundary:
    """Ochrona obejmuje wszystkie API, także pobieranie danych i plików."""
    def __init__(self,app,port): self.app=app; self.origin=f'http://127.0.0.1:{port}'; self.host=f'127.0.0.1:{port}'; self.sessions={}
    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        request=Request(scope,receive); headers=request.headers; method=scope['method']; path=scope['path']; session_id=request.cookies.get('career_session',''); current=time.monotonic()
        private=path.startswith('/api/') or path=='/cv-master-ai-oryginal.txt'
        for key in list(self.sessions):
            if self.sessions[key]['expires']<current: self.sessions.pop(key)
        policy={
          'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
          'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Cache-Control':'no-store','Permissions-Policy':'camera=(), microphone=(), geolocation=()'
        }
        async def reject(message,status): await JSONResponse({'message':message,'errors':{}},status_code=status,headers=policy)(scope,receive,send)
        if headers.get('host')!=self.host or len([h for h in scope['headers'] if h[0].lower()==b'host'])!=1: return await reject('Nieprawidłowy Host.',403)
        if headers.get('origin') and headers['origin']!=self.origin: return await reject('Niedozwolone źródło żądania.',403)
        if private and headers.get('sec-fetch-site')=='cross-site': return await reject('Żądanie spoza aplikacji.',403)
        new_session=False
        if method=='GET' and path=='/' and session_id not in self.sessions:
            if len(self.sessions)>=128: return await reject('Limit lokalnych sesji.',429)
            session_id=secrets.token_urlsafe(32); self.sessions[session_id]={'csrf':secrets.token_urlsafe(32),'expires':current+8*3600}; new_session=True
        session=self.sessions.get(session_id)
        if private:
            if not session: return await reject('Sesja wygasła. Odśwież stronę.',401)
            if method not in ('GET','HEAD') and (headers.get('origin')!=self.origin or not secrets.compare_digest(headers.get('x-csrf-token',''),session['csrf'])): return await reject('Nieprawidłowe potwierdzenie sesji. Odśwież stronę.',403)
            scope['career_session']=session_id; scope['career_csrf']=session['csrf']
        if method not in ('GET','HEAD','OPTIONS'):
            limit=MAX_ARCHIVE if path=='/api/import/preview' else 21*1024*1024 if path=='/api/materials/upload' else 1024*1024
            content_type=headers.get('content-type','').split(';')[0]
            expected_type='application/octet-stream' if path=='/api/import/preview' else 'multipart/form-data' if path in ('/api/materials/upload','/api/drive/client') else 'application/json'
            if content_type!=expected_type: return await reject('Nieprawidłowy typ żądania.',415)
            chunks=[]; size=0
            while True:
                chunk=await receive()
                if chunk['type']=='http.disconnect': return
                size+=len(chunk.get('body',b''))
                if size>limit: return await reject('Przekroczono limit rozmiaru żądania.',413)
                chunks.append(chunk.get('body',b''))
                if not chunk.get('more_body'): break
            content=b''.join(chunks); delivered=False
            async def replay():
                nonlocal delivered
                if not delivered: delivered=True; return {'type':'http.request','body':content,'more_body':False}
                return await receive()
            next_receive=replay
        else: next_receive=receive
        async def guarded_send(message):
            if message['type']=='http.response.start':
                message['headers']+= [(key.lower().encode(),value.encode()) for key,value in policy.items()]
                if new_session: message['headers'].append((b'set-cookie',f'career_session={session_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800'.encode()))
            await send(message)
        await self.app(scope,next_receive,guarded_send)
