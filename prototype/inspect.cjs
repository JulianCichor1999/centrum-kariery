const { chromium } = require('C:/Users/Julian/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');

(async () => {
  const output = path.join(__dirname, 'screenshots'); fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'America/New_York' });
  const page = await context.newPage(), errors = [], checks = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', req => { if (!req.url().startsWith('http://127.0.0.1:8765') && !req.url().startsWith('file:')) external.push(req.url()); });
  const check = (name, ok = true) => { assert.ok(ok, name); checks.push(name); };
  const action = name => page.locator(`#main [data-action="${name}"]`);
  const dialog = page.locator('#dialog');
  async function submit() { await dialog.locator('[type=submit]').click(); }
  async function nav(screen) { if (page.viewportSize().width <= 640) await page.locator('#menu').click(); await page.locator(`.cd-nav [data-screen="${screen}"]`).click(); }
  try {
    await page.goto('http://127.0.0.1:8765/prototype/');
    await page.waitForSelector('#main h1');
    await page.screenshot({ path: path.join(output, 'today-1440.png'), fullPage: true });
    await page.locator('.cd-topbar [data-action=add-offer]').click();
    await submit(); check('Puste wymagane pola mają błędy', await dialog.locator('[aria-invalid=true]').count() === 3);
    await dialog.locator('[name=title]').fill('Operator n8n DEMO'); await dialog.locator('[name=company]').fill('Testowa Firma'); await dialog.locator('[name=location]').fill('Zawiercie');
    await dialog.locator('[name=url]').fill('javascript:alert(1)'); await submit(); check('Link javascript jest odrzucony', await dialog.locator('[name=url]').getAttribute('aria-invalid') === 'true');
    await dialog.locator('[name=url]').fill('https://example.org/nowa?utm_source=demo'); await dialog.locator('[name=description]').fill('<img src=x onerror="window.injected=true">\nPrzykładowa oferta automatyzacji.'); await submit();
    check('Zapis nowej oferty', await page.locator('#main h1').textContent() === 'Operator n8n DEMO');
    check('Treść jest tekstem, nie HTML', await page.locator('#main img').count() === 0 && await page.evaluate(() => window.injected !== true));
    await action('create-application').click(); check('Aplikacja utworzona z oferty', await action('status').count() === 1);
    await action('offer').click(); await action('edit-offer').click(); await dialog.locator('[name=title]').fill('Operator n8n — poprawiony'); await submit(); await action('detail').click();
    check('Edycja wspólnej oferty widoczna w aplikacji', await page.locator('#main h1').textContent() === 'Operator n8n — poprawiony');
    await action('add-task').click(); await dialog.locator('[name=title]').fill('Zadanie testowe powiązane'); await submit(); check('Zadanie w aplikacji', await page.locator('#main').textContent().then(text => text.includes('Zadanie testowe powiązane')));
    await action('add-event').click(); await dialog.locator('[name=title]').fill('Rozmowa testowa DEMO'); await dialog.locator('[name=start]').fill('2026-12-01T10:00'); await dialog.locator('[name=end]').fill('2026-12-01T09:00'); await submit();
    check('Koniec wcześniejszy od początku jest odrzucony', await dialog.locator('[name=end]').getAttribute('aria-invalid') === 'true');
    await dialog.locator('[name=end]').fill('2026-12-01T10:30'); await submit(); check('Czas Warsaw niezależny od strefy przeglądarki', await page.locator('#main').textContent().then(text => text.includes('10:00 (Europe/Warsaw)')));
    await action('add-note').click(); await dialog.locator('[name=text]').fill('Notatka unikalna: zażółć'); await submit();
    await action('status').click(); await dialog.locator('[name=status]').selectOption('Wysłana'); await submit(); check('Wysłana wymaga potwierdzenia', await dialog.locator('h2').textContent() === 'Potwierdź oznaczenie wysłania');
    await page.keyboard.press('Escape'); check('Anulowanie statusu nie oznacza wysyłki', await page.locator('#main .cd-heading').textContent().then(text => text.includes('Przygotowanie')));
    await action('status').click(); await dialog.locator('[name=status]').selectOption('Wysłana'); await submit(); await submit();
    await page.locator('[data-tab=history]').click(); check('Historia ręcznie oznaczonego statusu', await page.locator('#main').textContent().then(text => text.includes('ręczne potwierdzenie DEMO')));
    await nav('materials'); await action('add-material').click(); await dialog.locator('[name=title]').fill('Materiał testowy'); await dialog.locator('[name=version]').fill('2'); await dialog.locator('[name=description]').fill('Opis wersji DEMO'); await submit();
    await nav('applications'); await page.locator('.cd-table tr').filter({ hasText: 'Operator n8n — poprawiony' }).locator('button').click(); await page.locator('[data-tab=documents]').click(); await action('pin-material').click(); await dialog.locator('[name=materialId]').selectOption({ label: 'Materiał testowy · v2' }); await submit();
    check('Materiał powiązany z aplikacją', await page.locator('#main').textContent().then(text => text.includes('Materiał testowy') && text.includes('Wersja 2')));
    await page.locator('[data-tab=overview]').click(); await action('assistant').click();
    for (let index = 0; index < 6; index++) { await page.locator(`[data-step="${index}"]`).click(); check(`Krok AI ${index + 1} to podgląd`, await page.locator('#main').textContent().then(text => text.includes('Model nie jest połączony'))); }
    await page.screenshot({ path: path.join(output, 'assistant-1440.png'), fullPage: true });
    await page.locator('#search').fill('zazolc'); await page.locator('#search-form [type=submit]').click(); check('Globalne wyszukiwanie notatki bez polskich znaków', await page.locator('#main h2').textContent().then(text => text.includes('Notatka unikalna'))); await action('result-detail').click();
    check('Wynik prowadzi do powiązanej aplikacji', await page.locator('#main h1').textContent() === 'Operator n8n — poprawiony');
    await nav('plan'); await page.locator('.task-row').filter({ hasText: 'Zadanie testowe powiązane' }).locator('input[type=checkbox]').click(); check('Ukończenie usuwa zadanie z otwartych', await page.locator('.task-row').filter({ hasText: 'Zadanie testowe powiązane' }).count() === 0);
    await page.locator('#plan-filter').selectOption('done'); const done = page.locator('.task-row').filter({ hasText: 'Zadanie testowe powiązane' }); check('Ukończone zadanie zachowane', await done.count() === 1);
    await done.locator('[data-action=delete-task]').click(); await page.keyboard.press('Escape'); check('Anulowanie usunięcia zachowuje zadanie', await done.count() === 1); await done.locator('[data-action=delete-task]').click(); await submit(); check('Potwierdzone usunięcie', await done.count() === 0);
    await nav('offers'); await page.locator('#filter-location').selectOption('Kraków'); await page.locator('#filter-mode').selectOption('Zdalna'); check('Pusty wynik filtrów', await page.getByText('Brak pasujących ofert', { exact: true }).count() === 1); await action('clear-filters').first().click(); check('Wyczyszczenie filtrów przywraca oferty', await page.locator('.cd-offer').count() === 4);
    await page.locator('.cd-topbar [data-action=add-offer]').click(); await dialog.locator('[name=title]').fill('Duplikat adresu'); await dialog.locator('[name=company]').fill('Inna firma'); await dialog.locator('[name=location]').fill('Katowice'); await dialog.locator('[name=url]').fill('https://example.org/nowa/#fragment'); await submit(); check('Duplikat URL z parametrem śledzącym i fragmentem', await dialog.locator('#err-url').textContent().then(text => text.includes('już istnieje')));
    await page.screenshot({ path: path.join(output, 'validation-1440.png'), fullPage: true }); await page.keyboard.press('Escape');
    await page.reload(); await page.waitForSelector('#main h1'); await nav('offers'); check('Odświeżenie resetuje przykłady', await page.locator('.cd-offer').count() === 3);

    const dimensions = [];
    for (const width of [1440, 768, 390, 360]) {
      await page.setViewportSize({ width, height: width < 641 ? 844 : 1000 });
      for (const view of ['today', 'offers', 'applications', 'plan', 'profile', 'materials', 'assistant', 'settings']) {
        await nav(view);
        const sizes = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: window.innerWidth }));
        check(`Brak poziomego przewijania: ${view} ${width}`, sizes.document <= sizes.viewport);
        dimensions.push({ view, width, ...sizes });
        if (width === 1440 || (width === 390 && ['today', 'offers', 'plan'].includes(view))) await page.screenshot({ path: path.join(output, `${view}-${width}.png`), fullPage: true });
      }
      await nav('applications'); await action('detail').first().click();
      for (const tab of ['overview', 'match', 'documents', 'history']) { await page.locator(`[data-tab=${tab}]`).click(); check(`Szczegóły ${tab} ${width}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); }
      if (width === 1440 || width === 390) { await page.locator('[data-tab=overview]').click(); await page.screenshot({ path: path.join(output, `detail-${width}.png`), fullPage: true }); }
      await page.locator('.cd-topbar [data-action=add-offer]').click();
      check(`Dialog nie wychodzi poza ekran ${width}`, await dialog.evaluate(el => { const box = el.getBoundingClientRect(); return box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight; }));
      if (width === 390) await page.screenshot({ path: path.join(output, 'dialog-390.png'), fullPage: true });
      await page.keyboard.press('Escape');
      check(`Escape zamyka dialog ${width}`, await dialog.evaluate(el => !el.open));
      check(`Fokus wraca do przycisku ${width}`, await page.evaluate(() => document.activeElement.dataset.action === 'add-offer'));
    }
    await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href); await page.waitForSelector('#main h1');
    await page.locator('.cd-topbar [data-action=add-offer]').click(); check('Działa też jako lokalny plik', await dialog.evaluate(el => el.open)); await page.keyboard.press('Escape');
    await page.emulateMedia({ reducedMotion: 'reduce' }); check('Ograniczenie ruchu', await page.locator('.cd-topbar button').first().evaluate(el => getComputedStyle(el).transitionDuration === '0s'));
    check('Brak błędów JavaScript', errors.length === 0); check('Brak żądań do zewnętrznych usług', external.length === 0);
    fs.writeFileSync(path.join(__dirname, 'verification-report.json'), JSON.stringify({ at: new Date().toISOString(), checks, dimensions, errors, external, browser: await browser.version(), browserTimezone: 'America/New_York', result: 'PASS' }, null, 2));
    console.log(`PASS: ${checks.length} kontroli; raport i zrzuty w prototype/.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
