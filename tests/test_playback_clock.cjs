const test=require('node:test'),assert=require('node:assert/strict');
const PlaybackFrameClock=require('../apps/viewer/playback-clock.js');
function setup(){
  const callbacks=[],cancelled=[],seen=[];
  const video={seeking:false,requestVideoFrameCallback(fn){callbacks.push(fn);return callbacks.length;},cancelVideoFrameCallback(id){cancelled.push(id);}};
  return {callbacks,cancelled,seen,video,clock:new PlaybackFrameClock(video,t=>seen.push(t))};
}
test('late frames before seek or source replacement cannot overwrite current presentation',()=>{
  const {callbacks,cancelled,seen,clock}=setup();
  clock.watch();clock.invalidate();clock.watch();
  callbacks[0](0,{mediaTime:45.2});
  assert.deepEqual(seen,[]);assert.deepEqual(cancelled,[1]);assert.equal(callbacks.length,2);
  callbacks[1](0,{mediaTime:45});assert.deepEqual(seen,[45]);assert.equal(callbacks.length,3);
  clock.invalidate();clock.watch();callbacks[2](0,{mediaTime:80});
  assert.deepEqual(seen,[45]);callbacks[3](0,{mediaTime:0});assert.deepEqual(seen,[45,0]);
});
test('watch has one subscription and withholds pending seek frames',()=>{
  const {callbacks,seen,video,clock}=setup();
  clock.watch();clock.watch();assert.equal(callbacks.length,1);
  video.seeking=true;callbacks[0](0,{mediaTime:40});assert.deepEqual(seen,[]);
  video.seeking=false;callbacks[1](0,{mediaTime:NaN});assert.deepEqual(seen,[]);
  callbacks[2](0,{mediaTime:50});assert.deepEqual(seen,[50]);
});
