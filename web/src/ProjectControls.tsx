import { useEffect, useState } from 'react';
import { api, errorText } from './api';
import Modal from './Modal';
import type { Project } from './types';
import './project-controls.css';

export function ProjectRules({project,onClose}:{project:Project;onClose:()=>void}){
 const [data,setData]=useState<any>(),[rules,setRules]=useState(''),[enabled,setEnabled]=useState<string[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[preview,setPreview]=useState<string>();
 useEffect(()=>{const c=new AbortController();api<any>(`/api/projects/${project.id}/resources`,{signal:c.signal}).then(r=>{setData(r);setRules(r.rules);setEnabled(r.skills.filter((s:any)=>s.enabled).map((s:any)=>s.name));}).catch(e=>{if(!c.signal.aborted)setError(errorText(e));});return()=>c.abort();},[project.id]);
 async function save(){setBusy(true);setError('');try{const r=await api<any>(`/api/projects/${project.id}/resources`,{method:'PUT',body:JSON.stringify({rules,enabled,revision:data.revision})});setData(r);setNotice('已保存；从下一次会话任务开始生效。');}catch(e){setError(errorText(e));}finally{setBusy(false);}}
 return <Modal label="项目约定与技能" className="control-dialog rules-dialog" onClose={onClose}><header><h2>{project.name} · 项目约定与技能</h2><button className="plain-button" onClick={onClose}>关闭</button></header><p>本项目各段会话共用 agent.md。编辑后在下一次任务加载。</p><label htmlFor="project-rules">项目约定 · agent.md</label><textarea id="project-rules" disabled={!data||busy} value={rules} maxLength={40000} onChange={e=>{setRules(e.target.value);setNotice('');}} rows={10}/><h3>专业技能</h3>{data?.skills.map((s:any)=><div className="skill-row" key={s.name}><label><input type="checkbox" checked={enabled.includes(s.name)} onChange={e=>setEnabled(e.target.checked?[...enabled,s.name]:enabled.filter(x=>x!==s.name))}/><b>{s.name}</b><small>{s.description}</small></label><button className="plain-button" onClick={()=>setPreview(preview===s.name?undefined:s.name)}>查看步骤</button>{preview===s.name&&<pre>{s.content}</pre>}</div>)}{error&&<p role="alert" className="error-text">{error}</p>}{notice&&<p role="status">{notice}</p>}<footer><button className="primary-button" disabled={!data||busy} onClick={()=>void save()}>{busy?'保存中…':'保存项目设置'}</button></footer></Modal>;
}
