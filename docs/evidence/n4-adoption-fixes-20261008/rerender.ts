// Re-render captured templates only. This script never starts a session/model.
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {annotateAnswer} from '../../server/answer-semantics.js';
const base=path.resolve('tmp/adoption');
const summary=JSON.parse(await readFile(path.join(base,'summary.json'),'utf8'));
for(const x of summary){
 const dir=path.join(base,'runs',x.case+'-'+x.profile);
 const result=JSON.parse(await readFile(path.join(dir,'result.json'),'utf8'));
 const answer=result.conversation.messages.at(-1);
 const template=await readFile(path.join(dir,'template.md'),'utf8');
 await writeFile(path.join(dir,'rerender-template.md'),annotateAnswer(template,answer.sources??[]));
}
console.log('Reclassified 12 captured templates; zero model requests.');
