const {test}=require('node:test');const assert=require('node:assert/strict');
const {ResultStore}=require('../apps/viewer/result-store.js');
global.location={href:'http://localhost/demo.html'};
global.crypto=require('node:crypto').webcrypto;
const digest=s=>require('node:crypto').createHash('sha256').update(s).digest('hex');
const block=i=>({schema_version:'labprism-frame-chunk/1',frames:[{timestamp_ms:i*1000}]});
const index={schema_version:'labprism-result-index/1',result_schema_version:'labprism-video-result/4',frame_count:8,chunks:Array.from({length:8},(_,i)=>({file:`frames-${i}.json`,start_ms:i*1000,end_ms:i*1000,count:1,times_ms:[i*1000],bytes:Buffer.byteLength(JSON.stringify(block(i))),sha256:digest(JSON.stringify(block(i)))}))};
function response(x){return {ok:true,arrayBuffer:async()=>new TextEncoder().encode(JSON.stringify(x)).buffer};}
test('long results load one block on demand with a three-block LRU',async()=>{
 let calls=[];const store=new ResultStore('/index.json',async url=>{calls.push(url);return response(url==='/index.json'?index:{schema_version:'labprism-frame-chunk/1',frames:[{timestamp_ms:Number(url.match(/frames-(\d+)/)[1])*1000}]});});
 await store.open();assert.equal(calls.length,1);
 for(let i=0;i<8;i++)await store.framesAt(i*1000);
 assert.equal(store.cache.size,3);assert.equal(calls.length,9);
 await store.framesAt(7000);assert.equal(calls.length,9);assert.equal(store.nextTime(7000,-1),6000);
 store.dispose();assert.equal(store.cache.size,0);
});
test('late results after cancellation cannot refill an old cache',async()=>{
 let resolve;const store=new ResultStore('/index.json',url=>url==='/index.json'?Promise.resolve(response(index)):new Promise(r=>{resolve=r;}));
 await store.open();const pending=store.framesAt(0);store.dispose();resolve(response(block(0)));
 await assert.rejects(pending,/Cancelled/);assert.equal(store.cache.size,0);
});
test('malformed index paths and oversized legacy results fail closed',async()=>{
 const invalid={...index,chunks:[{file:'../private.json',count:1,start_ms:0,end_ms:1}]};
 await assert.rejects(new ResultStore('/index',async()=>response(invalid)).open(),/索引/);
 await assert.rejects(new ResultStore('/legacy',async()=>response({schema_version:'labprism-video-result/1',frames:Array(501).fill({})})).open(),/时间块/);
});

test('altered payload with valid JSON is rejected by content hash',async()=>{
 const store=new ResultStore('/index.json',async url=>response(url==='/index.json'?index:{...block(0),frames:[{timestamp_ms:1}]}));
 await store.open();await assert.rejects(store.framesAt(0),/摘要/);assert.equal(store.cache.size,0);
});
test('rapid seeks abort superseded blocks and cannot restore stale data',async()=>{
 const pending=[];const store=new ResultStore('/index.json',(url,options)=>url==='/index.json'?Promise.resolve(response(index)):new Promise(resolve=>pending.push({url,options,resolve})));
 await store.open();const a=store.framesAt(0),b=store.framesAt(1000),c=store.framesAt(2000);
 const rejected=Promise.allSettled([a,b,c]);
 assert.equal(pending[0].options.signal.aborted,true);assert.equal(store.pending.size,1);
 pending.forEach((p,i)=>p.resolve(response(block(i))));
 const results=await rejected;assert.deepEqual(results.map(x=>x.status),['rejected','rejected','fulfilled']);
 assert.deepEqual([...store.cache.keys()],[2]);
});

test('contradictory time bounds, counts, versions and oversized cache are rejected',async()=>{
 for(const mutate of [r=>r.frame_count++,r=>r.chunks[0].end_ms=500,
     r=>r.result_schema_version='labprism-video-result/99',r=>r.chunks[1].file=r.chunks[0].file]) {
   const invalid=structuredClone(index);mutate(invalid);
   await assert.rejects(new ResultStore('/index',async()=>response(invalid)).open(),/索引/);
 }
 assert.throws(()=>new ResultStore('/index',null,4),/缓存/);
});
