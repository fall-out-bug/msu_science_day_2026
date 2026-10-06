/* The learner supplies every label; controls never enter the training set. */
function TrainingWorkshop(options){
 'use strict';
 const M=NightModel,host=options.host,names={sameObject:'Движущийся след',wrongLink:'Не движущийся след'};
 let session,index=0,view='label',notice='',controlIndex=0,review=false;
 const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
 const btn=(text,fn,cls)=>{const b=el('button',text,cls);b.type='button';b.onclick=fn;return b;};
 function strip(points,fieldId){
  const d=M.byId(fieldId).data,wrap=el('div',undefined,'training-frames');
  points.forEach((p,i)=>{const fig=el('figure'),c=el('canvas');c.width=c.height=256;const ctx=c.getContext('2d');ctx.drawImage(options.raw(d,i),0,0,256,256);ctx.strokeStyle='#ffce86';ctx.lineWidth=3;ctx.beginPath();ctx.arc((p.x+.5)*2,(p.y+.5)*2,14,0,Math.PI*2);ctx.stroke();c.setAttribute('role','img');c.setAttribute('aria-label',`Снимок ${i+1}: отмеченная точка x=${p.x}, y=${p.y}`);fig.append(c,el('figcaption','Снимок '+(i+1)));wrap.append(fig);});return wrap;
 }
 function changed(){options.onChange();render();}
 function label(value){M.label(session,M.examples[index].id,value);notice='Метка сохранена. Следующий шаг — обучить модель на всей выборке.';if(index<M.examples.length-1)index++;changed();}
 function render(){
  const s=M.trainingStatus(session),head=el('header',undefined,'training-heading');host.replaceChildren();
  head.append(el('span','ФАКУЛЬТЕТ ИИ · ЛАБОРАТОРИЯ ОБУЧЕНИЯ','eyebrow'),el('h1','Как научить машину искать?', 'training-title'));
  const steps=el('nav',undefined,'training-steps');steps.setAttribute('aria-label','Этапы обучения');
  [['label',`1. Разметка ${s.labeledCount}/6`],['train','2. Обучение'],['test','3. Проверка']].forEach(([id,title])=>{const b=btn(title,()=>{view=id;notice='';render();});b.setAttribute('aria-current',String(view===id));b.disabled=id==='train'&&!s.complete||id==='test'&&!s.trained;steps.append(b);});head.append(steps);host.append(head);
  const body=el('div',undefined,'training-body');host.append(body);
  if(view==='label'){
   const ex=M.examples[index],choice=session.training.labels.find(r=>r.id===ex.id)?.label;
   const intro=el('div',undefined,'training-intro');intro.append(el('h2','Ты составляешь обучающую выборку'),el('p','На каждом примере обведены три точки с последовательных снимков. Могла ли одна движущаяся точка оставить такой след? Твоя метка станет ответом, на котором учится модель.'));
   body.append(intro);
   const work=el('div',undefined,'training-work'),viewer=el('section',undefined,'training-viewer'),decision=el('aside',undefined,'training-decision');
   const picker=el('nav',undefined,'training-picker');picker.setAttribute('aria-label','Шесть учебных примеров');M.examples.forEach((r,i)=>{const done=session.training.labels.some(l=>l.id===r.id);const b=btn((done?'✓ ':'')+(i+1),()=>{index=i;notice='';render();});b.dataset.example=r.id;b.setAttribute('aria-label','Пример '+(i+1));b.setAttribute('aria-current',String(index===i));picker.append(b);});
   viewer.append(picker,strip(ex.points,'s02'));viewer.append(el('p','Золотые кольца показывают проверяемую связь. Остальные звёзды помогают сравнивать положение.','small'));
   decision.append(el('span','ПРИМЕР '+(index+1)+' ИЗ 6','eyebrow'),el('h2','Твоя метка'),el('p',ex.prompt));
   ['sameObject','wrongLink'].forEach(value=>{const b=btn(names[value],()=>label(value),'training-label');b.dataset.label=value;b.setAttribute('aria-pressed',String(choice===value));decision.append(b);});
   decision.append(el('p',choice?'Твоя метка: '+names[choice]:'Этот пример пока не размечен.','small'));const tip=el('details',undefined,'training-hint');tip.append(el('summary',review?'Разбор этого примера':'Как отличить след?'),el('p',review?ex.explanation:'Движущийся след последовательно смещается относительно звёзд. Неподвижные точки и случайные связи относятся ко второй группе.'));decision.append(tip);
   work.append(viewer,decision);body.append(work);
   const next=btn(s.complete?'К обучению модели →':'Сначала отметь все 6 примеров',()=>{view='train';notice='';render();},'primary');next.disabled=!s.complete;body.append(next);
  } else if(view==='train'){
   body.append(el('h2','Из твоих меток — модель'),el('p','Обычному алгоритму мы задавали правило движения. В машинном обучении задаём примеры с ответами: модель использует их, чтобы выбирать ответ для незнакомого следа.'));
   const grid=el('div',undefined,'training-concepts');[['Данные','Три положения и яркость точек на реальных снимках.'],['Признаки','Скорость, ровность движения и похожесть яркости. Это числа, по которым сравнивают следы.'],['Обучение','Наша простая модель запоминает шесть размеченных примеров и настраивает масштаб признаков. Новый след она сравнит с ближайшими примерами двух групп.']].forEach(([h,p])=>{const a=el('article');a.append(el('h3',h),el('p',p));grid.append(a);});body.append(grid);
   const positive=s.labels.filter(r=>r.label==='sameObject').length;body.append(el('p',`Твоя выборка: ${positive} движущихся следов, ${6-positive} примеров другой группы. Готовых ответов за тебя модель не получила.`));
   if(!s.trainable)body.append(el('p','В выборке нужны обе группы. Вернись к разметке: есть ли неподвижная точка? А последовательное движение?','training-warning'));
   const train=btn(s.trained?'Обучить заново':'Обучить на моих примерах',()=>{M.train(session);notice='Модель обучена на твоих шести метках. Теперь проверим её на другом поле.';changed();},'primary');train.id='g-train-model';train.disabled=!s.trainable;body.append(train);
   if(s.trained){const test=btn('Проверить на новых снимках →',()=>{M.evaluate(session);view='test';review=true;notice='';changed();},'primary');test.id='g-test-model';body.append(test);}
  } else {
   if(!s.evaluated)M.evaluate(session);
   const e=session.training.evaluation,control=e.controls[controlIndex]||e.controls[0];
   body.append(el('h2',`Проверка: ${e.correct} из ${e.total}`),el('p','Это '+e.total+' связей с другого участка неба. Модель не обучалась на них. Сравниваем её ответы с независимой проверкой положения и времени — это тест, а не новые метки для обучения.'));
   const score=el('div',undefined,'training-score');score.append(el('strong',`Ложных тревог: ${e.falsePositives}`),el('strong',`Пропущенных следов: ${e.falseNegatives}`));body.append(score);
   const work=el('div',undefined,'training-work'),viewer=el('section',undefined,'training-viewer'),verdict=el('aside',undefined,'training-decision');
   const controls=el('nav',undefined,'training-picker');controls.setAttribute('aria-label','Контрольные примеры');e.controls.forEach((r,i)=>{const b=btn((r.correct?'✓ ':'! ')+(i+1),()=>{controlIndex=i;render();});b.setAttribute('aria-current',String(controlIndex===i));controls.append(b);});viewer.append(controls,strip(control.points,'s07'));
   verdict.append(el('h3','Контроль '+(controlIndex+1)),el('p','Ответ модели: '+names[control.predictedLabel]),el('p','Проверка: '+names[control.verifiedLabel]),el('p',control.reason),el('strong',control.correct?'Ответы совпали':'Модель ошиблась','training-verdict'));work.append(viewer,verdict);body.append(work);
   body.append(el('p',e.correct===e.total?'На этих контрольных примерах ответы совпали. Это ещё не означает, что модель справится со всем небом.':'Ошибки помогают понять модель. Проверь свои метки: особенно неподвижные точки и след, у которого последняя точка чужая. Даже верные метки не гарантируют отсутствие ошибок.','training-tip'));
   const actions=el('div',undefined,'training-actions');actions.append(btn('Изменить мою разметку',()=>{view='label';notice='';render();}),btn('Применить модель в смене →',()=>options.onComplete(),'primary'));body.append(actions);options.onChange();
  }
  const status=el('p',notice,'training-notice');status.setAttribute('role','status');host.append(status);
 }
 return {open(value){session=value;index=0;controlIndex=0;review=M.trainingStatus(session).evaluated;view=review?'test':'label';notice='';render();host.querySelector('h1').tabIndex=-1;host.querySelector('h1').focus({preventScroll:true});},render};
}
