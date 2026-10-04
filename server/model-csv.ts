// Input interchange: RFC 4180 CSV with JSON Pointer paths and JSON-encoded values.
// Decimal strings remain strings; object keys containing dots remain intact.
const forbidden=new Set(['__proto__','prototype','constructor']);
const quote=(s:string)=>'"'+s.replaceAll('"','""')+'"';
export function modelInputCsv(kind:string,spec:Record<string,unknown>){
 const rows=[['path','value']];
 const walk=(value:any,pointer:string)=>{
  if(value&&typeof value==='object'&&Object.keys(value).length){for(const [key,child] of Object.entries(value))walk(child,pointer+'/'+key.replaceAll('~','~0').replaceAll('/','~1'));}
  else rows.push([pointer,JSON.stringify(value)]);
 };walk({kind,spec},'');return '\uFEFF'+rows.map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n';
}
export function parseModelInputCsv(input:string):{kind:string;spec:Record<string,any>}{
 if(typeof input!=='string'||input.length>1000000)throw new Error('输入 CSV 最多 1 MB');
 const text=input.replace(/^\uFEFF/,'');let field='',row:string[]=[],rows:string[][]=[],quoted=false,ended=false;
 const endField=()=>{row.push(field);field='';ended=false;};
 const endRow=()=>{endField();if(row.some(Boolean))rows.push(row);row=[];};
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(quoted){if(c==='"'){if(text[i+1]==='"'){field+='"';i++;}else{quoted=false;ended=true;}}else field+=c;continue;}
  if(c===','){endField();continue;}if(c==='\r'||c==='\n'){if(c==='\r'&&text[i+1]==='\n')i++;endRow();continue;}
  if(ended)throw new Error('CSV 引号后存在非法字符');
  if(c==='"'){if(field)throw new Error('CSV 引号位置无效');quoted=true;}else field+=c;
 }
 if(quoted)throw new Error('CSV 引号未闭合');if(field||row.length||ended)endRow();
 if(rows.shift()?.join(',')!=='path,value')throw new Error('CSV 表头应为 path,value；路径采用 /spec/base/revenue 形式，value 是 JSON 值');
 if(rows.length>10000)throw new Error('CSV 参数最多 10000 行');
 const root:Record<string,any>={},assigned=new Set<string>();
 for(const [pointer,raw,...extra] of rows){
  if(extra.length||raw===undefined||!pointer?.startsWith('/'))throw new Error('CSV 每行必须有路径和一个 JSON 值');
  if(assigned.has(pointer)||[...assigned].some(p=>pointer.startsWith(p+'/')||p.startsWith(pointer+'/')))throw new Error('CSV 路径重复或相互覆盖');
  const keys=pointer.slice(1).split('/').map(k=>{if(/~(?![01])/u.test(k))throw new Error('无效 JSON Pointer');return k.replaceAll('~1','/').replaceAll('~0','~');});
  if(keys.length>30||keys.some(k=>forbidden.has(k)||!k))throw new Error('CSV 路径无效');
  const value=JSON.parse(raw,(k,v)=>{if(forbidden.has(k))throw new Error('CSV 包含不允许的键');return v;});
  let node:any=root;
  for(let i=0;i<keys.length;i++){
   const key=keys[i];if(Array.isArray(node)&&(!/^(0|[1-9][0-9]*)$/.test(key)||Number(key)>10000))throw new Error('CSV 数组下标无效');
   if(i===keys.length-1){node[key]=value;break;}
   node[key]??=/^(0|[1-9][0-9]*)$/.test(keys[i+1])?[]:{};
   if(!node[key]||typeof node[key]!=='object')throw new Error('CSV 路径发生冲突');node=node[key];
  }
  assigned.add(pointer);
 }
 const check=(v:any)=>{if(!v||typeof v!=='object')return;if(Array.isArray(v)&&Object.keys(v).length!==v.length)throw new Error('CSV 数组不连续');for(const child of Object.values(v))check(child);};check(root);
 if(typeof root.kind!=='string'||!root.spec||Array.isArray(root.spec)||typeof root.spec!=='object'||Object.keys(root).some(k=>!['kind','spec'].includes(k)))throw new Error('CSV 必须包含 /kind 和 /spec 下的模型参数');
 return root as {kind:string;spec:Record<string,any>};
}
