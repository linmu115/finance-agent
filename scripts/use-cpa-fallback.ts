// Apply the user-authorized local CPA profile when DeepSeek quota is exhausted.
// No prompt is replayed. Continue the existing conversation after switching.
import path from 'node:path';
const port=Number(process.argv[2]||3001);
if(!Number.isInteger(port)||port<1||port>65535)throw Error('Invalid local application port');
process.env.FINANCE_DATA_DIR=path.resolve('data/provider-profiles/cpa-gpt-6-luna');
const {loadSettings}=await import('../server/config.js');
const {llm}=await loadSettings();
if(llm.provider!=='cpa-local'||llm.model!=='gpt-6-luna'||new URL(llm.baseUrl).hostname!=='127.0.0.1'||!llm.apiKey)throw Error('Verified local CPA profile is unavailable');
const response=await fetch(`http://127.0.0.1:${port}/api/settings`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({llm})});
if(!response.ok)throw Error('Application rejected the profile: '+response.status);
const saved:any=await response.json();const active=saved.settings?.llm||saved.llm;
if(active?.provider!=='cpa-local'||active?.model!=='gpt-6-luna')throw Error('Model readback mismatch');
console.log(JSON.stringify({port,provider:active.provider,model:active.model,baseUrl:active.baseUrl,hasKey:active.hasKey}));
