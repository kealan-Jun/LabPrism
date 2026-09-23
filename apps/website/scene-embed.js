"use strict";
// Same-origin embeds use the identical viewer and expose all of its controls.
document.querySelectorAll('iframe.scene-embed').forEach(frame=>{
  frame.addEventListener('load',()=>{
    if(new URL(frame.src,location.href).origin!==location.origin)return;
    const scene=frame.contentDocument?.querySelector('.live-viewer');
    if(!scene)return;
    const resize=()=>{frame.style.height=`${Math.ceil(scene.getBoundingClientRect().height)+2}px`;};
    const observer=new ResizeObserver(resize);observer.observe(scene);resize();
    window.addEventListener('pagehide',()=>observer.disconnect(),{once:true});
  });
});
