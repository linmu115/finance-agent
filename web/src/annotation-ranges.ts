import type { Annotation } from './types';

// Whitespace from rendered Markdown differs from plain text; keep durable quote/occurrence locators.
export const normalizeQuote = (text: string) => text.replace(/[\s\u200b-\u200d\u2060\ufeff]/gu, '');
export const sourceKey = (item: Annotation) => JSON.stringify([item.messageId, normalizeQuote(item.text), item.occurrence || 0]);
export function messageBody(item: Annotation): HTMLElement | null {
 return document.querySelector(`[data-message-id="${CSS.escape(item.messageId)}"] .${item.role === 'user' ? 'user-bubble' : 'markdown'}`);
}
type TextIndex = { content: string; chars: { node: Text; offset: number }[] };
export function indexText(root: HTMLElement): TextIndex {
 const chars: TextIndex['chars'] = []; let content = '';
 const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
 for (let value = walker.nextNode(); value; value = walker.nextNode()) {
  const node = value as Text;
  for (let offset = 0; offset < node.length; offset++) {
   const char = node.data[offset];
   if (!normalizeQuote(char)) continue;
   content += char; chars.push({ node, offset });
  }
 }
 return { content, chars };
}
export function quoteOccurrence(root: HTMLElement, range: Range, text: string): number {
 const prefix = document.createRange(); prefix.selectNodeContents(root); prefix.setEnd(range.startContainer, range.startOffset);
 const before = normalizeQuote(prefix.toString()), quote = normalizeQuote(text); let count = 0, cursor = 0;
 if (!quote) return 0;
 while ((cursor = before.indexOf(quote, cursor)) >= 0) { count++; cursor += quote.length; }
 return count;
}
export function quoteRange(root: HTMLElement, item: Annotation, index = indexText(root)): Range | undefined {
 const quote = normalizeQuote(item.text); if (!quote) return;
 let start = -1, cursor = 0;
 for (let i = 0; i <= (item.occurrence || 0); i++) {
  start = index.content.indexOf(quote, cursor); if (start < 0) return; cursor = start + quote.length;
 }
 const first = index.chars[start], last = index.chars[cursor - 1]; if (!first || !last) return;
 const range = document.createRange(); range.setStart(first.node, first.offset); range.setEnd(last.node, last.offset + 1); return range;
}
export type HighlightPlatform = { CSS?: { highlights?: Map<string, unknown> }; Highlight?: new (...ranges: Range[]) => unknown };
export function paintHighlights(name: string, ranges: Range[]) {
 const platform = globalThis as unknown as HighlightPlatform;
 if (platform.Highlight && platform.CSS?.highlights) platform.CSS.highlights.set(name, new platform.Highlight(...ranges));
}
export function clearHighlights(name: string) { (globalThis as unknown as HighlightPlatform).CSS?.highlights?.delete(name); }
export function locateAnnotation(item: Annotation) {
 const body = messageBody(item); if (!body) return false;
 const range = quoteRange(body, item), scroller = body.closest<HTMLElement>('.conversation-scroll');
 if (!range || !scroller) return false;
 const box = range.getBoundingClientRect(), viewport = scroller.getBoundingClientRect();
 scroller.scrollTo({ top: scroller.scrollTop + box.top - viewport.top - Math.max(16, (viewport.height - Math.min(box.height, 150)) / 2), behavior: 'smooth' });
 paintHighlights('finance-reference-active', [range]);
 return true;
}
