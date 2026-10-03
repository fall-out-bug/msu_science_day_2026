/* The player's submitted point is the only target; a later exposure checks it. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), fields = COMPARISON_DATA.cases.slice(0, 2);
  const state = { phase:'search', field:0, amount:0, mobileView:1, selection:null, result:null, attempts:[], journal:[], revealed:{} };
  let scene, timer, generation = 0;
  const current = () => fields[state.field];
  const mobile = () => matchMedia('(max-width:760px)').matches;
  const reduced = () => matchMedia('(prefers-reduced-motion:reduce)').matches;
  const time = (item, epoch) => item.dates[epoch].slice(11,19) + ' UTC';
  const feedback = message => { $('feedback').textContent = message; };
  function pixels(item, epoch, amount=0) {
    const source = epoch === 0 ? {...item, arrays:[item.arrays[0],item.arrays[0],item.arrays[0]]} : item;
    return ComparisonModel.render(source, amount, epoch || 1).pixels;
  }
  function imageCanvas(item, epoch, amount=0) {
    const canvas = document.createElement('canvas'); canvas.width=canvas.height=128;
    canvas.getContext('2d').putImageData(new ImageData(pixels(item,epoch,amount),128,128),0,0);
    return canvas;
  }
  function crop(canvas, item, epoch, point, fullFrame=false) {
    const ctx=canvas.getContext('2d'), raw=imageCanvas(item,epoch);
    ctx.fillStyle='#080e1d';ctx.fillRect(0,0,canvas.width,canvas.height);
    if (!point) { ctx.drawImage(raw,0,0,canvas.width,canvas.height);return; }
    const size=fullFrame?128:30, x=fullFrame?0:Math.max(0,Math.min(98,point.x-15)),y=fullFrame?0:Math.max(0,Math.min(98,point.y-15));
    ctx.drawImage(raw,x,y,size,size,0,0,canvas.width,canvas.height);
    ctx.strokeStyle='#a1f2d6';ctx.lineWidth=2;ctx.beginPath();ctx.arc((point.x+.5-x)/size*canvas.width,(point.y+.5-y)/size*canvas.height,fullFrame?6:11,0,Math.PI*2);ctx.stroke();
  }
  function choose(x,y) {
    if(state.phase !== 'search') return;
    const choice=TrackingModel.select(current(),x,y);
    if(choice.status !== 'selected') {
      state.selection=null;
      feedback(choice.status==='ambiguous' ? 'Рядом несколько точек. Нажми точнее или выбери номер в списке под снимками.' : 'Здесь прибор не видит яркой точки на втором снимке. Выбери одну из светлых точек.');
    } else {
      state.selection=choice;
      feedback('Точка выбрана и обведена кольцом. Нажми «Следить за этой точкой»: проверим её на следующем снимке.');
    }
    update();
  }
  function follow() {
    if(state.phase!=='search'||!state.selection) return;
    const item=current(), selection=state.selection, token=++generation;
    const submitted=Object.freeze({caseId:item.id,selection,amount:state.amount,firstLook:!state.revealed[item.id]});
    state.phase='checking';
    feedback('Прибор ищет выбранную точку на следующем наблюдении…');update();
    timer=setTimeout(()=>{
      if(token!==generation)return;
      const result=TrackingModel.confirm(item,selection);
      state.result=result;state.phase='result';state.mobileView=1;state.revealed[item.id]=true;
      state.attempts.push(Object.freeze({...submitted,result}));
      if(result.outcome==='moving'&&!state.journal.some(e=>e.caseId===item.id)) state.journal.push(Object.freeze({...submitted,result}));
      feedback(result.outcome==='moving' ? 'Кольцо на третьем снимке — прогноз прибора. Внутри него нашлась точка: движение подтвердилось.' : result.outcome==='stationary' ? 'Сравни кольца: точка осталась на том же месте. Прибор нашёл её, но движения здесь нет.' : 'Третий снимок не подтвердил однозначный след. Это повод проверить другую точку, а не угадывать ответ.');
      update();$('outcome-panel').focus({preventScroll:true});
      if(mobile()) $('outcome-panel').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'nearest'});
    }, reduced()?100:850);
  }
  function retry() {
    if(state.phase==='checking')return;
    state.phase='search';state.selection=null;state.result=null;state.mobileView=1;
    feedback('Попробуй другую точку. Настройка сохранена. Ищи ту, которая сместилась между первым и вторым снимками.');update();
  }
  function nextField() {
    if(state.result?.outcome!=='moving')return;
    if(state.field===1){window.brightnessEpisode.start();return;}
    state.field=1;state.phase='search';state.selection=null;state.result=null;state.mobileView=1;
    feedback('На новом участке звёзды расположены иначе. Найди движущуюся точку: настройка прибора осталась прежней.');update();
    $('sky-instruction').scrollIntoView({behavior:'instant',block:'center'});
  }
  function reset() {
    clearTimeout(timer);generation++;
    Object.assign(state,{phase:'search',field:0,amount:0,mobileView:1,selection:null,result:null,attempts:[],journal:[],revealed:{}});
    $('tools').open=false;$('point-tools').open=false;
    feedback('Первый снимок сделан раньше, второй — позже. Какая точка сменила место?');update();
  }
  function setAmount(amount) {
    if(state.phase!=='search')return;
    state.amount=Math.max(0,Math.min(1,Number(amount)||0));
    feedback(state.amount>0 ? 'На втором снимке звёзды приглушены. Ищи голубую точку, которой раньше не было на этом месте. Оранжевое — то, что было ярче на первом снимке. Не каждый остаток означает движение.' : 'Снова видны исходные снимки. Выбор точки доступен с любой настройкой.');update();
  }
  function setView(view){state.mobileView=view===0?0:1;update();}
  function update() {
    const item=current(),search=state.phase==='search',checking=state.phase==='checking',result=state.result;
    $('field-label').textContent=`УЧАСТОК ${state.field+1} ИЗ 2`;
    $('sky-instruction').textContent=search?(mobile()?'Выбери точку на втором снимке':'Выбери точку на правом снимке'):checking?'Проверяем твою цель':'Вот что стало с выбранной точкой';
    $('sky-status').textContent=search?'Два наблюдения':checking?'Следующее наблюдение…':'Третий снимок открыт';
    $('choice-panel').hidden=!!result;$('outcome-panel').hidden=!result;
    $('follow').disabled=!state.selection||!search;
    $('follow').textContent=checking?'Проверяем слежение…':state.selection?'Следить за этой точкой':'Сначала выбери точку';
    $('selection-preview').hidden=!state.selection;
    if(state.selection)crop($('selected-crop'),item,1,state.selection.point);
    $('suppression').value=state.amount*100;$('amount-output').textContent=Math.round(state.amount*100)+'%';
    $('suppression').disabled=!search;$('tools').hidden=!!result;
    $('point-tools').hidden=!search;
    $('difference-key').hidden=!search||state.amount===0;
    $('selection-key').textContent=result?(result.prediction?'На третьем снимке: мятное кольцо — прогноз, белая отметка — найденная точка.':'Однозначного прогноза нет. На втором снимке сохранена выбранная точка.'):state.selection?'Мятное кольцо — твоя выбранная точка.':'Кольцо покажет выбранную тобой точку.';
    $('frame-first').textContent=result?'Второй снимок':'Первый снимок';$('frame-second').textContent=result?'Третий снимок':'Второй снимок';
    for(const [i,id] of ['frame-first','frame-second'].entries())$(id).setAttribute('aria-pressed',String(state.mobileView===i));
    for(const [i,id] of ['step-find','step-check','step-save'].entries())$(id).classList.toggle('active',i===(search?0:result?.outcome==='moving'?2:1));
    $('point-list').replaceChildren();
    item.sources[1].forEach((s,i)=>{const b=document.createElement('button');b.textContent=String(i+1);b.setAttribute('aria-label',`Выбрать точку ${i+1}`);b.setAttribute('aria-pressed',String(state.selection?.point.x===s.x&&state.selection?.point.y===s.y));b.onclick=()=>choose(s.x,s.y);$('point-list').append(b);});
    if(result){
      const outcomes={moving:['ДВИЖЕНИЕ ПОДТВЕРДИЛОСЬ','Точка продолжила движение','Ты выбрал движущийся объект. По двум положениям прибор рассчитал, где искать его дальше, и нашёл рядом с прогнозом на третьем снимке.'],stationary:['ЦЕЛЬ НАЙДЕНА, ДВИЖЕНИЯ НЕТ','Эта точка осталась на месте','На всех трёх снимках она находится в одном месте. Для слежения за движением выбери другую точку — ту, которая сместилась.'],lost:['СЛЕЖЕНИЕ НЕ ПОДТВЕРДИЛОСЬ','Точка не нашлась там, где ожидал прибор','Возможно, прибор связал разные точки или следующий след слишком слабый. Сравни снимки и попробуй другую цель.'],unresolved:['НУЖНА ДРУГАЯ ПРОВЕРКА','Не удалось подтвердить слежение','Прибор не смог однозначно связать эту точку между снимками. По этим данным нельзя уверенно сказать, куда она переместилась. Попробуй другую точку.']};
      const copy=outcomes[result.outcome];$('outcome-tag').textContent=copy[0];$('outcome-title').textContent=copy[1];$('outcome-copy').textContent=copy[2];
      $('reward').textContent=result.outcome==='moving'?(state.journal.length===2?'Два следа в журнале. Ты проверил слежение на двух разных участках неба.':'Три положения объекта записаны в журнал. Проверь прибор на другом участке!'):'';
      $('next-field').hidden=result.outcome!=='moving';$('next-field').textContent=state.field===0?'Попробовать на другом участке':'Продолжить: изменение света';
      $('trail-strip').replaceChildren();result.positions.forEach((point,i)=>{const f=document.createElement('figure'),c=document.createElement('canvas'),caption=document.createElement('figcaption');c.width=c.height=96;crop(c,item,i,point,true);caption.textContent=point?`Снимок ${i+1}`:`${i+1}: след не определён`;f.append(c,caption);$('trail-strip').append(f);});
    }
    $('brightness-invitation').hidden=state.journal.length<2;
    $('journal-count').textContent=`${state.journal.length} / 2`;$('journal-empty').hidden=!!state.journal.length;$('journal-list').replaceChildren();
    state.journal.forEach(entry=>{const row=document.createElement('div');row.className='journal-entry';const positions=entry.result.positions;row.innerHTML=`<strong>${fields.find(c=>c.id===entry.caseId).name} · движение подтверждено</strong><svg viewBox="0 0 128 128" preserveAspectRatio="xMidYMid meet" aria-label="Три положения объекта"><polyline points="${positions.map(p=>`${p.x},${p.y}`).join(' ')}" fill="none" stroke="#8de1ce" stroke-width="2" vector-effect="non-scaling-stroke"/>${positions.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="3" fill="#e7fff7"/>`).join('')}</svg><small>Выбрана цель → проверен прогноз → записан след</small>`;$('journal-list').append(row);});
    $('source-note').textContent=`${item.name}. Наблюдения: ${item.dates.map(d=>d.replace('T',' ').replace('Z',' UTC')).join('; ')}.`;
    if(scene)scene.draw();
  }
  class Sky extends Phaser.Scene {
    create(){scene=this;this.input.on('pointerdown',p=>{if(state.phase!=='search')return;const r=this.rects.find(r=>p.x>=r.x&&p.x<r.x+r.size&&p.y>=r.y&&p.y<r.y+r.size);if(!r)return;if(r.side!==1){feedback('Выбери цель на втором снимке: именно за этой точкой прибор будет следить дальше.');return;}choose((p.x-r.x)/r.size*128-.5,(p.y-r.y)/r.size*128-.5);});this.draw();}
    draw(){
      this.children.removeAll(true);for(const key of ['sky0','sky1'])if(this.textures.exists(key))this.textures.remove(key);
      const narrow=mobile(),width=narrow?480:960;this.scale.resize(width,520);
      const result=state.result,checking=state.phase==='checking',item=current(),sides=narrow?[state.mobileView]:[0,1];this.rects=[];
      for(const side of sides){
        const x=narrow?48:side===0?48:536,y=84,size=narrow?384:376,epoch=(result||checking)?side+1:side;
        this.rects.push({side,x,y,size});
        const texture=this.textures.createCanvas('sky'+side,128,128),ctx=texture.getContext();if(checking&&side===1){ctx.fillStyle='#080e1d';ctx.fillRect(0,0,128,128);}else ctx.putImageData(new ImageData(pixels(item,epoch,!result&&!checking&&side===1?state.amount:0),128,128),0,0);texture.refresh();
        this.add.image(x,y,'sky'+side).setOrigin(0).setDisplaySize(size,size);
        this.add.text(x,26,`${epoch+1}. ${(result||checking)?(side===0?'Твой выбор':checking?'Где будем искать':'Проверка'):(side===0?'Раньше':'Позже · выбери точку')}`,{fontFamily:'system-ui',fontSize:'20px',color:'#dbe9fa'});
        this.add.text(x,y+size+15,time(item,epoch),{fontFamily:'system-ui',fontSize:'15px',color:'#9bb5cf'});
        const g=this.add.graphics();g.lineStyle(1,0x3a536b).strokeRect(x,y,size,size);
        const pos=p=>({x:x+(p.x+.5)/128*size,y:y+(p.y+.5)/128*size});
        const ring=(p,color,r=10)=>{if(!p||p.x<0||p.x>=128||p.y<0||p.y>=128)return;const q=pos(p);g.lineStyle(2,color,.95).strokeCircle(q.x,q.y,r);};
        if(result){if(side===0)ring(state.selection.point,0x9ef2d6);else {ring(result.prediction,0x9ef2d6,Math.max(10,TrackingModel.limits.confirmationRadiusPx/128*size));const p=result.positions[2];if(p){const q=pos(p);g.lineStyle(2,0xffffff).strokeCircle(q.x,q.y,4);}}}
        else if(side===1){ring(state.selection?.point,0x9ef2d6);if($('point-tools').open)item.sources[1].forEach((s,i)=>{const q=pos(s);this.add.text(Math.max(x+4,Math.min(x+size-22,q.x+9)),Math.max(y+4,q.y-20),String(i+1),{fontFamily:'system-ui',fontSize:'18px',color:'#ffe0a3',backgroundColor:'#102033'});});}
        if(checking){if(side===0)ring(state.selection.point,0x9ef2d6);else {ring(state.selection.prediction,0x9ef2d6,12);this.add.text(x+size/2,y+size-35,state.selection.prediction?'Проверяем эту область…':'Ищем соответствие…',{fontFamily:'system-ui',fontSize:'18px',color:'#b0f4de'}).setOrigin(.5);}}
      }
    }
  }
  $('follow').onclick=follow;$('retry').onclick=retry;$('next-field').onclick=nextField;$('restart').onclick=reset;
  $('suppression').oninput=e=>setAmount(e.target.value/100);
  $('frame-first').onclick=()=>setView(0);$('frame-second').onclick=()=>setView(1);
  $('point-tools').ontoggle=()=>scene?.draw();
  matchMedia('(max-width:760px)').addEventListener('change',()=>update());
  const game=new Phaser.Game({type:Phaser.CANVAS,parent:'game',width:mobile()?480:960,height:520,backgroundColor:'#121e30',scene:Sky,render:{antialias:true},audio:{noAudio:true},banner:false});
  window.comparisonProbe={state,choose,follow,retry,nextField,reset,setAmount,setView,game};reset();
})();
