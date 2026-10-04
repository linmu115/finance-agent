import test from 'node:test';
import assert from 'node:assert/strict';
import {chartSource} from '../web/src/chartValues.js';
const fact=(value:string,raw:string,scale:string)=>({value,raw_value:raw,source_ref:{normalization:{scale}}});
test('plot selects exact yuan disclosure only when rounded report units agree',()=>{
 const exact=fact('170899152276.34','170,899,152,276.34','1');
 const rounded=fact('170899152300','17089915.23','10000');
 assert.equal(chartSource([rounded,exact]),exact);
 assert.equal(chartSource([exact,rounded]),exact);
 assert.equal(chartSource([fact('-1234567.89','-1234567.89','1'),fact('-1234600','(123.46)','10000')])?.value,'-1234567.89');
});
test('conflicting same-precision cents and missing precision are never silently merged',()=>{
 assert.equal(chartSource([fact('9007199254740993.01','9007199254740993.01','1'),fact('9007199254740993.02','9007199254740993.02','1')]),undefined);
 assert.equal(chartSource([fact('100.00','100.00','1'),fact('101.00','101.00','1')]),undefined);
 assert.equal(chartSource([{value:'100'},{value:'101'}]),undefined);
 assert.equal(chartSource([{value:'100.00'},{value:'100'}])?.value,'100.00');
});
