/**
 * Local HTTP wrapper for @smogon/calc + @pkmn/sets.
 * Lifecycle: npm start → bind 127.0.0.1:PORT → SIGTERM closes cleanly.
 */
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {
  runCalculateSafe,
  runCalculateBatch,
  setsPack,
  setsUnpack,
  setsImport,
  setsExport,
  type CalcRequest,
} from './handlers.js';

const HOST = '127.0.0.1';
const DEFAULT_PORT = 4173;

function readJson(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw) return resolve(undefined);
      try {
        resolve(JSON.parse(raw));
      } catch {
        reject(new Error('invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

function send(res: http.ServerResponse, status: number, body: unknown) {
  const json = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(json),
  });
  res.end(json);
}

async function handle(req: http.IncomingMessage, res: http.ServerResponse) {
  const url = req.url?.split('?')[0] ?? '';
  const method = req.method ?? 'GET';

  if (method === 'GET' && url === '/health') {
    return send(res, 200, {status: 'ok'});
  }

  if (method !== 'POST') {
    return send(res, 404, {error: 'not found'});
  }

  let body: unknown;
  try {
    body = await readJson(req);
  } catch (e) {
    return send(res, 400, {error: e instanceof Error ? e.message : String(e)});
  }

  try {
    if (url === '/calculate') {
      const result = runCalculateSafe(body as CalcRequest);
      return send(res, 'error' in result ? 400 : 200, result);
    }

    if (url === '/calculate/batch') {
      const requests = (body as {requests?: CalcRequest[]})?.requests;
      if (!Array.isArray(requests)) {
        return send(res, 400, {error: 'requests array required'});
      }
      return send(res, 200, {results: runCalculateBatch(requests)});
    }

    if (url === '/sets/pack') {
      const set = (body as {set?: object})?.set;
      if (!set) return send(res, 400, {error: 'set required'});
      return send(res, 200, {packed: setsPack(set)});
    }

    if (url === '/sets/unpack') {
      const packed = (body as {packed?: string})?.packed;
      if (typeof packed !== 'string') return send(res, 400, {error: 'packed required'});
      return send(res, 200, {set: setsUnpack(packed)});
    }

    if (url === '/sets/import') {
      const text = (body as {text?: string})?.text;
      if (typeof text !== 'string') return send(res, 400, {error: 'text required'});
      return send(res, 200, {set: setsImport(text)});
    }

    if (url === '/sets/export') {
      const set = (body as {set?: object})?.set;
      if (!set) return send(res, 400, {error: 'set required'});
      return send(res, 200, {text: setsExport(set)});
    }

    return send(res, 404, {error: 'not found'});
  } catch (e) {
    return send(res, 400, {error: e instanceof Error ? e.message : String(e)});
  }
}

export function createServer() {
  return http.createServer((req, res) => {
    handle(req, res).catch((e) => {
      send(res, 500, {error: e instanceof Error ? e.message : String(e)});
    });
  });
}

function isMain() {
  const entry = process.argv[1];
  if (!entry) return false;
  return path.resolve(entry) === fileURLToPath(import.meta.url);
}

if (isMain()) {
  const port = Number(process.env.PORT) || DEFAULT_PORT;
  const server = createServer();
  const shutdown = () => server.close(() => process.exit(0));
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
  server.listen(port, HOST, () => {
    console.log(`calc-service listening on http://${HOST}:${port}`);
  });
}
