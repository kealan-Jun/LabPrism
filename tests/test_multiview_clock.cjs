const test=require('node:test'),assert=require('node:assert/strict');
const clock=require('../apps/viewer/multiview-clock.js');
test('uses piecewise recorded timing in both directions',()=>{
  const points=clock.validate([[0,2],[1,3],[3,4]]);
  assert.equal(clock.map(points,2),3.5);assert.equal(clock.map(points,3.5,1),2);
  assert.equal(clock.map(points,-1),null);assert.equal(clock.map(points,4),null);
  assert.equal(clock.map(points,0),2);assert.equal(clock.map(points,4,1),3);
});
test('rejects reversed and invalid clock knots',()=>{
  for(const p of [[],[[0,0],[0,1]],[[0,0],[1,-1]],[[0,0],[1,NaN]],[[0,0],[1,Infinity]]])assert.throws(()=>clock.validate(p));
});
test('nearby photos remain candidates and unknown camera/time cannot link',()=>{
  const data={global_origin_us:Date.parse('2026-09-21T09:54:00Z')*1000,duration_seconds:10,views:[{camera_id:'a'}]};
  const valid={job_id:'j',media_kind:'external_photo',camera_id:'a',captured_at:'2026-09-21T17:54:04+08:00',capture_time_basis:'nas_filename_local_time_not_hardware_verified',fields:[]};
  const candidates=clock.photoCandidates(data,[valid,{...valid,media_kind:'video_frame'},{...valid,camera_id:'unknown'},{...valid,captured_at:'2026-09-21T17:54:04'},{...valid,captured_at:'2026-09-21T09:55:00Z'}]);
  assert.equal(candidates.length,1);assert.equal(candidates[0].seconds,4);
  assert.equal(candidates[0].synchronization_error_ms,null);assert.equal(candidates[0].job.fields.length,0);
});
test('deep links require the exact received clock and source version',()=>{
  const {readLink}=require('../apps/viewer/multiview-clock.js');
  const action={id:'event-a',timestamp_seconds:4},photo={job:{job_id:'photo-a'},seconds:6};
  const link=s=>readLink(new URLSearchParams(s),'hash',10,[action],[photo]);
  assert.equal(link('clip=other'),null);
  assert.throws(()=>link('mv=wrong&mt=4'),/版本不匹配/);
  assert.throws(()=>link('mt=4'),/版本不匹配/);
  assert.throws(()=>link('mv=hash&mt=Infinity'),/超出/);
  assert.throws(()=>link('mv=hash&mt=11'),/超出/);
  assert.throws(()=>link('mv=hash&mp=unknown'),/不在/);
  assert.throws(()=>link('mv=hash&ma=event-a&mp=photo-a'),/冲突/);
  assert.deepEqual(link('mv=hash&mt=3.125'),{kind:'time',time:3.125});
  assert.deepEqual(link('mv=hash&mp=photo-a'),{kind:'photo',item:photo,time:6});
  assert.deepEqual(link('mv=hash&ma=event-a'),{kind:'action',item:action,time:4});
});
test('analysis links require the exact received bytes, source, camera and role',()=>{
  const {analysisVersions}=require('../apps/viewer/multiview-clock.js');
  const view={clip_sha256:'a'.repeat(64),source_sha256:'b'.repeat(64),camera_id:'cam-1',camera_role:'first_person'};
  const exact={...view,id:'baseline',title:'baseline'};
  const candidates=[exact,{...exact,id:'candidate'},{...exact,id:'resized',clip_sha256:'c'.repeat(64)},
    {...exact,id:'other-camera',camera_id:'cam-2'},{...exact,id:'other-source',source_sha256:'d'.repeat(64)},
    {...exact,id:'wrong-role',camera_role:'third_person'}];
  assert.deepEqual(analysisVersions(view,candidates).map(c=>c.id),['baseline','candidate']);
  assert.deepEqual(analysisVersions({...view,clip_sha256:null},candidates),[]);
});
test('return from analysis uses current media time and refuses unmatched or out-of-range views',()=>{
  const view={clip_sha256:'a'.repeat(64),source_sha256:'b'.repeat(64),camera_id:'cam',camera_role:'first_person',knots:[[0,1],[10,11]]};
  const clip={...view,id:'candidate',title:'candidate'};
  assert.equal(clock.analysisTime([view],clip,6),5);
  assert.equal(clock.analysisTime([view],clip,0),null);
  assert.equal(clock.analysisTime([view],{...clip,clip_sha256:'c'.repeat(64)},6),null);
  assert.equal(clock.analysisTime([view,view],clip,6),null);
  assert.equal(clock.analysisTime([view],clip,NaN),null);
});
