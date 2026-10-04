// Explicitly isolated browser acceptance: candidate assets with the local test backend.
import express from 'express';
import http from 'node:http';
import path from 'node:path';
const app = express();
app.use('/api', (req, res) => {
 const request = http.request('http://127.0.0.1:3003' + req.originalUrl, { method: req.method, headers: { ...req.headers, host: '127.0.0.1:3003' } }, response => { res.writeHead(response.statusCode || 502, response.headers); response.pipe(res); });
 request.on('error', () => { if (!res.headersSent) res.status(502).json({ error: { message: '验收服务未连接' } }); else res.end(); });
 req.pipe(request);
});
const folder = path.resolve('web/dist-ui-candidate');
app.use(express.static(folder));
app.get('/{*splat}', (_req, res) => res.sendFile(path.join(folder, 'index.html')));
app.listen(5173, '127.0.0.1', () => console.log('Isolated UI acceptance: http://127.0.0.1:5173'));
