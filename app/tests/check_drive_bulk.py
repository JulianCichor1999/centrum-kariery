"""Complete portfolio import: real store/vault/API boundary, simulated Google content."""
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.drive import Drive,API,TOKEN,SCOPE,FOLDER,DOC,MAX_BULK_FILE
from app.storage import Store,SCHEMA
from app.validation import DomainError
from app.materials import MaterialReader
F='bulk_root_demo_123';S='bulk_sub_demo_123';N='bulk_nested_demo_123'
checks=[]
def check(name,ok=True): assert ok,name;checks.append(name)
def reject(fn):
    try: fn()
    except DomainError: return True
    raise AssertionError('Expected rejection')
def docx():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive: archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DEMO: projekt automatyzacji n8n.</w:t></w:r></w:p></w:body></w:document>')
    return stream.getvalue()
def meta(key,name,mime,parent=F,size=100): return {'id':key,'name':name,'mimeType':mime,'parents':[parent],'size':str(size),'version':'1','modifiedTime':'2026-10-13T15:00:00Z','webViewLink':'https://drive.google.com/file/d/'+key+'/view','capabilities':{'canDownload':True},'trashed':False}
class Google:
    def __init__(self):
        self.calls=[];self.partial=False;self.fail_folder=False
        self.rows={F:meta(F,'Portfolio DEMO',FOLDER,'not_in_scope_123'),S:meta(S,'Projekty DEMO',FOLDER),N:meta(N,'n8n DEMO',FOLDER,S)}
        self.content={}
        formats=[('document_demo_123','Dokument DEMO',DOC,N,docx()),('sheet_demo_123','Arkusz DEMO','application/vnd.google-apps.spreadsheet',S,b'XLSX DEMO'),('audio_demo_123','voice-demo.mp3','audio/mpeg',S,b'ID3 DEMO'),('image_demo_123','image-demo.png','image/png',F,b'PNG DEMO'),('gimp_demo_123','design-demo.xcf','image/x-xcf',N,b'XCF DEMO'),('text_demo_123','notatki-demo.txt','text/plain',F,b'Text DEMO'),('word_demo_123','EN.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',S,docx()),('word_second_demo_123','EN.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',N,docx())]
        for key,name,mime,parent,content in formats:self.rows[key]=meta(key,name,mime,parent,len(content));self.content[key]=content
        self.rows['large_demo_123']=meta('large_demo_123','large-demo.mp4','video/mp4',N,MAX_BULK_FILE+1)
        self.rows['outside_demo_123']=meta('outside_demo_123','outside.txt','text/plain','other_folder_123')
    def json(self,url,params=None,token=None,form=None,**kwargs):
        self.calls.append((url,params,token,form))
        if url==TOKEN:return {'access_token':'DEMO','refresh_token':'REFRESH-DEMO','token_type':'Bearer','expires_in':3600,'scope':SCOPE}
        assert token=='DEMO'
        if url==API:
            folder=params['q'].split("'")[1]
            if self.fail_folder and folder==S:raise DomainError('DEMO brak dostępu do folderu')
            return {'files':[x.copy() for x in self.rows.values() if folder in x['parents'] and not x['trashed']], 'incompleteSearch':self.partial}
        key=url.rsplit('/',1)[-1]
        if key not in self.rows:raise DomainError('DEMO missing')
        return self.rows[key].copy()
    def request(self,url,params=None,token=None,form=None,limit=None):
        self.calls.append((url,params,token,form));key=url.split('/')[-2] if url.endswith('/export') else url.rsplit('/',1)[-1]
        content=self.content[key]
        assert len(content)<=limit
        return content

