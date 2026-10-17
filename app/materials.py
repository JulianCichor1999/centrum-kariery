"""Odczyt wskazanych materiałów. Linki tylko publiczne HTTPS, bez logowania i cookies."""
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import os
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin

MAX_BYTES = 5 * 1024 * 1024
MAX_WEB_BYTES = 2 * 1024 * 1024
MAX_TEXT = 24000

def public_target(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Odczyt linków wymaga publicznego adresu HTTPS bez loginu i hasła.')
    host = parts.hostname.encode('idna').decode('ascii')
    addresses = list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast for address in addresses):
        raise ValueError('Link do sieci lokalnej lub adresu niepublicznego nie jest odczytywany.')
    return host, addresses[0], (parts.path or '/') + ('?' + parts.query if parts.query else '')

class PublicHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=6, context=ssl.create_default_context()); self.address = address
    def connect(self):
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        try: self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception: sock.close(); raise

def fetch_public(url,allowed_types=('text/html','text/plain'),request_headers=None):
    credential_host=urlsplit(url).hostname
    for _ in range(4):
        host, address, target = public_target(url)
        if request_headers and host!=credential_host: raise ValueError('Przekierowanie z nagłówkami dostępu do innego serwera jest niedozwolone.')
        connection = PublicHTTPS(host, address)
        try:
            connection.request('GET', target, headers={'User-Agent': 'CentrumKariery/1.0', 'Accept': ','.join(allowed_types), 'Accept-Encoding': 'identity',**(request_headers or {})})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location: raise ValueError('Przekierowanie bez adresu docelowego.')
                url = urljoin(url, location); continue
            if response.status != 200: raise ValueError(f'Strona odpowiedziała kodem {response.status}. Dodaj treść jako plik lub opis.')
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity': raise ValueError('Strona wymaga nieobsługiwanego kodowania odpowiedzi.')
            kind = response.getheader('Content-Type', '').lower()
            if kind.split(';')[0].strip() not in allowed_types: raise ValueError('Link nie zawiera obsługiwanego rodzaju treści. Dodaj dokument jako plik.')
            content = response.read(MAX_WEB_BYTES + 1)
            if len(content) > MAX_WEB_BYTES: raise ValueError('Strona przekracza limit 2 MB.')
            charset = re.search(r'charset=([\w-]+)', kind)
            try: text = content.decode(charset.group(1) if charset else 'utf-8', errors='replace')
            except LookupError: text = content.decode('utf-8', errors='replace')
            return text, kind, url, hashlib.sha256(content).hexdigest()
        finally: connection.close()
    raise ValueError('Za dużo przekierowań. Dodaj treść jako plik lub opis.')

class VisibleText(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'header', 'footer', 'svg', 'noscript', 'form'}
    def __init__(self): super().__init__(convert_charrefs=True); self.skip = 0; self.output = []
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.skip += 1
        if not self.skip and tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'tr'): self.output.append('\n')
    def handle_endtag(self, tag):
        if tag in self.SKIP: self.skip = max(0, self.skip - 1)
        if not self.skip and tag in ('p', 'div', 'li', 'tr'): self.output.append('\n')
    def handle_data(self, data):
        if not self.skip: self.output.append(data + ' ')

def web_text(html):
    parser = VisibleText(); parser.feed(html)
    return '\n'.join(line for line in (' '.join(line.split()) for line in ''.join(parser.output).splitlines()) if line)

def fragments(parts, alias, row, sha, url):
    result = []
    for part in parts:
        text = part['text'].strip()
        while text:
            boundary = min(900, len(text))
            if len(text) > boundary:
                last = max(text.rfind('\n', 0, boundary), text.rfind(' ', 0, boundary))
                if last > 400: boundary = last
            excerpt = text[:boundary].strip(); text = text[boundary:].strip()
            if excerpt:
                result.append({'id': f'{alias}-F{len(result)+1}', 'materialId': row['id'], 'title': row['title'], 'version': row['version'], 'kind': row['kind'], 'locator': part['locator'], 'text': excerpt, 'sha256': sha, 'url': url})
    return result

