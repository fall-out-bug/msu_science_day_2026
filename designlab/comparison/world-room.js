/* Illustrated room renderer. Research/save rules remain in NightModel. */
(() => {
'use strict';
window.ObservatoryRoom=function({host,onLayout}){
 let scene,mode='welcome',state={},lastReceipt=null;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 class Room extends Phaser.Scene {
  constructor(){super('observatory');}
  preload(){this.load.image('room',NIGHTSHIFT_ART.room);this.load.image('nika',NIGHTSHIFT_ART.mentor);}
  create(){
   scene=this;this.room=this.add.image(0,0,'room');this.shade=this.add.rectangle(0,0,1,1,0x030a18,.14).setOrigin(0);
   this.displays=this.add.container();this.mentor=this.add.image(0,0,'nika').setOrigin(.5,1);this.board=this.add.container();this.modules=this.add.container();
   this.scale.on('resize',()=>this.layout());this.layout();drawState();
   host.dataset.ready='true';host.dispatchEvent(new Event('roomready'));
  }
  layout(){
   const w=this.scale.width,h=this.scale.height,mobile=w<700;
   const s=mobile?w/1672:mode==='welcome'?Math.max(w/1672,h/941):Math.min(w/1672,(h-60)/941),x=(w-1672*s)/2,y=mobile?Math.max(110,h*.16):mode==='welcome'?(h-941*s)/2:60+(h-60-941*s)/2;
   this.room.setPosition(x+836*s,y+470.5*s).setScale(s);this.shade.setSize(w,h);
   this.mentor.setDisplaySize(mobile?200:Math.min(375,h*.51),mobile?300:Math.min(562,h*.765));
   this.mentor.setPosition(mobile?w-80:mode==='welcome'?w*.82:w*.18,mobile?h-165:h+10);this.mentor.setAlpha(mode==='game'?.15:1);
   this.board.setPosition(x,y).setScale(s);this.modules.setPosition(x,y).setScale(s);this.displays.setPosition(x,y).setScale(s);
   this.mentor.setVisible(mode!=='map'&&mode!=='game');
   onLayout?.({map:{x:x+285*s,y:y+360*s},instrument:{x:x+873*s,y:y+480*s},board:{x:x+1510*s,y:y+205*s},mobile});
  }
 }
 const game=new Phaser.Game({type:Phaser.CANVAS,parent:host,width:host.clientWidth||innerWidth,height:host.clientHeight||innerHeight,transparent:true,banner:false,audio:{noAudio:true},fps:{target:30},scale:{mode:Phaser.Scale.RESIZE},scene:Room});
 function drawState(){
  if(!scene)return;scene.board.removeAll(true);scene.modules.removeAll(true);scene.displays.removeAll(true);
  (state.monitors||[]).forEach((canvas,i)=>{const key='monitor-'+i;if(scene.textures.exists(key))scene.textures.remove(key);scene.textures.addCanvas(key,canvas);scene.displays.add(scene.add.image(795+i*135,499,key).setDisplaySize(78,78).setAlpha(.85));});
  const modules=[['ДВИЖЕНИЕ',!!state.session?.installed.movement],['СВЕТ',!!state.session?.installed.fading],['ПРИМЕРЫ',state.session?.learningLabel==='wrongLink']];
  modules.forEach(([label,on],i)=>{const x=692+i*114,y=565;const led=scene.add.circle(x,y,6,on?0x95ffe0:0x415052);scene.modules.add(led);scene.modules.add(scene.add.text(x+11,y-7,label,{fontFamily:'system-ui',fontSize:'11px',color:on?'#d2fff0':'#9aa7a5'}));});
  (state.previews||[]).slice(0,9).forEach((entry,i)=>{
   const key='result-'+entry.id;if(scene.textures.exists(key))scene.textures.remove(key);scene.textures.addCanvas(key,entry.canvas);
   const x=1510+(i%3)*52,y=310+Math.floor(i/3)*77;
   const back=scene.add.rectangle(x,y,50,62,0xd9c7a5),photo=scene.add.image(x,y-3,key).setDisplaySize(44,44),pin=scene.add.circle(x,y-27,3,0xffd37c);
   const group=scene.add.container(x,y,[back.setPosition(0,0),photo.setPosition(0,-3),pin.setPosition(0,-31)]);scene.board.add(group);
   if(mode==='room'&&entry.id===state.receipt&&lastReceipt!==state.receipt&&!reduced.matches){group.setPosition(890,505).setScale(.15);scene.tweens.add({targets:group,x,y,scale:1,duration:650,ease:'Cubic.Out'});}
  });
  if(mode==='room'&&state.receipt)lastReceipt=state.receipt;
  scene.layout();
 }
 function wake(){if(!document.hidden&&['welcome','room','ending'].includes(mode)){game.loop.wake();if(scene)scene.scene.resume();}}
 const visibility=()=>document.hidden?game.loop.sleep():wake();document.addEventListener('visibilitychange',visibility);
 return {
  setMode(value){mode=value;host.dataset.mode=value;if(scene)scene.layout();if(['map','game'].includes(value))game.loop.sleep();else wake();},
  setState(value){state=value;drawState();},
  pause(){game.loop.sleep();},resume:wake,
  destroy(){document.removeEventListener('visibilitychange',visibility);game.destroy(true);}
 };
};
})();
