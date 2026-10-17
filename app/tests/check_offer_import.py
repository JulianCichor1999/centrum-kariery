"""Offer URL -> public text -> protected preview/confirmation -> existing AI context."""
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.runtime/python'))
from app.offer_import import OfferImport,read_offer,PORTAL,PUBLIC_BACKEND
from app.materials import fetch_public
from app.server import create_app
from app.storage import Store
from app.ai import Assistant
from app.validation import DomainError
KEY='9a0d28ac-4ccf-4ac7-890d-96eb419000b3';URL='https://'+PORTAL+'/job/'+KEY+'/animator-ka-klubu-rozwoju-cyfrowego';TITLE='Animator/ka Klubu Rozwoju Cyfrowego'
TEXT='\n'.join('Wymaganie DEMO '+str(n)+': znajomość narzędzi cyfrowych.' for n in range(1,53));checks=[]
def check(name,ok=True):assert ok,name;checks.append(name)
def reject(fn):
    try:fn()
    except (ValueError,DomainError):return True
    raise AssertionError('Expected rejection')
def b64(value):return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()
class PublicSite:
    def __init__(self):self.role='anon';self.status='published';self.calls=[]
    def __call__(self,url,allowed_types=('text/html','text/plain'),request_headers=None):
        self.calls.append((url,allowed_types,request_headers));parts=urlsplit(url)
        if parts.hostname==PORTAL and parts.path.startswith('/job/'):
            text='<html><body>Portal ogłoszeń, bez treści oferty<script src="/assets/index-DEMO.js"></script></body></html>';kind='text/html'
        elif parts.hostname==PORTAL and parts.path.startswith('/assets/'):
            token=b64({'alg':'HS256'})+'.'+b64({'role':self.role,'ref':urlsplit(PUBLIC_BACKEND).hostname.split('.')[0]})+'.DEMO'
            text='const host="'+PUBLIC_BACKEND+'",publicClient="'+token+'";';kind='application/javascript'
        else:
            assert url.startswith(PUBLIC_BACKEND+'/rest/v1/job_postings?')
            params=parse_qs(parts.query);assert params['id']==['eq.'+KEY] and params['status']==['eq.published'];assert request_headers and request_headers['apikey']==request_headers['Authorization'][7:]
            text=json.dumps([{'id':KEY,'status':self.status,'title':TITLE,'description':TEXT,'requirements':'','responsibilities':None}]);kind='application/json'
        return text,kind,url,hashlib.sha256(text.encode()).hexdigest()
site=PublicSite();result=read_offer(URL,TITLE,site)
check('Czytnik pobiera tekst konkretnej opublikowanej oferty',result['text']==TEXT and len(site.calls)==3)
check('Publiczny klient nie trafia do wyniku dla interfejsu','apikey' not in json.dumps(result) and 'publicClient' not in json.dumps(result))
site.role='service_role';before=len(site.calls)
check('Klucz innej roli nie jest używany',reject(lambda:read_offer(URL,TITLE,site)) and len(site.calls)==before+2)
site.role='anon';site.status='draft'
check('Nieopublikowana oferta jest odrzucona',reject(lambda:read_offer(URL,TITLE,site)))
site.status='published'
check('Odmienny tytuł jest odrzucony',reject(lambda:read_offer(URL,'Inne stanowisko',site)))
def generic(url,**kwargs):
    value={'@context':'https://schema.org','@type':'JobPosting','title':TITLE,'description':'<p>'+TEXT+'</p><script>UNTRUSTED()</script>'}
    html='<script type="application/ld+json">'+json.dumps(value).replace('<',chr(92)+'u003c')+'</script>'
    return html,'text/html',url,'a'*64
generic_result=read_offer('https://example.org/job',TITLE,generic)
check('Ogólne strony obsługują jednoznaczny JobPosting','Wymaganie DEMO' in generic_result['text'])
check('Kod z opisu HTML nie trafia do treści','UNTRUSTED' not in generic_result['text'])
check('Sama nawigacja portalu nie staje się ofertą',reject(lambda:read_offer('https://example.org/job',TITLE,lambda url:('<h1>Portal</h1>','text/html',url,'a'*64))))
class Redirect:
    def request(self,*args,**kwargs):pass
    def getresponse(self):return self
    status=302
    def getheader(self,name,*args):return 'https://other.example/job' if name=='Location' else None
    def close(self):pass
with patch('app.materials.public_target',side_effect=lambda url:(urlsplit(url).hostname,'8.8.8.8','/job')),patch('app.materials.PublicHTTPS',return_value=Redirect()) as connections:
    check('Nagłówki publicznego klienta nie przechodzą na inny host',reject(lambda:fetch_public('https://example.org/job',allowed_types=('application/json',),request_headers={'apikey':'DEMO'})) and connections.call_count==1)
