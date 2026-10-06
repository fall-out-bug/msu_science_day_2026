/* Illustrated room renderer. Research/save rules remain in NightModel. */
(() => {
'use strict';
window.ObservatoryRoom=function({host,onLayout}){
 let scene,mode='welcome',state={},lastReceipt=null,paused=false,lastModules=[];
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 class Room extends Phaser.Scene {
  constructor(){super('observatory');}
  preload(){this.load.image('room',NIGHTSHIFT_ART.room);this.load.image('dawn',NIGHTSHIFT_ART.roomDawn);this.load.image('nika',NIGHTSHIFT_ART.mentor);this.load.image('nika-success',NIGHTSHIFT_ART.mentorSuccess);}
  create(){
   scene=this;this.room=this.add.image(0,0,'room');this.dawn=this.add.image(0,0,'dawn').setAlpha(0);this.shade=this.add.rectangle(0,0,1,1,0x030a18,.14).setOrigin(0);
   this.displays=this.add.container();
   // Both portraits have a small transparent margin below the soles. Keep the
   // same floor contact through the expression crossfade, without stretching.
   this.contactShadow=this.add.container(0,0);
   for(let i=5;i>=0;i--)this.contactShadow.add(this.add.ellipse(0,0,116+i*15,15+i*4,0x020812,.045));
   this.basePortrait=this.add.image(0,14,'nika').setOrigin(.5,1);this.successPortrait=this.add.image(0,16,'nika-success').setOrigin(.5,1).setAlpha(0);
   this.mentor=this.add.container(0,0,[this.basePortrait,this.successPortrait]);this.board=this.add.container();this.modules=this.add.container();
   this.scale.on('resize',()=>this.layout());this.layout();drawState();
   host.dataset.ready='true';host.dispatchEvent(new Event('roomready'));
  }
  layout(){
   const w=this.scale.width,h=this.scale.height,mobile=w<700;
   const s=mobile?Math.max(w/1672,Math.min(420,h*.54)/941):mode==='welcome'?Math.max(w/1672,h/941):Math.min(w/1672,(h-60)/941),x=(w-1672*s)/2,y=mobile?142:mode==='welcome'?(h-941*s)/2:60+(h-60-941*s)/2;
   this.room.setPosition(x+836*s,y+470.5*s).setScale(s);this.dawn.setPosition(this.room.x,this.room.y).setScale(s);this.shade.setSize(w,h);
   // Place Nika in the open floor between the console and telescope. Room
   // coordinates preserve perspective when the viewport or scene changes.
   const mentorX=x+(mobile?1010:1220)*s,mentorY=y+835*s;
   this.mentor.setScale(470*s/1536);
   this.mentorBaseY=mentorY;this.mentor.setPosition(mentorX,mentorY).setAlpha(1);
   this.contactShadow.setPosition(mentorX,mentorY+2*s).setScale(s);
   this.board.setPosition(x,y).setScale(s);this.modules.setPosition(x,y).setScale(s);this.displays.setPosition(x,y).setScale(s);
   const active=!['map','game','training'].includes(mode);
   this.mentor.setVisible(active);this.contactShadow.setVisible(active);
   onLayout?.(mobile?{
    mosaic:{x:w*.46,y:176},map:{x:w*.20,y:y+390*s},
    instrument:{x:w*.20,y:y+620*s},board:{x:w*.80,y:y+900*s},
    observatory:{x:w*.78,y:y+250*s},mobile
   }:{
    mosaic:{x:x+760*s,y:y+130*s},map:{x:x+215*s,y:y+405*s},
    instrument:{x:x+850*s,y:y+(w<=1100&&h<680?440:585)*s},board:{x:x+1510*s,y:y+240*s},
    observatory:{x:x+1150*s,y:y+290*s},mobile
   });
  }
  update(time){this.mentor.y=this.mentorBaseY;if(!reduced.matches&&['welcome','room','ending'].includes(mode)){this.mentor.rotation=Math.sin(time/1800)*.001;}else{this.mentor.rotation=0;}}
 }
 const game=new Phaser.Game({type:Phaser.CANVAS,parent:host,width:host.clientWidth||innerWidth,height:host.clientHeight||innerHeight,transparent:true,banner:false,audio:{noAudio:true},fps:{target:30},scale:{mode:Phaser.Scale.RESIZE},scene:Room});
 function drawState(){
  if(!scene)return;scene.board.removeAll(true);scene.modules.removeAll(true);scene.displays.removeAll(true);
  (state.monitors||[]).forEach((canvas,i)=>{const key='monitor-'+i;if(scene.textures.exists(key))scene.textures.remove(key);scene.textures.addCanvas(key,canvas);scene.displays.add(scene.add.image(766+i*141,514,key).setDisplaySize(54,54).setAlpha(.85));});
  const modules=[['ДВИЖЕНИЕ',!!state.session?.installed.movement],['СВЕТ',!!state.session?.installed.fading],['ПРИМЕРЫ',!!state.session?.training?.snapshot]];
  modules.forEach(([label,on],i)=>{const x=688+i*114,y=579;const led=scene.add.circle(x,y,6,on?0x95ffe0:0x415052);scene.modules.add(led);scene.modules.add(scene.add.text(x+11,y-7,label,{fontFamily:'system-ui',fontSize:'11px',color:on?'#d2fff0':'#9aa7a5'}));if(on&&!lastModules[i]&&mode==='room'&&!reduced.matches){const glow=scene.add.circle(x,y,10,0x95ffe0,.7);scene.modules.add(glow);scene.tweens.add({targets:glow,scale:4,alpha:0,duration:800,ease:'Cubic.Out'});}});
  lastModules=modules.map(m=>m[1]);
  (state.previews||[]).slice(0,9).forEach((entry,i)=>{
   const key='result-'+entry.id;if(scene.textures.exists(key))scene.textures.remove(key);scene.textures.addCanvas(key,entry.canvas);
   const x=1510+(i%3)*52,y=310+Math.floor(i/3)*77;
   const back=scene.add.rectangle(x,y,50,62,0xd9c7a5),photo=scene.add.image(x,y-3,key).setDisplaySize(44,44),pin=scene.add.circle(x,y-27,3,0xffd37c);
   const group=scene.add.container(x,y,[back.setPosition(0,0),photo.setPosition(0,-3),pin.setPosition(0,-31)]);scene.board.add(group);
   if(mode==='room'&&entry.id===state.receipt&&lastReceipt!==state.receipt&&!reduced.matches){group.setPosition(890,505).setScale(.15);scene.tweens.add({targets:group,x,y,scale:1,duration:650,ease:'Cubic.Out'});}
  });
  if(mode==='room'&&state.receipt)lastReceipt=state.receipt;if(!state.previews?.length)lastReceipt=null;
  scene.layout();presentation();
 }
 function presentation(){
  if(!scene)return;const dawn=mode==='ending'||!!state.session?.daylight,success=mode==='ending'||mode==='room'&&!!state.receipt;
  host.dataset.daylight=String(dawn);host.dataset.expression=success?'pleased':'attentive';
  for(const [target,alpha,duration]of [[scene.dawn,dawn?1:0,1400],[scene.basePortrait,success?0:1,180],[scene.successPortrait,success?1:0,180]]){
   if(target.goalAlpha===alpha&&!reduced.matches)continue;target.goalAlpha=alpha;scene.tweens.killTweensOf(target);
   if(reduced.matches)target.setAlpha(alpha);else scene.tweens.add({targets:target,alpha,duration,ease:'Sine.InOut'});
  }
 }
 function wake(){if(!paused&&!document.hidden&&['welcome','room','ending'].includes(mode)){game.loop.wake();if(scene)scene.scene.resume();}}
 const motionChanged=()=>{if(scene){drawState();if(reduced.matches){scene.mentor.rotation=0;scene.mentor.y=scene.mentorBaseY;}}};reduced.addEventListener('change',motionChanged);
 const visibility=()=>document.hidden?game.loop.sleep():wake();document.addEventListener('visibilitychange',visibility);
 return {
  setMode(value){mode=value;host.dataset.mode=value;if(scene)scene.layout();presentation();if(['map','game','training'].includes(value))game.loop.sleep();else wake();},
  setState(value){state=value;drawState();},
  pause(){paused=true;game.loop.sleep();},resume(){paused=false;wake();},
  destroy(){document.removeEventListener('visibilitychange',visibility);reduced.removeEventListener('change',motionChanged);game.destroy(true);}
 };
};
})();
