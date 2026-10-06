/* A persistent workbench. Every thumbnail below comes from a saved measurement. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  let motionRecord=null,lightRecord=null;
  function image(data,epoch){
    const raw=document.createElement('canvas');raw.width=raw.height=128;
    const source=epoch===0?{...data,arrays:[data.arrays[0],data.arrays[0]]}:data;
    raw.getContext('2d').putImageData(new ImageData(ComparisonModel.render(source,0,epoch||1).pixels,128,128),0,0);
    return raw;
  }
  function brightnessImage(epoch){
    const raw=document.createElement('canvas');raw.width=raw.height=128;
    const data=BRIGHTNESS_DATA.arrays[epoch],pixels=new ImageData(128,128);
    for(let i=0;i<data.length;i++){
      const strength=data[i]<0?0:Math.min(1,Math.asinh(data[i]*.2)/Math.asinh(BRIGHTNESS_DATA.displayTop*.2));
      for(let c=0;c<3;c++)pixels.data[i*4+c]=[8,14,29][c]+([204,242,255][c]-[8,14,29][c])*strength;
      pixels.data[i*4+3]=255;
    }
    raw.getContext('2d').putImageData(pixels,0,0);return raw;
  }
  function crop(ctx,raw,point,left){
    const x=Math.max(0,Math.min(98,point.x-15)),y=Math.max(0,Math.min(98,point.y-15));
    ctx.drawImage(raw,x,y,30,30,left,0,128,128);
    ctx.strokeStyle='#d9f6ee';ctx.lineWidth=2;ctx.beginPath();ctx.arc(left+(point.x+.5-x)/30*128,(point.y+.5-y)/30*128,10,0,Math.PI*2);ctx.stroke();
  }
  function refresh(){
    const motion=comparisonProbe.state.journal[0],light=brightnessEpisode.state.attempts.find(a=>a.result?.outcome==='faded'&&Math.hypot(a.result.point.x-BRIGHTNESS_DATA.historical.point.x,a.result.point.y-BRIGHTNESS_DATA.historical.point.y)<=BRIGHTNESS_DATA.historical.associationRadiusPx);
    const installed=window.journey?.state.installed||{};
    $('bench-device-label').textContent=motion?'Результат остался на приборе':'Прибор получил два снимка';
    $('bench-device-action').textContent=motion?'Посмотреть мою проверку →':'Открыть снимки →';
    $('bench-motion-status').textContent=installed.movement?'Добавлен в автоматический поиск':motion?'Движение проверено · можно добавить в прибор':'Нужно проверить движение на трёх снимках';
    $('bench-light-status').textContent=installed.fading?'Добавлен в автоматический поиск':light?'Изменение проверено · можно добавить в прибор':'Нужно проверить изменение света';
    $('bench-motion').dataset.status=installed.movement?'installed':motion?'verified':'pending';
    $('bench-light').dataset.status=installed.fading?'installed':light?'verified':'pending';
    for(const id of ['bench-motion-result','bench-motion-evidence','bench-motion-open'])$(id).hidden=!motion;
    for(const id of ['bench-light-result','bench-light-evidence','bench-light-open'])$(id).hidden=!light;
    if(motion&&motion!==motionRecord){
      const data=COMPARISON_DATA.cases.find(c=>c.id===motion.caseId),ctx=$('bench-motion-result').getContext('2d');
      motion.result.positions.forEach((point,epoch)=>{
        ctx.drawImage(image(data,epoch),128*epoch,0);
        ctx.strokeStyle='#d9f6ee';ctx.lineWidth=1;ctx.beginPath();ctx.arc(128*epoch+point.x+.5,point.y+.5,6,0,Math.PI*2);ctx.stroke();
      });
      $('bench-motion-evidence').textContent='Снимки 1 → 2 → 3. Твоя точка отмечена кружком. Прогноз и найденное положение отличаются на '+motion.result.distancePx.toFixed(2)+' пикселя.';
    }
    if(light&&light!==lightRecord){
      const point=light.selection.point,ctx=$('bench-light-result').getContext('2d');
      for(let epoch=0;epoch<2;epoch++)crop(ctx,brightnessImage(epoch),point,128*epoch);
      $('bench-light-evidence').textContent='Измерение твоей области: 100 → '+Math.round(light.result.secondFlux/light.result.firstFlux*100)+'. Это относительная шкала изменившегося света.';
    }
    motionRecord=motion||null;lightRecord=light||null;
  }
  function inspect(){
    if(comparisonProbe.state.journal.length)comparisonProbe.openSaved('s02');
    window.journey.show('opening');
  }
  for(const [epoch,id] of ['bench-preview-first','bench-preview-second'].entries())$(id).getContext('2d').drawImage(image(COMPARISON_DATA.cases[0],epoch),0,0);
  $('bench-start').onclick=inspect;$('bench-motion-open').onclick=inspect;
  $('bench-light-open').onclick=()=>{journey.show('brightness');$('brightness-open-saved').click();};
  window.workbench={refresh};
})();
