import type { Express } from 'express';
import type { FinanceService } from './mcp.js';
import { z } from 'zod';

export function installDocumentLibraryApi(app:Express,service:FinanceService,active:(project:string)=>boolean){
 const id=z.string().regex(/^[A-Za-z0-9_-]{1,100}$/);
 app.delete('/api/projects/:projectId/documents/:documentId',async(req,res,next)=>{
  try{
   const project=id.parse(req.params.projectId),document=id.parse(req.params.documentId);
   // Explicit click confirmation; this route is never registered as an LLM tool.
   z.object({confirm_document_id:z.literal(document)}).parse(req.body);
   if(active(project)){res.status(409).json({error:{message:'当前项目有任务正在执行，请完成或停止任务后删除资料。'}});return;}
   res.json((await service.call('delete_library_document',{project_id:project,document_id:document})).data);
  }catch(error){next(error);}
 });
}
