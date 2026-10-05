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
   this.displays=this.add.container();this.basePortrait=this.add.image(0,0,'nika').setOrigin(.5,1);this.successPortrait=this.add.image(0,0,'nika-success').setOrigin(.5,1).setAlpha(0);
   this.mentor=this.add.container(0,0,[this.basePortrait,this.successPortrait]);this.board=this.add.container();this.modules=this.add.container();
   this.scale.on('resize',()=>this.layout());this.layout();drawState();
   host.dataset.ready='true';host.dispatchEvent(new Event('roomready'));
  }
  layout(){
   const w=this.scale.width,h=this.scale.height,mobile=w<700;
   const s=mobile?w/1672:mode==='welcome'?Math.max(w/1672,h/941):Math.min(w/1672,(h-60)/941),x=(w-1672*s)/2,y=mobile?Math.max(110,h*.16):mode==='welcome'?(h-941*s)/2:60+(h-60-941*s)/2;
   this.room.setPosition(x+836*s,y+470.5*s).setScale(s);this.dawn.setPosition(this.room.x,this.room.y).setScale(s);this.shade.setSize(w,h);
   this.mentor.setScale((mobile?200:Math.min(375,h*.51))/1024,(mobile?300:Math.min(562,h*.765))/1536);
   this.mentorBaseY=mobile?h-165:h+10;this.mentor.setPosition(mobile?w-80:mode==='welcome'?w*.82:w*.18,this.mentorBaseY);this.mentor.setAlpha(mode==='game'?.15:1);
   this.board.setPosition(x,y).setScale(s);this.modules.setPosition(x,y).setScale(s);this.displays.setPosition(x,y).setScale(s);
   this.mentor.setVisible(mode!=='map'&&mode!=='game');
   onLayout?.({mosaic:{x:x+285*s,y:y+185*s},map:{x:x+285*s,y:y+360*s},instrument:{x:x+873*s,y:y+410*s},board:{x:x+1510*s,y:y+205*s},mobile});
  }
  update(time){if(!reduced.matches&&['welcome','room','ending'].includes(mode)){this.mentor.y=this.mentorBaseY+Math.sin(time/1000)*1.1;this.mentor.rotation=Math.sin(time/1800)*.002;}else{this.mentor.y=this.mentorBaseY;this.mentor.rotation=0;}}
 }
 const game=new Phaser.Game({type:Phaser.CANVAS,parent:host,width:host.clientWidth||innerWidth,height:host.clientHeight||innerHeight,transparent:true,banner:false,audio:{noAudio:true},fps:{target:30},scale:{mode:Phaser.Scale.RESIZE},scene:Room});
 function drawState(){
  if(!scene)return;scene.board.removeAll(true);scene.modules.removeAll(true);scene.displays.removeAll(true);
  (state.monitors||[]).forEach((canvas,i)=>{const key='monitor-'+i;if(scene.textures.exists(key))scene.textures.remove(key);scene.textures.addCanvas(key,canvas);scene.displays.add(scene.add.image(766+i*141,514,key).setDisplaySize(54,54).setAlpha(.85));});
  const modules=[['ДВИЖЕНИЕ',!!state.session?.installed.movement],['СВЕТ',!!state.session?.installed.fading],['ПРИМЕРЫ',state.session?.learningLabel==='wrongLink']];
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
  setMode(value){mode=value;host.dataset.mode=value;if(scene)scene.layout();presentation();if(['map','game'].includes(value))game.loop.sleep();else wake();},
  setState(value){state=value;drawState();},
  pause(){paused=true;game.loop.sleep();},resume(){paused=false;wake();},
  destroy(){document.removeEventListener('visibilitychange',visibility);reduced.removeEventListener('change',motionChanged);game.destroy(true);}
 };
};
})();
