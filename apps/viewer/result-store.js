"use strict";
// One bounded cache per viewer. Loading/seek never invokes a model.
class ResultStore {
  constructor(url, fetcher=(...args)=>fetch(...args), maxChunks=3) {
    if(!Number.isInteger(maxChunks)||maxChunks<1||maxChunks>3)throw Error('结果缓存上限无效');
    this.url=url;this.fetcher=fetcher;this.maxChunks=maxChunks;
    this.cache=new Map();this.pending=new Map();this.controller=new AbortController();this.closed=false;
  }
  async json(url, expected=null) {
    const r=await this.fetcher(url,{signal:this.controller.signal});
    if(!r.ok)throw Error(`结果请求失败 (${r.status})`);
    const maximum=16*1024*1024;
    if(Number(r.headers?.get('content-length'))>maximum)throw Error('结果块过大');
    const bytes=new Uint8Array(await r.arrayBuffer());
    if(bytes.byteLength>maximum)throw Error('结果块过大');
    if(expected) {
      if(bytes.byteLength!==expected.bytes)throw Error('时间块长度不符');
      const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
      const hex=Array.from(digest,b=>b.toString(16).padStart(2,'0')).join('');
      if(hex!==expected.sha256)throw Error('时间块摘要不符');
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  async open() {
    const raw=await this.json(this.url);
    if(this.closed)throw Error('已取消');
    if(raw.schema_version==='labprism-result-index/1') {
      if(!/^labprism-video-result\/[1234]$/.test(raw.result_schema_version)
        ||!Array.isArray(raw.chunks)||!raw.chunks.length
        ||!Number.isInteger(raw.frame_count)||raw.frame_count!==raw.chunks.reduce((n,c)=>n+c.count,0)
        ||new Set(raw.chunks.map(c=>c.file)).size!==raw.chunks.length
        ||raw.chunks.some((c,i)=>!/^frames-\d+\.json$/.test(c.file)
        || !Number.isInteger(c.count)||c.count<1||c.count>100
        || !Number.isInteger(c.bytes)||c.bytes<1||c.bytes>16*1024*1024||!/^[a-f0-9]{64}$/.test(c.sha256)
        || !Number.isFinite(c.start_ms)||!Number.isFinite(c.end_ms)||c.start_ms<0||c.start_ms>c.end_ms
        || !Array.isArray(c.times_ms)||c.times_ms.length!==c.count
        || c.times_ms[0]!==c.start_ms||c.times_ms[c.count-1]!==c.end_ms
        || c.times_ms.some((t,j)=>!Number.isFinite(t)||t<c.start_ms||t>c.end_ms||(j&&t<=c.times_ms[j-1]))
        || (i&&c.start_ms<=raw.chunks[i-1].end_ms)))throw Error('时间块索引无效');
      this.index=raw;this.metadata={...raw,schema_version:raw.result_schema_version,frames:[]};
    } else {
      if(!/^labprism-video-result\/[1234]$/.test(raw.schema_version)||!raw.frames?.length||raw.frames.length>500)throw Error('旧结果需先转换为时间块');
      this.metadata=raw;
    }
    return this.metadata;
  }
  blockAt(ms) {
    if(!this.index)return -1;
    const chunks=this.index.chunks;let lo=0,hi=chunks.length;
    while(lo<hi){const mid=(lo+hi)>>1;if(chunks[mid].start_ms<=ms)lo=mid+1;else hi=mid;}
    return Math.max(0,lo-1);
  }
  async framesAt(ms) {
    if(!this.index)return this.metadata.frames;
    const i=this.blockAt(ms);
    if(this.cache.has(i)){const value=this.cache.get(i);this.cache.delete(i);this.cache.set(i,value);return value;}
    if(this.pending.has(i))return this.pending.get(i);
    // A fast drag cancels superseded work rather than growing an unbounded queue.
    if(this.pending.size>=2){this.controller.abort();this.controller=new AbortController();this.pending.clear();}
    const controller=this.controller;
    const job=(async()=>{
      const entry=this.index.chunks[i];
      const chunk=await this.json(new URL(entry.file,new URL(this.url,location.href)).href,entry);
      if(this.closed||controller.signal.aborted)throw new DOMException('Cancelled','AbortError');
      if(chunk.schema_version!=='labprism-frame-chunk/1'||!Array.isArray(chunk.frames)||chunk.frames.length!==entry.count
        ||chunk.frames.some((f,j)=>f.timestamp_ms!==entry.times_ms[j]))throw Error('时间块损坏');
      this.cache.set(i,chunk.frames);
      while(this.cache.size>this.maxChunks)this.cache.delete(this.cache.keys().next().value);
      return chunk.frames;
    })();
    this.pending.set(i,job);
    try{return await job;}finally{if(this.pending.get(i)===job)this.pending.delete(i);}
  }
  nextTime(ms,delta) {
    const times=this.index?this.index.chunks.flatMap(c=>c.times_ms):this.metadata.frames.map(f=>f.timestamp_ms);
    let i=0;while(i+1<times.length&&times[i+1]<=ms+.001)i++;
    return times[Math.max(0,Math.min(times.length-1,i+delta))];
  }
  dispose(){this.closed=true;this.controller.abort();this.cache.clear();this.pending.clear();}
}
if(typeof module!=='undefined')module.exports={ResultStore};
