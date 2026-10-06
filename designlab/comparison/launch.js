/* An automatic search whose proposals, checks and saved records stay distinct. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),cases=LAUNCH_DATA.cases;
  const state={active:false,phase:'idle',caseId:cases[0].id,mode:'movement',scan:null,selected:null,result:null,records:[]};
  let timer,generation=0;
  const current=()=>cases.find(c=>c.id===state.caseId);
  const reduced=()=>matchMedia('(prefers-reduced-motion:reduce)').matches;
  const say=message=>{$('launch-feedback').textContent=message;};
  const date=value=>new Date(value).toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
  const method=mode=>mode==='movement'?'Поиск движения':'Измеритель света';
  const canFinish=()=>new Set(state.records.map(record=>record.caseId)).size>=2;
  function imageCanvas(data,epoch){
    const canvas=document.createElement('canvas');canvas.width=canvas.height=128;
    const source=epoch===0?{...data,arrays:[data.arrays[0],data.arrays[0]]}:data;
    const pixels=ComparisonModel.render(source,0,epoch||1).pixels;
    canvas.getContext('2d').putImageData(new ImageData(pixels,128,128),0,0);
    return canvas;
  }
  function drawSky(){
    const canvas=$('launch-sky'),ctx=canvas.getContext('2d'),data=current();
    const epoch=state.mode==='movement'?1:0;
    ctx.drawImage(imageCanvas(data,epoch),0,0,512,512);
    state.scan.candidates.forEach((candidate,i)=>{
      const x=(candidate.point.x+.5)*4,y=(candidate.point.y+.5)*4;
      ctx.strokeStyle=state.selected?.id===candidate.id?'#fff3d2':'#9bf4d6';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,18,0,Math.PI*2);ctx.stroke();
      ctx.fillStyle='#091827';ctx.fillRect(Math.min(481,x+16),Math.max(1,y-28),27,25);
      ctx.font='bold 18px system-ui';ctx.textAlign='left';ctx.fillStyle='#fff0c6';ctx.fillText(String(i+1),Math.min(485,x+20),Math.max(19,y-9));
    });
    $('launch-sky-caption').textContent=data.name+' · '+date(data.dates[epoch])+'. '+(state.scan.candidates.length?'Кольцами отмечены предложения прибора.':'Прибор не выделил предложений этим способом.');
  }
  function evidenceCopy(result,mode){
    if(mode==='movement'){
      if(result.outcome==='moving')return {title:'Следующее наблюдение подтвердило движение',copy:'Прибор связал две точки и рассчитал, где искать продолжение. На третьем снимке источник оказался рядом с прогнозом.',detail:'Расстояние от прогноза до найденной точки: '+result.distancePx.toFixed(2)+' пикселя. Три положения ещё не определяют орбиту.'};
      return {title:'Однозначный след не подтвердился',copy:'Третий снимок не подтверждает предложенное продолжение движения. Сохрани этот исход: предположение прибора тоже нужно проверять.',detail:'Причиной могут быть неоднозначная связь точек, слабый источник или условия съёмки. Это не доказывает, что объект неподвижен.'};
    }
    const ratio=Math.round(result.ratio*100),third=Number.isFinite(result.thirdFlux)?Math.round(result.thirdFlux/result.firstFlux*100):null;
    return {title:result.thirdOutcome==='rebrightened'?'Сначала слабее — потом снова ярче':'Свет на втором снимке ослаб',copy:'На первых двух снимках прибор заметил ослабление: 100 → '+ratio+'. '+(result.thirdOutcome==='rebrightened'?'Но на третьем снимке уже '+third+'. Значит, по первой паре нельзя было заключить, что источник продолжит угасать.':'Третий снимок помогает проверить, что происходило дальше.'),detail:'Относительная шкала: свет в одной небольшой области на первом снимке принят за 100. Измерен свет с вычетом местного фона; он может включать соседние источники. Повтор измерения первых двух снимков не является независимой проверкой. Период и тип объекта по трём датам не определены.'};
  }
  function showEvidence(){
    const data=current(),result=state.result,copy=evidenceCopy(result,state.mode);
    $('launch-evidence-heading').textContent=copy.title;$('launch-evidence-copy').textContent=copy.copy;$('launch-evidence-detail').textContent=copy.detail;
    const frames=$('launch-evidence-frames');frames.replaceChildren();
    for(let epoch=0;epoch<3;epoch++){
      const figure=document.createElement('figure'),canvas=document.createElement('canvas'),caption=document.createElement('figcaption');
      canvas.width=canvas.height=180;
      const point=state.mode==='movement'?(result.positions?.[epoch]||(epoch===2?state.selected.prediction:state.selected.point)):state.selected.point;
      const target=point||state.selected.point,x=Math.max(0,Math.min(98,target.x-15)),y=Math.max(0,Math.min(98,target.y-15));
      const ctx=canvas.getContext('2d');ctx.drawImage(imageCanvas(data,epoch),x,y,30,30,0,0,180,180);
      if(point){ctx.strokeStyle='#aff2d9';ctx.lineWidth=2;ctx.beginPath();ctx.arc((point.x+.5-x)*6,(point.y+.5-y)*6,state.mode==='movement'?10:24,0,Math.PI*2);ctx.stroke();}
      if(state.mode==='movement'&&epoch===2&&result.prediction){
        ctx.setLineDash([4,3]);ctx.strokeStyle='#f5d199';ctx.beginPath();ctx.arc((result.prediction.x+.5-x)*6,(result.prediction.y+.5-y)*6,18,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);
      }
      const values=[result.firstFlux,result.secondFlux,result.thirdFlux];
      caption.textContent=date(data.dates[epoch])+(state.mode==='fading'&&Number.isFinite(values[epoch])?' · свет '+Math.round(values[epoch]/result.firstFlux*100):epoch===2?' · проверка прогноза':' · положение '+(epoch+1));
      figure.append(canvas,caption);frames.append(figure);
    }
    const known=state.caseId==='launch-motion'&&result.outcome==='moving'&&Math.hypot(state.selected.point.x-59,state.selected.point.y-65)<4;
    $('launch-history').hidden=!known;
    $('launch-history').textContent='По архивному сопоставлению с каталогом этот след принадлежит астероиду (8936) Gianni. Ты проверил движение известного объекта. Имя не участвовало в автоматическом поиске. Мятное кольцо — найденная точка, пунктирное янтарное — прогноз.';
    const saved=state.records.some(r=>r.caseId===state.caseId&&r.mode===state.mode&&r.candidate?.id===state.selected.id);
    $('launch-save').disabled=saved;$('launch-save').textContent=saved?'Проверка сохранена в журнале':'Сохранить результат проверки';
  }
  function renderLog(){
    $('launch-log-count').textContent=new Set(state.records.map(r=>r.caseId)).size+' / 2 участка';
    $('launch-log-empty').hidden=!!state.records.length;
    $('launch-log-list').replaceChildren();
    state.records.forEach(record=>{
      const article=document.createElement('article'),title=document.createElement('strong'),copy=document.createElement('p'),button=document.createElement('button');
      title.textContent=cases.find(c=>c.id===record.caseId).name+' · '+method(record.mode);
      copy.textContent=record.result?evidenceCopy(record.result,record.mode).title:record.scan.reason==='insufficient_stable_field_controls'?'Условия снимков не позволили надёжно сравнить свет.':'Поиск не выделил кандидатов. Другие изменения не исключены.';
      button.className='secondary';button.textContent='Открыть сохранённый запуск';button.onclick=()=>{
        suspend();Object.assign(state,{active:true,caseId:record.caseId,mode:record.mode,phase:'result',scan:record.scan,selected:record.candidate,result:record.result});
        say('Открыт сохранённый запуск. Новая проверка не добавлена.');update();$('launch-results').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'start'});
      };
      article.append(title,copy,button);$('launch-log-list').append(article);
    });
    $('launch-next-field').hidden=!state.records.length;
    $('launch-finish').hidden=!canFinish();$('launch-finish').textContent=window.journey?.state.finished?'Вернуться к итогам смены →':'Завершить смену · посмотреть результат →';
  }
  function update(){
    const unlocked=window.journey?.ready()||false,scanning=state.phase==='scanning';
    $('launch-locked').hidden=unlocked;$('launch-workspace').hidden=!unlocked;
    $('launch-field').value=state.caseId;
    $('launch-field-description').textContent=current().dates.map(date).join(' → ');
    $('launch-field').disabled=scanning;
    for(const input of document.querySelectorAll('input[name="launch-mode"]')){input.checked=input.value===state.mode;input.disabled=scanning;}
    $('launch-run').disabled=!unlocked||scanning;$('launch-run').textContent=scanning?'Прибор просматривает точки…':'Запустить поиск →';
    $('launch-results').hidden=!state.scan;
    $('launch-evidence').hidden=!state.result;
    if(state.scan){
      const n=state.scan.candidates.length;
      $('launch-method-label').textContent=method(state.mode)+' · '+current().name;
      $('launch-result-heading').textContent=n?'Точек для проверки: '+n:'Подходящих предложений нет';
      $('launch-count-copy').textContent='Просмотрено ярких точек: '+state.scan.inspectedCount+'. '+(n?'Прибор выделил '+n+' для проверки. Открой данные — автоматический поиск тоже может ошибаться.':'Пустой результат тоже можно сохранить и испытать другой способ.');
      $('launch-candidate-hint').hidden=!n;$('launch-empty').hidden=!!n;
      const explanation=$('launch-empty').querySelector('p');
      explanation.textContent=state.scan.reason==='insufficient_stable_field_controls'?'Яркость контрольных точек расходится слишком сильно. Прибор не может надёжно отделить изменение источника от различий снимков. Это не результат «ничего не изменилось».':'Для этого способа подходящих точек не нашлось. Это не означает, что на участке нет других изменений.';
      $('launch-candidates').replaceChildren();
      state.scan.candidates.forEach((candidate,i)=>{
        const button=document.createElement('button');button.dataset.candidate=candidate.id;button.setAttribute('aria-pressed',String(state.selected?.id===candidate.id));
        button.textContent='Точка '+(i+1)+' · '+(state.mode==='movement'?'открыть третий снимок':'посмотреть измерение и следующую дату');
        button.onclick=()=>verify(candidate.id);$('launch-candidates').append(button);
      });
      drawSky();if(state.result)showEvidence();
      const noneSaved=state.records.some(r=>r.caseId===state.caseId&&r.mode===state.mode&&!r.candidate);
      $('launch-save-empty').disabled=noneSaved;$('launch-save-empty').textContent=noneSaved?'Результат сохранён':'Сохранить результат этого поиска';
    }
    renderLog();window.journey?.refresh();
  }
  function run(){
    if(!window.journey?.ready()||state.phase==='scanning')return;
    const token=++generation;state.phase='scanning';state.scan=null;state.result=null;state.selected=null;
    say(method(state.mode)+' просматривает точки на '+current().name.toLowerCase()+'…');update();
    timer=setTimeout(()=>{
      if(token!==generation||!state.active)return;
      state.scan=LaunchModel.scan(current(),state.mode);state.phase='result';
      say(state.scan.candidates.length?'Поиск закончен. Прибор выделил предложения. Теперь открой данные и проверь их.':'Поиск закончен. Предложений нет — посмотри причину ниже или выбери другой способ.');update();
      $('launch-result-heading').focus({preventScroll:true});$('launch-results').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'start'});
    },reduced()?60:950);
  }
  function verify(id){
    if(!state.scan||state.phase==='scanning')return;
    const candidate=state.scan.candidates.find(c=>c.id===id);if(!candidate)return;
    state.selected=candidate;state.result=LaunchModel.verify(current(),state.mode,candidate);update();
    $('launch-evidence').focus({preventScroll:true});$('launch-evidence').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'start'});
  }
  function save(){
    if(!state.scan||state.phase==='scanning'||(state.scan.candidates.length&&!state.result))return;
    const duplicate=state.records.some(r=>r.caseId===state.caseId&&r.mode===state.mode&&(r.candidate?.id||null)===(state.selected?.id||null));
    if(!duplicate)state.records.push(Object.freeze({caseId:state.caseId,mode:state.mode,scan:state.scan,candidate:state.selected,result:state.result}));
    update();say(canFinish()?'Два участка исследованы. Можно завершить смену или попробовать другой поиск.':'Результат записан. Выбери другой участок и реши, что искать там.');
    $('launch-log-list').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'nearest'});
  }
  function configure(caseId,mode){
    if(state.phase==='scanning')return;
    if(!cases.some(c=>c.id===caseId)||!['movement','fading'].includes(mode))return;
    Object.assign(state,{caseId,mode,scan:null,selected:null,result:null,phase:'idle'});
    say('Задача изменена. Запусти '+method(mode).toLowerCase()+' на '+current().name.toLowerCase()+'.');update();
  }
  function suspend(){clearTimeout(timer);generation++;if(state.phase==='scanning'){state.phase='idle';say('Запуск прерван при переходе. Выбранная задача сохранена.');}state.active=false;}
  function activate(){state.active=true;update();}
  function reset(){suspend();Object.assign(state,{phase:'idle',caseId:cases[0].id,mode:'movement',scan:null,selected:null,result:null,records:[]});say('Выбери участок и способ поиска. Прибор просмотрит точки, а ты проверишь предложения.');update();}
  for(const data of cases){const option=document.createElement('option');option.value=data.id;option.textContent=data.name;$('launch-field').append(option);}
  const saveEmpty=document.createElement('button');saveEmpty.id='launch-save-empty';saveEmpty.className='secondary';saveEmpty.textContent='Сохранить результат этого поиска';saveEmpty.onclick=save;$('launch-empty').append(saveEmpty);
  $('launch-field').onchange=event=>configure(event.target.value,state.mode);
  for(const input of document.querySelectorAll('input[name="launch-mode"]'))input.onchange=()=>configure(state.caseId,input.value);
  const returnToControls=()=>{$('launch-run').focus({preventScroll:true});document.querySelector('.launch-controls').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'center'});};
  $('launch-switch-mode').onclick=()=>{configure(state.caseId,state.mode==='movement'?'fading':'movement');returnToControls();};
  $('launch-next-field').onclick=()=>{configure(cases.find(c=>c.id!==state.caseId).id,state.mode);returnToControls();};
  $('launch-run').onclick=run;$('launch-save').onclick=save;$('launch-finish').onclick=()=>window.journey.finish();
  $('launch-sky').onclick=event=>{
    if(!state.scan)return;const rect=event.currentTarget.getBoundingClientRect(),point={x:(event.clientX-rect.left)/rect.width*128-.5,y:(event.clientY-rect.top)/rect.height*128-.5};
    const candidate=state.scan.candidates.find(c=>Math.hypot(c.point.x-point.x,c.point.y-point.y)<7);if(candidate)verify(candidate.id);
  };
  window.launchEpisode={state,activate,suspend,reset,configure,run,verify,save,canFinish,refresh:update};
})();
