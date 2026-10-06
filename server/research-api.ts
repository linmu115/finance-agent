import type { Express } from 'express';
import { z } from 'zod';
import { researchStore, searchWeb } from './research.js';
import { getSettings } from './config.js';
import { ResearchWorkspace,artifactCsv,deliveryFile } from './research-artifacts.js';
import { artifactMediaType } from './artifact-media.js';
import type { FinanceService } from './mcp.js';
import { modelInputCsv, parseModelInputCsv } from './model-csv.js';
export function installResearchApi(app:Express,ensureProject:(id:string)=>Promise<string>,service:FinanceService){
 const workspace=new ResearchWorkspace(service);
 const route=(fn:(req:any,res:any)=>Promise<any>)=>(req:any,res:any,next:any)=>Promise.resolve(fn(req,res)).catch(next);
 app.get('/api/projects/:projectId/assets/catalog',route(async(req,res)=>{
  const p=await ensureProject(req.params.projectId);
  res.json((await service.call('get_asset_catalog',{project_id:p,...(req.query.entity?{entity_key:z.string().max(500).parse(req.query.entity)}:{})})).data);
 }));
 app.get('/api/projects/:projectId/assets/records',route(async(req,res)=>{
  const p=await ensureProject(req.params.projectId);
  const filters=z.record(z.string(),z.unknown()).parse(req.query.filters?JSON.parse(String(req.query.filters)):{});
  const offset=z.coerce.number().int().min(0).parse(req.query.offset??0),limit=z.coerce.number().int().min(1).max(200).parse(req.query.limit??30);
  const result=await service.call('query_research_records',{project_id:p,filters,offset,limit});
  res.json({...result.data,warnings:result.warnings});
 }));
 app.post('/api/projects/:projectId/research/models/import-csv',route(async(req,res)=>{const p=await ensureProject(req.params.projectId);const parsed=parseModelInputCsv(z.string().max(1000000).parse(req.body.csv));await service.call('get_research_model_schema',{project_id:p,kind:parsed.kind});res.json(parsed);}));
 app.get('/api/projects/:projectId/research/artifacts/:id/input-csv',route(async(req,res)=>{const p=await ensureProject(req.params.projectId),a=await workspace.get(p,req.params.id,req.query.revision);if(!a.spec)throw new Error('此成果不是模型');res.type('text/csv').setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent(a.title+'-输入.csv')).send(modelInputCsv(a.kind,a.spec));}));
 app.get('/api/projects/:projectId/research/sources',route(async(req,res)=>{const id=await ensureProject(req.params.projectId);res.json({sources:await researchStore.list(id)});}));
 app.get('/api/projects/:projectId/research/sources/:sourceId',route(async(req,res)=>{const id=await ensureProject(req.params.projectId);res.json(await researchStore.get(id,req.params.sourceId));}));
 app.get('/api/projects/:projectId/research/sources/:sourceId/raw',route(async(req,res)=>{const id=await ensureProject(req.params.projectId),blob=await researchStore.blob(id,req.params.sourceId);res.type('application/octet-stream');res.setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent(blob.snapshot.title+(blob.snapshot.kind==='pdf'?'.pdf':blob.snapshot.kind==='text'?'.txt':'.html')));res.sendFile(blob.path);}));
 app.post('/api/settings/search/test',route(async(_req,res)=>{const start=Date.now(),r=await searchWeb(getSettings().search,{query:'site.sse.com.cn 上市公司公告',max_results:1});res.json({ok:true,message:'搜索连接成功，已收到真实结果',provider:r.provider,resultCount:r.results.length,latencyMs:Date.now()-start});}));
 app.get('/api/projects/:projectId/research/artifacts',route(async(req,res)=>{const p=await ensureProject(req.params.projectId);res.json({artifacts:(await workspace.list(p)).map(({spec,result,content,...metadata})=>metadata)});}));
 app.get('/api/projects/:projectId/research/artifacts/:id',route(async(req,res)=>{const p=await ensureProject(req.params.projectId);res.json(await workspace.get(p,req.params.id,req.query.revision));}));
 app.post('/api/projects/:projectId/research/models',route(async(req,res)=>{const p=await ensureProject(req.params.projectId);res.status(201).json(await workspace.model(p,req.body));}));
 app.get('/api/projects/:projectId/research/models/schema/:kind',route(async(req,res)=>{const p=await ensureProject(req.params.projectId);res.json((await service.call('get_research_model_schema',{project_id:p,kind:req.params.kind})).data);}));
 app.get('/api/projects/:projectId/research/deliveries/:deliveryId/:name',route(async(req,res)=>{
  const p=await ensureProject(req.params.projectId),file=await deliveryFile(p,String(req.params.deliveryId),String(req.params.name));
  res.type(artifactMediaType(file.name)).setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent(String(req.query.as||file.name).replace(/[\\/:*?"<>|\x00-\x1f]/g,'_')));
  res.send(file.bytes);
 }));
 app.get('/api/projects/:projectId/research/artifacts/:id/export',route(async(req,res)=>{const p=await ensureProject(req.params.projectId),a=await workspace.get(p,req.params.id,req.query.revision);const format=z.enum(['json','csv']).parse(req.query.format||'json');res.setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent(a.title+'.'+format));res.type(format==='json'?'application/json':'text/csv');res.send(format==='json'?JSON.stringify(a,null,2):artifactCsv(a,String(req.query.table||'')));}));
}
