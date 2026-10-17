"""Odczyt materiałów, źródła, bezpieczne linki i nowy tryb AI na danych DEMO."""
import copy
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.ai import Assistant, OllamaProvider, materials_request
from app.storage import Store
from app.validation import DomainError
from app.materials import MaterialReader, public_target, fetch_public, web_text
from app.documents import pdf_bytes

checks=[]
def check(name,ok=True):
    assert ok,name
    checks.append(name); print('PASS '+name,flush=True)
def reject(fn,status=502):
    try: fn()
    except DomainError as error: assert error.status==status
    else: raise AssertionError('Oczekiwano odrzucenia')

directory=Path(tempfile.mkdtemp(prefix='materials-',dir=ROOT/'.test-data')); store=Store(directory)
def cmd(action,data): return store.mutate(action,data,None,None,store.state()['revision'])
def upload(title,name,content):
    return store.upload({'title':title,'kind':'CV' if title.startswith('CV') else 'Portfolio','version':'1','description':'','url':''},name,content,store.state()['revision'])
cv=upload('CV DEMO','cv.pdf',pdf_bytes('Tworzę automatyzacje w n8n.\n\nUczę się tworzenia materiałów audiowizualnych z AI.','CV DEMO'))
txt=upload('Tekst DEMO','portfolio.txt','Projekt DEMO: przygotowałem instrukcję korzystania z narzędzi cyfrowych.'.encode())
docx=io.BytesIO()
with zipfile.ZipFile(docx,'w') as z:
    z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Projekt DOCX DEMO: szkolenie z narzędzi cyfrowych.</w:t></w:r></w:p></w:body></w:document>')
