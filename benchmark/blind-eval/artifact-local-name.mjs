import path from 'node:path';
import {createHash} from 'node:crypto';

// Preserve the original display name in the manifest. Windows rejects some
// model-generated display names even though their HTTP artifact bytes are valid.
export function localArtifactName(url,name){
 const base=path.basename(name.replaceAll('\\','/')).replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[. ]+$/g,'');
 return createHash('sha256').update(url).digest('hex').slice(0,12)+'-'+base;
}
export function validWindowsBasename(name){
 return path.basename(name)===name&&!/[<>:"/\\|?*\x00-\x1f]/.test(name)&&!/[. ]$/.test(name)&&!/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name);
}
