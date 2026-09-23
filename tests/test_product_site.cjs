const test = require('node:test');
const assert = require('node:assert/strict');
const {groupRecords,validPoint} = require('../apps/website/product.js');
test('library groups exact clips and roles, not just common recording lineage',()=>{
  const base={source_sha256:'same-recording',clip_sha256:'first',camera_id:'camera',camera_role:'first_person'};
  const clips=[{...base,id:'a'},{...base,id:'b'},{...base,id:'other-crop',clip_sha256:'second'}, {...base,id:'role-conflict',camera_role:'unknown'}];
  const groups=groupRecords(clips);
  assert.equal(groups.length,3);assert.equal(groups[0].latest.id,'b');assert.deepEqual(groups[0].versions.map(c=>c.id),['a','b']);
});
test('presentation does not invent missing or low score joints',()=>{
  assert.equal(validPoint([2,3,null],.5,.3),true);
  for(const args of [[[2,3],.1,.3],[[null,3],.5,.3],[[2,3],null,.3],[[2,3],.5,undefined]])assert.equal(validPoint(...args),false);
});
