// Serwer wyłącznie do oglądania prototypu; nie ma API ani operacji zapisu.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const port = 8765;
const files = {
  '/prototype/': ['index.html', 'text/html; charset=utf-8'],
  '/prototype/index.html': ['index.html', 'text/html; charset=utf-8'],
  '/prototype/styles.css': ['styles.css', 'text/css; charset=utf-8'],
  '/prototype/model.js': ['model.js', 'text/javascript; charset=utf-8'],
  '/prototype/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/docs/materialy/cv-master-ai-oryginal.txt': ['../docs/materialy/cv-master-ai-oryginal.txt', 'text/plain; charset=utf-8']
};
const server = http.createServer((req, res) => {
  const origin = `http://127.0.0.1:${port}`;
  if (req.headers.host !== `127.0.0.1:${port}`) { res.writeHead(403); return res.end('Nieprawidlowy host.'); }
  const url = new URL(req.url, origin);
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405); return res.end(); }
  if (url.pathname === '/') { res.writeHead(302, { Location: '/prototype/' }); return res.end(); }
  const file = files[url.pathname];
  if (!file) { res.writeHead(404); return res.end('Nie znaleziono.'); }
  fs.readFile(path.resolve(__dirname, file[0]), (error, bytes) => {
    if (error) { res.writeHead(500); return res.end('Nie mozna odczytac pliku.'); }
    res.writeHead(200, { 'Content-Type': file[1], 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'" });
    res.end(req.method === 'HEAD' ? undefined : bytes);
  });
});
server.on('error', error => { console.error(`Nie uruchomiono serwera: ${error.code}. Port ${port} musi byc wolny.`); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Prototyp DEMO: http://127.0.0.1:${port}/prototype/ (Ctrl+C konczy serwer)`));
