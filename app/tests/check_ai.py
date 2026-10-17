"""Isolated safety checks and real Ollama integration, never the user's records."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.ai import Assistant, OllamaProvider
from app.storage import Store
from app.validation import DomainError, DIRECTIONS, CONTRACTS

checks=[]
def check(name,value=True):
    if not value: raise AssertionError(name)
    checks.append(name); print('PASS '+name,flush=True)
def reject(fn,status=None):
    try: fn()
    except DomainError as error:
        if status: assert error.status==status,(error.status,error.message)
        return
    raise AssertionError('Operacja powinna być odrzucona')

class Stub:
    name='ollama'
    def __init__(self): self.result={}; self.calls=[]
    def models(self): return ['qwen3:1.7b']
    def generate(self,model,instruction,data,schema):
        self.calls.append(copy.deepcopy(data)); result=copy.deepcopy(self.result)
        if 'tasks' in result and 'clarification' in result: result['intent']='clarify' if result.pop('clarification') else 'add'
        return result

directory=Path(tempfile.mkdtemp(prefix='ai-',dir=ROOT/'.test-data')); store=Store(directory)
def cmd(action,data,key=None,version=None): return store.mutate(action,data,key,version,store.state()['revision'])
profile=store.state()['profile']; cmd('saveProfile',{'name':'Osoba testowa','email':'test@example.org','goal':'Test lokalnego AI','preferences':profile['preferences']},profile['id'],profile['rowVersion'])
fact=cmd('saveEntry',{'kind':'Umiejętność','content':'Tworzę automatyzacje w n8n.','status':'Podane przez użytkownika','source':'Deklaracja DEMO'})
learning=cmd('saveEntry',{'kind':'Umiejętność','content':'Uczę się tworzenia materiałów audiowizualnych z AI.','status':'W nauce','source':'Deklaracja DEMO'})
unknown=cmd('saveEntry',{'kind':'Doświadczenie','content':'NIEPOTWIERDZONE 10 lat doświadczenia i 500 projektów.','status':'Do potwierdzenia','source':'Niezweryfikowany przykład'})
offer=cmd('saveOffer',{'title':'Specjalista automatyzacji DEMO','company':'Firma DEMO','location':'Polska','direction':DIRECTIONS[1],'mode':'Zdalna','contract':CONTRACTS[0],'url':'https://example.org/ai-demo','description':'Wymagania: n8n; tworzenie materiałów audiowizualnych z AI.','deadline':''})
application=cmd('createApplication',{'offerId':offer})
provider=Stub(); assistant=Assistant(store,provider)
reject(lambda:assistant.prepare('a','message',application,''),409); check('Wyłączony model nie generuje')
assistant.configure('qwen3:1.7b',True,store.state()['revision']); reject(lambda:assistant.configure('kimi-k2.5:cloud',True,store.state()['revision'])); check('Model cloud jest zablokowany')
revision,context=assistant.context(application,'Znajdź n8n')
check('Odczyt bazy zachowuje źródła i pomija niepotwierdzone wpisy',unknown not in [x['id'] for x in context['facts']] and context['facts'][1]['status']=='W nauce' and context['found'])
provider.result={'factIds':[fact,learning]}; baseline=store.export_json(); preview=assistant.prepare('a','message',application,'')
check('Generowanie nie zapisuje niczego w bazie',store.export_json()['tables']==baseline['tables'])
check('Szkic zachowuje dosłowne fakty i poziom w nauce','W nauce: Uczę się' in preview['draft'] and '500 projektów' not in preview['draft'])
reject(lambda:assistant.commit('b',preview['token'],preview['revision'],True),409); check('Inna sesja nie może zatwierdzić podglądu')
reject(lambda:assistant.commit('a',preview['token'],preview['revision'],False)); check('Brak potwierdzenia nie zapisuje')
keys=assistant.commit('a',preview['token'],preview['revision'],True); check('Zatwierdzenie atomowo zapisuje raport, tekst, PDF i DOCX',len(keys)==4 and len(store.state()['links'])==4)
reject(lambda:assistant.commit('a',preview['token'],preview['revision'],True),409); check('Powtórzenie zatwierdzenia nie powiela materiałów')
pdf=next(x for x in store.state()['materials'] if x['fileKey'].endswith('.pdf')); from pypdf import PdfReader
pdf_text='\n'.join(p.extract_text() for p in PdfReader(store.files/pdf['fileKey']).pages)
check('Prawdziwy PDF zachowuje polskie znaki i W nauce','Uczę się tworzenia materiałów audiowizualnych z AI.' in pdf_text and 'W nauce:' in pdf_text)
from app.documents import pdf_bytes
long_text='Zażółć gęślą jaźń.\n\n'+'\n\n'.join(['Długi tekst i źródła.']*80)
(directory/'sample-long.pdf').write_bytes(pdf_bytes(long_text,'Profil zawodowy'))
check('PDF obsługuje wielostronicową treść',len(PdfReader(directory/'sample-long.pdf').pages)>1)
provider.result={'factIds':[unknown]}; reject(lambda:assistant.prepare('a','message',application,''),502); check('AI nie może użyć niepotwierdzonego ID')
provider.result={'factIds':['nieznane']}; reject(lambda:assistant.prepare('a','message',application,''),502); check('Nieznane źródło zatrzymuje generowanie')
provider.result={'factIds':[[fact]]}; reject(lambda:assistant.prepare('a','message',application,''),502); check('Nieprawidłowy typ źródła jest odrzucony')
provider.result={'matches':[{'requirementId':'R1','factIds':[fact],'comment':'Wniosek testowy'},{'requirementId':'R2','factIds':[learning],'comment':'Model błędnie uznał kompetencję za opanowaną'}],'nextActions':['Sprawdź portfolio']}
preview=assistant.prepare('a','analysis',application,''); check('Ocena W nauce narzucona przez aplikację mimo komentarza modelu',preview['matches'][1]['assessment']=='W nauce / częściowo')
provider.result={'matches':[{'requirementId':'R999','factIds':[],'comment':''}],'nextActions':[]}; reject(lambda:assistant.prepare('a','analysis',application,''),502); check('Wymaganie musi być prawdziwym fragmentem oferty')
provider.result={'tasks':[{'title':'Przejrzeć oferty','due':'1999-01-01'}],'note':'Notatka DEMO','clarification':''}
preview=assistant.prepare('a','command',application,'Dodaj zadanie: przejrzeć oferty na piątek i notatkę: Notatka DEMO')
check('Piątek rozwiązany deterministycznie na datę z Europe/Warsaw',preview['operations'][0]['data']['due']!='1999-01-01')
revision=preview['revision']; assistant.commit('a',preview['token'],revision,True); check('Zadanie i notatka zapisane w jednej transakcji',len(store.state()['tasks'])==1 and len(store.state()['notes'])==1)
provider.result={'tasks':[{'title':'Zadanie','due':'2030-01-01'}],'note':'','clarification':''}; preview=assistant.prepare('a','command','','Dodaj zadanie: przejrzeć oferty'); check('Wymyślona data wymaga wyjaśnienia',bool(preview['clarification']) and not preview['operations'])
reject(lambda:assistant.commit('a',preview['token'],preview['revision'],True)); check('Niejasnej propozycji nie można zatwierdzić')
provider.result={'tasks':[{'title':'Zadanie','due':'2026-12-01'}],'note':'','clarification':''}; preview=assistant.prepare('a','command','','Dodaj zadanie na 2026-12-01'); cmd('saveTask',{'title':'Inna zmiana','due':'2026-12-02','applicationId':''}); reject(lambda:assistant.commit('a',preview['token'],preview['revision'],True),409); check('Zmiana danych po generowaniu unieważnia zatwierdzenie')
provider.result={'factIds':[fact]}; preview=assistant.prepare('a','message',application,''); assistant.pending[preview['token']]['expires']=0; reject(lambda:assistant.commit('a',preview['token'],preview['revision'],True),409); check('Wygasłego podglądu nie można zatwierdzić')
provider.result={'tasks':[{'title':'Pierwsze','due':'2026-12-01'},{'title':'Drugie','due':'2026-12-02'}],'note':'','clarification':''}
# Explicit dates needed when several dates appear; provider output has two independently checked dates.
preview=assistant.prepare('a','command','','Dodaj zadania na 2026-12-01 i 2026-12-02'); original_command=store.command
def fail_second(db,action,data,key,version):
    if data.get('title')=='Drugie': raise DomainError('Wymuszona awaria testowa')
    return original_command(db,action,data,key,version)
before=store.export_json(); store.command=fail_second; reject(lambda:assistant.commit('a',preview['token'],preview['revision'],True)); store.command=original_command; check('Awaria drugiej operacji nie zostawia pierwszej',store.export_json()['tables']==before['tables'])
snapshot=store.archive_bytes(); fresh=Store(Path(tempfile.mkdtemp(prefix='ai-restore-',dir=ROOT/'.test-data'))); fresh.commit_import(fresh.preview_import('zip',snapshot),fresh.state()['revision']); check('Backup i restore zachowują AI, źródła i pliki',Assistant(fresh,Stub()).config()['enabled'] and len(fresh.state()['materials'])==4 and len(fresh.state()['links'])==4)
check('Restart zachowuje konfigurację i materiały',Assistant(Store(directory),Stub()).config()['enabled'])
assistant.configure('qwen3:1.7b',False,store.state()['revision']); check('Można wyłączyć model bez utraty danych',not assistant.config()['enabled'] and len(store.state()['materials'])==4)

real=Assistant(store,OllamaProvider()); real.configure('qwen3:1.7b',True,store.state()['revision']); start=time.monotonic(); real_results=[]
for mode,query in [('analysis',''),('message',''),('command','Dodaj zadanie: przejrzeć oferty na piątek')]:
    p=real.prepare('real',mode,application,query); real_results.append(p)
    check('Rzeczywisty Ollama / '+mode,p['model']=='qwen3:1.7b' and (bool(p.get('matches')) if mode=='analysis' else bool(p['draft']) if mode in ('message','message') else bool(p['operations'])))
    real.commit('real',p['token'],p['revision'],True)
check('Rzeczywiste AI nie zmieniło profilu ani statusu aplikacji',len(store.state()['entries'])==3 and store.state()['applications'][0]['status']=='Przygotowanie')
report={'passed':len(checks),'checks':checks,'directory':str(directory),'realModel':'qwen3:1.7b','realElapsedSeconds':round(time.monotonic()-start,2),'realResults':real_results}
(Path(__file__).with_name('ai-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'passed':len(checks),'directory':str(directory)},ensure_ascii=False),flush=True)
