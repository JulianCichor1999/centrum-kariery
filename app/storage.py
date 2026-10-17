"""Jedna baza SQLite; zapisy i walidacja w transakcjach."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import io
import json
import sqlite3
import threading
import zipfile
from . import validation as v
from .transfer import Transfer

TABLES=['profiles','profile_entries','companies','offers','applications','tasks','events','notes','materials','application_materials','audit_events','settings']
SCHEMA=Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
ARCHIVABLE=['offers','applications','tasks','events','notes','profile_entries']
FIELDS={
 'saveOffer':{'title','company','location','description','url','direction','mode','contract','deadline','allowSimilar'},
 'createApplication':{'offerId'},'setStatus':{'status','confirmed'},'saveTask':{'title','due','applicationId'},'toggleTask':set(),
 'saveEvent':{'title','start','end','place','applicationId'},'addNote':{'text','applicationId'},
 'addMaterial':{'title','kind','version','description','url'},'pinMaterial':{'applicationId','materialId'},
 'saveProfile':{'name','email','goal','preferences'},'saveEntry':{'kind','content','status','source','confirmed'},
 'archive':{'table','confirmed'},'unarchive':{'table','confirmed'},'saveSearches':{'items'}
}

class Store(Transfer):
    def __init__(self,directory):
        self.directory=Path(directory).resolve(); self.directory.mkdir(parents=True,exist_ok=True)
        self.files=self.directory/'files'; self.files.mkdir(exist_ok=True)
        self.backups=self.directory/'backups'; self.backups.mkdir(exist_ok=True)
        self.path=self.directory/'career.sqlite'; self.lock=threading.RLock(); self.backup_error=''
        with self.connection() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version==0:
                db.executescript(SCHEMA)
                db.execute('INSERT INTO settings VALUES (?,?)',('revision','0'))
                self.insert(db,'profiles',{'name':'','email':'','goal':'','preferences':json.dumps({'directions':[],'locations':[],'contracts':[],'remote':''},ensure_ascii=False)})
                db.commit()
            elif version==1:
                self.make_backup('przed-schema-2')
                # Rebuild just this constraint, preserving IDs and all references.
                db.execute('PRAGMA foreign_keys=OFF'); db.execute('BEGIN IMMEDIATE')
                try:
                    ddl=next(line for line in SCHEMA.splitlines() if line.startswith('CREATE TABLE materials ('))
                    db.execute(ddl.replace('CREATE TABLE materials (','CREATE TABLE materials_upgrade (',1))
                    db.execute('INSERT INTO materials_upgrade SELECT * FROM materials')
                    db.execute('DROP TABLE materials'); db.execute('ALTER TABLE materials_upgrade RENAME TO materials')
                    if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise v.DomainError('Nie udało się zachować relacji podczas aktualizacji bazy.')
                    db.execute('PRAGMA user_version=2'); db.commit()
                except Exception: db.rollback(); raise
                finally: db.execute('PRAGMA foreign_keys=ON')
            elif version!=2: raise v.DomainError('Nieobsługiwana wersja bazy. Nie zmieniono danych.')
            original=Path(__file__).resolve().parents[1]/'docs/materialy/cv-master-ai-oryginal.txt'
            if not db.execute("SELECT 1 FROM settings WHERE key='cvMasterInstruction'").fetchone() and original.is_file():
                instruction=original.read_bytes().decode('utf-8')
                if len(instruction)>200000 or '\x00' in instruction: raise v.DomainError('Oryginalna instrukcja jest zbyt duża lub nieprawidłowa.')
                db.execute('INSERT INTO settings VALUES (?,?)',('cvMasterInstruction',instruction))
                db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"); db.commit()
        self.daily_backup()

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=10); db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA trusted_schema=OFF'); db.execute('PRAGMA busy_timeout=10000')
        try: yield db
        finally: db.close()

    @staticmethod
    def rows(db,table): return [dict(row) for row in db.execute(f'SELECT * FROM {table}')]
    @staticmethod
    def revision(db): return int(db.execute("SELECT value FROM settings WHERE key='revision'").fetchone()[0])
    def record(self,db,table,key):
        if table not in TABLES: raise v.DomainError('Nieprawidłowy typ rekordu.')
        v.check_uuid(key); row=db.execute(f'SELECT * FROM {table} WHERE id=?',(key,)).fetchone()
        if not row: raise v.DomainError('Rekord nie istnieje. Odśwież widok.',status=404)
        return dict(row)
    def app_ref(self,db,key):
        if key: self.record(db,'applications',key)
        return key or None
    @staticmethod
    def audit(db,action,message,application=None): db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?)',(v.uid(),application,v.now(),action,message))
    @staticmethod
    def insert(db,table,values):
        values={**values,'id':v.uid(),'rowVersion':1,'createdAt':v.now(),'updatedAt':v.now()}
        db.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",tuple(values.values())); return values['id']
    def update(self,db,table,key,values,version):
        row=self.record(db,table,key)
        if version!=row['rowVersion']: raise v.DomainError('Rekord zmienił się w innej karcie. Odśwież widok i sprawdź dane przed zapisem.',status=409)
        values={**values,'rowVersion':row['rowVersion']+1,'updatedAt':v.now()}
        db.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in values)} WHERE id=?",(*values.values(),key))

    def state(self):
        with self.lock,self.connection() as db:
            result={key:self.rows(db,key) for key in ['companies','offers','applications','tasks','events','notes','materials']}
            histories=self.rows(db,'audit_events')
            for row in result['applications']: row['history']=[item for item in histories if item['applicationId']==row['id']]
            for row in result['tasks']: row['done']=bool(row['done']); row['applicationId']=row['applicationId'] or ''
            for row in result['events']: row['applicationId']=row['applicationId'] or ''
            for row in result['notes']: row['at']=row['createdAt']
            result.update(links=self.rows(db,'application_materials'),profile=self.rows(db,'profiles')[0],entries=self.rows(db,'profile_entries'),revision=self.revision(db),backupError=self.backup_error)
            result['profile']['preferences']=json.loads(result['profile']['preferences'])
            row=db.execute("SELECT value FROM settings WHERE key='savedSearches'").fetchone()
            result['savedSearches']=json.loads(row['value']) if row else []
            result['archive']=[{'table':table,'id':item['id'],'title':item.get('title') or item.get('text') or item.get('content') or item.get('status'),'rowVersion':item['rowVersion']} for table in ARCHIVABLE for item in self.rows(db,table) if item['archived']]
            return result

    def mutate(self,action,data,key=None,version=None,expected=None,source=None):
        with self.lock:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                if expected!=self.revision(db): raise v.DomainError('Baza zmieniła się w innej karcie. Odśwież widok i sprawdź dane przed ponowieniem.',status=409)
                result=self.command(db,action,data,key,version)
                if source is not None:
                    application=db.execute('SELECT id FROM applications WHERE offerId=?',(key,)).fetchone()
                    self.audit(db,'offerTextImport','Odczyt treści oferty. Źródło: '+source['sourceUrl']+'; czas: '+source['fetchedAt']+'; SHA256: '+source['sha256'],application['id'] if application else None)
                db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"); db.commit()
            self.daily_backup(); return result

    def command(self,db,action,data,key,version):
        if action not in FIELDS or set(data)-FIELDS[action]: raise v.DomainError('Nieobsługiwana operacja lub dodatkowe pola.')
        if action=='saveOffer':
            values=v.offer_values(data); name=v.text(data,'company',120)
            if values['canonical'] and db.execute('SELECT 1 FROM offers WHERE canonical=? AND id!=?',(values['canonical'],key or '')).fetchone(): raise v.DomainError('Ta oferta już istnieje.',{'url':'Adres jest już zapisany, również gdy oferta jest w archiwum.'})
            firm=db.execute('SELECT id FROM companies WHERE nameKey=?',(v.fold(name),)).fetchone()
            values['companyId']=firm['id'] if firm else self.insert(db,'companies',{'name':name,'nameKey':v.fold(name)})
            similar=db.execute('SELECT title FROM offers WHERE companyId=? AND id!=?',(values['companyId'],key or '')).fetchall()
            if any(v.fold(row['title'])==v.fold(values['title']) for row in similar) and data.get('allowSimilar') is not True: raise v.DomainError('Podobne stanowisko w tej firmie jest już zapisane. Sprawdź, czy to odrębne ogłoszenie.',{'allowSimilar':'Potwierdź odrębne ogłoszenie. Nie scalamy go automatycznie.'},409)
            if key:
                self.update(db,'offers',key,values,version)
                for row in db.execute('SELECT id FROM applications WHERE offerId=?',(key,)): self.audit(db,action,'Zmieniono dane powiązanej oferty.',row['id'])
            else: key=self.insert(db,'offers',values)
        elif action=='createApplication':
            offer=self.record(db,'offers',data.get('offerId'))
            if offer['archived']: raise v.DomainError('Przywróć ofertę z archiwum.')
            existing=db.execute('SELECT id,archived FROM applications WHERE offerId=?',(offer['id'],)).fetchone()
            if existing:
                if existing['archived']: raise v.DomainError('Aplikacja już istnieje w archiwum. Przywróć ją zamiast powielać.')
                return existing['id']
            key=self.insert(db,'applications',{'offerId':offer['id'],'status':v.STATUSES[0],'sentAt':'','snapshot':'{}'}); self.audit(db,action,'Utworzono aplikację.',key)
        elif action=='setStatus':
            row=self.record(db,'applications',key); status=v.choice(data,'status',v.STATUSES); values={'status':status}
            if status=='Wysłana':
                if data.get('confirmed') is not True: raise v.DomainError('Potwierdź ręczne oznaczenie wysłania. System niczego nie wysyła.')
                if not row['sentAt']: values.update(sentAt=v.now(),snapshot=json.dumps({'offer':self.record(db,'offers',row['offerId']),'profile':self.rows(db,'profiles')[0],'entries':[x for x in self.rows(db,'profile_entries') if not x['archived']],'materialIds':[x['materialId'] for x in db.execute('SELECT materialId FROM application_materials WHERE applicationId=?',(key,))]},ensure_ascii=False))
            self.update(db,'applications',key,values,version); self.audit(db,action,f"Status: {row['status']} → {status}."+(' Ręczne potwierdzenie, bez wysyłki.' if status=='Wysłana' else ''),key)
        elif action in ('saveTask','saveEvent'):
            table='tasks' if action=='saveTask' else 'events'; values={'title':v.text(data,'title'),'applicationId':self.app_ref(db,data.get('applicationId'))}
            if table=='tasks': values['due']=v.day(data.get('due'))
            else:
                if v.warsaw(data.get('end'),'end')<=v.warsaw(data.get('start'),'start'): raise v.DomainError('Koniec musi być późniejszy od początku.',{'end':'Popraw godzinę końca.'})
                values.update(start=data['start'],end=data['end'],place=v.text(data,'place',500,False))
            old_app=self.record(db,table,key)['applicationId'] if key else None
            if key: self.update(db,table,key,values,version)
            else: key=self.insert(db,table,values)
            self.audit(db,action,f"Zapisano: {values['title']}.",values['applicationId'])
            if old_app and old_app!=values['applicationId']: self.audit(db,action,'Zmieniono powiązanie zadania lub terminu.',old_app)
        elif action=='toggleTask':
            row=self.record(db,'tasks',key); done=0 if row['done'] else 1; self.update(db,'tasks',key,{'done':done},version); self.audit(db,action,('Ukończono' if done else 'Wznowiono')+f" zadanie: {row['title']}.",row['applicationId'])
        elif action=='addNote':
            application=self.app_ref(db,data.get('applicationId'))
            if not application: raise v.DomainError('Wybierz aplikację.')
            key=self.insert(db,'notes',{'applicationId':application,'text':v.text(data,'text',5000)}); self.audit(db,action,'Dodano notatkę.',application)
        elif action=='addMaterial': key=self.material(db,data)
        elif action=='pinMaterial':
            application=self.app_ref(db,data.get('applicationId')); material=self.record(db,'materials',data.get('materialId'))
            if not application: raise v.DomainError('Wybierz aplikację.')
            if not db.execute('SELECT 1 FROM application_materials WHERE applicationId=? AND materialId=?',(application,material['id'])).fetchone():
                db.execute('INSERT INTO application_materials VALUES (?,?)',(application,material['id'])); self.audit(db,action,f"Przypięto: {material['title']} · wersja {material['version']}.",application)
            key=material['id']
        elif action=='saveProfile':
            row=self.rows(db,'profiles')[0]; values=v.profile_values(data); values['preferences']=json.dumps(values['preferences'],ensure_ascii=False); key=row['id']; self.update(db,'profiles',key,values,version); self.audit(db,action,'Zapisano profil i preferencje.')
        elif action=='saveEntry':
            values=v.entry_values(data); values['profileId']=self.rows(db,'profiles')[0]['id']
            if key:
                if data.get('confirmed') is not True: raise v.DomainError('Potwierdź zmianę informacji profilu.')
                self.update(db,'profile_entries',key,values,version)
            else: key=self.insert(db,'profile_entries',values)
            self.audit(db,action,'Zapisano wpis profilu wraz ze źródłem i stanem.')
        elif action in ('archive','unarchive'):
            if data.get('confirmed') is not True: raise v.DomainError('Ta operacja wymaga potwierdzenia.')
            table=v.choice(data,'table',ARCHIVABLE); row=self.record(db,table,key); self.update(db,table,key,{'archived':int(action=='archive')},version); self.audit(db,action,('Zarchiwizowano' if action=='archive' else 'Przywrócono')+' rekord.',row.get('applicationId') or (key if table=='applications' else None))
        elif action=='saveSearches':
            items=v.searches(data.get('items')); db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('savedSearches',json.dumps(items,ensure_ascii=False))); self.audit(db,action,'Zapisano odnośniki do wyszukiwań.')
        return key

    def material(self,db,data,file_info=None):
        values=v.material_values(data)
        if any(v.fold(row['title'])==v.fold(values['title']) and v.fold(row['version'])==v.fold(values['version']) for row in db.execute('SELECT title,version FROM materials')): raise v.DomainError('Ta nazwa i wersja już istnieją.',{'version':'Wpisz nowy numer wersji.'})
        values.update(file_info or {'fileKey':'','fileName':'','sha256':'','size':0}); key=self.insert(db,'materials',values); self.audit(db,'addMaterial','Dodano niezmienną wersję materiału.'); return key

    def commit_ai(self,preview,context,token):
        """Confirmed proposal, files and links saved atomically; no direct model access."""
        created=[]
        with self.lock:
            try:
                with self.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if preview['revision']!=self.revision(db): raise v.DomainError('Dane zmieniły się od generowania. Przygotuj nowy podgląd AI.',status=409)
                    application=preview['applicationId'] or None
                    if application and self.record(db,'applications',application)['archived']: raise v.DomainError('Aplikacja jest zarchiwizowana.')
                    keys=[]
                    if preview['mode']=='command':
                        if not preview['operations']: raise v.DomainError('Brak operacji do zatwierdzenia.')
                        for operation in preview['operations']:
                            if operation['action'] not in ('saveTask','addNote'): raise v.DomainError('AI nie ma uprawnień do tej operacji.')
                            keys.append(self.command(db,operation['action'],operation['data'],None,None))
                    else:
                        # Source IDs/context are an immutable historical snapshot, not a new profile.
                        report=json.dumps({'preview':preview,'context':context},ensure_ascii=False,indent=2).encode('utf-8')
                        files=[('Raport AI','Inny','.json',report)]
                        if preview['draft']:
                            from .documents import pdf_bytes,docx_bytes,cv_pdf_bytes,cv_docx_bytes
                            title=('CV do oferty' if preview.get('fullCV') else 'Szkic CV AI') if preview['mode']=='cv' else 'Szkic wiadomości AI'; kind='CV' if preview['mode']=='cv' else 'Wiadomość'
                            files.append((title,kind,'.md',preview['draft'].encode('utf-8')))
                            if preview.get('fullCV'):
                                files.append((title,kind,'.pdf',cv_pdf_bytes(preview['draft'])))
                                files.append((title,kind,'.docx',cv_docx_bytes(preview['draft'])))
                            else:
                                files.append((title,kind,'.pdf',pdf_bytes(preview['draft'],'Profil zawodowy' if preview['mode']=='cv' else 'Wiadomość rekrutacyjna')))
                                files.append((title,kind,'.docx',docx_bytes(preview['draft'],'Profil zawodowy' if preview['mode']=='cv' else 'Wiadomość rekrutacyjna')))
                        for title,kind,extension,content in files:
                            file_key=v.uid()+extension; path=self.files/file_key; created.append(path); path.write_bytes(content)
                            data={'title':title+' · '+context['offer']['title'][:100]+(' · '+extension[1:].upper() if extension in ('.pdf','.docx') else ''),'kind':kind,'version':token[:24],'description':'Szkic zaakceptowany do biblioteki. Model: '+preview['model']+'. Research nie wykonano. Źródła i kontekst w raporcie AI.','url':''}
                            key=self.material(db,data,{'fileKey':file_key,'fileName':title.replace(' ','-').lower()+extension,'sha256':hashlib.sha256(content).hexdigest(),'size':len(content)})
                            if application: self.command(db,'pinMaterial',{'applicationId':application,'materialId':key},None,None)
                            keys.append(key)
                    self.audit(db,'aiCommit','Zatwierdzono podgląd lokalnego AI ('+preview['model']+'). Bez wysyłki.',application)
                    db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"); db.commit()
            except Exception:
                for path in created: path.unlink(missing_ok=True)
                raise
            self.daily_backup()
            return keys

    @staticmethod
    def validate_upload(filename,content):
        name=Path(filename.replace('\\','/')).name; extension=Path(name).suffix.lower()
        maximum=(100 if extension=='.bin' else 20)*1024*1024
        if extension not in v.ALLOWED_FILES or not content or len(content)>maximum or len(name)>180 or any(c in name for c in ('\r','\n','\x00')): raise v.DomainError('Nieprawidłowy typ, nazwa lub rozmiar pliku. Dokumenty: do 20 MB; binarne załączniki Portfolio: do 100 MB.')
        if extension=='.pdf' and not content.startswith(b'%PDF-'): raise v.DomainError('Plik nie ma nagłówka PDF.')
        if extension=='.docx':
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as doc:
                    if 'word/document.xml' not in doc.namelist() or any('vbaProject' in n for n in doc.namelist()): raise ValueError()
            except (ValueError,zipfile.BadZipFile): raise v.DomainError('Nieprawidłowy DOCX lub plik z makrami.')
        return name,extension

    def upload(self,data,filename,content,expected):
        return self.import_materials([{'data':data,'name':filename,'content':content}],expected,backup=False)[0]

    def import_materials(self,rows,expected,backup=True):
        """All selected files and records commit together or are cleaned up together."""
        created=[]
        with self.lock:
            with self.connection() as db:
                if expected!=self.revision(db): raise v.DomainError('Baza zmieniła się. Odśwież widok i przygotuj nowy podgląd.',status=409)
            prepared=[(row,*self.validate_upload(row['name'],row['content'])) for row in rows]
            if backup: self.make_backup()
            try:
                with self.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if expected!=self.revision(db): raise v.DomainError('Baza zmieniła się. Odśwież widok.',status=409)
                    keys=[]
                    for row,name,extension in prepared:
                        download_name=row.get('downloadName',name)
                        if not isinstance(download_name,str) or not download_name or len(download_name)>180 or any(c in download_name for c in ('\r','\n','\x00','/','\\')): raise v.DomainError('Nieprawidłowa nazwa pobieranego pliku.')
                        content=row['content']; file_key=v.uid()+extension; target=self.files/file_key
                        created.append(target); target.write_bytes(content)
                        keys.append(self.material(db,row['data'],{'fileKey':file_key,'fileName':download_name,'sha256':hashlib.sha256(content).hexdigest(),'size':len(content)}))
                    if backup: self.audit(db,'driveImport','Zaimportowano wybrane pliki z Google Drive: '+str(len(keys))+'.')
                    db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"); db.commit()
            except Exception:
                for target in created: target.unlink(missing_ok=True)
                raise
            self.daily_backup(); return keys
