"""Preview a public job posting; no model, account login or page-script execution."""
import base64
from html.parser import HTMLParser
import http.client
import json
import re
import secrets
import threading
import time
from urllib.parse import urlsplit,urljoin,urlencode
from .materials import fetch_public,web_text
from .validation import DomainError,check_uuid,fold,now

PORTAL='rekrutacja.klaster.org.pl'
PUBLIC_BACKEND='https://pgoebowrnqrflqhxenqw.supabase.co'
class PageData(HTMLParser):
    def __init__(self):super().__init__();self.scripts=[];self.structured=[];self.capture=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='script':
            self.capture=attrs.get('type')=='application/ld+json'
            if attrs.get('src'):self.scripts.append(attrs['src'])
    def handle_endtag(self,tag):
        if tag=='script':self.capture=False
    def handle_data(self,data):
        if self.capture:
            try:self.structured.append(json.loads(data))
            except (ValueError,TypeError):pass

def clean(value):
    if not isinstance(value,str):return ''
    return web_text(value) if re.search(r'<[A-Za-z][^>]*>',value) else value.strip()

def read_offer(url,expected_title,fetch=fetch_public):
    html,kind,final,sha=fetch(url)
    parts=urlsplit(final);page=PageData();page.feed(html)
    job=None;method='Dane strukturalne JobPosting'
    if parts.hostname==PORTAL:
        match=re.fullmatch(r'/job/([0-9a-f-]{36})(?:/[^/]*)?/?',parts.path)
        if not match:raise ValueError('Wskaż stronę konkretnej oferty, nie listę ogłoszeń.')
        key=match[1];check_uuid(key)
        assets=[urljoin('https://'+PORTAL+'/',x) for x in page.scripts if re.fullmatch(r'/assets/index-[A-Za-z0-9_-]+\.js',x)]
        if len(assets)!=1:raise ValueError('Portal zmienił sposób udostępniania oferty. Wklej tekst ręcznie.')
        bundle,_,_,_=fetch(assets[0],allowed_types=('application/javascript','text/javascript'))
        if PUBLIC_BACKEND not in bundle:raise ValueError('Portal zmienił publiczne źródło danych. Wklej treść ręcznie.')
        client=None
        for token in re.findall(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',bundle):
            try:
                segment=token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))
                if claims.get('role')=='anon' and claims.get('ref')==urlsplit(PUBLIC_BACKEND).hostname.split('.')[0]:client=token;break
            except (ValueError,TypeError,UnicodeError):continue
        if not client:raise ValueError('Brak publicznej konfiguracji odczytu ogłoszenia. Wklej tekst ręcznie.')
        endpoint=PUBLIC_BACKEND+'/rest/v1/job_postings?'+urlencode({'id':'eq.'+key,'status':'eq.published','select':'id,title,description,requirements,responsibilities,status'})
        content,_,_,sha=fetch(endpoint,allowed_types=('application/json',),request_headers={'apikey':client,'Authorization':'Bearer '+client})
        rows=json.loads(content)
        if not isinstance(rows,list) or len(rows)!=1 or rows[0].get('id')!=key or rows[0].get('status')!='published':raise ValueError('Opublikowane ogłoszenie nie jest dostępne. Nie pobrano danych prywatnych.')
        job=rows[0];method='Publiczne dane opublikowanej oferty portalu Klaster'
    else:
        candidates=[]
        def visit(value,depth=0):
            if depth>8:return
            if isinstance(value,list):
                for child in value[:30]:visit(child,depth+1)
            elif isinstance(value,dict):
                types=value.get('@type',[])
                if types=='JobPosting' or isinstance(types,list) and 'JobPosting' in types:candidates.append(value)
                if '@graph' in value:visit(value['@graph'],depth+1)
        for value in page.structured:visit(value)
        if len(candidates)!=1:raise ValueError('Nie znaleziono jednoznacznej treści ogłoszenia. Strona może wymagać JavaScript lub logowania. Wklej tekst ręcznie w polu Treść i wymagania.')
        job=candidates[0]
    title=clean(job.get('title'));description=clean(job.get('description'))
    if not title or fold(title)!=fold(expected_title):raise ValueError('Tytuł pobranej oferty różni się od zapisanego. Sprawdź link i tytuł przed importem.')
    if len(description)<100:raise ValueError('Źródło nie udostępnia wystarczającej treści konkretnej oferty. Wklej tekst ręcznie.')
    text=description
    for key,label in [('requirements','Wymagania'),('responsibilities','Zakres obowiązków')]:
        value=clean(job.get(key))
        if value and value not in text:text+='\n\n'+label+':\n'+value
    if len(text)>10000:raise ValueError('Pobrana treść przekracza 10 000 znaków. Wklej ręcznie najważniejszą treść bez elementów portalu.')
    return {'title':title,'text':text,'sourceUrl':final,'sha256':sha,'fetchedAt':now(),'method':method}

class OfferImport:
    def __init__(self,store,reader=read_offer):self.store=store;self.reader=reader;self.pending={};self.lock=threading.RLock()
    def preview(self,owner,key):
        check_uuid(key);state=self.store.state();offer=next((x for x in state['offers'] if x['id']==key and not x['archived']),None)
        if not offer or not offer['url']:raise DomainError('Wybierz aktywną ofertę z zapisanym linkiem.')
        try:result=self.reader(offer['url'],offer['title'])
        except (ValueError,UnicodeError,OSError,http.client.HTTPException):raise DomainError('Nie udało się pobrać treści ogłoszenia. Strona może wymagać logowania lub mieć zmieniony format. Otwórz ofertę i wklej treść do pola „Treść i wymagania”.',status=422)
        with self.lock:
            current=time.monotonic()
            for token in list(self.pending):
                if self.pending[token]['owner']==owner or self.pending[token]['expires']<current:self.pending.pop(token)
            if len(self.pending)>=3:raise DomainError('Za dużo oczekujących podglądów ofert.')
            token=secrets.token_urlsafe(32);company=next(x for x in state['companies'] if x['id']==offer['companyId'])
            self.pending[token]={'owner':owner,'expires':current+900,'revision':state['revision'],'offer':offer,'company':company['name'],'source':result}
            return {**result,'token':token,'revision':state['revision'],'offerId':key,'replacesText':bool(offer['description'])}
    def commit(self,owner,token,revision,confirmed,text):
        with self.lock,self.store.lock:
            item=self.pending.get(token)
            if not item or item['owner']!=owner or item['expires']<time.monotonic():raise DomainError('Podgląd oferty wygasł lub został użyty.',status=409)
            if confirmed is not True or revision!=item['revision']:raise DomainError('Potwierdź aktualny podgląd treści.')
            if not isinstance(text,str) or not text.strip() or len(text)>10000:raise DomainError('Treść musi mieć od 1 do 10 000 znaków.')
            offer=item['offer'];data={k:offer[k] for k in ('title','location','direction','mode','contract','url','deadline')};data.update(company=item['company'],description=text,allowSimilar=True)
            if self.store.state()['revision']!=revision:raise DomainError('Baza zmieniła się. Przygotuj nowy podgląd.',status=409)
            self.store.make_backup('przed-odczytem-oferty')
            self.store.mutate('saveOffer',data,offer['id'],offer['rowVersion'],revision,source=item['source'])
            self.pending.pop(token);return self.store.state()
