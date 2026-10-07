import test from 'node:test';
import assert from 'node:assert/strict';
import { markdownArtifactUrl,latestNamedArtifacts } from '../web/src/artifact-links.js';

const run='de351fa19dd64a71a4cb9363738782c1';
const file={id:'file', name:'估值报告.csv', url:`/api/projects/p/artifacts/${run}/%E4%BC%B0%E5%80%BC%E6%8A%A5%E5%91%8A.csv`};

test('reply links resolve Linux, Windows and sandbox paths to attached downloads',()=>{
  for(const path of [`analysis/${run}/output/估值报告.csv`, `analysis\\${run}\\output\\估值报告.csv`, `sandbox:/analysis/${run}/output/估值报告.csv`, 'sandbox:/mnt/data/估值报告.csv', '/output/估值报告.csv','估值报告.csv']) {
    assert.equal(markdownArtifactUrl(path,[file]),file.url,path);
  }
  assert.equal(markdownArtifactUrl(encodeURI(`analysis/${run}/output/估值报告.csv`),[file]),file.url);
});

test('same-name output resolves to latest even in an old run path; history remains intact',()=>{
  const other={...file,id:'other',url:'/api/projects/p/artifacts/11111111111111111111111111111111/other.csv'};
  const history=[file,other];assert.deepEqual(latestNamedArtifacts(history),[other]);assert.equal(history.length,2);
  const early={...file,producedAt:1},late={...other,producedAt:2};assert.deepEqual(latestNamedArtifacts([early,late,early]),[late]);
  assert.equal(markdownArtifactUrl('sandbox:/mnt/data/估值报告.csv',history),other.url);
  assert.equal(markdownArtifactUrl(`analysis/${run}/output/估值报告.csv`,history),other.url);
  assert.equal(markdownArtifactUrl(file.url,history),other.url);
  const foreign=file.url.replace('/projects/p/','/projects/foreign/');assert.equal(markdownArtifactUrl(foreign,history),foreign);
  assert.equal(markdownArtifactUrl('sandbox:/mnt/data/unknown.csv',[file]),'');
  assert.equal(markdownArtifactUrl('javascript:alert(1)',[file]),'');
  assert.equal(markdownArtifactUrl('https://example.com/report',[file]),'https://example.com/report');
  assert.equal(markdownArtifactUrl('sandbox:/mnt/data/估值报告.csv',[{...file,url:'https://example.com/file'}]),'');
});

test('nested output links resolve only the exact attached relative path',()=>{
  const nested={...file,name:'model/估值报告.csv',url:`/api/projects/p/artifacts/${run}/model%2F%E4%BC%B0%E5%80%BC%E6%8A%A5%E5%91%8A.csv`};
  for(const target of [`analysis/${run}/output/model/估值报告.csv`,`analysis\\${run}\\output\\model\\估值报告.csv`,'/output/model/估值报告.csv','sandbox:/mnt/data/model/估值报告.csv','model/估值报告.csv']) {
    assert.equal(markdownArtifactUrl(target,[nested]),nested.url);
  }
  assert.equal(markdownArtifactUrl('/output/估值报告.csv',[nested]),'/output/估值报告.csv');
  assert.equal(markdownArtifactUrl('sandbox:/output/model/../估值报告.csv',[nested]),'');
  assert.equal(markdownArtifactUrl('analysis/cb1e5b17d2ed451dbcb9d8c8a49333/output/model/估值报告.csv',[nested]),nested.url);
  const other={...nested,id:'other',url:'/api/projects/p/artifacts/11111111111111111111111111111111/model%2Freport.csv'};
  assert.equal(markdownArtifactUrl('sandbox:/analysis/typo/output/model/估值报告.csv',[nested,other]),other.url);
  assert.equal(markdownArtifactUrl('analysis/11111111111111111111111111111111/output/model/估值报告.csv',[nested]),nested.url);
});
