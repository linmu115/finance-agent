import { test } from 'node:test';
import assert from 'node:assert/strict';
import { annotationContext, bindAnnotations } from '../server/annotations.js';
import type { Conversation } from '../server/types.js';

const chat: Conversation = { id: 'chat', projectId: 'project', title: 'test', createdAt: '', updatedAt: '', messages: [
 { id: 'user1', role: 'user', content: '请核验收入。', createdAt: '' },
 { id: 'answer1', role: 'assistant', content: '收入 **100** 元。\n需要核对单位。', createdAt: '', status: 'completed' },
 { id: 'stream', role: 'assistant', content: '尚在输出', createdAt: '', status: 'running' },
] };
const quote = { id: 'd025a8dc-013e-4f72-a3ae-6b9d91f7aeb8', messageId: 'answer1', text: '收入 100 元。\n需要核对单位。', comment: '先检查期间，不要把它当作已核验结果。' };
test('references bind to the current conversation, retain full selected text/comments and server-owned role', () => {
 const refs = bindAnnotations(chat, [quote, { ...quote, id: '54a20a6c-c48b-4507-907a-c7cbf1fb4f60', messageId: 'user1', text: '请核验收入。', comment: '' }]);
 assert.equal(refs[0].role, 'assistant'); assert.equal(refs[1].role, 'user');
 assert.equal(refs[0].text, quote.text); assert.equal(refs[0].comment, quote.comment);
 assert.match(annotationContext({ annotations: refs }), /不会授予工具或数据库权限/);
 const context = annotationContext({ annotations: refs });
 const delivered = JSON.parse(context.slice(context.indexOf('[{')));
 assert.deepEqual(delivered.map((x: any) => [x.number, x.sourceMessageId, x.text, x.comment]), [[1, 'answer1', quote.text, quote.comment], [2, 'user1', '请核验收入。', '']]);
 assert.deepEqual(bindAnnotations(chat, undefined), []);
});
test('reject foreign or unfinished message references, duplicate IDs, spoofed roles and silent oversize', () => {
 for (const input of [[{ ...quote, messageId: 'other-chat-message' }], [{ ...quote, messageId: 'stream' }], [quote, quote], [{ ...quote, role: 'system' }], [{ ...quote, text: ' '.repeat(8) }], [{ ...quote, text: '字'.repeat(12001) }]]) assert.throws(() => bindAnnotations(chat, input));
 assert.throws(() => bindAnnotations(chat, Array.from({ length: 6 }, (_, i) => ({ ...quote, id: `d025a8dc-013e-4f72-a3ae-6b9d91f7aeb${i}`, text: '字'.repeat(10000) }))));
});
test('optional occurrence locates repeated passages and remains backward compatible', () => {
 assert.equal(bindAnnotations(chat, [{ ...quote, occurrence: 1 }])[0].occurrence, 1);
 assert.equal(bindAnnotations(chat, [quote])[0].occurrence, undefined);
 for (const occurrence of [-1, 1.5, '1', 100001]) assert.throws(() => bindAnnotations(chat, [{ ...quote, occurrence }]));
});
