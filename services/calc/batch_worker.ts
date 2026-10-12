/**
 * Long-lived stdin/stdout JSONL worker for in-process @smogon/calc batches.
 * Same handlers as HTTP /calculate — pin is vendor/smogon-calc (package.json).
 *
 * Protocol (one JSON object per line):
 *   → {"id": number|string, "requests": CalcRequest[]}
 *   ← {"id": same, "results": CalcResult[]}
 */
import * as readline from 'node:readline';
import {runCalculateBatch, type CalcRequest} from './handlers.js';

const rl = readline.createInterface({input: process.stdin, terminal: false});

rl.on('line', (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let msg: {id?: unknown; requests?: CalcRequest[]};
  try {
    msg = JSON.parse(trimmed) as {id?: unknown; requests?: CalcRequest[]};
  } catch (e) {
    process.stdout.write(
      JSON.stringify({
        id: null,
        error: e instanceof Error ? e.message : String(e),
        results: [],
      }) + '\n',
    );
    return;
  }
  const requests = Array.isArray(msg.requests) ? msg.requests : [];
  const results = runCalculateBatch(requests);
  process.stdout.write(JSON.stringify({id: msg.id ?? null, results}) + '\n');
});
