"use strict";
const $ = id => document.getElementById(id);
const video = $("video"), svg = $("overlay"), ns = "http://www.w3.org/2000/svg";
const edges = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const colors = ["#d6f675","#63ddfa","#ffbb74","#e999ff","#68efba","#ff8db1"];
let data = null, lastIndex = -1, generation = 0, ready = false, frameTime = null;
const roleLabel = role => role === "first_person" ? "第一人称" : "第三人称";
function element(tag, attrs, parent = svg) { const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));parent.appendChild(e);return e; }
function indexAt(t) { let lo=0,hi=data.frames.length;while(lo<hi){const mid=(lo+hi)>>1;if(data.frames[mid].timestamp_ms<=t+0.5)lo=mid+1;else hi=mid;}return lo-1; }
function message(value) { $("load-status").textContent=value; }
function detail(index) {
  const obj=data?.frames[lastIndex]?.objects[Number(index)];
  $("instance-detail").textContent=index!==""&&obj ? `${obj.display_name || obj.label} · 置信度 ${(obj.confidence*100).toFixed(1)}% · 框 [${obj.box.join(", ")}] px · ${obj.mask_contours.length} 个轮廓 · 帧内实例，未分配轨迹身份` : "选择实例查看类别、置信度与坐标。";
}
function render(force=false) {
  if(!data||!ready)return;
  const t=(frameTime??video.currentTime)*1000, index=indexAt(t), frame=data.frames[index];
  $("time").textContent=`${(t/1000).toFixed(2)} / ${(data.video.duration_ms/1000).toFixed(2)} s`;
  $("seek").value=String(video.currentTime);
  const age=frame?t-frame.timestamp_ms:Infinity;
  const valid=frame&&age>=-0.5&&age<=150;
  $("sample-age").textContent=valid?`预测帧差 ${Math.max(0,age).toFixed(0)} ms · ${data.video.sample_hz} Hz 抽样`:"当前时刻无有效预测";
  if(!force&&index===lastIndex&&String(Boolean(valid))===svg.dataset.valid)return;
  svg.dataset.valid=String(Boolean(valid));
  if(index!==lastIndex){
    lastIndex=index;$("object-select").replaceChildren(new Option("全部实例",""));
    if(frame)frame.objects.forEach((o,i)=>$("object-select").add(new Option(`${i+1}. ${o.display_name || o.label} ${(o.confidence*100).toFixed(0)}%`,String(i))));
    detail("");
  }
  svg.replaceChildren();
  $("stage-label").textContent=$("original").checked?"原始画面":"模型叠加 · 候选结果";
  $("frame-stamp").textContent=frame?`${roleLabel(data.source.camera_role)} / 源视频 ${(frame.source_timestamp_ms/1000).toFixed(2)} s`:"尚无分析帧";
  $("counts").textContent=valid?`${frame.objects.length} 个检测 · ${frame.hands.length} 只手${frame.hands.length?"":"（未检出）"}`:"当前帧未分析";
  if(!valid||$("original").checked)return;
  const selected=$("object-select").value;
  frame.objects.forEach((o,i)=>{
    if(selected!==""&&Number(selected)!==i)return;
    const color=colors[o.class_id%colors.length], group=element("g",{class:"object"});
    group.addEventListener("click",()=>{$("object-select").value=String(i);detail(String(i));render(true);});
    if($("masks").checked&&o.mask_contours.length){const d=o.mask_contours.map(c=>"M"+c.map(p=>p.join(",")).join("L")+"Z").join(" ");element("path",{d,fill:color,"fill-opacity":.16,stroke:color,"stroke-width":1.2,"fill-rule":"evenodd"},group);}
    if($("boxes").checked){const [x,y,x2,y2]=o.box;element("rect",{x,y,width:x2-x,height:y2-y,fill:"transparent",stroke:color,"stroke-width":1.7},group);if(selected!==""||o.confidence>=.6){const text=element("text",{x:Math.max(0,x),y:Math.max(16,y-5),fill:color,"font-size":13,"font-family":"sans-serif",stroke:"#081c16","stroke-width":2.5,"paint-order":"stroke"},group);text.textContent=`${o.display_name || o.label} ${(o.confidence*100).toFixed(0)}%`;}}
  });
  if($("hands").checked)frame.hands.forEach(h=>{const color="#fff17e";edges.forEach(([a,b])=>element("line",{x1:h.points[a][0],y1:h.points[a][1],x2:h.points[b][0],y2:h.points[b][1],stroke:color,"stroke-width":2.5}));h.points.forEach(p=>element("circle",{cx:p[0],cy:p[1],r:3,fill:color,stroke:"#16362d","stroke-width":1}));});
}
function go(seconds){video.pause();frameTime=null;video.currentTime=Math.min(Math.max(0,seconds),video.duration||data.video.duration_ms/1000);}
async function loadClip(item){
  const ticket=++generation;ready=false;data=null;lastIndex=-1;frameTime=null;video.pause();video.removeAttribute("src");video.load();svg.replaceChildren();
  for(const id of ["play","previous","next","seek"])$(id).disabled=true;
  message("正在核对片段与模型记录…");
  try{
    const response=await fetch(item.result);if(!response.ok)throw Error(`结果请求失败 (${response.status})`);
    const result=await response.json();if(ticket!==generation)return;
    if(result.schema_version!=="labprism-video-result/1"||!result.frames.length)throw Error("结果契约不支持或没有分析帧");
    data=result;video.src=item.video;svg.setAttribute("viewBox",`0 0 ${data.video.width} ${data.video.height}`);
    $("clip-title").textContent=item.title;$("clip-meta").textContent=`${roleLabel(data.source.camera_role)} · ${(data.video.duration_ms/1000).toFixed(0)} 秒 · ${data.video.width} × ${data.video.height}`;
    $("evidence").replaceChildren();
    const entries=[["素材",`${data.source.source_id} · ${data.source.split} 组`],["源 SHA256",data.source.source_sha256],["检测模型",data.models[0].id],["实例分割","SAM 2.1 Tiny · 检测框提示"],["手姿","MediaPipe 21 点 · CPU/XNNPACK"],["运行",`${data.environment.gpu} · 离线 ${data.metrics.sampled_pipeline_fps} 分析帧/s`],["效果指标","准确率 / 泛化 / 时序质量：尚未测得"]];
    entries.forEach(([name,value])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=name;dd.textContent=value;$("evidence").append(dt,dd);});
    $("result-link").href=item.result;$("result-link").hidden=false;
    $("checkpoints").replaceChildren();[0,2,4,6].filter(t=>t<data.video.duration_ms/1000).forEach(t=>{const b=document.createElement("button");b.textContent=`${t.toFixed(2)} s ↗`;b.addEventListener("click",()=>go(t));$("checkpoints").appendChild(b);});
    message("真实离线推理已载入。8 秒开发片段，含误检与漏检，尚未完成独立质量验收。");
  }catch(error){if(ticket===generation)message(`暂时无法载入：${error.message}。请检查本机素材与推理包。`);}
}
video.addEventListener("loadeddata",()=>{if(!data)return;ready=true;$("seek").max=String(video.duration);for(const id of ["play","previous","next","seek"])$(id).disabled=false;render(true);});
video.addEventListener("error",()=>{if(data){ready=false;message("视频读取失败，请检查素材文件是否完整。");}});
video.addEventListener("play",()=>{$("play").textContent="暂停";});video.addEventListener("pause",()=>{$("play").textContent="播放";});
video.addEventListener("seeking",()=>{frameTime=null;svg.replaceChildren();});video.addEventListener("seeked",()=>{frameTime=video.currentTime;render(true);});
if(video.requestVideoFrameCallback){const tick=(_,meta)=>{frameTime=meta.mediaTime;render();video.requestVideoFrameCallback(tick);};video.requestVideoFrameCallback(tick);}else video.addEventListener("timeupdate",()=>{frameTime=video.currentTime;render();});
$("play").addEventListener("click",()=>{if(video.paused)video.play().catch(e=>message(`播放失败：${e.message}`));else video.pause();});
$("seek").addEventListener("input",()=>go(Number($("seek").value)));
$("speed").addEventListener("change",()=>{video.playbackRate=Number($("speed").value);});
for(const [id,delta] of [["previous",-1],["next",1]])$(id).addEventListener("click",()=>{if(!data)return;const i=Math.max(0,Math.min(data.frames.length-1,indexAt(video.currentTime*1000)+delta));go(data.frames[i].timestamp_ms/1000);});
for(const id of ["boxes","masks","hands","original"])$(id).addEventListener("change",()=>render(true));
$("object-select").addEventListener("change",()=>{detail($("object-select").value);render(true);});
(async()=>{try{const r=await fetch("demo-data/catalog.json");if(!r.ok)throw Error("尚未准备真实推理包");const catalog=await r.json();if(!catalog.clips?.length)throw Error("片段目录为空");$("clip-select").replaceChildren();catalog.clips.forEach((c,i)=>$("clip-select").add(new Option(c.title,String(i))));$("clip-select").disabled=false;$("clip-select").addEventListener("change",()=>loadClip(catalog.clips[Number($("clip-select").value)]));await loadClip(catalog.clips[0]);}catch(e){message(`${e.message}。请先运行本地推理并准备预览素材。`);}})();
