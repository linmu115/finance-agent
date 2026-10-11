import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
process.env.FINANCE_DATA_DIR=await mkdtemp(path.join(tmpdir(),'report-package-single-flight-'));
const {exportReportPackage}=await import('../server/report-package.js');
const chat=(id:string):any=>({id,projectId:'p',title:'财报分析',messages:[{id:'m',role:'assistant',status:'completed',content:'现金流分析',createdAt:'2026-10-12'}]});

test('two export requests share one prepare/render and result',{timeout:10000},async()=>{
 let release!:()=>void,started!:()=>void;
 const gate=new Promise<void>(resolve=>release=resolve),entered=new Promise<void>(resolve=>started=resolve);
 const calls:string[]=[];
 const service:any={call:async(name:string)=>{calls.push(name);
  if(name==='prepare_report_package')return {data:{package_id:'one',markdown:'# 财报分析报告'}};
  started();await gate;return {data:{package_id:'one',relative_path:'one/report_package.zip'}};
 }};
 const first=exportReportPackage(service,chat('same')),second=exportReportPackage(service,chat('same'));
 assert.equal(first,second);await entered;
 assert.deepEqual(calls,['prepare_report_package','finish_report_package']);release();
 const results=await Promise.all([first,second]);assert.deepEqual(results[0],results[1]);
});

test('failed export releases its slot, while a different conversation is independent',async()=>{
 let prepares=0,finishes=0;
 const service:any={call:async(name:string)=>{
  if(name==='prepare_report_package'){prepares++;return {data:{package_id:'p',markdown:'report'}};}
  if(++finishes===1)throw new Error('PDF worker stopped');return {data:{package_id:'done'}};
 }};
 await assert.rejects(exportReportPackage(service,chat('retry')),/PDF worker stopped/);
 assert.equal((await exportReportPackage(service,chat('retry'))).package_id,'done');
 await Promise.all([exportReportPackage(service,chat('a')),exportReportPackage(service,chat('b'))]);
 assert.equal(prepares,4);assert.equal(finishes,4);
});
