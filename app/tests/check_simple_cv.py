"""Complete source CV, edited approval and real exports in an isolated database."""
import io,json,sys,tempfile,copy,asyncio
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.storage import Store
from app.ai import Assistant
from app.validation import DomainError
from docx import Document
from pypdf import PdfReader
from app.server import create_app
checks=[]
def check(name,ok=True):assert ok,name;checks.append(name)
def reject(fn):
    try:fn()
    except DomainError:return True
    raise AssertionError('Expected rejection')
class Model:
    name='ollama'
    def models(self):return ['demo-local']
    def generate(self,model,instruction,data,schema):
        self.last=copy.deepcopy(data)
        return {'summaryIds':[data['cvPassages'][0]['id']],'projectIds':[data['portfolio'][0]['id']] if data['portfolio'] else []} if not hasattr(self,'result') else self.result
directory=Path(tempfile.mkdtemp(prefix='simple-cv-demo-',dir=ROOT/'.test-data'));store=Store(directory)
def cmd(action,data):return store.mutate(action,data,None,None,store.state()['revision'])
check('Nowy profil nie zawiera wcześniejszych danych ani miast',store.state()['profile']['name']=='' and store.state()['profile']['preferences']['locations']==[])
offer=cmd('saveOffer',{'title':'Animator DEMO','company':'Firma DEMO','location':'Polska','direction':'Inne','mode':'Zdalna','contract':'Umowa o pracę','url':'','description':'Wsparcie użytkowników komputerów i prowadzenie zajęć.','deadline':''});appid=cmd('createApplication',{'offerId':offer})
original='''JAN DEMO
demo@example.org

PROFIL
Pomagam użytkownikom komputerów i przygotowuję materiały edukacyjne DEMO.

DOŚWIADCZENIE
Firma DEMO - Specjalista wsparcia | 01.2020 - 02.2023
• Konfigurowałem sprzęt i oprogramowanie na stanowiskach użytkowników.
• Uczyłem się narzędzi do automatyzacji; projekt pozostaje w nauce.

WYKSZTAŁCENIE
Uczelnia DEMO - Informatyka | 10.2016 - 07.2020

JĘZYKI
Angielski B1

SŁOWA KLUCZOWE
ZBĘDNY BLOK SEO
'''
base=store.upload({'title':'CV bazowe DEMO','kind':'CV','version':'1','description':'','url':''},'cv.txt',original.encode(),store.state()['revision'])
extra=store.upload({'title':'Projekt DEMO','kind':'Portfolio','version':'1','description':'','url':''},'projekt.txt',b'Projekt DEMO: przygotowanie instrukcji obslugi komputera dla uzytkownikow.',store.state()['revision'])
unread=store.upload({'title':'Skan DEMO','kind':'Portfolio','version':'1','description':'','url':''},'scan.png',b'\x89PNG\r\n\x1a\nDEMO',store.state()['revision'])
model=Model();assistant=Assistant(store,model);assistant.configure('demo-local',True,store.state()['revision'])
before=store.export_json()['tables'];preview=assistant.prepare('owner','cv',appid,'',base,[extra,unread])
check('Pełne CV działa bez wpisów profilu',preview['fullCV'] and not store.state()['entries'])
check('Pełna historia i wykształcenie zachowane',all(text in preview['draft'] for text in ('01.2020 - 02.2023','10.2016 - 07.2020','Uczelnia DEMO','Angielski B1','projekt pozostaje w nauce')))
check('Końcowy blok słów kluczowych pominięty jawnie','ZBĘDNY BLOK SEO' not in preview['draft'] and any('Słowa kluczowe' in text for text in preview['control']))
check('Wybrany projekt pochodzi z odczytanego materiału','przygotowanie instrukcji' in preview['draft'])
check('Nieodczytany skan ma jawny status',any(row['materialId']==unread and row['status']=='Nieodczytany' for row in preview['inventory']))
check('Przygotowanie nie zapisuje danych',store.export_json()['tables']==before)
check('Nie można zatwierdzić cudzej sesji',reject(lambda:assistant.commit('another',preview['token'],preview['revision'],True)))
check('Zapis wymaga potwierdzenia',reject(lambda:assistant.commit('owner',preview['token'],preview['revision'],False)))
edited=preview['draft']+'\n\nMoja poprawka redakcyjna DEMO.'
ids=assistant.commit('owner',preview['token'],preview['revision'],True,edited)
rows=[row for row in store.state()['materials'] if row['id'] in ids]
check('Nowa wersja ma cztery powiązane pliki',len(rows)==4 and all(any(link['materialId']==row['id'] and link['applicationId']==appid for link in store.state()['links']) for row in rows))
for row in rows:
    content=(store.files/row['fileKey']).read_bytes()
    if row['fileKey'].endswith('.md'):check('Tekst zapisuje dokładnie poprawioną treść',content.decode()==edited)
    elif row['fileKey'].endswith('.docx'):
        doc=Document(io.BytesIO(content));check('DOCX zawiera poprawioną treść', '\n\n'.join(p.text for p in doc.paragraphs)==edited)
        check('DOCX jest A4',round(doc.sections[0].page_width.mm)==210 and round(doc.sections[0].page_height.mm)==297)
        (directory/'cv-demo.docx').write_bytes(content)
    elif row['fileKey'].endswith('.pdf'):
        pdf=PdfReader(io.BytesIO(content));text='\n'.join(p.extract_text() for p in pdf.pages)
        check('PDF zawiera poprawkę i polskie znaki','Moja poprawka redakcyjna DEMO.' in text and 'WYKSZTAŁCENIE' in text)
        check('W eksporcie nie ma uwag asystenta','SZKIC' not in text and 'Odczytano całe CV' not in text)
        (directory/'cv-demo.pdf').write_bytes(content)
    else:
        report=json.loads(content);check('Raport oddziela poprawki użytkownika od modelu',report['preview']['userEdited'] and report['preview']['originalDraftHash'])
