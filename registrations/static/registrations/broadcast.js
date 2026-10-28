/* A frame contains only results already revealed by the database-backed show. */
(() => {
  const config = JSON.parse(document.getElementById('show-config').textContent);
  const scene = document.getElementById('scene'), message = document.getElementById('show-message');
  const next = document.getElementById('next'), previous = document.getElementById('previous');
  let frame = null, busy = false, blocked = false, page = 0, lastInteraction = 0, hideTimer, messageTimer;
  const PAGE_SIZE = 10;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const cookie = name => document.cookie.split('; ').find(c => c.startsWith(name + '='))?.split('=').slice(1).join('=') || '';
  const notify = text => {clearTimeout(messageTimer); message.textContent = text; message.hidden = false; messageTimer = setTimeout(() => {if(!blocked)message.hidden=true;},6000);};
  function controls() {
    document.body.classList.remove('hide-controls'); clearTimeout(hideTimer);
    hideTimer=setTimeout(()=>{if(!document.querySelector('.show-controls:focus-within'))document.body.classList.add('hide-controls');},4500);
  }
  const values = r => `<div class="result-breakdown"><div><span>Журі</span><b>${r.jury}</b></div><div><span>Глядачі</span><b>${r.audience === null ? '—' : r.audience}</b></div><div class="total"><span>Разом</span><b>${r.total === null ? '—' : r.total}</b></div></div>`;
  const portrait = r => r.photo?`<figure class="contestant-portrait"><img src="${esc(r.photo)}" alt="${esc(r.name)}"></figure>`:'';
  const identity = r => `<div class="contestant-identity ${r.photo?'has-photo':''}"><div><p class="number">УЧАСНИК №${r.number}</p><h1 class="${r.name.length>70?'very-long-name':r.name.length>35?'long-name':''}">${esc(r.name)}</h1></div>${portrait(r)}</div>`;
  function applyBranding(data) {
    const branding=data.branding||{};
    const logo=document.getElementById('stage-logo'), fallback=document.querySelector('.brand-fallback');
    const mascot=document.getElementById('stage-mascot');
    [[logo,branding.logo],[mascot,branding.mascot]].forEach(([img,url])=>{
      img.hidden=!url;
      if(url&&img.getAttribute('src')!==url)img.src=url;
    });
    fallback.hidden=Boolean(branding.logo);
    logo.onerror=()=>{logo.hidden=true;fallback.hidden=false;};
    mascot.onerror=()=>{mascot.hidden=true;};
  }
  function welcomeSlide(data) {
    const brand=data.branding||{};
    return `<section class="welcome ${brand.logo?'with-logo':''} ${brand.mascot?'with-mascot':''}"><div class="welcome-content"><p class="eyebrow">КОНКУРС КОСТЮМІВ</p>${brand.logo?`<img class="welcome-logo" src="${esc(brand.logo)}" alt="DISCO UKRAÏNA">`:''}<h1>Ця ніч.<br>Ваші фаворити.</h1><p class="event-title">${esc(data.title)}</p><div class="bank-intro"><span><b>250</b>балів від журі</span><span><b>750</b>балів від глядачів</span></div></div>${brand.mascot?`<figure class="welcome-mascot"><img src="${esc(brand.mascot)}" alt="Гарбуз — символ події"></figure>`:''}</section>`;
  }
  function awardSlide(data) {
    const people=data.awardees, shared=people.length>1;
    const cards=people.slice(0,3).map(r=>`<article class="award-person">${portrait(r)}<p class="award-number">УЧАСНИК №${r.number}</p><h1 class="${r.name.length>70?'very-long-name':''}">${esc(r.name)}</h1><div class="award-score"><b>${r.total}</b><span>БАЛІВ</span></div>${values(r)}</article>`).join('');
    const mascot=data.scene==='victory'&&data.branding?.mascot?`<img class="award-brand-mascot" src="${esc(data.branding.mascot)}" alt="">`:'';
    return `<section class="award-scene ${data.scene==='victory'?'victory-scene':''} ${shared?'shared-award':''}" data-place="${data.award_place}"><div class="award-halo" aria-hidden="true"></div><header class="award-title"><span class="award-emblem" aria-hidden="true">${data.scene==='victory'?'✦':data.award_place}</span><p class="eyebrow">${data.scene==='victory'?'DISCO UKRAÏNA · КОНКУРС КОСТЮМІВ':'ФІНАЛЬНИЙ П’ЄДЕСТАЛ'}</p><h2>${esc(data.headline)}</h2></header><div class="award-people">${cards}</div>${people.length>3?`<p class="award-more">Спільне місце — ${people.length} учасників. Усі імена є в підсумковій таблиці.</p>`:''}<p class="award-congratulations">${data.scene==='victory'?'Ваша мить. Ваші оплески. Дякуємо, що створили цю ніч разом із нами!':'Вітаємо! Ці оплески — для вас.'}</p>${mascot}</section>`;
  }
  function board(data) {
    const count=data.board.length, pages=Math.max(1,Math.ceil(count/PAGE_SIZE));page=Math.min(page,pages-1);
    const visible=data.board.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE), columns=[visible];
    const rows=column => `<div class="board-column"><div class="board-head"><span>#</span><span>УЧАСНИК</span><span>ЖУРІ</span><span>ГЛЯДАЧІ</span><span>РАЗОМ</span></div>${column.map(r=>`<div class="board-row ${r.current?'current':''} ${r.rank===1?'leading':''} ${r.revealed?'audience-revealed':'pending'}" data-number="${r.number}"><span class="rank">${r.rank??'·'}</span><div class="board-name"><small>№${r.number??'—'}</small><strong title="${esc(r.name)}">${esc(r.name)}</strong></div><span class="jury">${r.jury??'—'}</span><span class="audience">${r.revealed?'<small class="audience-check" aria-label="Голоси оголошено">✓</small>':''}${r.audience===null?'—':r.audience}</span><span class="total">${r.total??'—'}</span></div>`).join('')}</div>`;
    return `<section class="standing-panel"><div class="standing-title"><h2>${data.scene==='final'?'Фінальна таблиця':['jury','jury_top','jury_points'].includes(data.scene)?'Рішення журі':'Таблиця результатів'}</h2><span>${data.scene==='final'?'1000 / 1000 БАЛІВ':['jury','jury_top','jury_points'].includes(data.scene)?'ЖУРІ · 250 БАЛІВ':data.revealed+' / '+data.count+' РЕЗУЛЬТАТІВ'}</span></div><div class="board-columns ${columns.length>1?'two':''}">${columns.map(rows).join('')}</div>${pages>1?`<div class="board-pages"><button type="button" data-page="-1" aria-label="Попередня частина таблиці">←</button><span>Рядки ${page*PAGE_SIZE+1}–${Math.min(count,(page+1)*PAGE_SIZE)} із ${count}</span><button type="button" data-page="1" aria-label="Наступна частина таблиці">→</button></div>`:''}</section>`;
  }
  function render(data, animate=true) {
    const old = frame;
    applyBranding(data);
    frame=data;blocked=false;message.hidden=true;
    document.body.dataset.theme=data.theme;
    document.body.dataset.scene=data.scene;
    document.body.dataset.place=data.award_place||'';
    document.getElementById('event-name').textContent=data.title;
    document.getElementById('show-context').textContent=data.stage_label||'ОГОЛОШЕННЯ РЕЗУЛЬТАТІВ';
    document.getElementById('progress-text').textContent=data.scene==='welcome'?'ОГОЛОШЕННЯ РЕЗУЛЬТАТІВ':['jury','jury_top','jury_points'].includes(data.scene)?'ОГОЛОШЕННЯ ЖУРІ':['podium','victory'].includes(data.scene)?'НАГОРОДЖЕННЯ':`ГЛЯДАЧІ: ${data.revealed} / ${data.count}`;
    document.getElementById('progress-fill').style.width=(data.revealed/data.count*100)+'%';
    document.getElementById('frame-counter').textContent=`${data.position+1} / ${data.last+1}`;
    next.disabled=data.position===data.last;previous.disabled=data.position===0;
    let html;
    if(data.scene==='welcome') {
      html=welcomeSlide(data);
    } else if(['jury_intro','audience_intro'].includes(data.scene)) {
      html=`<section class="phase-intro"><p class="eyebrow">${data.scene==='jury_intro'?'ПЕРШИЙ ЕТАП · 250 БАЛІВ':'ДРУГИЙ ЕТАП · 750 БАЛІВ'}</p><h1>${esc(data.headline)}</h1><p class="phase-explanation">${esc(data.context)}</p></section>`;
    } else if(data.scene==='jury') {
      html=`<div class="arena jury-arena"><section class="spotlight"><p class="eyebrow">ПЕРШИЙ АКОРД</p><h1>Слово<br>журі.</h1><p>${data.count>data.top_count?'Перші результати — на екрані.':'Кожен фіналіст отримає своє оголошення.'}<br>Далі оголосимо ${data.top_count} головних результатів журі.</p><div class="result-breakdown"><div><span>Журі</span><b>25%</b></div><div><span>Глядачі</span><b>75%</b></div></div></section>${board(data)}</div>`;
    } else if(data.scene==='jury_points') {
      html=`<div class="arena"><section class="spotlight jury-suspense"><p class="eyebrow">ЖУРІ · ОГОЛОШЕННЯ ${data.jury_sequence} / ${data.top_count}</p><h1>Ці бали<br>отримує…</h1><div class="reveal-value score-burst">${data.jury_points}</div><span class="reveal-label">балів від журі</span><p class="headline">Кого обрало журі?</p></section>${board(data)}</div>`;
    } else if(data.scene==='jury_top') {
      const r=data.current;
      html=`<div class="arena"><section class="spotlight"><p class="eyebrow">${data.top_count===5?'П’ЯТІРКА ЖУРІ':'РЕЗУЛЬТАТИ ЖУРІ'} · ${r.sequence} / ${data.top_count}</p>${identity(r)}<div class="reveal-value score-burst">${r.jury}</div><span class="reveal-label">балів від журі</span><p class="headline">Попереду — голоси глядачів</p></section>${board(data)}</div>`;
    } else if(['podium','victory'].includes(data.scene)) {
      html=awardSlide(data);
    } else if(data.scene==='final') {
      const shared=data.winners.length>1,winner=data.winners[0];
      html=`<div class="arena final-arena"><section class="spotlight"><div class="winner-mark" aria-hidden="true">✦</div><p class="eyebrow">${esc(data.headline)}</p>${shared?`<h1>${data.winners.slice(0,3).map(r=>esc(r.name)).join('<br>')}${data.winners.length>3?'<br><small>та ще '+(data.winners.length-3)+' учасників</small>':''}</h1><div class="shared-portraits">${data.winners.slice(0,3).map(portrait).join('')}</div>`:identity(winner)}${shared?data.winners.slice(0,3).map(r=>`<p class="final-notice">№${r.number} — ${r.jury} від журі + ${r.audience} від глядачів = ${r.total} балів</p>`).join(''):`<div class="reveal-value score-burst">${winner.total}</div>${values(winner)}`}<p class="final-notice">Вітаємо! Дякуємо всім учасникам.</p>${data.notices.map(text=>`<p class="final-notice">${esc(text)}</p>`).join('')}</section>${board(data)}</div>`;
    } else {
      const r=data.current;
      const phrase=data.scene==='contestant'?(r.sequence===data.count?'ОСТАННІЙ РЕЗУЛЬТАТ':data.count-r.sequence<3?'ФІНАЛЬНІ ОГОЛОШЕННЯ':'ГЛЯДАЧІ ВИЗНАЧИЛИСЯ'):data.scene==='audience'?'ВІД ГЛЯДАЧІВ':'ЖУРІ + ГЛЯДАЧІ';
      const value=data.scene==='contestant'?'?':data.scene==='audience'?`+${r.audience}`:r.total;
      html=`<div class="arena"><section class="spotlight"><p class="eyebrow">${phrase}</p>${identity(r)}<div class="reveal-value ${animate?'score-burst':''}">${value}</div><span class="reveal-label">${data.scene==='contestant'?'Скільки балів додадуть глядачі?':data.scene==='audience'?'балів від глядачів':'балів разом'}</span>${values(r)}${data.headline?`<p class="headline">${esc(data.headline)}</p>`:''}</section>${board(data)}</div>`;
    }
    const oldRects = new Map([...scene.querySelectorAll('.board-row')].map(el=>[el.dataset.number,el.getBoundingClientRect()]));
    scene.innerHTML=html;
    scene.querySelectorAll('.contestant-portrait img').forEach(img=>img.addEventListener('error',()=>{img.parentElement.remove();scene.querySelectorAll('.contestant-identity').forEach(el=>el.classList.remove('has-photo'));}));
    const currentScene=scene.firstElementChild;
    if(animate)currentScene.classList.add('entrance');
    scene.querySelectorAll('[data-page]').forEach(button=>button.addEventListener('click',event=>{event.stopPropagation();page=(page+Number(button.dataset.page)+Math.ceil(frame.board.length/PAGE_SIZE))%Math.ceil(frame.board.length/PAGE_SIZE);render(frame,false);}));
    if(animate&&old&&data.scene==='combined'&&!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      scene.querySelectorAll('.board-row').forEach(el=>{const before=oldRects.get(el.dataset.number),after=el.getBoundingClientRect();if(before&&Math.abs(before.top-after.top)>1)el.animate([{transform:`translateY(${before.top-after.top}px)`,opacity:.45},{transform:'translateY(0)',opacity:1}],{duration:800,easing:'cubic-bezier(.2,.8,.2,1)'});});
    }
    document.querySelector('.confetti')?.remove();
    if(animate&&(data.scene==='podium'||data.scene==='victory')&&old?.position!==data.position) {
      const confetti=document.createElement('div');confetti.className='confetti';confetti.setAttribute('aria-hidden','true');
      confetti.innerHTML=Array.from({length:data.scene==='victory'?95:55},(_,i)=>`<i style="--x:${(i*37)%100}%;--delay:${(i%9)*.14}s;--duration:${3+(i%5)*.4}s"></i>`).join('');document.body.append(confetti);setTimeout(()=>confetti.remove(),8000);
    }
  }
  async function request(action) {
    const controller = new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
    try {
      const options=action?{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(cookie('csrftoken'))},body:JSON.stringify({revision:frame.revision,action})}:{};
      const response=await fetch(config.url,{...options,credentials:'same-origin',cache:'no-store',signal:controller.signal});
      const data=await response.json();
      if(response.status===410){blocked=true;scene.innerHTML='<section class="welcome"><p class="eyebrow">ПОКАЗ ЗУПИНЕНО</p><h1>До нових<br>зустрічей.</h1><p class="event-title">Організатор має підготувати актуальне посилання.</p></section>';next.disabled=true;previous.disabled=true;notify(data.error);return;}
      if(data.frame&&(!frame||data.frame.revision>frame.revision||(data.frame.revision===frame.revision&&data.frame.brand_version!==frame.brand_version))) {
        if(data.frame.current){const currentIndex=data.frame.board.findIndex(r=>r.current);if(currentIndex>=0)page=Math.floor(currentIndex/PAGE_SIZE);}else page=0;
        render(data.frame);
      }
      if(!response.ok){notify(data.error||'Не вдалося змінити кадр. Спробуйте ще раз.');return;}
      if(!frame&&data.frame)render(data.frame);
    } catch(_){notify('Немає зв’язку з сервером. Поточний кадр збережено. Перевірте інтернет і повторіть клік.');}
    finally{clearTimeout(timeout);}
  }
  async function advance(action) {
    if(!frame||blocked||busy||performance.now()-lastInteraction<650)return;
    if(action==='next'&&frame.position===frame.last||action==='previous'&&frame.position===0)return;
    busy=true;lastInteraction=performance.now();next.disabled=previous.disabled=true;controls();
    try{await request(action);}finally{busy=false;next.disabled=blocked||frame.position===frame.last;previous.disabled=blocked||frame.position===0;}
  }
  async function fullscreen() {
    try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();else await document.exitFullscreen();}
    catch(_){notify('Браузер не дозволив повноекранний режим. Скористайтеся його меню або клавішею F11.');}
  }
  next.addEventListener('click',event=>{advance('next');if(event.detail)next.blur();});previous.addEventListener('click',event=>{advance('previous');if(event.detail)previous.blur();});
  document.getElementById('fullscreen').addEventListener('click',event=>{fullscreen();if(event.detail)event.currentTarget.blur();});
  document.getElementById('stage').addEventListener('click',event=>{if(!event.target.closest('button,a,input,select,textarea'))advance('next');});
  document.addEventListener('keydown',event=>{
    if(event.target.closest('input,select,textarea')||event.altKey||event.ctrlKey||event.metaKey)return;
    if(event.target.closest('button,a')&&[' ','Enter'].includes(event.key))return;
    if(['ArrowRight',' ','Enter','PageDown'].includes(event.key)){event.preventDefault();if(!event.repeat)advance('next');}
    if(['ArrowLeft','PageUp'].includes(event.key)){event.preventDefault();if(!event.repeat)advance('previous');}
    if(event.key.toLowerCase()==='f'){event.preventDefault();fullscreen();}
    controls();
  });
  document.addEventListener('mousemove',controls,{passive:true});document.addEventListener('touchstart',controls,{passive:true});document.addEventListener('focusin',controls);
  document.addEventListener('fullscreenchange',()=>{document.getElementById('fullscreen').textContent=document.fullscreenElement?'Згорнути екран':'На весь екран';controls();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!busy){controls();request();}});
  controls();request();setInterval(()=>{if(!busy&&!document.hidden)request();},1000);
})();
