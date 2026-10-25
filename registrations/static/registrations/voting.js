/* Database-backed competition workflow. Scores and transitions are authoritative on the server. */
(() => {
  const config = JSON.parse(document.getElementById('voting-data').textContent);
  let state = config.state, revision = config.revision, generation = 0, savedGeneration = 0;
  let queue = Promise.resolve(), timer, pending = 0, conflict = false;
  const step = config.step, app = document.getElementById('voting-app');
  const status = document.getElementById('save-status'), error = document.getElementById('vote-error');
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const uid = () => crypto.randomUUID();
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const person = (number) => ({id:uid(),original:number,name:'',phone:'',instagram:'',finalist:false,final:null,dq:false,reason:''});
  const people = () => state.contestants.filter(c => c.name.trim());
  const finalists = () => people().filter(c => !state.shortlist.enabled || c.finalist);
  const number = c => c.final || c.original;
  const frozen = config.locked || config.completed;
  const fail = message => { error.textContent = message; error.hidden = false; };
  function changed() {
    generation++; status.textContent = 'Є незбережені зміни…';
    if (config.phase > step && step < 5 && !frozen) {
      fail('Зміна попереднього кроку скасовує готовність наступних етапів. Перевірте фіналістів, номери та голоси ще раз.');
    }
    if (step >= 6) {
      fail('Результати змінилися. Перераховуйте їх перед оголошенням або завантаженням PDF.');
      const pdf = document.getElementById('pdf-link'); if (pdf) pdf.hidden = true;
      const next = document.querySelector('#vote-form [type=submit]'); if (next) next.disabled = true;
    }
    clearTimeout(timer); timer = setTimeout(() => save('save').catch(() => {}), 650);
  }
  function enqueue(task) { const next = queue.then(task); queue = next.catch(() => {}); return next; }
  function save(action = 'save') {
    clearTimeout(timer);
    return enqueue(async () => {
      if (conflict) throw new Error('Оновіть сторінку після конфлікту версій.');
      if (config.completed || (action === 'save' && generation === savedGeneration)) return;
      pending++; status.textContent = 'Зберігаємо…';
      const sentGeneration = generation;
      try {
        const response = await fetch(config.saveUrl, {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({state,revision,step,action})});
        let result;
        try { result = await response.json(); } catch (_) { throw new Error('Сесію входу завершено або сервер недоступний. Збережіть незаписані дані й увійдіть знову.'); }
        if (!response.ok) { if (response.status === 409) conflict = true; throw new Error(result.error || 'Не вдалося зберегти. Спробуйте ще раз.'); }
        revision = result.revision; savedGeneration = sentGeneration;
        if (generation === sentGeneration) {
          const finals = new Map(result.state.contestants.map(c => [c.id,c.final]));
          state.contestants.forEach(c => {c.final = finals.get(c.id) ?? null;});
          state.shortlist.confirmed = result.state.shortlist.confirmed;
        }
        status.textContent = generation === savedGeneration ? 'Збережено ✓' : 'Є незбережені зміни…';
        if (result.destination) { savedGeneration = generation; location.href = result.destination; }
        return result;
      } catch (e) { status.textContent = 'Не збережено'; fail(e.message); throw e; }
      finally { pending--; }
    });
  }
  function bind(id, event, callback) { const el = document.getElementById(id); if (el) el.addEventListener(event, callback); }
  function photoUrl(c) { return config.photoUrl + '?contestant=' + encodeURIComponent(c.id) + '&v=' + revision; }
  async function upload(c, file, remove=false) {
    try {
      await save();
      await enqueue(async () => {
        status.textContent = 'Зберігаємо фото…'; pending++;
        try {
          const body = new FormData(); body.append('contestant', c.id); body.append('revision',revision);
          if (remove) body.append('remove','1'); else body.append('photo',file);
          const response = await fetch(config.photoUrl,{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':csrf},body});
          const result = await response.json();
          if (!response.ok) { if (response.status === 409) conflict = true; throw new Error(result.error || 'Не вдалося зберегти фото.'); }
          revision = result.revision; status.textContent = 'Збережено ✓';
          const img = document.getElementById('photo-' + c.id); img.hidden = remove; if (!remove) img.src = photoUrl(c);
        } finally { pending--; }
      });
    } catch(e) { status.textContent = 'Не збережено'; fail(e.message); }
  }
  if (step === 1) {
    function renderJury() {
      const box = document.getElementById('jury-editor'); box.replaceChildren();
      state.jury.forEach(j => {
        const row = document.createElement('div'); row.className='vote-row vote-person';
        row.innerHTML=`<label>Журі ${esc(j.code)}<input type="text" maxlength="200" value="${esc(j.name)}" aria-label="Ім’я журі ${esc(j.code)}"></label><label><input type="checkbox" ${j.active?'checked':''}> Бере участь</label>`;
        row.querySelector('[type=text]').addEventListener('input',e => {j.name=e.target.value;changed();});
        row.querySelector('[type=checkbox]').addEventListener('change',e => {j.active=e.target.checked;changed();}); box.append(row);
      });
    }
    renderJury();
    bind('add-jury','click',() => {
      let n=state.jury.length, code=''; do {code=String.fromCharCode(65+n%26)+code;n=Math.floor(n/26)-1;}while(n>=0);
      state.jury.push({id:uid(),code,name:'',active:true});renderJury();changed();
    });
  }
  if (step === 2) {
    const initialCount = state.contestants.length;
    if (!frozen) while(state.contestants.length < 10) state.contestants.push(person(Math.max(0,...state.contestants.map(c=>c.original))+1));
    const box=document.getElementById('contestant-editor');
    function renderPeople() {
      box.replaceChildren(); state.contestants.forEach(c => {
        const row=document.createElement('div');row.className='vote-person';
        row.innerHTML=`<div class="vote-row"><label>№ реєстрації<input type="number" min="1" value="${c.original}" data-field="original"></label><label>Ім’я учасника<input type="text" maxlength="200" value="${esc(c.name)}" data-field="name"></label></div><details><summary>Фото та контакти — необов’язково</summary><div class="vote-input-grid"><label>Instagram<input type="text" maxlength="240" value="${esc(c.instagram)}" data-field="instagram"></label><label>Телефон<input type="tel" maxlength="80" value="${esc(c.phone)}" data-field="phone"></label></div><img class="vote-photo" id="photo-${c.id}" alt="Фото учасника" hidden><label>Обрати або замінити фото<input type="file" accept="image/jpeg,image/png,image/webp" data-upload="file"></label><label>Зробити фото на телефоні<input type="file" accept="image/*" capture="environment" data-upload="camera"></label><button type="button" data-remove>Видалити фото</button></details>`;
        row.querySelectorAll('[data-field]').forEach(input=>input.addEventListener('input',e=>{c[input.dataset.field]=input.type==='number'?Number(input.value):input.value;changed();}));
        row.querySelectorAll('[data-upload]').forEach(input=>input.addEventListener('change',()=>{if(input.files[0])upload(c,input.files[0]);}));
        row.querySelector('[data-remove]').addEventListener('click',()=>{if(confirm('Видалити фото учасника?'))upload(c,null,true);});
        const img=row.querySelector('img');img.onload=()=>{img.hidden=false;};img.onerror=()=>{img.hidden=true;};img.src=photoUrl(c);
        box.append(row);
      });
    }
    renderPeople();
    bind('add-contestant','click',()=>{state.contestants.push(person(Math.max(0,...state.contestants.map(c=>c.original))+1));renderPeople();changed();});
    if (!frozen && state.contestants.length !== initialCount) changed();
  }
  if (step === 3) {
    const enabled=document.getElementById('shortlist-enabled'),target=document.getElementById('shortlist-target');
    enabled.checked=state.shortlist.enabled;target.value=state.shortlist.target||Math.min(10,people().length-1);
    function update() {
      document.getElementById('shortlist-controls').hidden=!state.shortlist.enabled;
      document.getElementById('shortlist-progress').textContent=`Обрано ${finalists().length} із ${state.shortlist.target}`;
      document.querySelectorAll('[data-finalist]').forEach(el=>{el.hidden=!state.shortlist.enabled;});
    }
    people().forEach(c=>{
      const card=document.createElement('div');card.className='vote-tile';
      card.innerHTML=`<img class="vote-photo" src="${photoUrl(c)}" alt="Фото учасника"><strong>Реєстрація №${c.original} — ${esc(c.name)}</strong><label data-finalist><input type="checkbox" ${c.finalist?'checked':''}> Фіналіст</label>`;
      card.querySelector('img').onerror=e=>{e.target.hidden=true;};
      card.querySelector('input').addEventListener('change',e=>{c.finalist=e.target.checked;state.shortlist.confirmed=false;update();changed();});
      document.getElementById('shortlist-editor').append(card);
    });
    enabled.addEventListener('change',()=>{state.shortlist.enabled=enabled.checked;state.shortlist.target=Number(target.value);state.shortlist.confirmed=false;update();changed();});
    target.addEventListener('input',()=>{state.shortlist.target=Number(target.value);state.shortlist.confirmed=false;update();changed();});update();
  }
  function disqualifications(container) {
    if (!container) return;
    finalists().forEach(c=>{
      const row=document.createElement('div');row.className='vote-dq';
      row.innerHTML=`<label><input type="checkbox" ${c.dq?'checked':''}> Дискваліфіковано: №${number(c)} — ${esc(c.name)}</label><label>Причина (можна додати пізніше)<textarea maxlength="2000" rows="2">${esc(c.reason)}</textarea></label>`;
      row.querySelector('textarea').parentElement.hidden=!c.dq;
      row.querySelector('input').addEventListener('change',e=>{
        if(e.target.checked && !confirm('Дискваліфікувати учасника? Голоси та оцінки збережуться, але не братимуть участі у підсумковому розрахунку.')){e.target.checked=false;return;}
        c.dq=e.target.checked;row.querySelector('textarea').parentElement.hidden=!c.dq;changed();
      });
      row.querySelector('textarea').addEventListener('input',e=>{c.reason=e.target.value;changed();});container.append(row);
    });
  }
  if (step === 4) {
    const total=document.getElementById('total-ballots'),invalid=document.getElementById('invalid-ballots');
    total.value=state.ballots.total;invalid.value=state.ballots.invalid;
    function summary() {
      const valid=state.ballots.total-state.ballots.invalid,entered=finalists().reduce((sum,c)=>sum+(state.ballots.votes[c.id]||0),0),delta=valid-entered;
      document.getElementById('ballot-summary').textContent=`Усього: ${state.ballots.total} · Недійсні: ${state.ballots.invalid} · Дійсні: ${valid} · Внесено: ${entered} · ${delta===0?'Усе збігається ✓':delta>0?'Залишилося внести: '+delta:'Зайвих голосів: '+(-delta)}`;
    }
    [total,invalid].forEach(el=>el.addEventListener('input',()=>{state.ballots.total=Number(total.value);state.ballots.invalid=Number(invalid.value);summary();changed();}));
    const table=document.createElement('table');table.innerHTML='<thead><tr><th>№ / ім’я</th><th>Голосів</th></tr></thead><tbody></tbody>';
    finalists().forEach(c=>{const tr=document.createElement('tr');tr.innerHTML=`<td>№${number(c)} — ${esc(c.name)}${c.dq?' · Дискваліфіковано':''}</td><td><input type="number" min="0" value="${state.ballots.votes[c.id]||0}" aria-label="Голоси за ${esc(c.name)}"></td>`;tr.querySelector('input').addEventListener('input',e=>{state.ballots.votes[c.id]=Number(e.target.value);summary();changed();});table.querySelector('tbody').append(tr);});
    const wrap=document.getElementById('audience-editor');wrap.className='vote-scroll';wrap.append(table);disqualifications(wrap);summary();
  }
  if (step === 5) {
    const jury=state.jury.filter(j=>j.active), table=document.createElement('table');
    table.innerHTML='<thead><tr><th>№ / ім’я</th>'+jury.map(j=>`<th>Журі ${esc(j.code)}<br>${esc(j.name)}</th>`).join('')+'</tr></thead><tbody></tbody>';
    function summary() {
      document.getElementById('jury-summary').textContent=jury.map(j=>{const scores=state.scores[j.id]||{};const counts=[5,3,1].map(v=>finalists().filter(c=>scores[c.id]===v).length);return `Журі ${j.code}: ${counts.every(n=>n===1)?'готово ✓':`оцінок 5: ${counts[0]}, 3: ${counts[1]}, 1: ${counts[2]} (потрібна одна кожного виду)`}`;}).join(' · ');
    }
    finalists().forEach(c=>{const tr=document.createElement('tr');const name=document.createElement('td');name.textContent=`№${number(c)} — ${c.name}`;tr.append(name);jury.forEach(j=>{const td=document.createElement('td'),select=document.createElement('select');select.className='score-cell';select.setAttribute('aria-label',`Журі ${j.code} — ${c.name}`);[0,1,3,5].forEach(v=>select.add(new Option(String(v),String(v))));select.value=state.scores[j.id]?.[c.id]||0;select.addEventListener('change',()=>{state.scores[j.id]??={};state.scores[j.id][c.id]=Number(select.value);summary();changed();});td.append(select);tr.append(td);});table.querySelector('tbody').append(tr);});
    document.getElementById('score-editor').append(table);summary();
  }
  if(step===5||step===6) disqualifications(document.getElementById('disqualification-editor'));
  if(frozen && step<5 || config.completed) app.querySelectorAll('#vote-form input:not([type=hidden]),#vote-form select,#vote-form textarea,#add-jury,#add-contestant,[data-remove]').forEach(el=>{el.disabled=true;});
  if(config.completed) app.querySelectorAll('#recalculate').forEach(el=>el.disabled=true);
  async function transition(action) {
    const controls = [...app.querySelectorAll('input:not([type=hidden]),select,textarea,button')];
    const enabled = controls.filter(el=>!el.disabled);
    enabled.forEach(el=>{el.disabled=true;});
    try { await save(action); } catch(e) { enabled.forEach(el=>{el.disabled=false;}); }
  }
  bind('save-now','click',()=>save().catch(()=>{}));
  document.getElementById('vote-form').addEventListener('submit',async e=>{
    e.preventDefault();error.hidden=true;
    if(step===4&&!config.locked&&!confirm('Почати оцінювання журі та заблокувати попередні етапи?'))return;
    await transition('next');
  });
  bind('recalculate','click',()=>transition('calculate'));
  bind('complete','click',()=>{if(confirm('Завершити голосування та заблокувати подальші зміни?'))transition('complete');});
  app.querySelectorAll('a').forEach(link=>link.addEventListener('click',async e=>{
    if(generation===savedGeneration&&!pending)return;
    e.preventDefault();try{await save();if(link.id==='pdf-link'&&step>=6){fail('Спочатку перераховуйте змінені результати.');return;}location.href=link.href;}catch(_){}
  }));
  window.addEventListener('beforeunload',e=>{if(generation!==savedGeneration||pending){e.preventDefault();e.returnValue='';}});
})();
