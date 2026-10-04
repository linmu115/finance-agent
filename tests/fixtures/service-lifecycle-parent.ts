import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {acquireStartupGuard} from '../../server/startup-guard.js';

const data=process.env.FIXTURE_DATA!;
const guard=await acquireStartupGuard({dataDir:data,host:'127.0.0.1',port:0});
const transport=new StdioClientTransport({command:process.env.FIXTURE_PYTHON!,args:['tests/fixtures/service-lifecycle-child.py'],cwd:process.cwd(),env:{...process.env,FINANCE_DATA_DIR:data,PYTHONPATH:process.cwd(),PYTHONIOENCODING:'utf-8'},stderr:'pipe'});
transport.stderr?.on('data',()=>{});
const client=new Client({name:'lifecycle-private-parent',version:'1'});
await client.connect(transport);
const request=client.callTool({name:'fixture_slow_writer',arguments:{default_executor:process.env.FIXTURE_DEFAULT==='1'}});
if(process.env.FIXTURE_DEFAULT==='1')void request.catch(()=>{});else await request;
process.send?.({status:'started',child_pid:transport.pid,port:guard.port});
process.on('message',message=>{if(message==='end-stdin') (transport as any)._process.stdin.end();});
// The test kills this parent without running client.close or guard.close.
