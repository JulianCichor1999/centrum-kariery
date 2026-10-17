from datetime import date, datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
import re
import unicodedata
import uuid

WARSAW = ZoneInfo('Europe/Warsaw')
STATUSES = ['Przygotowanie','Wysłana','Rozmowa','Oferta współpracy','Odmowa','Wycofana']
DIRECTIONS = ['Marketing i treści z AI','Automatyzacje i wdrożenia AI']
OFFER_DIRECTIONS = [*DIRECTIONS, 'Inne']
MODES = ['Stacjonarna','Hybrydowa','Zdalna']
CONTRACTS = ['Umowa o pracę','Umowa zlecenie']
KINDS = ['CV','Portfolio','List','Wiadomość','Inny']
FACT_STATUSES = ['Podane przez użytkownika','Sprawdzone w materiale','Do potwierdzenia','W nauce','Wniosek']
FACT_KINDS = ['Umiejętność','Doświadczenie','Edukacja','Projekt','Język','Inne']
ALLOWED_FILES = {'.pdf','.docx','.txt','.md','.json','.png','.jpg','.jpeg','.bin'}

class DomainError(Exception):
    def __init__(self,message,errors=None,status=422):
        super().__init__(message); self.message=message; self.errors=errors or {}; self.status=status

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
def fold(value): return ' '.join(''.join(c for c in unicodedata.normalize('NFD',str(value).replace('ł','l').replace('Ł','L')) if not unicodedata.combining(c)).lower().split())
def check_uuid(value):
    try:
        if str(uuid.UUID(value))!=value: raise ValueError()
    except (ValueError,TypeError,AttributeError): raise DomainError('Nieprawidłowy identyfikator.')

def text(data,key,maxlen=200,required=True):
    value=data.get(key,'')
    if not isinstance(value,str): raise DomainError('Popraw dane.',{key:'Wymagany tekst.'})
    value=value.strip()
    if required and not value or len(value)>maxlen or '\x00' in value: raise DomainError('Popraw dane.',{key:f'Wpisz tekst, maksymalnie {maxlen} znaków.'})
    return value

def choice(data,key,values):
    value=data.get(key)
    if value not in values: raise DomainError('Popraw dane.',{key:'Wybierz dostępną wartość.'})
    return value

def day(value,key='due',optional=False):
    if optional and not value: return ''
    try:
        if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value: raise ValueError()
    except (ValueError,TypeError): raise DomainError('Popraw datę.',{key:'Wymagana data YYYY-MM-DD.'})
    return value

def warsaw(value,key):
    try:
        naive=datetime.strptime(value,'%Y-%m-%dT%H:%M')
        if naive.strftime('%Y-%m-%dT%H:%M')!=value: raise ValueError()
        candidates={naive.replace(tzinfo=WARSAW,fold=n).astimezone(timezone.utc) for n in (0,1) if naive.replace(tzinfo=WARSAW,fold=n).astimezone(timezone.utc).astimezone(WARSAW).replace(tzinfo=None)==naive}
        if len(candidates)!=1: raise ValueError()
        return candidates.pop()
    except (ValueError,TypeError): raise DomainError('Popraw godzinę.',{key:'Wybierz jednoznaczną godzinę w Europe/Warsaw; godziny zmiany czasu mogą nie istnieć lub wystąpić dwukrotnie.'})

def canonical_url(value,key='url'):
    if not value: return None
    try:
        parts=urlsplit(value)
        if len(value)>2000 or parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or any(c.isspace() for c in value): raise ValueError()
        host=parts.hostname.encode('idna').decode('ascii').lower()
        if ':' in host: host=f'[{host}]'
        port=parts.port
        netloc=host+(f':{port}' if port and not ((parts.scheme=='http' and port==80) or (parts.scheme=='https' and port==443)) else '')
        query=sorted((k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('gclid','fbclid'))
        return urlunsplit((parts.scheme,netloc,parts.path.rstrip('/') or '/',urlencode(query),''))
    except (ValueError,UnicodeError): raise DomainError('Popraw adres.',{key:'Wpisz adres HTTP/HTTPS bez loginu i hasła.'})

def offer_values(data):
    result={key:text(data,key,limit,required) for key,limit,required in [('title',180,True),('location',120,True),('description',12000,False),('url',2000,False)]}
    result.update(direction=choice(data,'direction',OFFER_DIRECTIONS),mode=choice(data,'mode',MODES),contract=choice(data,'contract',CONTRACTS),deadline=day(data.get('deadline',''),'deadline',True))
    result['canonical']=canonical_url(result['url']); return result

def profile_values(data):
    email=text(data,'email',254,False)
    if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise DomainError('Popraw e-mail.',{'email':'Wpisz prawidłowy e-mail.'})
    pref=data.get('preferences')
    if not isinstance(pref,dict) or set(pref)!={'directions','locations','contracts','remote'}: raise DomainError('Nieprawidłowe preferencje.')
    for key,allowed in [('directions',DIRECTIONS),('contracts',CONTRACTS)]:
        values=pref[key]
        if not isinstance(values,list) or any(not isinstance(item,str) or item not in allowed for item in values) or len(values)!=len(set(values)): raise DomainError('Nieprawidłowe preferencje.')
    if pref['remote'] not in ('','Cała Polska') or not isinstance(pref['locations'],list) or len(pref['locations'])>30 or any(not isinstance(item,str) or not item.strip() or len(item)>120 for item in pref['locations']): raise DomainError('Nieprawidłowe preferencje.')
    return {'name':text(data,'name',120,False),'email':email,'goal':text(data,'goal',2000,False),'preferences':pref}

def entry_values(data): return {'kind':choice(data,'kind',FACT_KINDS),'content':text(data,'content',5000),'status':choice(data,'status',FACT_STATUSES),'source':text(data,'source',500)}

def material_values(data):
    values={key:text(data,key,limit,required) for key,limit,required in [('title',180,True),('version',30,True),('description',5000,False),('url',2000,False)]}
    values['kind']=choice(data,'kind',KINDS); canonical_url(values['url']); return values

def ai_config(data):
    if not isinstance(data,dict) or set(data)!={'provider','model','enabled'} or data['provider']!='ollama' or type(data['enabled']) is not bool or not isinstance(data['model'],str) or not re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,120}',data['model']) or ':cloud' in data['model']:
        raise DomainError('Nieprawidłowa konfiguracja lokalnego AI.')
    return data

def searches(items):
    if not isinstance(items,list) or len(items)>30: raise DomainError('Maksymalnie 30 zapisanych wyszukiwań.')
    result=[]
    for item in items:
        if not isinstance(item,dict) or set(item)!={'name','url'}: raise DomainError('Nieprawidłowe wyszukiwanie.')
        result.append({'name':text(item,'name',120),'url':text(item,'url',2000)})
        canonical_url(result[-1]['url'])
    return result
