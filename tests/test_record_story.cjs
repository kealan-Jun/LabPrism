const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateStory,stepAt,wallTime} = require('../apps/website/multiview-story.js');
const Clock = require('../apps/viewer/multiview-clock.js');
function fixture() { return {schema_version:'labprism-record-story/1',origin_us:1789644916065492,duration:10,
 views:[{camera_id:'wearer',role:'first_person',source_sha256:'a'.repeat(64),video:'view-0.mp4',poster:'view-0.jpg',knots:[[0,.027],[10,10.037]]},{camera_id:'bench',role:'third_person',source_sha256:'b'.repeat(64),video:'view-1.mp4',poster:'view-1.jpg',knots:[[0,.41],[10,10.42]]}],
 steps:[{id:'step-0',start:2,end:4,evidence_time:3,supporting_camera_id:'wearer',image:'step-0.jpg',frame_id:'source-frame',image_sha256:'c'.repeat(64)}],readings:[]}; }
test('camera offsets and clock drift are retained when seeking a step',()=>{const story=validateStory(fixture());const times=story.views.map(v=>Clock.map(v.knots,3));assert.ok(Math.abs(times[0]-3.03)<1e-9);assert.ok(Math.abs(times[1]-3.413)<1e-9);assert.ok(Math.abs(Clock.map(story.views[1].knots,times[1],1)-3)<1e-9);});
test('rejects repeated footage, unknown roles, missing coverage and unsafe sources',()=>{for(const edit of [s=>s.views[1].source_sha256=s.views[0].source_sha256,s=>s.views[1].role='unknown',s=>s.views[1].knots=[[1,1],[10,10]],s=>s.views[1].video='../private.mp4',s=>s.views[1].knots=[[0,0],[0,1]]]){let s=fixture();edit(s);assert.throws(()=>validateStory(s));}});
test('rejects step and readout evidence from another camera or time',()=>{for(const edit of [s=>s.steps[0].end=11,s=>s.steps[0].supporting_camera_id='other',s=>s.steps[0].image='https://example.com/fake.jpg',s=>s.steps[0].frame_id=null,s=>s.readings=[{time:20,camera_id:'wearer',image:'readout.png'}]]){let s=fixture();edit(s);assert.throws(()=>validateStory(s));}});
test('gaps remain gaps, including single-frame observations',()=>{let s=fixture();assert.equal(stepAt(s.steps,1),null);assert.equal(stepAt(s.steps,3).id,'step-0');assert.equal(stepAt(s.steps,5),null);assert.equal(stepAt([{start:5,end:5}],5).start,5);assert.equal(Clock.map(s.views[0].knots,11),null);assert.equal(wallTime(s.origin_us,0),'19:35:16');});
const {validateCatalog,evidenceFor,valueText} = require('../apps/website/multiview-story.js');
test('day excerpts preserve gaps and reject overlapping or unsafe period routes',()=>{
 const catalog={schema_version:'labprism-story-catalog/1',date:'2026-09-17',coverage:'curated_excerpts_not_full_day',default_period:'period-b',periods:[{id:'period-a',story:'period-a/story.json',title:'A',origin_us:100000000,duration:10},{id:'period-b',story:'period-b/story.json',title:'B',origin_us:200000000,duration:20}]};
 assert.equal(validateCatalog(catalog).periods.length,2);
 for(const edit of [c=>c.periods[1].origin_us=105000000,c=>c.periods[1].story='../producer.json',c=>c.default_period='missing',c=>c.coverage='full_day']){let c=structuredClone(catalog);edit(c);assert.throws(()=>validateCatalog(c));}
});
test('dense adjacent actions do not keep an earlier candidate selected',()=>{
 const steps=[{id:'a',start:1,end:1.1},{id:'b',start:1.12,end:1.15},{id:'c',start:1.15,end:1.3}];
 assert.equal(stepAt(steps,1.12).id,'b');assert.equal(stepAt(steps,1.15).id,'c');assert.equal(stepAt(steps,1.11),null);
});
test('evidence context uses overlap, source camera and time basis without filling gaps',()=>{
 const d=fixture();d.audio={sentences:[{comment_id:'yes',start_us:d.origin_us+2e6,end_us:d.origin_us+3e6},{comment_id:'near',start_us:d.origin_us+5e6,end_us:d.origin_us+6e6}]};
 d.readings=[{id:'sync',time:3,camera_id:'wearer',association:'same_camera_and_synchronized_capture_time'},{id:'filename',time:3,camera_id:'wearer',association:'same_camera_and_filename_time_not_hardware_verified'},{id:'other-camera',time:3,camera_id:'bench',association:'same_camera_and_synchronized_capture_time'}];
 const context=evidenceFor(d,d.steps[0],3);assert.deepEqual(context.voices.map(v=>v.comment_id),['yes']);assert.deepEqual(context.readings.map(r=>r.id),['sync']);assert.equal(evidenceFor(d,null,4.5).voices.length,0);
});
test('zero, missing readings and distinct candidates remain distinct',()=>{
 assert.equal(valueText({values:[{value:0,unit:'g'}]}),'0g');assert.equal(valueText({values:[{value:null,unit:'g'}]}),'—');assert.notEqual(valueText({values:[{value:1.2005,unit:'g'}]}),valueText({values:[{value:1.2029,unit:'g'}]}));
 const s=fixture();s.audio={file:'audio.opus',start:0,sentences:[{comment_id:'bad',start_us:3,end_us:2,text:'bad'}]};assert.throws(()=>validateStory(s));
});
