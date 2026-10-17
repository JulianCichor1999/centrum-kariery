/* Jedno źródło rekordów DEMO. Żadnego zapisu trwałego ani żądań sieciowych. */
(function (root) {
  'use strict';
  const STATUSES = ['Przygotowanie', 'Wysłana', 'Rozmowa', 'Oferta współpracy', 'Odmowa', 'Wycofana'];
  const DIRECTIONS = ['Marketing i treści z AI', 'Automatyzacje i wdrożenia AI', 'Inne'];
  const MODES = ['Stacjonarna', 'Hybrydowa', 'Zdalna'];
  const CONTRACTS = ['Umowa o pracę', 'Umowa zlecenie'];
  const fold = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ł/g, 'l').replace(/Ł/g, 'L').toLowerCase().replace(/\s+/g, ' ').trim();
  const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw' }).format(new Date());
  function dayOffset(day, offset) { const d = new Date(`${day}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + offset); return d.toISOString().slice(0, 10); }
  function validDate(value) { return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T12:00:00Z`)) && new Date(`${value}T12:00:00Z`).toISOString().slice(0, 10) === value; }
  function warsawTime(value) {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) || !validDate(value.slice(0, 10))) return null;
    const base = Date.parse(`${value}:00Z`);
    if (Number.isNaN(base)) return null;
    const fmt = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    const candidates = [60, 120].map(offset => base - offset * 60000).filter(ms => fmt.format(new Date(ms)).replace(' ', 'T') === value);
    return candidates.length === 1 ? candidates[0] : null;
  }
  function canonicalUrl(value) {
    try {
      const url = new URL(value);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
      url.hash = '';
      for (const key of [...url.searchParams.keys()]) if (/^utm_/i.test(key) || /^(fbclid|gclid)$/i.test(key)) url.searchParams.delete(key);
      url.searchParams.sort(); url.pathname = url.pathname.replace(/\/$/, '') || '/';
      return url.href;
    } catch { return null; }
  }
  class ValidationError extends Error { constructor(errors) { super('Popraw dane formularza.'); this.errors = errors; } }
  function fail(errors) { if (Object.keys(errors).length) throw new ValidationError(errors); }
  function textField(value, key, errors, max, required = true) { const result = String(value || '').trim(); if (required && !result) errors[key] = 'Uzupełnij to pole.'; else if (result.length > max) errors[key] = `Maksymalnie ${max} znaków.`; return result; }
  function seed() {
    const day = today();
    return {
      companies: [{ id: 'c1', name: 'Studio Treści' }, { id: 'c2', name: 'Zespół Automatyzacji' }, { id: 'c3', name: 'Pracownia Wideo' }],
      offers: [
        { id: 'o1', companyId: 'c1', title: 'Specjalista automatyzacji treści', direction: DIRECTIONS[0], location: 'Katowice', mode: 'Hybrydowa', contract: CONTRACTS[0], url: 'https://example.com/oferty/studio-tresci', description: 'DEMO: automatyzacja tworzenia treści, praca z n8n, kontrola jakości. Wymagany przykład projektu i potwierdzenie doświadczenia.', deadline: dayOffset(day, 10), demo: true },
        { id: 'o2', companyId: 'c2', title: 'Młodszy specjalista automatyzacji', direction: DIRECTIONS[1], location: 'Polska', mode: 'Zdalna', contract: CONTRACTS[0], url: 'https://example.com/oferty/automatyzacje', description: 'DEMO: budowa przepływów w n8n, dokumentacja i testowanie. Wiedza o API do sprawdzenia w portfolio.', deadline: dayOffset(day, 14), demo: true },
        { id: 'o3', companyId: 'c3', title: 'Twórca materiałów wideo z AI', direction: DIRECTIONS[0], location: 'Kraków', mode: 'Stacjonarna', contract: CONTRACTS[1], url: 'https://example.com/oferty/wideo', description: 'DEMO: tworzenie i montaż materiałów audiowizualnych z AI. Samodzielne wykonanie filmu — luka: obecnie w nauce.', deadline: dayOffset(day, 7), demo: true }
      ],
      applications: [
        { id: 'a1', offerId: 'o1', status: 'Przygotowanie', history: [{ at: new Date().toISOString(), text: 'Utworzono przykładową aplikację DEMO.' }] },
        { id: 'a2', offerId: 'o2', status: 'Rozmowa', history: [{ at: new Date().toISOString(), text: 'Przykładowy status „Rozmowa” — nie jest to prawdziwa rekrutacja.' }] }
      ],
      tasks: [{ id: 't1', title: 'Wybrać projekt n8n do portfolio', due: day, applicationId: 'a1', done: false }, { id: 't2', title: 'Przygotować pytania do rozmowy', due: dayOffset(day, 1), applicationId: 'a2', done: false }, { id: 't3', title: 'Uzupełnić daty doświadczenia w profilu', due: dayOffset(day, -1), applicationId: '', done: false }],
      events: [{ id: 'e1', title: 'Rozmowa kwalifikacyjna — DEMO', start: `${dayOffset(day, 2)}T10:00`, end: `${dayOffset(day, 2)}T10:30`, applicationId: 'a2', place: 'Połączenie online — przykład, bez linku' }],
      notes: [{ id: 'n1', applicationId: 'a1', text: 'DEMO: przed przygotowaniem dokumentu wybierz projekt n8n i uzupełnij profil.', at: new Date().toISOString() }],
      materials: [{ id: 'm1', title: 'CV — przykładowy szkic', kind: 'CV', version: '1', description: 'DEMO: opis wersji, bez pliku PDF/DOCX i bez potwierdzonej historii zawodowej.' }, { id: 'm2', title: 'Portfolio n8n — przykładowy opis', kind: 'Portfolio', version: '1', description: 'DEMO: miejsce na dowód umiejętności. Twojego Drive i projektów nie odczytano.' }],
      links: [{ applicationId: 'a1', materialId: 'm1' }]
    };
  }
  function createStore() {
    let state = seed(), counter = 10;
    const id = prefix => `${prefix}${++counter}`;
    const find = (table, key) => { const record = state[table].find(item => item.id === key); if (!record) throw new Error('Nie znaleziono rekordu DEMO.'); return record; };
    const company = offer => find('companies', offer.companyId);
    const offer = app => find('offers', app.offerId);
    const applicationLabel = key => { if (!key) return 'Bez aplikacji'; const item = find('applications', key), vacancy = offer(item); return `${vacancy.title} · ${company(vacancy).name}`; };
    const history = (key, text) => { if (key) find('applications', key).history.push({ at: new Date().toISOString(), text }); };
    function appReference(key, errors) { if (key && !state.applications.some(item => item.id === key)) errors.applicationId = 'Wybierz istniejącą aplikację.'; }
    return {
      get state() { return state; }, find, company, offer, applicationLabel,
      reset() { state = seed(); counter = 10; },
      saveOffer(input, key) {
        const errors = {};
        if (key) find('offers', key);
        const title = textField(input.title, 'title', errors, 180), name = textField(input.company, 'company', errors, 120), location = textField(input.location, 'location', errors, 120);
        const description = textField(input.description, 'description', errors, 12000, false);
        const url = String(input.url || '').trim(), canonical = url ? canonicalUrl(url) : '';
        if (url && (!canonical || url.length > 2000)) errors.url = 'Wpisz adres HTTP/HTTPS bez loginu i hasła (maks. 2000 znaków) albo pozostaw puste.';
        if (!DIRECTIONS.includes(input.direction)) errors.direction = 'Wybierz kierunek.';
        if (!MODES.includes(input.mode)) errors.mode = 'Wybierz tryb pracy.';
        if (!CONTRACTS.includes(input.contract)) errors.contract = 'Wybierz rodzaj umowy.';
        if (input.deadline && !validDate(input.deadline)) errors.deadline = 'Wpisz prawidłową datę.';
        const duplicate = state.offers.find(item => item.id !== key && ((canonical && canonicalUrl(item.url) === canonical) || (fold(item.title) === fold(title) && fold(company(item).name) === fold(name))));
        if (duplicate) errors.url = `Taka oferta już istnieje: ${duplicate.title} · ${company(duplicate).name}. Zmień istniejący rekord.`;
        fail(errors);
        let firm = state.companies.find(item => fold(item.name) === fold(name));
        if (!firm) { firm = { id: id('c'), name }; state.companies.push(firm); }
        const record = { id: key || id('o'), companyId: firm.id, title, location, description, url, direction: input.direction, mode: input.mode, contract: input.contract, deadline: input.deadline || '', demo: true };
        if (key) { Object.assign(find('offers', key), record); state.applications.filter(item => item.offerId === key).forEach(item => history(item.id, 'Zmieniono dane powiązanej oferty DEMO.')); }
        else state.offers.push(record);
        return record;
      },
      createApplication(offerId) {
        find('offers', offerId);
        const existing = state.applications.find(item => item.offerId === offerId);
        if (existing) return existing;
        const app = { id: id('a'), offerId, status: STATUSES[0], history: [] };
        state.applications.push(app); history(app.id, 'Utworzono aplikację DEMO.'); return app;
      },
      setStatus(key, status, confirmed = false) {
        const app = find('applications', key);
        if (!STATUSES.includes(status)) throw new ValidationError({ status: 'Wybierz istniejący status.' });
        if (status === 'Wysłana' && !confirmed) throw new ValidationError({ status: 'Potwierdź ręczne oznaczenie wysłania. Prototyp nie wysyła wiadomości.' });
        if (status !== app.status) { history(key, `Status: ${app.status} → ${status}${status === 'Wysłana' ? ' (ręczne potwierdzenie DEMO, bez wysyłki)' : ''}.`); app.status = status; }
      },
      saveTask(input, key) {
        const errors = {}, title = textField(input.title, 'title', errors, 200);
        if (!validDate(input.due)) errors.due = 'Wybierz prawidłowy dzień.';
        appReference(input.applicationId, errors); fail(errors);
        const record = { id: key || id('t'), title, due: input.due, applicationId: input.applicationId || '', done: key ? find('tasks', key).done : false };
        if (key) { const oldApp = find('tasks', key).applicationId; Object.assign(find('tasks', key), record); history(oldApp, `Zmieniono zadanie DEMO: ${title}.`); if (record.applicationId !== oldApp) history(record.applicationId, `Powiązano zadanie DEMO: ${title}.`); }
        else { state.tasks.push(record); history(record.applicationId, `Dodano zadanie DEMO: ${title}.`); }
        return record;
      },
      toggleTask(key) { const task = find('tasks', key); task.done = !task.done; history(task.applicationId, `${task.done ? 'Ukończono' : 'Wznowiono'} zadanie DEMO: ${task.title}.`); },
      saveEvent(input, key) {
        const errors = {}, title = textField(input.title, 'title', errors, 200), place = textField(input.place, 'place', errors, 500, false);
        const start = warsawTime(input.start), end = warsawTime(input.end);
        if (start === null) errors.start = 'Wybierz jednoznaczną godzinę w Europe/Warsaw. Godzina zmiany czasu może nie istnieć lub wystąpić dwukrotnie.';
        if (end === null || (start !== null && end <= start)) errors.end = 'Koniec musi być późniejszy od początku; wybierz jednoznaczną godzinę.';
        appReference(input.applicationId, errors); fail(errors);
        const record = { id: key || id('e'), title, start: input.start, end: input.end, place, applicationId: input.applicationId || '' };
        if (key) { const oldApp = find('events', key).applicationId; Object.assign(find('events', key), record); history(oldApp, `Zmieniono termin DEMO: ${title}.`); if (oldApp !== record.applicationId) history(record.applicationId, `Powiązano termin DEMO: ${title}.`); }
        else { state.events.push(record); history(record.applicationId, `Dodano termin DEMO: ${title}.`); }
        return record;
      },
      addNote(input) {
        const errors = {}, text = textField(input.text, 'text', errors, 5000);
        appReference(input.applicationId, errors); if (!input.applicationId) errors.applicationId = 'Wybierz aplikację.'; fail(errors);
        const note = { id: id('n'), applicationId: input.applicationId, text, at: new Date().toISOString() }; state.notes.push(note); history(note.applicationId, 'Dodano notatkę DEMO.'); return note;
      },
      addMaterial(input) {
        const errors = {}, title = textField(input.title, 'title', errors, 180), version = textField(input.version, 'version', errors, 30), description = textField(input.description, 'description', errors, 5000, false);
        if (!['CV', 'Portfolio', 'List', 'Wiadomość', 'Inny'].includes(input.kind)) errors.kind = 'Wybierz typ materiału.';
        if (state.materials.some(item => fold(item.title) === fold(title) && fold(item.version) === fold(version))) errors.version = 'Ta nazwa i wersja już istnieją. Dodaj nową wersję.';
        fail(errors); const material = { id: id('m'), title, version, description, kind: input.kind }; state.materials.push(material); return material;
      },
      pinMaterial(applicationId, materialId) {
        find('applications', applicationId); find('materials', materialId);
        if (!state.links.some(item => item.applicationId === applicationId && item.materialId === materialId)) { state.links.push({ applicationId, materialId }); history(applicationId, 'Przypięto istniejącą wersję materiału DEMO.'); }
      },
      remove(table, key, confirmed) {
        if (!confirmed || !['tasks', 'events', 'notes'].includes(table)) throw new Error('Usuwanie wymaga potwierdzenia.');
        const record = find(table, key); state[table] = state[table].filter(item => item.id !== key); history(record.applicationId, `Usunięto ${table === 'tasks' ? 'zadanie' : table === 'events' ? 'termin' : 'notatkę'} DEMO.`);
      },
      search(query) {
        const q = fold(query), results = [];
        const add = (kind, key, title, detail, content, screen) => { if (fold(`${title} ${detail} ${content}`).includes(q)) results.push({ kind, key, title, detail, screen }); };
        if (!q) return results;
        state.offers.forEach(item => add('Oferta', item.id, item.title, company(item).name, `${item.location} ${item.direction} ${item.description} ${item.mode} ${item.contract}`, 'offer'));
        state.applications.forEach(item => add('Aplikacja', item.id, offer(item).title, `${company(offer(item)).name} · ${item.status}`, '', 'detail'));
        state.tasks.forEach(item => add('Zadanie', item.id, item.title, applicationLabel(item.applicationId), item.due, 'plan'));
        state.events.forEach(item => add('Termin', item.id, item.title, applicationLabel(item.applicationId), `${item.start} ${item.place}`, 'plan'));
        state.notes.forEach(item => add('Notatka', item.applicationId, item.text, applicationLabel(item.applicationId), '', 'detail'));
        state.materials.forEach(item => add('Materiał', item.id, item.title, `wersja ${item.version} · ${item.kind}`, item.description, 'materials'));
        return results;
      }
    };
  }
  root.CareerDemo = { createStore, STATUSES, DIRECTIONS, MODES, CONTRACTS, fold, today, dayOffset, validDate, warsawTime, canonicalUrl, ValidationError };
  if (typeof module !== 'undefined') module.exports = root.CareerDemo;
})(globalThis);