check('Oryginalny plik i profil pozostają bez zmian',(store.files/next(row['fileKey'] for row in store.state()['materials'] if row['id']==base)).read_bytes()==original.encode() and not store.state()['entries'])
check('Token jest jednorazowy',reject(lambda:assistant.commit('owner',preview['token'],preview['revision'],True,edited)))
model.result={'summaryIds':['UNKNOWN'],'projectIds':[]};check('Nieznane źródło modelu odrzucone',reject(lambda:assistant.prepare('owner','cv',appid,'',base,[])));del model.result
check('Wybór obcego CV odrzucony',reject(lambda:assistant.prepare('owner','cv',appid,'','00000000-0000-0000-0000-000000000000',[])))
check('Nie można użyć skanu jako CV bazowego',reject(lambda:assistant.prepare('owner','cv',appid,'',unread,[])))
new=assistant.prepare('owner','cv',appid,'',base,[]);cmd('saveTask',{'title':'Zmiana DEMO','due':'2026-12-01','applicationId':appid})
check('Zmiana bazy po generowaniu blokuje zapis',reject(lambda:assistant.commit('owner',new['token'],new['revision'],True,edited)))
boundary=create_app(directory,8768);boundary.app.state.assistant.provider=model
async def http(method,path,body=b'',headers=None):
    outgoing=[];delivered=False
    async def receive():
        nonlocal delivered
        if not delivered:delivered=True;return {'type':'http.request','body':body,'more_body':False}
        return {'type':'http.disconnect'}
    async def send(message):outgoing.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','headers':[(k.lower().encode(),v.encode()) for k,v in {'Host':'127.0.0.1:8768',**(headers or {})}.items()],'server':('127.0.0.1',8768),'client':('127.0.0.1',12345)}
    await boundary(scope,receive,send)
    start=next(x for x in outgoing if x['type']=='http.response.start');content=b''.join(x.get('body',b'') for x in outgoing if x['type']=='http.response.body');return start,content
def req(method,path,data=None,headers=None):return asyncio.run(http(method,path,json.dumps(data).encode() if data is not None else b'',headers))
start,_=req('GET','/');cookie=next(v.decode().split(';')[0] for k,v in start['headers'] if k==b'set-cookie');csrf=json.loads(req('GET','/api/session',headers={'Cookie':cookie})[1])['csrf']
headers={'Cookie':cookie,'Origin':'http://127.0.0.1:8768','X-CSRF-Token':csrf,'Content-Type':'application/json'}
start,content=req('POST','/api/ai/prepare',{'mode':'cv','applicationId':appid,'baseMaterialId':base,'materialIds':[]},headers)
check('Chronione API przygotowuje pełne CV',start['status']==200 and json.loads(content)['fullCV'])
p=json.loads(content);start,_=req('POST','/api/ai/commit',{'token':p['token'],'revision':p['revision'],'confirmed':True,'draft':'JAN DEMO\n\nPoprawiony dokument DEMO.'},headers)
check('API zapisuje edycję CV',start['status']==200)
check('API odrzuca nadmierną treść',req('POST','/api/ai/commit',{'token':p['token'],'revision':p['revision'],'confirmed':True,'draft':'x'*24001},headers)[0]['status']==422)
check('Przygotowanie CV bez CSRF odrzucone',req('POST','/api/ai/prepare',{'mode':'cv','applicationId':appid,'baseMaterialId':base},{**headers,'X-CSRF-Token':''})[0]['status']==403)
report={'result':'PASS','count':len(checks),'checks':checks,'directory':str(directory),'scope':'Izolowana baza DEMO, model symulowany; rzeczywisty odczyt plików, API, zapis i eksport.'}
(ROOT/'app/tests/simple-cv-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'result':'PASS','count':len(checks),'directory':str(directory)}))
