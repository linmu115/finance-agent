import type {ExtensionFactory} from '@earendil-works/pi-coding-agent';

/** Pi's message_end replacement runs before native persistence and public events. */
export function answerBindingExtension(options:{render:(body:string)=>Promise<string>;audit:(type:string,data:any)=>Promise<unknown>;repairSent:()=>boolean;markRepair:()=>void;error:(error?:Error)=>void}):ExtensionFactory{
 return pi=>{
  pi.on('message_end',async event=>{
   const message=event.message;
   if(message.role!=='assistant'||message.stopReason!=='stop')return;
   const body=message.content.filter(b=>b.type==='text').map(b=>b.text).join('');
   if(!body.includes('{{')){options.error();return;}
   try{
    const rendered=await options.render(body);options.error();
    await options.audit('answer_bound',{template:body,rendered});
    return {message:{...message,content:[...message.content.filter(b=>b.type!=='text'),{type:'text',text:rendered}]}};
   }catch(error){
    const failure=error as Error & {code?:string};options.error(failure);
    await options.audit('answer_binding_error',{message:failure.message,code:failure.code});
    if(failure.code!=='answer_reference_error'||options.repairSent())return;
    options.markRepair();
    pi.sendMessage({customType:'answer_reference_error',content:'回答中的数值引用无法解析，请按下列实际表键修正回答：\n'+failure.message,display:false},{deliverAs:'followUp',triggerTurn:true});
   }
  });
 };
}
