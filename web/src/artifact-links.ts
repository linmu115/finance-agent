import { defaultUrlTransform } from 'react-markdown';
import type { Artifact } from './types';

// Resolve generated sandbox paths only against files actually attached to this reply.
export function markdownArtifactUrl(url: string, artifacts: Artifact[] = []): string {
  let path: string;
  try { path = decodeURIComponent(url).replace(/\\/g, '/'); }
  catch { return defaultUrlTransform(url); }
  const analysis = /^(?:sandbox:)?\/?(?:\.\/)?analysis\/([^/]+)\/output\/(.+)$/.exec(path);
  const local = /^(?:sandbox:)?\/(?:mnt\/data|output)\/(.+)$/.exec(path);
  const name = analysis?.[2] || local?.[1] || (!/[:#?]/.test(path) ? path : undefined);
  // A mistyped, non-ID path can still identify one exact attached file. A
  // valid run ID must match, so different model revisions are never guessed.
  const run = analysis && /^[a-f0-9]{32}$/.test(analysis[1]) ? analysis[1] : undefined;
  if (name && name !== '.' && name !== '..') {
    const matches = artifacts.filter(artifact => artifact.name === name &&
      artifact.url?.startsWith('/api/projects/') &&
      (!run || artifact.url.includes(`/artifacts/${run}/`)));
    const urls = [...new Set(matches.map(artifact => artifact.url!))];
    if (urls.length === 1) return urls[0];
  }
  return defaultUrlTransform(url);
}
