
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import readline from 'node:readline';
const input = readline.createInterface({input:process.stdin, terminal:false});
const lines = input[Symbol.asyncIterator]();
const config = JSON.parse((await lines.next()).value);
const root = config.inspector;
const load = p => import(pathToFileURL(p).href);
const sdkRoot = path.join(root, '..', 'sdk');
const info = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const sdkInfo = JSON.parse(fs.readFileSync(path.join(sdkRoot, 'package.json'), 'utf8'));
const {Client} = await load(path.join(sdkRoot, 'dist/esm/client/index.js'));
const {connect,disconnect,listTools,callTool} = await load(path.join(root,'cli/build/client/index.js'));
const {createTransport} = await load(path.join(root,'cli/build/transport.js'));
let client, transport, session;
const emit = value => process.stdout.write(JSON.stringify(value)+'\n');
async function open() {
  client = new Client({name:info.name,version:info.version});
  transport = createTransport({transportType:'http',url:config.url,
    headers:{Authorization:'Bearer '+config.token}});
  await connect(client,transport);
}
function publicData(name, data) {
  if(name === 'session_open') session = data;
  if(name === 'inbox_pull') return {messages:data.messages.map(m => ({
    message_id:m.message_id,from_agent_id:m.from_agent_id,parent_message_id:m.parent_message_id,
    workspace_id:m.workspace_id,body:m.body}))};
  const keys=['session_id','agent_id','workspace_id','status','message_id','recipients',
    'delivered_count','acknowledged','read_message_ids'];
  return Object.fromEntries(keys.filter(k=>k in data).map(k=>[k,data[k]]));
}
function argsFor(name, args) {
  if(['inbox_pull','inbox_ack'].includes(name))
    return {...args,session_id:session.session_id,session_secret:session.session_secret};
  if(name === 'message_create')
    return {...args,from_session_id:session.session_id,session_secret:session.session_secret};
  if(['session_heartbeat','session_close'].includes(name))
    return {...args,session_id:session.session_id};
  return args;
}
try {
  if(config.probe) {
    emit({client:info.name,version:info.version,sdk:sdkInfo.version,
      api:[connect,disconnect,listTools,callTool,createTransport].every(x=>typeof x==='function')});
  } else {
    await open();
    emit({client:info.name,version:info.version,sdk:sdkInfo.version});
    for await (const line of lines) {
      const cmd=JSON.parse(line);
      try {
        if(cmd.method === 'stop') {await disconnect(transport);emit({ok:true});break;}
        if(cmd.method === 'reconnect') {await disconnect(transport);await open();emit({ok:true});continue;}
        if(cmd.method === 'list') {emit({ok:true,tools:(await listTools(client)).tools.map(t=>t.name)});continue;}
        const result=await callTool(client,cmd.name,argsFor(cmd.name,cmd.args||{}));
        const envelope=result.structuredContent || JSON.parse(result.content.find(c=>c.type==='text').text);
        if(result.isError || !envelope.ok) {emit({ok:false,code:envelope.error?.code||'TOOL_FAILED'});continue;}
        emit({ok:true,data:publicData(cmd.name,envelope.data)});
      } catch (error) {emit({ok:false,code:'CLIENT_CALL_FAILED',type:error.constructor.name});}
    }
  }
} catch(error) {emit({ok:false,code:'CLIENT_START_FAILED',type:error.constructor.name});process.exitCode=1;}
finally {input.close(); if(transport) {try {await disconnect(transport);} catch {process.exitCode=1;}}}
