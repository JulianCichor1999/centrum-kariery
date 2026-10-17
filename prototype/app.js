(function () {
  'use strict';
  const M = window.CareerDemo, store = M.createStore();
  const main = document.getElementById('main'), dialog = document.getElementById('dialog'), body = document.getElementById('dialog-body');
  let screen = 'today', selected = 'a1', selectedOffer = 'o1', detailTab = 'overview', aiStep = 0, opener, onSubmit;
  let filters = { direction: '', location: '', mode: '', contract: '' }, query = '', planFilter = 'open', appFilter = '';
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
    screen = name;
    if (name === 'detail') { selected = key || selected; detailTab = 'overview'; }
    if (name === 'offer') selectedOffer = key || selectedOffer;
    document.querySelector('.cd-shell').classList.remove('cd-nav-open'); document.getElementById('menu').setAttribute('aria-expanded', 'false');
    render(); main.focus(); window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function offerRows(items) {
    return items.map(item => `<article class="cd-offer"><div><h3>${esc(item.title)}</h3><p class="cd-muted cd-small">${esc(store.company(item).name)} · DEMO</p><div class="cd-meta"><span>${esc(item.location)} · ${esc(item.mode)}</span><span>${esc(item.contract)}</span></div><p class="cd-small">${esc(item.direction)}</p><p class="cd-small cd-muted">Kompetencje do sprawdzenia${item.deadline && item.deadline < M.today() ? ' · Termin oferty minął' : ''}</p></div>${button('Zobacz ofertę', 'offer', item.id)}</article>`).join('');
  }
  function taskRows(items) {
    return items.length ? items.map(item => `<article class="task-row${item.done ? ' completed' : ''}"><label class="task-check"><input type="checkbox" data-task="${item.id}"${item.done ? ' checked' : ''}><span class="sr-only">${item.done ? 'Wznów' : 'Ukończ'} zadanie: ${esc(item.title)}</span></label><div class="task-copy"><h3>${esc(item.title)}</h3><p class="cd-small ${!item.done && item.due < M.today() ? 'late' : 'cd-muted'}">${date(item.due)}${!item.done && item.due < M.today() ? ' · Zaległe' : ''}${item.done ? ' · Ukończone' : ''}</p><p class="cd-small cd-muted">${appName(item.applicationId)}</p><div class="cd-actions">${button('Edytuj', 'edit-task', item.id)}${button('Usuń', 'delete-task', item.id)}</div></div></article>`).join('') : '<p class="cd-muted">Brak zadań w tym widoku.</p>';
  }
  function eventRows(items) {
    return items.length ? items.map(item => `<article class="cd-detail"><h3>${esc(item.title)}</h3><p class="cd-small">${time(item.start)} – ${esc(item.end.slice(0, 10) === item.start.slice(0, 10) ? item.end.slice(11) : time(item.end))}</p><p class="cd-muted cd-small">${appName(item.applicationId)}</p><p class="cd-small">${esc(item.place || 'Miejsce do uzupełnienia')}</p><div class="cd-actions">${button('Edytuj termin', 'edit-event', item.id)}${button('Usuń', 'delete-event', item.id)}</div></article>`).join('') : '<p class="cd-muted">Brak rozmów i spotkań w tym widoku.</p>';
  }
  function todayView() {
    const s = store.state, tasks = s.tasks.filter(item => !item.done && item.due <= M.today()).sort((a, b) => a.due.localeCompare(b.due));
    const next = s.events.filter(item => M.warsawTime(item.start) >= Date.now()).sort((a, b) => a.start.localeCompare(b.start))[0];
    return heading('Dzisiaj', `${date(M.today())} · wybierz kolejny krok w poszukiwaniu pracy`) + `<div class="cd-summary"><span><strong>${s.offers.length}</strong> ofert DEMO</span><span><strong>${s.applications.length}</strong> aplikacje DEMO</span><span><strong>${tasks.length}</strong> zadań na dziś i zaległych</span></div><div class="cd-columns"><div><section class="cd-priority"><p class="cd-kicker">Najbliższy krok</p><h2>${tasks.length ? esc(tasks[0].title) : 'Przejrzyj oferty w obu kierunkach'}</h2><p>Marketing i treści z AI oraz automatyzacje. Porównaj wymagania z własnym profilem, zanim przygotujesz dokument.</p>${nav('Przejrzyj oferty', 'offers')}</section><section class="cd-section"><div class="cd-section-head"><h2>Oferty do przejrzenia</h2>${nav('Wszystkie oferty', 'offers')}</div>${offerRows(s.offers.slice(0, 3)) || empty('Nie ma ofert', 'Dodaj przykład, aby sprawdzić cały proces.', button('Dodaj ofertę', 'add-offer'))}</section><section class="cd-section"><div class="cd-section-head"><h2>Na dziś i zaległe</h2>${button('Dodaj zadanie', 'add-task')}</div>${taskRows(tasks)}</section></div><aside class="cd-aside">${panel('Najbliższa rozmowa', next ? `<p class="cd-time">${esc(next.start.slice(11))}</p><p>${date(next.start.slice(0, 10))}</p><p class="cd-small cd-muted">${appName(next.applicationId)}</p><p class="cd-small">Europe/Warsaw · DEMO</p><div class="cd-actions">${nav('Otwórz plan', 'plan')}</div>` : '<p class="cd-muted">Nie ma zaplanowanej rozmowy.</p>')}${panel('Do uzupełnienia', '<p class="cd-small">CV i historia zawodowa czekają na import. Podane umiejętności są deklaracjami; portfolio nie zostało odczytane.</p><div class="cd-actions">' + nav('Zobacz profil', 'profile') + '</div>')}${panel('Asystent AI', '<p class="cd-small">Model i źródła ofert nie są połączone. Możesz obejrzeć proces CV MASTER AI.</p><div class="cd-actions">' + nav('Otwórz asystenta', 'assistant') + '</div>')}</aside></div>`;
  }
  function offersView() {
    const locations = [...new Set(store.state.offers.map(item => item.location))].sort();
    const filtered = store.state.offers.filter(item => Object.entries(filters).every(([key, value]) => !value || item[key] === value));
    return heading('Oferty', 'Twoje kierunki: marketing i treści z AI oraz automatyzacje.', button('Dodaj ofertę', 'add-offer', '', true)) + `<div class="cd-filters">${[['direction', 'Kierunek', M.DIRECTIONS], ['location', 'Lokalizacja', locations], ['mode', 'Tryb pracy', M.MODES], ['contract', 'Umowa', M.CONTRACTS]].map(([key, label, values]) => `<label for="filter-${key}">${label}<select class="cd-field" id="filter-${key}" data-filter="${key}">${options(values, filters[key], 'Wszystkie')}</select></label>`).join('')}</div><div class="cd-section-head"><p class="cd-small cd-muted" aria-live="polite">Wyniki: ${filtered.length} z ${store.state.offers.length} ofert DEMO</p>${button('Wyczyść filtry', 'clear-filters')}</div>${filtered.length ? offerRows(filtered) : empty('Brak pasujących ofert', 'Zmień lub wyczyść filtry, aby zobaczyć pozostałe przykłady.', button('Wyczyść filtry', 'clear-filters'))}`;
  }
  function offerView() {
    const item = currentOffer(), app = store.state.applications.find(record => record.offerId === item.id);
    return heading(item.title, `${store.company(item).name} · oferta DEMO`, button('Edytuj ofertę', 'edit-offer', item.id)) + `<div class="cd-columns"><div><section class="cd-detail"><h2>Warunki i opis</h2><dl><dt>Lokalizacja</dt><dd>${esc(item.location)}</dd><dt>Tryb</dt><dd>${esc(item.mode)}</dd><dt>Umowa</dt><dd>${esc(item.contract)}</dd><dt>Kierunek</dt><dd>${esc(item.direction)}</dd><dt>Termin</dt><dd>${date(item.deadline)}${item.deadline && item.deadline < M.today() ? ' · Termin minął' : ''}</dd><dt>Źródło</dt><dd>${item.url ? `<span class="long-text">${esc(item.url)}</span>` : 'Brak linku — wpis ręczny'}</dd></dl><p class="preserve">${esc(item.description || 'Treść oferty nie została dodana.')}</p>${item.url && !new URL(item.url).hostname.endsWith('example.com') ? `<div class="cd-actions"><a class="cd-button" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Otwórz źródło w nowej karcie</a></div>` : ''}</section><div class="cd-notice"><strong>Dopasowanie wymaga sprawdzenia</strong>Nie wykonano analizy AI. Sam kierunek, miasto i rodzaj umowy nie potwierdzają kompetencji.</div></div><aside>${panel('Kolejny krok', `<p class="cd-small">${app ? 'Ta oferta ma już jedną powiązaną aplikację.' : 'Utwórz aplikację, aby powiązać zadania, notatki i materiały.'}</p><div class="cd-actions">${button(app ? 'Otwórz aplikację' : 'Utwórz aplikację DEMO', app ? 'detail' : 'create-application', app ? app.id : item.id, true)}</div>`)}</aside></div>`;
  }
  function applicationsView() {
    const items = store.state.applications.filter(item => !appFilter || item.status === appFilter);
    return heading('Aplikacje', 'Jedna oferta, jedna historia i powiązane materiały.', nav('Wybierz ofertę', 'offers')) + `<div class="cd-filters"><label for="app-filter">Status<select class="cd-field" id="app-filter">${options(M.STATUSES, appFilter, 'Wszystkie')}</select></label></div>${items.length ? `<table class="cd-table"><caption class="sr-only">Aplikacje demonstracyjne</caption><thead><tr><th scope="col">Stanowisko i firma</th><th scope="col">Status</th><th scope="col">Otwartych zadań</th><th scope="col">Szczegóły</th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${esc(store.offer(item).title)}</strong><p class="cd-muted">${esc(store.company(store.offer(item)).name)} · DEMO</p></td><td data-label="Status">${esc(item.status)}</td><td data-label="Otwarte zadania">${store.state.tasks.filter(task => task.applicationId === item.id && !task.done).length}</td><td>${button('Otwórz aplikację', 'detail', item.id)}</td></tr>`).join('')}</tbody></table>` : empty('Brak aplikacji w tym widoku', 'Utwórz aplikację z oferty lub zmień filtr statusu.', nav('Przejrzyj oferty', 'offers'))}`;
  }
  function linkedMaterials(key) { return store.state.links.filter(item => item.applicationId === key).map(item => store.find('materials', item.materialId)); }
  function materialRows(items) {
    return items.length ? items.map(item => `<article class="cd-detail"><h3>${esc(item.title)}</h3><p class="cd-meta"><span>${esc(item.kind)}</span><span>Wersja ${esc(item.version)}</span><span>DEMO · bez pliku</span></p><p class="preserve cd-small">${esc(item.description)}</p></article>`).join('') : '<p class="cd-muted">Brak przypiętych materiałów. Wybierz istniejącą wersję z biblioteki.</p>';
  }
  function detailView() {
    const app = currentApp(); if (!app) return empty('Wybierz aplikację', 'Utwórz aplikację z zapisanej oferty.', nav('Otwórz oferty', 'offers'));
    const item = store.offer(app);
    let content;
    if (detailTab === 'overview') {
      content = `<div class="cd-columns"><div><section class="cd-detail"><h2>Podsumowanie</h2><p>${esc(item.location)} · ${esc(item.mode)} · ${esc(item.contract)}</p><p class="cd-small cd-muted">Status: ${esc(app.status)}. Nie połączono poczty ani portalu rekrutacyjnego.</p><div class="cd-actions">${button('Zobacz ofertę', 'offer', item.id)}${button('Zmień status', 'status', app.id)}</div></section><section class="cd-section"><div class="cd-section-head"><h2>Powiązane zadania</h2>${button('Dodaj zadanie', 'add-task', app.id)}</div>${taskRows(store.state.tasks.filter(task => task.applicationId === app.id))}</section><section class="cd-section"><div class="cd-section-head"><h2>Rozmowy i terminy</h2>${button('Dodaj rozmowę', 'add-event', app.id)}</div>${eventRows(store.state.events.filter(event => event.applicationId === app.id))}</section><section class="cd-section"><div class="cd-section-head"><h2>Notatki</h2>${button('Dodaj notatkę', 'add-note', app.id)}</div>${store.state.notes.filter(note => note.applicationId === app.id).map(note => `<article class="cd-detail"><p class="preserve">${esc(note.text)}</p><p class="cd-small cd-muted">${stamp(note.at)} · DEMO</p>${button('Usuń notatkę', 'delete-note', note.id)}</article>`).join('') || '<p class="cd-muted">Brak notatek.</p>'}</section></div><aside>${panel('Przygotowanie aplikacji', '<p class="cd-small">Przejdź przez sześć kroków CV MASTER AI na tych samych danych. To podgląd procesu; model nie jest połączony.</p><div class="cd-actions">' + button('Przygotuj z CV MASTER AI', 'assistant', app.id, true) + '</div>')}${panel('Wersje materiałów', `<p class="cd-small">Przypiętych: ${linkedMaterials(app.id).length}. To odwołania do biblioteki, bez kopii.</p><div class="cd-actions">${button('Zobacz dokumenty', 'documents', app.id)}</div>`)}</aside></div>`;
    } else if (detailTab === 'match') {
      content = `<div class="cd-notice"><strong>Nie wykonano analizy tej oferty</strong>Treść została wpisana ręcznie lub pochodzi z przykładu. Nie ma oceny ATS ani procentu szans.</div><section class="cd-detail"><h2>Wymagania do analizy</h2><p class="preserve">${esc(item.description || 'Uzupełnij treść oferty.')}</p><h3>Znane deklaracje</h3><p>Automatyzacja produkcji treści. Projekty n8n istnieją, ale ich zawartość nie została odczytana.</p><h3>W nauce i braki</h3><p>Materiały audiowizualne z AI — w nauce. Brakuje zaimportowanego CV, dat doświadczenia i dowodów projektów.</p></section>${button('Zobacz proces dopasowania', 'assistant', app.id)}`;
    } else if (detailTab === 'documents') {
      content = `<div class="cd-section-head"><h2>Przypięte wersje</h2>${button('Przypnij materiał', 'pin-material', app.id)}</div>${materialRows(linkedMaterials(app.id))}<div class="cd-notice"><strong>Materiał DEMO nie jest dokumentem do wysłania</strong>Nie wygenerowano PDF/DOCX. Nową wersję dodaje się osobno; powiązanie aplikacji pozostaje przy wybranej wersji.</div>`;
    } else {
      content = `<ol class="cd-timeline">${[...app.history].reverse().map(item => `<li><p>${esc(item.text)}</p><p class="cd-small cd-muted">${stamp(item.at)} · DEMO</p></li>`).join('')}</ol>`;
    }
    return heading(item.title, `${store.company(item).name} · ${app.status} · aplikacja DEMO`) + `<div class="cd-tabs" role="group" aria-label="Sekcje aplikacji">${[['overview', 'Przegląd'], ['match', 'Dopasowanie'], ['documents', 'Dokumenty'], ['history', 'Historia']].map(([key, label]) => `<button type="button" data-tab="${key}" aria-pressed="${detailTab === key}">${label}</button>`).join('')}</div>${content}`;
  }
  function planView() {
    const tasks = store.state.tasks.filter(item => planFilter === 'all' || (planFilter === 'done' ? item.done : !item.done)).sort((a, b) => a.due.localeCompare(b.due));
    const events = [...store.state.events].sort((a, b) => a.start.localeCompare(b.start));
    return heading('Plan', 'Zadania i rozmowy · wszystkie godziny w Europe/Warsaw.', `<div class="cd-actions">${button('Dodaj zadanie', 'add-task', '', true)}${button('Dodaj rozmowę', 'add-event')}</div>`) + `<div class="cd-columns"><section class="cd-section"><div class="cd-section-head"><h2>Zadania</h2><label for="plan-filter" class="cd-small">Pokaż <select id="plan-filter" class="cd-field">${options([{ id: 'open', label: 'Otwarte' }, { id: 'done', label: 'Ukończone' }, { id: 'all', label: 'Wszystkie' }], planFilter)}</select></label></div>${taskRows(tasks)}</section><section class="cd-section"><h2>Rozmowy i spotkania</h2><div class="spaced">${eventRows(events)}</div></section></div>`;
  }
  function profileView() {
    return heading('Mój profil', 'Źródło: Twoje odpowiedzi w wywiadzie. Profil jest wspólny dla wszystkich aplikacji.') + `<div class="cd-columns"><div><section class="cd-detail"><h2>Cel i preferencje</h2><p>Szukasz pracy i rozwijasz umiejętności AI. Uwzględniamy marketing i treści z AI oraz automatyzacje i wdrożenia AI.</p><dl><dt>Umowy</dt><dd>Umowa o pracę, ewentualnie umowa zlecenie</dd><dt>Stacjonarnie / hybrydowo</dt><dd>Zawiercie, Kraków, Katowice, Częstochowa i okolice</dd><dt>Zdalnie</dt><dd>Cała Polska</dd><dt>Urządzenie</dt><dd>Komputer</dd><dt>Budżet usług</dt><dd>0 zł miesięcznie</dd></dl></section><section class="cd-detail"><h2>Umiejętności i materiały</h2><ul class="cd-checklist"><li><strong>Deklaracja użytkownika:</strong> automatyzacja produkcji poszczególnych treści.</li><li><strong>W nauce:</strong> tworzenie materiałów audiowizualnych w AI.</li><li><strong>Materiały istnieją, nie odczytano:</strong> CV, LinkedIn, Drive, projekty n8n, rozwijany GitHub i własna strona.</li></ul></section></div><aside>${panel('Brakujące dane', '<p class="cd-small">Import CV, daty i zakres doświadczenia, poziomy języków oraz dowody projektów. Uzupełnianie nastąpi w aplikacji z trwałym zapisem.</p>')}${panel('Zasada CV MASTER AI', '<p class="cd-small">Nie dopisujemy fikcyjnych osiągnięć. Informacje z wcześniejszych opisów AI wymagają potwierdzenia; nauka nie staje się opanowaną umiejętnością.</p>')}</aside></div>`;
  }
  function materialsView() {
    return heading('Materiały', 'Biblioteka opisów DEMO. Bez importowania plików i dostępu do Drive.', button('Dodaj opis materiału', 'add-material', '', true)) + materialRows(store.state.materials) + `<div class="cd-notice"><strong>Twoje materiały nie zostały zaimportowane</strong>Opis nowej wersji w DEMO nie tworzy CV i nie zmienia przypiętych wcześniej wersji. Prawdziwe pliki i ich wersje będą obsługiwane w kolejnych etapach.</div>`;
  }
  const steps = ['Profil', 'Research', 'Dopasowanie', 'Materiały', 'Kontrola', 'Akceptacja'];
  function assistantView() {
    const app = currentApp();
    const contents = [
      '<h2>1. Wspólny MASTER PROFILE</h2><p>Asystent korzysta z istniejącego profilu. Nie rozpoczyna kolejnego ogólnego wywiadu. Brakujące fakty zostają na liście do uzupełnienia.</p><ul class="cd-checklist"><li>Podane przez Ciebie: automatyzacja produkcji treści.</li><li>W nauce: materiały audiowizualne z AI.</li><li>Brak: odczytane CV, daty doświadczenia i dowody projektów.</li></ul>',
      '<h2>2. Research firmy</h2><p>Nie wykonano. Firmy DEMO są fikcyjne, a internet i źródła nie zostały połączone. W przyszłości każde ustalenie będzie miało źródło i datę odczytu.</p>',
      `<h2>3. Wymaganie → dowód → luka</h2><p class="preserve">${esc(app ? store.offer(app).description || 'Brak treści oferty.' : 'Wybierz aplikację, aby zobaczyć jej wymagania.')}</p><p>Nie wykonano oceny AI. Dowody wymagają odczytania rzeczywistych projektów. Niepotwierdzone fakty nie zostaną użyte w CV.</p>`,
      `<h2>4. Wybór materiałów</h2><p>Nie wygenerowano dokumentów. Poniżej opisy wersji DEMO przypięte do wybranej aplikacji.</p><div class="spaced">${app ? materialRows(linkedMaterials(app.id)) : '<p>Wybierz aplikację.</p>'}</div>${app ? button('Przypnij materiał DEMO', 'pin-material', app.id) : ''}`,
      '<h2>5. Kontrola dokumentu</h2><p>Kontrola niewykonana: brak wygenerowanego dokumentu i skonfigurowanego modelu.</p><ul class="cd-checklist"><li>Prawdziwość i źródła twierdzeń.</li><li>Daty, dane kontaktowe i oznaczenie umiejętności w nauce.</li><li>Dopasowanie do oferty i czytelność tekstu.</li><li>Podgląd pliku PDF/DOCX przed uznaniem go za gotowy.</li></ul>',
      '<h2>6. Akceptacja i wysyłka</h2><p>Nie ma dokumentu gotowego do akceptacji ani podłączonego kanału wysyłki. W przyszłości zobaczysz treść, odbiorcę i konkretne wersje załączników przed potwierdzeniem.</p><div class="cd-actions"><button type="button" class="cd-button" disabled>Wyślij — brak integracji</button></div>'
    ];
    return heading('CV MASTER AI', 'Twój agent kariery · demonstracja procesu, bez aktywnego modelu.') + `<div class="cd-notice"><strong>Model nie jest połączony</strong>Kroki pokazują kontekst i zasady. Kliknięcie „Dalej” nie wykonuje researchu, analizy ani generowania.</div><label class="context-label" for="ai-context">Kontekst aplikacji<select class="cd-field" id="ai-context">${options(store.state.applications.map(item => ({ id: item.id, label: store.applicationLabel(item.id) })), app ? app.id : '', 'Wybierz aplikację')}</select></label><div class="cd-steps spaced" role="group" aria-label="Kroki CV MASTER AI">${steps.map((label, index) => `<button type="button" data-step="${index}" aria-pressed="${index === aiStep}">${index + 1}. ${label}</button>`).join('')}</div><section class="cd-detail">${contents[aiStep]}</section><div class="cd-actions">${aiStep > 0 ? button('Poprzedni krok', 'previous-step') : ''}${aiStep < 5 ? button('Dalej — podgląd', 'next-step', '', true) : ''}${app ? button('Wróć do aplikacji', 'detail', app.id) : ''}</div><details class="cd-inline-details"><summary>Instrukcja i granice uprawnień</summary><p>Do aplikacji włączono projekt zachowania z Twojej instrukcji CV MASTER AI. Oryginał zachowano bez zmian. Instrukcja nie nadaje dostępu do bazy, poczty ani modelu; integracje wymagają konfiguracji w etapie 5.</p><p><a href="../docs/materialy/cv-master-ai-oryginal.txt" target="_blank" rel="noopener noreferrer">Zobacz oryginalną instrukcję</a></p></details>`;
  }
  function settingsView() {
    return heading('Ustawienia', 'Stan prototypu i przyszłych integracji.') + `<div class="cd-grid2"><section class="cd-detail"><h2>Dane i koszty</h2><p>Zmiany są tylko w pamięci tej karty. Odświeżenie przywraca DEMO. Nie ma bazy ani kopii zapasowych.</p><p class="cd-small">Sam prototyp nie używa płatnych usług ani pobieranych zasobów. W etapie 4 planujemy lokalną bazę i backupy; sprzęt oraz miejsce na dysku pozostają po Twojej stronie.</p><div class="cd-actions">${button('Przywróć dane DEMO', 'reset')}</div></section><section class="cd-detail"><h2>Integracje</h2><ul class="cd-checklist"><li>ChatGPT / Claude / Gemini / model lokalny: niepołączone</li><li>AOL: niepołączone; brak odczytu i wysyłki</li><li>Kalendarz zewnętrzny: niepołączony</li><li>Portale, grupy i LinkedIn: ręczne dodawanie; brak automatycznego wyszukiwania</li><li>Drive / GitHub / n8n: niepołączone</li></ul></section></div>`;
  }
  function searchView() {
    const results = store.search(query);
    return heading('Wyniki wyszukiwania', `Szukasz: „${query}” · wyniki: ${results.length}`) + (results.length ? results.map(item => `<article class="cd-offer"><div><p class="cd-kicker">${item.kind} · DEMO</p><h2 class="preserve">${esc(item.title)}</h2><p class="cd-small cd-muted">${esc(item.detail)}</p></div>${button('Otwórz wynik', `result-${item.screen}`, item.key)}</article>`).join('') : empty('Brak wyników', 'Szukamy w ofertach, aplikacjach, zadaniach, terminach, notatkach i opisach materiałów. Nie przeszukujemy internetu.', button('Wyczyść wyszukiwanie', 'clear-search')));
  }
  function render() {
    const views = { today: todayView, offers: offersView, offer: offerView, applications: applicationsView, detail: detailView, plan: planView, profile: profileView, materials: materialsView, assistant: assistantView, settings: settingsView, search: searchView };
    main.innerHTML = views[screen]();
    const navScreen = screen === 'offer' ? 'offers' : screen === 'detail' ? 'applications' : screen;
    document.querySelectorAll('.cd-nav button').forEach(item => { if (item.dataset.screen === navScreen) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current'); });
    document.title = `${main.querySelector('h1')?.textContent || 'Centrum Dowodzenia'} · DEMO`;
  }
  function showDialog(title, fields, submitLabel, callback) {
    opener = document.activeElement;
    body.innerHTML = `<div class="cd-dialog-head"><h2 id="dialog-title">${esc(title)}</h2><button type="button" class="cd-button" data-action="close-dialog" aria-label="Zamknij formularz">Zamknij</button></div><form id="edit-form" novalidate><p class="cd-small cd-muted spaced">DEMO · zmiany znikają po odświeżeniu. Pola z * są wymagane.</p><p id="form-error" class="field-error" role="alert" hidden></p>${fields}<div class="cd-actions"><button class="cd-button cd-primary" type="submit">${esc(submitLabel)}</button><button class="cd-button" type="button" data-action="close-dialog">Anuluj</button></div></form>`;
    onSubmit = callback;
    if (!dialog.open) dialog.showModal();
    (body.querySelector('input, textarea, select') || body.querySelector('button[type=submit]')).focus();
  }
  function closeDialog() { dialog.close(); if (opener?.isConnected) opener.focus(); else main.focus(); }
  function errors(error) {
    const top = document.getElementById('form-error'); top.hidden = false; top.textContent = error instanceof M.ValidationError ? 'Popraw wskazane pola.' : 'Nie udało się zapisać danych DEMO.';
    Object.entries(error.errors || {}).forEach(([name, message]) => { const field = body.querySelector(`[name="${name}"]`), text = document.getElementById(`err-${name}`); if (field) field.setAttribute('aria-invalid', 'true'); if (text) { text.textContent = message; text.hidden = false; } });
    (body.querySelector('[aria-invalid=true]') || top).focus();
  }
  function offerDialog(key) {
    const item = key ? store.find('offers', key) : { title: '', location: '', description: '', url: '', deadline: '', direction: M.DIRECTIONS[0], mode: M.MODES[1], contract: M.CONTRACTS[0] };
    showDialog(key ? 'Edytuj ofertę DEMO' : 'Dodaj ofertę DEMO', field('title', 'Stanowisko', item.title, 'text', true, 180) + field('company', 'Firma', key ? store.company(item).name : '', 'text', true, 120) + field('location', 'Lokalizacja', item.location, 'text', true, 120) + select('direction', 'Kierunek', M.DIRECTIONS, item.direction) + select('mode', 'Tryb pracy', M.MODES, item.mode) + select('contract', 'Umowa', M.CONTRACTS, item.contract) + field('url', 'Link źródłowy (opcjonalnie)', item.url, 'url', false, 2000) + '<p class="cd-small cd-muted">Duplikaty sprawdzamy według linku oraz firmy i stanowiska.</p>' + field('deadline', 'Termin aplikowania (opcjonalnie)', item.deadline, 'date') + textarea('description', 'Treść i wymagania (opcjonalnie)', item.description, false, 12000), 'Zapisz ofertę DEMO', input => { const record = store.saveOffer(input, key); closeDialog(); navigate('offer', record.id); announce('Zapisano ofertę DEMO. Zmiany są tylko w tej karcie.'); });
  }
  function taskDialog(key, appId) {
    const item = key ? store.find('tasks', key) : { title: '', due: M.today(), applicationId: appId || '' };
    showDialog(key ? 'Edytuj zadanie DEMO' : 'Dodaj zadanie DEMO', field('title', 'Zadanie', item.title, 'text', true) + field('due', 'Termin — dzień w Europe/Warsaw', item.due, 'date', true) + appSelect(item.applicationId), 'Zapisz zadanie DEMO', input => { store.saveTask(input, key); closeDialog(); render(); announce('Zapisano zadanie DEMO i jego powiązanie.'); });
  }
  function eventDialog(key, appId) {
    const day = M.dayOffset(M.today(), 1), item = key ? store.find('events', key) : { title: 'Rozmowa kwalifikacyjna — DEMO', start: `${day}T10:00`, end: `${day}T10:30`, applicationId: appId || '', place: '' };
    showDialog(key ? 'Edytuj rozmowę DEMO' : 'Dodaj rozmowę DEMO', field('title', 'Nazwa', item.title, 'text', true) + '<p class="cd-small spaced">Godziny w Europe/Warsaw, niezależnie od strefy komputera.</p>' + field('start', 'Początek', item.start, 'datetime-local', true) + field('end', 'Koniec', item.end, 'datetime-local', true) + field('place', 'Miejsce lub informacje o połączeniu', item.place, 'text', false, 500) + appSelect(item.applicationId), 'Zapisz termin DEMO', input => { store.saveEvent(input, key); closeDialog(); render(); announce('Zapisano termin DEMO. Nie dodano wydarzenia do zewnętrznego kalendarza.'); });
  }
  function statusDialog(key) {
    const app = store.find('applications', key);
    showDialog('Zmień status aplikacji DEMO', select('status', 'Status', M.STATUSES, app.status) + '<p class="cd-small spaced">„Wysłana” to Twoje ręczne oznaczenie. Prototyp niczego nie wysyła.</p>', 'Zapisz status DEMO', input => {
      if (input.status === 'Wysłana' && app.status !== 'Wysłana') {
        showDialog('Potwierdź oznaczenie wysłania', '<p class="spaced">Oznaczysz jako „Wysłana” przykładową aplikację: <strong>' + appName(key) + '</strong>. Wiadomość ani dokument nie zostaną wysłane. Czy potwierdzasz ręczne oznaczenie w DEMO?</p>', 'Potwierdzam oznaczenie DEMO', () => { store.setStatus(key, input.status, true); closeDialog(); render(); announce('Zmieniono status DEMO po potwierdzeniu. Niczego nie wysłano.'); });
      } else { store.setStatus(key, input.status, true); closeDialog(); render(); announce('Zmieniono status DEMO; wpisano zmianę do historii.'); }
    });
  }
  function deleteDialog(table, key) {
    const item = store.find(table, key);
    showDialog('Potwierdź usunięcie DEMO', `<p class="preserve spaced">Usuniesz ${esc(item.title || item.text)}. Powiązana aplikacja i inne rekordy pozostaną.</p>`, 'Usuń rekord DEMO', () => { store.remove(table, key, true); closeDialog(); render(); announce('Usunięto wskazany rekord DEMO.'); });
  }
  function pinDialog(appId) {
    const app = store.find('applications', appId);
    const candidates = store.state.materials.filter(item => !store.state.links.some(link => link.applicationId === app.id && link.materialId === item.id));
    if (!candidates.length) { announce('Wszystkie istniejące wersje są już przypięte do tej aplikacji. Dodaj nowy opis w Materiałach.'); return; }
    showDialog('Przypnij materiał DEMO', `<p class="spaced cd-small">${appName(appId)}. Wybierasz odwołanie do istniejącej wersji, bez kopiowania.</p>` + select('materialId', 'Materiał i wersja', candidates.map(item => ({ id: item.id, label: `${item.title} · v${item.version}` })), candidates[0].id), 'Przypnij wersję DEMO', input => { store.pinMaterial(appId, input.materialId); closeDialog(); render(); announce('Przypięto istniejącą wersję materiału DEMO.'); });
  }
  function action(name, key) {
    if (name.startsWith('result-')) {
      const dest = name.slice(7); navigate(dest, key);
      if (dest === 'plan') { planFilter = 'all'; render(); const item = main.querySelector(`[data-key="${CSS.escape(key)}"]`); item?.focus(); item?.scrollIntoView({ block: 'center' }); }
      if (dest === 'materials') announce('Otworzono bibliotekę; wynik: ' + store.find('materials', key).title);
      return;
    }
    switch (name) {
      case 'add-offer': offerDialog(); break;
      case 'edit-offer': offerDialog(key); break;
      case 'offer': navigate('offer', key); break;
      case 'detail': navigate('detail', key); break;
      case 'create-application': { const app = store.createApplication(key); navigate('detail', app.id); announce('Otwarto jedną aplikację DEMO powiązaną z ofertą.'); break; }
      case 'add-task': taskDialog('', key); break;
      case 'edit-task': taskDialog(key); break;
      case 'add-event': eventDialog('', key); break;
      case 'edit-event': eventDialog(key); break;
      case 'delete-task': deleteDialog('tasks', key); break;
      case 'delete-event': deleteDialog('events', key); break;
      case 'delete-note': deleteDialog('notes', key); break;
      case 'status': statusDialog(key); break;
      case 'add-note': showDialog('Dodaj notatkę DEMO', textarea('text', 'Notatka', '', true), 'Zapisz notatkę DEMO', input => { store.addNote({ ...input, applicationId: key }); closeDialog(); render(); announce('Dodano notatkę do wybranej aplikacji DEMO.'); }); break;
      case 'add-material': showDialog('Dodaj opis materiału DEMO', field('title', 'Nazwa', '', 'text', true, 180) + select('kind', 'Typ', ['CV', 'Portfolio', 'List', 'Wiadomość', 'Inny'], 'CV') + field('version', 'Wersja', '1', 'text', true, 30) + textarea('description', 'Opis — bez pliku', ''), 'Dodaj wersję DEMO', input => { store.addMaterial(input); closeDialog(); render(); announce('Dodano opis wersji DEMO. Nie utworzono pliku dokumentu.'); }); break;
      case 'pin-material': pinDialog(key); break;
      case 'documents': selected = key; screen = 'detail'; detailTab = 'documents'; render(); main.focus(); break;
      case 'assistant': selected = key; aiStep = 0; navigate('assistant'); break;
      case 'next-step': aiStep = Math.min(5, aiStep + 1); render(); main.focus(); break;
      case 'previous-step': aiStep = Math.max(0, aiStep - 1); render(); main.focus(); break;
      case 'clear-filters': filters = { direction: '', location: '', mode: '', contract: '' }; render(); main.focus(); break;
      case 'clear-search': query = ''; document.getElementById('search').value = ''; navigate('today'); document.getElementById('search').focus(); break;
      case 'close-dialog': closeDialog(); break;
      case 'reset': showDialog('Przywrócić dane DEMO?', '<p class="spaced">Wszystkie zmiany w tej karcie zostaną usunięte i zastąpione pierwotnymi przykładami. To nie jest odzyskiwanie z kopii zapasowej.</p>', 'Przywróć przykłady DEMO', () => { store.reset(); selected = 'a1'; selectedOffer = 'o1'; filters = { direction: '', location: '', mode: '', contract: '' }; query = ''; appFilter = ''; planFilter = 'open'; aiStep = 0; document.getElementById('search').value = ''; closeDialog(); navigate('today'); announce('Przywrócono pierwotne przykłady DEMO.'); }); break;
    }
  }
  document.getElementById('app').addEventListener('click', event => {
    const target = event.target.closest('button'); if (!target) return;
    if (target.dataset.screen) navigate(target.dataset.screen);
    else if (target.dataset.action) action(target.dataset.action, target.dataset.key);
    else if (target.dataset.tab) { detailTab = target.dataset.tab; render(); main.querySelector(`[data-tab="${detailTab}"]`).focus(); }
    else if (target.dataset.step) { aiStep = Number(target.dataset.step); render(); main.querySelector(`[data-step="${aiStep}"]`).focus(); }
  });
  document.getElementById('menu').addEventListener('click', () => { const open = document.querySelector('.cd-shell').classList.toggle('cd-nav-open'); document.getElementById('menu').setAttribute('aria-expanded', String(open)); if (open) document.querySelector('.cd-nav button').focus(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !dialog.open) { document.querySelector('.cd-shell').classList.remove('cd-nav-open'); document.getElementById('menu').setAttribute('aria-expanded', 'false'); } });
  document.getElementById('search-form').addEventListener('submit', event => { event.preventDefault(); query = document.getElementById('search').value.trim(); if (query) navigate('search'); else navigate('today'); });
  main.addEventListener('change', event => {
    const target = event.target;
    if (target.dataset.filter) { filters[target.dataset.filter] = target.value; render(); document.getElementById(target.id).focus(); }
    else if (target.dataset.task) { store.toggleTask(target.dataset.task); render(); const checkbox = main.querySelector(`[data-task="${target.dataset.task}"]`); (checkbox || main).focus(); announce(target.checked ? 'Ukończono zadanie DEMO.' : 'Wznowiono zadanie DEMO.'); }
    else if (target.id === 'app-filter') { appFilter = target.value; render(); document.getElementById('app-filter').focus(); }
    else if (target.id === 'plan-filter') { planFilter = target.value; render(); document.getElementById('plan-filter').focus(); }
    else if (target.id === 'ai-context') { selected = target.value; render(); document.getElementById('ai-context').focus(); }
  });
  body.addEventListener('submit', event => {
    event.preventDefault(); body.querySelectorAll('[aria-invalid]').forEach(item => item.removeAttribute('aria-invalid')); body.querySelectorAll('.field-error').forEach(item => { item.hidden = true; });
    try { onSubmit(Object.fromEntries(new FormData(event.target))); } catch (error) { errors(error); }
  });
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(); });
  render();
})();
