"""Complete CV from an explicitly selected document, with extractive AI priorities.

The model selects existing passages. Names, dates and the career history are never
generated. The user can edit the complete preview before confirming its export.
"""
import re,subprocess,http.client
from . import validation as v

HEADINGS={'profil','profil zawodowy','doswiadczenie','doswiadczenie zawodowe','wyksztalcenie',
          'edukacja','kluczowe kompetencje','umiejetnosci','umiejetnosci dodatkowe informacje',
          'szkolenia','kursy','certyfikaty','projekty','wolontariat','jezyki','jezyki zainteresowania',
          'zainteresowania','dodatkowe informacje'}

def is_heading(line):
    return v.fold(line.strip().strip('#').strip().rstrip(':')) in HEADINGS

def document_blocks(parts):
    """Join wrapped lines without losing bullets, dates or named sections."""
    blocks=[]; current=''; in_header=True; removed_keywords=False
    for part in parts:
        for raw in part['text'].splitlines():
            line=' '.join(raw.replace('\x00','').split())
            if v.fold(line).strip('# :')=='slowa kluczowe':
                removed_keywords=True; break
            if not line:
                if current: blocks.append(current);current=''
                continue
            heading=is_heading(line)
            new_bullet=bool(re.match(r'^[•▪●\-]\s|^o\s',line))
            job=bool(re.search(r'\|\s*\d{2}[./]\d{4}',line))
            label=bool(re.match(r'^[^:]{3,65}:',line)) or v.fold(line).startswith(('studia ','angielski ','polski ','pakiet ms ','windows &','seo i ','chatgpt,','uczestnik ','wolontariat ','wspoltworzenie ','wyrazam zgode','technologie:'))
            if in_header or heading or new_bullet or job or label:
                if current: blocks.append(current);current=''
                blocks.append(line)
                if heading: in_header=False
            elif blocks and (blocks[-1].startswith(('•','▪','●','-','o '))) and not current:
                blocks[-1]+=' '+line
            else:
                current=(current+' '+line).strip()
        if removed_keywords: break
        if current: blocks.append(current);current=''
    if current:blocks.append(current)
    if not blocks or sum(map(len,blocks))<80: raise v.DomainError('CV nie zawiera wystarczającej treści. Dodaj PDF z tekstem, DOCX lub TXT.')
    return blocks,removed_keywords