class MaterialReader:
    def __init__(self, files): self.files = Path(files).resolve()
    def read(self, row):
        if row['title'].startswith(('Raport AI', 'Szkic CV AI', 'Szkic wiadomości AI','CV do oferty')):
            raise ValueError('Wcześniejszy wynik AI nie jest pierwotnym dowodem kwalifikacji; użyj oryginalnych materiałów.')
        if row['fileKey']:
            path = self.files / row['fileKey']
            if path.resolve().parent != self.files or path.is_symlink() or not path.is_file(): raise ValueError('Plik jest brakujący lub ma nieprawidłową ścieżkę.')
            if path.stat().st_size > MAX_BYTES: raise ValueError('Odczyt dokumentów obsługuje pliki do 5 MB.')
            if path.suffix.lower() not in ('.pdf', '.docx', '.txt', '.md', '.json'): raise ValueError('Ten format wymaga OCR lub transkrypcji. Dodaj tekst, PDF z tekstem lub DOCX.')
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']: raise ValueError('Plik zmienił się od zapisania. Dodaj poprawną wersję.')
            reply = subprocess.run([sys.executable, '-m', 'app.extract_material', str(path)], cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, close_fds=True)
            if reply.returncode or len(reply.stdout) > 500000: raise ValueError('Nie udało się odczytać dokumentu.')
            data = json.loads(reply.stdout)
            if data.get('error'): raise ValueError(data['error'])
            return data['parts'], data['warnings'], row['sha256'], ''
        if row['url']:
            host = (urlsplit(row['url']).hostname or '').lower()
            if host == 'drive.google.com' or host == 'docs.google.com' or host.endswith('.googleusercontent.com'):
                raise ValueError('Sam link Google Drive nie zawiera tekstu dokumentów. Zaimportuj wybrane pliki w Ustawieniach → Google Drive lub dodaj lokalne pliki do Materiałów; tego linku nie odczytano.')
            text, kind, final_url, sha = fetch_public(row['url'])
            text = web_text(text) if kind.startswith('text/html') else text
            if len(text.strip()) < 40: raise ValueError('Strona nie udostępnia wystarczającej treści tekstowej; może wymagać logowania lub JavaScript.')
            warnings = ['Odczytano tekst wskazanej strony, bez podstron, plików repozytorium i obrazów.']
            if len(text) > MAX_TEXT: warnings.append('Odczyt strony ograniczono do 24 000 znaków.')
            return [{'locator': 'Publiczna strona', 'text': text[:MAX_TEXT]}], warnings, sha, final_url
        if row['description'].strip(): return [{'locator': 'Opis materiału', 'text': row['description']}], ['Odczytano tylko zapisany opis; brak pliku i linku.'], '', ''
        raise ValueError('Brak pliku, linku i opisu do odczytu.')

    def load(self, rows):
        inventory = []; sources = []; links = 0
        for number, row in enumerate(rows, 1):
            item = {'materialId': row['id'], 'title': row['title'], 'version': row['version'], 'status': 'Nieodczytany', 'reason': '', 'fragments': 0, 'analysedFragments': 0}
            try:
                if number > 30: raise ValueError('Limit przeglądu: pierwsze 30 materiałów. Pozostałe wymagają osobnego przeglądu.')
                if row['url'] and not row['fileKey']:
                    links += 1
                    if links > 8: raise ValueError('Limit przeglądu: osiem linków. Dodaj treść jako pliki.')
                parts, warnings, sha, url = self.read(row)
                excerpts = fragments(parts, f'M{number}', row, sha, url)
                sources.extend(excerpts); item.update(status='Częściowo odczytany' if warnings else 'Odczytany', reason=' '.join(warnings), fragments=len(excerpts))
            except (ValueError, OSError, http.client.HTTPException, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                # Brak pliku lub sieci nigdy nie staje się deklaracją odczytania.
                item['reason'] = str(error) if isinstance(error, ValueError) else 'Odczyt nie powiódł się lub przekroczył czas. Dodaj treść jako plik tekstowy.'
                if row['description'].strip() and not row['title'].startswith(('Raport AI', 'Szkic CV AI', 'Szkic wiadomości AI','CV do oferty')):
                    excerpts = fragments([{'locator': 'Opis materiału', 'text': row['description']}], f'M{number}', row, '', '')
                    sources.extend(excerpts); item.update(status='Częściowo odczytany', fragments=len(excerpts)); item['reason'] += ' Dostępny jest tylko zapisany opis.'
            inventory.append(item)
        return {'inventory': inventory, 'sources': sources}
