// Small CDP client for the isolated browser created by record-demo.py.
const [port, kind, expression] = process.argv.slice(2);
const targets=await(await fetch(`http://127.0.0.1:${Number(port)}/json/list`)).json();
const selected=kind==='ui' ? targets.filter(t=>t.url.endsWith('/window.html')) : targets.filter(t=>t.type==='page' && t.url.includes('/docs/demo/index.html'));
if(!selected.length) throw new Error(`No ${kind} demo target`);
const values=[];
for(const target of selected) {
  const ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})});
  try {
    const result=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Demo evaluation timed out')),10000);
      ws.addEventListener('message',e=>{
        const m=JSON.parse(e.data);
        if(m.id!==1)return;
        clearTimeout(timer);
        if(m.error||m.result?.exceptionDetails)reject(new Error(JSON.stringify(m)));
        else resolve(m.result.result.value);
      });
      ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression,returnByValue:true,awaitPromise:true}}));
    });
    values.push(result);
  } finally {ws.close()}
}
console.log(JSON.stringify(kind==='ui'?values[0]:values));
