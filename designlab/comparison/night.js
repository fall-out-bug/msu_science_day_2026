/* One instrument, one shift. Scientific decisions live in NightModel. */
(() => {
'use strict';
const $=id=>document.getElementById('g-'+id), M=NightModel, storageKey='science-day-night-v1';
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
let session=null, stage='welcome', phase='choose', epoch=1, selected=null, result=null, scan=null, selectedCandidate=null, method='movement', hint=0, hintPoint=null, subtract=0, playing=false, timer=null, runTimer=null, generation=0, sound=false, audio=null;
const frames=new Map();
const current=()=>M.byId(session?.caseId||'s02');
const summaryCount=()=>session.records.filter(r=>M.cases.slice(0,session.length).some(c=>c.id===r.caseId)).length;
const date=s=>new Date(s).toLocaleString('ru-RU',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'})+' UTC';
function el(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
function button(text,fn,className){const e=el('button',text,className);e.onclick=fn;return e;}
function tone(type='select'){
 if(!sound)return;try{audio??=new (window.AudioContext||window.webkitAudioContext)();audio.resume();const notes=type==='success'?[440,554,659]:type==='save'?[330,440]:[280];notes.forEach((f,i)=>{const osc=audio.createOscillator(),gain=audio.createGain(),time=audio.currentTime+i*.09;osc.type='sine';osc.frequency.value=f;gain.gain.setValueAtTime(0,time);gain.gain.linearRampToValueAtTime(.045,time+.01);gain.gain.exponentialRampToValueAtTime(.001,time+.18);osc.connect(gain).connect(audio.destination);osc.start(time);osc.stop(time+.2);});}catch{sound=false;}
}
function raw(d,i){
 const key=d.id+':'+i;if(frames.has(key))return frames.get(key);
 const c=document.createElement('canvas');c.width=c.height=128;
 if(COMPARISON_DATA.cases.some(x=>x.id===d.id)){
  const source=i===0?{...d,arrays:[d.arrays[0],d.arrays[0]]}:d;
  c.getContext('2d').putImageData(new ImageData(ComparisonModel.render(source,0,i||1).pixels,128,128),0,0);frames.set(key,c);return c;
 }
 const pixels=new ImageData(128,128),a=d.arrays[i],top=d.displayTop;
 for(let n=0;n<a.length;n++){const t=a[n]<0?0:Math.min(1,Math.asinh(a[n]*.2)/Math.asinh(top*.2));[8,14,29].forEach((b,k)=>pixels.data[n*4+k]=b+([204,242,255][k]-b)*t);pixels.data[n*4+3]=255;}
 c.getContext('2d').putImageData(pixels,0,0);frames.set(key,c);return c;
}
function stop(){clearInterval(timer);timer=null;playing=false;}
function cancel(){stop();clearTimeout(runTimer);generation++;}
function persist(){try{localStorage.setItem(storageKey,JSON.stringify(session));$('autosave').textContent='Смена сохранена на этом устройстве.';}catch{$('autosave').textContent='Автосохранение недоступно. Не закрывай вкладку; журнал можно скачать в конце.';}}
function showStage(value){stage=value;for(const name of ['welcome','game','ending'])$(name).hidden=name!==value;$('pause').hidden=value!=='game';}
function say(text){$('feedback').textContent=text;}
function openCase(id,review=false){
 cancel();session.caseId=id;epoch=current().kind==='light'||current().kind==='photometry'?0:1;selected=null;result=null;scan=null;selectedCandidate=null;hint=0;hintPoint=null;subtract=0;$('subtract').value=0;
 phase='choose';method=current().kind==='light'||current().kind==='photometry'?'fading':current().id==='s07'&&session.learningSeen?'learning':'movement';
 if(review){result=session.records.find(r=>r.caseId===id)||null;phase=result?'saved':'choose';if(result)method=result.method;}
 showStage('game');say(result?result.detail:current().kind==='auto'?'Выбери, какое изменение поручить искать прибору.':'Сравни кадры кнопками под снимком. Нажми на точку, которую хочешь проверить.');persist();render();$('title').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});
}
function start(length){session=M.fresh(length);persist();openCase('s02');tone();}
function draw(){
 if(stage!=='game')return;
 const d=current().data,canvas=$('sky'),ctx=canvas.getContext('2d');
 if(subtract&&epoch>0&&phase!=='learning'){
  const pixels=ComparisonModel.render(d,subtract/100,epoch).pixels,c=document.createElement('canvas');c.width=c.height=128;c.getContext('2d').putImageData(new ImageData(pixels,128,128),0,0);ctx.drawImage(c,0,0,640,640);
 }else ctx.drawImage(raw(d,Math.min(epoch,d.arrays.length-1)),0,0,640,640);
 const circle=(p,color='#a2f0d4',radius=13,dashed=false)=>{if(!p)return;ctx.beginPath();ctx.setLineDash(dashed?[9,6]:[]);ctx.strokeStyle=color;ctx.lineWidth=2.5;ctx.arc((p.x+.5)*5,(p.y+.5)*5,radius,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);};
 if(hintPoint&&!result){ctx.strokeStyle='#ffcc81';ctx.lineWidth=2;ctx.setLineDash([8,6]);ctx.strokeRect(Math.max(0,Math.min(88,hintPoint.x-20))*5,Math.max(0,Math.min(88,hintPoint.y-20))*5,200,200);ctx.setLineDash([]);}
 let points=null;
 if(phase==='learning'||phase==='learned'){
  const verified=session.records.find(r=>r.caseId==='s02')?.positions;
  if(verified){ctx.strokeStyle='#89edc6';ctx.lineWidth=3;ctx.beginPath();verified.forEach((p,i)=>i?ctx.lineTo((p.x+.5)*5,(p.y+.5)*5):ctx.moveTo((p.x+.5)*5,(p.y+.5)*5));ctx.stroke();circle(verified[2],'#89edc6',18);ctx.fillStyle='#b5ffe3';ctx.font='bold 20px system-ui';ctx.fillText('Твоя точка 3',(verified[2].x+.5)*5-65,(verified[2].y+.5)*5-25);}
  points=M.train.candidates.find(c=>c.id===LEARNING_DATA.correction.id).points;
 }
 else if(selectedCandidate?.points)points=selectedCandidate.points;
 else if(result?.positions)points=result.positions;
 if(points){
  ctx.strokeStyle='#ffcc81';ctx.lineWidth=2;ctx.setLineDash([7,6]);ctx.beginPath();points.filter(Boolean).forEach((p,i)=>i?ctx.lineTo((p.x+.5)*5,(p.y+.5)*5):ctx.moveTo((p.x+.5)*5,(p.y+.5)*5));ctx.stroke();ctx.setLineDash([]);
  points.forEach((p,i)=>{if(!p)return;circle(p,i===epoch?'#effff9':'#ffcc81',i===epoch?15:8);ctx.fillStyle='#ffdfae';ctx.font='bold 20px system-ui';ctx.fillText(String(i+1),(p.x+.5)*5+17,(p.y+.5)*5-9);});
 }else if(selected){circle(epoch===0&&selected.origin?selected.origin:selected.point);if(selected.prediction&&epoch===2)circle(selected.prediction,'#ffcc81',15,true);}
 if(result?.prediction&&epoch===2)circle(result.prediction,'#ffcc81',15,true);
 if(scan&&!result&&phase==='scanned')scan.candidates.slice(0,50).forEach((c,i)=>{const p=c.point||c.points[epoch];circle(p,'#ffcc81',14);ctx.fillStyle='#ffcc81';ctx.font='bold 19px system-ui';ctx.fillText(String(i+1),(p.x+.5)*5+15,(p.y+.5)*5-12);});
 if($('source-picker').open&&!result&&!['learning','learned','scanned'].includes(phase)){ctx.font='bold 18px system-ui';(d.sources[epoch]||[]).forEach((p,i)=>{const x=Math.min(610,(p.x+.5)*5+12),y=Math.max(22,(p.y+.5)*5-12);ctx.fillStyle='#101725';ctx.fillRect(x-3,y-20,28,24);ctx.fillStyle='#ffdfae';ctx.fillText(String(i+1),x,y);});}
 $('frame-label').textContent='Снимок '+(epoch+1)+' · '+date(d.dates[epoch]);
 document.querySelectorAll('[data-epoch]').forEach(b=>{const i=+b.dataset.epoch;b.hidden=i>=d.arrays.length;b.setAttribute('aria-pressed',String(i===epoch));b.disabled=i>=d.arrays.length||(i===2&&!thirdAllowed());b.textContent='Снимок '+(i+1)+(i===2&&!thirdAllowed()?' · закрыт':'');});
 $('blink').textContent=playing?'Остановить':'Чередовать';$('blink').setAttribute('aria-pressed',String(playing));
}
function thirdAllowed(){return !!result||['learning','learned'].includes(phase)||method==='learning'&&phase==='scanned';}
function play(){if(phase==='scanning')return;stop();playing=true;timer=setInterval(()=>{if(document.hidden||stage!=='game'||$('overlay').open)return;epoch=epoch===0?1:0;draw();},1000);draw();}
function chooseEpoch(i){if(i===2&&!thirdAllowed())return;stop();epoch=i;draw();renderPoints();}
function renderPoints(){const container=$('points');container.replaceChildren();(current().data.sources[epoch]||[]).forEach((p,i)=>container.append(button(String(i+1),()=>pick(p.x,p.y))));}
function renderArchive(){
 const nav=$('archive');nav.replaceChildren();const completed=new Set(session.records.map(r=>r.caseId));
 M.cases.slice(0,session.length).forEach((c,i)=>{const b=button((completed.has(c.id)?'✓ ':String(i+1)+'. ')+c.title,()=>openCase(c.id,completed.has(c.id)));b.className=completed.has(c.id)?'complete':'';if(c.id===session.caseId)b.classList.add('active');b.disabled=!completed.has(c.id)&&c.id!==session.caseId&&(i>0&&!completed.has(M.cases[i-1].id));b.setAttribute('aria-current',String(c.id===session.caseId));nav.append(b);});
}
function render(){
 if(stage!=='game')return;const c=current(),tutorial=c.kind==='motion'||c.kind==='light'||c.kind==='photometry';
 $('chapter').textContent='СМЕНА · '+summaryCount()+' / '+session.length+' ИССЛЕДОВАНИЙ';$('count').textContent=session.records.length;
 $('title').textContent=['learning','learned'].includes(phase)?'Покажи прибору ошибку':c.title;
 $('source').textContent='Архив ZTF · '+(c.data.id==='s04'||c.data.id==='archive-steady'||c.data.id==='archive-track'?'разные окна общих экспозиций':'реальные наблюдения');
 $('mission').textContent=['learning','learned'].includes(phase)?'Зелёный след — твоя проверка. Оранжевый — версия прибора. Какая точка в его версии не совпадает с твоим следом? Нажми на неё.':c.goal;
 $('hint-text').hidden=!hint;
 $('source-picker').hidden=['scanning','scanned','learning','learned'].includes(phase)||!!result;
 $('difference').hidden=c.kind!=='motion'||epoch===0||['learning','learned'].includes(phase);
 $('subtract-value').textContent=subtract+'%';
 $('legend').textContent=['learning','learned'].includes(phase)?'Зелёный — твой проверенный след. Оранжевый — версия прибора. Найди отличающуюся точку.':subtract?'Голубой: стало больше света. Оранжевый: стало меньше. Остаток может быть помехой.':result?.prediction?'Пунктирный круг — прогноз. Светлый круг — измеренное положение.':'Положение звёзд — наша опора при сравнении снимков.';
 document.querySelectorAll('[data-tool]').forEach(b=>{const t=b.dataset.tool;const available=t==='movement'?session.installed.movement||c.id==='s02':t==='fading'?session.installed.fading||c.id==='brightness-01':session.learningSeen&&c.id==='s07';b.disabled=!available||tutorial||['scanning','learning','learned'].includes(phase);b.classList.toggle('active',t===method);b.setAttribute('aria-pressed',String(t===method));b.title=available?'':'Сначала проверь этот инструмент';});
 $('tools').hidden=['learning','learned'].includes(phase);
 $('learning-effect').hidden=!(c.id==='s07'&&session.learningSeen||phase==='learned');
 if(!$('learning-effect').hidden){$('learning-count').textContent=session.learningLabel==='wrongLink'?'Ты показал прибору перепутанный след. Теперь он отбрасывает похожие ошибки. Оставшиеся версии всё равно нужно проверить.':'В учебном примере перепутанный след остался разрешённым. Поэтому прибор предлагает слишком много версий. Разберём эту ошибку на твоём проверенном следе.';$('learning-edit').textContent=session.learningLabel==='wrongLink'?'Посмотреть мой пример':'Разобрать учебный пример';}
 $('learning-edit').hidden=phase==='learned';
 $('action').hidden=false;$('action').disabled=false;$('secondary').hidden=true;$('hint').hidden=['saved','learning','learned'].includes(phase);$('science').hidden=!result;$('reward').hidden=!result||!canSave();
 $('reward-copy').textContent=c.reward;
 $('measurement').hidden=!result?.ratios;
 if(result?.ratios){$('measurement-title').textContent=result.summary;$('bars').replaceChildren();const max=Math.max(...result.ratios);result.ratios.forEach((r,i)=>{const row=el('div',undefined,'bar-row');row.append(el('span','Кадр '+(i+1)));const meter=el('span',undefined,'bar');meter.style.setProperty('--amount',(Math.max(0,r)/max*100)+'%');row.append(meter,el('strong',String(r)));$('bars').append(row);});$('measurement-detail').textContent='Первый снимок = 100. '+(result.product==='difference'?'Изменившийся свет относительно архивного фона.':'Свет выбранной области; относительная шкала.');}
 const action=$('action');
 if(phase==='choose'){action.textContent=tutorial?'Выбери точку на снимке':c.id==='s07'&&method==='learning'&&session.learningLabel!=='wrongLink'?'Разобрать ошибку с Никой →':'Запустить выбранный инструмент →';action.disabled=tutorial;}
 if(phase==='selected')action.textContent=c.kind==='motion'?'Проверить по третьему снимку →':'Измерить свет →';
 if(phase==='scanning'){action.textContent='Прибор сравнивает наблюдения…';action.disabled=true;}
 if(phase==='scanned'){action.textContent=scan.candidates.length?'Открой версию прибора':'Сохранить результат поиска';action.disabled=!!scan.candidates.length;}
 if(phase==='result'){action.textContent=canSave()?(c.id==='s02'?'Установить поиск движения':c.id==='brightness-01'?'Установить измеритель света':'Сохранить наблюдение'):(c.kind==='auto'?(scan?.candidates.length?'Открыть другую версию':'Изменить способ поиска'):'Выбрать другую точку');$('secondary').hidden=false;$('secondary').textContent='Проверить ещё раз';}
 if(phase==='saved'){action.textContent=c.id==='s02'&&!session.learningSeen?'Дать прибору примеры →':summaryCount()>=session.length?'Завершить смену →':'К следующему исследованию →';$('secondary').hidden=false;$('secondary').textContent='Перепроверить наблюдение';}
 if(phase==='learning'){action.textContent='Нажми на отличающуюся точку';action.disabled=true;}
 if(phase==='learned'){action.textContent='Сохранить пример и продолжить →';$('secondary').hidden=false;$('secondary').textContent='Отменить мою метку';}
 renderPoints();renderArchive();draw();
}
function canSave(){return M.canSave(result);}
function pick(x,y){
 if(stage!=='game')return;if(phase==='learning'){const point=M.train.candidates.find(c=>c.id===LEARNING_DATA.correction.id).points.findIndex(p=>Math.hypot(p.x-x,p.y-y)<6);if(point>=0)chooseLearningPoint(point);else say('Нажми на оранжевую точку, которая не совпадает с твоим зелёным следом. Можно выбрать номер кнопкой.');return;}if(!['choose','selected','scanned'].includes(phase))return;stop();
 if(phase==='scanned'){const list=scan.candidates.map(c=>({c,p:c.point||c.points[epoch]}));const hit=list.find(({p})=>Math.hypot(p.x-x,p.y-y)<7);if(hit)inspectCandidate(hit.c);return;}
 const c=current();if(c.kind==='auto')return;
 if(c.kind==='motion'){
  if(epoch===0){const options=c.data.sources[1].map(p=>TrackingModel.select(c.data,p.x,p.y)).filter(s=>s.origin&&Math.hypot(s.origin.x-x,s.origin.y-y)<=5);if(options.length===1){selected=options[0];epoch=1;}else{selected=null;say('Не получилось однозначно связать эту точку. Выбери её на снимке 2.');phase='choose';render();return;}}
  else selected=TrackingModel.select(c.data,x,y);
 }else selected=BrightnessModel.select(c.data,x,y);
 if(selected.status!=='selected'){say(selected.status==='ambiguous'?'Рядом несколько точек. Нажми ближе к центру выбранной.':'Здесь нет отдельной измеренной точки. Попробуй нажать на светлое пятно.');selected=null;phase='choose';render();return;}
 phase='selected';say(c.kind==='motion'?(selected.prediction?'Точка выбрана. Прибор вычислил, где искать её на следующем снимке. Проверим прогноз?':'Точка выбрана, но первых двух снимков мало для надёжной связи. Посмотрим третий?'):'Область выбрана. Прибор сравнит свет в одинаковом кружке на двух снимках и вычтет местный фон.');tone();render();
}
function showResult(r){stop();result=r;phase='result';epoch=current().data.arrays.length-1;subtract=0;$('subtract').value=0;if(!scan)$('candidates').replaceChildren();say(r.summary+'. '+r.detail);$('sky-status').textContent=r.summary;tone(['moving','faded','brightened'].includes(r.outcome)?'success':'select');render();}
function inspectCandidate(c){selectedCandidate=c;showResult(M.verify(current().id,method,c,session));}
function run(){
 if(phase==='scanning')return;if(current().id==='s07'&&method==='learning'&&session.learningLabel!=='wrongLink'){learningLesson();return;}cancel();const token=generation;phase='scanning';selected=null;result=null;scan=null;selectedCandidate=null;$('candidates').replaceChildren();$('sky-status').textContent='Поиск по наблюдениям';say('Прибор просматривает измеренные точки. Затем ты проверишь его версии.');render();
 runTimer=setTimeout(()=>{if(token!==generation||stage!=='game')return;scan=M.scan(current().id,method,session);phase='scanned';
 const n=scan.candidates.length;say(n?(method==='learning'?'После твоего примера прибор отобрал '+n+' версии следа.':'Прибор нашёл '+n+' версии.')+' Открой каждую и проверь по снимкам. Предложение ещё не означает находку.':'Подходящих версий нет. Это результат выбранного способа, а не доказательство, что ничего не менялось.');
 $('sky-status').textContent=n?'Найдено версий: '+n:'Подходящих версий нет';
 if(!n){result=M.empty(current().id,method,scan);phase='result';say(result.summary+'. '+result.detail);}
 $('candidates').replaceChildren();scan.candidates.slice(0,30).forEach((c,i)=>{const b=button('След '+(i+1)+' · проверить',()=>inspectCandidate(c));if(c.points){const preview=document.createElement('canvas');preview.width=384;preview.height=128;preview.className='candidate-preview';preview.setAttribute('aria-hidden','true');const ctx=preview.getContext('2d');c.points.forEach((p,k)=>{ctx.drawImage(raw(current().data,k),k*128,0);ctx.strokeStyle='#ffcc81';ctx.lineWidth=2;ctx.beginPath();ctx.arc(k*128+p.x+.5,p.y+.5,7,0,Math.PI*2);ctx.stroke();});b.prepend(preview);}$('candidates').append(b);});
 if(n>30)$('candidates').append(el('p','Показаны первые 30 версий. Так много связей неудобно проверять: можно вернуться к примерам и улучшить отбор.','small'));
 tone();render();},reduced.matches?50:750);
}
function learningLesson(){cancel();$('candidates').replaceChildren();session.caseId='s02';result=null;selected=null;scan=null;selectedCandidate=null;phase='learning';epoch=2;subtract=0;showStage('game');$('sky-status').textContent='Предложенный след';say('Ты уже проверил движение на трёх снимках. Сравни с ним новую версию прибора: начало то же, а что случилось с концом?');[0,1,2].forEach(i=>$('candidates').append(button('Точка '+(i+1),()=>chooseLearningPoint(i))));render();}
function chooseLearningPoint(i){const candidate=M.train.candidates.find(c=>c.id===LEARNING_DATA.correction.id).points,truth=session.records.find(r=>r.caseId==='s02')?.positions;if(!truth)return;if(Math.hypot(candidate[i].x-truth[i].x,candidate[i].y-truth[i].y)<3){say('Точка '+(i+1)+' совпадает с твоей проверкой. Ищи ту, где оранжевый след расходится с зелёным.');tone();return;}label('wrongLink');$('candidates').replaceChildren();}
function label(value){
 M.label(session,value);phase='learned';
 say('Ты нашёл ошибку: прибор выбрал другую точку в третьем снимке. Эта связь сохранена как пример, который нужно отвергать. Теперь испытаем отбор на другом поле.');
 $('sky-status').textContent='Пример изменил отбор';persist();tone();render();
}
function next(){
 if(summaryCount()>=session.length){finish();return;}
 const candidate=M.cases.slice(0,session.length).find(c=>!session.records.some(r=>r.caseId===c.id));openCase(candidate.id);
}
function act(){
 if(phase==='choose'&&current().kind==='auto'){run();return;}
 if(phase==='selected'){showResult(current().kind==='motion'?M.motion(current().id,selected):current().kind==='light'?M.light(current().id,selected):M.photometry(current().id,selected.point));return;}
 if(phase==='result'){if(!canSave()){if(scan?.candidates.length){result=null;selectedCandidate=null;phase='scanned';say('Эта версия не выдержала проверку. Открой другой предложенный след.');render();return;}retry();if(current().kind==='auto')say(current().id==='launch-variable'?'Поиск движения не ответил на вопрос о свете. Выбери измеритель света и проверь следующую дату.':'Здесь нужно проверить след на другом поле. Попробуй поиск движения или обучаемый отбор.');return;}M.save(session,result);phase='saved';persist();tone('save');$('sky-status').textContent='Сохранено в журнале';say(current().reward);render();return;}
 if(phase==='saved'){if(current().id==='s02'&&!session.learningSeen)learningLesson();else next();return;}
 if(phase==='learning')return;
 if(phase==='learned'){persist();next();}
}
function retry(){cancel();result=null;selected=null;selectedCandidate=null;scan=null;phase='choose';epoch=current().kind==='light'||current().kind==='photometry'?0:1;$('sky-status').textContent='';$('candidates').replaceChildren();say(current().goal);render();}
function secondary(){if(phase==='learned'){M.label(session,null);session.learningSeen=false;learningLesson();persist();return;}retry();}
function finish(){cancel();session.finished=true;persist();showStage('ending');const found=session.records.filter(r=>['moving','faded','brightened'].includes(r.outcome)).length;
 $('ending-copy').textContent='Ты проверил '+summaryCount()+' участков. Подтверждённых изменений: '+found+'. Остальные наблюдения тоже сохранены — вместе с причинами, по которым вывод остался открытым.';
 $('summary').replaceChildren();session.records.forEach(r=>{const entry=el('article');entry.append(el('span',M.byId(r.caseId).title,'eyebrow'),el('h2',r.summary),el('p',r.detail));$('summary').append(entry);});
 if(session.learningSeen){const e=el('article');e.append(el('span','ТВОЙ ОБУЧАЕМЫЙ ОТБОР','eyebrow'),el('h2','Пример помог отбирать следы'),el('p','Ты показал прибору ошибочную связь и проверил его предложения на другом поле. Это маленький учебный набор: на других наблюдениях у модели могут быть новые ошибки.'));$('summary').append(e);}
 $('continue').textContent=session.length<9?'Открыть ещё три исследования →':'Вернуться к прибору';$('ending').querySelector('h1').focus();tone('success');
}
function modal(title,content){stop();const box=$('overlay-content');box.replaceChildren(el('h2',title),...content);$('overlay').showModal();}
function journal(){const content=[];session.records.forEach(r=>{const a=el('article');a.append(el('h3',M.byId(r.caseId).title),el('p',r.summary),button('Открыть наблюдение',()=>{$('overlay').close();openCase(r.caseId,true);}));content.push(a);});if(!content.length)content.push(el('p','Здесь останутся твои проверенные наблюдения.'));if(session.installed.movement)content.push(button('Вернуться к примерам для модели',()=>{$('overlay').close();learningLesson();}));modal('Журнал твоей смены',content);}
const stories={
 motion:{title:'Точки, за которыми движутся миры',text:'Астероид на короткой серии снимков выглядит как маленькая точка. Сравнение наблюдений позволяет выделить движение среди звёзд. Для орбиты нужны дополнительные наблюдения: трёх точек недостаточно. Ты проверил известные архивные данные, а не объявил новое открытие.',links:[['Как наблюдают астероиды · NASA/JPL','https://cneos.jpl.nasa.gov/about/search_program.html']]},
 supernova:{title:'ИИ помогает выбрать, куда смотреть',text:'В 2023 году BTSbot помог выбрать сверхновую SN 2023tyk для наблюдения спектра. Другой алгоритм, SNIascore, помог классифицировать спектр. Твои два снимка показывают изменение света; они сами по себе не определяют тип сверхновой. Разные инструменты решают разные части научной задачи.',links:[['Исследование авторов BTSbot','https://arxiv.org/html/2401.15167v1#S5.SS1']]},
 variable:{title:'Небо живёт по своим часам',text:'Свет звезды может меняться. Иногда она снова становится ярче. Три редких снимка помогают заметить изменение, но не рассказывают всю историю. Чтобы найти период, астрономы строят кривую блеска по многим наблюдениям.',links:[['ZTF: наблюдения меняющегося неба','https://www.ztf.caltech.edu/']]},
 controls:{title:'Почему учёные любят проверять',text:'Различие на снимках может появиться из-за самого объекта, атмосферы или прибора. Поэтому мы сравниваем соседние точки, вычитаем фон и проверяем шум. «Пока неясно» — честный результат, после которого можно придумать более точный эксперимент.',links:[['Архив наблюдений ZTF · IRSA','https://irsa.ipac.caltech.edu/Missions/ztf.html']]},
 artifact:{title:'Космос оставляет не только открытия',text:'На изображении бывают следы помех. Один яркий сигнал не доказывает существование движущегося объекта. Его нужно сопоставить с другими наблюдениями и сведениями о качестве снимка. Именно поэтому результат алгоритма проверяет исследователь.',links:[['Данные и качество наблюдений ZTF','https://irsa.ipac.caltech.edu/data/ZTF/docs/releases/ztf_release_notes.html']]}
};
function science(){const s=stories[current().story];const items=[el('p',s.text)];for(const [title,url]of s.links){const a=el('a',title);a.href=url;a.target='_blank';a.rel='noopener noreferrer';items.push(a);}if(current().id==='brightness-01')items.push(el('p','Шкала 100 → 34 относится к изменившемуся свету выбранной области на разностных снимках ZTF. Она не равна полной светимости сверхновой.','small'));modal(s.title,items);}
function help(){
 hint=Math.min(3,hint+1);let message;
 if(hint===1)message='Сначала поочерёдно открой снимки 1 и 2. Смотри, какие точки остаются на месте, а какие отличаются.';
 else if(hint===2)message=current().kind==='motion'?'Попробуй ползунок «Убрать неизменившиеся звёзды». Парные следы могут показать смещение. Затем проверь третий снимок.':'Выбирай светлую область далеко от края. Для поиска ослабления пригодится инструмент «Свет».';
 else{const d=current().data;let p;if(current().kind==='motion'){const m=LaunchModel.scan(d,'movement').candidates[0];p=m?.point;}else if(current().id==='brightness-01'){p=d.sources[0].find(s=>M.light(d.id,{status:'selected',point:s}).outcome==='faded');}else{p=d.sources[0].filter(s=>s.x>12&&s.x<115&&s.y>12&&s.y<115).sort((a,b)=>b.peak-a.peak)[0];}
  message=p?'Сравни точки в выделенном участке. Прямоугольник — подсказка, а не результат проверки.':'Попробуй другой инструмент. Если версий нет, это тоже можно сохранить с объяснением.';if(p){hintPoint=p;epoch=current().kind==='motion'?1:0;}}
 $('hint-text').textContent=message;render();
}
$('start').onclick=()=>{const value=+document.querySelector('input[name=length]:checked').value;if(session?.records.length){modal('Начать новую смену?',[el('p','Сохранённая смена на этом устройстве будет заменена.'),button('Начать новую смену',()=>{$('overlay').close();start(value);},'primary')]);}else start(value);};
$('resume').onclick=()=>session.finished?finish():openCase(session.caseId,session.records.some(r=>r.caseId===session.caseId));
$('learning-edit').onclick=learningLesson;
$('action').onclick=act;$('secondary').onclick=secondary;$('hint').onclick=help;$('science').onclick=science;$('journal-open').onclick=journal;
$('sky').onclick=e=>{const rect=e.currentTarget.getBoundingClientRect();pick((e.clientX-rect.left)/rect.width*128-.5,(e.clientY-rect.top)/rect.height*128-.5);};
$('sky').onkeydown=e=>{if(['ArrowLeft','ArrowRight',' '].includes(e.key)){e.preventDefault();if(e.key===' ')playing?stop():play();else chooseEpoch(epoch===0?1:0);draw();}};
$('source-picker').ontoggle=draw;
$('subtract').oninput=e=>{subtract=+e.target.value;$('subtract-value').textContent=subtract+'%';draw();};
$('blink').onclick=()=>{if(playing)stop();else play();draw();};
for(const b of document.querySelectorAll('[data-epoch]'))b.onclick=()=>chooseEpoch(+b.dataset.epoch);
for(const b of document.querySelectorAll('[data-tool]'))b.onclick=()=>{method=b.dataset.tool;retry();say(method==='learning'?'Модель использует все три снимка и твои примеры. Оценивает сочетания точек; её оценка не является вероятностью.':method==='movement'?'Прибор сравнит положения на первых двух снимках. Третий оставит для проверки.':'Прибор ищет заметное ослабление света по первым двум датам. Усиление света этот способ может пропустить.');tone();};
$('sound').onclick=()=>{sound=!sound;$('sound').textContent=sound?'Звук вкл.':'Звук выкл.';$('sound').setAttribute('aria-pressed',String(sound));tone();};
$('pause').onclick=()=>{cancel();if(phase==='scanning'){phase='choose';say('Поиск остановлен. Его можно запустить снова.');render();}modal('Смена на паузе',[el('p','Все сохранённые наблюдения останутся на этом устройстве.'),button('Продолжить',()=>$('overlay').close(),'primary'),button('К началу игры',()=>{$('overlay').close();showStage('welcome');$('resume').hidden=false;})]);};
$('close').onclick=()=>$('overlay').close();$('overlay').onclick=e=>{if(e.target===$('overlay'))$('overlay').close();};
$('continue').onclick=()=>{session.finished=false;if(session.length<9)session.length+=3;persist();if(summaryCount()<session.length)next();else openCase(session.caseId,true);};
$('new').onclick=()=>modal('Передать смену?',[el('p','Сначала можно скачать свой журнал. Новая смена очистит сохранённое прохождение.'),button('Начать новую смену',()=>{$('overlay').close();session=null;try{localStorage.removeItem(storageKey);}catch{}$('resume').hidden=true;showStage('welcome');},'primary')]);
$('export').onclick=()=>{const blob=new Blob([JSON.stringify({title:'Мастерская неба — мой журнал',version:1,observations:session.records,learningLabel:session.learningLabel,scienceNote:'Учебная работа с архивными наблюдениями. Не новые астрономические открытия.'},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='my-sky-journal.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
reduced.addEventListener('change',()=>{if(reduced.matches){stop();draw();}});document.addEventListener('visibilitychange',()=>{if(document.hidden){cancel();if(phase==='scanning'){phase='choose';say('Поиск остановлен, пока вкладка скрыта. Запусти его снова.');render();}}});
for(const [i,id]of ['intro-a','intro-b'].entries())$(id).getContext('2d').drawImage(raw(M.cases[0].data,i),0,0,256,256);
try{const saved=localStorage.getItem(storageKey);if(saved){session=M.restore(JSON.parse(saved));$('resume').hidden=false;$('save-note').textContent='Есть сохранённая смена: '+session.records.length+' наблюдений.';}}catch{$('save-note').textContent='Предыдущее сохранение прочитать не удалось. Можно начать новую смену.';}
showStage('welcome');window.night={get session(){return session;},get state(){return {stage,phase,epoch,method,selected,result,scan,playing};}};
})();