word=upload('DOCX DEMO','projekt.docx',docx.getvalue())
image=upload('Obraz DEMO','obraz.png',b'\x89PNG\r\n\x1a\nDEMO')
drive=cmd('addMaterial',{'title':'Dysk DEMO','kind':'Portfolio','version':'1','description':'','url':'https://drive.google.com/drive/folders/demo'})
website=cmd('addMaterial',{'title':'Strona DEMO','kind':'Portfolio','version':'1','description':'','url':'https://example.org/portfolio'})
offer=cmd('saveOffer',{'title':'Animator KRC DEMO','company':'Firma DEMO','location':'Polska','direction':'Inne','mode':'Stacjonarna','contract':'Umowa o pracę','description':'Prowadzenie zajęć z narzędzi cyfrowych.','url':'','deadline':''})
application=cmd('createApplication',{'offerId':offer})
reader=MaterialReader(store.files)
def fake_web(url): return '<html><script>Nie pokazuj</script><p>Portfolio DEMO: przygotowanie instrukcji i materiałów do zajęć cyfrowych.</p></html>','text/html','https://example.org/portfolio','a'*64
with patch('app.materials.fetch_public',fake_web): loaded=reader.load(store.state()['materials'])
items={x['materialId']:x for x in loaded['inventory']}
check('Każdy materiał ma stan odczytu',len(items)==6)
check('PDF z polskim tekstem i lokalizatorem strony',any(x['materialId']==cv and x['locator']=='Strona 1' and 'Uczę się' in x['text'] for x in loaded['sources']))
check('DOCX ma tekst i lokalizator akapitu',any(x['materialId']==word and x['locator']=='Akapit 1' and 'szkolenie' in x['text'] for x in loaded['sources']))
check('TXT odczytany bez zmiany treści',any(x['materialId']==txt and x['text'].startswith('Projekt DEMO:') for x in loaded['sources']))
check('Skrypty HTML nie trafiają do źródeł','Nie pokazuj' not in web_text(fake_web('')[0]))
check('Obraz jawnie wymaga OCR',items[image]['status']=='Nieodczytany' and 'OCR' in items[image]['reason'])
check('Sam link Drive bez importu plików jest jawnie niedostępny',items[drive]['status']=='Nieodczytany' and 'Zaimportuj wybrane pliki' in items[drive]['reason'])
row=next(x for x in store.state()['materials'] if x['id']==txt); path=store.files/row['fileKey']; old=path.read_bytes(); path.write_bytes(b'zmieniony')
check('Zmiana pliku jest wykrywana',reader.load([row])['inventory'][0]['status']=='Nieodczytany'); path.write_bytes(old)
check('Ścieżka poza folderem plików jest odrzucona',reader.load([{**row,'fileKey':'../secret.txt'}])['inventory'][0]['status']=='Nieodczytany')
for address in ('127.0.0.1','10.0.0.1','169.254.169.254','::1','224.0.0.1'):
    with patch('app.materials.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]):
        try: public_target('https://example.org/')
        except ValueError: pass
        else: raise AssertionError(address)
check('Adresy prywatne, metadanych i multicast są blokowane')
try: public_target('https://user:password@example.org/')
except ValueError: pass
else: raise AssertionError('Credentials')
check('Link z loginem i hasłem jest blokowany')
class Redirect:
    connections=0
    def __init__(self,*args): Redirect.connections+=1
    def request(self,*args,**kwargs): pass
    def getresponse(self): return self
    status=302
    def getheader(self,name,default=None): return 'https://127.0.0.1/secret' if name=='Location' else default
    def close(self): pass
def addresses(host,*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.1.1.1' if host=='example.org' else '127.0.0.1',443))]
with patch('app.materials.PublicHTTPS',Redirect),patch('app.materials.socket.getaddrinfo',addresses):
    try: fetch_public('https://example.org/')
    except ValueError: pass
    else: raise AssertionError('Private redirect')
check('Przekierowanie do sieci lokalnej jest blokowane przed połączeniem',Redirect.connections==1)
check('Polecenie przeglądu rozpoznaje polskie znaki',materials_request('Przejrzyj wszystkie moje materiały pod kątem aplikacji.'))
check('Dodaj zadanie nie uruchamia odczytu materiałów',not materials_request('Dodaj zadanie: przejrzeć materiały na piątek'))

parser_store=Store(Path(tempfile.mkdtemp(prefix='materials-parser-',dir=ROOT/'.test-data')))
def parser_upload(name,content):
    key=parser_store.upload({'title':name,'kind':'Inny','version':'1','description':'','url':''},name,content,parser_store.state()['revision'])
    row=next(x for x in parser_store.state()['materials'] if x['id']==key)
    return MaterialReader(parser_store.files).load([row])
check('Markdown jest odczytywany',parser_upload('notatka.md',b'# Projekt DEMO')['sources'][0]['text']=='# Projekt DEMO')
check('JSON jest odczytywany jako tekst źródłowy','n8n' in parser_upload('projekt.json',b'{"tool":"n8n"}')['sources'][0]['text'])
from pypdf import PdfWriter
writer=PdfWriter(); writer.add_blank_page(width=100,height=100); writer.encrypt('demo'); content=io.BytesIO(); writer.write(content)
encrypted=parser_upload('encrypted.pdf',content.getvalue())
check('PDF z hasłem jest jawnie niedostępny','zaszyfrowany' in encrypted['inventory'][0]['reason'])
long_text=parser_upload('long.txt',('Ćwiczenie DEMO.\n'*3000).encode())
check('Limit tekstu jest jawny',long_text['inventory'][0]['status']=='Częściowo odczytany' and '24 000' in long_text['inventory'][0]['reason'])

class Stub:
    calls=[]
    def models(self): return ['qwen3:1.7b']
    def generate(self,model,instruction,data,schema):
        self.calls.append(copy.deepcopy(data))
        return {'findings':[{'sourceId':data['sources'][0]['id'],'requirementIds':[data['requirements'][0]['id']] if data['requirements'] else [],'comment':'Przydatny fragment DEMO — do oceny.','recommended':True}],'cvSuggestions':['Ułatw znalezienie opisu projektu w CV.'],'nextActions':['Sprawdź treść ogłoszenia.']}
provider=Stub(); assistant=Assistant(store,provider); assistant.configure('qwen3:1.7b',True,store.state()['revision'])
before=store.export_json()['tables']; files_before=set(store.files.iterdir())
with patch('app.materials.fetch_public',fake_web): preview=assistant.prepare('test','command',application,'Przejrzyj wszystkie moje materiały pod kątem aplikacji na animatora KRC.')
check('Polecenie trafia do trybu przeglądu materiałów',preview['mode']=='materials' and preview['materialsReview'])
check('Podgląd nie zmienia bazy ani plików',before==store.export_json()['tables'] and files_before==set(store.files.iterdir()))
check('Źródła w wyniku mają dosłowny tekst',preview['findings'][0]['source'] in loaded['sources'])
check('Wymagania są wstawiane z ogłoszenia',preview['findings'][0]['requirements']==['Prowadzenie zajęć z narzędzi cyfrowych.'])
reject(lambda:assistant.commit('test',preview['token'],preview['revision'],False),422)
check('Zapis raportu wymaga potwierdzenia')
ids=assistant.commit('test',preview['token'],preview['revision'],True)
check('Zapisuje się tylko raport, bez aktualizacji kwalifikacji',len(ids)==1 and len(store.state()['entries'])==0)
check('Raport jest przypięty do aplikacji',any(x['materialId']==ids[0] and x['applicationId']==application for x in store.state()['links']))
reject(lambda:assistant.commit('test',preview['token'],preview['revision'],True),409)
check('Ponowny zapis nie powiela raportu')
bad={'findings':[{'sourceId':'nieznane','requirementIds':[],'comment':'','recommended':True}],'cvSuggestions':[],'nextActions':[]}
reject(lambda:assistant.validate_material_result(bad,loaded['sources'],[]))
check('Nieznany cytat modelu jest odrzucony')
bad['findings'][0]['sourceId']=loaded['sources'][0]['id']; bad['findings'][0]['requirementIds']=['R999']
reject(lambda:assistant.validate_material_result(bad,loaded['sources'],[]))
check('Zmyślone wymaganie modelu jest odrzucone')
reject(lambda:assistant.prepare('test','materials','',''),422)
check('Brak wybranej aplikacji ma czytelny błąd')
rev,context=assistant.context(application,'',True); context['requirements']=[]
with patch('app.materials.fetch_public',fake_web): missing=assistant.review_materials(context,'qwen3:1.7b','DEMO')
check('Brak ogłoszenia nie daje pozornego porównania',any('Brak treści ogłoszenia' in x for x in missing['warnings']) and not missing['findings'][0]['requirements'])
check('Poprzedni raport AI nie staje się dowodem kwalifikacji',next(x for x in missing['inventory'] if x['materialId']==ids[0])['status']=='Nieodczytany')
huge_sources=[{**loaded['sources'][0],'id':f'L-F{i}','text':'X'*900} for i in range(70)]
huge={'sources':huge_sources,'inventory':[{'materialId':cv,'title':'Limit DEMO','version':'1','status':'Odczytany','reason':'','fragments':70,'analysedFragments':0}]}
with patch.object(assistant.material_reader,'load',return_value=huge): bounded=assistant.review_materials(context,'qwen3:1.7b','DEMO')
check('Limit analizy nie ukrywa pominiętych fragmentów',bounded['coverage']['analysedFragments']<70 and bounded['inventory'][0]['status']=='Częściowo odczytany' and any('Limit analizy' in text for text in bounded['warnings']))
real=Assistant(store,OllamaProvider())
with patch('app.materials.fetch_public',fake_web): result=real.prepare('real','materials',application,'Przejrzyj wszystkie moje materiały i wskaż źródła przydatne do aplikacji na animatora KRC.')
check('Rzeczywisty lokalny model analizuje odczytane fragmenty',result['modelCalled'] and result['coverage']['analysedFragments']==result['coverage']['fragments'] and bool(result['findings']))
check('Rzeczywisty model zachowuje niedostępne materiały w raporcie',next(x for x in result['inventory'] if x['materialId']==drive)['status']=='Nieodczytany')
report={'result':'PASS','count':len(checks),'checks':checks,'directory':str(directory),'realModel':result['model'],'realCoverage':result['coverage'],'scope':'Bazy DEMO, sieć symulowana; generowanie w rzeczywistym lokalnym Ollama.'}
(ROOT/'app/tests/materials-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:',len(checks),'kontroli materiałów.')
