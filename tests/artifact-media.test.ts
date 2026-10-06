import test from 'node:test';
import assert from 'node:assert/strict';
import {artifactMediaType,artifactDownloadOnly} from '../server/artifact-media.js';

test('analysis downloads use file format rather than Windows MIME registry',()=>{
 assert.equal(artifactMediaType('D:\\output\\经营现金流.CSV'),'text/csv');
 assert.equal(artifactMediaType('report.md'),'text/markdown');
 assert.equal(artifactMediaType('analysis.py'),'text/x-python');
 assert.equal(artifactDownloadOnly('analysis.py'),true);
 assert.equal(artifactDownloadOnly('chart.png'),false);
 assert.equal(artifactMediaType('untrusted.html'),'application/octet-stream');
 assert.equal(artifactDownloadOnly('untrusted.html'),true);
 assert.equal(artifactDownloadOnly('model.xlsx'),true);
});
