// Test adaptera danych interfejsu przez rzeczywiste API, bez sterowania przeglądarką.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict'), {spawn} = require('node:child_process');
const {File} = require('node:buffer');
const ROOT = path.resolve(__dirname, '../..'), BASE = 'http://127.0.0.1:8770';
const PYTHON = path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe');
const directory = fs.mkdtempSync(path.join(ROOT, '.test-data/client-'));
const checks = []; let server;
const check = (name, ok = true) => {assert.ok(ok, name); checks.push(name);};
async function start() {
  server = spawn(PYTHON, ['-m', 'app.run', '--data-dir', directory, '--port', '8770'], {cwd: ROOT, windowsHide: true, stdio: 'ignore'});
  for (let i = 0; i < 100; i++) {
    try {if ((await fetch(BASE + '/health')).ok) return;} catch {}
    if (server.exitCode !== null) throw new Error('Serwer DEMO zakończył pracę.');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Serwer DEMO nie odpowiedział.');
}
async function stop() {
  if (server && server.exitCode === null) await new Promise(resolve => {server.once('exit', resolve); server.kill();});
}
async function client() {
  const response = await fetch(BASE + '/');
  const cookie = response.headers.get('set-cookie').split(';')[0];
  const rawFetch = (target, options = {}) => {
    const url = new URL(target, BASE); assert.equal(url.origin, BASE);
    return fetch(url, {...options, headers: {Cookie: cookie, ...(options.method ? {Origin: BASE} : {}), ...options.headers}});
  };
  const context = {window: {}, fetch: rawFetch, FormData, Intl, Date, URL};
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, 'app/static/model.js'), 'utf8'), context);
  return {model: context.window.CareerModel, store: await context.window.CareerModel.createStore(), rawFetch};
}
(async () => {
  try {
    await start(); let {model, store, rawFetch} = await client();
    check('Interfejs odczytuje pustą bazę DEMO przez API', store.state.offers.length === 0);
    const data = {title: 'Oferta DEMO', company: 'Firma DEMO', location: 'Zawiercie', direction: 'Inne', mode: 'Hybrydowa', contract: 'Umowa o pracę', url: 'https://example.org/client-demo', description: 'Zażółć — n8n', deadline: ''};
    let offer = await store.saveOffer(data);
    check('Inne zapisuje się przez adapter interfejsu', offer.direction === 'Inne');
    const application = await store.createApplication(offer.id);
    check('Relacja aplikacji używa tego samego rekordu', application.offerId === offer.id);
    await store.saveTask({title: 'Zadanie DEMO', due: '2026-12-01', applicationId: application.id});
    await store.saveEvent({title: 'Rozmowa DEMO', start: '2026-12-01T10:00', end: '2026-12-01T10:30', place: 'Online', applicationId: application.id});
    await store.addNote({text: 'Zażółć — notatka DEMO', applicationId: application.id});
    check('Zadanie, termin i notatka zachowują relacje', ['tasks', 'events', 'notes'].every(table => store.state[table][0].applicationId === application.id));
    check('Wyszukiwanie bez polskich znaków wskazuje właściwą aplikację', store.search('zazolc').some(row => row.kind === 'Notatka' && row.key === application.id));
    await store.saveOffer({...data, title: 'Oferta po edycji DEMO'}, offer.id);
    check('Edycja wspólnej oferty jest widoczna przy aplikacji', store.applicationLabel(application.id).includes('Oferta po edycji'));
    const rival = (await client()).store;
    await store.saveTask({title: 'Zmiana pierwszej karty DEMO', due: '2026-12-02', applicationId: ''});
    await assert.rejects(() => rival.saveTask({title: 'Konflikt DEMO', due: '2026-12-03', applicationId: ''}), error => error.status === 409);
    check('Nieaktualna karta nie nadpisuje zmian');
    await rival.refresh(); await rival.saveTask({title: 'Po odświeżeniu DEMO', due: '2026-12-03', applicationId: ''});
    await store.refresh(); check('Odświeżenie pozwala kontynuować pracę', store.state.tasks.length === 3);
    await store.upload({title: 'CV DEMO', kind: 'CV', version: '1', description: '', url: ''}, new File(['Zażółć — CV DEMO'], 'cv-demo.txt', {type: 'text/plain'}));
    const material = store.state.materials[0]; await store.pinMaterial(application.id, material.id);
    const file = await rawFetch('/api/materials/' + material.id + '/download');
    check('Plik zachowuje bajty i jest pobierany jako załącznik', (await file.text()) === 'Zażółć — CV DEMO' && file.headers.get('content-disposition').includes('attachment'));
    check('Materiał jest przypięty do aplikacji', store.state.links[0].materialId === material.id);
    const beforeStatus = JSON.stringify(store.state);
    await assert.rejects(() => store.setStatus(application.id, 'Wysłana', false));
    check('Brak potwierdzenia wysłania zachowuje dane klienta', JSON.stringify(store.state) === beforeStatus);
    await store.setStatus(application.id, 'Wysłana', true);
    check('Potwierdzony status zapisuje historię', store.find('applications', application.id).snapshot && store.find('applications', application.id).sentAt);
    const backup = await store.createBackup();
    await store.saveTask({title: 'Po kopii DEMO', due: '2026-12-04', applicationId: ''});
    const plan = await store.previewBackup(backup.name);
    await store.commitImport(plan);
    check('Przywrócenie zachowuje UUID, relacje i wcześniejsze zadania', store.state.tasks.length === 3 && store.state.links[0].materialId === material.id);
    await store.archive('offers', offer.id, true);
    check('Archiwizacja ukrywa ofertę w wyszukiwaniu', !store.search('Oferta po edycji').some(row => row.kind === 'Oferta'));
    await store.archive('offers', offer.id, true, true);
    check('Przywrócenie oferty zachowuje identyfikator', store.find('offers', offer.id).archived === 0);
    const offlineState = JSON.stringify(store.state); await stop();
    await assert.rejects(() => store.saveOffer({...data, url: 'https://example.org/offline-demo'}), error => error.status === 503);
    check('Utrata połączenia nie tworzy pozornego zapisu', JSON.stringify(store.state) === offlineState);
    await start(); await assert.rejects(() => store.refresh(), error => error.status === 401);
    check('Restart wymaga nowej sesji');
    ({store} = await client());
    check('Nowa sesja po restarcie odzyskuje rekordy i materiały', store.state.offers.length === 1 && store.state.links[0].materialId === material.id && store.state.tasks.length === 3);
    fs.writeFileSync(path.join(__dirname, 'client-report.json'), JSON.stringify({result: 'PASS', count: checks.length, checks, directory, scope: 'Adapter JavaScript + rzeczywiste API; bez kontroli wizualnej.'}, null, 2));
    console.log('PASS:', checks.length, 'kontroli adaptera interfejsu i API na bazie DEMO.');
  } finally {await stop();}
})().catch(error => {console.error(error); process.exitCode = 1;});
