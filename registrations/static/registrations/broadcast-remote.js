/* A phone controls the same persisted show as the projector; commands are never queued offline. */
(() => {
  const config=JSON.parse(document.getElementById('remote-config').textContent);
  const next=document.getElementById('remote-next'),previous=document.getElementById('remote-previous');
  const connection=document.getElementById('connection'),error=document.getElementById('remote-error'),status=document.getElementById('command-status');
  let frame=null,busy=false,connected=false,blocked=false,refreshing=false,lastTap=-1000;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const cookie=name=>document.cookie.split('; ').find(c=>c.startsWith(name+'='))?.split('=').slice(1).join('=')||'';
  function controls(){next.disabled=busy||!connected||blocked||!frame||frame.position===frame.last;previous.disabled=busy||!connected||blocked||!frame||frame.position===0;}
  function showError(text){error.textContent=text;error.hidden=false;}
  function render(data){
    if(frame&&data.revision<=frame.revision)return;
    frame=data;
    document.getElementById('show-title').textContent=data.title;
    document.getElementById('counter').textContent=`Кадр ${data.position+1} / ${data.last+1}`;
    document.getElementById('stage-label').textContent=data.stage_label||data.headline||'Оголошення результатів';
    let html='';
    const person=data.current||data.awardees?.[0];
    if(person){
      html=`${person.photo?`<img class="current-photo" src="${esc(person.photo)}" alt="">`:''}<p class="current-number">Учасник №${person.number}</p><p class="current-name">${esc(person.name)}</p><div class="remote-score"><div><span>Журі</span><b>${person.jury}</b></div><div><span>Глядачі</span><b>${person.audience??'—'}</b></div><div><span>Разом</span><b>${person.total??'—'}</b></div></div>`;
      if((data.awardees?.length||0)>1)html+=`<p class="remote-help">Спільне місце: ${data.awardees.map(r=>esc(r.name)).join(', ')}.</p>`;
    }else if(data.scene==='jury_points')html=`<p class="points-only">${data.jury_points}</p><p class="remote-help">Балів від журі. Ім’я з’явиться наступним кліком.</p>`;
    else html=`<p class="current-name">${esc(data.headline||({'welcome':'Початкова заставка','jury':'Перша група результатів журі','final':'Підсумкова таблиця'}[data.scene])||'Оголошення результатів')}</p>${data.context?`<p class="remote-help">${esc(data.context)}</p>`:''}`;
    document.getElementById('current-person').innerHTML=html;
    document.querySelector('.current-photo')?.addEventListener('error',e=>e.target.remove());
    controls();
  }
  async function fetchState(action){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{
      const options=action?{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(cookie('csrftoken'))},body:JSON.stringify({revision:frame.revision,action})}:{};
      const response=await fetch(config.url,{...options,credentials:'same-origin',cache:'no-store',signal:controller.signal});
      const data=await response.json();
      if(response.status===410){
        blocked=true;connected=false;connection.textContent='Показ вимкнено';connection.dataset.state='offline';
        showError(data.error);document.getElementById('current-person').replaceChildren();status.textContent='Попросіть організатора актуальне посилання на пульт';controls();return false;
      }
      if(data.frame)render(data.frame);
      if(!response.ok&&response.status!==409)throw new Error(data.error||'Не вдалося отримати підтвердження.');
      connected=true;connection.dataset.state='online';connection.textContent='З’єднано з показом';error.hidden=true;
      if(response.status===409)status.textContent='Кадр уже перемкнули з іншого пристрою. Пульт синхронізовано.';
      else if(!busy)status.textContent=frame.position===frame.last?'Останній кадр показу':'Готово до наступного натискання';
      controls();return response.status!==409;
    }catch(_){
      connected=false;connection.dataset.state='offline';connection.textContent='Немає зв’язку';
      showError('Не вдалося підтвердити зв’язок. Перевірте інтернет. Команди без зв’язку не накопичуються.');status.textContent='Відновлюємо з’єднання…';controls();return false;
    }finally{clearTimeout(timer);}
  }
  async function refresh(){if(busy||refreshing||blocked||document.hidden)return;refreshing=true;try{await fetchState();}finally{refreshing=false;}}
  async function command(action){
    if(busy||!connected||!frame||blocked||performance.now()-lastTap<700)return;
    if(action==='next'&&frame.position===frame.last||action==='previous'&&frame.position===0)return;
    busy=true;lastTap=performance.now();status.textContent='Перемикаємо кадр…';controls();
    try{
      const acknowledged=await fetchState(action);
      if(acknowledged)status.textContent=frame.position===frame.last?'Показ завершився фінальним кадром':'Кадр перемкнено ✓';
      else if(!blocked&&!connected)await fetchState();
    }finally{busy=false;controls();}
  }
  next.addEventListener('click',()=>command('next'));previous.addEventListener('click',()=>command('previous'));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  window.addEventListener('online',refresh);
  window.addEventListener('offline',()=>{connected=false;connection.dataset.state='offline';connection.textContent='Немає зв’язку';status.textContent='Перевірте підключення до інтернету';controls();});
  refresh();setInterval(refresh,1000);
})();
