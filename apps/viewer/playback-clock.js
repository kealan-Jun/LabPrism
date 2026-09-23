/* Ignore video-frame callbacks scheduled before a seek or source change. */
(function(root){
  class PlaybackFrameClock {
    constructor(video,onFrame){this.video=video;this.onFrame=onFrame;this.epoch=0;this.handle=null;}
    invalidate(){
      this.epoch++;
      if(this.handle!==null)this.video.cancelVideoFrameCallback(this.handle);
      this.handle=null;
    }
    watch(){
      if(this.handle!==null)return;
      const epoch=this.epoch;
      this.handle=this.video.requestVideoFrameCallback((_,meta)=>{
        if(epoch!==this.epoch)return;
        this.handle=null;
        if(!this.video.seeking&&Number.isFinite(meta.mediaTime))this.onFrame(meta.mediaTime);
        this.watch();
      });
    }
  }
  if(typeof module!=='undefined')module.exports=PlaybackFrameClock;else root.PlaybackFrameClock=PlaybackFrameClock;
})(typeof window==='undefined'?globalThis:window);
