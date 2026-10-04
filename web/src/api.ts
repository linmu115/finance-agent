export class ApiError extends Error {
  constructor(message: string, public code = 'REQUEST_FAILED', public status = 0) { super(message); this.name = 'ApiError'; }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...options, headers: { ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('无法连接本地服务。请确认服务已启动，再重试。', 'NETWORK_ERROR');
  }
  const type = response.headers.get('content-type') || '';
  if (!type.includes('application/json')) {
    throw new ApiError(response.ok ? '服务返回了不支持的响应格式。' : `请求失败（HTTP ${response.status}）。`, 'INVALID_RESPONSE', response.status);
  }
  const body = await response.json();
  if (!response.ok) throw new ApiError(body.error?.message || body.message || `请求失败（HTTP ${response.status}）`, body.error?.code, response.status);
  return body as T;
}
export const errorText = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试。';
export const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';
export function listResult<T>(result: T[] | Record<string, unknown>, key: string): T[] {
  return Array.isArray(result) ? result : (Array.isArray(result[key]) ? result[key] as T[] : []);
}
export function safeArtifactUrl(url?: string): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/') ? parsed.href : undefined;
  } catch { return undefined; }
}
