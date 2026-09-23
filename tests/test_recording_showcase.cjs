const test = require('node:test');
const assert = require('node:assert/strict');
const {formatTime,verifyRecording} = require('../apps/website/recording-showcase.js');
const clip={id:'video-generic-display',clip_sha256:'a'.repeat(64),source_sha256:'b'.repeat(64),video:'demo-data/video-generic-display/clip.mp4'};
const index={source:{clip_sha256:clip.clip_sha256,source_sha256:clip.source_sha256},video:{duration_ms:152033}};
test('record replay requires matching received source and clip hashes',()=>{
 assert.equal(verifyRecording({clips:[clip]},index),clip);
 for(const field of ['clip_sha256','source_sha256']) {
  assert.throws(()=>verifyRecording({clips:[clip]},{...index,source:{...index.source,[field]:'c'.repeat(64)}}));
  assert.throws(()=>verifyRecording({clips:[{...clip,[field]:undefined}]},{...index,source:{...index.source,[field]:undefined}}));
 }
});
test('record replay rejects missing clips, unknown duration and external video paths',()=>{
 assert.throws(()=>verifyRecording({clips:[]},index));
 for(const duration_ms of [0,-1,null,NaN]) assert.throws(()=>verifyRecording({clips:[clip]},{...index,video:{duration_ms}}));
 for(const video of ['https://example.com/private.mp4','../clip.mp4','demo-data/x/../clip.mp4']) assert.throws(()=>verifyRecording({clips:[{...clip,video}]},index));
});
test('elapsed timestamps remain inside the clip time domain',()=>{
 assert.equal(formatTime(80.9),'01:20'); assert.equal(formatTime(152.033),'02:32'); assert.equal(formatTime(-1),'00:00');assert.equal(formatTime(NaN),'00:00');
});
