import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Markdown from '../web/src/Markdown.tsx';

const render = (children: string) => renderToStaticMarkup(createElement(Markdown, { children }));

test('financial Markdown keeps tables and currency while typesetting inline and display TeX', () => {
  const html = render(String.raw`## 估值

价格由 $10 升至 $20，回报率为 $$r=\frac{P_1-P_0}{P_0}$$。

$$
EV=\sum_{t=1}^{n}\frac{FCF_t}{(1+WACC)^t}+\frac{TV}{(1+WACC)^n}
$$

| 指标 | 公式 |
| --- | --- |
| 毛利率 | $$\frac{R-C}{R}$$ |
`);
  assert.match(html, /<h2>估值<\/h2>/);
  assert.match(html, /价格由 \$10 升至 \$20/);
  assert.match(html, /<table>/);
  assert.equal((html.match(/class="katex"/g) || []).length, 3);
  assert.equal((html.match(/class="katex-display"/g) || []).length, 1);
  assert.match(html, /<mfrac>/);
  assert.doesNotMatch(html, /katex-error/);
});

test('code and unfinished streaming expressions stay readable', () => {
  const html = render('`$$x^2$$`\n\n```python\nprice = "$10"\n```\n\n生成中 $$\\frac{1}{');
  assert.match(html, /<code>\$\$x\^2\$\$<\/code>/);
  assert.match(html, /language-python/);
  assert.match(html, /生成中/);
  assert.doesNotMatch(html, /class="katex"/);
});

test('LaTeX does not gain trusted HTML or URL execution', () => {
  const html = render(String.raw`$$\href{javascript:alert(1)}{x}$$`);
  assert.doesNotMatch(html, /href="javascript:/);
});

test('native TeX delimiters from actual model replies render without changing code', () => {
  const html = render(String.raw`终值按 \(1+g\) 延伸。

\[
0.83\ \text{人民币元/股}\times10.0\times1.0807\approx8.97
\]

~~~tex
\[literal\]
~~~
` + '\n\n`\\(literal\\)`\n\n```tex\n\\(unfinished code\\)\n');
  assert.equal((html.match(/class="katex"/g) || []).length, 2);
  assert.equal((html.match(/class="katex-display"/g) || []).length, 1);
  assert.match(html, /<code>\\\(literal\\\)<\/code>/);
  assert.match(html, /\\\[literal\\\]/);
  assert.match(html, /\\\(unfinished code\\\)/);
  assert.doesNotMatch(html, /katex-error/);
});
