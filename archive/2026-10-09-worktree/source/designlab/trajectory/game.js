(function () {
  'use strict';
  const { Investigation, TOLERANCE } = TrajectoryModel;
  const cases = window.TRAJECTORY_DATA;
  const sessions = cases.map(c => new Investigation(c));
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = { caseIndex: 0, epoch: 0, blend: 0, blinking: false,
    cursor: { x: 63.5, y: 63.5 }, helpVisible: false, dragging: false };
  let scene, blinkTimer;
  const current = () => sessions[state.caseIndex];
  const item = () => cases[state.caseIndex];
  const px = p => ({ x: 4 + (p.x + .5) * 4, y: 36 + (p.y + .5) * 4 });
  const field = p => p.x >= 4 && p.x <= 516 && p.y >= 36 && p.y <= 548;
  const source = p => ({ x: Math.max(-.5, Math.min(127.5, (p.x - 4) / 4 - .5)),
    y: Math.max(-.5, Math.min(127.5, (p.y - 36) / 4 - .5)) });
  const date = o => o.date.slice(8,10) + '.' + o.date.slice(5,7) + '.' + o.date.slice(0,4) +
    ' · ' + o.date.slice(11,19) + ' UTC';
  function stopBlink() {
    clearInterval(blinkTimer); state.blinking = false; $('#blink').setAttribute('aria-pressed', 'false');
    $('#blink').textContent = 'Чередовать 1 ↔ 2';
  }
  function selectEpoch(epoch) {
    if (epoch === 2 && !current().revealed) return;
    stopBlink(); state.epoch = epoch; state.blend = 0; $('#blend').value = 0; sync();
  }
  function place(x, y) {
    if (state.epoch === 2 || state.blend > 0) return;
    stopBlink(); current().mark(state.epoch, x, y); state.cursor = { x, y }; sync();
  }
  function outcome(result) {
    return result.withinTolerance ? 'Точка оказалась в твоём круге.' :
      'Точка оказалась вне круга. Возможно, мы связали разные звёзды.';
  }
  function sync() {
    const m = current(), c = item(), p = m.prediction;
    $('#frame-date').textContent = date(c.observations[state.epoch]) + ' · r';
    $('#stage').textContent = m.assisted ? 'С ориентиром' : m.revealed ? 'Проверка открыта' : 'Два наблюдения';
    document.querySelectorAll('[data-epoch]').forEach(b => {
      const e = Number(b.dataset.epoch); b.disabled = e === 2 && !m.revealed;
      b.setAttribute('aria-pressed', String(e === state.epoch));
      if (e === 2) b.textContent = m.revealed ? '3 · проверка' : '3 · ещё закрыт';
    });
    document.querySelectorAll('[data-case]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.case) === state.caseIndex)));
    $('#test').disabled = !p;
    $('#test').textContent = m.revealed ? 'Посмотреть третий кадр' : 'Проверить на третьем кадре';
    if (state.blend > 0) $('#feedback').textContent = 'Переключи на отдельный кадр, чтобы поставить отметку.';
    else if (!m.marks[0]) $('#feedback').textContent = 'Нажми на движущуюся точку в кадре 1. Отметку можно двигать.';
    else if (!m.marks[1]) $('#feedback').textContent = 'Переключись на кадр 2 и отметь ту же точку в новом положении.';
    else if (!m.revealed) $('#feedback').textContent = 'Круг показывает твой прогноз. Двигай отметки — или проверь третьим снимком.';
    else {
      const revised = JSON.stringify(m.marks) !== JSON.stringify(m.frozen.marks);
      $('#feedback').textContent = (revised ? 'Теперь: ' + outcome(m.result()) + ' Первый прогноз сохранён.' :
        outcome(m.result(true))) + (m.result().withinTolerance ? ' Попробуй другой объект.' : ' Вернись к кадрам 1 и 2, уточни отметки.');
    }
    $('#help').textContent = state.helpVisible ? 'Скрыть ориентир' : 'Нужен ориентир';
    $('#help').setAttribute('aria-pressed', String(state.helpVisible));
    if (scene) scene.renderState();
  }
  class ObservationScene extends Phaser.Scene {
    preload() {
      cases.forEach(c => c.frames.forEach((uri, e) => this.load.image(c.id + '-' + e, uri)));
    }
    create() {
      scene = this;
      this.add.rectangle(260, 292, 520, 560, 0x070c15);
      this.picture = this.add.image(4, 36, cases[0].id + '-0').setOrigin(0).setDisplaySize(512, 512);
      this.second = this.add.image(4, 36, cases[0].id + '-1').setOrigin(0).setDisplaySize(512, 512).setAlpha(0);
      for (const c of cases) for (let e=0;e<3;e++) this.textures.get(c.id + '-' + e).setFilter(Phaser.Textures.FilterMode.NEAREST);
      this.lines = this.add.graphics();
      this.title = this.add.text(5, 6, '', { fontFamily: 'system-ui', fontSize: '13px', color: '#c5d9ee' });
      this.tags = [0,1].map(() => this.add.text(0,0,'', { fontFamily:'system-ui',fontSize:'13px',color:'#fff0d2',backgroundColor:'#172338',padding:{x:4,y:2} }));
      const canvas = this.game.canvas; canvas.tabIndex = 0;
      canvas.setAttribute('aria-label', 'Архивный снимок. Стрелки перемещают прицел, Enter ставит отметку. Клавиши 1 и 2 переключают кадры.');
      this.input.on('pointerdown', pointer => {
        canvas.focus({ preventScroll: true });
        if (!field(pointer) || state.epoch === 2 || state.blend > 0) return;
        state.dragging = true; const p = source(pointer); place(p.x,p.y);
      });
      this.input.on('pointermove', pointer => {
        if (!field(pointer)) return;
        const p = source(pointer); state.cursor = p;
        if (state.dragging && pointer.isDown && state.epoch < 2) place(p.x,p.y);
        else this.renderState();
      });
      this.input.on('pointerup', () => state.dragging = false);
      this.input.on('gameout', () => state.dragging = false);
      canvas.addEventListener('keydown', event => {
        if (['1','2','3'].includes(event.key)) { event.preventDefault(); selectEpoch(Number(event.key)-1); return; }
        if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter'].includes(event.key)) return;
        event.preventDefault();
        const step = event.shiftKey ? 5 : 1;
        if (event.key === 'ArrowLeft') state.cursor.x -= step;
        if (event.key === 'ArrowRight') state.cursor.x += step;
        if (event.key === 'ArrowUp') state.cursor.y -= step;
        if (event.key === 'ArrowDown') state.cursor.y += step;
        state.cursor.x = Math.max(-.5,Math.min(127.5,state.cursor.x));
        state.cursor.y = Math.max(-.5,Math.min(127.5,state.cursor.y));
        if (event.key === 'Enter') place(state.cursor.x,state.cursor.y); else this.renderState();
      });
      window.trajectoryProbe = { sessions, state, game: this.game, ready: true };
      sync();
    }
    renderState() {
      const m = current(), c = item(), g = this.lines, prediction = m.prediction;
      this.picture.setTexture(c.id + '-' + state.epoch).setDisplaySize(512,512);
      this.second.setTexture(c.id + '-1').setDisplaySize(512,512).setAlpha(state.epoch === 2 ? 0 : state.blend / 100);
      if (state.blend > 0 && state.epoch !== 2) this.picture.setTexture(c.id + '-0').setDisplaySize(512,512);
      this.title.setText(state.blend > 0 && state.epoch !== 2 ? 'СОВМЕЩЕНИЕ 1 + 2 · ' + state.blend + '%' :
        'КАДР ' + (state.epoch+1) + (state.epoch === 2 ? ' · ПРОГНОЗ И НАБЛЮДЕНИЕ' : state.epoch === 0 ? ' · НАЙДИ ТОЧКУ' : ' · НАЙДИ ЕЁ СНОВА'));
      g.clear(); g.lineStyle(1,0x33435d); g.strokeRect(4,36,512,512);
      const circle = (p,color,radius=4,dashed=false) => {
        const q = px(p); g.lineStyle(2,color);
        if (dashed) for(let i=0;i<12;i++){g.beginPath();g.arc(q.x,q.y,radius*4,i*Math.PI/6,i*Math.PI/6+.13);g.strokePath();}
        else g.strokeCircle(q.x,q.y,radius*4);
      };
      // Clip model overlays to the same scientific image bounds.
      const inside = p => p && p.x >= -.5 && p.x <= 127.5 && p.y >= -.5 && p.y <= 127.5;
      this.tags.forEach((label,e) => {
        const p=m.marks[e]; label.setVisible(Boolean(p));
        if(p){const q=px(p);label.setPosition(Math.min(490,q.x+10),Math.max(38,q.y-21)).setText(e===0?'1':'2');circle(p,e===state.epoch?0xffc77e:0x829bb9,2);}
      });
      if (prediction) {
        const a=px(m.marks[0]), b=px(m.marks[1]); g.lineStyle(1,0x8fdbfa,.7); g.lineBetween(a.x,a.y,b.x,b.y);
        if(inside(prediction)){const q=px(prediction);g.lineBetween(b.x,b.y,q.x,q.y);circle(prediction,m.revealed?0x8fdbfa:0xffc77e,TOLERANCE);}
        else this.title.setText('ПРОГНОЗ ЗА ГРАНИЦЕЙ СНИМКА · УТОЧНИ ОТМЕТКИ');
      }
      if(m.frozen && inside(m.frozen.prediction)) circle(m.frozen.prediction,0xffc77e,TOLERANCE,true);
      // Ground truth enters presentation only after explicit reveal or explicit help.
      if(m.revealed && state.epoch===2){const q=px(c.truth.targets[2]);circle(c.truth.targets[2],0x7ee8be,2);g.lineStyle(1,0x7ee8be);g.lineBetween(q.x-12,q.y,q.x+12,q.y);g.lineBetween(q.x,q.y-12,q.x,q.y+12);}
      if(state.helpVisible && state.epoch===0) circle(c.truth.targets[0],0x7ee8be,4);
      if(state.epoch<2){const q=px(state.cursor);g.lineStyle(1,0xe7efff,.65);g.lineBetween(q.x-7,q.y,q.x+7,q.y);g.lineBetween(q.x,q.y-7,q.x,q.y+7);}
    }
  }
  document.querySelectorAll('[data-epoch]').forEach(b => b.onclick=()=>selectEpoch(Number(b.dataset.epoch)));
  document.querySelectorAll('[data-case]').forEach(b => b.onclick=()=>{
    stopBlink();state.caseIndex=Number(b.dataset.case);state.epoch=0;state.blend=0;state.helpVisible=false;$('#blend').value=0;sync();sources();
  });
  $('#blink').onclick=()=>{
    if(state.blinking){stopBlink();sync();return;}
    state.blend=0;$('#blend').value=0;state.epoch=0;state.blinking=true;
    $('#blink').textContent='Остановить чередование';$('#blink').setAttribute('aria-pressed','true');
    blinkTimer=setInterval(()=>{state.epoch=state.epoch===0?1:0;sync();},650);sync();
  };
  $('#blend').oninput=e=>{stopBlink();state.epoch=0;state.blend=Number(e.target.value);sync();};
  $('#test').onclick=()=>{if(current().test())selectEpoch(2);};
  $('#help').onclick=()=>{state.helpVisible=!state.helpVisible;if(state.helpVisible){current().assisted=true;selectEpoch(0);}sync();};
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stopBlink();state.dragging=false;sync();}});
  function sources(){const c=item();$('#sources').innerHTML='<p>Поле '+esc(c.id)+' · α '+c.ra+'° · δ '+c.dec+'°.</p>'+c.observations.map((o,e)=>'<p>Кадр '+(e+1)+': '+esc(date(o))+' · экспозиция '+o.exposure+' с · <a href="'+esc(o.source)+'" target="_blank" rel="noopener">Исходный FITS ↗</a></p>').join('')+'<p class="credit">'+esc(c.source.credit)+'</p><p>'+esc(c.truth.note)+'</p><p>Источник центроидов: '+esc(c.truth.source)+'</p>';}
  sources();
  new Phaser.Game({type:Phaser.AUTO,parent:'game',width:520,height:552,backgroundColor:'#070c15',
    scene:ObservationScene,render:{antialias:false},scale:{mode:Phaser.Scale.FIT,autoCenter:Phaser.Scale.CENTER_BOTH},
    fps:{target:60},audio:{noAudio:true}});
})();
