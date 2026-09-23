const test=require('node:test');
const assert=require('node:assert/strict');
const {initialSelection,modelNames,sourceUse,outputSummary,runSummary}=require('../apps/viewer/result-presentation.js');
const {poseEvidence}=require('../apps/viewer/result-presentation.js');
const clips=[{id:'a',camera_id:'camera-1'},{id:'b',camera_id:'camera-2'}];
test('temporal timing requires current-stage frame count and never borrows parent speed',()=>{
  const result={models:[{id:'sam2',task:'video_instance_segmentation'}],metrics:{stage_seconds:235.6397,temporal_frames:667},parent_metrics:{processing_fps:100}};
  assert.match(runSummary(result),/667 帧，用时 235.64 秒；不含检测/);
  delete result.metrics.temporal_frames;
  assert.doesNotMatch(runSummary(result),/235.64|100/);
});
test('unexecuted tasks are distinct from zero detections and unknown metrics',()=>{
  const p=require('../apps/viewer/result-presentation.js');
  const r={output_statuses:{keypoints:{state:'not_run'},events:{state:'not_run'}},metrics:{}};
  assert.equal(p.handCoverage(r,378),'本轮未执行手姿');
  assert.equal(p.handCoverage({metrics:{}},378),'手姿覆盖未测量');
  assert.equal(p.frameCounts({objects:[{}],hands:[]},r),'1 个检测 · 手姿未执行');
  assert.equal(p.emptyEventStatus(r),'本轮未执行事件识别。');
  assert.deepEqual(p.poseEvidence(r,true),{active:'未执行',parent:null});
});
test('deep links cannot silently select a different input or view',()=>{
  assert.throws(()=>initialSelection(clips,new URLSearchParams('clip=missing&t=4&object=1')),/不存在/);
  assert.throws(()=>initialSelection(clips,new URLSearchParams('clip=a&view=camera-2')),/不匹配/);
  assert.deepEqual(initialSelection(clips,new URLSearchParams('clip=b&view=camera-2&t=12.345&object=track-1')),
    {item:clips[1],start:12.345,object:'track-1'});
});
test('invalid times cannot enter a seek',()=>{
  for(const value of ['Infinity','NaN','-1'])assert.equal(initialSelection(clips,new URLSearchParams('clip=a&t='+value)).start,0);
});
test('model labels follow task identity and preserve missing records',()=>{
  const result={models:[{id:'pose',task:'hand_landmarks_candidate'},{id:'mask-new',task:'box_prompted_instance_segmentation'}]};
  assert.equal(modelNames(result,['object_detection']),'未提供模型记录');
  assert.equal(modelNames(result,['box_prompted_instance_segmentation']),'mask-new');
});
test('trained pose uses the current model and hash-bound parent without assuming registry order',()=>{
  const result={configuration:{trained_hand_replay:{model_id:'trained'}},models:[
    {id:'base',task:'hand_landmarks_candidate',sha256:'base-hash'},
    {id:'unrelated',task:'hand_landmarks_candidate',sha256:'other'},
    {id:'trained',task:'hand_landmarks_candidate',sha256:'trained-hash',parent_sha256:'base-hash'}]};
  assert.deepEqual(poseEvidence(result,true),{active:'trained',parent:'base'});
  assert.deepEqual(poseEvidence({model_usage:{hand_pose:'trained'},models:result.models},true),{active:'trained',parent:'base'});
  result.configuration.trained_hand_replay.model_id='missing';
  assert.deepEqual(poseEvidence(result,true),{active:'当前手姿模型记录缺失',parent:null});
  delete result.configuration.trained_hand_replay;
  assert.equal(poseEvidence(result,true).active,'base / unrelated / trained');
});
test('current detector can use separately pinned pose lineage without inventing a missing registry model',()=>{
  const model={id:'trained',task:'hand_landmarks_candidate',parent_sha256:'1234567890abcdef',
    pose_lineage:{result_sha256:'result',receipt_sha256:'receipt'}};
  const result={configuration:{trained_hand_replay:{model_id:'trained'}},models:[model]};
  assert.deepEqual(poseEvidence(result,true),{active:'trained',parent:'1234567890ab · 来源回执已校验'});
  delete model.pose_lineage.receipt_sha256;
  assert.equal(poseEvidence(result,true).parent,'父模型记录缺失');
});
test('production purpose and failed outputs keep their meaning',()=>{
  const result={data_use:{purpose:'production_observation'},source:{split:null},output_statuses:{keypoints:{state:'failed',reason:'模型调用失败'},readouts:{state:'not_connected',reason:'尚无绑定'}}};
  assert.equal(sourceUse(result),'生产观察 · 未划入训练或验证分区');
  assert.deepEqual(outputSummary(result),[['手姿','失败 · 模型调用失败'],['读数','未接入 · 尚无绑定']]);
});
test('parent GPU and parent timing cannot become current-stage measurements',()=>{
  const result={environment:{gpu:'parent GPU'},parent_metrics:{sampled_pipeline_fps:40},metrics:{candidate_processing_fps:null,sampled_pipeline_fps:null}};
  assert.match(runSummary(result),/未测量/);
  assert.doesNotMatch(runSummary(result),/40|parent GPU/);
  assert.equal(runSummary({metrics:{candidate_processing_fps:7.2}}),'新增阶段 7.2 分析帧/s；非完整流水线速度');
  assert.equal(runSummary({metrics:{sampled_pipeline_fps:2.830225}}),'本轮已启用模块 2.83 分析帧/s；未运行模块不计入');
});
test('received OCR composition never inherits visual-only throughput',()=>{
  assert.equal(runSummary({ocr_integration:{mode:'received_sparse_frame_observations'},metrics:{sampled_pipeline_fps:40}}),
    '接收既有视觉结果与稀疏 OCR；组合流水线速度未测量');
});
test('hand detections and accepted poses remain distinct when pose output is withheld',()=>{
  const {frameCounts}=require('../apps/viewer/result-presentation.js');
  assert.equal(frameCounts({objects:[{label:'hand'},{label:'balance'}],hands:[]}), '2 个检测 · 1 个手部框 · 0 组手姿');
  assert.equal(frameCounts({objects:[{label:'gloved-hand'}],hands:[{}]}), '1 个检测 · 1 个手部框 · 1 组手姿');
});
test('equipment identity abstention is not mislabeled as hand or confirmed duplicate',()=>{
  const {trackingExclusion}=require('../apps/viewer/result-presentation.js');
  assert.equal(trackingExclusion({}),'');
  const text=trackingExclusion({tracking_exclusion:{reason:'high_overlap_same_class_instance_proposals'}});
  assert.match(text,/同类器材或物体/);assert.doesNotMatch(text,/手部/);
  assert.match(text,/是否同一实物尚未确认/);
  assert.match(trackingExclusion({tracking_exclusion:{reason:'high_overlap_same_class_hand_proposal'}}),/手部/);
  assert.match(trackingExclusion({tracking_exclusion:{reason:'upstream_mask_supported_duplicate_proposals'}}),/VisionCortex.*原始检测仍保留/);
});

test('joint segmentation uses its actual task record and scoped throughput',()=>{
  const result={models:[{id:'joint-v3',task:'joint_detection_instance_segmentation_candidate'}],metrics:{processing_fps:18.036863}};
  assert.equal(modelNames(result,['object_detection','joint_detection_instance_segmentation_candidate']),'joint-v3');
  assert.equal(runSummary(result),'解码、检测与实例分割 18.037 分析帧/s；非完整流水线速度');
  assert.match(runSummary({metrics:{processing_fps:18}}),/未测量/);
});