directory=Path(tempfile.mkdtemp(prefix='offer-import-demo-',dir=ROOT/'.test-data'));store=Store(directory)
offer=store.mutate('saveOffer',{'title':TITLE,'company':'Firma DEMO','location':'Polska','direction':'Inne','mode':'Zdalna','contract':'Umowa o pracę','url':URL,'description':'','deadline':''},None,None,store.state()['revision'])
application=store.mutate('createApplication',{'offerId':offer},None,None,store.state()['revision'])
importer=OfferImport(store,lambda url,title:read_offer(url,title,site));before=store.export_json()['tables'];plan=importer.preview('owner',offer)
check('Podgląd nie zmienia bazy',store.export_json()['tables']==before)
check('Brak potwierdzenia blokuje zapis',reject(lambda:importer.commit('owner',plan['token'],plan['revision'],False,plan['text'])))
check('Inna sesja nie zatwierdzi treści',reject(lambda:importer.commit('other',plan['token'],plan['revision'],True,plan['text'])))
state=importer.commit('owner',plan['token'],plan['revision'],True,plan['text'])
check('Potwierdzenie uzupełnia istniejącą ofertę',len(state['offers'])==1 and state['offers'][0]['id']==offer and state['offers'][0]['description']==TEXT)
check('Import zachowuje profil, aplikację i parametry oferty',store.export_json()['tables']['profiles']==before['profiles'] and state['applications'][0]['id']==application and state['offers'][0]['direction']=='Inne' and state['offers'][0]['url']==URL)
check('Historia zawiera pochodzenie i hash źródła',any(x['action']=='offerTextImport' and 'SHA256:' in x['text'] for x in state['applications'][0]['history']))
check('Przed zapisem powstaje kopia',any('przed-odczytem-oferty' in x['name'] for x in store.backup_list()))
check('Jednorazowy podgląd nie powiela zapisu',reject(lambda:importer.commit('owner',plan['token'],plan['revision'],True,plan['text'])))
_,context=Assistant(store).context(application,'')
check('Analiza zachowuje wszystkie 52 fragmenty zamiast zgłaszać brak treści',len(context['requirements'])==52 and context['offer']['description']==TEXT)
plan=importer.preview('owner',offer);store.mutate('saveTask',{'title':'DEMO','due':'2026-10-14','applicationId':''},None,None,store.state()['revision'])
check('Konflikt rewizji nie nadpisuje nowszych danych',reject(lambda:importer.commit('owner',plan['token'],plan['revision'],True,plan['text'])))
boundary=create_app(directory,8779);boundary.app.state.offer_import.reader=lambda url,title:read_offer(url,title,site)
async def http(method,path,body=b'',headers=None):
    outgoing=[];delivered=False
    async def receive():
        nonlocal delivered
        if not delivered:delivered=True;return {'type':'http.request','body':body,'more_body':False}
        return {'type':'http.disconnect'}
    async def send(message):outgoing.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','headers':[(k.lower().encode(),v.encode()) for k,v in {'Host':'127.0.0.1:8779',**(headers or {})}.items()],'server':('127.0.0.1',8779),'client':('127.0.0.1',12345)}
    await boundary(scope,receive,send);start=next(x for x in outgoing if x['type']=='http.response.start');content=b''.join(x.get('body',b'') for x in outgoing if x['type']=='http.response.body');return start,content
def req(*args,**kwargs):return asyncio.run(http(*args,**kwargs))
check('Odczyt linku wymaga sesji',req('POST','/api/offers/'+offer+'/read-link',b'{}',{'Content-Type':'application/json'})[0]['status']==401)
start,_=req('GET','/');cookie=next(v.decode().split(';')[0] for k,v in start['headers'] if k==b'set-cookie');csrf=json.loads(req('GET','/api/session',headers={'Cookie':cookie})[1])['csrf']
headers={'Cookie':cookie,'Origin':'http://127.0.0.1:8779','X-CSRF-Token':csrf,'Content-Type':'application/json'}
check('Odczyt linku wymaga CSRF',req('POST','/api/offers/'+offer+'/read-link',b'{}',{**headers,'X-CSRF-Token':''})[0]['status']==403)
start,content=req('POST','/api/offers/'+offer+'/read-link',b'{}',headers);http_plan=json.loads(content)
check('Chroniony endpoint przygotowuje podgląd',start['status']==200 and http_plan['text']==TEXT)
payload={'token':http_plan['token'],'revision':http_plan['revision'],'confirmed':True,'text':'Wymagania DEMO po świadomej korekcie użytkownika.'}
start,content=req('POST','/api/offers/read-link/commit',json.dumps(payload).encode(),headers)
check('Użytkownik może poprawić pobraną treść przed zapisem',start['status']==200 and json.loads(content)['state']['offers'][0]['description']==payload['text'])
(ROOT/'app/tests/offer-import-report.json').write_text(json.dumps({'result':'PASS','count':len(checks),'checks':checks,'scope':'Osobna baza DEMO, rzeczywiste API ASGI i zabezpieczenia; pobranie ze stron symulowane.'},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:',len(checks),'kontroli odczytu oferty z linku.')
