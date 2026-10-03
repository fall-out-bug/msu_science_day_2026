/* The observatory connects earned tests, installed tools and an independent run. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const state={view:'opening',visited:{tracking:false,brightness:false},installed:{movement:false,fading:false},finished:false};
  const sections={opening:'opening',overview:'overview',tracking:'tracking-episode',brightness:'brightness-episode',launch:'launch-episode'};
  const scrollTo=id=>{const node=$(id);node.focus({preventScroll:true});node.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});};
  const earned=()=>({movement:comparisonProbe.state.journal.length>0,fading:brightnessEpisode.state.earned});
  const ready=()=>state.installed.movement&&state.installed.fading;
  function storyEntry(){return comparisonProbe.state.journal.find(entry=>entry.caseId==='s02'&&entry.result.outcome==='moving'&&Math.hypot(entry.selection.point.x-58,entry.selection.point.y-68)<=4);}
  function nextAction(){
    const done=earned();
    if(!done.movement)return {kind:'test',route:'tracking',title:'Испытать поиск движения →',line:'Я Ника. Помоги мне собрать прибор, который сам ищет изменения на снимках. Сначала проверим поиск движения.'};
    if(!state.installed.movement)return {kind:'install',mode:'movement',title:'Установить поиск движения',line:'Точка оказалась рядом с прогнозом! Поиск движения прошёл испытание. Установи этот инструмент: потом он сам просмотрит точки на другом участке.'};
    if(!done.fading)return {kind:'test',route:'brightness',title:'Испытать измеритель света →',line:'Поиск движения готов. Но точка может остаться на месте и стать слабее. Проверим второй инструмент — он измеряет изменение света.'};
    if(!state.installed.fading)return {kind:'install',mode:'fading',title:'Установить измеритель света',line:'Ты проверил: свет в выбранной области ослаб. Добавим измеритель света — теперь прибор сможет искать два разных изменения.'};
    return {kind:'test',route:'launch',title:state.finished?'Продолжить самостоятельный поиск →':'Запустить свой прибор →',line:state.finished?'Смена завершена. Результаты остались в журнале. Можешь взять другой участок или сравнить два способа поиска.':'Прибор собран. Другая подборка уже на пульте. Теперь ты выбираешь, что искать, а прибор просматривает точки и предлагает, что проверить.'};
  }
  function refresh(){
    const tracking=comparisonProbe.state,brightness=brightnessEpisode.state,done=earned(),total=Number(done.movement)+Number(done.fading),installed=Number(state.installed.movement)+Number(state.installed.fading);
    $('nav-total').textContent=state.finished?'Смена завершена':installed+' / 2 инструмента';
    $('overview-count').textContent=total+' / 2';
    for(const view of Object.keys(sections)){const button=$('nav-'+view);if(!button)continue;if(state.view===view)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}
    for(const [view,mode] of [['tracking','movement'],['brightness','fading']]){
      const status=done[mode]?'Завершён':state.visited[view]?'В процессе':'Не начат';
      $('nav-'+view+'-status').textContent=status;
      $('card-'+view).textContent=(done[mode]?'Открыть':state.visited[view]?'Продолжить':'Начать')+' испытание';
      $('card-'+view+'-status').textContent=status+(done[mode]?' · инструмент проверен':'');
    }
    $('nav-launch-status').textContent=state.finished?'Смена завершена':ready()?'Прибор готов':'Сначала собери прибор';
    $('tracking-completion').hidden=!done.movement;$('brightness-completion').hidden=!done.fading;
    $('brightness-to-overview').textContent='В обсерваторию · установить инструмент →';
    $('journey-finished').hidden=!state.finished;
    $('overview-heading').textContent=state.finished?'Первая смена завершена':ready()?'Прибор готов к работе':installed?'Обсерватория оживает':'Откроем небо вместе';
    $('overview-copy').textContent=ready()?'Выбери задачу. Прибор найдёт предложения, а ты решишь, что показали снимки.':'Собери прибор, который поможет искать изменения среди звёзд.';
    $('shift-chapter').textContent=state.finished?'СМЕНА ЗАВЕРШЕНА':ready()?'03 · САМОСТОЯТЕЛЬНЫЙ ЗАПУСК':'01–02 · ИСПЫТАТЬ И СОБРАТЬ ПРИБОР';
    const action=nextAction();$('nika-line').textContent=action.line;$('shift-action').textContent=action.title;
    const stage=$('observatory-stage');stage.dataset.motion=state.installed.movement?'ready':'locked';stage.dataset.light=state.installed.fading?'ready':'locked';stage.dataset.phase=state.finished?'finished':window.launchEpisode?.state.phase==='scanning'?'scanning':'ready';
    $('stage-motion-label').textContent='Поиск движения · '+(state.installed.movement?'установлен':'не установлен');
    $('stage-light-label').textContent='Измеритель света · '+(state.installed.fading?'установлен':'не установлен');
    $('overview-tracking-story').hidden=!tracking.journal.length;$('overview-brightness-story').hidden=!done.fading;
    const entry=storyEntry();$('tracking-story').hidden=!entry;$('track-story-open').hidden=!entry;
    if(entry){
      $('tracking-story-title').textContent='Ты проследил астероид (2948) Amosov';
      $('tracking-story-copy').textContent='Эти наблюдения ZTF сделаны 25 марта 2025 года. Положения найденной точки согласуются с каталогом известного астероида (2948) Amosov. Ты связал наблюдения и проверил продолжение движения.';
      $('tracking-catalog-link').href='https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=2948';
      const points=entry.result.positions;
      $('tracking-story-trail').innerHTML='<polyline points="'+points.map(p=>p.x+','+p.y).join(' ')+'" fill="none" stroke="#8de1ce" stroke-width="1.5"/>'+points.map((p,i)=>'<circle cx="'+p.x+'" cy="'+p.y+'" r="3" fill="#effbf5"/><text x="'+(p.x+5)+'" y="'+(p.y-4)+'" fill="#d4eaf3" font-size="8">'+(i+1)+'</text>').join('');
      $('tracking-story-next').textContent='В обсерваторию · установить инструмент →';
    }
    window.opening?.refresh();
    if(state.finished&&window.launchEpisode){
      const records=launchEpisode.state.records,fields=new Set(records.map(r=>r.caseId)).size,confirmed=records.filter(r=>['moving','faded'].includes(r.result?.outcome)).length;
      $('shift-summary').textContent='Исследовано участков: '+fields+'. Сохранено проверок: '+records.length+'. Подтверждённых изменений: '+confirmed+'. '+(confirmed?'Открой журнал, чтобы снова увидеть следы и измерения.':'В этих запусках подтверждённых изменений нет. Другой способ поиска может дать другие предложения.');
    }
  }
  function show(view,push=true){
    if(!Object.hasOwn(sections,view))view='opening';
    if(view!==state.view){comparisonProbe.suspend();brightnessEpisode.suspend();window.launchEpisode?.suspend();window.opening?.suspend();}
    state.view=view;document.body.dataset.opening=String(view==='opening');if(view==='tracking'||view==='brightness')state.visited[view]=true;
    for(const [key,id] of Object.entries(sections))$(id).hidden=key!==view;
    if(view==='brightness'){comparisonProbe.game.scene.pause();brightnessEpisode.activate();}
    else if(view==='tracking'){comparisonProbe.game.scene.resume();comparisonProbe.refresh();}
    else comparisonProbe.game.scene.pause();
    if(view==='overview'||view==='launch')$(view==='overview'?'overview-art-slot':'launch-art-slot').append($('observatory-stage'));
    if(view==='launch')window.launchEpisode?.activate();
    if(view==='opening')window.opening?.activate();
    refresh();
    if(push&&location.hash!==('#'+view))history.pushState({view},'','#'+view);
    $(view==='opening'?'opening-heading':view==='overview'?'overview-heading':view==='tracking'?'tracking-heading':view==='brightness'?'brightness-heading':'launch-heading').focus({preventScroll:true});
    window.scrollTo({top:0,behavior:'instant'});
  }
  function reset(){
    comparisonProbe.reset();brightnessEpisode.reset();window.launchEpisode?.reset();window.opening?.reset();
    state.visited={tracking:false,brightness:false};state.installed={movement:false,fading:false};state.finished=false;
    $('shift-feedback').textContent='';$('episode-directory').open=false;show('opening');
  }
  function finish(){if(window.launchEpisode?.canFinish()){state.finished=true;show('overview');}}
  for(const button of document.querySelectorAll('[data-route]'))button.addEventListener('click',()=>show(button.dataset.route));
  $('shift-action').onclick=()=>{
    const action=nextAction();
    if(action.kind==='install'){
      state.installed[action.mode]=true;refresh();
      $('shift-feedback').textContent=action.mode==='movement'?'Поиск движения установлен: на пульте загорелся голубой экран.':'Измеритель света установлен: на пульте загорелся янтарный экран.';
      $('observatory-stage').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'center'});
    }else{$('shift-feedback').textContent='';show(action.route);}
  };
  $('track-story-open').onclick=()=>scrollTo('tracking-story');
  $('tracking-story-return').onclick=()=>{comparisonProbe.openSaved('s02');scrollTo('outcome-panel');};
  $('tracking-story-next').onclick=()=>show('overview');
  $('overview-tracking-story').onclick=()=>{comparisonProbe.openSaved('s02');show('tracking');scrollTo('tracking-story');};
  $('overview-brightness-story').onclick=()=>{show('brightness');$('brightness-open-saved').click();brightnessEpisode.reveal();};
  $('journey-reset').onclick=reset;$('restart').onclick=reset;$('brightness-restart').onclick=reset;
  window.addEventListener('popstate',()=>show(location.hash.slice(1),false));
  window.journey={state,show,refresh,reset,ready,finish};
  show(location.hash.slice(1)||'opening',false);
})();
