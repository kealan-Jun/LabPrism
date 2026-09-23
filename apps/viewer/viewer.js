"use strict";
const $ = id => document.getElementById(id);
const video = $("video"), svg = $("overlay"), ns = "http://www.w3.org/2000/svg";
const edges = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const colors = ["#d6f675","#63ddfa","#ffbb74","#e999ff","#68efba","#ff8db1"];
let textObservations = [];
let store=null, loadedBlock=-2, pendingBlock=null, catalogClips=[], currentClip=null;
let failedBlocks=new Set();
let selectedTrack=null, selectedEvent=-1, pendingSeek=0, deepObject=null;
const stateNames={candidate:'候选',partial_evidence:'部分证据',pending_confirmation:'待确认',confirmed:'已确认',rejected:'已拒绝',dependency_error:'依赖异常',unassociated:'未关联',available:'已接入'};
const query=new URLSearchParams(location.search);
if(query.get('embed')==='1')document.body.classList.add('embedded-viewer');
let data = null, lastIndex = -1, generation = 0, ready = false, frameTime = null;
const playbackClock=video.requestVideoFrameCallback?new PlaybackFrameClock(video,time=>{frameTime=time;render();}):null;
const roleLabel = role => role === "first_person" ? "第一人称" : role === "third_person" ? "第三人称" : "视角待确认";
function element(tag, attrs, parent = svg) { const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));parent.appendChild(e);return e; }
function indexAt(t) { let lo=0,hi=data.frames.length;while(lo<hi){const mid=(lo+hi)>>1;if(data.frames[mid].timestamp_ms<=t+0.001)lo=mid+1;else hi=mid;}return lo-1; }
function message(value) { $("load-status").textContent=value; }
function detail(index) {
  const obj=data?.frames[lastIndex]?.objects[Number(index)];
  $("instance-detail").textContent=index!==""&&obj ? `${obj.display_name || obj.label} · 置信度 ${(obj.confidence*100).toFixed(1)}% · 框 [${obj.box.join(", ")}] px · ${obj.mask_contours.length} 个轮廓 · ${obj.track_id ? `预测轨迹 ${obj.track_id} / ${obj.track_state}` : "帧内实例"}${obj.model_conflict ? " · 类别冲突待复核" : ""}` : "选择实例查看类别、置信度与坐标。";
  if(obj&&index!=="") {
    if(obj.tracking_exclusion)$("instance-detail").textContent+=" · "+ResultPresentation.trackingExclusion(obj);
    const related=(data.events||[]).filter(e=>e.object_track_id&&e.object_track_id===obj.track_id);
    $("instance-detail").textContent+=` · ${related.length} 条相关接近区间 · 登记设备身份尚未关联`;
  }
}
function drawTrail(item, color) {
  if(!$("trails").checked || !item.trail?.length)return;
  const d=item.trail.map((p,i)=>`${i===0 || p[0]-item.trail[i-1][0]>1000/data.video.sample_hz+75 ? "M" : "L"}${p[1]},${p[2]}`).join(" ");
  element("path",{class:"trail",d,fill:"none",stroke:color,"stroke-width":2,"stroke-opacity":.8});
}
function render(force=false) {
  if(!ready)return;
  if(!data){$("time").textContent=`${video.currentTime.toFixed(2)} / ${(video.duration||0).toFixed(2)} s`;$("seek").value=String(video.currentTime);return;}
  const t=(frameTime??video.currentTime)*1000;
  $("time").textContent=`${(t/1000).toFixed(2)} / ${(data.video.duration_ms/1000).toFixed(2)} s`;
  $("seek").value=String(video.currentTime);
  if(store?.index&&loadedBlock!==store.blockAt(t)) {
    svg.replaceChildren();svg.dataset.valid="false";svg.dataset.frameIndex="";
    $("object-select").disabled=true;
    $("counts").textContent="此时刻的预测尚不可用";
    $("instance-detail").textContent="等待当前时刻的实例；没有沿用上一时刻的预测。";
    $("text-observation").textContent="当前时刻的文字观察尚不可用。";
    $("video-ocr-evidence").replaceChildren();
    $("conflicts").textContent="";$("semantic-note").textContent="";
    $("sample-age").textContent=failedBlocks.has(store.blockAt(t))?"结果载入失败，可重试；原视频可继续播放":"正在载入此时刻的结果；原视频可继续播放";
    requestFrames(t);return;
  }
  const index=indexAt(t), frame=data.frames[index];
  const age=frame?t-frame.timestamp_ms:Infinity;
  // Allow the normal interval of the sampled stream while keeping a missing
  // sample visibly invalid instead of carrying an older prediction forward.
  const sampleWindow=Math.max(150,1000/data.video.sample_hz+75);
  const valid=frame&&age>=-Math.min(100,sampleWindow/2)&&age<=sampleWindow;
  $("object-select").disabled=!valid;
  svg.dataset.presentationMs=String(t);
  svg.dataset.frameIndex=valid?String(frame.frame_index):"";
  $("sample-age").textContent=valid?`预测帧差 ${Math.max(0,age).toFixed(0)} ms · ${data.video.sample_hz} Hz 抽样`:"当前时刻无有效预测";
  if(!force&&index===lastIndex&&String(Boolean(valid))===svg.dataset.valid)return;
  svg.dataset.valid=String(Boolean(valid));
  if(index!==lastIndex){
    lastIndex=index;$("object-select").replaceChildren(new Option("全部实例",""));
    if(frame)frame.objects.forEach((o,i)=>$("object-select").add(new Option(`${i+1}. ${o.display_name || o.label} ${(o.confidence*100).toFixed(0)}%`,String(i))));
    if(selectedTrack&&frame) {
      const selected=frame.objects.findIndex(o=>o.track_id===selectedTrack);
      $("object-select").value=selected>=0?String(selected):"";
    }
    if(deepObject&&valid){const selected=frame.objects.findIndex(o=>o.track_id===deepObject||o.id===deepObject);if(selected>=0){$("object-select").value=String(selected);selectedTrack=frame.objects[selected].track_id;}else{$("link-status").textContent="定位对象在当前分析帧没有观测；未选择其他对象。";}deepObject=null;}
    detail($("object-select").value);
    if(selectedTrack&&$("object-select").value==="")$("instance-detail").textContent=`轨迹 ${selectedTrack} 在当前帧没有观测；继续播放可回查再次出现的位置。`;
  }
  svg.replaceChildren();
  $("stage-label").textContent=$("original").checked?"原始画面":"模型叠加 · 候选结果";
  $("frame-stamp").textContent=frame?`${roleLabel(data.source.camera_role)} / 源视频 ${(frame.source_timestamp_ms/1000).toFixed(2)} s`:"尚无分析帧";
  $("counts").textContent=valid?ResultPresentation.frameCounts(frame,data):"当前帧未分析";
  const regions=frame?.semantic_regions || [];
  $("semantic-note").textContent=$("semantic").checked ? `研究候选，类别质量尚未验收。当前类别：${regions.map(r=>r.label).join("、")}。颜色按类别编号分配；轮廓简化，原始像素图保留在运行包。` : "";
  $("conflicts").textContent=valid ? ((frame.conflicting_objects || frame.rejected_objects || []).map(o=>`${o.display_name || o.label}：与笔记本模型冲突，${frame.conflicting_objects ? "保留原检测" : "旧候选曾过滤"}，待复核`).join("；") || "本帧无已记录的类别冲突。") : "";
  $("text-observation").textContent=valid ? (frame.availability.ocr==="not_run" ? "本轮未执行文字识别。" : frame.availability.ocr==="not_sampled" ? "本帧未采样文字；文字列表可跳到实际识别帧。" : (frame.texts || []).map(x=>`${x.text}（${(x.score*100).toFixed(0)}%）`).join("；") || "本帧无文字输出。") : "当前时刻无文字观察。";
  renderVideoOcrEvidence(valid ? frame : null);
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
    if(selectedTrack&&o.track_id!==selectedTrack)return;
    if(!selectedTrack&&selected!==""&&Number(selected)!==i)return;
    const color=colors[o.class_id%colors.length];drawTrail(o,color);const group=element("g",{class:"object"});
    const select=()=>{$("object-select").value=String(i);selectedTrack=o.track_id||null;detail(String(i));render(true);};
    group.setAttribute("tabindex","0");group.setAttribute("role","button");group.setAttribute("aria-label",`${o.display_name||o.label} ${o.track_id||o.id}`);
    group.addEventListener("click",select);group.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();select();}});
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
function renderVideoOcrEvidence(frame){
  const panel=$("video-ocr-evidence");panel.replaceChildren();
  if(!frame?.ocr_observations?.length)return;
  const title=document.createElement('h3'),intro=document.createElement('p');
  title.textContent=`当前帧文字证据 · ${(frame.timestamp_ms/1000).toFixed(2)} s`;
  intro.className='muted';intro.textContent='FieldRecognition 实际 CPU 识别。按原视频帧匹配；设备、字段、单位未确认，以下文字不构成正式读数。';panel.append(title,intro);
  const textOf=rows=>rows.filter(r=>r.text.trim()).map(r=>`${r.text}（${Math.round(r.score*100)}%）`).join(' / ')||'未检出文字';
  const labels={whole_image:'整帧识别',actual_panel_model_proposal:'自动面板候选',project_manual_review:'手选区域诊断'};
  const stages={panel_ocr:'区域原文',digit_ocr:'数字裁剪',small_panel_ocr:'放大区域',digit_ocr_check:'源图复核'};
  const regionCounts={};
  for(const observation of frame.ocr_observations){
    const details=document.createElement('details'),summary=document.createElement('summary');
    const basis=observation.region.basis;regionCounts[basis]=(regionCounts[basis]||0)+1;
    const label=labels[basis]+(basis==='whole_image'?'':` ${regionCounts[basis]}`);
    summary.textContent=`${label} · ${textOf(observation.lines)}`;
    details.append(summary);
    const raw=document.createElement('p');raw.textContent='识别原文：'+textOf(observation.lines);details.append(raw);
    if(observation.mode==='manual'){const note=document.createElement('p');note.className='muted';note.textContent='此区域由项目手选，不计入自动面板定位成果。';details.append(note);}
    const refined=observation.refinement;
    if(refined){
      const p=document.createElement('p');p.textContent='数字精读候选：'+textOf(refined.lines);
      if(refined.consistency_status==='disagreement')p.textContent+=' · 多次识别冲突，未选定结果';
      else if(refined.consistency_status==='resolved')p.textContent+=' · 经源图复核选择候选，仍未确认读数';
      details.append(p);
      for(const alternative of refined.alternatives.filter(r=>r.text.trim())){const line=document.createElement('p');line.className='muted';line.textContent=`${stages[alternative.stage]||alternative.stage}：${alternative.text}（${Math.round(alternative.score*100)}%）`;details.append(line);}
    }
    if(/^ocr-[a-f0-9]{64}\.png$/.test(observation.image_file)){
      const link=document.createElement('a'),img=document.createElement('img');
      link.href=new URL(observation.image_file,new URL(currentClip.result,location.href)).href;
      link.target='_blank';link.rel='noopener';link.title='打开原始识别输入';
      img.src=link.href;img.alt=`${labels[observation.region.basis]}的实际输入裁剪`;img.loading='lazy';img.className='video-ocr-crop';link.append(img);details.append(link);
    }
    panel.append(details);
  }
}
function renderEvents(){
  $("event-list").replaceChildren();
  const events=data.events || [];
  $("event-status").textContent=events.length ? `${events.length} 个二维接近区间${data.events_truncated?`（共 ${data.event_count} 个；其余见下载记录）`:""}；不证明物理接触或实验步骤。` : ResultPresentation.emptyEventStatus(data);
  for(const id of ["event-previous","event-next","event-loop"])$(id).disabled=!events.length;
  events.forEach(event=>{const b=document.createElement("button");b.type="button";b.textContent=`${(event.start_ms/1000).toFixed(2)}–${(event.end_ms/1000).toFixed(2)} s · ${event.label}`;
    b.addEventListener("click",()=>selectEvent(events.indexOf(event)));$("event-list").appendChild(b);});
}
function clampTime(seconds){const duration=Number.isFinite(video.duration)?video.duration:(data?.video.duration_ms/1000||0);return Number.isFinite(seconds)?Math.min(Math.max(0,seconds),Math.max(0,duration-.001)):0;}
function updatePlaybackControls(){
  const usable=ready&&!video.error&&video.readyState>=2;
  for(const id of ['play','seek'])$(id).disabled=!usable;
  for(const id of ['previous','next'])$(id).disabled=!usable||!data;
}
function go(seconds){video.pause();frameTime=null;video.currentTime=clampTime(seconds);}
async function requestFrames(ms){
  const active=store,ticket=generation,block=active.blockAt(ms);
  if(pendingBlock===block||failedBlocks.has(block))return;pendingBlock=block;
  try {
    const frames=await active.framesAt(ms);
    if(ticket!==generation||store!==active||block!==active.blockAt((frameTime??video.currentTime)*1000))return;
    data.frames=frames;loadedBlock=block;lastIndex=-1;render(true);
    message("当前时刻的结果已载入 · 模型输出需复核。");
  } catch(e){if(ticket===generation&&e.name!=="AbortError"){failedBlocks.add(block);$("retry-results").hidden=false;message(`此结果图层暂不可用：${e.message}。原视频仍可播放。`);render(true);}}
  finally{if(ticket===generation&&pendingBlock===block)pendingBlock=null;}
}
function selectEvent(index){
  if(!data?.events?.length)return;selectedEvent=Math.max(0,Math.min(data.events.length-1,index));
  const event=data.events[selectedEvent];selectedTrack=event.object_track_id||null;
  $("event-detail").textContent=`${event.label} · ${event.evidence_count??event.evidence?.length??0} 个实际证据帧 · 候选二维接近，不证明接触。`;
  go(event.start_ms/1000+.000001);
}
function setLink(){
  if(!currentClip)return;
  const params=new URLSearchParams({clip:currentClip.id,t:video.currentTime.toFixed(3),view:currentClip.camera_id||""});
  const obj=data?.frames[lastIndex]?.objects[Number($("object-select").value)];
  if(svg.dataset.valid==="true"&&$("object-select").value!==""&&obj)params.set('object',obj.track_id||obj.id);
  history.replaceState(null,'',location.pathname+'?'+params.toString());
  $("link-status").textContent='地址栏已更新，可复制此定位链接。';
}
$("multiview-return")?.addEventListener('click',()=>{
  if(!currentClip||!ready)return;
  video.pause();
  document.dispatchEvent(new CustomEvent('labprism:show-original-views',{
    detail:{clip:currentClip,mediaSeconds:video.currentTime}
  }));
});
async function loadClip(item,start=0,object=null){
  playbackClock?.invalidate();
  deepObject=object;
  store?.dispose();store=null;loadedBlock=-2;pendingBlock=null;failedBlocks=new Set();selectedTrack=null;selectedEvent=-1;pendingSeek=start;currentClip=item;$("clip-select").dataset.clipId=item.id;
  $("retry-results").hidden=true;
  $("run-review-note").textContent=item.review_note||"含误检与漏检，尚未完成独立质量验收。";
  $("event-detail").textContent="";$("event-loop").checked=false;$("link-status").textContent="";
  const ticket=++generation;ready=false;data=null;lastIndex=-1;frameTime=null;video.pause();video.removeAttribute("src");video.load();svg.replaceChildren();
  $("labels").checked=query.get('embed')!=='1';
  for(const id of ["play","previous","next","seek","object-select","event-previous","event-next","event-loop"])$(id).disabled=true;
  svg.dataset.valid="false";svg.dataset.frameIndex="";
  for(const id of ["masks","trails","semantic","temporal","ocr"]){$(id).checked=false;$(id).disabled=true;}
  $("hands").disabled=true;
  $("semantic-note").textContent="";$("conflicts").textContent="";$("text-observation").textContent="";textObservations=[];$("text-search").value="";$("text-list").replaceChildren();$("event-list").replaceChildren();$("event-status").textContent="";$("ocr-status").textContent="";
  $("video-ocr-evidence").replaceChildren();$("ocr-samples").replaceChildren();
  $("object-select").replaceChildren(new Option("全部实例",""));detail("");
  $("evidence").replaceChildren();$("checkpoints").replaceChildren();$("result-link").hidden=true;$("result-link").removeAttribute("href");
  $("counts").textContent="等待模型结果";$("sample-age").textContent="";$("time").textContent="0.00 / 0.00 s";$("seek").value="0";
  $("clip-title").textContent=item.title;$("clip-meta").textContent="";$("frame-stamp").textContent="等待视频";
  const peers=catalogClips.filter(c=>c.clip_sha256===item.clip_sha256&&c.width===item.width&&c.height===item.height);
  $("compare-select").replaceChildren();peers.forEach(c=>$("compare-select").add(new Option(c.title,c.id)));$("compare-select").value=item.id;$("compare-select").disabled=peers.length<2;
  $("view-status").textContent=`${peers.length} 个同输入版本可对照；切换时保留源时间。跨机位同步待可靠时间映射，不按同实验名称推定。`;
  video.dataset.generation=String(ticket);video.src=item.video;
  message("正在核对片段与模型记录…");
  try{
    const active=new ResultStore(item.result);store=active;
    const result=await active.open();const frames=await active.framesAt(start*1000);if(ticket!==generation)return;
    data=result;data.frames=frames;loadedBlock=active.blockAt(start*1000);svg.setAttribute("viewBox",`0 0 ${data.video.width} ${data.video.height}`);
    $("stage").style.aspectRatio=`${data.video.width} / ${data.video.height}`;
    $("clip-title").textContent=item.title;$("clip-meta").textContent=`${roleLabel(data.source.camera_role)} · ${(data.video.duration_ms/1000).toFixed(0)} 秒 · ${data.video.width} × ${data.video.height}`;
    $("evidence").replaceChildren();
    const candidate=data.schema_version!=="labprism-video-result/1";
    const names=data.ontology?.display_names || {};
    $("ocr").disabled=!(store.index?.layers.ocr??data.frames.some(f=>f.texts?.length));
    $("temporal").disabled=!(store.index?.layers.temporal??data.frames.some(f=>f.temporal_instances?.length));
    $("masks").disabled=!(store.index?.layers.masks??data.frames.some(f=>f.objects.some(o=>o.mask_contours?.length)));
    $("masks").checked=!$("masks").disabled&&$("masks").defaultChecked;
    $("hands").disabled=!(store.index?.layers.hands??data.frames.some(f=>f.hands.length));
    $("hands").checked=!$("hands").disabled&&$("hands").defaultChecked;
    textObservations=store.index?.text_index||data.frames.flatMap(f=>(f.texts || []).map(item=>({...item,timestamp_ms:f.timestamp_ms})));renderTextList();renderEvents();
    for(const sample of store.index?.ocr_frame_index||[]){const b=document.createElement('button');b.type='button';b.textContent=`${(sample.timestamp_ms/1000).toFixed(2)} s · 文字诊断 · ${sample.automatic} 自动区域 / ${sample.manual} 手选区域`;b.addEventListener('click',()=>go(sample.timestamp_ms/1000+.000001));$("ocr-samples").append(b);}
    $("trails").disabled=!(store.index?.layers.trails??data.frames.some(f=>[...f.objects,...f.hands].some(o=>o.track_id)));$("semantic").disabled=!(store.index?.layers.semantic??data.frames.some(f=>f.semantic_regions?.length));
    const poseEvidence=ResultPresentation.poseEvidence(data,candidate),handModel=poseEvidence.active;
    const entries=[["素材",`${data.source.source_id} · ${ResultPresentation.sourceUse(data)}`],["源 SHA256",data.source.source_sha256],["检测模型",ResultPresentation.modelNames(data,["object_detection","joint_detection_instance_segmentation_candidate"])],["类别词典",`${Object.keys(names).length} 类 · ${data.ontology?.display_language || "未声明"}`],["实例分割",ResultPresentation.modelNames(data,["box_prompted_instance_segmentation","joint_detection_instance_segmentation_candidate"])],["手姿",handModel==="未执行"?handModel:`${handModel} · ${candidate?"2D / 深度与左右手未知，隐藏低分点":"相对深度，非全局 3D"}`],["运行",ResultPresentation.runSummary(data)],["手姿覆盖",ResultPresentation.handCoverage(data,store.index?.frame_count||data.frames.length)],["效果指标","独立准确率 / 泛化 / 时序质量：尚未测得"]];
    if(candidate)entries.push(["候选状态",item.review_note||"模型与关系输出仍需质量复核；结果格式版本不代表质量通过。"]);
    if(data.ocr_integration)entries.push(["文字来源",`${data.ocr_integration.producer} · Paddle CPU · 精确原帧接收；手选诊断另列`],["文字模型",ResultPresentation.modelNames(data,['ocr','panel_detection'])],["OCR 模型哈希","识别器以模型文件清单哈希记录；面板检测以权重文件哈希记录。许可信息尚待补齐。"]);
    if(poseEvidence.parent)entries.push(["手姿父模型",`${poseEvidence.parent} · 保留为对照；当前骨架使用训练候选`]);
    if(Object.keys(data.environment?.actual_execution_providers||{}).length)entries.push(["实际执行",Object.entries(data.environment.actual_execution_providers).filter(([,value])=>value).map(([name,value])=>`${name}: ${value}`).join("；")]);
    if(data.temporal_windows?.length)entries.push(["时序掩码",`${data.temporal_windows.length} 个窗口；窗口间身份重置，未测时序质量`],["时序模型",ResultPresentation.modelNames(data,["video_instance_segmentation","box_prompted_instance_segmentation"])]);
    if(data.source.complete_source_file)entries.push(["素材范围","完整提供文件；原件可能是既有实验剪辑，实验完整性未验收。"]);
    entries.push(...ResultPresentation.outputSummary(data));
    entries.forEach(([name,value])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=name;dd.textContent=value;$("evidence").append(dt,dd);});
    $("result-link").href=item.download||item.result;$("result-link").hidden=false;
    $("checkpoints").replaceChildren();Array.from(new Set([0,2,4,6,...(data.video.duration_ms>30000 ? [.25,.5,.75,.95].map(r=>{const target=data.video.duration_ms*r;return target/1000;}) : [])])).filter(t=>t<data.video.duration_ms/1000).forEach(t=>{const b=document.createElement("button");b.textContent=`${t.toFixed(2)} s ↗`;b.addEventListener("click",()=>go(t));$("checkpoints").appendChild(b);});
    if(video.readyState>=2){ready=true;for(const id of ["play","previous","next","seek"])$(id).disabled=false;go(start);render(true);}
    message(video.error?"视频读取失败，请检查素材文件是否完整或切换片段。":`真实离线分析 · ${(data.video.duration_ms/1000).toFixed(0)} 秒 · 模型输出需复核`);
    document.dispatchEvent(new CustomEvent('labprism:analysis-selected',{detail:{clip:item}}));
    $("run-review-note").textContent=`${ResultPresentation.sourceUse(data)}。`+(item.review_note||"含误检与漏检，尚未完成独立质量验收。");
  }catch(error){if(ticket===generation){$("retry-results").hidden=false;message(`结果暂不可用：${error.message}。原视频仍可播放。`);}}
}
video.addEventListener("loadeddata",()=>{if(video.dataset.generation!==String(generation))return;ready=true;video.currentTime=clampTime(pendingSeek);video.playbackRate=Number($("speed").value);$("seek").max=String(video.duration);for(const id of ["play","seek"])$(id).disabled=false;for(const id of ["previous","next"])$(id).disabled=!data;render(true);});
video.addEventListener("error",()=>{if(!currentClip||!video.getAttribute("src"))return;ready=false;svg.replaceChildren();svg.dataset.valid="false";svg.dataset.frameIndex="";for(const id of ["play","previous","next","seek","object-select"])$(id).disabled=true;$("counts").textContent="原始视频不可用";message("视频读取失败，请检查素材文件是否完整或切换片段。");});
video.addEventListener("play",()=>{$("play").textContent="暂停";});video.addEventListener("pause",()=>{$("play").textContent="播放";});
video.addEventListener("seeking",()=>{playbackClock?.invalidate();frameTime=null;svg.replaceChildren();svg.dataset.valid="false";svg.dataset.frameIndex="";$("video-ocr-evidence").replaceChildren();$("text-observation").textContent="正在定位，等待此时刻的文字观察。";});video.addEventListener("seeked",()=>{frameTime=video.currentTime;updatePlaybackControls();render(true);playbackClock?.watch();});
video.addEventListener('canplay',()=>{updatePlaybackControls();render(true);});
if(playbackClock)video.addEventListener('loadeddata',()=>playbackClock.watch());else video.addEventListener("timeupdate",()=>{frameTime=video.currentTime;render();});
$("play").addEventListener("click",()=>{if(video.paused)video.play().catch(e=>message(`播放失败：${e.message}`));else video.pause();});
$("seek").addEventListener("input",()=>go(Number($("seek").value)));
$("speed").addEventListener("change",()=>{video.playbackRate=Number($("speed").value);});
for(const [id,delta] of [["previous",-1],["next",1]])$(id).addEventListener("click",()=>{if(!data)return;const t=store.nextTime(video.currentTime*1000,delta);go(t/1000+.000001);});
for(const id of ["boxes","masks","temporal","hands","labels","original","trails","semantic","ocr"])$(id).addEventListener("change",()=>render(true));
$("text-search").addEventListener("input",renderTextList);
$("object-select").addEventListener("change",()=>{const i=$("object-select").value;selectedTrack=i!==""?data?.frames[lastIndex]?.objects[Number(i)]?.track_id||null:null;detail(i);render(true);});
$("compare-select").addEventListener("change",()=>{const item=catalogClips.find(c=>c.id===$("compare-select").value);if(item){$("clip-select").value=String(catalogClips.indexOf(item));loadClip(item,video.currentTime);}});
$("copy-link").addEventListener("click",setLink);
$("retry-results").addEventListener("click",()=>{if(!currentClip)return;$("retry-results").hidden=true;if(data){failedBlocks.clear();render(true);}else loadClip(currentClip,video.currentTime);});
$("event-previous").addEventListener("click",()=>selectEvent(selectedEvent-1));$("event-next").addEventListener("click",()=>selectEvent(selectedEvent+1));
video.addEventListener("timeupdate",()=>{const event=data?.events?.[selectedEvent];if(event&&$("event-loop").checked&&video.currentTime*1000>event.end_ms){video.currentTime=event.start_ms/1000;}});
(async()=>{try{const r=await fetch(document.body.dataset.catalog || "demo-data/catalog.json");if(!r.ok)throw Error("尚未准备真实推理包");const catalog=await r.json();if(!catalog.clips?.length)throw Error("片段目录为空");catalogClips=catalog.clips;$("clip-select").replaceChildren();catalog.clips.forEach((c,i)=>$("clip-select").add(new Option(c.title,String(i))));$("clip-select").disabled=false;$("clip-select").addEventListener("change",()=>loadClip(catalog.clips[Number($("clip-select").value)]));let selection;try{selection=ResultPresentation.initialSelection(catalog.clips,query);}catch(error){const placeholder=new Option("选择可用片段", "", true, true);placeholder.disabled=true;$("clip-select").prepend(placeholder);message(error.message);return;}
$("clip-select").value=String(catalog.clips.indexOf(selection.item));await loadClip(selection.item,selection.start,selection.object);}catch(e){message(`${e.message}。请先运行本地推理并准备预览素材。`);}})();

