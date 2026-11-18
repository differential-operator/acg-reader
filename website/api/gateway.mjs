import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import worker from '../dist/server/index.js';
export default async function handler(req,res){
 const origin='https://'+(req.headers.host||'localhost');
 const input=new URL(req.url,origin);const operation=input.searchParams.get('operation');
 if(!['page','media','hls'].includes(operation)){res.statusCode=404;res.end('Not found');return}
 input.pathname='/api/'+operation;input.searchParams.delete('operation');
 const cancellation=new AbortController();res.on('close',()=>{if(!res.writableFinished)cancellation.abort()});
 try{const response=await worker.fetch(new Request(input,{method:req.method,signal:cancellation.signal}));res.statusCode=response.status;for(const [key,value]of response.headers)res.setHeader(key,value);if(response.body)await pipeline(Readable.fromWeb(response.body),res);else res.end()}
 catch(error){if(!res.headersSent){res.statusCode=502;res.setHeader('Content-Type','application/json; charset=utf-8');res.end(JSON.stringify({error:'请求失败，请稍后重试'}))}else res.destroy(error)}
}
