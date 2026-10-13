// Scheduling only: API/profile/freeze verification remains in the execution adapter.
// A chain owns one slot until all its dependent turns settle. No HTTP in this module.
export async function scheduleChains(chains, runTurn, {signal, onEvent=()=>{}}={}) {
 const active=new Map(),records=[];let next=0,stopped=Boolean(signal?.aborted),failure=null;
 const stop=()=>{stopped=true;};signal?.addEventListener('abort',stop,{once:true});
 const execute=async chain=>{
  for(const turn of chain.turns){
   if(stopped||signal?.aborted){records.push({chain:chain.id,task:turn.task,status:'not_submitted_cancelled'});break;}
   onEvent({type:'dispatch',chain:chain.id,arm:chain.arm,task:turn.task});
   // Event consumers can cancel synchronously. Check again immediately before
   // entering the adapter; it must also check immediately before each HTTP POST.
   if(stopped||signal?.aborted){records.push({chain:chain.id,arm:chain.arm,task:turn.task,status:'not_submitted_cancelled'});break;}
   const outcome=await runTurn(turn,chain);
   if(!outcome||!['completed','infrastructure_failure','product_failure','validity_failure','cancelled'].includes(outcome.status))throw Error('runTurn must return an explicit outcome');
   records.push({chain:chain.id,arm:chain.arm,task:turn.task,...outcome});
   if(outcome.status==='validity_failure'||outcome.status==='cancelled'){stopped=true;break;}
   if(outcome.status!=='completed'&&!outcome.usable_parent){
    const i=chain.turns.indexOf(turn);
    for(const child of chain.turns.slice(i+1))records.push({chain:chain.id,arm:chain.arm,task:child.task,status:'dependency_unavailable'});
    break;
   }
  }
 };
 try {
  while(next<chains.length||active.size){
   while(!stopped&&!signal?.aborted&&active.size<2&&next<chains.length){
    const chain=chains[next];
    if([...active.values()].some(v=>v.arm===chain.arm))break;
    next++;
    const promise=execute(chain).catch(error=>{stopped=true;failure??=error;}).finally(()=>{active.delete(chain.id);onEvent({type:'chain_settled',chain:chain.id,arm:chain.arm});});
    active.set(chain.id,{arm:chain.arm,promise});
   }
   if(active.size)await Promise.race([...active.values()].map(v=>v.promise));
   else break;
  }
  if(failure)throw failure;
  return {records,stopped:stopped||Boolean(signal?.aborted),unsubmitted_chains:chains.slice(next).map(c=>c.id)};
 } finally {signal?.removeEventListener('abort',stop);}
}
