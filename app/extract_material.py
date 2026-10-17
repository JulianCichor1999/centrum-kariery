"""Odczyt tekstu w osobnym procesie; bez makr, OCR i wykonywania dokumentów."""
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

runtime = Path(__file__).resolve().parents[1] / '.runtime/python'
if runtime.is_dir(): sys.path.insert(0, str(runtime))
MAX_TEXT = 24000
MAX_PAGES = 30

def extract(path):
    parts = []; warnings = []
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted: raise ValueError('PDF jest zaszyfrowany. Dodaj odblokowaną kopię.')
        if len(reader.pages) > MAX_PAGES: warnings.append('Odczyt obejmuje pierwsze 30 stron PDF.')
        empty = 0
        for number, page in enumerate(reader.pages[:MAX_PAGES], 1):
            text = page.extract_text() or ''
            if text.strip(): parts.append({'locator': f'Strona {number}', 'text': text})
            else: empty += 1
        if empty: warnings.append('Niektóre strony nie zawierają tekstu; skany wymagają OCR.')
    elif path.suffix.lower() == '.docx':
        with zipfile.ZipFile(path) as archive:
            if any('vbaProject' in name for name in archive.namelist()): raise ValueError('Dokument z makrami nie jest obsługiwany.')
            names = [name for name in archive.namelist() if name == 'word/document.xml' or name.startswith(('word/header', 'word/footer')) and name.endswith('.xml')]
            if sum(archive.getinfo(name).file_size for name in names) > 8 * 1024 * 1024: raise ValueError('Rozpakowany dokument jest za duży.')
            for name in names:
                raw = archive.read(name)
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('Niedozwolona struktura XML.')
                tree = ET.fromstring(raw); ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                for number, paragraph in enumerate(tree.iter(ns + 'p'), 1):
                    text = ''.join(node.text or '' for node in paragraph.iter(ns + 't'))
                    if text.strip(): parts.append({'locator': ('Akapit ' if name == 'word/document.xml' else 'Nagłówek lub stopka ') + str(number), 'text': text})
    else:
        parts = [{'locator': 'Tekst', 'text': path.read_bytes().decode('utf-8-sig')}]
    remaining = MAX_TEXT; clipped = []
    for part in parts:
        text = part['text'].replace('\x00', '').strip()
        if len(text) > remaining:
            warnings.append('Odczyt ograniczono do 24 000 znaków na materiał.')
            if remaining: clipped.append({**part, 'text': text[:remaining]})
            break
        clipped.append({**part, 'text': text}); remaining -= len(text)
    if not clipped: raise ValueError('Brak tekstu do odczytu. Dla skanu potrzebne jest OCR.')
    return {'parts': clipped, 'warnings': list(dict.fromkeys(warnings))}

if __name__ == '__main__':
    try: result = extract(Path(sys.argv[1]))
    except ValueError as error: result = {'error': str(error)}
    except Exception: result = {'error': 'Nie udało się odczytać dokumentu. Sprawdź plik i dodaj poprawną wersję.'}
    print(json.dumps(result, ensure_ascii=True), flush=True)
