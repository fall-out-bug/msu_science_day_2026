/* Archive brightness comparison. Measurement precedes historical identification. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const data = BRIGHTNESS_DATA;
  const state = {active:false,phase:'search',view:0,difference:false,selection:null,result:null,attempts:[],earned:false,storyOpen:false};
  let timer, generation=0;
  const narrow=()=>matchMedia('(max-width:760px)').matches;
  const reduced=()=>matchMedia('(prefers-reduced-motion:reduce)').matches;
  const say=text=>{$('brightness-feedback').textContent=text;};
  const historyMatches=result=>result?.outcome==='faded' &&
    Math.hypot(result.point.x-data.historical.point.x,result.point.y-data.historical.point.y)<=data.historical.associationRadiusPx;
  function start(){
    if(comparisonProbe.state.journal.length<2)return;
    state.active=true;$('tracking-episode').hidden=true;$('brightness-episode').hidden=false;
    comparisonProbe.game.scene.pause();
    update();$('brightness-heading').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});
  }
  function back(){
    clearTimeout(timer);generation++;
    if(state.phase==='measuring'){state.phase='search';say('Измерение прервано. Твой выбор сохранён — можно проверить его снова.');}
    state.active=false;$('brightness-episode').hidden=true;$('tracking-episode').hidden=false;
    comparisonProbe.game.scene.resume();
    $('brightness-invitation').scrollIntoView({behavior:'instant',block:'center'});$('start-brightness').focus({preventScroll:true});
  }
  function reset(){
    clearTimeout(timer);generation++;
    Object.assign(state,{phase:'search',view:0,difference:false,selection:null,result:null,attempts:[],earned:false,storyOpen:false});
    $('brightness-help').open=false;$('brightness-point-tools').open=false;
    say('Ищи изменение света. Положение точки может остаться прежним.');update();
  }
  function choose(x,y){
    if(!state.active||state.phase!=='search')return;
    const selected=BrightnessModel.select(data,x,y);
    state.selection=selected.status==='selected'?selected:null;
    say(selected.status==='selected'?'Точка выбрана. Кольца показывают одну и ту же область на обеих датах. Нажми «Измерить изменение».':selected.status==='ambiguous'?'Рядом несколько точек. Нажми точнее или выбери номер под снимками.':'В этом месте на первом снимке нет выделенной яркой точки. Выбери светлую точку или её номер под снимками.');
    update();
  }
  function measure(){
    if(!state.active||state.phase!=='search'||!state.selection)return;
    const submitted=Object.freeze({selection:state.selection,difference:state.difference});
    const token=++generation;state.phase='measuring';say('Измеряем свет внутри колец. Сравниваем одну и ту же область на двух датах…');update();
    timer=setTimeout(()=>{
      if(token!==generation||!state.active)return;
      const result=BrightnessModel.measure(data,submitted.selection);
      state.result=result;state.phase='result';state.attempts.push(Object.freeze({...submitted,result}));
      if(historyMatches(result))state.earned=true;
      say(result.outcome==='faded'?'Свет в выбранной области ослаб. На шкале измерения видно, сколько изменившегося света осталось.':result.outcome==='stable'?'У этой яркой области нет большого изменения. Попробуй найти точку, которая стала заметно слабее.':'По этой области надёжного сравнения не получилось. Попробуй другую точку; подсказка под снимками поможет увидеть изменения.');
      update();$('brightness-outcome').focus({preventScroll:true});
      if(narrow())$('brightness-outcome').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'nearest'});
    },reduced()?100:700);
  }
  function retry(){
    if(state.phase==='measuring')return;
    state.phase='search';state.selection=null;state.result=null;state.storyOpen=false;
    say('Проверь другую точку. Предыдущее измерение сохранено; режим изображения остался прежним.');update();
  }
  function reveal(){
    if(!historyMatches(state.result))return;
    state.storyOpen=true;update();$('brightness-story').focus({preventScroll:true});
    $('brightness-story').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'start'});
  }
  function setDifference(value){
    if(state.phase==='measuring')return;
    state.difference=!!value;
    say(state.difference?'Свет, который совпадает с архивным снимком, приглушён. Голубым показано, где стало ярче, оранжевым — где слабее. Некоторые следы могут быть помехами.':'Снова видны обычные снимки. Выбранная область и результат измерения сохраняются.');update();
  }
  function draw(canvas,epoch){
    const raw=document.createElement('canvas');raw.width=raw.height=128;
    const source=(state.difference?data.differenceArrays:data.arrays)[epoch];
    const top=state.difference?data.differenceDisplayTop:data.displayTop;
    const image=new ImageData(128,128),base=[8,14,29];
    for(let i=0;i<source.length;i++){
      const value=source[i],strength=Math.min(1,Math.asinh(Math.abs(value)*.2)/Math.asinh(top*.2));
      const visible=value<0&&!state.difference?0:strength;
      const color=value<0?[255,189,124]:[204,242,255];
      for(let c=0;c<3;c++)image.data[i*4+c]=base[c]+(color[c]-base[c])*visible;
      image.data[i*4+3]=255;
    }
    raw.getContext('2d').putImageData(image,0,0);
    const ctx=canvas.getContext('2d');ctx.drawImage(raw,0,0,512,512);
    const point=state.selection?.point;
    if(point){ctx.strokeStyle='#a2f1d4';ctx.lineWidth=2.5;ctx.beginPath();ctx.arc((point.x+.5)*4,(point.y+.5)*4,18,0,2*Math.PI);ctx.stroke();}
    if($('brightness-point-tools').open){
      ctx.font='20px system-ui';ctx.textBaseline='top';
      data.sources[0].forEach((p,i)=>{const x=Math.min(485,Math.max(4,(p.x+.5)*4+12)),y=Math.min(484,Math.max(4,(p.y+.5)*4-23));ctx.fillStyle='#102033';ctx.fillRect(x-2,y-1,25,25);ctx.fillStyle='#ffe0a3';ctx.fillText(String(i+1),x,y);});
    }
    if(state.phase==='measuring'){
      ctx.fillStyle='#09172799';ctx.fillRect(0,0,512,512);
      if(point){ctx.strokeStyle='#b1f9e3';ctx.lineWidth=3;ctx.beginPath();ctx.arc((point.x+.5)*4,(point.y+.5)*4,18,0,2*Math.PI);ctx.stroke();}
      ctx.fillStyle='#d6faef';ctx.font='21px system-ui';ctx.textAlign='center';ctx.fillText('Измеряем свет…',256,470);ctx.textAlign='start';
    }
  }
  function chart(result){
    let first,second,label;
    if(result.outcome==='faded'){
      first=result.firstFlux;second=result.secondFlux;label='Изменившийся свет в выбранной области';
    }else if(result.outcome==='stable'){
      first=result.measurements[0].scienceFlux;second=result.measurements[1].scienceFlux;label='Общая яркость выбранной области';
    }
    const valid=Number.isFinite(first)&&first>0&&Number.isFinite(second)&&second>=0;
    $('brightness-chart').hidden=!valid;
    if(!valid)return;
    const percent=Math.round(second/first*100),maximum=Math.max(100,percent);
    $('brightness-chart-label').textContent=label;
    $('brightness-bar-first').style.width=100/maximum*100+'%';
    $('brightness-bar-second').style.width=percent/maximum*100+'%';
    $('brightness-value-first').textContent='100';$('brightness-value-second').textContent=String(percent);
    $('brightness-chart-note').textContent='Относительная шкала: свет 7 октября принят за 100.';
  }
  function update(){
    const result=state.result,checking=state.phase==='measuring';
    $('brightness-choice').hidden=!!result;$('brightness-outcome').hidden=!result;
    $('brightness-measure').disabled=!state.selection||state.phase!=='search';
    $('brightness-measure').textContent=checking?'Измеряем…':state.selection?'Измерить изменение':'Сначала выбери точку';
    $('brightness-help').hidden=false;$('brightness-difference').disabled=checking;
    $('brightness-difference').setAttribute('aria-pressed',String(state.difference));
    $('brightness-difference').textContent=state.difference?'Вернуть обычные снимки':'Показать изменившийся свет';
    $('brightness-image-key').textContent=state.difference?'Сравнение с архивным снимком: голубое — ярче, оранжевое — слабее.':'Одинаковое место на обоих снимках. Кольцо отметит твой выбор.';
    $('brightness-instruction').textContent=checking?'Прибор измеряет свет':result?'Сравни свет в отмеченной области':'Выбери точку на первом снимке';
    for(const [i,id] of ['brightness-tab-first','brightness-tab-second'].entries())$(id).setAttribute('aria-pressed',String(state.view===i));
    $('brightness-first-frame').hidden=narrow()&&state.view!==0;$('brightness-second-frame').hidden=narrow()&&state.view!==1;
    $('brightness-point-tools').hidden=state.phase!=='search';
    $('brightness-point-list').replaceChildren();
    data.sources[0].forEach((p,i)=>{const button=document.createElement('button');button.textContent=String(i+1);button.setAttribute('aria-label',`Проверить точку ${i+1}`);button.setAttribute('aria-pressed',String(state.selection?.point.x===p.x&&state.selection?.point.y===p.y));button.onclick=()=>choose(p.x,p.y);$('brightness-point-list').append(button);});
    $('brightness-story').hidden=!state.storyOpen;
    $('brightness-step-find').classList.toggle('active',state.phase==='search');
    $('brightness-step-check').classList.toggle('active',state.phase!=='search'&&!state.storyOpen);
    $('brightness-step-story').classList.toggle('active',state.storyOpen);
    $('brightness-open-saved').hidden=!state.earned;
    $('brightness-earned').textContent=state.earned?'Свет проверен':'—';
    $('brightness-journal-copy').textContent=state.earned?'Изменение света подтверждено по двум датам. Твоя находка и история объекта доступны в этом эпизоде.':'Сюда добавится проверенное изменение света.';
    if(result){
      const copy={faded:['ИЗМЕНЕНИЕ ПОДТВЕРДИЛОСЬ','Свет заметно ослаб','Ты заметил ослабление света. Чтобы измерить его, прибор сравнил одну и ту же область после вычитания постоянного света.'],stable:['БОЛЬШОГО ИЗМЕНЕНИЯ НЕТ','Эта область почти такая же яркая','Её общая яркость изменилась мало. Здесь заметного ослабления не подтвердилось. Попробуй другую точку.'],unresolved:['НУЖНА ДРУГАЯ ПРОВЕРКА','Не хватает надёжного сигнала','Здесь измерению мешает слабый сигнал, шум или край снимка. Это не доказывает, что источник не менялся. Проверь другую область.']}[result.outcome];
      $('brightness-outcome-tag').textContent=copy[0];$('brightness-outcome-title').textContent=copy[1];$('brightness-outcome-copy').textContent=copy[2];
      if(result.reason==='incomplete_background_annulus'){$('brightness-outcome-title').textContent='Эта точка слишком близко к краю';$('brightness-outcome-copy').textContent='Для измерения нужен и свет точки, и фон вокруг неё. Часть этой области за краем снимка. Выбери точку подальше от края.';}
      chart(result);$('brightness-measurement-note').textContent=result.outcome==='faded'?'Измерена небольшая область снимка. Она может включать свет соседних источников.':'Мы ищем заметное изменение; небольшая разница может быть связана с условиями съёмки.';
      $('brightness-reveal').hidden=!historyMatches(result);
    }
    if(state.active){draw($('brightness-first'),0);draw($('brightness-second'),1);}
  }
  for(const [epoch,id] of ['brightness-first','brightness-second'].entries())$(id).addEventListener('pointerdown',event=>{
    if(state.phase!=='search')return;
    if(epoch!==0){say('Выбери эту область на первом снимке — там источник был ярче. На телефоне нажми вкладку «7 октября».');return;}
    const rect=event.currentTarget.getBoundingClientRect();choose((event.clientX-rect.left)/rect.width*128-.5,(event.clientY-rect.top)/rect.height*128-.5);
  });
  $('start-brightness').onclick=start;$('brightness-back').onclick=back;
  $('brightness-open-saved').onclick=()=>{const saved=state.attempts.find(a=>historyMatches(a.result));if(!saved)return;clearTimeout(timer);generation++;state.selection=saved.selection;state.result=saved.result;state.phase='result';state.storyOpen=false;say('Открыто твоё сохранённое измерение. Это прежний результат, а не новая попытка.');update();$('brightness-outcome').focus({preventScroll:true});$('brightness-outcome').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'center'});};
  $('brightness-measure').onclick=measure;$('brightness-retry').onclick=retry;$('brightness-reveal').onclick=reveal;
  $('brightness-difference').onclick=()=>setDifference(!state.difference);
  $('brightness-tab-first').onclick=()=>{state.view=0;update();};$('brightness-tab-second').onclick=()=>{state.view=1;update();};
  $('brightness-point-tools').ontoggle=()=>{if(state.active)update();};
  $('brightness-return-observation').onclick=()=>{$('brightness-outcome').focus({preventScroll:true});$('brightness-outcome').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'center'});};
  $('brightness-restart').onclick=()=>{reset();back();comparisonProbe.reset();window.scrollTo({top:0,behavior:'instant'});};
  $('restart').addEventListener('click',reset);
  matchMedia('(max-width:760px)').addEventListener('change',()=>{if(state.active)update();});
  window.brightnessEpisode={state,start,back,reset,choose,measure,retry,reveal,setDifference};
})();
