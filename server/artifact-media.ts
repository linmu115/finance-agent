import path from 'node:path';

// Generated files have known formats. Windows' registry-derived CSV MIME must
// not make an otherwise valid analysis artifact impossible to download.
const media:Record<string,string>={
 '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp',
 '.json':'application/json','.csv':'text/csv','.txt':'text/plain',
 '.md':'text/markdown','.py':'text/x-python','.pdf':'application/pdf',
};
export function artifactMediaType(name:string){
 return media[path.extname(name).toLowerCase()]||'application/octet-stream';
}
// Unknown formats remain downloadable, without executing active HTML/SVG in
// the app's origin or preventing the rest of the result from being delivered.
export const artifactDownloadOnly=(name:string)=>['.py','.md'].includes(path.extname(name).toLowerCase())||artifactMediaType(name)==='application/octet-stream';
