import type { Express } from 'express';
import type { FinanceService } from './mcp.js';
import type { RunManager } from './runs.js';
import { projectResources } from './project-resources.js';
import { z } from 'zod';
export function installProjectApi(app:Express,service:FinanceService,runs:RunManager,ensureProject:(id:string)=>Promise<string>){
 const route=(fn:(req:any,res:any)=>Promise<any>)=>(req:any,res:any,next:any)=>Promise.resolve(fn(req,res)).catch(next);
 app.get('/api/approvals',(_req,res)=>res.json({requests:runs.approvals.list()}));
 app.post('/api/approvals/:id',route(async(req,res)=>{
  if(!req.headers.origin||!req.is('application/json'))throw Object.assign(new Error('请在本地应用授权窗口确认'),{status:403});
  const input=z.object({digest:z.string().length(64),allow:z.boolean()}).strict().parse(req.body);
  runs.approvals.decide(req.params.id,input.digest,input.allow);res.json({ok:true});
 }));
 app.get('/api/projects/:projectId/resources',route(async(req,res)=>{const id=await ensureProject(req.params.projectId);res.json(await projectResources.load(id));}));
 app.put('/api/projects/:projectId/resources',route(async(req,res)=>{const id=await ensureProject(req.params.projectId);res.json(await projectResources.save(id,z.object({rules:z.string().max(40000),enabled:z.array(z.string()),revision:z.string()}).strict().parse(req.body)));}));
 app.get('/api/conversations/:id/attachment-flows',route(async(req,res)=>{
  const chat=await runs.getConversation(req.params.id);
  const owners=chat.messages.flatMap(m=>m.runId?[m.runId]:[]);
  const result=await service.call('get_attachment_flows',{project_id:chat.projectId,owner_run_ids:owners,flow_id:req.query.flow_id||undefined,offset:Math.max(0,Number(req.query.offset)||0)});
  const documents=[...new Set(chat.messages.flatMap(m=>m.attachments||[]))];
  res.json({...result.data,document_ids:documents});
 }));
}
