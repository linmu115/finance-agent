import { createElement } from 'react';
import ReactMarkdown, { type Options } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

// Models also use TeX's native delimiters. Normalize prose only: code examples
// retain their literal content, including while a fenced block is streaming.
function normalizeTex(source: string) {
  const prose = (text: string) => text.replace(/(`+)[\s\S]*?\1(?!`)|\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]/g,
    (match, code, inline, block) => code ? match : inline !== undefined ? `$$${inline}$$` : `\n$$\n${block.trim()}\n$$\n`);
  const output: string[] = [];
  let pending: string[] = [], fence: { char: string; length: number } | undefined;
  for (const line of source.split('\n')) {
    if (fence) {
      output.push(line);
      if (new RegExp(`^ {0,3}${fence.char}{${fence.length},}\\s*$`).test(line)) fence = undefined;
    } else {
      const opening = /^ {0,3}(`{3,}|~{3,})/.exec(line);
      if (opening) {
        if (pending.length) output.push(prose(pending.join('\n')));
        pending = []; fence = { char: opening[1][0], length: opening[1].length };
        output.push(line);
      } else pending.push(line);
    }
  }
  if (pending.length) output.push(prose(pending.join('\n')));
  return output.join('\n');
}

export default function Markdown(props: Options) {
  return createElement(ReactMarkdown, { ...props, children: normalizeTex(props.children || ''),
    remarkPlugins: [remarkGfm, [remarkMath, { singleDollarTextMath: false }]],
    rehypePlugins: [[rehypeKatex, { trust: false }]],
  });
}
