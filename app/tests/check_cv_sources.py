"""Regression: small model repeats valid IDs when fewer than six profile facts exist."""
import copy
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.storage import Store
from app.ai import Assistant
from app.validation import DomainError
checks=[]
def check(name,ok=True):assert ok,name;checks.append(name)
def reject(fn):
    try:fn()
    except DomainError:return True
    raise AssertionError('Expected rejection')
class Model:
    name='ollama'
    def __init__(self):self.result={};self.schemas=[]
    def models(self):return ['qwen3:1.7b']
    def generate(self,model,instruction,data,schema):self.schemas.append(copy.deepcopy(schema));return copy.deepcopy(self.result)
store=Store(Path(tempfile.mkdtemp(prefix='cv-sources-demo-',dir=ROOT/'.test-data')))
def cmd(action,data):return store.mutate(action,data,None,None,store.state()['revision'])
known=cmd('saveEntry',{'kind':'Umiejętność','content':'Przygotowuję treści edukacyjne DEMO.','status':'Podane przez użytkownika','source':'DEMO'})
learning=cmd('saveEntry',{'kind':'Umiejętność','content':'Uczę się n8n DEMO.','status':'W nauce','source':'DEMO'})
third=cmd('saveEntry',{'kind':'Inne','content':'Wpis profilu DEMO.','status':'Podane przez użytkownika','source':'DEMO'})
unconfirmed=cmd('saveEntry',{'kind':'Inne','content':'Niepotwierdzone osiągnięcie DEMO.','status':'Do potwierdzenia','source':'DEMO'})
offer=cmd('saveOffer',{'title':'Animator DEMO','company':'Firma DEMO','location':'Polska','direction':'Inne','mode':'Zdalna','contract':'Umowa o pracę','url':'','description':'Wymagania: treści edukacyjne i narzędzia cyfrowe.','deadline':''});appid=cmd('createApplication',{'offerId':offer})
model=Model();assistant=Assistant(store,model);assistant.configure('qwen3:1.7b',True,store.state()['revision'])
model.result={'factIds':[known,learning,third,learning,third,learning]};before=store.export_json()['tables']
preview=assistant.prepare('owner','message',appid,'')
check('Trzy istniejące źródła powtórzone sześć razy dają poprawny szkic',len(preview['evidence'])==3 and preview['draft'])
check('Kolejność pierwszych wystąpień jest zachowana',[x['id'] for x in preview['evidence']]==[known,learning,third])
check('Tekst każdego źródła pojawia się w szkicu jeden raz',all(preview['draft'].count(x['content'])==1 for x in preview['evidence']))
check('Poziom W nauce pozostaje bez zmian','W nauce: Uczę się n8n DEMO.' in preview['draft'])
check('Normalizacja jest jawna',preview['selectionNormalized'] and any('Powtórzone' in x for x in preview['control']))
check('Schemat ogranicza wybór do liczby dostępnych faktów',model.schemas[-1]['properties']['factIds']['maxItems']==3 and model.schemas[-1]['properties']['factIds']['uniqueItems'] is True)
check('Podgląd nie zapisuje danych',store.export_json()['tables']==before)
check('Adaptacja wiadomości ma osobną wersję',preview['instructionVersion']=='cv-master-local-4')
check('Zapis nadal wymaga potwierdzenia',reject(lambda:assistant.commit('owner',preview['token'],preview['revision'],False)))
ids=assistant.commit('owner',preview['token'],preview['revision'],True)
check('Potwierdzony szkic zachowuje cztery powiązane pliki',len(ids)==4 and all(any(x['materialId']==key and x['applicationId']==appid for x in store.state()['links']) for key in ids))
model.result={'factIds':[known,known,'UNKNOWN']}
check('Nieznane ID nie zostaje ukryte przez deduplikację',reject(lambda:assistant.prepare('owner','message',appid,'')))
model.result={'factIds':[unconfirmed,unconfirmed]}
check('Niepotwierdzone wpisy nadal są blokowane',reject(lambda:assistant.prepare('owner','message',appid,'')))
model.result={'factIds':[[known]]}
check('Nieprawidłowe typy nadal są blokowane',reject(lambda:assistant.prepare('owner','message',appid,'')))
model.result={'factIds':[known]*7}
check('Nadmierny surowy wynik nadal jest blokowany',reject(lambda:assistant.prepare('owner','message',appid,'')))
model.result={'factIds':[known,known,learning]};message=assistant.prepare('owner','message',appid,'')
check('Wiadomość korzysta z tej samej poprawki źródeł',len(message['evidence'])==2 and message['draft'].count('Przygotowuję treści edukacyjne DEMO.')==1)
model.result={'matches':[{'requirementId':'R1','factIds':[known,known],'comment':'DEMO'}],'nextActions':[]}
check('Reguły odrębnej analizy pozostały bez zmian',reject(lambda:assistant.prepare('owner','analysis',appid,'')))
check('Profil zachowuje źródła i poziomy po zapisie szkicu',store.export_json()['tables']['profile_entries']==before['profile_entries'])
(ROOT/'app/tests/cv-sources-report.json').write_text(json.dumps({'result':'PASS','count':len(checks),'checks':checks,'scope':'Osobna baza DEMO, model symulowany; podgląd, zapis i walidacja źródeł rzeczywiste.'},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:',len(checks),'kontroli źródeł szkicu CV.')
