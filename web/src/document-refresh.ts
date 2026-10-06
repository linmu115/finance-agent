import type { ToolEvent } from './types';

// Tools that only read: their result cannot change what the document list shows.
const READ_ONLY = /^(get_|query_|search_|list_|read_|calculate_|inspect_|compare_)/;

/** Whether a tool event can have changed the document list (state, counts, or a newly registered file). */
export function affectsDocuments(event: Pick<ToolEvent, 'name' | 'status'>): boolean {
  return event.status !== 'started' && !READ_ONLY.test(event.name);
}

/** Turns a burst of requests for the same key into one call, `intervalMs` after the first of them. */
export function coalesce<K>(run: (key: K) => void, intervalMs: number) {
  const pending = new Map<K, ReturnType<typeof setTimeout>>();
  const request = (key: K) => {
    if (pending.has(key)) return;
    pending.set(key, setTimeout(() => { pending.delete(key); run(key); }, intervalMs));
  };
  request.cancel = () => { for (const timer of pending.values()) clearTimeout(timer); pending.clear(); };
  return request;
}
