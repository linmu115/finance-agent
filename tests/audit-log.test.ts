import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, open, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { AuditLog } from '../server/audit-log.js';

const busy = () => Object.assign(new Error('EBUSY: resource busy or locked'), { code: 'EBUSY' });

test('a briefly locked audit file is retried and every record is written once, in order', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-audit-')), file = path.join(dir, 'run.jsonl');
  let opens = 0;
  const log = new AuditLog(file, { retryDelaysMs: [1, 1, 1], open: async (name, flags) => { if (++opens <= 2) throw busy(); return open(name, flags); } });
  try {
    await Promise.all([log.append('a\n'), log.append('b\n'), log.append('c\n')]);
    await log.append('d\n');
    assert.equal(await readFile(file, 'utf8'), 'a\nb\nc\nd\n');
    // Two refused opens, then one handle reused for every later record.
    assert.equal(opens, 3);
  } finally { await log.close(); await rm(dir, { recursive: true, force: true }); }
});

test('a write that keeps failing rejects its caller without losing the record or blocking later ones', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-audit-')), file = path.join(dir, 'run.jsonl');
  let locked = true, opens = 0;
  const log = new AuditLog(file, { retryDelaysMs: [1, 1], open: async (name, flags) => { opens++; if (locked) throw busy(); return open(name, flags); } });
  try {
    await assert.rejects(log.append('first\n'), /EBUSY/);
    assert.equal(opens, 3);
    await assert.rejects(log.append('second\n'), /EBUSY/);
    locked = false;
    await log.append('third\n');
    assert.equal(await readFile(file, 'utf8'), 'first\nsecond\nthird\n');
  } finally { await log.close(); await rm(dir, { recursive: true, force: true }); }
});

test('records queued behind a locked file share one retry cycle instead of one each', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-audit-')), file = path.join(dir, 'run.jsonl');
  let opens = 0;
  const log = new AuditLog(file, { retryDelaysMs: [1, 1], open: async () => { opens++; await delay(5); throw busy(); } });
  try {
    const first = log.append('0\n');
    await delay(1);
    // The first write is now in flight; these 200 arrive behind it.
    const rest = Array.from({ length: 200 }, (_, i) => log.append(`${i + 1}\n`));
    const outcomes = await Promise.allSettled([first, ...rest]);
    assert.ok(outcomes.every(o => o.status === 'rejected'));
    // One cycle of three attempts for the first record and one shared by the 200 queued behind it.
    assert.equal(opens, 6);
  } finally { await log.close().catch(() => {}); await rm(dir, { recursive: true, force: true }); }
});

test('a write interrupted part-way resumes after the bytes already on disk', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-audit-')), file = path.join(dir, 'run.jsonl');
  let calls = 0;
  const log = new AuditLog(file, { retryDelaysMs: [1], open: async (name, flags) => {
    const handle = await open(name, flags);
    return {
      close: () => handle.close(),
      write: (async (buffer: Buffer, offset: number, length: number, position: null) => {
        calls++;
        // A short write, then a lock before the remainder goes out.
        if (calls === 1) return handle.write(buffer, offset, 4, position);
        if (calls === 2) throw busy();
        return handle.write(buffer, offset, length, position);
      }) as any,
    };
  } });
  try {
    await log.append('{"type":"model_usage"}\n');
    assert.equal(await readFile(file, 'utf8'), '{"type":"model_usage"}\n');
    assert.equal(calls, 3);
  } finally { await log.close(); await rm(dir, { recursive: true, force: true }); }
});

test('errors that are not transient locks are reported at once', async () => {
  let opens = 0;
  const log = new AuditLog('unused', { retryDelaysMs: [1, 1, 1], open: async () => { opens++; throw Object.assign(new Error('ENOSPC: no space left on device'), { code: 'ENOSPC' }); } });
  await assert.rejects(log.append('x\n'), /ENOSPC/);
  assert.equal(opens, 1);
});