def build_cv(reader,rows,base_id,extra_ids,offer,provider,model,instruction):
    known={row['id']:row for row in rows}
    if not base_id:
        candidates=[row for row in rows if row['kind']=='CV' and row['fileKey'] and not row['title'].startswith(('Szkic CV AI','CV do oferty'))]
        if len(candidates)!=1: raise v.DomainError('Wybierz CV bazowe w polu „CV bazowe”.')
        base_id=candidates[0]['id']
    v.check_uuid(base_id)
    if base_id not in known or known[base_id]['kind']!='CV' or not known[base_id]['fileKey']: raise v.DomainError('Wybierz zapisany plik CV bazowego, nie sam link.')
    if not isinstance(extra_ids,list) or len(extra_ids)>5 or any(not isinstance(key,str) or key not in known or key==base_id for key in extra_ids) or len(set(extra_ids))!=len(extra_ids): raise v.DomainError('Wybierz do pięciu różnych materiałów portfolio.')
    base=known[base_id]
    if base['title'].startswith(('Raport AI','Szkic CV AI','CV do oferty')): raise v.DomainError('Wybierz oryginalne CV bazowe, nie wcześniejszy wynik AI.')
    parts,warnings,sha,url=reader.read(base)
    if warnings: raise v.DomainError('CV bazowego nie odczytano w całości: '+' '.join(warnings)+' Dodaj pełną wersję tekstową.')
    blocks,removed_keywords=document_blocks(parts)
    candidates=[]; size=0
    for number,block in enumerate(blocks):
        # Contact lines and headings are preserved in the document, not sent for ranking.
        if len(block)<45 or is_heading(block) or '@' in block or re.search(r'https?://|linkedin\.com',block): continue
        for sentence_number,sentence in enumerate(re.split(r'(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])',block),1):
            if len(sentence)<45 or len(sentence)>600 or size+len(sentence)>12000: continue
            candidates.append({'id':f'C{number+1}S{sentence_number}','text':sentence});size+=len(sentence)
    if not candidates: raise v.DomainError('Nie rozpoznano opisów doświadczenia w CV. Sprawdź odczyt dokumentu lub dodaj DOCX/TXT.')
    focus=re.split(r'\bwymagania\s*:',offer['description'],flags=re.I)[-1]
    stop={'przez','ktore','ktory','ktora','ktorym','takze','jednego','jednym','wybran','wymaga','doswia','praca','pracy','przygo','inne','oraz','tego','jest','mojego','swojej'}
    terms={word[:6] for word in re.findall(r'[a-z]{4,}',v.fold(focus)) if word[:6] not in stop}
    candidates.sort(key=lambda row:sum(term in v.fold(row['text']) for term in terms),reverse=True)
    candidates=[{**row,'sourceId':row['id'],'id':f'S{number:02d}'} for number,row in enumerate(candidates[:12],1)]
    inventory=[{'materialId':base_id,'title':base['title'],'version':base['version'],'sha256':sha,'status':'Odczytany','role':'CV bazowe'}]
    projects=[];project_size=0
    for number,key in enumerate(extra_ids,1):
        row=known[key]
        try:
            extra_parts,extra_warnings,extra_sha,extra_url=reader.read(row)
            text='\n'.join(part['text'] for part in extra_parts)
            if extra_warnings or len(text)>5000 or project_size+len(text)>6000: raise ValueError('Materiał nie mieści się w pełnym odczycie (5000 znaków na projekt, 6000 łącznie). Dodaj krótszy opis projektu.')
            projects.append({'id':'P'+str(number),'title':row['title'],'text':text})
            project_size+=len(text)
            inventory.append({'materialId':key,'title':row['title'],'version':row['version'],'sha256':extra_sha,'status':'Odczytany','role':'Portfolio'})
        except (ValueError,OSError,subprocess.TimeoutExpired,http.client.HTTPException) as error:
            inventory.append({'materialId':key,'title':row['title'],'version':row['version'],'status':'Nieodczytany','reason':str(error),'role':'Portfolio'})
    properties={'summaryIds':{'type':'array','items':{'type':'string','enum':[row['id'] for row in candidates]},'maxItems':3,'uniqueItems':True},
                'projectIds':{'type':'array','items':{'type':'string','enum':[row['id'] for row in projects]} if projects else {'type':'string'},'maxItems':min(2,len(projects)),'uniqueItems':True}}
    schema={'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    result=provider.generate(model,instruction,{'position':offer['title'],'requirements':offer['description'],'cvPassages':candidates,'portfolio':projects},schema)
    if not isinstance(result,dict) or set(result)!=set(properties): raise v.DomainError('Model zwrócił nieprawidłowy wybór fragmentów CV. Nic nie zapisano.',status=502)
    def selection(key,known_rows,maximum):
        values=result[key]; allowed={row['id']:row for row in known_rows}
        if not isinstance(values,list) or len(values)>maximum or any(not isinstance(item,str) or item not in allowed for item in values): raise v.DomainError('Model wskazał nieznany fragment CV. Nic nie zapisano.',status=502)
        return [allowed[item] for item in dict.fromkeys(values)]
    summary=selection('summaryIds',candidates,3); selected_projects=selection('projectIds',projects,min(2,len(projects)))
    # Keep the complete original history. Tailored passages are highlights, not new facts.
    body=[]; inserted=False;skip_profile=False;replaced_profile=False
    for block in blocks:
        if is_heading(block):
            skip_profile=False
            if v.fold(block.strip().strip('#').strip().rstrip(':')) in ('profil','profil zawodowy') and summary:
                body.extend(['Profil zawodowy',*[row['text'].lstrip('•▪●- ').strip() for row in summary]])
                inserted=True;skip_profile=True;replaced_profile=True;continue
        elif skip_profile:continue
        if is_heading(block) and not inserted:
            if summary:
                body.extend(['Profil zawodowy',*[row['text'].lstrip('•▪●- ').strip() for row in summary],''])
            inserted=True
        body.append(block)
        if is_heading(block): body.append('')
    if not inserted and summary: body.extend(['','Najważniejsze doświadczenie do tej oferty',*[row['text'] for row in summary]])
    if selected_projects:
        body.extend(['','Materiały portfolio'])
        for row in selected_projects: body.extend([row['title'],row['text'],''])
    draft='\n\n'.join(block for block in body if block)
    if len(draft)>24000: raise v.DomainError('Pełne CV przekracza 24 000 znaków. Wybierz mniej dodatkowych materiałów; nie skracamy historii automatycznie.')
    control=['Odczytano całe CV bazowe. Zachowano historię zatrudnienia, wykształcenie i dane kontaktowe ze źródła.',
             'AI wybrało dosłowne fragmenty do wyróżnienia. Nie dopisało nowych kwalifikacji ani dat.',
             'Przed zapisem sprawdź aktualność danych, układ odczytu PDF i trafność wyróżnień. Treść możesz poprawić poniżej.']
    if removed_keywords:control.append('Pominięto końcowy blok „Słowa kluczowe”; pozostała treść CV została zachowana.')
    if replaced_profile:control.append('Pierwotny profil zawodowy zastąpiono krótkimi cytatami dopasowanymi do oferty. Oryginalne podsumowanie pozostaje w CV bazowym i raporcie źródeł.')
    control.append('AI dobierało podsumowanie z maksymalnie 12 fragmentów znalezionych według słów z wymagań. Trafność doboru wymaga przeglądu; pełna historia pozostała w dokumencie.')
    if any(row['status']=='Nieodczytany' for row in inventory):control.append('Części wskazanych materiałów portfolio nie odczytano. Szczegóły w źródłach.')
    return {'draft':draft,'fullCV':True,'baseMaterialId':base_id,'inventory':inventory,'evidence':[],
            'operations':[],'control':control,'summarySources':summary,'projectSources':selected_projects}, {'base':base,'parts':parts,'portfolio':projects}
