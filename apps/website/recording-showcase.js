/* Read-only, source-checked playback. No uploads, jobs, analysis API or synthetic events. */
(() => {
  'use strict';
  const CLIP_ID = 'video-generic-display';
  function formatTime(seconds) {
    const time = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
    return `${String(Math.floor(time / 60)).padStart(2, '0')}:${String(time % 60).padStart(2, '0')}`;
  }
  function verifyRecording(catalog, index) {
    const clip = catalog?.clips?.find(item => item.id === CLIP_ID);
    if (!clip || !/^[a-f0-9]{64}$/.test(clip.clip_sha256 || '') ||
        !/^[a-f0-9]{64}$/.test(clip.source_sha256 || '') ||
        clip.clip_sha256 !== index?.source?.clip_sha256 ||
        clip.source_sha256 !== index?.source?.source_sha256 ||
        !Number.isFinite(index?.video?.duration_ms) || index.video.duration_ms <= 0 ||
        !/^demo-data\/[a-z0-9-]+\/clip\.mp4$/.test(clip.video)) {
      throw Error('记录来源未能核对，暂不播放。');
    }
    return clip;
  }
  if (typeof module !== 'undefined') module.exports = {formatTime, verifyRecording};
  if (typeof document === 'undefined') return;
  const root = document.querySelector('[data-recording]');
  if (!root) return;
  const video = root.querySelector('[data-record-video]');
  const slider = root.querySelector('[data-record-scrub]');
  const status = root.querySelector('[data-record-status]');
  const output = root.querySelector('[data-record-time]');
  const buttons = [...root.querySelectorAll('[data-record-seek]')];
  let pendingTime = 5;
  buttons.forEach(button => {button.disabled = true;});
  function update() {
    const current = video.currentTime;
    output.textContent = formatTime(current);
    slider.value = String(current);
    slider.style.setProperty('--progress',`${video.duration ? current / video.duration * 100 : 0}%`);
    slider.setAttribute('aria-valuetext',`片段内 ${formatTime(current)}`);
    const thumbs = buttons.filter(button => button.querySelector('[data-record-thumb]'));
    const selected = thumbs.filter(button => Number(button.dataset.recordSeek) <= current).at(-1);
    thumbs.forEach(button => button.setAttribute('aria-pressed',String(button === selected)));
  }
  function seek(seconds) {
    if (!Number.isFinite(seconds)) return;
    pendingTime = Math.max(0, Math.min(seconds, Number.isFinite(video.duration) ? video.duration : seconds));
    if (video.readyState > 0) {video.currentTime = pendingTime; update();}
  }
  video.addEventListener('loadedmetadata', () => {
    slider.max = String(video.duration); slider.disabled = false;
    root.querySelector('[data-record-duration]').textContent = formatTime(video.duration);
    buttons.forEach(button => {button.disabled = Number(button.dataset.recordSeek) > video.duration;});
    seek(pendingTime);
  });
  video.addEventListener('loadeddata', () => {status.hidden = true;});
  video.addEventListener('timeupdate', update);
  video.addEventListener('seeked', update);
  video.addEventListener('error', () => {
    status.hidden = false; status.textContent = '这段记录暂时无法播放，请稍后重试。';
    slider.disabled = true; buttons.forEach(button => {button.disabled = true;});
  });
  slider.addEventListener('input', () => seek(Number(slider.value)));
  buttons.forEach(button => button.addEventListener('click', () => seek(Number(button.dataset.recordSeek))));
  const readJSON = async path => {const response = await fetch(path); if (!response.ok) throw Error('真实记录暂不可用。'); return response.json();};
  Promise.all([readJSON('demo-data/catalog.json'),readJSON(`demo-data/${CLIP_ID}/index.json`)]).then(([catalog,index]) => {
    const clip = verifyRecording(catalog,index);
    const date = /^nas-capture-day-(\d{4})(\d{2})(\d{2})$/.exec(index.source.source_group || '');
    root.querySelector('[data-record-date]').textContent = date ? `RECORDING / ${date[1]}.${date[2]}.${date[3]}` : 'SOURCE RECORDING';
    video.src = clip.video;
    root.querySelectorAll('[data-record-thumb]').forEach(thumb => {
      const at = Number(thumb.dataset.recordThumb);
      thumb.addEventListener('loadedmetadata', () => {thumb.currentTime = Math.min(at, thumb.duration);},{once:true});
      thumb.src = `${clip.video}#t=${at}`;
    });
  }).catch(error => {status.hidden = false; status.textContent = error.message;});
})();