test('close releases the handle and a late record still reaches the file', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-audit-')), file = path.join(dir, 'run.jsonl');
  let openHandles = 0;
  const log = new AuditLog(file, { open: async (name, flags) => { const handle = await open(name, flags); openHandles++; return { write: handle.write.bind(handle) as any, close: async () => { openHandles--; await handle.close(); } }; } });
  try {
    await log.append('a\n');
    assert.equal(openHandles, 1);
    await log.close();
    assert.equal(openHandles, 0);
    await log.append('late\n');
    assert.equal(openHandles, 0);
    assert.equal(await readFile(file, 'utf8'), 'a\nlate\n');
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('an audit file that stays locked fails only its own run; the server and other conversations continue', { timeout: 120000 }, async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-audit-run-'));
  process.env.FINANCE_DATA_DIR = dir;
  const { loadSettings, saveSettings } = await import('../server/config.js');
  const { FinanceService } = await import('../server/mcp.js');
  const { RunManager } = await import('../server/runs.js');
  await loadSettings();
  const service = new FinanceService(); await service.connect();
  const mock = createServer(async (req, res) => {
    for await (const _ of req);
    res.writeHead(200, { 'Content-Type': 'text/event-stream' });
    const envelope = { id: 'mock', object: 'chat.completion.chunk', created: 1, model: 'audit-mock' };
    for (const text of ['审计', '写入', '回归']) res.write('data: ' + JSON.stringify({ ...envelope, choices: [{ index: 0, delta: { role: 'assistant', content: text }, finish_reason: null }] }) + '\n\n');
    res.write('data: ' + JSON.stringify({ ...envelope, choices: [{ index: 0, delta: {}, finish_reason: 'stop' }], usage: { prompt_tokens: 10, completion_tokens: 3, total_tokens: 13 } }) + '\n\n');
    res.end('data: [DONE]\n\n');
  });
  await new Promise<void>(resolve => mock.listen(0, '127.0.0.1', resolve));
  const manager: any = new RunManager(service);
  const unhandled: unknown[] = [], onUnhandled = (reason: unknown) => { unhandled.push(reason); };
  process.on('unhandledRejection', onUnhandled);
  // The first run's audit file never opens; every other run uses the real file.
  let lockedRun: string | undefined;
  manager.auditLog = (runId: string) => {
    let log = manager.auditLogs.get(runId);
    if (!log) {
      lockedRun ??= runId;
      log = new AuditLog(path.join(dir, 'audit', runId + '.jsonl'), runId === lockedRun ? { retryDelaysMs: [1, 1], open: async () => { throw busy(); } } : {});
      manager.auditLogs.set(runId, log);
    }
    return log;
  };
  const finished = async (id: string) => {
    const until = Date.now() + 60000;
    for (;;) {
      const run = await manager.getRun(id);
      if (['completed', 'failed', 'cancelled'].includes(run.status) && !manager.activeFor(run.conversationId)) return run;
      assert.ok(Date.now() < until, 'run did not finish');
      await delay(50);
    }
  };
  try {
    await saveSettings({ llm: { baseUrl: 'http://127.0.0.1:' + (mock.address() as any).port + '/v1', model: 'audit-mock', apiKey: 'TEST-ONLY', contextWindow: 16384, maxTokens: 512 } });
    await service.call('create_project', { project_id: 'audit', name: 'Audit failure isolation' });
    const chats = [0, 1].map(() => ({ id: randomUUID(), projectId: 'audit', title: '新对话', messages: [], createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }));
    for (const chat of chats) { await service.putState('audit', 'conversations', chat.id, chat); manager.indexConversation(chat.id, 'audit'); }
    const locked = await finished((await manager.start(chats[0], '第一轮', [])).id);
    assert.equal(locked.id, lockedRun);
    assert.equal(locked.status, 'failed');
    assert.match(locked.error, /无法写入审计记录.*EBUSY/);
    assert.match(locked.auditError, /EBUSY/);
    // The failed run was saved as finished, so a restart will not replay it.
    assert.equal((await service.getState<any>('audit', 'runs', locked.id))?.status, 'failed');
    const healthy = await finished((await manager.start(chats[1], '第二轮', [])).id);
    assert.equal(healthy.status, 'completed', healthy.error);
    assert.equal(healthy.auditError, undefined);
    assert.equal((await manager.getConversation(chats[1].id)).messages.at(-1).content, '审计写入回归');
    const audit = (await readFile(path.join(dir, 'audit', healthy.id + '.jsonl'), 'utf8')).trim().split('\n').map(line => JSON.parse(line));
    assert.ok(audit.some(row => row.type === 'model_usage'));
    assert.equal(audit.filter(row => row.type === 'event' && row.data.type === 'done').length, 1);
    assert.deepEqual(audit.filter(row => row.type === 'event').map(row => row.data.seq), audit.filter(row => row.type === 'event').map((_, index) => index + 1));
    // A record that arrives after the run ended goes through the same closed log and leaves no handle open.
    const closedLog = manager.auditLogs.get(healthy.id);
    await manager.audit(manager.live.get(healthy.id), 'late_record', { note: 'after close' });
    assert.equal(manager.auditLogs.get(healthy.id), closedLog);
    assert.equal(closedLog.handle, undefined);
    assert.equal(JSON.parse((await readFile(path.join(dir, 'audit', healthy.id + '.jsonl'), 'utf8')).trim().split('\n').at(-1)!).type, 'late_record');
    await delay(50);
    assert.deepEqual(unhandled, []);
  } finally {
    process.off('unhandledRejection', onUnhandled);
    await manager.shutdown(); await service.close(); await new Promise<void>(resolve => mock.close(() => resolve()));
    await rm(dir, { recursive: true, force: true });
  }
});
