/* Invert only published piecewise clock knots; never extrapolate a missing view. */
(function(root){
  function validate(knots) {
    if(!Array.isArray(knots)||knots.length<2||knots.length>10000)throw Error('缺少采集时间映射');
    knots.forEach((p,i)=>{
      if(!Array.isArray(p)||p.length!==2||!p.every(Number.isFinite)||
        (i&&(p[0]<=knots[i-1][0]||p[1]<=knots[i-1][1])))throw Error('采集时间映射无效');
    });return knots;
  }
  function map(knots,value,axis=0) {
    if(!Number.isFinite(value)||value<knots[0][axis]||value>knots.at(-1)[axis])return null;
    let lo=1,hi=knots.length-1;
    while(lo<hi){const mid=(lo+hi)>>1;if(knots[mid][axis]<value)lo=mid+1;else hi=mid;}
    const a=knots[lo-1],b=knots[lo],other=1-axis;
    return a[other]+(value-a[axis])/(b[axis]-a[axis])*(b[other]-a[other]);
  }
  function photoCandidates(data,jobs){
    const cameras=new Set(data.views.map(v=>v.camera_id));
    if(!Number.isSafeInteger(data.global_origin_us))return [];
    return jobs.flatMap(job=>{
      if(job.media_kind!=='external_photo'||!cameras.has(job.camera_id)||typeof job.captured_at!=='string'||
        !/(Z|[+-]\d{2}:\d{2})$/.test(job.captured_at)||!job.capture_time_basis)return [];
      const seconds=(Date.parse(job.captured_at)-data.global_origin_us/1000)/1000;
      if(!Number.isFinite(seconds)||seconds<0||seconds>data.duration_seconds)return [];
      return [{job,seconds,basis:'same_camera_and_reported_capture_time_only',synchronization_error_ms:null}];
    });
  }
  function readLink(query,identity,duration,actions,photos){
    if(!['mv','mt','ma','mp'].some(key=>query.has(key)))return null;
    if(query.get('mv')!==identity)throw Error('定位链接的多视角来源版本不匹配，请重新选择证据');
    const action=query.get('ma'),photo=query.get('mp'),time=query.has('mt')?Number(query.get('mt')):0;
    if(action&&photo)throw Error('定位链接包含冲突的证据选择');
    if(!Number.isFinite(time)||time<0||time>duration)throw Error('多视角定位时间超出可用范围');
    if(action){const item=actions.find(row=>row.id===action);if(!item)throw Error('该动作证据不在当前来源中');return {kind:'action',item,time:item.timestamp_seconds};}
    if(photo){const item=photos.find(row=>row.job.job_id===photo);if(!item)throw Error('该照片不在当前机位与时间范围中');return {kind:'photo',item,time:item.seconds};}
    return {kind:'time',time};
  }
  function analysisVersions(view,clips){
    if(!/^[a-f0-9]{64}$/.test(view.clip_sha256||'')||!/^[a-f0-9]{64}$/.test(view.source_sha256||''))return [];
    return clips.filter(clip=>clip.clip_sha256===view.clip_sha256&&clip.source_sha256===view.source_sha256&&
      clip.camera_id===view.camera_id&&clip.camera_role===view.camera_role&&/^[a-z0-9-]+$/.test(clip.id));
  }
  function analysisTime(views,clip,mediaSeconds){
    if(!clip||!Number.isFinite(mediaSeconds))return null;
    const matches=views.filter(view=>analysisVersions(view,[clip]).length===1);
    return matches.length===1?map(matches[0].knots,mediaSeconds,1):null;
  }
  const api={validate,map,photoCandidates,readLink,analysisVersions,analysisTime};if(typeof module!=='undefined')module.exports=api;else root.LabPrismClock=api;
})(globalThis);
