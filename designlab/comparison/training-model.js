/* A small supervised lesson. Only the player's six labels enter the fitted
 * nearest-example model. Verification uses measured geometry afterwards. */
(function(root){
'use strict';
const choices=['sameObject','wrongLink'];
const trainField=COMPARISON_DATA.cases.find(row=>row.id===LEARNING_DATA.trainCase);
const testField=COMPARISON_DATA.cases.find(row=>row.id===LEARNING_DATA.reservedCase);
const training=LearningModel.generate(trainField,LEARNING_DATA.pixelScaleArcsec[trainField.id]);
const reserved=LearningModel.generate(testField,LEARNING_DATA.pixelScaleArcsec[testField.id]);
const sourceLabels=[...LEARNING_DATA.initialExamples,LEARNING_DATA.correction];
const hints={
 '5:4:3':['Сравни расстояния между отмеченными точками на трёх датах.','Положения последовательно смещаются; проверка по времени подтверждает общий след.'],
 '0:0:0':['Проследи положение этой точки относительно соседних звёзд.','Все три положения совпадают. Это неподвижный фон, а не движущийся след.'],
 '1:1:1':['Проверь, произошло ли смещение между наблюдениями.','Совпадение положений на трёх датах не показывает движение.'],
 '2:2:2':['Сравни положение и яркость: что здесь говорит именно о движении?','Изменение яркости само по себе не превращает неподвижную точку в движущийся след.'],
 '3:3:4':['Посмотри, согласуются ли три отмеченных положения по времени.','Точка остаётся на прежнем месте; этот пример учит отклонять неподвижный фон.'],
 '5:4:5':['Первые две точки можно связать. Подходит ли к ним третья?','Третья точка далеко от продолжения движения: такая связь ошибочна.']
};
const examples=Object.freeze(sourceLabels.map(({id,label})=>{
 const row=training.candidates.find(candidate=>candidate.id===id);
 if(!row||!hints[id])throw Error('Training example is missing');
 return Object.freeze({id,points:row.points,prompt:hints[id][0],expectedLabel:label,explanation:hints[id][1]});
}));
const exampleIds=new Set(examples.map(row=>row.id));
const controls=Object.freeze(['5:5:5','0:0:0','1:1:1','5:5:4','5:5:3','5:4:5','4:5:5','8:8:7','7:7:8']);
function state(session){
 if(!session.training||typeof session.training!=='object')session.training={labels:[],revision:0,snapshot:null,evaluation:null};
 const t=session.training;
 if(!Array.isArray(t.labels))t.labels=[];
 if(!Number.isSafeInteger(t.revision)||t.revision<0)t.revision=0;
 if(!('snapshot' in t))t.snapshot=null;
 if(!('evaluation' in t))t.evaluation=null;
 return t;
}
function validLabels(labels){return labels.length<=examples.length&&labels.every(row=>row&&exampleIds.has(row.id)&&choices.includes(row.label))&&new Set(labels.map(row=>row.id)).size===labels.length;}
function signature(labels){return examples.map(row=>`${row.id}:${labels.find(item=>item.id===row.id)?.label||'-'}`).join('|');}
function snapshot(session){
 const t=state(session),s=t.snapshot;
 return s&&s.revision===t.revision&&s.signature===signature(t.labels)&&validLabels(t.labels)&&t.labels.length===examples.length?s:null;
}
function status(session){
 const t=state(session),labels=t.labels.slice(),complete=labels.length===examples.length;
 const trainable=complete&&choices.every(choice=>labels.some(row=>row.label===choice));
 const trained=!!snapshot(session),evaluated=trained&&!!t.evaluation&&t.evaluation.revision===t.revision&&t.evaluation.signature===signature(labels);
 return {labels,labeledCount:labels.length,total:examples.length,complete,trainable,trained,evaluated,revision:t.revision};
}
function label(session,id,value){
 if(!exampleIds.has(id)||!(choices.includes(value)||value===null))throw Error('Unknown training example or label');
 const t=state(session),old=t.labels.find(row=>row.id===id)?.label||null;
 if(old===value)return status(session);
 t.labels=t.labels.filter(row=>row.id!==id);
 if(value)t.labels.push({id,label:value});
 t.labels.sort((a,b)=>examples.findIndex(row=>row.id===a.id)-examples.findIndex(row=>row.id===b.id));
 t.revision++;
 t.snapshot=null;t.evaluation=null;
 if(Array.isArray(session.records))session.records=session.records.filter(row=>row.caseId!==testField.id);
 session.finished=false;
 return status(session);
}
function train(session){
 const t=state(session),s=status(session);
 if(!s.trainable)throw Error('Label all six tracks with at least one example of each class');
 const rows=t.labels.map(row=>training.candidates.find(candidate=>candidate.id===row.id));
 const fitted=LearningModel.fit({candidates:rows});
 t.snapshot={revision:t.revision,signature:signature(t.labels),labels:t.labels.map(row=>({...row})),scale:[...fitted.scale]};
 t.evaluation=null;
 return status(session);
}
function predict(session,caseId='s07'){
 const s=snapshot(session);if(!s)throw Error('Train on the current labels first');
 if(caseId!==trainField.id&&caseId!==testField.id)throw Error('Unknown learning field');
 const field=caseId===trainField.id?training:reserved;
 const rows=s.labels.map(label=>training.candidates.find(candidate=>candidate.id===label.id));
 const scores=LearningModel.score({candidates:rows},s.labels,field,{scale:s.scale});
 const all=field.candidates.map((candidate,i)=>({...candidate,score:scores[i].acceptanceScore,accepted:scores[i].accepted}));
 const candidates=all.filter(row=>row.accepted).sort((a,b)=>b.score-a.score);
 return {inspectedCount:all.length,candidates,all,acceptedCount:candidates.length,revision:s.revision,signature:s.signature};
}
function verifyControl(candidate){
 const selection=TrackingModel.select(testField,candidate.points[1].x,candidate.points[1].y);
 const result=TrackingModel.confirm(testField,selection);
 const sameTrack=result.outcome==='moving'&&result.positions.every((position,i)=>position&&Math.hypot(position.x-candidate.points[i].x,position.y-candidate.points[i].y)<3);
 return {verifiedLabel:sameTrack?'sameObject':'wrongLink',reason:sameTrack?'Три измерения согласуются с рассчитанным движением.':result.outcome==='stationary'?'Точка остаётся на месте.':'Эта связь не проходит проверку положения и времени.'};
}
function evaluate(session){
 const t=state(session),prediction=predict(session,testField.id),byId=new Map(prediction.all.map(row=>[row.id,row]));
 const rows=controls.map(id=>{
  const candidate=byId.get(id);if(!candidate)throw Error('Heldout control is missing');
  const checked=verifyControl(candidate),predictedLabel=candidate.accepted?'sameObject':'wrongLink';
  return {id,points:candidate.points,predictedLabel,verifiedLabel:checked.verifiedLabel,correct:predictedLabel===checked.verifiedLabel,reason:checked.reason,score:candidate.score};
 });
 const result={correct:rows.filter(row=>row.correct).length,total:rows.length,
  falsePositives:rows.filter(row=>row.predictedLabel==='sameObject'&&row.verifiedLabel==='wrongLink').length,
  falseNegatives:rows.filter(row=>row.predictedLabel==='wrongLink'&&row.verifiedLabel==='sameObject').length,
  controls:rows,revision:prediction.revision,signature:prediction.signature};
 t.evaluation=result;return result;
}
function restore(session){
 const t=state(session);
 if(!validLabels(t.labels)){t.labels=[];t.revision++;t.snapshot=null;t.evaluation=null;}
 if(!snapshot(session)){t.snapshot=null;t.evaluation=null;}
 else if(t.evaluation&&(t.evaluation.revision!==t.revision||t.evaluation.signature!==signature(t.labels)))t.evaluation=null;
 return status(session);
}
root.TrainingModel=Object.freeze({examples,label,train,evaluate,predict,status,restore,signature,verifyControl});
})(typeof window==='undefined'?globalThis:window);
