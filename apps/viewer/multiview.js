/* Actual received originals, synchronized to the producer clock, without overlays. */
(async function(){
  const host=document.getElementById('multiview');if(!host||new URLSearchParams(location.search).get('embed')==='1')return;
  host.hidden=true;
  document.getElementById('multiview-return').hidden=true;
  const status=document.getElementById('multiview-status'),clock=LabPrismClock;
  try {
    const response=await fetch('multiview/snapshot.json');if(!response.ok)throw Error('尚无已接收的多视角记录');
    const raw=await response.text(),data=JSON.parse(raw);
    const snapshotHash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw)))].map(v=>v.toString(16).padStart(2,'0')).join('');
    if(data.schema_version!=='labprism-multiview-playback/1'||data.source_mode!=='real_api_and_received_media'||
      !Array.isArray(data.views)||data.views.length<2||data.views.length>6||
      !Number.isFinite(data.duration_seconds)||data.duration_seconds<=0||data.duration_seconds>1800)throw Error('多视角记录格式不支持');
    if(new Set(data.views.map(v=>v.camera_id)).size!==data.views.length)throw Error('重复机位不构成多视角');
    document.getElementById('multiview-title').textContent=data.title;
    const grid=document.getElementById('multiview-grid'),seek=document.getElementById('multiview-seek');
    const toggle=document.getElementById('multiview-play'),output=document.getElementById('multiview-time');
    let current=0,playing=false,generation=0,frame=0,master=null,selectedAction=null,selectedPhoto=null;
    const views=data.views.map(v=>{
      clock.validate(v.knots);if(!/^view-\d+\.mp4$/.test(v.video))throw Error('素材路径无效');
      const article=document.createElement('article'),name=document.createElement('h3'),video=document.createElement('video'),note=document.createElement('p'),analysis=document.createElement('div');
      name.textContent=({first_person:'第一人称',third_person:'第三人称'}[v.camera_role]||'未知视角')+' · '+v.camera_id;
      video.src='multiview/'+v.video;video.muted=true;video.playsInline=true;video.preload='metadata';video.setAttribute('aria-label',name.textContent+'原画');
      note.setAttribute('role','status');note.textContent='正在载入原画';analysis.className='multiview-analysis';article.append(name,video,note,analysis);grid.append(article);
      return {...v,mediaUrl:'multiview/'+v.video,video,note,analysis,analysisLinks:[],failed:false};
    });
    function pause(message){
      playing=false;generation++;cancelAnimationFrame(frame);views.forEach(v=>v.video.pause());toggle.textContent='播放可用视角';
      if(message)status.textContent=message;
    }
    function showTime(){seek.value=String(current);output.textContent=current.toFixed(2)+' / '+data.duration_seconds.toFixed(2)+' s';}
    function position(t,force=false){
      current=Math.max(0,Math.min(data.duration_seconds,t));showTime();
      for(const view of views){
        const target=clock.map(view.knots,current);
        const available=target!==null&&!view.failed&&(!Number.isFinite(view.video.duration)||target<view.video.duration);
        for(const {link,clip} of view.analysisLinks){
          link.hidden=!available;
          if(available){const url=new URL('demo.html',location.href);url.search=new URLSearchParams({clip:clip.id,view:view.camera_id,t:target.toFixed(6),mv:snapshotHash,mt:current.toFixed(6)}).toString();url.hash='main';link.href=url.href;}
        }
        view.video.hidden=!available;
        if(!available){view.video.pause();view.note.textContent=view.failed?'该视角载入失败；可重试原画':'此时刻没有已映射画面';continue;}
        view.note.textContent='原始画面 · 采集时钟对照';
        if(force||Math.abs(view.video.currentTime-target)>.12)view.video.currentTime=target;
      }
    }
    function tick(){
      if(!playing||!master)return;
      const t=clock.map(master.knots,master.video.currentTime,1);
      if(t===null){pause('已到达此视角的有效时间边界');return;}
      position(t);
      if(t>=data.duration_seconds-.04){pause();return;}
      frame=requestAnimationFrame(tick);
    }
    async function play(){
      if(playing){pause();return;}
      if(current>=data.duration_seconds-.1)position(0,true);
      const eligible=views.filter(v=>{
        const target=clock.map(v.knots,current);
        return !v.failed&&target!==null&&Number.isFinite(v.video.duration)&&target<v.video.duration;
      });
      if(!eligible.length){status.textContent='此时刻无可播放画面，请选择其他时间。';return;}
      selectedAction=null;selectedPhoto=null;master=eligible[0];const token=++generation;
      const results=await Promise.allSettled(eligible.map(v=>v.video.play()));
      if(token!==generation){eligible.forEach(v=>v.video.pause());return;}
      if(results.some(r=>r.status==='rejected')){pause('播放未能开始，请重试原画。');return;}
      playing=true;toggle.textContent='暂停多视角';status.textContent='按上游采集时钟联动；精确同步、同一器材与操作者身份尚未验证。';tick();
    }
    for(const view of views){
      view.video.addEventListener('error',()=>{view.failed=true;pause('部分原画不可用；其他视角仍可单独播放。');position(current);});
      view.video.addEventListener('loadedmetadata',()=>{view.failed=false;position(current,true);});
      view.video.addEventListener('waiting',()=>{if(playing)pause('原画缓冲中，已暂停联动；就绪后可继续播放。');});
      view.video.addEventListener('ended',()=>{if(playing)pause('已到达原画末尾。');});
    }
    seek.max=String(data.duration_seconds);seek.disabled=false;toggle.disabled=false;
    seek.addEventListener('input',()=>{pause();selectedAction=null;selectedPhoto=null;position(Number(seek.value),true);});toggle.addEventListener('click',play);
    const linkStatus=document.getElementById('multiview-link-status');
    document.getElementById('multiview-link').disabled=false;
    document.getElementById('multiview-link').addEventListener('click',()=>{
      const url=new URL('demo.html',location.href);url.searchParams.set('mv',snapshotHash);url.searchParams.set('mt',current.toFixed(6));url.hash='multiview';
      if(selectedAction)url.searchParams.set('ma',selectedAction.id);if(selectedPhoto)url.searchParams.set('mp',selectedPhoto.job.job_id);
      history.replaceState(null,'',url);const a=document.createElement('a');a.href=url.href;a.textContent='重新打开此定位';linkStatus.replaceChildren(a);
    });
    document.getElementById('multiview-retry').addEventListener('click',()=>{
      pause();const attempt=Date.now();
      views.forEach(v=>{v.failed=false;v.video.src=v.mediaUrl+'?retry='+attempt;v.video.load();});position(current,true);
    });
    document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
    document.addEventListener('labprism:show-original-views',event=>{
      const t=clock.analysisTime(views,event.detail?.clip,event.detail?.mediaSeconds);
      pause();
      if(t===null){status.textContent='当前分析时刻没有匹配的多视角映射；下方保留独立原画位置。';return;}
      selectedAction=null;selectedPhoto=null;position(t,true);
      status.textContent='已按当前分析原片和采集时钟定位双路原画；精确同步与跨视角身份尚未验证。';
    });
    window.addEventListener('pagehide',()=>pause());
    const link=document.getElementById('multiview-evidence');link.href='multiview/snapshot.json';link.hidden=false;
    const actions=views.flatMap(view=>(view.action_evidence||[]).map(event=>({...event,camera_role:view.camera_role})))
      .filter(event=>Number.isFinite(event.timestamp_seconds)&&event.timestamp_seconds>=0&&event.timestamp_seconds<=data.duration_seconds)
      .sort((a,b)=>a.timestamp_seconds-b.timestamp_seconds);
    const actionList=document.getElementById('multiview-actions'),actionDetail=document.getElementById('multiview-action-detail');
    const labels={device_panel_operation:'面板操作',pipetting:'移液操作',weighing:'称量操作',pouring:'倾倒操作',mixing:'混合操作'};
    function selectAction(event){
      pause();selectedAction=event;selectedPhoto=null;position(event.timestamp_seconds,true);
      actionDetail.textContent=`VisionCortex 候选证据帧 · ${event.camera_id} · ${event.producer_event_id}。由上游选择，不表示操作已确认；另一视角仅按采集时钟对照，不计为动作共识。`;
    }
    for(const event of actions){
      const button=document.createElement('button'),role=event.camera_role==='first_person'?'第一人称':event.camera_role==='third_person'?'第三人称':'未知视角';
      button.type='button';button.textContent=`${event.timestamp_seconds.toFixed(2)} s · ${labels[event.action_type]||event.action_type||'动作观察'}候选 · ${role}`;
      button.addEventListener('click',()=>selectAction(event));actionList.append(button);
    }
    if(!actions.length)actionDetail.textContent='本时间范围尚无带已验证源帧定位的上游动作候选。';
    else actionDetail.textContent=`${actions.length} 个上游候选证据帧；点击定位原画。时间点不是完整动作区间。`;
    status.textContent='两路已处理活动原片 · 采集时钟对照 · 精确同步、实验完整性与跨视角身份尚未验证。';
    position(0,true);
    try{
      const r=await fetch('demo-data/catalog.json');if(!r.ok)throw Error('分析目录不可用');
      const catalog=await r.json();if(catalog.schema_version!=='labprism-demo-catalog/1'||!Array.isArray(catalog.clips)||catalog.clips.length>100)throw Error('分析目录格式不支持');
      function scopeToInput(clip){
        const matched=views.some(view=>clock.analysisVersions(view,clip?[clip]:[]).length);
        host.hidden=!matched;document.getElementById('multiview-return').hidden=!matched;
        if(!matched)pause();
      }
      document.addEventListener('labprism:analysis-selected',event=>scopeToInput(event.detail.clip));
      scopeToInput(catalog.clips.find(c=>c.id===document.getElementById('clip-select').dataset.clipId));
      for(const view of views){
        const versions=clock.analysisVersions(view,catalog.clips);
        if(!versions.length){view.analysis.textContent='此原片尚未接入逐帧分析';continue;}
        for(const clip of versions){const link=document.createElement('a');link.textContent='查看分析 · '+clip.title;link.addEventListener('click',()=>pause());view.analysis.append(link);view.analysisLinks.push({link,clip});}
      }
      position(current);
    }catch(_){views.forEach(view=>view.analysis.textContent='分析入口暂不可用，原画可继续查看');}
    let candidates=[];
    function selectPhoto(item){
      pause();selectedPhoto=item;selectedAction=null;position(item.seconds,true);showReadout(item.job,null,'multiview-photo-detail');
      document.getElementById('multiview-photo-note').textContent='已按上游照片标注时间定位附近视频，同步误差未知；设备身份、读数与视频对象未关联，采集时钟依据见下方记录。';
    }
    // A nearby photo is a navigational hint, never an instrument/experiment link.
    try{
      const r=await fetch('upstream/snapshot.json');if(!r.ok)throw Error('照片接收记录不可用');
      const upstream=await r.json();if(upstream.mode!=='real_api')throw Error('照片来源未验证');
      candidates=clock.photoCandidates(data,upstream.readouts||[]);const photos=document.getElementById('multiview-photos');
      for(const [index,item] of candidates.entries()){
        const button=document.createElement('button');button.type='button';button.textContent=`约 ${item.seconds.toFixed(2)} s · 同机位照片 ${index+1} · ${recognitionReason(item.job)}`;
        button.addEventListener('click',()=>selectPhoto(item));photos.append(button);
      }
      if(!candidates.length)document.getElementById('multiview-photo-note').textContent='本次快照中没有同机位、落在该时间范围的照片记录。';
    }catch(e){document.getElementById('multiview-photo-note').textContent=e.message+'；原画与动作证据帧仍可查看。';}
    try{
      const target=clock.readLink(new URLSearchParams(location.search),snapshotHash,data.duration_seconds,actions,candidates);
      if(target?.kind==='photo')selectPhoto(target.item);else if(target?.kind==='action')selectAction(target.item);else if(target)position(target.time,true);
    }catch(e){linkStatus.textContent=e.message;}
  }catch(error){status.textContent=error.message+'；上方单视角分析可继续使用。';}
})();
