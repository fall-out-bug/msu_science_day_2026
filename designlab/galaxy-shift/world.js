/* The room renderer owns images and motion; game state stays in model.js. */
(function () {
  'use strict';
  const canvas = document.querySelector('#world');
  const ctx = canvas.getContext('2d', {alpha:false});
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const images = {};
  let width = 0, height = 0, phase = 'intro', target = 0, camera = 0;
  let mouseX = 0, mouseY = 0, last = 0, frames = 0, draws = 0, dirty = true, started = performance.now();
  const ready = Promise.all(Object.entries({room:'laboratory-modern-v1.png',desk:'workstation-modern-v1.png',nika:'nika.png',table:'worktop-modern-v1.png'}).map(([key,file]) => new Promise((resolve,reject) => {
    const img = new Image(); images[key] = img;
    img.onload = resolve; img.onerror = () => reject(new Error('Не загрузился элемент лаборатории: '+file));
    img.src = 'assets/art/'+file;
  })));
  const monitorReady=Promise.all(['child_ic5332','child_ngc5023'].map((id,i)=>new Promise(resolve=>{const img=new Image();images['science'+i]=img;img.onload=resolve;img.onerror=resolve;img.src=GALAXY_DATA.images.find(p=>p.id===id).src;})));
  function resize() {
    width = innerWidth; height = innerHeight; dirty=true;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    canvas.style.width = width+'px'; canvas.style.height = height+'px';
    if (ctx) ctx.setTransform(ratio,0,0,ratio,0,0);
  }
  function sprite(img,x,y,w) {ctx.drawImage(img,x,y,w,w*img.height/img.width);}
  function monitor(texture,x,y,w,points) {
    if(!texture.complete||!texture.naturalWidth)return;
    const quad=points.map(([a,b])=>({x:x+a*w,y:y+b*w*images.desk.height/images.desk.width}));
    // Two affine triangles map an actual admitted scientific image onto the monitor.
    const iw=texture.width,ih=texture.height;
    for(let side=0;side<2;side++){
      const p=quad,indices=side?[1,2,3]:[0,1,3];ctx.save();ctx.beginPath();
      indices.forEach((j,i)=>i?ctx.lineTo(p[j].x,p[j].y):ctx.moveTo(p[j].x,p[j].y));ctx.closePath();ctx.clip();
      if(!side)ctx.transform((p[1].x-p[0].x)/iw,(p[1].y-p[0].y)/iw,(p[3].x-p[0].x)/ih,(p[3].y-p[0].y)/ih,p[0].x,p[0].y);
      else{const a=(p[2].x-p[3].x)/iw,b=(p[2].y-p[3].y)/iw,c=(p[2].x-p[1].x)/ih,d=(p[2].y-p[1].y)/ih;ctx.transform(a,b,c,d,p[1].x-a*iw,p[1].y-b*iw);}
      ctx.drawImage(texture,0,0);ctx.restore();
    }
  }
  function draw(time) {
    const delta = Math.min(64, time-last || 16); last = time;
    camera += (target-camera) * (reduce.matches ? 1 : Math.min(1,delta/180));
    if (ctx && (dirty || Math.abs(target-camera)>.001 || (!reduce.matches && target===0))) {
      dirty=false; draws++;
      const mobile = width < 700;
      const zoom = 1 + camera * .07;
      const scale = Math.max(width/images.room.width,(mobile?height*.67:height)/images.room.height) * zoom;
      const rw = images.room.width*scale, rh = images.room.height*scale;
      const px = reduce.matches ? 0 : mouseX*5;
      const py = reduce.matches ? 0 : mouseY*3;
      if(mobile){ctx.drawImage(images.room,0,images.room.height*.8,images.room.width,images.room.height*.2,0,height*.6,width,height*.4);ctx.drawImage(images.room,(width-rw)/2+px,py,rw,rh);}else ctx.drawImage(images.room,(width-rw)/2+px,(height-rh)/2+py,rw,rh);
      // Soft window light and a restrained day-to-evening colour change.
      ctx.fillStyle = phase === 'final' ? 'rgba(214,132,62,.16)' : 'rgba(19,50,49,.07)';
      ctx.fillRect(0,0,width,height);
      const nw = mobile ? width*.40 : Math.min(width*.205,height*.36);
      const dw = mobile ? width*.79 : Math.min(width*.51,height*.79);
      const deskBottom = mobile ? height*.56 : height*.94;
      const nikaBottom = mobile ? height*.53 : height*.80;
      sprite(images.nika,mobile?width*.05:width*.49,nikaBottom-nw*images.nika.height/images.nika.width,nw);
      const deskX=mobile?width*.24:width*.52,deskY=deskBottom-dw*images.desk.height/images.desk.width;
      sprite(images.desk,deskX,deskY,dw);
      monitor(images.science0,deskX,deskY,dw,[[.183,.079],[.449,.070],[.449,.294],[.185,.315]]);
      monitor(images.science1,deskX,deskY,dw,[[.469,.071],[.733,.087],[.730,.309],[.469,.288]]);
      if (!reduce.matches && !document.hidden) {
        ctx.fillStyle='rgba(255,249,211,.3)';
        for(let i=0;i<14;i++){
          const x=(width*(i*.137+Math.sin(time*.00006+i)*.022))%width;
          const y=(height*(i*.219)-time*.006+i*57)%(height*.8);
          ctx.beginPath();ctx.arc(x,y<0?y+height*.8:y,1.1+(i%3)*.4,0,Math.PI*2);ctx.fill();
        }
      }
      if(camera>.001){const surfaceScale=Math.max(width/images.table.width,height/images.table.height);const tw=images.table.width*surfaceScale,th=images.table.height*surfaceScale;ctx.globalAlpha=camera;ctx.drawImage(images.table,(width-tw)/2,(height-th)/2,tw,th);ctx.globalAlpha=1;}
      const fade = camera*.015;
      if(fade>.001){ctx.fillStyle='rgba(7,29,33,'+fade+')';ctx.fillRect(0,0,width,height);}
    }
    frames++;
    requestAnimationFrame(draw);
  }
  addEventListener('resize',resize);
  addEventListener('pointermove',event => {mouseX=event.clientX/innerWidth-.5;mouseY=event.clientY/innerHeight-.5;},{passive:true});
  resize();
  Promise.all([ready,monitorReady]).then(() => {
    document.querySelector('#loading').remove();
    if (!ctx) document.body.classList.add('canvas-fallback');
    requestAnimationFrame(draw);
  }).catch(error => {
    const loading=document.querySelector('#loading');
    loading.textContent=error.message+'. Распакуйте игру целиком.';
    loading.classList.add('failed');
  });
  globalThis.galaxyWorld={ready,setPhase(next){phase=next;dirty=true;target=next==='intro'||next==='final'?0:1;canvas.setAttribute('aria-label',next==='final'?'Вечерняя лаборатория Ники':'Лаборатория Ники в горах');},stats(){return {frames,draws,width,height,elapsed:performance.now()-started,canvas:!!ctx};}};
})();