(async()=>{
  if(query.get('embed')==='1'||!$("upstream-status"))return;
  try {
    const r=await fetch('upstream/snapshot.json');if(!r.ok)throw Error('尚无上游接收快照');const snapshot=await r.json();
    if(snapshot.schema_version!=='labprism-upstream-snapshot/1'||snapshot.mode!=='real_api')throw Error('上游来源格式不支持');
    $("upstream-status").textContent=Object.entries(snapshot.sources).map(([name,source])=>`${name} · ${stateNames[source.state]||source.state}`).join(' / ')+` · 快照 ${snapshot.created_at.slice(0,16).replace('T',' ')} UTC`;
    const list=$("upstream-list");
    for(const row of snapshot.experiments||[]) {
      const p=document.createElement('p');p.textContent=`视频观察 · ${row.camera_id} · ${stateNames[row.evidence_state]||row.evidence_state} · ${row.kind} · 来源版本 ${row.revision.slice(0,10)}`;list.append(p);
    }
    for(const job of snapshot.readouts||[]) {
      if(!job.fields.length){
        const button=document.createElement('button');button.type='button';button.textContent=`照片 · ${job.captured_at||'采集时间未知'} · ${recognitionReason(job)}`;
        button.addEventListener('click',()=>showReadout(job,null));list.append(button);
      }
      for(const field of job.fields){
        const button=document.createElement('button');button.type='button';button.textContent=`${field.instrument_name||'设备待确认'} · ${field.name} ${field.value??field.display_state??'未读出'} ${field.unit||''} · ${stateNames[field.status]||field.status}`;
        button.addEventListener('click',()=>showReadout(job,field));list.append(button);
      }
    }
    if(!(snapshot.readouts||[]).length){const p=document.createElement('p');p.textContent='上游尚无可显示读数。';list.append(p);}
  }catch(e){$("upstream-status").textContent=e.message+'；已有视频可继续查看。';}
})();
function recognitionReason(job){
  const r=job.recognition||{};
  if(r.reason==='no_active_instrument_binding')return '未绑定仪器，OCR 未执行';
  if(r.reason==='no_visible_bound_panel')return '未找到可归属的仪器面板，OCR 未执行';
  if(job.fields?.length)return `${job.fields.length} 个读数字段可检查`;
  return ({not_run:'OCR 未执行',no_detection:'未取得读数字段',failed:'识别失败',unknown:'执行依据未提供'}[r.state]||'尚无读数字段')+(r.reason?' · '+r.reason:'');
}
function showReadout(job,field,panelId='readout-detail'){
  const panel=$(panelId);panel.hidden=false;panel.replaceChildren();
  const generation=String(Number(panel.dataset.generation||0)+1);panel.dataset.generation=generation;
  const h=document.createElement('h3');h.textContent=field?`${field.instrument_name||'设备待确认'} / ${field.name}`:'照片记录 · 识别与归属';panel.append(h);
  const info=document.createElement('p');info.textContent=(field?`${field.value??field.display_state??'未取得有效数值'} ${field.unit||''} · ${stateNames[field.status]||field.status}`:recognitionReason(job))+` · ${job.captured_at||'采集时钟不可用'} · 未关联到当前实验`;panel.append(info);
  const timeBasis={nas_filename_local_time_not_hardware_verified:'NAS 文件名时间 · 硬件时钟未核验',source_capture_time:'来源提供的采集时间 · 精度未提供',synchronized_frame_timestamp:'上游同步帧时间'}[job.capture_time_basis]||job.capture_time_basis;
  const attribution=job.attribution_reason==='historical_binding_missing'?'拍摄时没有可核验的仪器绑定':job.attribution_reason;
  for(const [label,value] of [['设备 ID',field?.instrument_id],['面板',field?.panel_id],['OCR 原文',field?.raw_text||(field?.raw_lines||[]).map(x=>x.text).join(' / ')||'无可用原文'],['归属检查',field?field.association_issue||'拍摄时有效绑定快照':attribution||'尚无可核验仪器绑定'],['使用时段',field?.binding_id||'无法确认'],['处理状态',job.processing_state==='completed'?'已处理':job.processing_state],['实际 OCR 调用',job.recognition?.actual_model_invocation===true?'已执行':job.recognition?.actual_model_invocation===false?'未执行':'未知'],['采集时间依据',timeBasis],['记录范围',job.record_scope==='draft'?'草稿':job.record_scope],['识别版本',job.revision]]) {
    const p=document.createElement('p');p.textContent=`${label}：${value??'未知'}`;panel.append(p);
  }
  if(!field)for(const item of job.fields||[]){
    const button=document.createElement('button');button.type='button';button.textContent=`${item.instrument_name||'设备待确认'} · ${item.name} · ${stateNames[item.status]||item.status}`;
    button.addEventListener('click',()=>showReadout(job,item,panelId));panel.append(button);
  }
  for(const [name,file] of [['原始面板',field?.panel_image_url],['原始照片',job.image_url]]) {
    if(!/^[a-f0-9]{64}\.png$/.test(file||''))continue;
    const figure=document.createElement('figure'),img=document.createElement('img'),cap=document.createElement('figcaption');img.src='upstream/'+file;img.alt=name;img.loading='lazy';cap.textContent=name;figure.append(img,cap);panel.append(figure);
  }
  panel.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  appendOcrDiagnostic(job,panel,generation);
}
let ocrDiagnosticRequest;
async function appendOcrDiagnostic(job,panel,generation){
  try{
    ocrDiagnosticRequest ||= fetch('ocr-diagnostic/snapshot.json').then(r=>r.ok?r.json():null).catch(()=>null);
    const snapshot=await ocrDiagnosticRequest;
    if(panel.dataset.generation!==generation||!['labprism-ocr-diagnostic/1','labprism-ocr-diagnostic/2'].includes(snapshot?.schema_version)||snapshot.mode!=='real_producer_diagnostic')return;
    const item=snapshot.images.find(row=>row.job_id===job.job_id&&row.source_image_sha256+'.png'===job.image_url);
    if(!item)return;
    const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='离线 OCR 诊断 · 查看原图与区域对照';details.append(summary);
    const intro=document.createElement('p');intro.textContent=`FieldRecognition · ${snapshot.model} · ${snapshot.device.toUpperCase()}。以下是另一次实际识别的候选，未修改上游记录；设备、字段及单位未确认。手选与自动候选分别标明，检测类别不建立仪器身份。`;details.append(intro);
    for(const [index,observation] of item.observations.entries()){
      const article=document.createElement('article'),heading=document.createElement('h4'),text=document.createElement('p');
      const basis=observation.region.basis;
      const label=basis==='whole_image'?'整张照片识别':basis==='actual_panel_model_proposal'?`自动面板候选 ${index}`:`手选区域 ${index}`;
      heading.textContent=label;
      text.textContent='识别原文：'+(observation.lines.map(line=>line.text).filter(Boolean).join(' / ')||'未检出文字');article.append(heading,text);
      if(observation.refinement){const p=document.createElement('p');p.textContent='数字精读：'+(observation.refinement.lines?.map(line=>line.text).join(' / ')||'未取得可靠数字候选');article.append(p);}
      if(basis!=='whole_image'&&/^[a-f0-9]{64}\.png$/.test(observation.image_url)){const img=document.createElement('img');img.src='ocr-diagnostic/'+observation.image_url;img.alt=`实际识别输入 · ${label}`;img.loading='lazy';img.className='diagnostic-crop';article.append(img);}
      details.append(article);
    }
    const link=document.createElement('a');link.href='ocr-diagnostic/snapshot.json';link.textContent='查看本轮诊断记录';details.append(link);panel.append(details);
  }catch(_){/* Optional diagnostic failure does not hide the actual upstream evidence. */}
}
