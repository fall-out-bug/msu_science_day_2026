/* A shift samples three archive galaxies. Only the 1-NN lookup is evaluated here;
   image features were measured offline, and the scientific images stay intact. */
(function (root) {
  'use strict';
  function combinations(base, archive) {
    if (!Array.isArray(base?.classes) || !Array.isArray(archive?.images)) throw new Error('Не удалось открыть учебный архив.');
    const groups=base.classes.map(c=>archive.images.filter(i=>i.label===c.id).map(i=>i.id));
    if(groups.some(g=>!g.length))throw new Error('В архиве не хватает снимков для задания.');
    return groups[0].flatMap(a=>groups[1].flatMap(b=>groups[2].map(c=>[a,b,c])));
  }
  function choose(base,archive,storage) {
    const all=combinations(base,archive),version=archive.datasetVersion||archive.version;
    if(!version)throw new Error('У учебного архива нет версии.');
    const key='galaxy-shifts-'+version;
    let seen=[];try{seen=JSON.parse(storage?.getItem(key)||'[]');if(!Array.isArray(seen))seen=[];}catch{}
    const used=new Set(seen.filter(n=>Number.isInteger(n)&&n>=0&&n<all.length));
    let available=all.map((_,i)=>i).filter(i=>!used.has(i));
    if(!available.length){available=all.map((_,i)=>i).filter(i=>i!==seen.at(-1));seen=[];}
    const random=()=>{if(root.crypto?.getRandomValues){const bytes=new Uint32Array(1);root.crypto.getRandomValues(bytes);return bytes[0]/4294967296;}return Math.random();};
    const index=available[Math.floor(random()*available.length)];
    try{storage?.setItem(key,JSON.stringify([...seen,index]));}catch{}
    const ids=[...all[index]];
    for(let i=ids.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[ids[i],ids[j]]=[ids[j],ids[i]];}
    return ids;
  }
  function create(base,archive,ids) {
    const archiveById=new Map(archive?.images?.map(i=>[i.id,i]));
    const classIds=base?.classes?.map(c=>c.id)||[];
    if(!Array.isArray(ids)||ids.length!==classIds.length||new Set(ids).size!==ids.length||ids.some(id=>!archiveById.has(id))||new Set(ids.map(id=>archiveById.get(id).label)).size!==classIds.length||classIds.some(label=>!ids.some(id=>archiveById.get(id).label===label)))throw new Error('Неверная подборка смены.');
    const originalChild=new Set(base.childIds),selected=new Set(ids),merged=new Map(base.images.map(i=>[i.id,{...i}]));
    for(const image of archive.images)merged.set(image.id,{...image});
    const images=[...merged.values()].map(i=>({...i,split:selected.has(i.id)?'train':originalChild.has(i.id)||archive.images.some(a=>a.id===i.id)?'archive':i.split,role:selected.has(i.id)?'child':originalChild.has(i.id)?'archive':i.role}));
    const byId=Object.fromEntries(images.map(i=>[i.id,i]));
    const train=[...base.protocol.trainingIds.filter(id=>!originalChild.has(id)),...ids].sort();
    const feature=archive.features,editable=[...ids,...base.oldIds],classes=classIds;
    const neighbours={};
    for(const id of [...base.protocol.reviewIds,...base.protocol.finalIds]) {
      if(!feature[id]?.length)throw new Error('Нет признаков снимка '+id);
      let nearest=null,best=Infinity;
      for(const candidate of train){
        if(!feature[candidate]||feature[candidate].length!==feature[id].length)throw new Error('Нет признаков учебного снимка '+candidate);
        const distance=feature[id].reduce((sum,x,j)=>sum+(x-feature[candidate][j])**2,0);
        if(distance<best||(distance===best&&candidate<nearest)){best=distance;nearest=candidate;}
      }
      neighbours[id]=nearest;
    }
    const evaluate=(targets,labels)=>{
      const predictions=targets.map(id=>({id,predicted:labels[neighbours[id]],expected:byId[id].label,neighborId:neighbours[id]}));
      return {predictions,correct:predictions.filter(p=>p.predicted===p.expected).length,total:predictions.length};
    };
    const experiments={};
    for(let n=0;n<243;n++){
      const key=n.toString(3).padStart(5,'0'),labels=Object.fromEntries(train.map(id=>[id,byId[id].label]));
      editable.forEach((id,i)=>labels[id]=classes[Number(key[i])]);
      experiments[key]={key,review:evaluate(base.protocol.reviewIds,labels),final:evaluate(base.protocol.finalIds,labels)};
    }
    return {...base,images,childIds:[...ids],editableIds:editable,experiments,sessionIds:[...ids],datasetVersion:archive.datasetVersion||archive.version,
      protocol:{...base.protocol,trainingIds:train,selection:'Три случайных снимка из учебного архива; по одному примеру каждого видимого типа. Признаки измерены заранее; сосед определяется только среди девяти учебных примеров текущей смены.'},
      model:{...base.model,description:'Ближайший сосед по заранее измеренным признакам яркости. Программа сравнивает девять учебных примеров текущей смены; ответ следует выбранной метке ближайшего примера.'}};
  }
  root.GalaxySession={create,choose,combinations};
})(globalThis);
