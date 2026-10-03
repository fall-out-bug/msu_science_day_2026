/* Shared navigation. Outcomes complete episodes; reading a story is optional. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const state={view:'overview',visited:{tracking:false,brightness:false}};
  const sections={overview:'overview',tracking:'tracking-episode',brightness:'brightness-episode'};
  const histories={
    s02:{name:'(2948) Amosov',number:2948,x:58,y:68,date:'25 марта 2025 года'},
    s07:{name:'(8936) Gianni',number:8936,x:59,y:65,date:'2 января 2020 года'}
  };
  const scrollTo=id=>{
    const node=$(id);node.focus({preventScroll:true});
    node.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});
  };
  function storyEntry(){
    const tracking=comparisonProbe.state;
    const caseId=COMPARISON_DATA.cases[tracking.field].id;
    return tracking.journal.find(entry=>entry.caseId===caseId&&histories[caseId]&&
      entry.result.outcome==='moving'&&Math.hypot(entry.selection.point.x-histories[caseId].x,entry.selection.point.y-histories[caseId].y)<=4);
  }
  function refresh(){
    const tracking=comparisonProbe.state,brightness=brightnessEpisode.state;
    const doneTracking=tracking.journal.length===2,doneBrightness=brightness.earned;
    const total=Number(doneTracking)+Number(doneBrightness);
    $('nav-total').textContent=`${total} / 2 завершено`;
    $('overview-count').textContent=`${total} / 2`;
    const statuses={tracking:doneTracking?'Завершён':state.visited.tracking?'В процессе':'Не начат',brightness:doneBrightness?'Завершён':state.visited.brightness?'В процессе':'Не начат'};
    for(const view of Object.keys(sections)){
      const button=$('nav-'+view);
      if(state.view===view)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
      if(view==='overview')continue;
      $('nav-'+view+'-status').textContent=statuses[view];
      $('card-'+view).textContent=(statuses[view]==='Не начат'?'Начать':statuses[view]==='Завершён'?'Открыть':'Продолжить')+` эпизод ${view==='tracking'?1:2}`;
    }
    $('card-tracking-status').textContent=`${statuses.tracking} · ${tracking.journal.length} из 2 следов`;
    $('card-brightness-status').textContent=`${statuses.brightness} · ${doneBrightness?'изменение света проверено':'измерение ещё не завершено'}`;
    $('tracking-completion').hidden=!doneTracking;
    $('brightness-completion').hidden=!doneBrightness;
    $('brightness-to-overview').textContent=total===2?'К итогам двух эпизодов →':'К списку эпизодов →';
    $('journey-finished').hidden=total!==2;
    $('overview-heading').textContent=total===2?'Исследование завершено':'Что меняется в небе?';
    $('overview-copy').textContent=total===2?'Ты проверил движение и изменение света. Можно открыть результаты каждого эпизода, прочитать истории объектов или начать новую игру.':'Сначала проследи движение астероидов, затем измерь свет сверхновой. Можно открыть любой эпизод и вернуться к нему позже.';
    $('overview-tracking-story').hidden=!tracking.journal.length;
    $('overview-brightness-story').hidden=!doneBrightness;
    const entry=storyEntry();
    $('tracking-story').hidden=!entry;$('track-story-open').hidden=!entry;
    if(entry){
      const history=histories[entry.caseId];
      $('tracking-story-title').textContent=`Ты проследил астероид ${history.name}`;
      $('tracking-story-copy').textContent=`Эти наблюдения ZTF сделаны ${history.date}. Положения найденной точки согласуются с каталогом известного астероида ${history.name}. Ты повторил важную часть работы астронома: связал наблюдения и проверил продолжение движения.`;
      $('tracking-catalog-link').href=`https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=${history.number}`;
      const points=entry.result.positions;
      $('tracking-story-trail').innerHTML=`<polyline points="${points.map(p=>`${p.x},${p.y}`).join(' ')}" fill="none" stroke="#8de1ce" stroke-width="1.5"/>${points.map((p,i)=>`<circle cx="${p.x}" cy="${p.y}" r="3" fill="#effbf5"/><text x="${p.x+5}" y="${p.y-4}" fill="#d4eaf3" font-size="8">${i+1}</text>`).join('')}`;
      $('tracking-story-next').textContent=doneTracking?'К эпизоду 2 «Свет сверхновой» →':'Открыть участок 2 · ещё один астероид →';
    }
  }
  function show(view,push=true){
    if(!Object.hasOwn(sections,view))view='overview';
    if(view!==state.view){comparisonProbe.suspend();brightnessEpisode.suspend();}
    state.view=view;if(view!=='overview')state.visited[view]=true;
    for(const [key,id] of Object.entries(sections))$(id).hidden=key!==view;
    if(view==='brightness'){
      comparisonProbe.game.scene.pause();brightnessEpisode.activate();
    }else if(view==='tracking'){
      comparisonProbe.game.scene.resume();comparisonProbe.refresh();
    }else comparisonProbe.game.scene.pause();
    refresh();
    if(push&&location.hash!==`#${view}`)history.pushState({view},'',`#${view}`);
    $(view==='overview'?'overview-heading':view==='tracking'?'tracking-heading':'brightness-heading').focus({preventScroll:true});
    window.scrollTo({top:0,behavior:'instant'});
  }
  function reset(){
    comparisonProbe.reset();brightnessEpisode.reset();
    state.visited={tracking:false,brightness:false};show('overview');
  }
  for(const button of document.querySelectorAll('[data-route]'))button.addEventListener('click',()=>show(button.dataset.route));
  $('track-story-open').onclick=()=>scrollTo('tracking-story');
  $('tracking-story-return').onclick=()=>{
    const entry=storyEntry();if(entry)comparisonProbe.openSaved(entry.caseId);scrollTo('outcome-panel');
  };
  $('tracking-story-next').onclick=()=>{
    if(comparisonProbe.state.journal.length===2)show('brightness');
    else{comparisonProbe.openSaved('s02');comparisonProbe.nextField();}
  };
  $('overview-tracking-story').onclick=()=>{comparisonProbe.openSaved('s02');show('tracking');scrollTo('tracking-story');};
  $('overview-brightness-story').onclick=()=>{show('brightness');$('brightness-open-saved').click();brightnessEpisode.reveal();};
  $('journey-reset').onclick=reset;$('restart').onclick=reset;$('brightness-restart').onclick=reset;
  window.addEventListener('popstate',()=>show(location.hash.slice(1),false));
  window.journey={state,show,refresh,reset};
  show(location.hash.slice(1)||'overview',false);
})();
