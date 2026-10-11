import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Markdown from '../web/src/Markdown.tsx';

const render = (children: string) => renderToStaticMarkup(createElement(Markdown, { children }));

test('actual Chinese risk statement renders bold without changing the source message', () => {
  const message = Object.freeze({content: '【推论/分析】**适用范围 / 风险：**以上判断基于2024年年报。'});
  assert.equal(render(message.content), '<p>【推论/分析】<strong>适用范围 / 风险：</strong> 以上判断基于2024年年报。</p>');
  assert.equal(message.content, '【推论/分析】**适用范围 / 风险：**以上判断基于2024年年报。');
});

test('punctuation-ending bold renders in prose, lists and tables', () => {
  for (const label of ['风险：', '风险:', '适用范围（年度）', '结论。', '假设，', '风险！', '风险？']) {
    const html = render(`**${label}**以上判断基于年报。`);
    assert.ok(html.includes(`<strong>${label}</strong> 以上判断基于年报。`), html);
    assert.ok(!html.includes('**'), html);
  }
  const html = render('- **风险：**经营波动。\n\n| 说明 |\n| --- |\n| **口径：**合并 |');
  assert.match(html, /<li><strong>风险：<\/strong> 经营波动。<\/li>/);
  assert.match(html, /<td><strong>口径：<\/strong> 合并<\/td>/);
  assert.equal(render('**已规范：** 保持单空格。'), '<p><strong>已规范：</strong> 保持单空格。</p>');
});

test('inline code and fenced or indented code keep literal stars', () => {
  const literal = '**风险：**以上判断';
  for (const source of [
    '`'+literal+'`',
    '``'+literal+' `内容` ``',
    '```text\n'+literal+'\n```',
    '~~~text\n'+literal+'\n~~~',
    '````text\n```\n'+literal+'\n```\n````',
    '```text\n'+literal, // Still streaming: do not normalize an unclosed block.
    '    '+literal,
    '\t'+literal,
  ]) {
    const html = render(source);
    assert.ok(html.includes(literal), html);
    assert.doesNotMatch(html, /<strong>/);
    assert.match(html, /<code(?:\s|>)/);
  }
  const mixed = render('`'+literal+'`\n\n**风险：**以上判断');
  assert.ok(mixed.includes('<code>'+literal+'</code>'));
  assert.match(mixed, /<strong>风险：<\/strong> 以上判断/);
});
