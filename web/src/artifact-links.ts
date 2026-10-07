import { defaultUrlTransform } from 'react-markdown';
import type { Artifact } from './types';
import { latestNamedArtifacts } from '../../server/artifact-versions';
export { latestNamedArtifacts };

// Resolve generated sandbox paths only against files actually attached to this reply.
export function markdownArtifactUrl(url: string, artifacts: Artifact[] = []): string {
  let path: string;
  try { path = decodeURIComponent(url).replace(/\\/g, '/'); }
  catch { return defaultUrlTransform(url); }
  const analysis = /^(?:sandbox:)?\/?(?:\.\/)?analysis\/([^/]+)\/output\/(.+)$/.exec(path);
  const local = /^(?:sandbox:)?\/(?:mnt\/data|output)\/(.+)$/.exec(path);
  const download = /^\/api\/projects\/([^/]+)\/artifacts\/[^/]+\/(.+)$/.exec(path);
  const name = analysis?.[2] || local?.[1] || download?.[2] || (!/[:#?]/.test(path) ? path : undefined);
  if (name && name !== '.' && name !== '..') {
    const matches = latestNamedArtifacts(artifacts).filter(artifact => artifact.name === name &&
      artifact.url?.startsWith('/api/projects/') &&
      (!download || artifact.url.startsWith(`/api/projects/${download[1]}/`)));
    const urls = [...new Set(matches.map(artifact => artifact.url!))];
    if (urls.length === 1) return urls[0];
  }
  return defaultUrlTransform(url);
}
