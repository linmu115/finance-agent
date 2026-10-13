// The stop check belongs at the HTTP boundary, after caller-side persistence.
export async function requestJson(route,body,{stopped,fetchImpl=fetch}){
 if(body!==undefined&&stopped()){const e=new Error('Operator stopped before POST');e.code='NOT_DISPATCHED';throw e;}
 const res=await fetchImpl('http://127.0.0.1:3001'+route,{signal:AbortSignal.timeout(120000),...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
 if(!res.ok)throw Error(`HTTP ${res.status} ${route}: ${await res.text()}`);return res.json();
}
