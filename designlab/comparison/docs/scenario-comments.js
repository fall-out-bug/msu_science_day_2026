(()=>{'use strict';
const toggle=document.getElementById('toggle-diffs');if(toggle)toggle.onclick=()=>{const items=[...document.querySelectorAll('.diff-original')];const show=items.some(e=>!e.open);items.forEach(e=>e.open=show);toggle.textContent=show?'Скрыть прежние формулировки':'Показать прежние формулировки'};
const doc=document.documentElement.dataset.reviewDocument||'first-shift-v1', api='/scenario-comments', localKey='scenario-comments:'+doc;
const local=location.protocol==='file:'||new URLSearchParams(location.search).has('local-comments');
const get=(k,f)=>{try{return JSON.parse(localStorage.getItem(k))??f}catch{return f}};
const put=(k,v)=>localStorage.setItem(k,JSON.stringify(v));
const make=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e};
let rows=[],selected='',quote='';
const panel=make('dialog');panel.id='comment-panel';
const title=make('h2','Комментарий к фрагменту'), close=make('button','Закрыть');close.type='button';close.onclick=()=>panel.close();
const excerpt=make('blockquote'),list=make('div'),form=make('form'),message=make('textarea'),send=make('button','Добавить комментарий'),status=make('p');
message.id='comment-message';message.maxLength=4000;message.required=true;message.rows=5;
const messageLabel=make('label','Комментарий');messageLabel.htmlFor=message.id;
status.setAttribute('role','status');send.type='submit';form.append(messageLabel,message,send);
panel.append(close,title,excerpt,make('p',local?'Личные заметки сохраняются в этом браузере.':'Комментарии видны всем, у кого есть ссылка.'),list,form,status);document.body.append(panel);
function render(){list.replaceChildren();rows.filter(r=>r.block===selected).forEach(r=>{const a=make('article');a.append(make('small',new Date(r.created).toLocaleString('ru')),make('p',r.text));if(r.quote&&r.quote!==quote){const d=make('details');d.append(make('summary','Комментарий к прежней редакции'),make('blockquote',r.quote));a.append(d)}list.append(a)});document.querySelectorAll('[data-comment-block]').forEach(b=>{const count=rows.filter(r=>r.block===b.dataset.commentBlock).length;b.textContent=count?'💬 '+count:'＋';b.setAttribute('aria-label','Комментировать фрагмент'+(count?', комментариев: '+count:''))})}
async function refresh(){if(local)rows=get(localKey,[]);else{const r=await fetch(api+'?document='+doc,{cache:'no-store'});if(!r.ok)throw Error('Не удалось загрузить комментарии');rows=await r.json()}render()}
function open(id,text){selected=id;quote=text;excerpt.textContent=text;message.value='';status.textContent='';render();panel.showModal();refresh().catch(e=>status.textContent=e.message);message.focus()}
let ordinal=0;const blocks={};
const targets=document.querySelector('[data-review-id]')?document.querySelectorAll('[data-review-id]'):document.querySelectorAll('main > p, main > blockquote, main > ul > li, main > ol > li, main > h2, main > h3, main > table tbody tr');
for(const e of targets){if(e.classList.contains('inline-diff'))continue;const text=e.textContent.trim();if(!text)continue;const id=e.dataset.reviewId||('p'+String(++ordinal).padStart(3,'0'));blocks[id]=text;const b=make('button','＋');b.type='button';b.className='comment-anchor';b.dataset.commentBlock=id;b.onclick=()=>open(id,text);e.id=e.id||id;if(e.tagName==='TR'){e.lastElementChild.append(b)}else e.append(b)}
window.scenarioCommentBlocks=blocks;
form.onsubmit=async e=>{e.preventDefault();const text=message.value.trim();if(!text){status.textContent='Введите комментарий.';return}send.disabled=true;status.textContent='Сохраняем…';try{const row={document:doc,block:selected,quote,text};if(local){rows=get(localKey,[]);rows.push({...row,id:crypto.randomUUID(),created:new Date().toISOString()});put(localKey,rows)}else{const r=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});if(!r.ok)throw Error('Не удалось сохранить комментарий. Текст оставлен в поле.')}message.value='';await refresh();status.textContent='Комментарий сохранён.'}catch(e){status.textContent=e.message}finally{send.disabled=false}};
const info=make('aside');info.className='comment-help';info.append(make('strong',document.documentElement.dataset.reviewTitle||'Обсуждение сценария'),make('p','Нажмите «＋» рядом с абзацем или репликой, чтобы оставить комментарий. '+(local?'Заметки хранятся только в этом браузере.':'Комментарии общие для всех читателей ссылки.')));
const exportButton=make('button','Скачать комментарии');exportButton.onclick=async()=>{try{await refresh();const a=make('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({document:doc,comments:rows},null,2)],{type:'application/json'}));a.download=doc+'-comments.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}catch(e){alert(e.message)}};info.append(exportButton);document.querySelector('nav').before(info);
refresh().catch(()=>{info.append(make('p',local?'Хранилище браузера недоступно.':'Комментарии временно недоступны. Текст сценария можно читать.'))});
})();
