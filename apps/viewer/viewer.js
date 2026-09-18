"use strict";
const $ = id => document.getElementById(id);
const video = $("video"), svg = $("overlay"), ns = "http://www.w3.org/2000/svg";
const edges = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const colors = ["#d6f675","#63ddfa","#ffbb74","#e999ff","#68efba","#ff8db1"];
let textObservations = [];
let data = null, lastIndex = -1, generation = 0, ready = false, frameTime = null;
const roleLabel = role => role === "first_person" ? "第一人称" : "第三人称";
function element(tag, attrs, parent = svg) { const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));parent.appendChild(e);return e; }
function indexAt(t) { let lo=0,hi=data.frames.length;while(lo<hi){const mid=(lo+hi)>>1;if(data.frames[mid].timestamp_ms<=t+0.001)lo=mid+1;else hi=mid;}return lo-1; }
function message(value) { $("load-status").textContent=value; }
function detail(index) {
  const obj=data?.frames[lastIndex]?.objects[Number(index)];
  $("instance-detail").textContent=index!==""&&obj ? `${obj.display_name || obj.label} · 置信度 ${(obj.confidence*100).toFixed(1)}% · 框 [${obj.box.join(", ")}] px · ${obj.mask_contours.length} 个轮廓 · ${obj.track_id ? `预测轨迹 ${obj.track_id} / ${obj.track_state}` : "帧内实例"}${obj.model_conflict ? " · 类别冲突待复核" : ""}` : "选择实例查看类别、置信度与坐标。";
}
function drawTrail(item, color) {
  if(!$("trails").checked || !item.trail?.length)return;
  const d=item.trail.map((p,i)=>`${i===0 || p[0]-item.trail[i-1][0]>150 ? "M" : "L"}${p[1]},${p[2]}`).join(" ");
  element("path",{class:"trail",d,fill:"none",stroke:color,"stroke-width":2,"stroke-opacity":.8});
}
function render(force=false) {
  if(!data||!ready)return;
  const t=(frameTime??video.currentTime)*1000, index=indexAt(t), frame=data.frames[index];
  $("time").textContent=`${(t/1000).toFixed(2)} / ${(data.video.duration_ms/1000).toFixed(2)} s`;
  $("seek").value=String(video.currentTime);
  const age=frame?t-frame.timestamp_ms:Infinity;
  // Allow the normal interval of the sampled stream while keeping a missing
  // sample visibly invalid instead of carrying an older prediction forward.
  const sampleWindow=Math.max(150,1000/data.video.sample_hz+75);
  const valid=frame&&age>=-Math.min(100,sampleWindow/2)&&age<=sampleWindow;
  svg.dataset.presentationMs=String(t);
  svg.dataset.frameIndex=valid?String(frame.frame_index):"";
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
  const regions=frame?.semantic_regions || [];
  $("semantic-note").textContent=$("semantic").checked ? `研究候选，实验台误分明显。当前类别：${regions.map(r=>r.label).join("、")}。颜色按类别编号分配；轮廓简化，原始像素图保留在运行包。` : "";
  $("conflicts").textContent=valid ? ((frame.conflicting_objects || frame.rejected_objects || []).map(o=>`${o.display_name || o.label}：与笔记本模型冲突，${frame.conflicting_objects ? "保留原检测" : "旧候选曾过滤"}，待复核`).join("；") || "本帧无已记录的类别冲突。") : "";
  $("text-observation").textContent=valid ? (frame.availability.ocr==="not_sampled" ? "本帧未采样文字；文字列表可跳到实际识别帧。" : (frame.texts || []).map(x=>`${x.text}（${(x.score*100).toFixed(0)}%）`).join("；") || "本帧无文字输出。") : "当前时刻无文字观察。";
  if(!valid||$("original").checked)return;
  if($("ocr").checked)(frame.texts || []).forEach(item=>{
    element("polygon",{class:"ocr-region",points:item.quad.map(p=>p.join(",")).join(" "),fill:"none",stroke:"#ffffff","stroke-width":2});
    const text=element("text",{class:"ocr-text",x:item.quad[0][0],y:Math.max(16,item.quad[0][1]-4),fill:"#fff","font-size":14,stroke:"#081c16","stroke-width":3,"paint-order":"stroke"});text.textContent=item.text;
  });
  if($("semantic").checked)regions.forEach(r=>{
    const d=r.mask_contours.map(c=>"M"+c.map(p=>p.join(",")).join("L")+"Z").join(" ");
    element("path",{class:"semantic",d,fill:`hsl(${r.class_id*137.508%360} 70% 60%)`,"fill-opacity":.3,"fill-rule":"evenodd"});
  });
  if($("temporal").checked)(frame.temporal_instances || []).forEach(item=>{
    const d=(item.mask_contours || []).map(c=>"M"+c.map(p=>p.join(",")).join("L")+"Z").join(" ");
    if(!d)return;
    element("path",{class:"temporal-mask",d,fill:"#ffcf5c","fill-opacity":.18,stroke:"#ffcf5c","stroke-width":1.5,"stroke-dasharray":"5 3","fill-rule":"evenodd"});
  });
  const selected=$("object-select").value;
  frame.objects.forEach((o,i)=>{
    if(selected!==""&&Number(selected)!==i)return;
    const color=colors[o.class_id%colors.length];drawTrail(o,color);const group=element("g",{class:"object"});
    group.addEventListener("click",()=>{$("object-select").value=String(i);detail(String(i));render(true);});
    if($("masks").checked&&o.mask_contours.length){const d=o.mask_contours.map(c=>"M"+c.map(p=>p.join(",")).join("L")+"Z").join(" ");element("path",{d,fill:color,"fill-opacity":.16,stroke:color,"stroke-width":1.2,"fill-rule":"evenodd"},group);}
    if($("boxes").checked){const [x,y,x2,y2]=o.box;element("rect",{x,y,width:x2-x,height:y2-y,fill:"transparent",stroke:color,"stroke-width":1.7},group);if(selected!==""||$("labels").checked){const text=element("text",{x:Math.max(0,x),y:Math.max(16,y-5),fill:color,"font-size":13,"font-family":"sans-serif",stroke:"#081c16","stroke-width":2.5,"paint-order":"stroke"},group);text.textContent=`${o.display_name || o.label} ${(o.confidence*100).toFixed(0)}%`;}}
  });
  if($("hands").checked)frame.hands.forEach(h=>{
    const color="#fff17e", visible=i=>!h.point_scores || h.point_scores[i]>=(h.keypoint_threshold ?? .3);
    drawTrail(h,color);
    edges.filter(([a,b])=>visible(a)&&visible(b)).forEach(([a,b])=>element("line",{x1:h.points[a][0],y1:h.points[a][1],x2:h.points[b][0],y2:h.points[b][1],stroke:color,"stroke-width":2.5}));
    h.points.forEach((p,i)=>{if(visible(i))element("circle",{cx:p[0],cy:p[1],r:3,fill:color,stroke:"#16362d","stroke-width":1});});
  });
}
function renderTextList(){
  const query=$("text-search").value.toLocaleLowerCase();
  const found=textObservations.filter(x=>x.text.toLocaleLowerCase().includes(query));
  $("text-list").replaceChildren();
  found.slice(0,100).forEach(item=>{const b=document.createElement("button");b.type="button";b.textContent=`${(item.timestamp_ms/1000).toFixed(2)} s · ${item.text} · ${(item.score*100).toFixed(0)}%`;
    b.addEventListener("click",()=>{$("ocr").checked=true;go(item.timestamp_ms/1000+.000001);});$("text-list").appendChild(b);});
  $("ocr-status").textContent=textObservations.length ? `共 ${textObservations.length} 条未复核文字候选，当前匹配 ${found.length} 条，显示前 100 条。分数不是读数准确率。` : "本段尚无文字候选。";
}
function renderEvents(){
  $("event-list").replaceChildren();
  const events=data.events || [];
  $("event-status").textContent=events.length ? `${events.length} 个二维接近区间；不证明物理接触或实验步骤。` : "本段尚无满足持续时间要求的接近事件。";
  events.forEach(event=>{const b=document.createElement("button");b.type="button";b.textContent=`${(event.start_ms/1000).toFixed(2)}–${(event.end_ms/1000).toFixed(2)} s · ${event.label}`;
    b.addEventListener("click",()=>go(event.start_ms/1000+.000001));$("event-list").appendChild(b);});
}
function go(seconds){video.pause();frameTime=null;video.currentTime=Math.min(Math.max(0,seconds),video.duration||data.video.duration_ms/1000);}
async function loadClip(item){
  const ticket=++generation;ready=false;data=null;lastIndex=-1;frameTime=null;video.pause();video.removeAttribute("src");video.load();svg.replaceChildren();
  for(const id of ["play","previous","next","seek"])$(id).disabled=true;
  svg.dataset.valid="false";svg.dataset.frameIndex="";
  for(const id of ["trails","semantic","temporal","ocr"]){$(id).checked=false;$(id).disabled=true;}
  $("semantic-note").textContent="";$("conflicts").textContent="";$("text-observation").textContent="";textObservations=[];$("text-search").value="";$("text-list").replaceChildren();$("event-list").replaceChildren();$("event-status").textContent="";$("ocr-status").textContent="";
  $("object-select").replaceChildren(new Option("全部实例",""));detail("");
  $("evidence").replaceChildren();$("checkpoints").replaceChildren();$("result-link").hidden=true;$("result-link").removeAttribute("href");
  $("counts").textContent="等待模型结果";$("sample-age").textContent="";$("time").textContent="0.00 / 0.00 s";$("seek").value="0";
  $("clip-title").textContent=item.title;$("clip-meta").textContent="";$("frame-stamp").textContent="等待视频";
  message("正在核对片段与模型记录…");
  try{
    const response=await fetch(item.result);if(!response.ok)throw Error(`结果请求失败 (${response.status})`);
    const result=await response.json();if(ticket!==generation)return;
    if(!["labprism-video-result/1","labprism-video-result/2","labprism-video-result/3"].includes(result.schema_version)||!result.frames.length)throw Error("结果契约不支持或没有分析帧");
    data=result;video.src=item.video;svg.setAttribute("viewBox",`0 0 ${data.video.width} ${data.video.height}`);
    $("clip-title").textContent=item.title;$("clip-meta").textContent=`${roleLabel(data.source.camera_role)} · ${(data.video.duration_ms/1000).toFixed(0)} 秒 · ${data.video.width} × ${data.video.height}`;
    $("evidence").replaceChildren();
    const candidate=data.schema_version!=="labprism-video-result/1";
    $("ocr").disabled=!data.frames.some(f=>f.texts?.length);
    $("temporal").disabled=!data.frames.some(f=>f.temporal_instances?.length);
    textObservations=data.frames.flatMap(f=>(f.texts || []).map(item=>({...item,timestamp_ms:f.timestamp_ms})));renderTextList();renderEvents();
    $("trails").disabled=!candidate;$("semantic").disabled=!data.frames.some(f=>f.semantic_regions?.length);
    const handModel=data.models.find(m=>m.task===(candidate?"hand_landmarks_candidate":"hand_landmarks"));
    const entries=[["素材",`${data.source.source_id} · ${data.source.split} 组`],["源 SHA256",data.source.source_sha256],["检测模型",data.models[0].id],["实例分割","SAM 2.1 Tiny · 检测框提示"],["手姿",`${handModel?.id || "未知"} · ${candidate?"2D / 深度与左右手未知，隐藏低分点":"相对深度，非全局 3D"}`],["运行",`${data.environment.gpu} · ${candidate?`复用基线检测/分割；新增阶段 ${data.metrics.candidate_processing_fps} 分析帧/s，非整链路速度`:`离线 ${data.metrics.sampled_pipeline_fps} 分析帧/s`}`],["手姿覆盖",`${data.metrics.frames_with_hands}/${data.frames.length} 帧有输出；不等于关节准确率`],["效果指标","独立准确率 / 泛化 / 时序质量：尚未测得"]];
    if(candidate)entries.push(["候选状态",data.schema_version==="labprism-video-result/3" ? "相机补偿与外观关联待验证；OCR、接近事件和时序掩码均为未复核候选。" : "轨迹身份待验证；语义域外误分明显；类别冲突保留。未晋级质量验收。"]);
    if(data.temporal_windows?.length)entries.push(["时序掩码",`${data.temporal_windows.length} 个窗口；窗口间身份重置，未测时序质量`]);
    if(data.source.complete_source_file)entries.push(["素材范围","完整提供文件；原件可能是既有实验剪辑，实验完整性未验收。"]);
    entries.forEach(([name,value])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=name;dd.textContent=value;$("evidence").append(dt,dd);});
    $("result-link").href=item.result;$("result-link").hidden=false;
    $("checkpoints").replaceChildren();Array.from(new Set([0,2,4,6,...(data.video.duration_ms>30000 ? [.25,.5,.75,.95].map(r=>{const target=data.video.duration_ms*r;return data.frames.reduce((best,f)=>Math.abs(f.timestamp_ms-target)<Math.abs(best.timestamp_ms-target)?f:best,data.frames[0]).timestamp_ms/1000;}) : [])])).filter(t=>t<data.video.duration_ms/1000).forEach(t=>{const b=document.createElement("button");b.textContent=`${t.toFixed(2)} s ↗`;b.addEventListener("click",()=>go(t));$("checkpoints").appendChild(b);});
    message(`真实离线推理 · ${(data.video.duration_ms/1000).toFixed(0)} 秒开发片段。` + (item.review_note || "含误检与漏检，尚未完成独立质量验收。"));
  }catch(error){if(ticket===generation)message(`暂时无法载入：${error.message}。请检查本机素材与推理包。`);}
}
video.addEventListener("loadeddata",()=>{if(!data)return;ready=true;video.playbackRate=Number($("speed").value);$("seek").max=String(video.duration);for(const id of ["play","previous","next","seek"])$(id).disabled=false;render(true);});
video.addEventListener("error",()=>{if(data){ready=false;svg.replaceChildren();svg.dataset.valid="false";svg.dataset.frameIndex="";for(const id of ["play","previous","next","seek"])$(id).disabled=true;message("视频读取失败，请检查素材文件是否完整。");}});
video.addEventListener("play",()=>{$("play").textContent="暂停";});video.addEventListener("pause",()=>{$("play").textContent="播放";});
video.addEventListener("seeking",()=>{frameTime=null;svg.replaceChildren();});video.addEventListener("seeked",()=>{frameTime=video.currentTime;render(true);});
if(video.requestVideoFrameCallback){const tick=(_,meta)=>{frameTime=meta.mediaTime;render();video.requestVideoFrameCallback(tick);};video.requestVideoFrameCallback(tick);}else video.addEventListener("timeupdate",()=>{frameTime=video.currentTime;render();});
$("play").addEventListener("click",()=>{if(video.paused)video.play().catch(e=>message(`播放失败：${e.message}`));else video.pause();});
$("seek").addEventListener("input",()=>go(Number($("seek").value)));
$("speed").addEventListener("change",()=>{video.playbackRate=Number($("speed").value);});
for(const [id,delta] of [["previous",-1],["next",1]])$(id).addEventListener("click",()=>{if(!data)return;const i=Math.max(0,Math.min(data.frames.length-1,indexAt(video.currentTime*1000)+delta));go((data.frames[i].presentation_seconds ?? data.frames[i].timestamp_ms/1000)+0.000001);});
for(const id of ["boxes","masks","temporal","hands","labels","original","trails","semantic","ocr"])$(id).addEventListener("change",()=>render(true));
$("text-search").addEventListener("input",renderTextList);
$("object-select").addEventListener("change",()=>{detail($("object-select").value);render(true);});
(async()=>{try{const r=await fetch("demo-data/catalog.json");if(!r.ok)throw Error("尚未准备真实推理包");const catalog=await r.json();if(!catalog.clips?.length)throw Error("片段目录为空");$("clip-select").replaceChildren();catalog.clips.forEach((c,i)=>$("clip-select").add(new Option(c.title,String(i))));$("clip-select").disabled=false;$("clip-select").addEventListener("change",()=>loadClip(catalog.clips[Number($("clip-select").value)]));await loadClip(catalog.clips[0]);}catch(e){message(`${e.message}。请先运行本地推理并准备预览素材。`);}})();
