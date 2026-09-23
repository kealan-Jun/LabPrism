/* A read-only product story. All steps and clocks come from the producer bundle. */
(() => {
  'use strict';
  const Clock = typeof module !== 'undefined' ? require('../viewer/multiview-clock.js') : window.LabPrismClock;
  const finite = Number.isFinite;
  function validateStory(data) {
    const asset = value => typeof value === 'string' && /^[a-z0-9-]+\.(mp4|jpg|png|opus)$/.test(value);
    if (data?.schema_version !== 'labprism-record-story/1' || !Number.isSafeInteger(data.origin_us) || !finite(data.duration) || data.duration <= 0 || data.duration > 1800 || !Array.isArray(data.views) || data.views.length < 2 || data.views.length > 6) throw Error('记录与时间信息不完整。');
    const cameras = new Set(); const sources = new Set();
    data.views.forEach(view => {
      if (!view.camera_id || cameras.has(view.camera_id) || !/^[a-f0-9]{64}$/.test(view.source_sha256) || sources.has(view.source_sha256) || !['first_person','third_person'].includes(view.role) || !asset(view.video) || !asset(view.poster)) throw Error('机位来源未能核对。');
      cameras.add(view.camera_id); sources.add(view.source_sha256); Clock.validate(view.knots);
      if (Clock.map(view.knots, 0) === null || Clock.map(view.knots, data.duration) === null) throw Error('机位未覆盖共同时间段。');
    });
    if (!data.views.some(v => v.role === 'first_person') || !data.views.some(v => v.role === 'third_person')) throw Error('缺少第一／第三人称机位。');
    if (!Array.isArray(data.steps) || data.steps.length > 500) throw Error('步骤记录无效。');
    const ids = new Set();
    data.steps.forEach(step => {
      if (!step.id || ids.has(step.id) || ![step.start,step.end,step.evidence_time].every(finite) || step.start < 0 || step.end < step.start || step.end > data.duration || step.evidence_time < 0 || step.evidence_time > data.duration || !cameras.has(step.supporting_camera_id) || !asset(step.image) || !step.frame_id || !/^[a-f0-9]{64}$/.test(step.image_sha256)) throw Error('步骤与原始证据未能关联。');
      ids.add(step.id);
    });
    (data.readings || []).forEach(item => {
      if (!finite(item.time) || item.time < 0 || item.time > data.duration || !cameras.has(item.camera_id) || !asset(item.image)) throw Error('读数证据超出当前记录。');
    });
    if (data.audio && (!asset(data.audio.file) || !finite(data.audio.start))) throw Error('录音来源无效。');
    (data.audio?.sentences || []).forEach(s => {
      if (!Number.isSafeInteger(s.start_us) || !Number.isSafeInteger(s.end_us) || s.end_us < s.start_us || typeof s.text !== 'string' || !s.comment_id) throw Error('语音时间信息无效。');
    });
    return data;
  }
  function stepAt(steps, seconds) { return [...steps].reverse().find(s => seconds >= s.start && seconds <= s.end) || null; }
  function wallTime(origin, seconds) { return new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(origin/1000 + seconds*1000)); }
  function validateCatalog(catalog) {
    if (catalog?.schema_version !== 'labprism-story-catalog/1' || catalog.coverage !== 'curated_excerpts_not_full_day' || !/^\d{4}-\d{2}-\d{2}$/.test(catalog.date) || !Array.isArray(catalog.periods) || !catalog.periods.length || catalog.periods.length > 24) throw Error('工作时段索引无效。');
    const ids = new Set(); let end = -Infinity;
    catalog.periods.forEach(period => {
      if (!/^period-[a-z0-9-]+$/.test(period.id) || ids.has(period.id) || period.story !== `${period.id}/story.json` || !Number.isSafeInteger(period.origin_us) || !finite(period.duration) || period.duration <= 0 || period.duration > 1800 || period.origin_us < end || typeof period.title !== 'string') throw Error('时段来源、顺序或覆盖区间无效。');
      ids.add(period.id); end = period.origin_us + period.duration*1e6;
    });
    if (!ids.has(catalog.default_period)) throw Error('缺少默认时段。');
    return catalog;
  }
  function evidenceFor(data, step, seconds) {
    const start = step?.start ?? seconds, end = step?.end ?? seconds;
    const voices = (data.audio?.sentences || []).filter(s => (s.start_us-data.origin_us)/1e6 <= end && (s.end_us-data.origin_us)/1e6 >= start);
    // Filename times support nearby navigation, never step-level confirmation.
    const readings = (data.readings || []).filter(r => r.association === 'same_camera_and_synchronized_capture_time' && (!step || r.camera_id === step.supporting_camera_id) && r.time >= start && r.time <= end);
    return {voices, readings};
  }
  function valueText(reading) { return reading.values.map(v => `${v.value === null ? '—' : v.value}${v.value !== null ? v.unit || '' : ''}`).join(' / '); }
  if (typeof module !== 'undefined') module.exports = {validateStory, validateCatalog, stepAt, wallTime, evidenceFor, valueText};
  if (typeof document === 'undefined') return;
  const root = document.querySelector('[data-record-story]'); if (!root) return;
  const $ = selector => root.querySelector(selector);
  const make = (tag, cls, content) => { const node=document.createElement(tag); if(cls) node.className=cls; if(content!==undefined) node.textContent=content; return node; };
  const button = (cls, text, action) => { const node=make('button',cls,text);node.type='button';node.addEventListener('click',action);return node; };
  const stamp = seconds => wallTime(data.origin_us,seconds);
  const precise = seconds => `${stamp(seconds)}.${String(Math.floor((data.origin_us/1000 + seconds*1000)%1000)).padStart(3,'0')}`;
  const title = step => period.step_labels?.[data.steps.indexOf(step)] || step.action;
  const status=$('[data-story-status]'), play=$('[data-story-play]'), scrub=$('[data-story-scrub]'), sound=$('[data-story-audio]');
  let catalog, period, data, base='', views=[], audio=null, time=0, playing=false, raf, generation=0, loadGeneration=0, controller, contextKey='', readingIndex=0;
  function message(text) { status.textContent=text;status.hidden=!text; }
  function pause() { playing=false;views.forEach(v=>v.video.pause());audio?.pause();cancelAnimationFrame(raf);play.textContent='▶';play.setAttribute('aria-label','播放所有机位');play.setAttribute('aria-pressed','false'); }
  function jump(text, seconds, cls='jump-link') { return button(cls,text,()=>seek(seconds)); }
  function dispose() {
    generation++;pause();
    for(const {video} of views) {video.removeAttribute('src');video.load();}
    if(audio) {audio.removeAttribute('src');audio.load();audio.remove();}
    views=[];audio=null;data=null;contextKey='';
    for(const sel of ['[data-story-views]','[data-story-steps]','[data-step-track]','[data-voice-track]','[data-story-filmstrip]','[data-voice-list]','[data-context-voice]','[data-context-readings]','[data-story-chapters]','[data-step-original]','[data-story-provenance]']) $(sel).replaceChildren();
    $('[data-selected-title]').textContent='正在读取所选时段…';$('[data-selected-evidence]').textContent='';$('[data-evidence-jump]').hidden=true;$('[data-step-detail]').hidden=true;
    play.disabled=scrub.disabled=sound.disabled=true;sound.textContent='Sound off';sound.setAttribute('aria-pressed','false');sound.setAttribute('aria-label','开启原始录音');
    $('[data-story-time]').textContent='--:--:--';$('[data-story-count]').textContent='—';$('[data-story-range]').textContent='正在连接时段';
  }
  function update() {
    if(!data)return;
    $('[data-story-time]').textContent=stamp(time);scrub.value=time;scrub.setAttribute('aria-valuetext',precise(time));root.style.setProperty('--story-progress',`${time/data.duration*100}%`);
    const current=stepAt(data.steps,time);
    root.querySelectorAll('[data-step-id]').forEach(b=>b.setAttribute('aria-current',String(b.dataset.stepId===current?.id)));
    const context=evidenceFor(data,current,time);
    const key=[current?.id||'gap',...context.voices.map(v=>v.comment_id),...context.readings.map(r=>r.id)].join('|');
    if(key!==contextKey){contextKey=key;showContext(current,context);}
    $('[data-step-state]').textContent=current ? '当前步骤 · 模型候选' : '当前时刻暂无步骤 · 原始影像';
  }
  function showContext(step, context) {
    $('[data-selected-title]').textContent=step ? title(step) : 'Keep the context.';
    $('[data-selected-evidence]').textContent=step ? step.after : '这个时刻尚无已归档的步骤条目。画面与同期语音仍可沿时间回看。';
    $('[data-step-detail]').hidden=!step;$('[data-step-detail]').open=false;
    const original=$('[data-step-original]');original.replaceChildren();
    const frame=$('[data-evidence-jump]');frame.hidden=!step;
    if(step){
      for(const [label,text] of [['模型原文',step.action],['时间范围',`${precise(step.start)} — ${precise(step.end)}`],['之前',step.before],['之后',step.after],['可见依据',step.visible_evidence],['来源',`${step.supporting_camera_id} · ${step.frame_id}`],['理解状态',`${step.basis} / ${step.outcome} · 未经人工确认。上方短标题为界面摘要。`]]) original.append(make('dt','',label),make('dd','',text));
      frame.onclick=()=>seek(step.evidence_time);frame.setAttribute('aria-label',`定位步骤证据 ${stamp(step.evidence_time)}`);$('[data-evidence-image]').src=base+step.image;$('[data-evidence-image]').alt=step.visible_evidence;$('[data-evidence-time]').textContent=stamp(step.evidence_time);
      const row=[...root.querySelectorAll('.story-step')].find(b=>b.dataset.stepId===step.id), list=$('[data-story-steps]');
      if(row && list.scrollWidth>list.clientWidth+5){const x=row.offsetLeft;if(x<list.scrollLeft || x+row.offsetWidth>list.scrollLeft+list.clientWidth)list.scrollLeft=Math.max(0,x-16);}
      if(row && list.scrollHeight>list.clientHeight+5){const y=row.offsetTop;if(y<list.scrollTop || y+row.offsetHeight>list.scrollTop+list.clientHeight)list.scrollTop=Math.max(0,y-12);}
    }
    const voice=$('[data-context-voice]');voice.replaceChildren();
    if(context.voices.length){
      for(const sentence of context.voices){voice.append(make('blockquote','',`“${sentence.text}”`),jump(`${stamp((sentence.start_us-data.origin_us)/1e6)}  ↗ 定位录音`,(sentence.start_us-data.origin_us)/1e6));}
      voice.append(make('p','context-note','时间重叠的语音转录，可能含识别误差；不作为动作确认。'));
    }else{
      voice.append(make('p','context-empty',data.audio?.sentences?.length ? '该步骤时刻没有重叠语句。可在下方选择这段记录中的其他语音。' : '本时段保留原始录音，归档转录为空。开启 Sound 可随画面收听。'));
    }
    renderReadings(context.readings);
  }
  function renderReadings(linked=[]) {
    const target=$('[data-context-readings]');target.replaceChildren();
    const items=linked.length ? linked : data.readings || [];
    if(!items.length){target.append(make('p','context-empty','这一时段没有可关联的仪器读数。'));return;}
    const same=linked.length>0;const index=Math.min(readingIndex,items.length-1);const selected=items[index];
    target.append(make('p','context-empty',same ? '本步骤同机位的同步采集证据' : '本时段另有读数证据，未关联当前步骤。'));
    const values=make('div','reading-values');
    items.forEach((r,i)=>{const b=button('reading-value','',()=>{readingIndex=i;seek(r.time);renderReadings(linked);$('[data-context-readings]').querySelectorAll('.reading-value')[i]?.focus({preventScroll:true});});b.append(make('span','',valueText(r)),make('small','',`${items.length>1 ? `候选 ${i+1} · ` : ''}${r.values.every(v=>v.value===null)?'不可读':'待核验'}`));b.setAttribute('aria-pressed',String(i===index));values.append(b);});target.append(values);
    target.append(jump(`${stamp(selected.time)}  ↗ ${selected.association==='same_camera_and_synchronized_capture_time'?'定位采集时刻':'定位附近画面'}`,selected.time));
    const img=make('img','readout-source');img.src=base+selected.image;img.alt='FieldRecognition 原始读数图像';img.loading='lazy';
    const inspect=button('readout-inspect','',()=>openImage(selected.image));inspect.setAttribute('aria-label','放大读数原图');inspect.append(img);target.append(inspect);
    const discrepant=new Set(items.map(valueText)).size>1;
    target.append(make('p','context-note',`${discrepant?'同一标记时刻的多张照片有不同候选值，全部保留。':selected.values.every(v=>v.value===null)?'读数为空，保留原始证据。':'读数来自模型，需结合原图核验。'}${selected.association!=='same_camera_and_synchronized_capture_time'?'照片按文件名时间定位，未验证硬件同步。':''}`));
  }
  function openImage(file) {
    const dialog=make('dialog','story-image-dialog'), img=make('img');img.src=base+file;img.alt='原始读数证据';
    const close=button('','关闭 ×',()=>dialog.close());dialog.append(close,img);root.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});dialog.showModal();close.focus();
  }
  function seek(seconds) {
    if(!data || !finite(seconds))return;
    generation++;pause();time=Math.max(0,Math.min(data.duration,seconds));
    for(const {video,view} of views){const target=Clock.map(view.knots,time);if(target!==null && video.readyState)video.currentTime=target;}
    if(audio?.readyState)audio.currentTime=Math.max(0,time-data.audio.start);
    update();message('');
  }
  function tick() {
    if(!playing || !data)return;
    const current=Clock.map(views[0].view.knots,views[0].video.currentTime,1);if(current!==null)time=Math.min(data.duration,current);
    if(time>=data.duration-.05 || views[0].video.ended){pause();update();return;}
    for(const {video,view} of views.slice(1)){const target=Clock.map(view.knots,time);if(target===null){generation++;pause();message('这个时刻的机位影像不可用。');return;}if(!video.seeking && Math.abs(video.currentTime-target)>.12)video.currentTime=target;}
    if(audio && !audio.muted && !audio.seeking && Math.abs(audio.currentTime-(time-data.audio.start))>.15)audio.currentTime=Math.max(0,time-data.audio.start);
    update();raf=requestAnimationFrame(tick);
  }
  async function start() {
    if(!data)return;if(time>=data.duration-.1)seek(0);
    if(views.some(v=>v.video.readyState<2 || v.video.seeking)){message('正在对齐各机位，请稍后播放。');return;}
    const token=++generation, group=views.map(v=>v.video), voice=audio, offset=data.audio?.start;
    try{
      await Promise.all(group.map(v=>v.play()));if(token!==generation)return;
      if(voice && !voice.muted){voice.currentTime=Math.max(0,time-offset);await voice.play();}if(token!==generation)return;
      playing=true;play.textContent='Ⅱ';play.setAttribute('aria-label','暂停所有机位');play.setAttribute('aria-pressed','true');message('');tick();
    }catch{if(token===generation){pause();message('暂时无法播放全部机位，请重试。');}}
  }
  play.addEventListener('click',()=>playing?(generation++,pause()):start());scrub.addEventListener('input',()=>seek(Number(scrub.value)));
  sound.addEventListener('click',()=>{
    if(!audio)return;audio.muted=!audio.muted;sound.setAttribute('aria-pressed',String(!audio.muted));sound.textContent=audio.muted?'Sound off':'Sound on';sound.setAttribute('aria-label',audio.muted?'开启原始录音':'关闭原始录音');
    if(playing && !audio.muted){audio.currentTime=Math.max(0,time-data.audio.start);audio.play().catch(()=>message('录音暂不可用。'));}else audio.pause();
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden){generation++;pause();}});
  function overview() {
    const items=catalog.periods;const sum=items.reduce((n,p)=>n+p.duration,0);
    $('[data-day-date]').textContent=catalog.date.replaceAll('-','.');$('[data-day-summary]').textContent=`${items.length} 段选录 · ${Math.floor(sum/60)} 分 ${Math.round(sum%60)} 秒`;
    const hour=3600e6,start=Math.floor(items[0].origin_us/hour)*hour,end=Math.ceil((items.at(-1).origin_us+items.at(-1).duration*1e6)/hour)*hour;
    const ruler=$('[data-day-ruler]');for(let t=start;t<=end;t+=hour){const tick=make('span','day-tick',wallTime(t,0).slice(0,5));tick.style.left=`${(t-start)/(end-start)*100}%`;ruler.append(tick);}
    for(const [i,item] of items.entries()){
      const mark=button('day-period-mark','',()=>activate(item));mark.style.left=`${(item.origin_us-start)/(end-start)*100}%`;mark.style.width=`${item.duration*1e6/(end-start)*100}%`;mark.dataset.periodId=item.id;mark.setAttribute('aria-label',`定位时段 ${wallTime(item.origin_us,0)}`);ruler.append(mark);
      const card=button('period-card','',()=>activate(item));card.dataset.periodId=item.id;card.append(make('time','',wallTime(item.origin_us,0).slice(0,5)));
      const copy=make('span');copy.append(make('strong','',item.title),make('small','',`${item.steps} 步骤 · ${item.views} 机位${item.voices ? ` · ${item.voices} 条语音` : ' · 原始录音'}`));card.append(copy,make('b','','↗'));$('[data-period-list]').append(card);
      if(i){const gap=(item.origin_us-items[i-1].origin_us)/1e6-items[i-1].duration;card.setAttribute('aria-description',`与上一选段相隔 ${Math.round(gap/60)} 分钟，期间记录未纳入展示。`);}
    }
    const note=$('.day-note');note.style.display='block';
  }
  function renderViews(token) {
    views=data.views.map((view,i)=>{
      const figure=make('figure',`story-view ${i===0?'is-primary':''}`),video=make('video');video.muted=true;video.playsInline=true;video.preload='metadata';video.poster=base+view.poster;video.setAttribute('aria-label',`${view.role==='first_person'?'第一人称':'第三人称'} ${view.camera_id}`);
      const caption=make('figcaption');caption.append(make('span','',`${String(i+1).padStart(2,'0')} / ${view.role==='first_person'?'FIRST PERSON':'THIRD PERSON'}`));
      const focus=button('view-focus','⤢',()=>{root.querySelectorAll('.story-view').forEach(f=>f.classList.remove('is-primary'));root.querySelectorAll('.view-focus').forEach(b=>b.setAttribute('aria-pressed','false'));figure.classList.add('is-primary');focus.setAttribute('aria-pressed','true');});focus.setAttribute('aria-label',`放大${i+1}号机位`);focus.setAttribute('aria-pressed',String(i===0));caption.append(focus);figure.append(video,caption);$('[data-story-views]').append(figure);
      video.addEventListener('loadedmetadata',()=>{if(token!==loadGeneration || !data)return;const target=Clock.map(view.knots,time);if(target!==null)video.currentTime=target;});
      video.addEventListener('error',()=>{if(token!==loadGeneration)return;generation++;pause();play.disabled=true;message('一个机位暂不可用，重新选择此时段可重试。');});
      video.addEventListener('waiting',()=>{if(token===loadGeneration && playing){generation++;pause();message('影像缓冲中，所有机位已暂停。');}});
      video.addEventListener('seeked',()=>{if(token===loadGeneration && data && views.length===data.views.length && views.every(v=>v.video.readyState>=2&&!v.video.seeking))message('');});
      video.src=base+view.video;return {video,view};
    });
  }
  function renderSteps() {
    data.steps.forEach((step,i)=>{
      const row=button('story-step','',()=>seek(step.start));row.dataset.stepId=step.id;
      const meta=make('span','step-meta');meta.append(make('time','',`${precise(step.start)}–${precise(step.end).slice(6)}`),make('i','',step.outcome==='visible_change'?'可见变化':'待核验'));
      row.append(make('small','',String(i+1).padStart(2,'0')),make('strong','',title(step)),meta);$('[data-story-steps]').append(row);
      const seg=make('span','step-segment');seg.setAttribute('aria-hidden','true');seg.style.left=`${step.start/data.duration*100}%`;seg.style.width=`${Math.max(.15,(step.end-step.start)/data.duration*100)}%`;seg.dataset.stepId=step.id;seg.setAttribute('aria-label',`步骤 ${i+1}：${title(step)}`);$('[data-step-track]').append(seg);
    });
    const featured=period.featured_steps ? data.steps.filter(s=>period.featured_steps.includes(s.id)) : data.steps.slice(0,6);
    featured.forEach(step=>{const b=jump('',step.evidence_time,'story-moment');b.dataset.stepId=step.id;const img=make('img');img.src=base+step.image;img.alt=step.visible_evidence;img.loading='lazy';const cap=make('span','moment-caption');cap.append(make('time','',stamp(step.evidence_time)),make('span','',title(step)));b.append(img,cap);$('[data-story-filmstrip]').append(b);});
  }
  function renderAudio() {
    const sentences=data.audio?.sentences || [];const list=$('[data-voice-list]');$('[data-voice-count]').textContent=sentences.length;
    for(const sentence of sentences){const s=(sentence.start_us-data.origin_us)/1e6,e=(sentence.end_us-data.origin_us)/1e6;if(e<0 || s>data.duration)continue;
      const line=jump('',Math.max(0,s),'voice-line');line.append(make('time','',stamp(s)),make('span','',sentence.text));list.append(line);
      const seg=jump('',Math.max(0,s),'voice-segment');seg.style.left=`${Math.max(0,s)/data.duration*100}%`;seg.style.width=`${Math.max(.15,(Math.min(e,data.duration)-Math.max(0,s))/data.duration*100)}%`;seg.setAttribute('aria-label',`语音 ${stamp(s)} ${sentence.text}`);$('[data-voice-track]').append(seg);
    }
    if(data.audio){audio=new Audio(base+data.audio.file);audio.preload='metadata';audio.muted=true;audio.hidden=true;audio.setAttribute('aria-label','VisionCortex 原始录音');root.append(audio);sound.disabled=false;}
    const chapters=$('[data-story-chapters]');
    if(sentences.length)chapters.append(jump(`同期语音 ${sentences.length} ↗`,Math.max(0,(sentences.find(s=>/加载枪头/.test(s.text))||sentences[0]).start_us-data.origin_us)/1e6));
    if(data.readings?.length)chapters.append(jump(`仪器证据 ${data.readings.length} ↗`,data.readings[0].time));
  }
  function provenance() {
    const node=$('[data-story-provenance]');node.append(make('p','',`${data.date} · ${stamp(0)}–${stamp(data.duration)}。${data.views.length} 个独立机位按采集时钟映射联动；独立同步误差尚未测得。当前展示为选段，不代表全天完整覆盖。`));
    node.append(make('p','',`步骤来自 VisionCortex 已保存的模型结果（${data.understanding.status}），由第一人称证据帧支持，未作人工确认。本片段步骤输入为 ${data.understanding.content_sources.join(' / ')}；同期录音以时间重叠提供参照，不能视为已参与步骤推理。简短操作名是界面摘要，原文和前后状态保留在展开项。`));
    node.append(make('p','',`仪器证据由 FieldRecognition 提供。照片时间精度、空值和不同候选值均保留；文件名时间只用于查找附近画面，不确认物理同步或步骤因果。完整记录管理与分析由 VisionCortex 承载。`));
  }
  async function activate(item) {
    const token=++loadGeneration;controller?.abort();controller=new AbortController();dispose();period=item;readingIndex=0;
    root.querySelectorAll('[data-period-id]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.periodId===item.id)));$('[data-period-title]').textContent=item.title;
    $('.story-console').setAttribute('aria-busy','true');message('正在读取真实多机位记录…');
    try{
      const response=await fetch(`record-story/${item.story}`,{signal:controller.signal});if(!response.ok)throw Error('该时段暂不可用，请重新选择。');
      const story=validateStory(await response.json());if(token!==loadGeneration)return;
      if(story.origin_us!==item.origin_us || story.duration!==item.duration || story.steps.length!==item.steps || story.views.length!==item.views)throw Error('时段索引与来源不一致。');
      data=story;base=`record-story/${item.id}/`;time=0;
      $('[data-story-range]').textContent=`${stamp(0)} — ${stamp(data.duration)}`;$('[data-story-count]').textContent=String(data.steps.length).padStart(2,'0');$('[data-track-start]').textContent=stamp(0);$('[data-track-end]').textContent=stamp(data.duration);scrub.max=data.duration;scrub.disabled=false;
      renderViews(token);renderSteps();renderAudio();provenance();play.disabled=false;
      const initial=data.steps.find(s=>s.id===item.default_step)||data.steps[0];seek(initial?.evidence_time||0);$('.story-console').setAttribute('aria-busy','false');
    }catch(error){if(token!==loadGeneration || error.name==='AbortError')return;play.disabled=scrub.disabled=true;$('.story-console').setAttribute('aria-busy','false');message(error.message||'记录加载失败。');}
  }
  async function load() {
    try{const response=await fetch('record-story/catalog.json');if(!response.ok)throw Error('时段索引暂不可用。');catalog=validateCatalog(await response.json());overview();await activate(catalog.periods.find(p=>p.id===catalog.default_period));}
    catch(error){$('.story-console').setAttribute('aria-busy','false');message(error.message||'记录加载失败。');}
  }
  load();
})();
