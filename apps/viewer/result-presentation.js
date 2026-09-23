"use strict";
// Pure presentation rules shared by the browser and regression checks.
(function(root){
  function initialSelection(clips, query){
    const id=query.get('clip'), view=query.get('view');
    const item=id?clips.find(c=>c.id===id):clips.find(c=>c.id==='dissolve-first')||clips[0];
    if(!item)throw Error(id?'定位链接中的片段不存在；请选择可用片段':'片段目录为空');
    if(view&&view!==item.camera_id)throw Error('定位链接的机位与片段不匹配；请选择可用片段');
    const time=Number(query.get('t'));
    return {item,start:Number.isFinite(time)&&time>=0?time:0,object:query.get('object')||null};
  }
  function modelNames(result,tasks){
    return (result.models||[]).filter(m=>tasks.includes(m.task)).map(m=>m.id).join(' / ')||'未提供模型记录';
  }
  function poseEvidence(result,candidate){
    if(result.output_statuses?.keypoints?.state==='not_run')return {active:'未执行',parent:null};
    const id=result.model_usage?.hand_pose||result.configuration?.trained_hand_replay?.model_id;
    if(!id)return {active:modelNames(result,[candidate?'hand_landmarks_candidate':'hand_landmarks']),parent:null};
    const model=(result.models||[]).find(m=>m.id===id&&m.task==='hand_landmarks_candidate');
    if(!model)return {active:'当前手姿模型记录缺失',parent:null};
    const parent=(result.models||[]).find(m=>m.sha256===model.parent_sha256&&m.task==='hand_landmarks_candidate');
    return {active:model.id,parent:parent?.id||'父模型记录缺失'};
  }
  function sourceUse(result){
    const purpose=result.data_use?.purpose;
    if(purpose==='production_observation')return '生产观察 · 未划入训练或验证分区';
    return `${purpose==='evaluation'?'评测':purpose==='development'?'开发':'历史开发'} · ${result.source.split??'未知'} 分区`;
  }
  function outputSummary(result){
    const names={boxes:'检测',instance_masks:'实例轮廓',semantic_map:'语义分割',keypoints:'手姿',tracks:'轨迹',relations:'关系',events:'事件',readouts:'读数'};
    const states={predicted:'已有预测',no_detection:'未检出',not_run:'未执行',not_connected:'未接入',failed:'失败',not_applicable:'不适用'};
    return Object.entries(result.output_statuses||{}).map(([key,value])=>[names[key]||key,`${states[value.state]||value.state} · ${value.reason}`]);
  }
  function runSummary(result){
    if(result.ocr_integration?.mode==='received_sparse_frame_observations')return '接收既有视觉结果与稀疏 OCR；组合流水线速度未测量';
    const metrics=result.metrics||{};
    if((result.models||[]).some(m=>m.task==='video_instance_segmentation')&&Number.isFinite(metrics.stage_seconds)&&Number.isFinite(metrics.temporal_frames))return `视频分割阶段处理 ${metrics.temporal_frames} 帧，用时 ${Number(metrics.stage_seconds.toFixed(2))} 秒；不含检测、手姿与其他模块`;
    if((result.models||[]).some(m=>m.task==='joint_detection_instance_segmentation_candidate')&&Number.isFinite(metrics.processing_fps))return `解码、检测与实例分割 ${Number(metrics.processing_fps.toFixed(3))} 分析帧/s；非完整流水线速度`;
    if(Number.isFinite(metrics.candidate_processing_fps))return `新增阶段 ${Number(metrics.candidate_processing_fps.toFixed(3))} 分析帧/s；非完整流水线速度`;
    if(Number.isFinite(metrics.sampled_pipeline_fps))return `本轮已启用模块 ${Number(metrics.sampled_pipeline_fps.toFixed(3))} 分析帧/s；未运行模块不计入`;
    return '本轮阶段与完整流水线速度未测量；来源环境记录不代表本轮实际执行设备';
  }
  function frameCounts(frame,result){
    if(result?.output_statuses?.keypoints?.state==='not_run')return `${frame.objects.length} 个检测 · 手姿未执行`;
    const handBoxes=frame.objects.filter(o=>['hand','gloved_hand'].includes(o.label?.replace(/-/g,'_'))).length;
    return `${frame.objects.length} 个检测 · ${handBoxes} 个手部框 · ${frame.hands.length} 组手姿`;
  }
  function handCoverage(result, total){
    if(result.output_statuses?.keypoints?.state==='not_run')return '本轮未执行手姿';
    return Number.isFinite(result.metrics?.frames_with_hands)?`${result.metrics.frames_with_hands}/${total} 帧有输出；不等于关节准确率`:'手姿覆盖未测量';
  }
  function emptyEventStatus(result){
    return result.output_statuses?.events?.state==='not_run'?'本轮未执行事件识别。':'本段尚无满足持续时间要求的接近事件。';
  }
  function trackingExclusion(object){
    const evidence=object?.tracking_exclusion;
    if(!evidence)return '';
    if(evidence.reason==='upstream_mask_supported_duplicate_proposals')return 'VisionCortex 分割支持的重合候选，暂未分配轨迹身份；原始检测仍保留，是否同一实物尚未确认';
    const kind=evidence.reason==='high_overlap_same_class_hand_proposal'?'手部':
      evidence.reason==='high_overlap_same_class_instance_proposals'?'同类器材或物体':'';
    return `高度重合的${kind}候选，暂未分配轨迹身份；原始检测仍保留，是否同一实物尚未确认`;
  }
  const api={initialSelection,modelNames,poseEvidence,sourceUse,outputSummary,runSummary,frameCounts,trackingExclusion,handCoverage,emptyEventStatus};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.ResultPresentation=api;
})(globalThis);
