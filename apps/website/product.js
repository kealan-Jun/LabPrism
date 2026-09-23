/* Product presentation consumes only prepared real observations and the runtime catalog. */
(() => {
  'use strict';
  function groupRecords(clips) {
    const groups = new Map();
    for (const clip of clips) {
      // The same recording may contain distinct clips. Only identical input bytes group together.
      const key = `${clip.clip_sha256}|${clip.camera_id}|${clip.camera_role}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(clip);
    }
    return Array.from(groups.values()).map(versions => ({versions, latest: versions.at(-1)}));
  }
  function validPoint(p, score, threshold) {
    return Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]) &&
      Number.isFinite(score) && Number.isFinite(threshold) && score >= threshold;
  }
  if (typeof module !== 'undefined') module.exports = {groupRecords, validPoint};
  if (typeof document === 'undefined') return;
  const ns = 'http://www.w3.org/2000/svg';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const copy = {
    perception: ['PERCEPTION', 'Objects, in context.', '识别器材在画面中的位置，以检测框提示模型提取实例轮廓。框与轮廓分层查看，回到原画检查透明、反光和遮挡区域。', '实际候选输出；仍有误检与漏检，分割轮廓不代表独立语义理解。'],
    motion: ['MOTION', 'Follow the motion.', '把检测到的手、可用关节与轨迹放回同一时刻。低分关键点保持隐藏，未检出的手不会由界面补画。', '手姿仍有错位和缺失。二维靠近不等于物理接触，也不自动代表某个实验步骤。'],
    readout: ['READOUT', 'A reading. And its source.', '通用显示窗定位与文字识别连接到原始裁剪。查看识别原文、候选精读与冲突，再回到采样时刻核对。', '此帧实际候选存在 267 / 251 识别冲突；设备、字段和单位保持未知。未晋级为正式读数。'],
    perspective: ['PERSPECTIVE', 'Another point of view.', '查看第一人称与第三人称原画，复用采集来源的时间映射，按实际可用时间查阅画面。', '多机位精确同步与跨视角身份尚未通过验证；未将相似画面自动认作同一物体。']
  };
  const catalogPromise = fetch('demo-data/catalog.json').then(r => {
    if (!r.ok) throw Error('本机片段目录暂不可用');
    return r.json();
  });
  const showcasePromise = fetch('showcase/showcase.json').then(r => {
    if (!r.ok) throw Error('展示画面暂未准备，请进入工作台查看已有记录。');
    return r.json();
  });
  // Handle both independent loads immediately, including on pages that only need one.
  catalogPromise.catch(() => {});
  showcasePromise.catch(() => {});

  function shape(svg, type, attributes, text) {
    const node = document.createElementNS(ns, type);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    svg.append(node); return node;
  }
  function draw(scene, svg) {
    svg.replaceChildren(); svg.setAttribute('viewBox', `0 0 ${scene.width} ${scene.height}`);
    const scale = scene.width / 960;
    const box = (coordinates, color, label) => {
      const [x, y, right, bottom] = coordinates;
      shape(svg, 'rect', {x, y, width:right-x, height:bottom-y, fill:'none', stroke:color, 'stroke-width':1.4*scale});
      if (label) {
        const size = 11*scale; const top = Math.max(size+4, y);
        shape(svg, 'rect', {x, y:top-size-5, width:Math.min(scene.width-x, label.length*size+10), height:size+5, fill:'#142c26dd', rx:2});
        shape(svg, 'text', {x:x+4, y:top-3, fill:color, 'font-size':size, 'font-family':'system-ui,sans-serif'}, label);
      }
    };
    if (scene.layers.includes('masks')) for (const obj of scene.frame.objects || []) {
      for (const contour of obj.mask_contours || []) shape(svg, 'polygon', {points:contour.map(p => p.join(',')).join(' '), fill:'#ccec9a28', stroke:'#d3ed8c', 'stroke-width':scale});
    }
    if (scene.layers.includes('boxes')) for (const obj of scene.frame.objects || []) box(obj.box, '#d3ed8c', obj.display_name || obj.label);
    if (scene.layers.includes('hands')) for (const hand of scene.frame.hands || []) {
      const points = hand.points || [], scores = hand.point_scores || [];
      const edges = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
      const valid = i => validPoint(points[i], scores[i], hand.keypoint_threshold);
      for (const [a,b] of edges) if (valid(a) && valid(b)) shape(svg, 'line', {x1:points[a][0], y1:points[a][1], x2:points[b][0], y2:points[b][1], stroke:'#d3ed8c', 'stroke-width':2*scale});
      points.forEach((p,i) => { if (valid(i)) shape(svg, 'circle', {cx:p[0],cy:p[1],r:2.5*scale,fill:'#f4fff0',stroke:'#356240','stroke-width':scale}); });
    }
    if (scene.layers.includes('ocr')) for (const observation of scene.frame.ocr_observations || []) {
      if (observation.mode !== 'automatic') continue;
      if (observation.region.basis !== 'whole_image') box(observation.region.xyxy, '#d3ed8c', '显示窗候选');
      for (const line of observation.lines || []) if (line.quad) shape(svg, 'polygon', {points:line.quad.map(p => p.join(',')).join(' '), fill:'#d3ed8c22', stroke:'#e8ffb6', 'stroke-width':scale});
    }
  }

  async function mountObservation(root, name) {
    const generation = String((Number(root.dataset.generation) || 0) + 1);
    root.dataset.generation = generation;
    const status = $('[data-scene-status]',root), img = $('[data-scene-image]',root), svg = $('[data-scene-overlay]',root), video = $('video',root);
    video.pause(); video.hidden = true; video.removeAttribute('src'); video.load();
    img.hidden = false; img.removeAttribute('src'); svg.replaceChildren(); svg.removeAttribute('hidden');
    status.hidden = false; status.textContent = '正在加载实验画面…';
    const toggle = $('[data-toggle-overlay]',root), play = $('[data-play-original]',root);
    const compare = $('[data-compare]',root), compareControl = $('[data-comparison-control]',root);
    const guide = $('[data-comparison-guide]',root), slider = compareControl?.querySelector('input');
    const resetComparison = () => {
      svg.style.clipPath = '';
      if (compare) { compare.setAttribute('aria-pressed','false'); compare.textContent='拖动对照'; }
      if (compareControl) compareControl.hidden = true;
      if (guide) guide.hidden = true;
    };
    resetComparison();
    if (compare) compare.disabled = true;
    let layerControls = $('[data-layer-controls]',root);
    if (!layerControls) {
      layerControls=document.createElement('div');layerControls.dataset.layerControls='';layerControls.className='observation-layers';
      $('.observation-top',root).after(layerControls);
    }
    layerControls.replaceChildren();
    toggle.disabled = play.disabled = true; toggle.textContent = '隐藏预测'; toggle.setAttribute('aria-pressed','true'); play.textContent='播放原片';
    try {
      const data = await showcasePromise;
      if (root.dataset.generation !== generation) return;
      const scene = data.scenes.find(s => s.id === name); if (!scene) throw Error('该能力的展示帧暂不可用');
      root.dataset.scene = name;
      img.alt = `${scene.description}，${(scene.timestamp_ms/1000).toFixed(2)} 秒的原始画面`;
      img.onload = () => { if(root.dataset.generation === generation) status.hidden = true; };
      img.onerror = () => {status.hidden=false;status.textContent='展示帧加载失败，请通过完整分析查看原片。';};
      img.src = `showcase/${scene.image}`;
      const enabledLayers = new Set(scene.layers.includes('masks') ? ['masks'] : scene.layers);
      const layerNames = {boxes:'器材框',masks:'实例轮廓',hands:'手部关键点',ocr:'显示窗与文字'};
      for (const layer of scene.layers) {
        const button=document.createElement('button');button.type='button';button.textContent=layerNames[layer];
        button.setAttribute('aria-pressed',String(enabledLayers.has(layer)));
        button.onclick=()=>{
          if(enabledLayers.has(layer))enabledLayers.delete(layer);else enabledLayers.add(layer);
          button.setAttribute('aria-pressed',String(enabledLayers.has(layer)));draw({...scene,layers:[...enabledLayers]},svg);
        };
        layerControls.append(button);
      }
      draw({...scene,layers:[...enabledLayers]},svg);
      $('[data-scene-title]',root).textContent = scene.title;
      $('.observation-type',root).textContent = '实际候选输出';
      $('[data-scene-caption]',root).textContent = `${scene.description} · ${(scene.timestamp_ms/1000).toFixed(2)} s`;
      const link = $('[data-scene-link]',root);
      if (link) link.href = `technology.html#${encodeURIComponent(name)}`;
      toggle.disabled = play.disabled = false;
      if (compare) {
        compare.disabled = false;
        const position = () => {
          svg.style.clipPath = `inset(0 0 0 ${slider.value}%)`;
          guide.style.left = `${slider.value}%`;
          slider.setAttribute('aria-valuetext',`左侧原画 ${slider.value}%，右侧预测 ${100-Number(slider.value)}%`);
        };
        slider.oninput = position;
        compare.onclick = () => {
          if (compare.getAttribute('aria-pressed') === 'true') { resetComparison(); return; }
          svg.removeAttribute('hidden'); toggle.setAttribute('aria-pressed','true'); toggle.textContent='隐藏预测';
          $('.observation-type',root).textContent='实际候选输出';
          compare.setAttribute('aria-pressed','true'); compare.textContent='结束对照';
          compareControl.hidden = guide.hidden = false; slider.value='50'; position();
        };
      }
      toggle.onclick = () => {
        resetComparison();
        const hidden = !svg.hasAttribute('hidden'); svg.toggleAttribute('hidden', hidden);
        toggle.setAttribute('aria-pressed',String(!hidden));
        toggle.textContent = hidden ? '显示预测' : '隐藏预测';
        $('.observation-type',root).textContent = hidden ? '实验原画' : '实际候选输出';
      };
      play.onclick = async () => {
        if (!video.hidden) {
          video.pause(); video.hidden=true;img.hidden=false;svg.toggleAttribute('hidden',toggle.getAttribute('aria-pressed')!=='true');toggle.disabled=false;play.textContent='播放原片';status.hidden=true;
          $$('button',layerControls).forEach(b=>{b.disabled=false;});
          if (compare) compare.disabled=false;
          $('.observation-type',root).textContent=svg.hasAttribute('hidden')?'实验原画':'实际候选输出';return;
        }
        play.disabled=true;
        try {
          const catalog = await catalogPromise;
          if(root.dataset.generation!==generation)return;
          const clip=catalog.clips.find(c=>c.id===scene.clip_id);if(!clip)throw Error('原片暂不可用');
          resetComparison(); if (compare) compare.disabled=true;
          video.onloadedmetadata=()=>{video.currentTime=scene.timestamp_ms/1000;};
          video.onerror=()=>{status.hidden=false;status.textContent='原片加载失败，可返回分析帧或打开完整分析。';};
          video.src=clip.video;video.hidden=false;img.hidden=true;svg.setAttribute('hidden','');toggle.disabled=true;play.textContent='返回分析帧';
          $$('button',layerControls).forEach(b=>{b.disabled=true;});
          $('.observation-type',root).textContent='原片播放 · 无预测叠加';
          await video.play();
        } catch(error) {if(root.dataset.generation===generation){status.hidden=false;status.textContent='未能自动播放，请使用视频播放控件或打开完整分析。';}}
        finally{if(root.dataset.generation===generation)play.disabled=false;}
      };
    } catch(error) {status.textContent=error.message;}
  }
  $$('.observation').forEach(root=>mountObservation(root,root.dataset.scene));
  const heroScenes = $$('[data-hero-scene]');
  heroScenes.forEach(button => button.addEventListener('click', () => {
    heroScenes.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    mountObservation($('.hero-observation'), button.dataset.heroScene);
  }));
  showcasePromise.then(data => {
    $$('[data-scene-photo]').forEach(root => {
      const scene=data.scenes.find(s=>s.id===root.dataset.scenePhoto); if(!scene)return;
      const img=document.createElement('img');img.alt=scene.description+' · 原始画面';img.loading='lazy';img.src=`showcase/${scene.image}`;
      img.onerror=()=>{root.textContent='画面暂不可用';};root.replaceChildren(img);
    });
  }).catch(()=>{$$('[data-scene-photo]').forEach(root=>{root.textContent='画面暂未准备';});});

  const tabs=$$('[data-capability]');
  function activate(tab,focus=false){
    tabs.forEach(t=>{const active=t===tab;t.setAttribute('aria-selected',String(active));t.tabIndex=active?0:-1;});
    const name=tab.dataset.capability, words=copy[name];
    ['kicker','title','description','boundary'].forEach((id,i)=>{$(`#capability-${id}`).textContent=words[i];});
    $('#capability-panel').setAttribute('aria-labelledby',tab.id);
    mountObservation($('.observation',$('#capability-panel')),name);
    if(focus)tab.focus();
  }
  tabs.forEach((tab,i)=>{
    tab.onclick=()=>activate(tab);
    tab.onkeydown=event=>{
      let next;if(event.key==='ArrowRight'||event.key==='ArrowDown')next=(i+1)%tabs.length;if(event.key==='ArrowLeft'||event.key==='ArrowUp')next=(i+tabs.length-1)%tabs.length;if(event.key==='Home')next=0;if(event.key==='End')next=tabs.length-1;
      if(next!==undefined){event.preventDefault();activate(tabs[next],true);}
    };
  });
  const deepLink=()=>{const tab=tabs.find(t=>t.dataset.capability===location.hash.slice(1));if(tab)activate(tab);};
  deepLink();window.addEventListener('hashchange',deepLink);

  if($('#record-list'))catalogPromise.then(catalog=>{
    const groups=groupRecords(catalog.clips);
    const render=()=>{
      const search=$('#record-search').value.trim().toLocaleLowerCase();
      const visible=groups.filter(g=>g.versions.some(c=>`${c.title} ${c.camera_id}`.toLocaleLowerCase().includes(search)));
      $('#record-list').replaceChildren();$('#library-status').textContent=`${visible.length} 条片段记录 · ${catalog.clips.length} 个分析版本`;
      for(const group of visible){
        const c=group.latest,a=document.createElement('a');a.className='record-row';a.href=`demo.html?clip=${encodeURIComponent(c.id)}`;
        const div=document.createElement('div'),title=document.createElement('h3'),meta=document.createElement('p'),action=document.createElement('span');
        title.textContent=c.title;meta.textContent=`${c.camera_role==='first_person'?'第一人称':c.camera_role==='third_person'?'第三人称':'视角待确认'} · ${c.camera_id||'机位待确认'} · ${group.versions.length} 个分析版本`;action.textContent='查看分析 ↗';div.append(title,meta);a.append(div,action);$('#record-list').append(a);
      }
      if(!visible.length)$('#library-status').textContent='没有匹配的记录，请尝试其他名称或机位。';
    };
    $('#record-search').addEventListener('input',render);render();
  }).catch(error=>{$('#library-status').textContent=error.message+'。请检查本地预览素材是否已准备。';});
})();
