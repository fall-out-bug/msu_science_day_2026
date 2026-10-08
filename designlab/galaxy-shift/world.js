/* One coherently lit scene; the camera moves between the room and its desk. */
(function () {
  'use strict';
  const canvas=document.querySelector('#world'),ctx=canvas.getContext('2d',{alpha:false});
  const reduce=matchMedia('(prefers-reduced-motion: reduce)'),images={};
  let width=0,height=0,phase='intro',target=0,camera=0,mouseX=0,mouseY=0,panX=0,panY=0;
  let last=0,frames=0,draws=0,dirty=true,started=performance.now(),sceneBounds=null;
  const ready=Promise.all(Object.entries({intro:'observatory-arkhyz-night-v1.png',room:'observatory-night-v2.png',portrait:'observatory-night-portrait-v3.png',table:'worktop-night-v2.png'}).map(([key,file])=>new Promise((resolve,reject)=>{
    const img=new Image();images[key]=img;img.onload=resolve;img.onerror=()=>reject(new Error('Не загрузилась сцена: '+file));img.src='assets/art/'+file;
  })));
  function resize(){width=innerWidth;height=innerHeight;dirty=true;const ratio=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);canvas.style.width=width+'px';canvas.style.height=height+'px';ctx?.setTransform(ratio,0,0,ratio,0,0);}
  function contain(img,areaHeight,key,top=0){
    const scale=Math.min(width/img.width,areaHeight/img.height),w=img.width*scale,h=img.height*scale;
    const slackX=(width-w)/2,slackY=(areaHeight-h)/2;
    const x=slackX+Math.max(-Math.abs(slackX),Math.min(Math.abs(slackX),panX));
    const y=top+slackY+Math.max(-Math.abs(slackY),Math.min(Math.abs(slackY),panY));
    ctx.drawImage(img,x,y,w,h);sceneBounds={key,x,y,width:w,height:h,sourceWidth:img.width,sourceHeight:img.height,mode:'contain'};
  }
  function cover(img,areaHeight,key,focus=.5){
    const scale=Math.max(width/img.width,areaHeight/img.height),w=img.width*scale,h=img.height*scale;
    const x=Math.min(0,Math.max(width-w,width*.5-w*focus))+panX,y=(areaHeight-h)*.5+panY;
    ctx.drawImage(img,x,y,w,h);sceneBounds={key,x,y,width:w,height:h,sourceWidth:img.width,sourceHeight:img.height,mode:'cover'};
  }
  function draw(time){
    const dt=Math.min(64,time-last||16);last=time;
    const previous=camera;camera+=(target-camera)*(reduce.matches?1:Math.min(1,dt/210));
    const px=panX,py=panY;panX+=(mouseX*5-panX)*.08;panY+=(mouseY*3-panY)*.08;
    const moving=Math.abs(previous-camera)>.0001||Math.abs(px-panX)>.01||Math.abs(py-panY)>.01;
    if(ctx&&(dirty||moving)){
      dirty=false;draws++;ctx.fillStyle='#08141e';ctx.fillRect(0,0,width,height);
      const mobile=width<700,roomTop=mobile?55:0,roomHeight=mobile?Math.min(height*.58,500):height;
      if(phase==='intro') { if(mobile) cover(images.intro,height,'intro',.62); else contain(images.intro,roomHeight,'intro',roomTop); }
      else contain(mobile?images.portrait:images.room,roomHeight,mobile?'portrait':'room',roomTop);
      if(camera>.001){ctx.globalAlpha=camera;contain(images.table,height,'table');ctx.globalAlpha=1;}
    }
    frames++;requestAnimationFrame(draw);
  }
  addEventListener('resize',resize);
  addEventListener('pointermove',event=>{if(reduce.matches||target!==0)return;mouseX=event.clientX/innerWidth-.5;mouseY=event.clientY/innerHeight-.5;},{passive:true});
  resize();ready.then(()=>{document.querySelector('#loading')?.remove();if(!ctx)document.body.classList.add('canvas-fallback');requestAnimationFrame(draw);}).catch(error=>{const loading=document.querySelector('#loading');if(!loading)return;loading.textContent=error.message+'. Распакуйте игру целиком.';loading.classList.add('failed');});
  globalThis.galaxyWorld={ready,setPhase(next){phase=next;dirty=true;target=next==='intro'||next==='final'?0:1;mouseX=0;mouseY=0;canvas.setAttribute('aria-label','Обсерватория ночью: Ника за рабочим столом, за дверью звёздное небо');},stats(){return {frames,draws,width,height,phase,elapsed:performance.now()-started,canvas:!!ctx,sceneBounds};}};
})();
