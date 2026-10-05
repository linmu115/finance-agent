import {useEffect,useState} from 'react';
import {api,errorText} from './api';
import type {Settings} from './types';
type CatalogModel={provider:string;id:string;name:string;reasoning:boolean;contextWindow:number;maxTokens:number;configured:boolean};
export default function ModelCatalogFields({value,onChange}:{value:Settings['llm'];onChange:(patch:Partial<Settings['llm']>)=>void}){
 const [catalog,setCatalog]=useState<{path:string;models:CatalogModel[];error?:string}>();
 const [error,setError]=useState('');
 useEffect(()=>{void api<{path:string;models:CatalogModel[];error?:string}>('/api/models').then(setCatalog).catch(e=>setError(errorText(e)));},[]);
 const providers=[...new Set(catalog?.models.map(m=>m.provider)||[])].sort();
 const choose=(model:CatalogModel)=>onChange({provider:model.provider,model:model.id,contextWindow:model.contextWindow,maxTokens:Math.min(value.maxTokens||32768,model.maxTokens)});
 return <>
  <label htmlFor="llm-provider">模型来源</label>
  <select id="llm-provider" value={value.provider} onChange={event=>{
   const provider=event.target.value;
   if(provider==='openai-compatible'){onChange({provider});return;}
   const model=catalog?.models.find(m=>m.provider===provider);if(model){choose(model);onChange({baseUrl:'',apiKey:'',hasKey:false});}
  }}><option value="openai-compatible">现有 API 配置 / 自定义兼容接口</option>{providers.map(provider=><option key={provider} value={provider}>{provider}{catalog?.models.some(m=>m.provider===provider&&m.configured)?' · 已配置':''}</option>)}</select>
  {value.provider!=='openai-compatible'&&<><label htmlFor="llm-catalog-model">Pi 模型目录</label><select id="llm-catalog-model" value={value.model} onChange={event=>{const m=catalog?.models.find(m=>m.provider===value.provider&&m.id===event.target.value);if(m)choose(m);}}>{catalog?.models.filter(m=>m.provider===value.provider).map(m=><option key={m.id} value={m.id}>{m.name} · {m.id}</option>)}</select><p className="field-note">沿用 Pi 的接口、认证及思考能力配置。修改全局模型文件后，下一次任务会重新读取。</p></>}
  {catalog&&<p className="field-note">全局模型文件：{catalog.path}</p>}
  {(error||catalog?.error)&&<p className="error-text" role="alert">{error||catalog?.error}</p>}
 </>;
}
