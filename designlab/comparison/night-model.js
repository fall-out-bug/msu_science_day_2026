/* Campaign rules and scientific results. No DOM, timing or catalogue answer key. */
(function(root){
'use strict';
const data=[...COMPARISON_DATA.cases,BRIGHTNESS_DATA,...LAUNCH_DATA.cases,...ARCHIVE_DATA.cases];
const definitions=[
 {id:'s02',title:'Поймать движение',kind:'motion',goal:'На двух снимках одна точка сместилась. Найди её: по первым двум положениям прибор предскажет третье.',reward:'Поиск движения установлен: прибор сам сравнит точки на двух снимках. Ты проверишь его версию по третьему.',story:'motion'},
 {id:'brightness-01',title:'Измерить угасающий свет',kind:'light',goal:'Иногда точка остаётся на месте, но меняет яркость. Выбери такую область и измерь, сколько света в ней осталось.',reward:'Измеритель света. Поиск движения не замечает всё — теперь у прибора два способа.',story:'supernova'},
 {id:'s07',title:'Испытать наш ИИ',kind:'auto',goal:'Ты обучил ИИ на примере ошибки. Теперь запусти его на другом участке. Какой из предложенных следов выдержит проверку?',reward:'ИИ проверен на другом участке. Он помог отобрать следы, а ты проверил, какие из них верны.',story:'motion'},
 {id:'launch-variable',title:'Свет вернулся?',kind:'auto',goal:'На первых двух снимках свет изменился. Что случилось потом? Выбери способ поиска и проверь третью дату.',reward:'Третья дата помогает пересмотреть вывод. Ослабление света ещё не значит, что он продолжит угасать.',story:'variable'},
 {id:'archive-steady',title:'Когда ничего не найдено',kind:'auto',goal:'Не каждый участок обязан дать находку. Проверь это поле и сохрани честный результат работы прибора.',reward:'Пустой результат тоже полезен: теперь ты знаешь, что именно проверил прибор.',story:'controls'},
 {id:'s04',title:'Один сигнал — ещё не след',kind:'motion',goal:'На одном снимке есть сигнал. Получится ли связать его с другими наблюдениями? Проверь, прежде чем объявлять находку.',reward:'Одиночного сигнала недостаточно. Прибору нужны согласованные наблюдения.',story:'artifact'},
 {id:'archive-brightening',title:'А если стало ярче?',kind:'photometry',goal:'Наш автомат искал ослабление. А здесь стоит измерить свет вручную. Сравни область на двух датах.',reward:'Вопрос определяет инструмент. Поиск угасания может пропустить усиление света.',story:'variable'},
 {id:'archive-small-change',title:'Граница уверенности',kind:'photometry',goal:'Кажется, свет изменился совсем немного. Измерь его и проверь, достаточно ли данных для уверенного вывода.',reward:'Изменение слишком мало по сравнению с погрешностью. Для вывода нужны дополнительные наблюдения.',story:'controls'},
 {id:'archive-track',title:'Не всякая полоска — астероид',kind:'auto',goal:'На снимке видна полоска. Проверь движение между датами. Сама форма пятна ещё ничего не доказывает.',reward:'Красивое объяснение должно выдержать проверку по другим наблюдениям.',story:'artifact'}
];
const cases=definitions.map(d=>Object.freeze({...d,data:data.find(x=>x.id===d.id)}));
if(cases.some(c=>!c.data))throw Error('Campaign observation missing');
const byId=id=>cases.find(c=>c.id===id);
const fresh=length=>({version:1,length:[3,6,9].includes(length)?length:6,caseId:'s02',records:[],installed:{movement:false,fading:false},learningLabel:null,learningSeen:false,finished:false,startedAt:Date.now()});
const point=p=>p?{x:p.x,y:p.y}:null;
const format=n=>Number(n).toLocaleString('ru-RU',{maximumFractionDigits:2});
const train=LearningModel.generate(byId('s02').data,LEARNING_DATA.pixelScaleArcsec.s02);
const fitted=LearningModel.fit(train);
function labels(session){return [...LEARNING_DATA.initialExamples,...(session.learningLabel?[{id:LEARNING_DATA.correction.id,label:session.learningLabel}]:[])];}
function learning(session,caseId='s07'){
 const field=caseId==='s02'?train:LearningModel.generate(byId(caseId).data,LEARNING_DATA.pixelScaleArcsec[caseId]);
 const scores=LearningModel.score(train,labels(session),field,fitted);
 const candidates=scores.filter(s=>s.accepted).sort((a,b)=>b.acceptanceScore-a.acceptanceScore).map(s=>({...field.candidates.find(c=>c.id===s.id),score:s.acceptanceScore}));
 return {inspectedCount:field.candidates.length,candidates,all:field.candidates,acceptedCount:candidates.length};
}
function label(session,value){if(!['sameObject','wrongLink',null].includes(value))throw Error('Unknown label');session.learningLabel=value;session.learningSeen=true;}
function recordBase(id,method,outcome,summary,detail,extra={}){return {caseId:id,method,outcome,summary,detail,...extra};}
function motion(id,selection){
 const r=TrackingModel.confirm(byId(id).data,selection);
 const summary={moving:'Движение подтвердилось',stationary:'Точка осталась на месте',lost:'На месте прогноза нет сигнала',unresolved:'Надёжного следа не получилось'}[r.outcome];
 const detail=r.outcome==='moving'?'Прогноз и измеренное положение отличаются на '+format(r.distancePx)+' пикселя. Три наблюдения согласуются с движением.':r.outcome==='stationary'?'На всех трёх снимках точка остаётся рядом с прежним положением. Это полезный пример неподвижного фона.':r.outcome==='lost'?'Третий снимок не поддержал прогноз. Одного похожего пятна недостаточно для вывода о движении.':'По этим снимкам нельзя уверенно связать точки. Попробуй другую точку. В задаче об одиночном сигнале такой результат тоже полезен.';
 return recordBase(id,'movement',r.outcome,summary,detail,{positions:r.positions,point:point(selection.point),prediction:r.prediction,distancePx:r.distancePx,reason:r.reason});
}
function light(id,selection){
 const r=BrightnessModel.measure(byId(id).data,selection);
 const faded=r.outcome==='faded',stable=r.outcome==='stable';
 return recordBase(id,'fading',r.outcome,faded?'Свет заметно ослаб':stable?'Яркость почти не изменилась':'Для вывода не хватает точности',faded?'Сравниваем свет, добавившийся относительно старого снимка: на первой дате — 100 условных единиц, на второй — '+Math.round(100*r.ratio)+'. Это не вся яркость звезды.':stable?'Общая яркость выбранной точки почти та же. Попробуй сравнить другие области.':'Измерению мешают шум, соседние источники или край кадра. Такой результат нельзя выдавать за находку.',{point:r.point,ratios:faded?[100,Math.round(100*r.ratio)]:stable?[100,Math.round(100*(1+r.scienceChangeFraction))]:null,reason:r.reason,product:faded?'difference':'science'});
}
function photometry(id,p){
 const d=byId(id).data,ms=d.arrays.map(a=>LaunchModel.aperture(a,p));
 if(ms.some(x=>!x)||ms[0].flux<=0)return recordBase(id,'fading','unresolved','Здесь не получилось измерить свет','У края кадра не хватает фона для сравнения. Выбери область дальше от края.',{point:p});
 const ratios=ms.map(m=>100*m.flux/ms[0].flux),ratio=ratios[1]/100;
 const diagnostic=LaunchModel.scan(d,'fading'),controls=diagnostic.controls;
 const commonRatio=controls?.valid?controls.ratio:1;
 const correctedRatio=ratio/commonRatio;
 const noise=Math.hypot(ms[0].noiseScale,ms[1].noiseScale/commonRatio,ms[0].flux*Math.max(.05,controls?.scatter||0));
 const reliable=controls?.valid&&ms.slice(0,2).every(m=>m.flux>5*m.noiseScale),change=ms[1].flux/commonRatio-ms[0].flux;
 const outcome=reliable&&Math.abs(change)>5*noise&&Math.abs(correctedRatio-1)>.35?(correctedRatio>1?'brightened':'faded'):'unresolved';
 return recordBase(id,'fading',outcome,outcome==='brightened'?'Свет усилился':outcome==='faded'?'Свет ослаб':'Отличие есть. Уверенного вывода пока нет',outcome==='brightened'?'Поиск только угасающих источников пропустил бы этот случай. Новый вопрос потребовал нового измерения.':outcome==='faded'?'В выбранной области стало меньше света. Третья дата показывает, что было дальше.':'Разница есть, но её пока нельзя отличить от погрешности измерения. Нужно больше наблюдений.',{point:p,ratios:ratios.map(Math.round),reason:reliable?'diagnostic_change_check':'field_controls_unreliable',product:'science'});
}
function scan(id,method,session){
 if(method==='learning')return {...learning(session,id),mode:method};
 if(id==='brightness-01')throw Error('Use manual light measurement');
 return LaunchModel.scan(byId(id).data,method);
}
function verify(id,method,candidate,session){
 if(method==='learning'){
  const actual=learning(session,id).candidates.find(c=>c.id===candidate.id);if(!actual)throw Error('Unselected learning candidate');
  const s=TrackingModel.select(byId(id).data,actual.points[1].x,actual.points[1].y),r=motion(id,s);
  const matches=r.outcome==='moving'&&r.positions.every((p,i)=>p&&Math.hypot(p.x-actual.points[i].x,p.y-actual.points[i].y)<3);
  return {...r,method:'learning',outcome:matches?'moving':'unresolved',summary:matches?'Предложение ИИ прошло проверку':'Модель перепутала связь',detail:matches?'Точки лежат там, где их ожидает расчёт движения. ИИ предложил этот след, а проверка по времени и положениям подтвердила его.':r.outcome==='stationary'?'Точка под номером 2 остаётся на месте на остальных снимках. Прибор соединил её с другими источниками — это не один движущийся объект.':'Эта связь не выдержала проверки по времени и положениям точек. Даже после обучения предложения нужно проверять.',positions:actual.points.map(point)};
 }
 const r=LaunchModel.verify(byId(id).data,method,candidate);
 if(method==='movement')return motion(id,candidate.selection);
 return recordBase(id,method,r.outcome,r.thirdOutcome==='rebrightened'?'Свет ослаб — а потом вернулся':'Ослабление найдено',r.thirdOutcome==='rebrightened'?'Первые два снимка показывали падение. На третьей дате свет снова усилился. По первой паре нельзя было заключить, что угасание продолжится.':'Измерение подтверждает отличие первых двух дат. Третье наблюдение рассматриваем отдельно; оно не устанавливает тип источника.',{point:r.point,ratios:[100,Math.round(100*r.ratio),r.thirdFlux?Math.round(100*r.thirdFlux/r.firstFlux):null].filter(x=>x!==null),positions:r.positions,reason:r.reason,product:'science'});
}
function empty(id,method,scan){return recordBase(id,method,'unresolved',scan.reason==='insufficient_stable_field_controls'?'Снимки трудно сравнить надёжно':'Подходящих версий не найдено',scan.reason==='insufficient_stable_field_controls'?'Яркость контрольных точек меняется слишком по-разному. Прибор отказался от вывода, а не доказал отсутствие изменений.':'Этот способ не нашёл подходящих изменений. Можно попробовать другой инструмент. Пустой список не значит, что на небе ничего не происходит.',{reason:scan.reason,inspectedCount:scan.inspectedCount});}
function canSave(result){
 if(!result)return false;
 if(['s02','s07'].includes(result.caseId))return result.outcome==='moving';
 if(['brightness-01','launch-variable'].includes(result.caseId))return result.outcome==='faded';
 if(result.caseId==='s04')return result.method==='movement'&&['unresolved','lost'].includes(result.outcome)&&result.reason!=='no_selected_peak'&&Number.isFinite(result.point?.x)&&Number.isFinite(result.point?.y);
 if(result.caseId==='archive-brightening')return result.outcome==='brightened';
 if(result.caseId==='archive-small-change')return result.reason==='diagnostic_change_check'&&result.ratios?.length===3&&result.ratios.every(Number.isFinite);
 if(result.caseId==='archive-track')return result.method==='movement';
 return !!byId(result.caseId);
}
function save(session,result){
 if(!byId(result.caseId))throw Error('Unknown observation');
 if(!canSave(result))return false;
 const old=session.records.findIndex(r=>r.caseId===result.caseId);if(old<0)session.records.push(result);else session.records[old]=result;
 if(result.caseId==='s02')session.installed.movement=true;
 if(result.caseId==='brightness-01')session.installed.fading=true;
 return true;
}
function restore(value){
 if(!value||value.version!==1||![3,6,9].includes(value.length)||!byId(value.caseId)||!Array.isArray(value.records)||value.records.some(r=>!byId(r.caseId)||typeof r.summary!=='string'||typeof r.detail!=='string')||new Set(value.records.map(r=>r.caseId)).size!==value.records.length)throw Error('Invalid saved shift');
 const s={...fresh(value.length),...value};s.installed={movement:s.records.some(r=>r.caseId==='s02'&&r.outcome==='moving'),fading:s.records.some(r=>r.caseId==='brightness-01'&&r.outcome==='faded')};
 if(![null,'sameObject','wrongLink'].includes(s.learningLabel))s.learningLabel=null;
 s.finished=!!s.finished&&cases.slice(0,s.length).every(c=>s.records.some(r=>r.caseId===c.id&&canSave(r)));return s;
}
root.NightModel=Object.freeze({cases,byId,fresh,restore,motion,light,photometry,scan,verify,empty,canSave,save,learning,label,train});
})(typeof window==='undefined'?globalThis:window);
