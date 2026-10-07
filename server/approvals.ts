import { randomUUID, createHash } from 'node:crypto';

export interface Approval { id:string; runId:string; conversationId:string; projectId:string; requestedAt:string; digest:string; operation:unknown }
export class ApprovalQueue {
 private pending=new Map<string,{value:Approval; finish:(ok:boolean)=>void}>();
 list(){return [...this.pending.values()].map(x=>structuredClone(x.value));}
 async request(context:{runId:string;conversationId:string;projectId:string},operation:unknown,signal:AbortSignal):Promise<Approval>{
  signal.throwIfAborted();
  const value:Approval={...context,id:randomUUID(),requestedAt:new Date().toISOString(),operation:structuredClone(operation),digest:createHash('sha256').update(JSON.stringify(operation)).digest('hex')};
  return new Promise((resolve,reject)=>{
   const abort=()=>finish(false);
   const finish=(ok:boolean)=>{this.pending.delete(value.id);signal.removeEventListener('abort',abort);ok?resolve(value):reject(new Error(signal.aborted?'任务已停止，授权失效':'用户未授权此操作；请勿重复申请相同操作'));};
   this.pending.set(value.id,{value,finish});signal.addEventListener('abort',abort,{once:true});
   if(signal.aborted)abort();
  });
 }
 decide(id:string,digest:string,allow:boolean){
  const item=this.pending.get(id);if(!item)throw Object.assign(new Error('授权请求已结束或失效'),{status:409});
  if(item.value.digest!==digest)throw Object.assign(new Error('操作内容已改变，请重新核对'),{status:409});
  item.finish(allow);
 }
}
export const ADMIN_TOOL={name:'request_database_operation',description:"请求一次弹窗授权并说明用途：SQL/DDL、破坏性写入或 read_other_project。SQL 不自动按项目过滤，运行/审计表受保护。沙箱可输出 /output/database_changes.json={commands:[{sql,parameters:[]}]}，用 analysis_changes 提交。主库不挂载；拒绝后不绕过或重复申请。",inputSchema:{type:'object',properties:{operation:{type:'string',enum:['sql','read_other_project','update_fact','delete_fact','delete_document','analysis_changes']},reason:{type:'string',minLength:1,maxLength:2000},sql:{type:'string',maxLength:20000},parameters:{type:'array',items:{anyOf:[{type:'string'},{type:'number'},{type:'null'}]},maxItems:1000},target_project_id:{type:'string'},fact_id:{type:'string'},document_id:{type:'string'},value:{type:'string'},analysis_run_id:{type:'string'}},required:['operation','reason'],additionalProperties:false}};
