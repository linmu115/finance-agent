import { loadSettings, getSettings, ROOT } from '../server/config.js';
import { researchStore } from '../server/research.js';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
await loadSettings();
const start=Date.now(),project='research-live-development';
const search=await researchStore.search(project,getSettings().search,{query:'site:liugong.com 2025 年度报告',max_results:3});
// This is a connectivity/replay check, independent of the frozen financial holdout.
const snapshot=await researchStore.saveSnapshot(project,'https://pages.stern.nyu.edu/adamodar/New_Home_Page/lectures/approach.html');
const replay=await researchStore.read(project,snapshot.source_id);
const report={created_at:new Date().toISOString(),search:{provider:search.provider,query_id:search.query_id,result_count:search.results.length,results:search.results,usage:search.usage},source:{id:snapshot.source_id,url:snapshot.url,sha256:snapshot.sha256,paragraph_count:snapshot.paragraphs.length,byte_count:snapshot.byte_count},offline_replay:{source_id:replay.source_id,paragraph_count:replay.paragraphs.length,matching:replay.sha256===snapshot.sha256},duration_ms:Date.now()-start};
await writeFile(path.join(ROOT,'benchmark/results/research-tavily-live-v04.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({provider:search.provider,result_count:search.results.length,source_paragraphs:snapshot.paragraphs.length,replay_ok:report.offline_replay.matching,duration_ms:report.duration_ms}));