directory=Path(tempfile.mkdtemp(prefix='drive-bulk-demo-',dir=ROOT/'.test-data'));store=Store(directory);google=Google();drive=Drive(store,google)
drive.configure(json.dumps({'installed':{'client_id':'bulk-demo.apps.googleusercontent.com','client_secret':'DEMO'}}).encode());drive.save_token({'access_token':'DEMO','refresh_token':'REFRESH-DEMO','token_type':'Bearer','expires_in':3600,'scope':SCOPE});drive.set_folder(F)
before=store.export_json()['tables']; before_files=set(store.files.iterdir()); plan=drive.preview_all('owner')
check('Cały folder obejmuje pliki z trzech poziomów',plan['wholeFolder'] and plan['foldersScanned']==3 and plan['filesFound']==9 and len(plan['items'])==8)
check('Import całego folderu przekracza ograniczenie pięciu plików',len(plan['items'])>5)
check('Podgląd całego folderu nie zapisuje bazy ani plików',store.export_json()['tables']==before and set(store.files.iterdir())==before_files)
check('Zbyt duży plik jest jawnie wymieniony',len(plan['skipped'])==1 and plan['skipped'][0]['name']=='large-demo.mp4')
check('Dokument Google jest eksportowany do DOCX',any(x['title']=='Dokument DEMO.docx' and x['readable'] for x in plan['items']))
check('Arkusz zachowuje format XLSX bez udawania odczytu AI',any(x['title']=='Arkusz DEMO.xlsx' and not x['readable'] for x in plan['items']))
check('Nagrania i pliki projektowe są objęte importem',all(any(x['title']==name and not x['readable'] for x in plan['items']) for name in ['voice-demo.mp3','design-demo.xcf']))
check('Powtarzające się nazwy zachowują odrębne źródła',len([x for x in plan['items'] if x['title']=='EN.docx'])==2 and len({x['version'] for x in plan['items'] if x['title']=='EN.docx'})==2)
check('Plik spoza drzewa nie zostaje pobrany',not any('outside_demo_123' in x[0] for x in google.calls))
check('Zapis całego folderu wymaga potwierdzenia',reject(lambda:drive.commit('owner',plan['token'],plan['revision'],False)))
check('Inna sesja nie może zapisać całego folderu',reject(lambda:drive.commit('other',plan['token'],plan['revision'],True)))
ids=drive.commit('owner',plan['token'],plan['revision'],True)
check('Jedno potwierdzenie zapisuje całą partię atomowo',len(ids)==8 and store.state()['revision']==plan['revision']+1)
audio=next(x for x in store.state()['materials'] if x['fileName']=='voice-demo.mp3')
check('Binarny załącznik zachowuje oryginalną nazwę i bajty',audio['fileKey'].endswith('.bin') and (store.files/audio['fileKey']).read_bytes()==b'ID3 DEMO')
check('Ścieżka podfolderu pozostaje w pochodzeniu',all('Folder: Portfolio DEMO' in x['description'] for x in store.state()['materials']))
native=next(x for x in store.state()['materials'] if x['title']=='Dokument DEMO.docx');parts,_,_,_=MaterialReader(store.files).read(native)
check('Czytnik AI odczytuje tekst eksportowanego DOCX',any('n8n' in x['text'] for x in parts))
try:MaterialReader(store.files).read(audio)
except ValueError as error:check('Czytnik nie interpretuje nagrania jako tekst',bool(str(error)))
else:raise AssertionError('Binary read as text')
archive=store.archive_bytes();package,files=store.read_archive(archive)
check('Pełny ZIP waliduje i zawiera binarne pliki portfolio',bool(store.validate_snapshot(package)) and any(x.endswith('.bin') for x in files))
second=Store(directory/'restore-demo');preview=second.preview_import('zip',archive);second.commit_import(preview,second.state()['revision'])
check('Pełna kopia odtwarza portfolio z nagraniami i źródłami',len(second.state()['materials'])==8 and any(x['fileName']=='voice-demo.mp3' for x in second.state()['materials']))
again=drive.preview_all('owner')
check('Ponowne wczytanie nie powiela tych samych wersji',again['token'] is None and not again['items'] and len(again['skipped'])==9)
google.partial=True;partial=drive.preview_all('owner')
check('Niepełne listowanie Google nie udaje pełnego importu',bool(partial['warnings']))
google.partial=False;google.fail_folder=True;partial=drive.preview_all('owner')
check('Brak dostępu do podfolderu jest jawny',any('brak dostępu' in x for x in partial['warnings']))
google.fail_folder=False
google.rows['text_demo_123']['version']='2'
with patch('app.drive.MAX_BULK_BYTES',1):budget=drive.preview_all('owner')
check('Limit łącznych danych nie zapisuje niepełnej partii automatycznie',not budget['items'] and budget['token'] is None and any('200 MB' in x['reason'] for x in budget['skipped']))
check('Duże nagranie mieści się w limicie binarnych załączników',store.validate_upload('recording.bin',b'a'*(21*1024*1024))[1]=='.bin')
check('Duży załącznik zachowuje pełną kopię z limitem 300 MB',__import__('app.transfer',fromlist=['MAX_ARCHIVE']).MAX_ARCHIVE==300*1024*1024)
check('Po testach odmów baza zachowuje osiem materiałów',len(store.state()['materials'])==8)
large_bytes=b'a'*(21*1024*1024)
store.import_materials([{'data':{'title':'Large recording DEMO','kind':'Portfolio','version':'1','description':'DEMO','url':''},'name':'large.bin','downloadName':'large.m4a','content':large_bytes}],store.state()['revision'])
large_package,large_files=store.read_archive(store.archive_bytes())
check('Kopia zachowuje załącznik powyżej dawnego limitu 20 MB',any(x['fileName']=='large.m4a' and x['size']==len(large_bytes) for x in large_package['tables']['materials']) and any(len(x)==len(large_bytes) for x in large_files.values()))
legacy=Store(directory/'legacy-schema-demo')
offer=legacy.mutate('saveOffer',{'title':'Animator DEMO','company':'Firma DEMO','location':'Polska','direction':'Inne','mode':'Zdalna','contract':'Umowa o pracę','description':'','url':'','deadline':''},None,None,legacy.state()['revision'])
application=legacy.mutate('createApplication',{'offerId':offer},None,None,legacy.state()['revision'])
material=legacy.upload({'title':'Legacy DEMO','kind':'Portfolio','version':'1','description':'DEMO','url':''},'legacy.txt',b'Legacy source DEMO',legacy.state()['revision'])
legacy.mutate('pinMaterial',{'applicationId':application,'materialId':material},None,None,legacy.state()['revision'])
legacy_before=legacy.export_json()['tables']
with legacy.connection() as db:
    ddl=next(x for x in SCHEMA.splitlines() if x.startswith('CREATE TABLE materials ('))
    ddl=ddl.replace("CHECK(size>=0 AND (size<=20971520 OR (fileKey LIKE '%.bin' AND size<=104857600)))",'CHECK(size>=0 AND size<=20971520)').replace('CREATE TABLE materials (','CREATE TABLE materials_legacy (')
    db.execute('PRAGMA foreign_keys=OFF');db.execute('BEGIN IMMEDIATE');db.execute(ddl);db.execute('INSERT INTO materials_legacy SELECT * FROM materials');db.execute('DROP TABLE materials');db.execute('ALTER TABLE materials_legacy RENAME TO materials');db.execute('PRAGMA user_version=1');db.commit()
migrated=Store(legacy.directory)
check('Aktualizacja starej bazy zachowuje wszystkie rekordy i identyfikatory',migrated.export_json()['tables']==legacy_before)
with migrated.connection() as db:check('Aktualizacja zachowuje relacje i ustawia wersję 2',db.execute('PRAGMA user_version').fetchone()[0]==2 and not db.execute('PRAGMA foreign_key_check').fetchall())
check('Przed aktualizacją starej bazy powstaje pełna kopia',any('przed-schema-2' in x['name'] for x in migrated.backup_list()))
check('Przypięty materiał po aktualizacji ma niezmienną treść',(migrated.files/migrated.state()['materials'][0]['fileKey']).read_bytes()==b'Legacy source DEMO' and migrated.state()['links'][0]['materialId']==material)
(ROOT/'app/tests/drive-bulk-report.json').write_text(json.dumps({'result':'PASS','count':len(checks),'checks':checks,'scope':'Oddzielne dane DEMO, rzeczywisty magazyn, DPAPI, eksport i odzyskiwanie ZIP; odpowiedzi Google symulowane.'},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:',len(checks),'kontroli importu całego portfolio.')
