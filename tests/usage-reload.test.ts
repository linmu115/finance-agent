import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, type ServerResponse } from 'node:http';
import { mkdtemp, rename, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';

test('a finished run\'s usage is read from its audit file once; a running one is always read fresh', { timeout: 120000 }, async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'finance-usage-'));
  process.env.FINANCE_DATA_DIR = dir;
  const { loadSettings, saveSettings } = await import('../server/config.js');
  const { FinanceService } = await import('../server/mcp.js');
  const { RunManager } = await import('../server/runs.js');
  await loadSettings();
  const service = new FinanceService(); await service.connect();
  let held: ServerResponse | undefined;
  const reply = (res: ServerResponse, delta: any, finish: string) => {
    res.writeHead(200, { 'Content-Type': 'text/event-stream' });
    const envelope = { id: 'mock', object: 'chat.completion.chunk', created: 1, model: 'usage-mock' };
    res.write('data: ' + JSON.stringify({ ...envelope, choices: [{ index: 0, delta: { role: 'assistant', ...delta }, finish_reason: null }] }) + '\n\n');
    res.write('data: ' + JSON.stringify({ ...envelope, choices: [{ index: 0, delta: {}, finish_reason: finish }], usage: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120 } }) + '\n\n');
    res.end('data: [DONE]\n\n');
  };
  const mock = createServer(async (req, res) => {
    let raw = ''; for await (const chunk of req) raw += chunk;
    if (JSON.parse(raw).messages.some((m: any) => m.role === 'tool')) { held = res; return; }
    reply(res, { tool_calls: [{ index: 0, id: 'calc', type: 'function', function: { name: 'calculate_financial_metrics', arguments: JSON.stringify({ operation: 'divide', inputs: { a: '12', b: '3' } }) } }] }, 'tool_calls');
  });
  await new Promise<void>(resolve => mock.listen(0, '127.0.0.1', resolve));
  const manager: any = new RunManager(service);
  try {
    await saveSettings({ llm: { baseUrl: 'http://127.0.0.1:' + (mock.address() as any).port + '/v1', model: 'usage-mock', apiKey: 'TEST-ONLY', contextWindow: 16384, maxTokens: 512 } });
    await service.call('create_project', { project_id: 'usage', name: 'Usage reload' });
    const chat = { id: randomUUID(), projectId: 'usage', title: '新对话', messages: [], createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
    await service.putState('usage', 'conversations', chat.id, chat); manager.indexConversation(chat.id, 'usage');
    const run = await manager.start(chat, '请计算', []);
    for (const until = Date.now() + 30000; !held;) { assert.ok(Date.now() < until, 'second model request never arrived'); await delay(30); }
    // Mid-run: one settled request and one still open. Nothing is remembered yet.
    for (let i = 0; i < 2; i++) {
      const partial = await manager.reconcileUsage(run.id);
      assert.equal(partial.calls, 2);
      assert.equal(partial.unknownCalls, 1);
    }
    assert.equal(manager.settledUsage.has(run.id), false);
    reply(held, { content: '结果为 4。' }, 'stop');
    for (const until = Date.now() + 30000; manager.activeFor(chat.id);) { assert.ok(Date.now() < until, 'run did not finish'); await delay(30); }
    const finished = await manager.getRun(run.id);
    assert.equal(finished.status, 'completed', finished.error);
    assert.deepEqual([finished.usage.calls, finished.usage.unknownCalls, finished.usage.input, finished.usage.output], [2, 0, 200, 40]);
    const first = await manager.getConversation(chat.id);
    assert.deepEqual([first.messages.at(-1).usage.calls, first.messages.at(-1).usage.unknownCalls, first.messages.at(-1).usage.input], [2, 0, 200]);
    assert.equal(manager.settledUsage.has(run.id), true);
    // With the file moved away, later loads still report the same totals: they no longer read it.
    await rename(path.join(dir, 'audit', run.id + '.jsonl'), path.join(dir, 'audit', run.id + '.moved'));
    const again = await manager.getConversation(chat.id);
    assert.deepEqual(again.messages.at(-1).usage, first.messages.at(-1).usage);
    assert.deepEqual((await manager.getRun(run.id)).usage, finished.usage);
  } finally {
    await manager.shutdown(); await service.close(); await new Promise<void>(resolve => mock.close(() => resolve()));
    await rm(dir, { recursive: true, force: true });
  }
});
