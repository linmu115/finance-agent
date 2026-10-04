/** Parameter provenance for editable research drafts. Never infer disclosure from a URL. */
export type InputBasis = { basis: 'disclosed' | 'derived' | 'assumption'; rationale: string };
export type InputEvidence = { kind: 'source' | 'document' | 'artifact'; id: string; locator?: string; quote?: string };
type Data = Record<string, any>;
const metadata = new Set(['input_basis', 'source_refs', 'scenario_assumptions']);
const forbidden = new Set(['__proto__', 'prototype', 'constructor']);

export function inputPath(path: string): string {
  const normalized = path.replace(/^\$\.?/, '').replace(/\[(\d+)\]/g, '.$1');
  return /^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$/.test(normalized) && !normalized.split('.').some(part => forbidden.has(part)) ? normalized : '';
}

function leaves(spec: Data): Map<string, unknown> {
  const values = new Map<string, unknown>();
  function visit(value: unknown, parts: string[]) {
    if (value !== null && typeof value === 'object') Object.entries(value).forEach(([key, child]) => {
      if (!forbidden.has(key) && !(parts.length === 0 && metadata.has(key))) visit(child, [...parts, key]);
    });
    else if (parts.length) values.set(parts.join('.'), value);
  }
  visit(spec, []); return values;
}

function indexed(value: unknown): Map<string, any> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return new Map();
  return new Map(Object.entries(value).map(([key, item]): [string, any] => [inputPath(key), item]).filter(([key]) => key));
}

export function inputBasisRows(spec: Data) {
  const basis = indexed(spec.input_basis), sources = indexed(spec.source_refs);
  return [...leaves(spec)].map(([path, value]) => {
    const record = basis.get(path), valid = record && ['disclosed', 'derived', 'assumption'].includes(record.basis) && typeof record.rationale === 'string';
    const evidence = sources.get(path);
    const refs: InputEvidence[] = (Array.isArray(evidence) ? evidence : []).filter(item => item && ['source', 'document', 'artifact'].includes(item.kind) && typeof item.id === 'string');
    return { path, value, basis: valid ? record.basis as InputBasis['basis'] : 'unknown' as const, rationale: valid ? record.rationale : '', refs };
  });
}

/** Apply equally to field edits, row operations and advanced JSON. Original objects remain immutable. */
export function markDraftInputEdits(previous: Data, candidate: Data): Data {
  const next = structuredClone(candidate), oldValues = leaves(previous), newValues = leaves(next);
  const oldBasis = indexed(previous.input_basis), proposedBasis = indexed(next.input_basis);
  const changed = new Set([...newValues].filter(([path, value]) => !oldValues.has(path) || !Object.is(oldValues.get(path), value)).map(([path]) => path));
  // A moved fiscal-year/peer row must not inherit evidence belonging to the old row.
  const movedRows = [...changed].filter(path => /\.\d+\.(year|id)$/.test(path)).map(path => path.slice(0, path.lastIndexOf('.') + 1));
  for (const path of newValues.keys()) if (movedRows.some(prefix => path.startsWith(prefix))) changed.add(path);
  const output: Record<string, InputBasis> = {};
  for (const path of newValues.keys()) {
    if (changed.has(path)) {
      const old = oldBasis.get(path), prior = old?.rationale ? ` 原记录依据：${old.rationale}` : '';
      output[path] = { basis: 'assumption', rationale: old?.basis === 'assumption' && old.rationale?.startsWith('在界面中修改或新增此参数；') ? old.rationale : `在界面中修改或新增此参数；当前值为研究假设，保留的原引用仅供对照，不证明修改后的值。${prior}` };
    } else if (proposedBasis.has(path)) output[path] = proposedBasis.get(path);
  }
  next.input_basis = output;
  return next;
}
