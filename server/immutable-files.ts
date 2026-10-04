import {writeFile,link,unlink,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
/** Publish a complete immutable file atomically. Existing destinations are never overwritten. */
export async function publishFile(filename:string,bytes:string|Buffer){
 await mkdir(path.dirname(filename),{recursive:true});
 const temp=filename+'.'+randomUUID()+'.incomplete';
 await writeFile(temp,bytes,{flag:'wx',mode:0o600});
 try{await link(temp,filename);}finally{await unlink(temp).catch(()=>{});}
}
