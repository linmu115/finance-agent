import {modelCatalog} from './model-runtime.js';
import {artifactMediaType,artifactDownloadOnly} from './artifact-media.js';
import { mkdir, readFile, readdir, stat, realpath } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { APP_VERSION,DATA,ROOT,HOST,PORT,loadSettings,getSettings,publicSettings,saveSettings,testSettings,redactError,requireModel } from './config.js';
import {acquireStartupGuard} from './startup-guard.js';
import type { Conversation } from './types.js';
import { installProjectApi } from './project-api.js';
import { projectResources } from './project-resources.js';
import { annotationsSchema } from './annotations.js';
import { installDocumentLibraryApi } from './document-library-api.js';

const startup=await acquireStartupGuard({dataDir:DATA,host:HOST,port:PORT});
let cleanup:()=>Promise<unknown>=async()=>{};
try {
// Import business modules only after both port and DATA ownership are held.
const [{default:express},{default:multer},{z},{FinanceService,safeDataPath},{RunManager},{normalizeEvaluation},{installWorkspaceApi},{installResearchApi}]=await Promise.all([
 import('express'),import('multer'),import('zod'),import('./mcp.js'),import('./runs.js'),import('./evaluation-budget.js'),import('./workspace-api.js'),import('./research-api.js'),
]);
await loadSettings();
const service=new FinanceService();
cleanup=()=>service.close();
await service.connect();
const runs=new RunManager(service);
cleanup=()=>runs.shutdown().finally(()=>service.close());
const app=express();
app.disable('x-powered-by');
app.use((req,res,next)=>{
 const host=req.headers.host?.toLowerCase();
 const allowed=new Set(['127.0.0.1:'+PORT,'localhost:'+PORT,'[::1]:'+PORT]);
 if(!host || !allowed.has(host)){res.status(403).json({error:{code:'HOST_REJECTED',message:'仅允许本机访问'}});return;}
 const origin=req.headers.origin;
 if(origin && !['http://127.0.0.1:'+PORT,'http://localhost:'+PORT,'http://127.0.0.1:5173','http://localhost:5173'].includes(origin)){res.status(403).json({error:{code:'ORIGIN_REJECTED',message:'不允许跨站访问本地工作空间'}});return;}
 res.setHeader('X-Content-Type-Options','nosniff');
 res.setHeader('Referrer-Policy','no-referrer');
 res.setHeader('Cross-Origin-Resource-Policy','same-origin');
 res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'");
 next();
});
app.use(express.json({limit:'2mb'}));
const route=(fn:(req:any,res:any)=>Promise<any>)=>(req:any,res:any,next:any)=>Promise.resolve(fn(req,res)).catch(next);
const idSchema=z.string().regex(/^[A-Za-z0-9_-]{1,100}$/);
const readId=(id:any)=>idSchema.parse(id);
const projects=async()=>{
 const result=await service.call('list_projects',{});
 return result.data?.projects || result.data?.items || (Array.isArray(result.data)?result.data:[]);
};
const ensureProject=async(id:string)=>{
 id=readId(id);const all=await projects();if(!all.some((p:any)=>(p.project_id||p.id)===id)){const e:any=new Error('项目不存在');e.status=404;throw e;}return id;
};
const toDoc=(d:any)=>({id:d.document_id || d.id,name:d.original_name || d.name,status:d.state || d.status,statusLabel:d.status_label,ingestion:d.ingestion,pageCount:d.page_count,company:d.company,sha256:d.sha256,warnings:d.warnings || [],jobId:d.job_id,createdAt:d.created_at,error:d.error,tableCount:d.table_count,factCount:d.fact_count,researchRecordCount:d.research_record_count,profile:d.profile,processing:d.processing,normalization:d.normalization,normalization_engine:d.normalization_engine,normalized_fact_count:d.normalized_fact_count,legacy_fact_count:d.legacy_fact_count});
const docList=(r:any)=>r.data?.documents || r.data?.items || (Array.isArray(r.data)?r.data:[]);
const documentInfo=async(projectId:string,documentId:string)=>{
 const r=await service.call('get_document',{project_id:readId(projectId),document_id:readId(documentId)});return r.data?.document || r.data;
};
const allProjects=await projects();
if(!allProjects.length)await service.call('create_project',{project_id:'default',name:'金融研究'});
for(const p of await projects()){
 const id=p.project_id || p.id;
 await service.configure(id,getSettings());
 await runs.recover(id);await projectResources.load(id);
}
app.get('/api/models',route(async(_req,res)=>res.json(await modelCatalog())));
app.get('/api/health',route(async(_req,res)=>res.status(service.connected?200:503).json({ok:service.connected,version:APP_VERSION,service:service.connected?'connected':'disconnected',modelConfigured:!!getSettings().llm.model})));
app.get('/api/projects',route(async(_req,res)=>res.json({projects:(await projects()).map((p:any)=>({id:p.project_id||p.id,name:p.name,createdAt:p.created_at,documentCount:p.document_count}))})));
app.post('/api/projects',route(async(req,res)=>{
 const {name}=z.object({name:z.string().trim().min(1).max(100)}).parse(req.body);
 const id=randomUUID();await service.call('create_project',{project_id:id,name});await service.configure(id,getSettings());await projectResources.load(id);res.status(201).json({id,name});
}));
app.get('/api/projects/:projectId/conversations',route(async(req,res)=>{
 const id=await ensureProject(req.params.projectId);const list=await service.listState<Conversation>(id,'conversations');
 res.json({conversations:list.map(({messages,...c})=>({...c,activeRunId:runs.activeFor(c.id)})).sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt))});
}));
app.post('/api/projects/:projectId/conversations',route(async(req,res)=>{
 const projectId=await ensureProject(req.params.projectId),time=new Date().toISOString();
 const chat:Conversation={id:randomUUID(),projectId,title:'新对话',messages:[],createdAt:time,updatedAt:time};
 await service.putState(projectId,'conversations',chat.id,chat);runs.indexConversation(chat.id,projectId);res.status(201).json(chat);
}));
app.get('/api/conversations/:id',route(async(req,res)=>{
 const chat=await runs.getConversation(readId(req.params.id));res.json({...chat,activeRunId:runs.activeFor(chat.id)});
}));
app.post('/api/conversations/:id/messages',route(async(req,res)=>{
 const {content,documentIds,evaluation,annotations,mode}=z.object({mode:z.enum(['steer','followUp']).default('steer'),content:z.string().max(50000).default(''),documentIds:z.array(idSchema).default([]),evaluation:z.unknown().optional(),annotations:annotationsSchema}).parse(req.body);
 if(!content.trim()&&!documentIds.length&&!annotations.length){res.status(400).json({error:{code:'EMPTY_MESSAGE',message:'请填写消息或添加附件、引用'}});return;}
 requireModel();
 const chat=await runs.getConversation(readId(req.params.id));
 for(const id of documentIds)await documentInfo(chat.projectId,id);
 const run=await runs.start(chat,content,documentIds,undefined,normalizeEvaluation(evaluation),annotations,mode);
 res.status(202).json({runId:run.id,messageId:run.messageId,userMessageId:run.userMessageId,inputStatus:run.inputStatus});
}));
app.get('/api/runs/:runId',route(async(req,res)=>res.json(await runs.getRun(readId(req.params.runId)))));
app.get('/api/runs/:runId/events',route(async(req,res)=>runs.subscribe(readId(req.params.runId),req,res)));
app.post('/api/runs/:runId/cancel',route(async(req,res)=>res.json(await runs.cancel(readId(req.params.runId)))));
app.get('/api/projects/:projectId/documents',route(async(req,res)=>{
 const id=await ensureProject(req.params.projectId);const r=await service.call('list_documents',{project_id:id});res.json({documents:docList(r).map(toDoc)});
}));
app.get('/api/projects/:projectId/documents/:documentId',route(async(req,res)=>res.json(toDoc(await documentInfo(req.params.projectId,req.params.documentId)))));
app.get('/api/projects/:projectId/documents/:documentId/file',route(async(req,res)=>{
 const d=await documentInfo(req.params.projectId,req.params.documentId),filename=safeDataPath(d.relative_path);
 const actual=await realpath(filename);if(!actual.startsWith((await realpath(DATA))+path.sep))throw new Error('文件路径越界');
 res.type(d.media_type || 'application/octet-stream');
 res.setHeader('Content-Disposition',"inline; filename*=UTF-8''"+encodeURIComponent(d.original_name));
 res.sendFile(actual);
}));
app.get('/api/projects/:projectId/documents/:documentId/pages/:page',route(async(req,res)=>{
 const r=await service.call('get_source_page',{project_id:readId(req.params.projectId),document_id:readId(req.params.documentId),page:z.coerce.number().int().min(1).parse(req.params.page)});
 const data=r.data;
 if(data.image_relative_path)data.imageUrl='/api/projects/'+req.params.projectId+'/documents/'+req.params.documentId+'/pages/'+req.params.page+'/image';
 delete data.image_relative_path;res.json(data);
}));
app.get('/api/projects/:projectId/documents/:documentId/pages/:page/image',route(async(req,res)=>{
 const r=await service.call('get_source_page',{project_id:readId(req.params.projectId),document_id:readId(req.params.documentId),page:z.coerce.number().int().min(1).parse(req.params.page)});
 if(!r.data.image_relative_path){res.status(404).json({error:{code:'NO_IMAGE',message:'此资料没有页面图像'}});return;}
 const filename=safeDataPath(r.data.image_relative_path),actual=await realpath(filename);
 if(!actual.startsWith((await realpath(DATA))+path.sep))throw new Error('图像路径越界');res.sendFile(actual);
}));
app.get('/api/projects/:projectId/documents/:documentId/tables',route(async(req,res)=>{
 const r=await service.call('get_source_table',{project_id:readId(req.params.projectId),document_id:readId(req.params.documentId)});
 res.json(r.data);
}));
const upload=multer({
 storage:multer.diskStorage({
  destination:async(req:any,_file,cb)=>{try{const dir=path.join(DATA,'uploads',readId(req.params.projectId));await mkdir(dir,{recursive:true});cb(null,dir);}catch(e){cb(e as Error,'');}},
  filename:(_req,file,cb)=>cb(null,randomUUID()+path.extname(file.originalname).toLowerCase()),
 }),
 limits:{fileSize:50*1024*1024,files:8,fields:4},
 fileFilter:(_req,file,cb)=>{
  if(!['.pdf','.xlsx','.xls','.csv','.tsv'].includes(path.extname(file.originalname).toLowerCase())){cb(new Error('支持PDF、Excel、CSV和TSV'));return;}cb(null,true);
 },
});
app.post('/api/projects/:projectId/uploads',route(async(req,res)=>{
 await ensureProject(req.params.projectId);
 await new Promise<void>((resolve,reject)=>upload.array('files',8)(req,res,(error:any)=>error?reject(error):resolve()));
 const files=(req.files||[]) as Express.Multer.File[];
 if(!files.length){res.status(400).json({error:{code:'NO_FILES',message:'没有收到附件'}});return;}
 const docs=[];
 for(const f of files){
   let original=f.originalname;
   const repaired=Buffer.from(original,'latin1').toString('utf8');if(!repaired.includes('\uFFFD')&&/[^\x00-\x7F]/.test(repaired))original=repaired;
   const r=await service.call('register_document',{project_id:req.params.projectId,path:f.path,original_name:original});
   docs.push(toDoc({...r.data,original_name:original}));
 }
 res.status(202).json({documents:docs});
}));
app.get('/api/settings',(_req,res)=>res.json(publicSettings()));
app.put('/api/settings',route(async(req,res)=>{
 const result=await saveSettings(req.body);for(const p of await projects())await service.configure(p.project_id||p.id,getSettings());res.json(result);
}));
app.post('/api/settings/test',route(async(req,res)=>{
 const {section}=z.object({section:z.enum(['llm','embedding','ocr'])}).parse(req.body);
 res.json(await testSettings(section));
}));
app.get('/api/benchmark/results',route(async(_req,res)=>{
 const dir=path.join(ROOT,'benchmark','results'),reports:any[]=[];
 try{for(const file of await readdir(dir)){if(!file.endsWith('.json'))continue;try{reports.push({name:file,...JSON.parse(await readFile(path.join(dir,file),'utf8'))});}catch{}}}catch{}
 res.json({runs:reports.filter(x=>!x.runtime),runtime:reports.filter(x=>x.runtime)});
}));
app.get('/api/projects/:projectId/artifacts/:runId/:name',route(async(req,res)=>{
 // The runner validates the exact relative name against its project-owned
 // manifest, rejects traversal/links, and verifies the file hash.
 const name=z.string().min(1).parse(req.params.name);
 const r=await service.call('get_artifact_metadata',{project_id:readId(req.params.projectId),run_id:readId(req.params.runId),name});
 const d=r.data,filename=safeDataPath(d.relative_path),actual=await realpath(filename);
 if(!actual.startsWith((await realpath(DATA))+path.sep))throw new Error('产物路径越界');
 const type=artifactMediaType(actual);
 res.type(type).setHeader('X-Content-Type-Options','nosniff');if(req.query.download||artifactDownloadOnly(actual))res.setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent(d.name||path.basename(actual)));res.sendFile(actual);
}));
app.post('/api/conversations/:id/report-package',route(async(req,res)=>{
 const chat=await runs.getConversation(readId(req.params.id));
 const {exportReportPackage}=await import('./report-package.js');
 const result=await exportReportPackage(service,chat);
 res.type('application/zip').setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent('财报分析报告.zip'));
 res.sendFile(safeDataPath(result.relative_path));
}));
app.get('/api/conversations/:id/export',route(async(req,res)=>{
 const chat=await runs.getConversation(readId(req.params.id));
 const text='# '+chat.title+'\n\n'+chat.messages.map(m=>'## '+(m.role==='user'?'用户':'金融研究')+'\n\n'+m.content+'\n\n'+(m.annotations||[]).map((a,i)=>`引用 ${i+1}\n> ${a.text.replace(/\n/g,'\n> ')}\n补充说明：${a.comment||'无'}\n`).join('\n')+(m.sources||[]).map(s=>'- 来源 '+s.documentId+(s.page?' 第'+s.page+'页':'')+(s.quote?'：'+s.quote:'')).join('\n')).join('\n\n');
 res.type('text/markdown; charset=utf-8').setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent(chat.title+'.md'));res.send(text);
}));
installWorkspaceApi(app,service);
installDocumentLibraryApi(app,service,project=>runs.activeInProject(project));
installResearchApi(app,ensureProject,service);
installProjectApi(app,service,runs,ensureProject);
app.use('/api',(_req,res)=>res.status(404).json({error:{code:'NOT_FOUND',message:'接口不存在'}}));
const dist=path.join(ROOT,'web','dist');app.use(express.static(dist,{index:'index.html'}));
app.get('/{*splat}',route(async(_req,res)=>{try{await stat(path.join(dist,'index.html'));res.sendFile(path.join(dist,'index.html'));}catch{res.type('text').status(503).send('前端尚未构建，请运行 npm run build');}}));
app.use((error:any,_req:any,res:any,_next:any)=>{
 const status=error.status || (error instanceof z.ZodError?400:error.code==='LIMIT_FILE_SIZE'?413:400);
 res.status(status).json({error:{code:error.code || 'REQUEST_FAILED',message:redactError(error)}});
});
startup.activate(app);
console.log('金融研究已启动 http://'+HOST+':'+PORT);
let stopping=false;
for(const signal of ['SIGINT','SIGTERM'] as const)process.on(signal,()=>{if(stopping)return;stopping=true;startup.stopAccepting();cleanup().finally(()=>startup.close()).finally(()=>process.exit(0));});
} catch(error) {
 try{await cleanup();}finally{await startup.close();}
 throw error;
}
