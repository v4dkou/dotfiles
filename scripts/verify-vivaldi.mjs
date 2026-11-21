import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';

const [port, repo, output] = process.argv.slice(2);
assert(port && repo && output, 'Run scripts/verify-vivaldi.sh to create an isolated test browser.');
const base = `http://127.0.0.1:${Number(port)}`;
let target;
for (let i=0; i<100; i++) {
  const targets = await (await fetch(`${base}/json/list`)).json();
  target = targets.find(t => t.url.endsWith('/window.html'));
  if (target) break;
  await delay(100);
}
assert(target, 'Vivaldi UI debugging target not found (--debug-packed-apps is required).');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject) => {
  ws.addEventListener('open', resolve, {once:true});
  ws.addEventListener('error', reject, {once:true});
});
let nextId=0;
const pending=new Map();
ws.addEventListener('message', e => {
  const m=JSON.parse(e.data);
  const p=pending.get(m.id);
  if (p) {
    pending.delete(m.id);
    clearTimeout(p.timer);
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
});
const call=(method, params={}) => new Promise((resolve,reject) => {
  const id=++nextId;
  const timer=setTimeout(() => {pending.delete(id);reject(new Error(`${method} timed out`));}, 20000);
  pending.set(id,{resolve,reject,timer});
  ws.send(JSON.stringify({id,method,params}));
});
const evaluate=async expression => {
  const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const custom=await fs.readFile(path.join(repo,'vivaldi/custom.css'),'utf8');
const fixed=await fs.readFile(path.join(repo,'vivaldi/single-tab.css'),'utf8');
const original='#browser.tabs-top:has(#tabs-container .tab):not(:has(#tabs-container .tab:not(.active))) #header {display:none !important;}';
const report={browser:await (await fetch(`${base}/json/version`)).json(),scenarios:[]};
await fs.mkdir(output,{recursive:true});

async function apply(css) {
  await evaluate(`(() => {
    document.querySelectorAll('link[href*="css-mods"]').forEach(l => l.disabled=true);
    document.querySelector('#single-tab-test')?.remove();
    let style=document.querySelector('#dotfiles-verification');
    if(!style) {style=document.createElement('style');style.id='dotfiles-verification';document.head.append(style);}
    style.textContent=${JSON.stringify(custom+'\n'+css)};
  })()`);
  await delay(500);
}

async function sample(name, expected) {
  const sampling=evaluate(`new Promise(resolve => {
    const frames=[], start=performance.now();
    function frame() {
      const h=document.querySelector('#header'), css=getComputedStyle(h), rect=h.getBoundingClientRect();
      frames.push({ms:Math.round(performance.now()-start),display:css.display,visibility:css.visibility,position:css.position,
        y:rect.y,width:rect.width,height:rect.height,tabs:document.querySelectorAll('#tabs-container .tab').length});
      if(performance.now()-start<3000) requestAnimationFrame(frame); else resolve(frames);
    }
    requestAnimationFrame(frame);
  })`).then(frames=>({frames}),error=>({error}));
  // These are screenshots of the browser chrome, not screenshots of a web page.
  for(let i=0;i<6;i++) {
    await delay(350);
    const screenshot=await call('Page.captureScreenshot',{format:'png'});
    await fs.writeFile(path.join(output,`${name}-${i}.png`),Buffer.from(screenshot.data,'base64'));
  }
  const sampled=await sampling;
  if(sampled.error) throw sampled.error;
  const frames=sampled.frames;
  assert(frames.length>=30, `${name}: too few frames to assess flicker`);
  const state=f=>JSON.stringify([f.display,f.visibility,f.position,f.y,f.height,f.tabs]);
  const changes=frames.slice(1).filter((f,i)=>state(f)!==state(frames[i])).length;
  const result={name,frames:frames.length,changes,states:[...new Set(frames.map(state))]};
  report.scenarios.push(result);
  await fs.writeFile(path.join(output,`${name}.json`),JSON.stringify(frames,null,2)+'\n');
  console.log(`${name}: ${frames.length} frames, ${changes} state changes`);
  if(expected) {
    assert.equal(changes,0,`${name}: header flickers or changes size`);
    assert(frames.every(f=>f.tabs===expected.tabs),`${name}: rendered tabs disappear`);
    if(expected.hidden) {
      assert(frames.every(f=>f.visibility==='hidden' && f.position==='absolute' && f.width>0),`${name}: header must be hidden and measurable`);
    } else {
      assert(frames.every(f=>f.visibility==='visible' && f.display!=='none' && f.y>=0),`${name}: header must be visible`);
    }
  }
}

try {
  for(let i=0;i<100;i++) {
    if(await evaluate('Boolean(document.querySelector("#browser") && document.querySelector("#header"))')) break;
    await delay(100);
  }
  // Only the throwaway profile created by verify-vivaldi.sh is controlled here.
  await evaluate(`new Promise(resolve=>chrome.tabs.query({currentWindow:true},async tabs=>{
    if(tabs.length>1) await new Promise(r=>chrome.tabs.remove(tabs.slice(1).map(t=>t.id),r));
    chrome.tabs.update(tabs[0].id,{url:'about:blank'},()=>resolve(true));
  }))`);
  await delay(1000);
  await sample('installed-one-tab',{tabs:1,hidden:true});
  await apply(original);
  await sample('before-one-tab');
  await apply(fixed);
  await sample('after-one-tab',{tabs:1,hidden:true});
  const second=await evaluate(`new Promise(resolve=>chrome.tabs.create({url:'about:blank'},tab=>resolve(tab.id)))`);
  await delay(750);
  await sample('after-two-tabs',{tabs:2,hidden:false});
  await evaluate(`new Promise(resolve=>chrome.tabs.remove(${second},()=>resolve(true)))`);
  await delay(750);
  await sample('after-return-to-one',{tabs:1,hidden:true});
  // Repeat the transition to catch stale tab virtualization after closing tabs.
  for(let i=0;i<3;i++) {
    const id=await evaluate(`new Promise(resolve=>chrome.tabs.create({url:'about:blank'},tab=>resolve(tab.id)))`);
    await delay(250);
    await evaluate(`new Promise(resolve=>chrome.tabs.remove(${id},()=>resolve(true)))`);
    await delay(250);
  }
  await sample('after-three-cycles',{tabs:1,hidden:true});
  report.passed=true;
  console.log('PASS: single-tab header stays hidden; two-tab header returns.');
} finally {
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
  await call('Browser.close').catch(()=>{});
  for(const p of pending.values()) clearTimeout(p.timer);
  ws.close();
}
