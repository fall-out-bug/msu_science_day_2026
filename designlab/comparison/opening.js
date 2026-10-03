/* Playable cold open: the same real two-frame selection and third-frame check.
 * No target coordinates or catalogue labels choose the answer here.
 */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),data=COMPARISON_DATA.cases[0];
  const state={active:false,epoch:1,playing:false,message:'Смотри: почти всё остаётся на месте. Нажми на точку, которая перескочила.',lastResult:null};
  const motion=matchMedia('(prefers-reduced-motion:reduce)');
  let interval=null;
  const canvases=[null,null,null];
  const time=epoch=>data.dates[epoch].slice(11,16);
  function frame(epoch){
    if(!canvases[epoch]){
      const source=epoch===0?{...data,arrays:[data.arrays[0],data.arrays[0]]}:data;
      const raw=document.createElement('canvas');raw.width=raw.height=128;
      raw.getContext('2d').putImageData(new ImageData(ComparisonModel.render(source,0,epoch||1).pixels,128,128),0,0);
      canvases[epoch]=raw;
    }
    return canvases[epoch];
  }
  function stop(){clearInterval(interval);interval=null;state.playing=false;}
  function play(){
    if(!state.active||comparisonProbe.state.phase!=='search')return;
    stop();state.playing=true;
    interval=setInterval(()=>{if(!state.active||document.hidden)return;state.epoch=state.epoch===0?1:0;draw();},1400);
    draw();
  }
  function draw(){
    if(!state.active)return;
    const trial=comparisonProbe.state,canvas=$('opening-sky'),ctx=canvas.getContext('2d'),result=trial.result;
    ctx.drawImage(frame(state.epoch),0,0,640,640);
    const ring=(point,color,r,dashed=false)=>{
      if(!point)return;
      ctx.setLineDash(dashed?[7,5]:[]);ctx.strokeStyle=color;ctx.lineWidth=2.5;
      ctx.beginPath();ctx.arc((point.x+.5)*5,(point.y+.5)*5,r,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);
    };
    if(result&&state.epoch===2){ring(result.prediction,'#ffd18c',TrackingModel.limits.confirmationRadiusPx*5,true);ring(result.positions[2],'#e8fff5',7);}
    else if(trial.selection)ring(state.epoch===0?trial.selection.origin:trial.selection.point,'#a7f5d6',16);
    if($('opening-points').parentElement.open&&state.epoch===1&&trial.phase==='search'){
      ctx.font='bold 18px system-ui';ctx.textAlign='left';ctx.textBaseline='top';
      data.sources[1].forEach((p,i)=>{const x=Math.min(608,Math.max(4,(p.x+.5)*5+14)),y=Math.min(607,Math.max(4,(p.y+.5)*5-26));ctx.fillStyle='#081727';ctx.fillRect(x-3,y-2,29,26);ctx.fillStyle='#ffdb9e';ctx.fillText(String(i+1),x,y);});
    }
    if(trial.phase==='checking'){
      ctx.fillStyle='#07132399';ctx.fillRect(0,0,640,640);
      ring(trial.selection.point,'#c0f4e2',18);
    }
    $('opening-stamp').textContent=(state.epoch===0?'РАНЬШЕ':state.epoch===1?'ПОЗЖЕ':'СЛЕДУЮЩЕЕ НАБЛЮДЕНИЕ')+' · '+time(state.epoch)+' UTC';
    $('opening-earlier').setAttribute('aria-pressed',String(state.epoch===0));
    $('opening-later').setAttribute('aria-pressed',String(state.epoch===1));
    $('opening-play').setAttribute('aria-pressed',String(state.playing||state.epoch===2));
    $('opening-play').textContent=result?'Кадр проверки · '+time(2):state.playing?'Остановить чередование':'Чередовать снимки';
    for(const id of ['opening-earlier','opening-later','opening-play'])$(id).disabled=trial.phase==='checking';
  }
  function refresh(){
    if(!state.active)return;
    const trial=comparisonProbe.state,result=trial.result,checking=trial.phase==='checking';
    if(result!==state.lastResult){
      state.lastResult=result;
      if(result){stop();state.epoch=2;}
    }
    $('opening').dataset.phase=checking?'checking':result?.outcome==='moving'?'caught':result?'retry':trial.selection?'selected':'search';
    $('opening-action').hidden=!trial.selection&&!result;
    $('opening-action').disabled=checking;
    $('opening-points').parentElement.hidden=trial.phase!=='search';
    $('opening-heading').textContent=result?.outcome==='moving'?'Есть! Он движется.':result?'Проверим ещё?':'Кто-то сдвинулся.';
    $('opening-prompt').textContent=result?.outcome==='moving'?'Ты нашёл след среди звёзд.':result?'Наблюдение помогло проверить твою догадку.':'Сравни снимки. Какая точка сменила место?';
    if(checking){
      $('opening-feedback').textContent='Выбор сохранён. Прибор рассчитал, где искать точку. Открываем следующее наблюдение…';
      $('opening-action').textContent='Открываем следующий снимок…';
    }else if(result){
      $('opening-feedback').textContent=result.outcome==='moving'?'Нашлась рядом с прогнозом! Пунктирное кольцо — где искал прибор, белая отметка — где оказалась точка. Давай соберём прибор, который будет искать такие следы сам.':result.outcome==='stationary'?'Эта точка осталась на месте на всех трёх снимках. Попробуй ту, которая сместилась между первым и вторым.':'На следующем снимке след не подтвердился однозначно. Попробуем другую точку?';
      $('opening-action').textContent=result.outcome==='moving'?'Собрать свой поисковый прибор →':'Выбрать другую точку →';
    }else{
      $('opening-feedback').textContent=state.message;
      $('opening-action').textContent='Проверить на следующем снимке →';
    }
    draw();
  }
  function select(x,y){
    if(!state.active||comparisonProbe.state.phase!=='search')return;
    stop();
    // An earlier-frame click transfers only an unambiguous first→second match.
    // The third observation is not consulted here.
    if(state.epoch===0){
      const near=data.sources[0].filter(p=>Math.hypot(p.x-x,p.y-y)<=TrackingModel.limits.clickRadiusPx);
      const matches=near.length===1?data.sources[1].map(p=>TrackingModel.select(data,p.x,p.y)).filter(s=>s.status==='selected'&&s.origin&&Math.hypot(s.origin.x-near[0].x,s.origin.y-near[0].y)<.01):[];
      if(matches.length===1){x=matches[0].point.x;y=matches[0].point.y;}
      else{state.epoch=1;state.message='На раннем снимке не получилось однозначно выбрать эту точку. Теперь открыт поздний — нажми на неё здесь.';comparisonProbe.retry();refresh();return;}
    }
    state.epoch=1;
    state.message='Точка выбрана. Посмотрим на следующем снимке, куда она попала.';
    comparisonProbe.choose(x,y);
    if(!comparisonProbe.state.selection){state.message='Здесь нет однозначной яркой точки. Нажми точнее на одну из звёздочек.';refresh();}
  }
  function activate(){
    state.active=true;
    if(comparisonProbe.state.result)state.epoch=2;
    refresh();
    if(!motion.matches&&comparisonProbe.state.phase==='search'&&!comparisonProbe.state.selection)play();
  }
  function suspend(){stop();state.active=false;}
  function reset(){suspend();Object.assign(state,{epoch:1,lastResult:null,message:'Смотри: почти всё остаётся на месте. Нажми на точку, которая перескочила.'});}
  for(const [id,epoch] of [['opening-earlier',0],['opening-later',1]])$(id).onclick=()=>{stop();state.epoch=epoch;draw();};
  $('opening-play').onclick=()=>{
    if(comparisonProbe.state.result){stop();state.epoch=2;draw();}
    else if(state.playing){stop();draw();}else play();
  };
  $('opening-sky').onclick=event=>{const rect=event.currentTarget.getBoundingClientRect();select((event.clientX-rect.left)/rect.width*128-.5,(event.clientY-rect.top)/rect.height*128-.5);};
  $('opening-action').onclick=()=>{
    const trial=comparisonProbe.state;
    if(trial.result?.outcome==='moving'){window.journey.show('overview');return;}
    if(trial.result){state.lastResult=null;state.epoch=1;state.message='Сравни снимки ещё раз. На позднем снимке точка будет в другом месте.';comparisonProbe.retry();return;}
    stop();comparisonProbe.follow();
  };
  $('opening-skip').onclick=()=>window.journey.show('overview');
  data.sources[1].forEach((p,i)=>{
    const button=document.createElement('button');button.textContent=String(i+1);button.setAttribute('aria-label','Выбрать точку '+(i+1));
    button.onclick=()=>{state.epoch=1;select(p.x,p.y);};$('opening-points').append(button);
  });
  $('opening-points').parentElement.ontoggle=()=>{if($('opening-points').parentElement.open){stop();state.epoch=1;}draw();};
  motion.addEventListener('change',()=>{if(motion.matches){stop();draw();}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();draw();}});
  window.opening={state,activate,suspend,reset,refresh,select};
})();
