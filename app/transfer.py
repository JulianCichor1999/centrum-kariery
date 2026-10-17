"""Podgląd importu, eksport relacji i spójne kopie z załącznikami."""
import csv
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from . import validation as v

MAX_RECORDS=20000
MAX_ARCHIVE=300*1024*1024
def digest(data): return hashlib.sha256(data).hexdigest()

class Transfer:
    def export_json(self):
        from .storage import TABLES
        with self.lock,self.connection() as db: return {'schema_version':1,'exported_at':v.now(),'tables':{t:self.rows(db,t) for t in TABLES}}

    @staticmethod
    def csv_safe(value):
        result=str(value)
        return "'"+result if result.lstrip().startswith(('=','+','-','@')) or result.startswith(('\t','\r','\n')) else result

    def export_csv(self,table):
        state=self.state(); out=io.StringIO(newline=''); writer=csv.writer(out,delimiter=';')
        if table=='offers':
            columns=['title','company','location','direction','mode','contract','url','description','deadline']; writer.writerow(columns); companies={row['id']:row['name'] for row in state['companies']}
            for row in state['offers']:
                if not row['archived']: writer.writerow([self.csv_safe(companies[row['companyId']] if key=='company' else row[key]) for key in columns])
        elif table=='applications':
            columns=['id','offerId','status','sentAt','archived']; writer.writerow(columns)
            for row in state['applications']: writer.writerow([self.csv_safe(row[key]) for key in columns])
        else: raise v.DomainError('Nieprawidłowy typ eksportu.')
        return ('\ufeff'+out.getvalue()).encode('utf-8')

    def validate_snapshot(self,package):
        from .storage import TABLES,SCHEMA
        if not isinstance(package,dict) or package.get('schema_version')!=1 or not isinstance(package.get('tables'),dict) or set(package['tables'])!=set(TABLES): raise v.DomainError('Nieobsługiwany format pełnego JSON.')
        tables=package['tables']
        if any(not isinstance(rows,list) for rows in tables.values()) or sum(map(len,tables.values()))>MAX_RECORDS: raise v.DomainError('Nieprawidłowy zestaw rekordów (limit 20 000).')
        temp=sqlite3.connect(':memory:'); temp.row_factory=sqlite3.Row; temp.execute('PRAGMA foreign_keys=ON'); temp.executescript(SCHEMA)
        try:
            for table,rows in tables.items():
                columns={row['name']:row for row in temp.execute(f'PRAGMA table_info({table})')}
                for row in rows:
                    if not isinstance(row,dict) or set(row)!=set(columns): raise v.DomainError(f'Nieprawidłowe pola: {table}.')
                    for key,value in row.items():
                        if value is None and not columns[key]['notnull'] and not columns[key]['pk']: continue
                        expected=int if columns[key]['type']=='INTEGER' else str
                        if type(value) is not expected or isinstance(value,str) and (len(value)>250000 or '\x00' in value): raise v.DomainError(f'Nieprawidłowy typ pola: {table}.{key}.')
                    if 'id' in row: v.check_uuid(row['id'])
                    if 'rowVersion' in row and row['rowVersion']<1: raise v.DomainError('Nieprawidłowa wersja rekordu.')
                    for key in ['createdAt','updatedAt','at']:
                        if key in row:
                            try:
                                if datetime.fromisoformat(row[key]).tzinfo is None: raise ValueError()
                            except (ValueError,TypeError): raise v.DomainError('Nieprawidłowy znacznik czasu.')
            if len(tables['profiles'])!=1: raise v.DomainError('Wymagany jeden profil.')
            for row in tables['profiles']:
                try: v.profile_values({**row,'preferences':json.loads(row['preferences'])})
                except (ValueError,TypeError): raise v.DomainError('Nieprawidłowe preferencje.')
            for row in tables['profile_entries']: v.entry_values(row)
            for row in tables['companies']:
                if row['nameKey']!=v.fold(v.text(row,'name',120)): raise v.DomainError('Nieprawidłowy klucz firmy.')
            for row in tables['offers']:
                if v.offer_values(row)['canonical']!=row['canonical']: raise v.DomainError('Nieprawidłowy adres źródła.')
            for row in tables['applications']:
                v.choice(row,'status',v.STATUSES)
                try:
                    if not isinstance(json.loads(row['snapshot']),dict): raise ValueError()
                    if row['sentAt'] and datetime.fromisoformat(row['sentAt']).tzinfo is None: raise ValueError()
                except (ValueError,TypeError): raise v.DomainError('Nieprawidłowa historia wysłania.')
            for row in tables['tasks']: v.text(row,'title'); v.day(row['due']); v.choice(row,'done',[0,1])
            for row in tables['events']:
                v.text(row,'title'); v.text(row,'place',500,False)
                if v.warsaw(row['end'],'end')<=v.warsaw(row['start'],'start'): raise v.DomainError('Nieprawidłowy termin.')
            for row in tables['notes']: v.text(row,'text',5000)
            for row in tables['materials']:
                v.material_values(row)
                if row['fileKey']:
                    maximum=(100 if row['fileKey'].endswith('.bin') else 20)*1024*1024
                    if not re.fullmatch(r'[0-9a-f-]{36}\.(pdf|docx|txt|md|json|png|jpe?g|bin)',row['fileKey']) or not re.fullmatch(r'[0-9a-f]{64}',row['sha256']) or not 0<row['size']<=maximum or len(row['fileName'])>180 or any(c in row['fileName'] for c in ('\r','\n','/','\\')): raise v.DomainError('Nieprawidłowy załącznik.')
                    v.check_uuid(row['fileKey'].split('.')[0])
                elif row['sha256'] or row['size'] or row['fileName']: raise v.DomainError('Niekompletne dane załącznika.')
            if {row['key'] for row in tables['settings']}-{'revision','savedSearches','cvMasterInstruction','aiConfig'}: raise v.DomainError('Nieobsługiwane ustawienia.')
            revisions=[row['value'] for row in tables['settings'] if row['key']=='revision']
            if len(revisions)!=1 or not revisions[0].isdigit() or len(revisions[0])>18: raise v.DomainError('Nieprawidłowa rewizja bazy.')
            for row in tables['settings']:
                if row['key']=='aiConfig':
                    try: v.ai_config(json.loads(row['value']))
                    except (ValueError,TypeError): raise v.DomainError('Nieprawidłowa konfiguracja AI w kopii.')
                if row['key']=='cvMasterInstruction' and len(row['value'])>200000: raise v.DomainError('Instrukcja asystenta przekracza limit.')
                if row['key']=='savedSearches':
                    try: v.searches(json.loads(row['value']))
                    except (ValueError,TypeError): raise v.DomainError('Nieprawidłowe zapisane wyszukiwania.')
            for table in TABLES:
                for row in tables[table]: temp.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",tuple(row.values()))
            if temp.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or temp.execute('PRAGMA foreign_key_check').fetchall(): raise v.DomainError('Zerwane relacje.')
        except sqlite3.IntegrityError: raise v.DomainError('Duplikaty lub zerwane relacje w eksporcie.')
        finally: temp.close()
        return package

    def preview_import(self,kind,content):
        if kind=='csv':
            try:
                decoded=content.decode('utf-8-sig'); reader=csv.DictReader(io.StringIO(decoded),delimiter=';' if ';' in decoded.splitlines()[0] else ',')
                fields={'title','company','location','direction','mode','contract','url','description','deadline'}
                if set(reader.fieldnames or [])!=fields: raise ValueError()
                rows=list(reader)
                if len(rows)>2000: raise ValueError()
                planned=[]; skipped=0
                with self.connection() as db:
                    existing={row['canonical'] for row in db.execute('SELECT canonical FROM offers WHERE canonical IS NOT NULL')}
                    identities={(v.fold(row['name']),v.fold(row['title']),v.fold(row['location'])) for row in db.execute('SELECT c.name,o.title,o.location FROM offers o JOIN companies c ON c.id=o.companyId')}
                seen=set()
                for row in rows:
                    row={k:(value[1:] if isinstance(value,str) and value.startswith("'") and value[1:].lstrip().startswith(('=','+','-','@')) else value) for k,value in row.items()}
                    values=v.offer_values(row); name=v.text(row,'company',120); identity=values['canonical'] or (v.fold(name),v.fold(values['title']),v.fold(values['location']))
                    if identity in seen or values['canonical'] and identity in existing or not values['canonical'] and identity in identities: skipped+=1
                    else: seen.add(identity); planned.append(row)
                return {'kind':kind,'rows':planned,'summary':f'CSV: nowych ofert {len(planned)}, pominiętych duplikatów {skipped}. Podobne nazwy z różnymi linkami pozostaną osobnymi ogłoszeniami.','skipped':skipped}
            except (UnicodeError,ValueError,IndexError,csv.Error): raise v.DomainError('Nieprawidłowy CSV. Użyj szablonu eksportu UTF-8 z nagłówkami.')
        if kind=='json':
            try: package=self.validate_snapshot(json.loads(content))
            except (ValueError,UnicodeError,RecursionError): raise v.DomainError('Nieprawidłowy JSON.')
            for row in package['tables']['materials']:
                if row['fileKey'] and (not (self.files/row['fileKey']).is_file() or digest((self.files/row['fileKey']).read_bytes())!=row['sha256']): raise v.DomainError('JSON wskazuje brakujące pliki. Użyj pełnego pakietu ZIP do przenoszenia załączników.')
            return {'kind':kind,'package':package,'summary':'Pełny JSON zastąpi obecne rekordy, zachowując relacje. Przed zapisem powstanie kopia bieżącego stanu.'}
        if kind=='zip':
            package,files=self.read_archive(content); return {'kind':kind,'package':package,'files':files,'summary':'Pakiet zastąpi obecne rekordy i przywróci wskazane pliki. Przed zapisem powstanie kopia bieżącego stanu.'}
        raise v.DomainError('Nieobsługiwany format importu.')

    def commit_import(self,plan,expected):
        with self.lock:
            with self.connection() as db:
                if expected!=self.revision(db): raise v.DomainError('Baza zmieniła się po podglądzie. Przygotuj import ponownie.',status=409)
            self.make_backup('przed-przywroceniem' if plan.get('restore') else 'przed-importem')
            if plan['kind']=='csv':
                with self.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    for row in plan['rows']: self.command(db,'saveOffer',{**row,'allowSimilar':True},None,None)
                    self.audit(db,'import','Zaimportowano CSV ofert.'); db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"); db.commit()
            else: self.replace_snapshot(plan['package'],plan.get('files',{}),expected)
            self.daily_backup()

    def replace_snapshot(self,package,files,revision):
        from .storage import TABLES
        self.validate_snapshot(package); written=[]
        try:
            for name,content in files.items():
                target=self.files/name
                if not target.exists(): target.write_bytes(content); written.append(target)
                elif digest(target.read_bytes())!=digest(content): raise v.DomainError('Konflikt identyfikatora załącznika. Nie zmieniono danych.')
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                for table in reversed(TABLES): db.execute(f'DELETE FROM {table}')
                for table in TABLES:
                    for row in package['tables'][table]: db.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",tuple(row.values()))
                db.execute("UPDATE settings SET value=? WHERE key='revision'",(str(revision+1),)); self.audit(db,'restore','Przywrócono pełny zestaw danych z relacjami.'); db.commit()
        except Exception:
            for target in written: target.unlink(missing_ok=True)
            raise

    def archive_bytes(self):
        from .storage import TABLES
        with self.lock,self.connection() as source:
            snapshot=sqlite3.connect(':memory:'); snapshot.row_factory=sqlite3.Row; source.backup(snapshot)
            try: package={'schema_version':1,'exported_at':v.now(),'tables':{t:self.rows(snapshot,t) for t in TABLES}}
            finally: snapshot.close()
            entries={'data.json':json.dumps(package,ensure_ascii=False).encode('utf-8')}
            for row in package['tables']['materials']:
                if row['fileKey']:
                    content=(self.files/row['fileKey']).read_bytes()
                    if digest(content)!=row['sha256']: raise v.DomainError('Załącznik zmienił się poza aplikacją. Kopia została zatrzymana.')
                    entries['files/'+row['fileKey']]=content
            if sum(map(len,entries.values()))>MAX_ARCHIVE: raise v.DomainError('Pakiet przekracza limit 150 MB.')
            manifest={'schema_version':1,'created_at':v.now(),'revision':self.revision(source),'files':{name:digest(value) for name,value in entries.items()}}
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
                for name,value in entries.items(): archive.writestr(name,value)
            return out.getvalue()

    def read_archive(self,content):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names=archive.namelist()
                if len(names)>MAX_RECORDS or len(set(names))!=len(names) or sum(item.file_size for item in archive.infolist())>MAX_ARCHIVE or any(name not in ('data.json','manifest.json') and not re.fullmatch(r'files/[0-9a-f-]{36}\.(pdf|docx|txt|md|json|png|jpe?g|bin)',name) for name in names): raise ValueError()
                manifest=json.loads(archive.read('manifest.json'))
                if not isinstance(manifest,dict) or manifest.get('schema_version')!=1 or not isinstance(manifest.get('files'),dict) or set(manifest['files'])!=set(names)-{'manifest.json'}: raise ValueError()
                values={name:archive.read(name) for name in manifest['files']}
                if any(digest(value)!=manifest['files'][name] for name,value in values.items()): raise ValueError()
                package=self.validate_snapshot(json.loads(values.pop('data.json')))
                material_rows=[row for row in package['tables']['materials'] if row['fileKey']]
                expected={'files/'+row['fileKey'] for row in material_rows}
                if set(values)!=expected or any(digest(values['files/'+row['fileKey']])!=row['sha256'] or len(values['files/'+row['fileKey']])!=row['size'] for row in material_rows): raise ValueError()
                return package,{name.removeprefix('files/'):value for name,value in values.items()}
        except (ValueError,TypeError,KeyError,UnicodeError,zipfile.BadZipFile,RuntimeError,RecursionError): raise v.DomainError('Pakiet jest niekompletny, uszkodzony lub ma niedozwolone ścieżki. Nie zmieniono danych.')

    def make_backup(self,label='reczna',filename=None):
        with self.lock:
            filename=filename or datetime.now(v.WARSAW).strftime('%Y%m%d-%H%M%S-')+v.uid()[:8]+'-'+label+'.zip'
            target=self.backups/filename; temp=target.with_suffix('.tmp'); temp.write_bytes(self.archive_bytes()); temp.replace(target); self.backup_error=''; return filename

    def daily_backup(self):
        try:
            with self.lock:
                current=datetime.now(v.WARSAW); self.make_backup(filename='daily-'+current.strftime('%Y-%m-%d')+'.zip'); self.make_backup(filename='weekly-'+current.strftime('%G-%V')+'.zip')
                for prefix,keep in [('daily-',7),('weekly-',4)]:
                    for file in sorted(self.backups.glob(prefix+'*.zip'),reverse=True)[keep:]: file.unlink()
        except (OSError,v.DomainError): self.backup_error='Ostatnia automatyczna kopia nie powiodła się. Dane zapisano; sprawdź wolne miejsce i utwórz kopię ręcznie.'

    def backup_list(self): return [{'name':p.name,'size':p.stat().st_size,'at':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()} for p in sorted(self.backups.glob('*.zip'),reverse=True)]
    def backup_plan(self,name):
        if not re.fullmatch(r'[a-zA-Z0-9-]+\.zip',name) or not (self.backups/name).is_file(): raise v.DomainError('Kopia nie istnieje.',status=404)
        package,files=self.read_archive((self.backups/name).read_bytes()); return {'kind':'zip','package':package,'files':files,'restore':True,'summary':'Przywrócenie zastąpi obecne rekordy. Przed operacją powstanie kopia bieżącego stanu.'}
