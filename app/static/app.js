(async function () {
  'use strict';
  const M = window.CareerModel, store = await M.createStore();
  const main = document.getElementById('main'), dialog = document.getElementById('dialog'), body = document.getElementById('dialog-body');
  let screen = 'today', selected = store.state.applications.find(x=>!x.archived)?.id || '', selectedOffer = store.state.offers.find(x=>!x.archived)?.id || '', detailTab = 'overview', opener, onSubmit;
  let filters = { direction: '', location: '', mode: '', contract: '' }, query = '', planFilter = 'open', appFilter = '';
  let aiStatus=null, aiPreview=null, aiBusy=false, aiError='', aiQuery='', cvBase='', cvExtras=[];
  let driveStatus=null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const button = (label, action, key = '', primary = false) => `<button type="button" class="cd-button${primary ? ' cd-primary' : ''}" data-action="${action}" data-key="${esc(key)}">${esc(label)}</button>`;
  const nav = (label, name) => `<button type="button" class="cd-button" data-screen="${name}">${esc(label)}</button>`;
  const heading = (title, subtitle, action = '') => `<div class="cd-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${action}</div>`;
  const empty = (title, subtitle, action = '') => `<div class="cd-state"><h2>${esc(title)}</h2><p>${esc(subtitle)}</p>${action}</div>`;
  const panel = (title, content) => `<section class="cd-side-panel"><h2>${esc(title)}</h2>${content}</section>`;
  const date = value => value ? new Intl.DateTimeFormat('pl-PL', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Europe/Warsaw' }).format(new Date(`${value}T12:00:00Z`)) : 'Brak terminu';
  const time = value => `${date(value.slice(0, 10))}, ${value.slice(11)} (Europe/Warsaw)`;
  const stamp = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Warsaw' }).format(new Date(value));
  const appName = key => esc(store.applicationLabel(key));
  const options = (values, current = '', blank = '') => `${blank ? `<option value="">${esc(blank)}</option>` : ''}${values.map(item => `<option value="${esc(typeof item === 'string' ? item : item.id)}"${(typeof item === 'string' ? item : item.id) === current ? ' selected' : ''}>${esc(typeof item === 'string' ? item : item.label)}</option>`).join('')}`;
  const field = (name, label, value = '', type = 'text', required = false, max = 200) => `<div class="form-field"><label for="f-${name}">${esc(label)}${required ? ' *' : ''}</label><input class="cd-field" id="f-${name}" name="${name}" type="${type}" value="${esc(value)}"${required ? ' required' : ''} maxlength="${max}" aria-describedby="err-${name}"><p class="field-error" id="err-${name}" hidden></p></div>`;
  const textarea = (name, label, value = '', required = false, max = 5000) => `<div class="form-field"><label for="f-${name}">${esc(label)}${required ? ' *' : ''}</label><textarea class="cd-field" id="f-${name}" name="${name}" rows="4"${required ? ' required' : ''} maxlength="${max}" aria-describedby="err-${name}">${esc(value)}</textarea><p class="field-error" id="err-${name}" hidden></p></div>`;
  const select = (name, label, values, current = '', blank = '') => `<div class="form-field"><label for="f-${name}">${esc(label)}</label><select class="cd-field" name="${name}" id="f-${name}" aria-describedby="err-${name}">${options(values, current, blank)}</select><p class="field-error" id="err-${name}" hidden></p></div>`;
  const appSelect = key => select('applicationId', 'Powiązana aplikacja', store.state.applications.map(item => ({ id: item.id, label: store.applicationLabel(item.id) })), key, 'Bez aplikacji');
  const currentApp = () => store.state.applications.find(item => item.id === selected);
  const currentOffer = () => screen === 'offer' ? store.find('offers', selectedOffer) : store.offer(currentApp());
  function announce(message) { const notice = document.getElementById('notice'); notice.textContent = message; notice.hidden = false; }
  function navigate(name, key) {
    document.getElementById('notice').hidden=true;
    screen = name;
    if (name === 'detail') { selected = key || selected; detailTab = 'overview'; }
    if (name === 'offer') selectedOffer = key || selectedOffer;
    document.querySelector('.cd-shell').classList.remove('cd-nav-open'); document.getElementById('menu').setAttribute('aria-expanded', 'false');
    render(); main.focus(); window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function offerRows(items) {
    return items.filter(item=>!item.archived).map(item => `<article class="cd-offer"><div><h3>${esc(item.title)}</h3><p class="cd-muted cd-small">${esc(store.company(item).name)}</p><div class="cd-meta"><span>${esc(item.location)} · ${esc(item.mode)}</span><span>${esc(item.contract)}</span></div><p class="cd-small">${esc(item.direction)}</p><p class="cd-small cd-muted">Kompetencje do sprawdzenia${item.deadline && item.deadline < M.today() ? ' · Termin oferty minął' : ''}</p></div>${button('Zobacz ofertę', 'offer', item.id)}</article>`).join('');
  }
  function taskRows(items) {
    items=items.filter(item=>!item.archived);
    return items.length ? items.map(item => `<article class="task-row${item.done ? ' completed' : ''}"><label class="task-check"><input type="checkbox" data-task="${item.id}"${item.done ? ' checked' : ''}><span class="sr-only">${item.done ? 'Wznów' : 'Ukończ'} zadanie: ${esc(item.title)}</span></label><div class="task-copy"><h3>${esc(item.title)}</h3><p class="cd-small ${!item.done && item.due < M.today() ? 'late' : 'cd-muted'}">${date(item.due)}${!item.done && item.due < M.today() ? ' · Zaległe' : ''}${item.done ? ' · Ukończone' : ''}</p><p class="cd-small cd-muted">${appName(item.applicationId)}</p><div class="cd-actions">${button('Edytuj', 'edit-task', item.id)}${button('Archiwizuj', 'delete-task', item.id)}</div></div></article>`).join('') : '<p class="cd-muted">Brak zadań w tym widoku.</p>';
  }
  function eventRows(items) {
    items=items.filter(item=>!item.archived);
    return items.length ? items.map(item => `<article class="cd-detail"><h3>${esc(item.title)}</h3><p class="cd-small">${time(item.start)} – ${esc(item.end.slice(0, 10) === item.start.slice(0, 10) ? item.end.slice(11) : time(item.end))}</p><p class="cd-muted cd-small">${appName(item.applicationId)}</p><p class="cd-small">${esc(item.place || 'Miejsce do uzupełnienia')}</p><div class="cd-actions">${button('Edytuj termin', 'edit-event', item.id)}${button('Archiwizuj', 'delete-event', item.id)}</div></article>`).join('') : '<p class="cd-muted">Brak rozmów i spotkań w tym widoku.</p>';
  }
  function todayView() {
    const s = store.state, tasks = s.tasks.filter(item => !item.archived && !item.done && item.due <= M.today()).sort((a, b) => a.due.localeCompare(b.due));
    const next = s.events.filter(item => !item.archived && M.warsawTime(item.start) >= Date.now()).sort((a, b) => a.start.localeCompare(b.start))[0];
    return heading('Dzisiaj', `${date(M.today())} · wybierz kolejny krok w poszukiwaniu pracy`) + `<div class="cd-summary"><span><strong>${s.offers.filter(x=>!x.archived).length}</strong> ofert</span><span><strong>${s.applications.filter(x=>!x.archived).length}</strong> aplikacje</span><span><strong>${tasks.length}</strong> zadań na dziś i zaległych</span></div><div class="cd-columns"><div><section class="cd-priority"><p class="cd-kicker">Najbliższy krok</p><h2>${tasks.length ? esc(tasks[0].title) : 'Przejrzyj oferty w obu kierunkach'}</h2><p>Marketing i treści z AI oraz automatyzacje. Porównaj wymagania z własnym profilem, zanim przygotujesz dokument.</p>${nav('Przejrzyj oferty', 'offers')}</section><section class="cd-section"><div class="cd-section-head"><h2>Oferty do przejrzenia</h2>${nav('Wszystkie oferty', 'offers')}</div>${offerRows(s.offers.filter(x=>!x.archived).slice(0, 3)) || empty('Nie ma ofert', 'Dodaj link i treść znalezionej oferty.', button('Dodaj ofertę', 'add-offer'))}</section><section class="cd-section"><div class="cd-section-head"><h2>Na dziś i zaległe</h2>${button('Dodaj zadanie', 'add-task')}</div>${taskRows(tasks)}</section></div><aside class="cd-aside">${panel('Najbliższa rozmowa', next ? `<p class="cd-time">${esc(next.start.slice(11))}</p><p>${date(next.start.slice(0, 10))}</p><p class="cd-small cd-muted">${appName(next.applicationId)}</p><p class="cd-small">Europe/Warsaw</p><div class="cd-actions">${nav('Otwórz plan', 'plan')}</div>` : '<p class="cd-muted">Nie ma zaplanowanej rozmowy.</p>')}${panel('Do uzupełnienia', '<p class="cd-small">Uzupełnij profil wpisami z CV i dowodami projektów. Zapisanie pliku w bibliotece nie oznacza wykonania analizy AI.</p><div class="cd-actions">' + nav('Zobacz profil', 'profile') + '</div>')}${panel('Asystent AI', '<p class="cd-small">Lokalny model można włączyć w ustawieniach. Analizuje zapisane dane. Treść oferty można pobrać z jej linku po sprawdzeniu podglądu. Poczta nie jest połączona.</p><div class="cd-actions">' + nav('Otwórz asystenta', 'assistant') + '</div>')}</aside></div>`;
  }
  function offersView() {
    const locations = [...new Set(store.state.offers.filter(item=>!item.archived).map(item => item.location))].sort();
    const filtered = store.state.offers.filter(item => !item.archived && Object.entries(filters).every(([key, value]) => !value || item[key] === value));
    return heading('Oferty', 'Twoje kierunki: marketing i treści z AI oraz automatyzacje.', button('Dodaj ofertę', 'add-offer', '', true)) + `<section class="cd-detail"><div class="cd-section-head"><h2>Zapisane wyszukiwania</h2>${button('Zapisz wyszukiwanie','save-search')}</div><p class="cd-small cd-muted">Otwórz wyniki portalu, a wybrane oferty zapisz poniżej. Nie pobieramy wyników automatycznie.</p>${store.state.savedSearches.map((item,index)=>`<div class="archive-row"><a class="cd-button" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.name)}</a>${button('Usuń odnośnik','remove-search',String(index))}</div>`).join('')}</section><div class="cd-filters">${[['direction', 'Kierunek', M.DIRECTIONS], ['location', 'Lokalizacja', locations], ['mode', 'Tryb pracy', M.MODES], ['contract', 'Umowa', M.CONTRACTS]].map(([key, label, values]) => `<label for="filter-${key}">${label}<select class="cd-field" id="filter-${key}" data-filter="${key}">${options(values, filters[key], 'Wszystkie')}</select></label>`).join('')}</div><div class="cd-section-head"><p class="cd-small cd-muted" aria-live="polite">Wyniki: ${filtered.length} z ${store.state.offers.filter(item=>!item.archived).length} ofert</p>${button('Wyczyść filtry', 'clear-filters')}</div>${filtered.length ? offerRows(filtered) : empty('Brak pasujących ofert', 'Zmień lub wyczyść filtry, aby zobaczyć pozostałe oferty.', button('Wyczyść filtry', 'clear-filters'))}`;
  }
  function offerView() {
    const item = currentOffer(), app = store.state.applications.find(record => record.offerId === item.id);
    return heading(item.title, `${store.company(item).name} · oferta`, button('Edytuj ofertę', 'edit-offer', item.id)) + `<div class="cd-actions spaced">${button(item.archived?'Przywróć ofertę':'Archiwizuj ofertę',item.archived?'unarchive':'archive-offer',item.id)}</div><div class="cd-columns spaced"><div><section class="cd-detail"><h2>Warunki i opis</h2><dl><dt>Lokalizacja</dt><dd>${esc(item.location)}</dd><dt>Tryb</dt><dd>${esc(item.mode)}</dd><dt>Umowa</dt><dd>${esc(item.contract)}</dd><dt>Kierunek</dt><dd>${esc(item.direction)}</dd><dt>Termin</dt><dd>${date(item.deadline)}${item.deadline && item.deadline < M.today() ? ' · Termin minął' : ''}</dd><dt>Źródło</dt><dd>${item.url ? `<span class="long-text">${esc(item.url)}</span>` : 'Brak linku — wpis ręczny'}</dd></dl><p class="preserve">${esc(item.description || 'Treść oferty nie została dodana.')}</p>${item.url?`<div class="cd-actions">${button('Pobierz treść z linku','offer-read-link',item.id)}</div>`:''}${item.url && !new URL(item.url).hostname.endsWith('example.com') ? `<div class="cd-actions"><a class="cd-button" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Otwórz źródło w nowej karcie</a></div>` : ''}</section><div class="cd-notice"><strong>Dopasowanie wymaga sprawdzenia</strong>Nie wykonano analizy AI. Sam kierunek, miasto i rodzaj umowy nie potwierdzają kompetencji.</div></div><aside>${panel('Kolejny krok', `<p class="cd-small">${app ? 'Ta oferta ma już jedną powiązaną aplikację.' : 'Utwórz aplikację, aby powiązać zadania, notatki i materiały.'}</p><div class="cd-actions">${button(app ? 'Otwórz aplikację' : 'Utwórz aplikację', app ? 'detail' : 'create-application', app ? app.id : item.id, true)}</div>`)}</aside></div>`;
  }
  function applicationsView() {
    const items = store.state.applications.filter(item => !item.archived && (!appFilter || item.status === appFilter));
    return heading('Aplikacje', 'Jedna oferta, jedna historia i powiązane materiały.', nav('Wybierz ofertę', 'offers')) + `<div class="cd-filters"><label for="app-filter">Status<select class="cd-field" id="app-filter">${options(M.STATUSES, appFilter, 'Wszystkie')}</select></label></div>${items.length ? `<table class="cd-table"><caption class="sr-only">Zapisane aplikacje</caption><thead><tr><th scope="col">Stanowisko i firma</th><th scope="col">Status</th><th scope="col">Otwartych zadań</th><th scope="col">Szczegóły</th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${esc(store.offer(item).title)}</strong><p class="cd-muted">${esc(store.company(store.offer(item)).name)}</p></td><td data-label="Status">${esc(item.status)}</td><td data-label="Otwarte zadania">${store.state.tasks.filter(task => !task.archived && task.applicationId === item.id && !task.done).length}</td><td>${button('Otwórz aplikację', 'detail', item.id)}</td></tr>`).join('')}</tbody></table>` : empty('Brak aplikacji w tym widoku', 'Utwórz aplikację z oferty lub zmień filtr statusu.', nav('Przejrzyj oferty', 'offers'))}`;
  }
  function linkedMaterials(key) { return store.state.links.filter(item => item.applicationId === key).map(item => store.find('materials', item.materialId)); }
  function materialRows(items) {
    return items.length ? items.map(item=>`<article class="cd-detail"><h3>${esc(item.title)}</h3><p class="cd-meta"><span>${esc(item.kind)}</span><span>Wersja ${esc(item.version)}</span><span>${item.fileKey ? esc(item.fileName) : item.url ? 'Odnośnik' : 'Opis'}</span></p><p class="preserve cd-small">${esc(item.description)}</p><div class="cd-actions">${item.fileKey ? `<a class="cd-button" href="/api/materials/${encodeURIComponent(item.id)}/download" download>Pobierz plik</a>` : ''}${item.url ? `<a class="cd-button" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Otwórz odnośnik</a>` : ''}</div></article>`).join('') : '<p class="cd-muted">Brak materiałów. Dodaj plik, odnośnik albo opis wersji.</p>';
  }

  function detailView() {
    const app = currentApp(); if (!app) return empty('Wybierz aplikację', 'Utwórz aplikację z zapisanej oferty.', nav('Otwórz oferty', 'offers'));
    const item = store.offer(app);
    let content;
    if (detailTab === 'overview') {
      content = `<div class="cd-columns"><div><section class="cd-detail"><h2>Podsumowanie</h2><p>${esc(item.location)} · ${esc(item.mode)} · ${esc(item.contract)}</p><p class="cd-small cd-muted">Status: ${esc(app.status)}. Nie połączono poczty ani portalu rekrutacyjnego.</p><div class="cd-actions">${button('Zobacz ofertę', 'offer', item.id)}${button('Zmień status', 'status', app.id)}${button('Archiwizuj aplikację','archive-application',app.id)}</div></section><section class="cd-section"><div class="cd-section-head"><h2>Powiązane zadania</h2>${button('Dodaj zadanie', 'add-task', app.id)}</div>${taskRows(store.state.tasks.filter(task => task.applicationId === app.id))}</section><section class="cd-section"><div class="cd-section-head"><h2>Rozmowy i terminy</h2>${button('Dodaj rozmowę', 'add-event', app.id)}</div>${eventRows(store.state.events.filter(event => event.applicationId === app.id))}</section><section class="cd-section"><div class="cd-section-head"><h2>Notatki</h2>${button('Dodaj notatkę', 'add-note', app.id)}</div>${store.state.notes.filter(note => !note.archived && note.applicationId === app.id).map(note => `<article class="cd-detail"><p class="preserve">${esc(note.text)}</p><p class="cd-small cd-muted">${stamp(note.at)}</p>${button('Archiwizuj notatkę', 'delete-note', note.id)}</article>`).join('') || '<p class="cd-muted">Brak notatek.</p>'}</section></div><aside>${panel('Przygotowanie aplikacji', '<p class="cd-small">Wybierz ofertę i CV bazowe, popraw podgląd i zapisz dokumenty. Nie musisz przepisywać historii zatrudnienia do profilu.</p><div class="cd-actions">' + button('Przygotuj z CV MASTER AI', 'assistant', app.id, true) + '</div>')}${panel('Wersje materiałów', `<p class="cd-small">Przypiętych: ${linkedMaterials(app.id).length}. To odwołania do biblioteki, bez kopii.</p><div class="cd-actions">${button('Zobacz dokumenty', 'documents', app.id)}</div>`)}</aside></div>`;
    } else if (detailTab === 'match') {
      content = `<div class="cd-notice"><strong>Nie wykonano analizy tej oferty</strong>Treść została wpisana ręcznie lub zaimportowana. Lokalną analizę możesz uruchomić w CV MASTER AI. Nie ma oceny ATS ani procentu szans.</div><section class="cd-detail"><h2>Wymagania do analizy</h2><p class="preserve">${esc(item.description || 'Uzupełnij treść oferty.')}</p><h3>Znane deklaracje</h3><p>Sprawdź aktualne wpisy ze źródłami w Moim profilu. Wymagania tej oferty nie zostały jeszcze porównane przez AI.</p></section>${button('Zobacz proces dopasowania', 'assistant', app.id)}`;
    } else if (detailTab === 'documents') {
      content = `<div class="cd-section-head"><h2>Przypięte wersje</h2>${button('Przypnij materiał', 'pin-material', app.id)}</div>${materialRows(linkedMaterials(app.id))}<div class="cd-notice"><strong>Wersję wybierasz samodzielnie</strong>Importowany plik jest zachowany bez automatycznej analizy. Wyniki AI mają własny raport i oznaczenie szkicu. Nową wersję dodaje się osobno; powiązanie aplikacji pozostaje przy wybranej wersji.</div>`;
    } else {
      content = `<ol class="cd-timeline">${[...app.history].reverse().map(item => `<li><p>${esc(item.text)}</p><p class="cd-small cd-muted">${stamp(item.at)}</p></li>`).join('')}</ol>`;
    }
    return heading(item.title, `${store.company(item).name} · ${app.status} · aplikacja`) + `<div class="cd-tabs" role="group" aria-label="Sekcje aplikacji">${[['overview', 'Przegląd'], ['match', 'Dopasowanie'], ['documents', 'Dokumenty'], ['history', 'Historia']].map(([key, label]) => `<button type="button" data-tab="${key}" aria-pressed="${detailTab === key}">${label}</button>`).join('')}</div>${content}`;
  }
  function planView() {
    const tasks = store.state.tasks.filter(item => planFilter === 'all' || (planFilter === 'done' ? item.done : !item.done)).sort((a, b) => a.due.localeCompare(b.due));
    const events = [...store.state.events].sort((a, b) => a.start.localeCompare(b.start));
    return heading('Plan', 'Zadania i rozmowy · wszystkie godziny w Europe/Warsaw.', `<div class="cd-actions">${button('Dodaj zadanie', 'add-task', '', true)}${button('Dodaj rozmowę', 'add-event')}</div>`) + `<div class="cd-columns"><section class="cd-section"><div class="cd-section-head"><h2>Zadania</h2><label for="plan-filter" class="cd-small">Pokaż <select id="plan-filter" class="cd-field">${options([{ id: 'open', label: 'Otwarte' }, { id: 'done', label: 'Ukończone' }, { id: 'all', label: 'Wszystkie' }], planFilter)}</select></label></div>${taskRows(tasks)}</section><section class="cd-section"><h2>Rozmowy i spotkania</h2><div class="spaced">${eventRows(events)}</div></section></div>`;
  }
  function profileView() {
    const profile=store.state.profile, pref=profile.preferences, entries=store.state.entries.filter(item=>!item.archived);
    return heading('Mój profil','Wspólny MASTER PROFILE: każda informacja ma źródło i stan.',button('Edytuj profil','edit-profile')) + `<div class="cd-columns"><div><section class="cd-detail"><h2>Cel i preferencje</h2><p>${esc(profile.goal || 'Uzupełnij swój cel zawodowy.')}</p><dl><dt>Imię i nazwisko</dt><dd>${esc(profile.name || 'Do uzupełnienia')}</dd><dt>E-mail</dt><dd>${esc(profile.email || 'Do uzupełnienia')}</dd><dt>Kierunki</dt><dd>${esc(pref.directions.join('; '))}</dd><dt>Umowy</dt><dd>${esc(pref.contracts.join('; '))}</dd><dt>Miasta i okolice</dt><dd>${esc(pref.locations.join(', '))}</dd><dt>Zdalnie</dt><dd>${esc(pref.remote)}</dd></dl></section><section class="cd-section"><div class="cd-section-head"><h2>Informacje zawodowe</h2>${button('Dodaj wpis ze źródłem','add-entry')}</div>${entries.length ? entries.map(item=>`<article class="cd-detail"><h3>${esc(item.kind)}</h3><p class="cd-tag">${esc(item.status)}</p><p class="preserve">${esc(item.content)}</p><p class="cd-small cd-muted">Źródło: ${esc(item.source)}</p><div class="cd-actions">${button('Edytuj wpis','edit-entry',item.id)}${button('Archiwizuj wpis','archive-entry',item.id)}</div></article>`).join('') : '<p class="cd-muted">Nie ma jeszcze wpisów. Dodaj informacje z CV wraz ze źródłem; nie dopisujemy nieznanych faktów.</p>'}</section></div><aside>${panel('CV i dowody','<p class="cd-small">Dodaj istniejące CV jako plik w Materiałach. Plik zostanie zachowany; jego treści nie analizujemy automatycznie. Generator CV odczyta dokument po kliknięciu „Przygotuj CV”; nie musisz przepisywać informacji do profilu.</p><div class="cd-actions">'+nav('Otwórz materiały','materials')+'</div>')}${panel('Zasada CV MASTER AI','<p class="cd-small">Informacje do potwierdzenia i wnioski nie stają się faktami. Umiejętność w nauce zachowuje ten stan. Lokalny asystent dobiera fakty do szkicu. Zapis tekstu, PDF i DOCX wymaga sprawdzenia oraz zatwierdzenia.</p><div class="cd-actions"><a class="cd-button" href="/api/export/profile" download>Eksport MASTER PROFILE</a></div>')}</aside></div>`;
  }

  function materialsView() {
    return heading('Materiały','Lokalne pliki, odnośniki i niezmienne wersje. Drive nie jest połączony.',button('Dodaj materiał','add-material','',true)) + `<div class="cd-actions spaced">${nav('Przegląd materiałów z AI','assistant')}</div>` + materialRows(store.state.materials) + `<div class="cd-notice"><strong>Wersje są niezmienne</strong>Zmiana dokumentu oznacza dodanie nowej wersji. Przypięta wcześniej wersja pozostaje przy aplikacji. Import pliku nie oznacza analizy jego treści przez AI.</div>`;
  }
  function assistantView() {
    const app=currentApp(), offer=app?store.offer(app):store.find('offers',selectedOffer);
    const originals=store.state.materials.filter(row=>row.kind==='CV'&&row.fileKey&&!/^(Szkic CV AI|CV do oferty)/.test(row.title));
    if(!originals.some(row=>row.id===cvBase)) cvBase=originals[0]?.id||'';
    const extras=store.state.materials.filter(row=>['Portfolio','Inny'].includes(row.kind)&&!row.title.startsWith('Raport AI'));
    const ready=aiStatus?.available&&!aiBusy;
    const runButton=(label,mode)=>`<button type="button" class="cd-button${mode==='cv'?' cd-primary':''}" data-action="ai-run" data-key="${mode}"${ready&&(mode==='command'||mode==='search'||app||(mode==='cv'&&offer))&&(mode!=='cv'||cvBase)?'':' disabled'}>${label}</button>`;
    return heading('CV do oferty','Wybierz ofertę i CV bazowe. Przygotuj, popraw, zapisz.',button('Sprawdź połączenie','ai-status'))+
      `<section class="cd-detail"><div class="cd-grid2"><label class="context-label" for="ai-context">Oferta<select class="cd-field" id="ai-context"${aiBusy?' disabled':''}>${options(store.state.offers.filter(row=>!row.archived).map(row=>({id:row.id,label:row.title+' · '+store.company(row).name})),offer?.id||'','Wybierz ofertę')}</select></label><label class="context-label" for="cv-base">CV bazowe<select class="cd-field" id="cv-base"${aiBusy?' disabled':''}>${options(originals.map(row=>({id:row.id,label:row.title+' · wersja '+row.version})),cvBase,'Wybierz CV')}</select></label></div><div class="cd-actions spaced">${button('Dodaj ofertę','add-offer')}${button('Dodaj CV','add-cv')}</div>${!originals.length?'<p class="cd-notice">Dodaj swoje CV jako PDF z tekstem, DOCX lub TXT. Nie musisz przepisywać doświadczenia do profilu.</p>':''}<details class="cd-inline-details"><summary>Portfolio — dodatkowe materiały (${cvExtras.length})</summary><p class="cd-small">Opcjonalnie wybierz do 5 krótkich opisów projektów. AI może dołączyć do CV maksymalnie 2. Skany, obrazy i nagrania wymagają najpierw odczytu do tekstu.</p>${extras.length?extras.map(row=>`<label class="confirm-check"><input type="checkbox" data-cv-extra="${esc(row.id)}"${cvExtras.includes(row.id)?' checked':''}${aiBusy?' disabled':''}><span>${esc(row.title)} · wersja ${esc(row.version)}</span></label>`).join(''):'<p class="cd-small">Nie dodano materiałów portfolio.</p>'}</details><div class="cd-actions spaced">${runButton('Przygotuj CV','cv')}${offer?.url?button('Pobierz treść z linku','offer-read-link',offer.id):''}</div><p class="cd-small spaced">${aiStatus?.available?'Lokalny model: '+esc(aiStatus.model)+'. Pełne CV bazowe pozostaje w szkicu; AI wybiera fragmenty do wyróżnienia.':esc(aiStatus?.error||'Włącz lokalne AI w Ustawieniach, aby przygotować CV.')} Przygotowanie dla nowej oferty rozpoczyna aplikację w statusie „Przygotowanie”. Zapis dokumentów wymaga Twojego potwierdzenia.</p>${!aiStatus?.available?nav('Otwórz ustawienia','settings'):''}</section>
      ${aiBusy?'<p class="spaced" role="status">Trwa odczyt materiałów i przygotowanie podglądu…</p>':''}${aiError?`<p class="field-error spaced" role="alert" tabindex="-1">${esc(aiError)}</p>`:''}${aiPreviewView()}
      <details class="cd-inline-details"><summary>Dodatkowe narzędzia</summary><div class="cd-actions spaced">${runButton('Analizuj ofertę i wpisy profilu','analysis')}${runButton('Przygotuj wiadomość z profilu','message')}${runButton('Przejrzyj materiały','materials')}</div><section class="cd-section ai-command"><h2>Polecenie do bazy</h2><label for="ai-query">Twoje polecenie</label><textarea class="cd-field" id="ai-query" rows="3" maxlength="2500"${aiBusy?' disabled':''}>${esc(aiQuery)}</textarea><div class="cd-actions">${runButton('Przygotuj podgląd polecenia','command')}${runButton('Znajdź w bazie','search')}</div><p class="cd-small">Dodawanie zadań i notatek z osobnym potwierdzeniem. Bez wysyłki wiadomości. Analiza i wiadomość korzystają z wpisów profilu; generator CV korzysta z wybranego dokumentu.</p></section></details>`;
  }
  function materialReviewView(p) {
    const recommended=[...new Map(p.findings.filter(row=>row.recommended).map(row=>[row.source.materialId,row.source.title+' · wersja '+row.source.version])).values()];
    return `<h3>Zakres przeglądu</h3><p>Materiały: ${p.coverage.materials}. Analiza objęła ${p.coverage.analysedFragments} z ${p.coverage.fragments} odczytanych fragmentów.</p>${p.warnings.map(text=>`<div class="cd-notice"><strong>Ograniczenie przeglądu</strong>${esc(text)}</div>`).join('')}<h3>Odczyt materiałów</h3>${p.inventory.map(item=>`<article class="cd-detail"><h3>${esc(item.title)} · wersja ${esc(item.version)}</h3><p class="cd-tag">${esc(item.status)}</p><p class="cd-small">Analiza: ${item.analysedFragments} z ${item.fragments} fragmentów</p>${item.reason?`<p class="cd-small cd-muted preserve">${esc(item.reason)}</p>`:''}</article>`).join('')}<h3>Źródła przydatne do aplikacji</h3><p class="cd-small cd-muted">Cytaty pochodzą z materiałów użytkownika. Ich odczyt nie potwierdza niezależnie kwalifikacji.</p>${p.findings.length?p.findings.map(row=>`<article class="cd-detail"><h3>${esc(row.source.title)} · wersja ${esc(row.source.version)}</h3><p class="cd-small cd-muted">${esc(row.source.locator)} · ${esc(row.source.id)}</p><p class="preserve">${esc(row.source.text)}</p>${row.requirements.length?`<h3>Wymagania z ogłoszenia</h3><ul>${row.requirements.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`:''}<p class="cd-small preserve">Wniosek AI — do oceny: ${esc(row.comment)}</p>${row.source.url?`<a class="cd-button" href="${esc(row.source.url)}" target="_blank" rel="noopener noreferrer">Otwórz źródło</a>`:''}</article>`).join(''):'<p>Model nie wskazał przydatnych fragmentów. Sprawdź zakres odczytu i brakujące materiały.</p>'}<h3>Materiały proponowane do dołączenia</h3>${recommended.length?`<ul>${recommended.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`:'<p>Brak rekomendowanych materiałów w tej analizie.</p>'}<h3>Proponowane poprawki CV — do oceny</h3><ul>${p.cvSuggestions.map(text=>`<li>${esc(text)}</li>`).join('')}</ul><h3>Następne działania</h3><ul>${p.nextActions.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`;
  }
  function aiPreviewView() {
    const p=aiPreview;
    if(!p || p.applicationId!==(currentApp()?.id||'')) return '';
    let content=p.clarification?`<p class="field-error">${esc(p.clarification)}</p>`:'';
    if(p.materialsReview) content+=materialReviewView(p);
    if(p.matches) content+=p.matches.map(row=>`<article class="cd-detail"><h3>${esc(row.requirement)}</h3><p class="cd-tag">${esc(row.assessment)}</p>${row.evidence.map(fact=>`<p class="preserve">${esc(fact.content)}</p><p class="cd-small cd-muted">${esc(fact.status)} · ${esc(fact.source)}</p>`).join('')}<p class="cd-small">Wniosek AI — do oceny: ${esc(row.comment)}</p></article>`).join('')+`<h3>Proponowane działania</h3><ul>${p.nextActions.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`;
    if(p.fullCV) content+=`<label for="ai-draft">Treść CV — możesz ją poprawić</label><textarea class="cd-field cv-editor spaced" id="ai-draft" rows="24" maxlength="24000"${p.saved?' readonly':''}>${esc(p.draft)}</textarea><details class="cd-inline-details"><summary>Uwagi i wykorzystane źródła</summary><ul>${p.control.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>${p.inventory.map(row=>`<p>${esc(row.title)} · ${esc(row.version)} · ${esc(row.status)}${row.reason?' — '+esc(row.reason):''}</p>`).join('')}<p class="cd-small">Źródła są deklaracjami z Twoich dokumentów. Twoje poprawki zostaną zapisane jako treść zatwierdzona przez użytkownika.</p></details>`;
    else if(p.draft) content+=`<p class="preserve spaced" id="ai-draft">${esc(p.draft)}</p><h3>Kontrola źródeł</h3><ul>${p.control.map(text=>`<li>${esc(text)}</li>`).join('')}</ul><details><summary>Wpisy wykorzystane w szkicu</summary>${p.evidence.map(f=>`<p>${esc(f.content)} · ${esc(f.status)} · ${esc(f.source)}</p>`).join('')}</details>`;
    if(p.operations?.length) content+=`<ul>${p.operations.map(op=>`<li>${op.action==='saveTask'?'Nowe zadanie':'Nowa notatka'}: ${esc(op.data.title||op.data.text)}${op.data.due?' · '+esc(op.data.due):''}</li>`).join('')}</ul>`;
    if(p.found) content+=p.found.length?p.found.map(row=>`<article class="cd-detail"><p class="preserve">${esc(row.text)}</p><p class="cd-small cd-muted">Rekord: ${esc(row.type)}${row.status?' · '+esc(row.status):''}</p>${row.type==='entries'?nav('Otwórz profil','profile'):button('Otwórz rekord',row.type==='offers'?'result-offer':row.type==='materials'?'result-materials':row.type==='notes'?'result-detail':'result-plan',row.type==='notes'?row.applicationId:row.id)}</article>`).join(''):'<p>Brak trafnych zapisanych rekordów. Nie przeszukiwano internetu ani zawartości plików.</p>';
    const canSave=p.mode!=='search'&&!p.saved&&!p.clarification&&(p.mode!=='command'||p.operations.length);
    return `<section class="cd-section" id="ai-preview" tabindex="-1"><div class="cd-section-head"><h2>${p.saved?'Zapisany wynik':'Podgląd — jeszcze nie zapisano'}</h2></div><p class="cd-small cd-muted">${p.modelCalled===false?'Wyszukiwanie bazy bez uruchomienia modelu':esc(p.model)} · ${stamp(p.createdAt)} · ${p.fullCV?'CV bazowe i wybrane materiały':p.materialsReview?'przegląd zapisanych materiałów':'research niewykonany'}</p>${content}<div class="cd-actions">${canSave?button(p.fullCV?'Zapisz CV i pobierz pliki':p.mode==='command'?'Sprawdź i zatwierdź operacje':'Sprawdź i zapisz wynik','ai-save','',true):''}${p.saved?(p.savedIds||[]).map(key=>store.find('materials',key)).filter(row=>row&&/\.(pdf|docx)$/.test(row.fileKey)).map(row=>`<a class="cd-button" href="/api/materials/${esc(row.id)}/download" download>Pobierz ${row.fileKey.endsWith('.pdf')?'PDF':'DOCX'}</a>`).join('')+nav('Otwórz materiały','materials'):''}</div></section>`;
  }
  async function runAI(mode) {
    if(aiBusy) return;
    const app=currentApp(),offer=app?store.offer(app):(mode==='cv'?store.find('offers',selectedOffer):null);
    if(['analysis','cv','message'].includes(mode)&&offer&&!offer.description.trim()&&offer.url){await offerTextDialog(offer.id,mode);return;}
    aiQuery=document.getElementById('ai-query')?.value||aiQuery; aiBusy=true; aiError=''; aiPreview=null; render();
    try { if(mode==='cv'&&!currentApp()&&offer) { const created=await store.createApplication(offer.id); selected=created.id; } aiPreview=await store.aiPrepare(mode,currentApp()?.id||'',mode==='command'||mode==='search'||mode==='materials'?aiQuery:'',mode==='cv'?{baseMaterialId:cvBase,materialIds:cvExtras}:{}); }
    catch(error) { aiError=error.message; }
    finally { aiBusy=false; if(screen==='assistant') { render(); (main.querySelector('#ai-preview')||main.querySelector('[role=alert]')||main).focus(); } }
  }
  async function offerTextDialog(key,nextMode='') {
    announce('Pobieranie treści wskazanej oferty…');
    let plan;
    try{plan=await store.offerTextPreview(key);}
    catch(error){announce(error.message);offerDialog(key);const message=document.getElementById('form-error');message.textContent=error.message;message.hidden=false;return;}
    showDialog('Treść oferty z linku',`<p class="spaced">${esc(plan.title)}</p><p class="cd-small preserve">Źródło: ${esc(plan.sourceUrl)}<br>Odczyt: ${esc(stamp(plan.fetchedAt))} · ${esc(plan.method)}</p>${plan.replacesText?'<p class="cd-notice">Zapis zastąpi obecny opis tej oferty. Sprawdź i popraw poniższą treść.</p>':'<p class="cd-small spaced">Sprawdź pobraną treść. Możesz ją poprawić przed zapisaniem.</p>'}`+textarea('description','Treść i wymagania',plan.text,true,10000)+'<p class="cd-small spaced">Przed zapisem powstanie kopia danych. Pobranie ogłoszenia nie jest weryfikacją firmy ani Twoich kompetencji.</p>',nextMode?'Zapisz treść i rozpocznij analizę':'Potwierdzam zapis treści',async input=>{await store.offerTextCommit(plan,input.description);closeDialog();render();announce('Zapisano treść oferty ze źródła.');if(nextMode)await runAI(nextMode);});
  }
  function saveAI() {
    const p=aiPreview;
    if(!p || p.saved) return;
    if(p.fullCV) p.draft=document.getElementById('ai-draft')?.value??p.draft;
    showDialog('Potwierdź zapis wyniku AI',`<p class="spaced">${p.mode==='command'?'Zapisz poniższe zadania i notatki.':'Zapisz raport ze źródłami'+(p.draft?', szkic tekstowy, PDF i DOCX':'')+' i przypnij je do wybranej aplikacji.'}</p><p class="cd-small spaced">${esc(p.applicationId?store.applicationLabel(p.applicationId):'Bez aplikacji')} · ${esc(p.model)}. Nic nie zostanie wysłane.</p>${p.operations?.length?`<ul>${p.operations.map(op=>`<li>${esc(op.data.title||op.data.text)}${op.data.due?' · '+esc(op.data.due):''}</li>`).join('')}</ul>`:''}${p.draft?`<p class="preserve">${esc(p.draft)}</p>`:''}<p class="cd-small spaced">Potwierdzam, że sprawdziłem treść i źródła. Zmiana danych po generowaniu wymaga nowego podglądu.</p>`,'Potwierdzam zapis',async()=>{ p.savedIds=await store.aiCommit(p,p.fullCV?p.draft:undefined); p.saved=true; closeDialog(); render(); announce('Zapisano zatwierdzony wynik AI. Bez wysyłki.'); });
  }
  function driveGuide() {
    return `<details class="cd-inline-details"><summary>Jak uzyskać plik JSON — instrukcja</summary><ol><li>Otwórz <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer">Google Cloud</a> na koncie, które ma Twoje materiały. Utwórz projekt „Centrum Kariery”.</li><li>W „API i usługi → Biblioteka” znajdź „Google Drive API” i kliknij „Włącz”.</li><li>Otwórz „Google Auth Platform”. W „Branding” rozpocznij konfigurację: nazwa „Centrum Kariery”, Twój e-mail jako kontakt.</li><li>W „Audience / Odbiorcy” wybierz „External / Zewnętrzni” dla zwykłego konta Google. Zachowaj tryb „Testing / Testowanie” i dodaj swój adres konta Google jako użytkownika testowego.</li><li>W „Data Access / Dostęp do danych” dodaj zakres <code>https://www.googleapis.com/auth/drive.readonly</code>. To odczyt Dysku, bez zmiany i usuwania plików.</li><li>W „Clients / Klienci” wybierz „Create Client / Utwórz klienta”, typ „Desktop app / Aplikacja komputerowa”, nazwa „Centrum Kariery”. Utwórz i pobierz JSON.</li><li>Tutaj wybierz „Dodaj plik JSON”, potem „Połącz Google Drive”. Otwórz logowanie w zwykłej przeglądarce, udziel zgody i wróć do aplikacji.</li></ol><p class="cd-small">Nie wklejaj zawartości JSON do czatu. Nie potrzebujesz klucza API. W trybie testowym Google może wymagać ponownego logowania po 7 dniach. <a href="https://developers.google.com/workspace/drive/api/quickstart/python" target="_blank" rel="noopener noreferrer">Instrukcja Google</a>.</p></details>`;
  }
  function driveView() {
    const s=driveStatus;
    return `<section class="cd-detail"><h2>Google Drive</h2><p>${s?(s.unreadable?'Konfiguracja jest nieczytelna. Dodaj plik JSON ponownie.':s.authorized?'Autoryzacja zapisana. Ustaw folder i sprawdź listę plików.':s.configured?'Plik konfiguracji dodany. Możesz rozpocząć logowanie.':'Niepołączony. Najpierw przygotuj plik JSON według instrukcji.'):'Kliknij „Sprawdź stan”, aby odczytać konfigurację.'}</p>${s?.error?`<p class="field-error">${esc(s.error)}</p>`:''}${s?.pending?'<p class="cd-notice">Oczekiwanie na zgodę Google. Po logowaniu kliknij „Sprawdź stan”.</p>':''}${s?.folder?`<p>Folder: <strong>${esc(s.folder.name)}</strong></p>`:''}<p class="cd-small">Wczytaj całe Portfolio wraz z podfolderami jednym importem lub wybierz pojedyncze pliki. Zapisujemy również nagrania, obrazy i arkusze. Ich zapis nie oznacza odczytania treści przez AI — pokażemy to w podglądzie. Import całego folderu: do 200 plików, 50 folderów, 100 MB na plik i 200 MB łącznie.</p><p class="cd-small cd-muted">Google udziela uprawnienia odczytu całego Dysku. Aplikacja ogranicza import do wybranego folderu. Po imporcie AI czyta lokalne kopie; zmiany na Dysku wymagają kolejnego importu. Autoryzacja jest chroniona przez konto Windows i nie trafia do kopii ani eksportów.</p><div class="cd-actions">${button(s?.configured?'Zmień plik JSON':'Dodaj plik JSON','drive-client')}${button('Sprawdź stan','drive-status')}${s?.configured&&!s?.unreadable?button('Połącz Google Drive','drive-connect'):''}${s?.authorized?button('Ustaw folder','drive-folder')+button('Odłącz Google Drive','drive-disconnect'):''}${s?.authorized&&s?.folder?button('Wczytaj całe Portfolio','drive-import-all','',true)+button('Wybierz pojedyncze pliki','drive-import'):''}</div>${driveGuide()}</section>`;
  }
  function driveClientDialog() {
    showDialog('Dodaj konfigurację Google Drive',driveGuide()+'<label for="drive-client-file">Plik JSON klienta OAuth *</label><input class="cd-field" id="drive-client-file" name="file" type="file" accept=".json">'+(driveStatus?.configured?'<label class="confirm-check"><input type="checkbox" name="confirmed"><span>Potwierdzam zastąpienie konfiguracji i usunięcie lokalnej autoryzacji. Poprzednią zgodę mogę cofnąć w koncie Google.</span></label>':''),'Zapisz konfigurację',async input=>{
      if (!(input.file instanceof File)||!input.file.size) throw new M.ValidationError('Wybierz pobrany plik JSON.');
      driveStatus=await store.driveClient(input.file,input.confirmed==='on'); closeDialog(); render(); announce('Dodano konfigurację. Teraz rozpocznij logowanie Google.');
    });
  }
  function driveConnectDialog() {
    showDialog('Połącz Google Drive',`<p class="spaced">Google poprosi o uprawnienie odczytu <strong>całego Dysku</strong>, bez zmiany i usuwania plików. Aplikacja pobiera tylko pliki wybrane z ustawionego folderu. Nie udostępnia modelowi AI autoryzacji Google.</p><label class="confirm-check"><input type="checkbox" name="confirmed"><span>Rozumiem zakres odczytu i chcę rozpocząć logowanie Google.</span></label>`,'Przygotuj logowanie',async input=>{
      if(input.confirmed!=='on') throw new M.ValidationError('Zaznacz potwierdzenie zakresu dostępu.');
      const result=await store.driveConnect(); const url=new URL(result.url);
      if(url.origin!=='https://accounts.google.com'||url.pathname!=='/o/oauth2/v2/auth') throw new M.ValidationError('Nieprawidłowy adres logowania Google.');
      driveStatus=await store.driveStatus(); render();
      showDialog('Zaloguj się w Google',`<p class="spaced">Otwórz poniższy link w zwykłej przeglądarce (Chrome lub Edge), wybierz swoje konto i sprawdź zgodę Google. Link jest ważny 10 minut. Gdy zobaczysz potwierdzenie połączenia, wróć tutaj.</p><p class="spaced"><a class="cd-button cd-primary" href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">Otwórz logowanie Google</a></p><p class="cd-small">Jeśli Google blokuje logowanie w przeglądarce aplikacji, skopiuj adres tego odnośnika i otwórz go w Chrome lub Edge. Hasła wpisujesz wyłącznie na stronie Google.</p>`,'Sprawdź stan po logowaniu',async()=>{driveStatus=await store.driveStatus(); if(!driveStatus.authorized) throw new M.ValidationError(driveStatus.error||(driveStatus.pending?'Nie zakończono jeszcze logowania. Wróć do karty Google.':'Sesja logowania jest nieaktywna. Zamknij to okno i kliknij ponownie „Połącz Google Drive”, aby użyć nowego linku.')); closeDialog(); render(); announce('Autoryzacja zapisana. Wybierz folder materiałów.');});
    });
  }
  function driveFolderDialog() {
    const material=store.state.materials.find(x=>/^https:\/\/drive\.google\.com\/drive\/(?:u\/\d+\/)?folders\//.test(x.url));
    showDialog('Wybierz folder materiałów',field('url','Link do folderu Google Drive',driveStatus?.folder?'https://drive.google.com/drive/folders/'+driveStatus.folder.id:material?.url||'','url',true,2000)+'<p class="cd-small spaced">Wybierz główny folder portfolio. Przy imporcie możesz otwierać jego podfoldery, do 8 poziomów.</p>','Sprawdź i ustaw folder',async input=>{driveStatus=await store.driveFolder(input.url); closeDialog(); render(); announce('Ustawiono folder. Możesz wybrać pliki do importu.');});
  }
  function driveImportFields(data) {
    const crumbs=data.breadcrumbs||[data.folder];
    const folders=data.items.filter(x=>x.isFolder),files=data.items.filter(x=>!x.isFolder);
    return `<p class="spaced">Folder: <strong>${esc(crumbs.map(x=>x.name).join(' / '))}</strong>. Otwórz podfolder lub wybierz do 5 plików oraz ich typy. Przygotowanie podglądu pobierze kopie; poczekaj na zakończenie.</p>${crumbs.length>1?`<div class="cd-actions">${button('Wróć do folderu nadrzędnego','drive-open-folder',crumbs[crumbs.length-2].id)}${crumbs.length>2?button('Folder główny portfolio','drive-open-folder',crumbs[0].id):''}</div>`:''}${data.partial?'<p class="cd-notice">Lista jest niepełna (maksymalnie 200 pozycji). Wybierz mniejszy folder.</p>':''}${folders.map(x=>`<section class="cd-side-panel"><h3 class="preserve">${esc(x.name)}</h3>${button('Otwórz folder','drive-open-folder',x.id)}</section>`).join('')}${files.map(x=>`<section class="cd-side-panel"><label class="confirm-check"><input type="checkbox" name="pick-${esc(x.id)}"${x.reason?' disabled':''}><span>${esc(x.name)}</span></label>${x.reason?`<p class="cd-small cd-muted">${esc(x.reason)}</p>`:select('kind-'+x.id,'Typ materiału',['CV','Portfolio','List','Wiadomość','Inny'],/\bcv\b/i.test(x.name)?'CV':'Portfolio')}</section>`).join('')}${!files.length?'<p class="cd-small spaced">W tym folderze nie ma plików do zaznaczenia. Otwórz jeden z podfolderów.</p>':''}<p class="cd-small">Przejście do innego folderu usuwa zaznaczenia. Importuj wybrane pliki z bieżącego folderu, a następnie wróć po pozostałe.</p>`;
  }
  async function driveImportDialog(folder='') {
    announce('Pobieranie listy plików z Google Drive…');
    const data=await store.driveFiles(folder);
    showDialog('Wybierz pliki z Google Drive',driveImportFields(data),'Przygotuj podgląd importu',async input=>{
      const selection=data.items.filter(x=>!x.isFolder&&!x.reason&&input['pick-'+x.id]==='on').map(x=>({id:x.id,kind:input['kind-'+x.id]}));
      if(!selection.length||selection.length>5) throw new M.ValidationError('Wybierz od 1 do 5 plików. Jeśli widzisz tylko foldery, najpierw otwórz wybrany folder.');
      driveImportConfirm(await store.drivePreview(selection));
    });
  }
  function driveImportAllDialog() {
    showDialog('Wczytaj całe Portfolio',`<p class="spaced">Folder główny: <strong>${esc(driveStatus?.folder?.name||'Portfolio')}</strong>. Pobierzemy zawartość tego folderu i jego podfolderów, bez ręcznego zaznaczania plików. Wszystkie nowe materiały otrzymają typ Portfolio.</p><p class="cd-small spaced">Przygotowanie może zająć kilka minut. Dokumenty Google eksportujemy do DOCX, Arkusze do XLSX, Prezentacje do PPTX. Pozostałe pliki zachowujemy w oryginalnej postaci. Nagrania i obrazy zostaną zapisane, ale obecne AI nie ma transkrypcji ani OCR.</p><p class="cd-small spaced">Przed zapisem zobaczysz pełną listę, duplikaty i pominięcia. Limit: 200 plików, 50 folderów, 8 poziomów, 100 MB na plik, 200 MB łącznie. Nie odświeżaj strony podczas przygotowania.</p>`,'Przygotuj podgląd całego Portfolio',async()=>{
      document.getElementById('save-status').textContent='Przygotowywanie całego Portfolio…';
      driveImportConfirm(await store.drivePreviewAll());
    });
  }
  function driveImportConfirm(plan) {
    const unreadable=plan.items.filter(x=>x.readable===false).length;
    showDialog(plan.wholeFolder?'Potwierdź import całego Portfolio':'Potwierdź import z Google Drive',`<p class="spaced">Gotowe do zapisu: <strong>${plan.items.length} plików</strong>${plan.wholeFolder?` · znalezione: ${plan.filesFound} · sprawdzone foldery: ${plan.foldersScanned}`:''}.</p>${(plan.warnings||[]).length?`<p class="field-error">Import jest niepełny:</p><ul>${plan.warnings.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${unreadable?`<p class="cd-notice">${unreadable} plików zachowamy jako załączniki. Ich treść wymaga OCR, transkrypcji, obsługi arkuszy albo przekracza limit czytnika AI. Pozostałe dokumenty można poddać analizie tekstowej; skany PDF także mogą wymagać OCR.</p>`:''}${plan.items.length?`<ul>${plan.items.map(x=>`<li>${esc(x.title)} · ${esc(x.kind)} · ${Math.ceil(x.size/1024)} KB${x.path?`<p class="cd-small cd-muted">${esc(x.path)}</p>`:''}${x.readable===false?'<span class="cd-tag">Załącznik — bez odczytu treści przez AI</span>':''}</li>`).join('')}</ul>`:'<p class="spaced">Brak nowych plików do zapisania. Sprawdź listę pominiętych wersji.</p>'}${plan.skipped.length?`<p class="spaced">Pominięte (${plan.skipped.length}):</p><ul>${plan.skipped.map(x=>`<li>${x.name?esc(x.name)+' — ':''}${esc(x.reason)}</li>`).join('')}</ul>`:''}<p class="cd-small spaced">Pliki na Dysku pozostają bez zmian. Przed zapisem utworzymy kopię danych aplikacji. Podgląd jest ważny 15 minut; zmiana bazy wymaga nowego podglądu. Każdy plik zachowa źródło i ścieżkę folderu.</p>`,plan.token?'Potwierdzam import':'Zamknij podsumowanie',async()=>{ if(!plan.token){closeDialog();return;} const ids=await store.driveCommit(plan); closeDialog(); navigate('materials'); announce('Zaimportowano '+ids.length+' plików. Możesz teraz uruchomić przegląd materiałów z AI.'); });
  }
  function settingsView() {
    return heading('Ustawienia','Trwałe dane lokalne, kopie i status integracji.') + `<div class="cd-grid2"><section class="cd-detail"><h2>Dane i kopie</h2><p>Zapisy pozostają po odświeżeniu i restarcie. Automatycznie zachowujemy ostatnie 7 kopii dziennych i 4 tygodniowe. Kopie ręczne i kopie przed importem pozostają osobno.</p><p class="cd-small cd-muted">Kopia na tym samym dysku nie chroni przed jego awarią. Pobierz pełny pakiet i skopiuj go na własny drugi nośnik.</p>${store.state.backupError ? `<p class="field-error">${esc(store.state.backupError)}</p>` : ''}<div class="cd-actions">${button('Utwórz kopię teraz','create-backup')}${button('Wybierz kopię do przywrócenia','restore-backup')}</div></section><section class="cd-detail"><h2>Import i eksport</h2><p class="cd-small">CSV dodaje oferty; pełny JSON lub ZIP zastępuje rekordy po podglądzie i potwierdzeniu. ZIP obejmuje lokalne pliki. JSON przenosi relacje, ale nie pliki.</p><div class="cd-actions">${button('Importuj plik','import')}<a class="cd-button" href="/api/export/zip" download>Pobierz pełny pakiet ZIP</a><a class="cd-button" href="/api/export/json" download>Eksport JSON</a><a class="cd-button" href="/api/export/offers" download>Oferty / szablon CSV</a><a class="cd-button" href="/api/export/applications" download>Aplikacje CSV</a></div></section><section class="cd-detail"><h2>Archiwum</h2><p class="cd-small">Archiwizacja zachowuje rekord i powiązania. Zarchiwizowane dane są pomijane na głównych listach.</p>${store.state.archive.length ? store.state.archive.map(item=>`<div class="archive-row"><p class="preserve cd-small">${esc(item.title)}</p>${button('Przywróć rekord','unarchive',item.id)}</div>`).join('') : '<p class="cd-muted">Archiwum jest puste.</p>'}</section><section class="cd-detail"><h2>Integracje i koszty</h2><p class="cd-small">Ta wersja działa bez płatnych usług. Ochrona konta i szyfrowania dysku zależy od konfiguracji Windows; sama baza i eksporty nie są szyfrowane.</p><ul class="cd-checklist"><li>Ollama: ${aiStatus?.available ? 'dostępny lokalnie · '+esc(aiStatus.model) : 'wyłączony lub niedostępny'}</li><li>ChatGPT / Claude / Gemini API: niepołączone; adaptery chmurowe wymagają konfiguracji w kodzie i osobnych kluczy</li><li>AOL: niepołączone; brak odczytu i wysyłki</li><li>Kalendarz zewnętrzny: niepołączony</li><li>Portale, grupy i LinkedIn: ręczne linki i import</li><li>Google Drive: ${driveStatus?.authorized?'autoryzacja zapisana; ręczny import':'niepołączony'}</li><li>GitHub / n8n: zapisane linki, brak synchronizacji</li></ul><div class="cd-actions">${button('Konfiguruj lokalny model','ai-config')}${button('Sprawdź połączenie','ai-status')}</div></section>${driveView()}</div>`;
  }

  function searchView() {
    const results = store.search(query);
    return heading('Wyniki wyszukiwania', `Szukasz: „${query}” · wyniki: ${results.length}`) + (results.length ? results.map(item => `<article class="cd-offer"><div><p class="cd-kicker">${item.kind}</p><h2 class="preserve">${esc(item.title)}</h2><p class="cd-small cd-muted">${esc(item.detail)}</p></div>${button('Otwórz wynik', `result-${item.screen}`, item.key)}</article>`).join('') : empty('Brak wyników', 'Szukamy w ofertach, aplikacjach, zadaniach, terminach, notatkach i opisach materiałów. Nie przeszukujemy internetu.', button('Wyczyść wyszukiwanie', 'clear-search')));
  }
  function render() {
    const views = { today: todayView, offers: offersView, offer: offerView, applications: applicationsView, detail: detailView, plan: planView, profile: profileView, materials: materialsView, assistant: assistantView, settings: settingsView, search: searchView };
    main.innerHTML = views[screen]();
    main.setAttribute('aria-busy',String(aiBusy));
    if (store.state.backupError) announce(store.state.backupError);
    const navScreen = screen === 'offer' ? 'offers' : screen === 'detail' ? 'applications' : screen;
    document.querySelectorAll('.cd-nav button').forEach(item => { if (item.dataset.screen === navScreen) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current'); });
    document.title = `${main.querySelector('h1')?.textContent || 'Centrum Dowodzenia'} ·`;
  }
  function showDialog(title, fields, submitLabel, callback) {
    opener = document.activeElement;
    body.innerHTML = `<div class="cd-dialog-head"><h2 id="dialog-title">${esc(title)}</h2><button type="button" class="cd-button" data-action="close-dialog" aria-label="Zamknij formularz">Zamknij</button></div><form id="edit-form" novalidate><p class="cd-small cd-muted spaced">dane są zapisywane lokalnie. Pola z * są wymagane.</p><p id="form-error" class="field-error" role="alert" hidden></p>${fields}<div class="cd-actions"><button class="cd-button cd-primary" type="submit">${esc(submitLabel)}</button><button class="cd-button" type="button" data-action="close-dialog">Anuluj</button></div></form>`;
    onSubmit = callback;
    if (!dialog.open) dialog.showModal();
    (body.querySelector('input, textarea, select') || body.querySelector('button[type=submit]')).focus();
  }
  function closeDialog() { dialog.close(); if (opener?.isConnected) opener.focus(); else main.focus(); }
  function errors(error) {
    const top = document.getElementById('form-error'); top.hidden = false; top.textContent = error.message || 'Nie udało się zapisać danych.';
    Object.entries(error.errors || {}).forEach(([name, message]) => { const field = body.querySelector(`[name="${name}"]`), text = document.getElementById(`err-${name}`); if (field) field.setAttribute('aria-invalid', 'true'); if (text) { text.textContent = message; text.hidden = false; } });
    (body.querySelector('[aria-invalid=true]') || body.querySelector('[type=submit]')).focus();
  }
  function offerDialog(key) {
    const item = key ? store.find('offers', key) : { title: '', location: '', description: '', url: '', deadline: '', direction: M.DIRECTIONS[0], mode: M.MODES[1], contract: M.CONTRACTS[0] };
    showDialog(key ? 'Edytuj ofertę' : 'Dodaj ofertę', field('title', 'Stanowisko', item.title, 'text', true, 180) + field('company', 'Firma', key ? store.company(item).name : '', 'text', true, 120) + field('location', 'Lokalizacja', item.location, 'text', true, 120) + select('direction', 'Kierunek', M.DIRECTIONS, item.direction) + select('mode', 'Tryb pracy', M.MODES, item.mode) + select('contract', 'Umowa', M.CONTRACTS, item.contract) + field('url', 'Link źródłowy (opcjonalnie)', item.url, 'url', false, 2000) + '<p class="cd-small cd-muted">Identyczny link blokuje zapis. Podobna firma i tytuł wymagają sprawdzenia.</p><label class="confirm-check"><input type="checkbox" name="allowSimilar"><span>Sprawdziłem podobne wpisy: to odrębne ogłoszenie.</span></label><p id="err-allowSimilar" class="field-error" hidden></p>' + field('deadline', 'Termin aplikowania (opcjonalnie)', item.deadline, 'date') + textarea('description', 'Treść i wymagania (opcjonalnie)', item.description, false, 12000), 'Zapisz ofertę', async input => { const record = await store.saveOffer({...input,allowSimilar:input.allowSimilar==='on'}, key); closeDialog(); navigate('offer', record.id); announce('Zapisano ofertę. Dane zapisano w bazie.'); });
  }
  function taskDialog(key, appId) {
    const item = key ? store.find('tasks', key) : { title: '', due: M.today(), applicationId: appId || '' };
    showDialog(key ? 'Edytuj zadanie' : 'Dodaj zadanie', field('title', 'Zadanie', item.title, 'text', true) + field('due', 'Termin — dzień w Europe/Warsaw', item.due, 'date', true) + appSelect(item.applicationId), 'Zapisz zadanie', async input => { await store.saveTask(input, key); closeDialog(); render(); announce('Zapisano zadanie i jego powiązanie.'); });
  }
  function eventDialog(key, appId) {
    const day = M.dayOffset(M.today(), 1), item = key ? store.find('events', key) : { title: 'Rozmowa kwalifikacyjna', start: `${day}T10:00`, end: `${day}T10:30`, applicationId: appId || '', place: '' };
    showDialog(key ? 'Edytuj rozmowę' : 'Dodaj rozmowę', field('title', 'Nazwa', item.title, 'text', true) + '<p class="cd-small spaced">Godziny w Europe/Warsaw, niezależnie od strefy komputera.</p>' + field('start', 'Początek', item.start, 'datetime-local', true) + field('end', 'Koniec', item.end, 'datetime-local', true) + field('place', 'Miejsce lub informacje o połączeniu', item.place, 'text', false, 500) + appSelect(item.applicationId), 'Zapisz termin', async input => { await store.saveEvent(input, key); closeDialog(); render(); announce('Zapisano termin. Nie dodano wydarzenia do zewnętrznego kalendarza.'); });
  }
  function statusDialog(key) {
    const app = store.find('applications', key);
    showDialog('Zmień status aplikacji', select('status', 'Status', M.STATUSES, app.status) + '<p class="cd-small spaced">„Wysłana” to Twoje ręczne oznaczenie. System niczego nie wysyła.</p>', 'Zapisz status', async input => {
      if (input.status === 'Wysłana' && app.status !== 'Wysłana') {
        showDialog('Potwierdź oznaczenie wysłania', '<p class="spaced">Oznaczysz jako „Wysłana” aplikację: <strong>' + appName(key) + '</strong>. Wiadomość ani dokument nie zostaną wysłane. Czy potwierdzasz ręczne oznaczenie?</p>', 'Potwierdzam oznaczenie', async () => { await store.setStatus(key, input.status, true); closeDialog(); render(); announce('Zmieniono status po potwierdzeniu. Niczego nie wysłano.'); });
      } else { await store.setStatus(key, input.status, true); closeDialog(); render(); announce('Zmieniono status; wpisano zmianę do historii.'); }
    });
  }
  function deleteDialog(table, key) {
    const item = store.find(table, key);
    showDialog('Potwierdź archiwizację', `<p class="preserve spaced">Zarchiwizujesz ${esc(item.title || item.text)}. Powiązana aplikacja i inne rekordy pozostaną.</p>`, 'Archiwizuj rekord', async () => { await store.remove(table, key, true); closeDialog(); render(); announce('Zarchiwizowano wskazany rekord.'); });
  }
  function pinDialog(appId) {
    const app = store.find('applications', appId);
    const candidates = store.state.materials.filter(item => !store.state.links.some(link => link.applicationId === app.id && link.materialId === item.id));
    if (!candidates.length) { announce('Wszystkie istniejące wersje są już przypięte do tej aplikacji. Dodaj nowy opis w Materiałach.'); return; }
    showDialog('Przypnij materiał', `<p class="spaced cd-small">${appName(appId)}. Wybierasz odwołanie do istniejącej wersji, bez kopiowania.</p>` + select('materialId', 'Materiał i wersja', candidates.map(item => ({ id: item.id, label: `${item.title} · v${item.version}` })), candidates[0].id), 'Przypnij wersję', async input => { await store.pinMaterial(appId, input.materialId); closeDialog(); render(); announce('Przypięto istniejącą wersję materiału.'); });
  }
  function materialDialog(defaultKind='CV') {
    showDialog('Dodaj materiał', field('title','Nazwa','','text',true,180) + select('kind','Typ',['CV','Portfolio','List','Wiadomość','Inny'],defaultKind) + field('version','Wersja','1','text',true,30) + field('url','Odnośnik (opcjonalnie)','','url',false,2000) + textarea('description','Opis i pochodzenie (opcjonalnie)') + '<label for="material-file">Plik lokalny (opcjonalnie, do 20 MB; odczyt CV do 5 MB)</label><input class="cd-field" id="material-file" name="file" type="file" accept=".pdf,.docx,.txt,.md,.json,.png,.jpg,.jpeg"><p class="cd-small cd-muted">Plik zachowujemy bez zmian. Generator CV obsługuje PDF z tekstem, DOCX i TXT. Skany oraz obrazy wymagają odczytu do tekstu.</p>', 'Dodaj wersję', async input => {
      const {file,...data}=input;
      if (file?.size) await store.upload(data,file); else await store.addMaterial(data);
      closeDialog(); render(); announce('Zapisano niezmienną wersję materiału.');
    });
  }
  function profileDialog() {
    const profile=store.state.profile;
    showDialog('Edytuj profil',field('name','Imię i nazwisko',profile.name,'text',false,120)+field('email','E-mail do kontaktu',profile.email,'email',false,254)+textarea('goal','Cel zawodowy',profile.goal,false,2000)+field('locations','Miasta i okolice — oddziel przecinkami',profile.preferences.locations.join(', '),'text',false,2000), 'Zapisz profil', async input=>{
      await store.saveProfile({name:input.name,email:input.email,goal:input.goal,preferences:{...profile.preferences,locations:input.locations.split(',').map(item=>item.trim()).filter(Boolean)}}); closeDialog(); render(); announce('Zapisano wspólny profil i listę miejscowości.');
    });
  }
  function entryDialog(key) {
    const item=key ? store.find('entries',key) : {kind:'Umiejętność',content:'',status:'Podane przez użytkownika',source:''};
    showDialog(key ? 'Edytuj wpis profilu' : 'Dodaj wpis ze źródłem',select('kind','Rodzaj',['Umiejętność','Doświadczenie','Edukacja','Projekt','Język','Inne'],item.kind)+textarea('content','Informacja',item.content,true)+select('status','Stan informacji',['Podane przez użytkownika','Sprawdzone w materiale','Do potwierdzenia','W nauce','Wniosek'],item.status)+field('source','Źródło / skąd pochodzi informacja',item.source,'text',true,500)+(key ? '<label class="confirm-check"><input type="checkbox" name="confirmed"><span>Potwierdzam zmianę tej informacji i jej źródła.</span></label>' : ''),'Zapisz wpis',async input=>{
      await store.saveEntry({...input,confirmed:input.confirmed==='on'},key); closeDialog(); render(); announce('Zapisano informację wraz ze źródłem i stanem.');
    });
  }
  function searchDialog() {
    showDialog('Zapisz wyszukiwanie ofert',field('name','Nazwa wyszukiwania','','text',true,120)+field('url','Link do wyników na portalu','','url',true,2000)+'<p class="cd-small spaced">Zapisujesz odnośnik do ręcznego otwierania. Nie łączymy konta ani nie pobieramy wyników.</p>','Zapisz odnośnik',async input=>{ await store.saveSearches([...store.state.savedSearches,{name:input.name,url:input.url}]); closeDialog(); render(); announce('Zapisano odnośnik do wyszukiwania.'); });
  }
  function importDialog() {
    showDialog('Importuj dane',select('kind','Format',['csv','json','zip'],'csv')+'<label for="import-file">Plik *</label><input class="cd-field" id="import-file" name="file" type="file" accept=".csv,.json,.zip"><p class="cd-small spaced">CSV dodaje oferty. Pełny JSON i ZIP zastępują rekordy po potwierdzeniu. Limit pakietu: 300 MB.</p><details class="cd-inline-details"><summary>Kolumny CSV i mapowanie</summary><p>title → stanowisko; company → firma; location → miejscowość; direction → kierunek; mode → tryb; contract → umowa; url → link; description → opis; deadline → data YYYY-MM-DD. Użyj szablonu z eksportu ofert. Kodowanie UTF-8, separator przecinek lub średnik.</p></details>','Przygotuj podgląd',async input=>{
      if (!input.file?.size) throw new M.ValidationError('Wybierz niepusty plik.');
      const plan=await store.previewImport(input.kind,input.file); confirmPlan(plan);
    });
  }
  function confirmPlan(plan) {
    const labels={profiles:'Profile',profile_entries:'Wpisy profilu',companies:'Firmy',offers:'Oferty',applications:'Aplikacje',tasks:'Zadania',events:'Terminy',notes:'Notatki',materials:'Materiały',application_materials:'Powiązania materiałów',audit_events:'Wpisy historii',settings:'Ustawienia'};
    const preview=plan.preview.length ? '<h3 class="spaced">Pierwsze rekordy</h3>'+plan.preview.map(item=>`<p class="cd-small preserve">${esc(item.title)} · ${esc(item.company)} · ${esc(item.location)}</p>`).join('') : '';
    showDialog('Potwierdź import lub przywrócenie',`<p class="spaced">${esc(plan.summary)}</p><ul class="cd-checklist">${Object.entries(plan.counts).map(([name,count])=>`<li>${esc(labels[name]||name)}: ${count}</li>`).join('')}</ul>${preview}<p class="cd-small spaced">Podgląd jest ważny 15 minut. Każda zmiana bazy wymaga ponownego podglądu. Kliknięcie poniżej zatwierdza wskazaną operację.</p>`,'Potwierdzam zapis danych',async ()=>{ await store.commitImport(plan); closeDialog(); selected=store.state.applications.find(x=>!x.archived)?.id||''; selectedOffer=store.state.offers.find(x=>!x.archived)?.id||''; filters={direction:'',location:'',mode:'',contract:''}; navigate('today'); announce('Zakończono import lub przywrócenie. Utworzono kopię poprzedniego stanu.'); });
  }
  async function restoreDialog() {
    const data=await store.backups();
    if (!data.items.length) { announce('Brak kopii do przywrócenia.'); return; }
    showDialog('Wybierz kopię',select('name','Kopia',data.items.map(item=>({id:item.name,label:`${stamp(item.at)} · ${item.name}`})),data.items[0].name)+'<p class="cd-small spaced">Najpierw sprawdzimy integralność i pokażemy podgląd. Bieżące dane zostaną zachowane w osobnej kopii przed zatwierdzonym przywróceniem.</p>','Sprawdź i pokaż podgląd',async input=>confirmPlan(await store.previewBackup(input.name)));
  }
  function archiveDialog(table,key,restore=false) {
    const item=store.find(table==='profile_entries'?'entries':table,key);
    showDialog(restore?'Przywróć rekord z archiwum':'Archiwizuj rekord',`<p class="preserve spaced">${esc(item.title||item.content||item.text||store.applicationLabel(key))}</p><p class="cd-small spaced">Powiązania i historia pozostaną. Archiwizacja nie usuwa trwale danych.</p>`,restore?'Przywróć rekord':'Potwierdzam archiwizację',async ()=>{ await store.archive(table,key,true,restore); closeDialog(); if (table==='offers'||table==='applications') navigate(restore?'settings':table==='offers'?'offers':'applications'); else render(); announce(restore?'Przywrócono rekord.':'Zarchiwizowano rekord i zachowano relacje.'); });
  }
  async function action(name, key) {
    if (name.startsWith('result-')) {
      const dest = name.slice(7); navigate(dest, key);
      if (dest === 'plan') { planFilter = 'all'; render(); const item = main.querySelector(`[data-key="${CSS.escape(key)}"]`); item?.focus(); item?.scrollIntoView({ block: 'center' }); }
      if (dest === 'materials') announce('Otworzono bibliotekę; wynik: ' + store.find('materials', key).title);
      return;
    }
    switch (name) {
      case 'offer-read-link': await offerTextDialog(key); break;
      case 'drive-status': driveStatus=await store.driveStatus(); render(); announce(driveStatus.authorized?'Autoryzacja zapisana. Odczyt folderu sprawdzisz przy imporcie.':'Sprawdzono stan Google Drive.'); break;
      case 'drive-client': driveStatus=await store.driveStatus(); driveClientDialog(); break;
      case 'drive-connect': driveConnectDialog(); break;
      case 'drive-folder': driveFolderDialog(); break;
      case 'drive-import': await driveImportDialog(); break;
      case 'drive-import-all': driveImportAllDialog(); break;
      case 'drive-open-folder': await driveImportDialog(key); break;
      case 'drive-disconnect': showDialog('Odłącz Google Drive','<p class="spaced">Cofniemy zgodę w Google i usuniemy lokalną autoryzację. Zaimportowane materiały pozostaną.</p>','Potwierdzam odłączenie',async()=>{driveStatus=await store.driveDisconnect();closeDialog();render();announce(driveStatus.error||'Odłączono Google Drive.');}); break;
      case 'ai-run': await runAI(key); break;
      case 'ai-save': saveAI(); break;
      case 'ai-status': aiStatus=await store.aiStatus(); render(); announce(aiStatus.available?'Lokalny model odpowiada. Stan innych integracji znajdziesz w Ustawieniach.':'Sprawdzono stan. '+(aiStatus.error||'Włącz model w ustawieniach.')); break;
      case 'ai-config': {
        aiStatus=await store.aiStatus();
        const models=aiStatus.models.length?aiStatus.models:[aiStatus.model];
        showDialog('Lokalny model AI',select('model','Zainstalowany model lokalny',models,aiStatus.model)+`<label class="check-label"><input type="checkbox" name="enabled"${aiStatus.enabled?' checked':''}> Włącz lokalne AI</label><p class="cd-small spaced">Ollama musi działać na 127.0.0.1:11434. Modele cloud są pomijane. Nie pobieramy nowych modeli. Dane nie są przesyłane do usług chmurowych. Zmiana modelu nie zmienia bazy ani zasad zatwierdzania.</p>`,'Zapisz konfigurację',async input=>{ aiStatus=await store.aiConfigure(input.model,input.enabled==='on'); aiPreview=null; closeDialog(); render(); announce('Zapisano konfigurację lokalnego AI.'); }); break;
      }
      case 'edit-profile': profileDialog(); break;
      case 'add-entry': entryDialog(); break;
      case 'edit-entry': entryDialog(key); break;
      case 'archive-entry': archiveDialog('profile_entries',key); break;
      case 'archive-offer': archiveDialog('offers',key); break;
      case 'archive-application': archiveDialog('applications',key); break;
      case 'unarchive': { const item=store.state.archive.find(x=>x.id===key); if (item) archiveDialog(item.table,key,true); break; }
      case 'save-search': searchDialog(); break;
      case 'remove-search': showDialog('Usuń zapisany odnośnik','<p class="spaced">Usunięcie odnośnika nie zmieni ofert ani aplikacji.</p>','Potwierdzam usunięcie odnośnika',async()=>{ await store.saveSearches(store.state.savedSearches.filter((_,index)=>index!==Number(key))); closeDialog(); render(); }); break;
      case 'import': importDialog(); break;
      case 'create-backup': { const result=await store.createBackup(); announce('Utworzono i zapisano kopię: '+result.name); break; }
      case 'restore-backup': await restoreDialog(); break;
      case 'refresh': await store.refresh(); navigate('today'); announce('Odświeżono dane z bazy.'); break;
      case 'add-offer': offerDialog(); break;
      case 'edit-offer': offerDialog(key); break;
      case 'offer': navigate('offer', key); break;
      case 'detail': navigate('detail', key); break;
      case 'create-application': { const app = await store.createApplication(key); navigate('detail', app.id); announce('Otwarto jedną aplikację powiązaną z ofertą.'); break; }
      case 'add-task': taskDialog('', key); break;
      case 'edit-task': taskDialog(key); break;
      case 'add-event': eventDialog('', key); break;
      case 'edit-event': eventDialog(key); break;
      case 'delete-task': deleteDialog('tasks', key); break;
      case 'delete-event': deleteDialog('events', key); break;
      case 'delete-note': deleteDialog('notes', key); break;
      case 'status': statusDialog(key); break;
      case 'add-note': showDialog('Dodaj notatkę', textarea('text', 'Notatka', '', true), 'Zapisz notatkę', async input => { await store.addNote({ ...input, applicationId: key }); closeDialog(); render(); announce('Dodano notatkę do wybranej aplikacji.'); }); break;
      case 'add-material': materialDialog(); break;
      case 'add-cv': materialDialog('CV'); break;
      case 'pin-material': pinDialog(key); break;
      case 'documents': selected = key; screen = 'detail'; detailTab = 'documents'; render(); main.focus(); break;
      case 'assistant': selected = key; navigate('assistant'); break;
      case 'clear-filters': filters = { direction: '', location: '', mode: '', contract: '' }; render(); main.focus(); break;
      case 'clear-search': query = ''; document.getElementById('search').value = ''; navigate('today'); document.getElementById('search').focus(); break;
      case 'close-dialog': closeDialog(); break;

    }
  }
  document.getElementById('app').addEventListener('click', async event => {
    const target = event.target.closest('button'); if (!target) return;
    try {
    if (target.dataset.screen) { if(target.dataset.screen==='settings') driveStatus=await store.driveStatus(); navigate(target.dataset.screen); }
    else if (target.dataset.action) await action(target.dataset.action, target.dataset.key);
    else if (target.dataset.tab) { detailTab = target.dataset.tab; render(); main.querySelector(`[data-tab="${detailTab}"]`).focus(); }
    } catch(error) { announce(error.message); }
  });
  document.getElementById('menu').addEventListener('click', () => { const open = document.querySelector('.cd-shell').classList.toggle('cd-nav-open'); document.getElementById('menu').setAttribute('aria-expanded', String(open)); if (open) document.querySelector('.cd-nav button').focus(); });
  document.addEventListener('keydown', async event => { if (event.key === 'Escape' && !dialog.open) { document.querySelector('.cd-shell').classList.remove('cd-nav-open'); document.getElementById('menu').setAttribute('aria-expanded', 'false'); } });
  document.getElementById('search-form').addEventListener('submit', async event => { event.preventDefault(); query = document.getElementById('search').value.trim(); if (query) navigate('search'); else navigate('today'); });
  main.addEventListener('change', async event => {
    const target = event.target;
    try {
    if (target.dataset.filter) { filters[target.dataset.filter] = target.value; render(); document.getElementById(target.id).focus(); }
    else if (target.dataset.task) { await store.toggleTask(target.dataset.task); render(); const checkbox = main.querySelector(`[data-task="${target.dataset.task}"]`); (checkbox || main).focus(); announce(target.checked ? 'Ukończono zadanie.' : 'Wznowiono zadanie.'); }
    else if (target.id === 'app-filter') { appFilter = target.value; render(); document.getElementById('app-filter').focus(); }
    else if (target.id === 'plan-filter') { planFilter = target.value; render(); document.getElementById('plan-filter').focus(); }
    else if (target.id === 'ai-context') { selectedOffer=target.value; selected=store.state.applications.find(row=>row.offerId===target.value&&!row.archived)?.id||''; aiPreview=null; aiError=''; render(); document.getElementById('ai-context').focus(); }
    else if(target.id==='cv-base') { cvBase=target.value; aiPreview=null; render(); document.getElementById('cv-base').focus(); }
    else if(target.dataset.cvExtra) { if(target.checked&&cvExtras.length>=5) { target.checked=false; announce('Wybierz maksymalnie 5 materiałów.'); return; } cvExtras=target.checked?[...cvExtras,target.dataset.cvExtra]:cvExtras.filter(key=>key!==target.dataset.cvExtra); aiPreview=null; render(); }
    } catch(error) { render(); announce(error.message); }
  });
  main.addEventListener('input',event=>{ if(event.target.id==='ai-query') aiQuery=event.target.value; if(event.target.id==='ai-draft'&&aiPreview?.fullCV&&!aiPreview.saved) aiPreview.draft=event.target.value; });
  body.addEventListener('submit', async event => {
    event.preventDefault(); body.querySelectorAll('[aria-invalid]').forEach(item => item.removeAttribute('aria-invalid')); body.querySelectorAll('.field-error').forEach(item => { item.hidden = true; });
    const form=event.target, controls=[...form.querySelectorAll('button')]; controls.forEach(item=>item.disabled=true); document.getElementById('save-status').textContent='Zapisywanie…';
    try { await onSubmit(Object.fromEntries(new FormData(form))); } catch (error) { if(dialog.open) errors(error); else announce(error.message); } finally { controls.forEach(item=>item.disabled=false); document.getElementById('save-status').textContent=''; }
  });
  dialog.addEventListener('cancel', async event => { event.preventDefault(); closeDialog(); });
  render();
  try { aiStatus=await store.aiStatus(); if(!aiBusy) render(); } catch(error) { aiStatus={available:false,error:error.message,model:'qwen3:1.7b',models:[],enabled:false}; }
})().catch(error=>{ const main=document.getElementById('main'); main.replaceChildren(); const heading=document.createElement('h1'); heading.textContent='Nie można otworzyć danych'; const text=document.createElement('p'); text.textContent=error.message; const retry=document.createElement('button'); retry.type='button'; retry.className='cd-button'; retry.textContent='Odśwież stronę'; retry.addEventListener('click',()=>location.reload()); main.append(heading,text,retry); });
