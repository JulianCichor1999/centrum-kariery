/* Backend jest jedynym źródłem prawdy; ten magazyn jest odświeżanym widokiem. */
(function () {
  'use strict';
  const STATUSES = ['Przygotowanie','Wysłana','Rozmowa','Oferta współpracy','Odmowa','Wycofana'];
  const DIRECTIONS = ['Marketing i treści z AI','Automatyzacje i wdrożenia AI','Inne'];
  const MODES = ['Stacjonarna','Hybrydowa','Zdalna'], CONTRACTS = ['Umowa o pracę','Umowa zlecenie'];
  const fold = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ł/g,'l').replace(/Ł/g,'L').toLowerCase().replace(/\s+/g,' ').trim();
  const today = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Warsaw'}).format(new Date());
  function dayOffset(day,offset) { const value=new Date(`${day}T12:00:00Z`); value.setUTCDate(value.getUTCDate()+offset); return value.toISOString().slice(0,10); }
  function warsawTime(value) { const base=Date.parse(`${value}:00Z`), fmt=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Warsaw',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}); return [60,120].map(offset=>base-offset*60000).find(ms=>fmt.format(new Date(ms)).replace(' ','T')===value) ?? null; }
  class ValidationError extends Error { constructor(message,errors={},status=422) { super(message); this.errors=errors; this.status=status; } }
  async function createStore() {
    let cache, csrf;
    async function request(path,options={}) {
      let response;
      try { response=await fetch(path,{credentials:'same-origin',...options,headers:{...(options.method ? {'X-CSRF-Token':csrf} : {}),...options.headers}}); }
      catch { throw new ValidationError('Nie można połączyć się z lokalną aplikacją. Formularz zachowano; uruchom serwer i spróbuj ponownie.',{},503); }
      if (!response.ok) { const error=await response.json().catch(()=>({message:'Nie udało się zakończyć operacji.'})); throw new ValidationError(error.message,error.errors,response.status); }
      return response.json();
    }
    csrf=(await request('/api/session')).csrf; cache=await request('/api/state');
    const find=(table,key)=>{ const row=cache[table].find(item=>item.id===key); if (!row) throw new ValidationError('Rekord nie istnieje. Odśwież widok.'); return row; };
    const company=offer=>find('companies',offer.companyId), offer=app=>find('offers',app.offerId);
    const applicationLabel=key=>{ if (!key) return 'Bez aplikacji'; const app=find('applications',key), item=offer(app); return `${item.title} · ${company(item).name}${app.archived ? ' (archiwum)' : ''}`; };
    async function command(action,data={},key) {
      const tables={saveOffer:'offers',setStatus:'applications',saveTask:'tasks',toggleTask:'tasks',saveEvent:'events',saveProfile:'profile',saveEntry:'entries'};
      const row=key && tables[action] ? tables[action]==='profile' ? cache.profile : find(tables[action],key) : null;
      const result=await request('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,data,key:key||null,version:row?.rowVersion||null,revision:cache.revision})});
      cache=result.state; return result.id;
    }
    return {
      get state() { return cache; }, find, company, offer, applicationLabel, request,
      offerTextPreview:key=>request('/api/offers/'+encodeURIComponent(key)+'/read-link',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),
      async offerTextCommit(plan,text) { const result=await request('/api/offers/read-link/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:plan.token,revision:plan.revision,confirmed:true,text})});cache=result.state; },
      driveStatus:()=>request('/api/drive/status'),
      async driveClient(file,confirmed) { const form=new FormData(); form.append('file',file); form.append('confirmed',String(confirmed)); return request('/api/drive/client',{method:'POST',body:form}); },
      driveConnect:()=>request('/api/drive/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed:true})}),
      driveDisconnect:()=>request('/api/drive/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed:true})}),
      driveFolder:url=>request('/api/drive/folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})}),
      driveFiles:(folder='')=>request('/api/drive/files'+(folder?'?folder='+encodeURIComponent(folder):'')),
      drivePreview:selection=>request('/api/drive/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({selection})}),
      drivePreviewAll:()=>request('/api/drive/preview-all',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),
      async driveCommit(plan) { const result=await request('/api/drive/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:plan.token,revision:plan.revision,confirmed:true})}); cache=result.state; return result.ids; },
      aiStatus:()=>request('/api/ai/status'),
      async aiConfigure(model,enabled) { const result=await request('/api/ai/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,enabled,revision:cache.revision})}); cache=result.state; return result.status; },
      aiPrepare:(mode,applicationId,query,cv={})=>request('/api/ai/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,applicationId,query,...cv})}),
      async aiCommit(preview,draft) { const result=await request('/api/ai/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:preview.token,revision:preview.revision,confirmed:true,...(draft===undefined?{}:{draft})})}); cache=result.state; return result.ids; },
      async refresh() { cache=await request('/api/state'); },
      async saveOffer(data,key) { return find('offers',await command('saveOffer',data,key)); },
      async createApplication(key) { return find('applications',await command('createApplication',{offerId:key})); },
      setStatus:(key,status,confirmed)=>command('setStatus',{status,confirmed:confirmed===true},key),
      saveTask:(data,key)=>command('saveTask',data,key), toggleTask:key=>command('toggleTask',{},key),
      saveEvent:(data,key)=>command('saveEvent',data,key), addNote:data=>command('addNote',data),
      addMaterial:data=>command('addMaterial',data), pinMaterial:(applicationId,materialId)=>command('pinMaterial',{applicationId,materialId}),
      saveProfile:data=>command('saveProfile',data,cache.profile.id), saveEntry:(data,key)=>command('saveEntry',data,key),
      saveSearches:items=>command('saveSearches',{items}),
      async archive(table,key,confirmed,restore=false) {
        const row=find(table==='profile_entries'?'entries':table,key);
        const result=await request('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:restore?'unarchive':'archive',data:{table,confirmed},key,version:row.rowVersion,revision:cache.revision})}); cache=result.state;
      },
      remove(table,key,confirmed) { return this.archive(table,key,confirmed); },
      async upload(data,file) {
        const form=new FormData(); form.append('data',JSON.stringify(data)); form.append('revision',String(cache.revision)); form.append('file',file);
        const result=await request('/api/materials/upload',{method:'POST',body:form}); cache=result.state;
      },
      previewImport:(kind,file)=>request(`/api/import/preview?kind=${encodeURIComponent(kind)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file}),
      previewBackup:name=>request('/api/backups/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})}),
      async commitImport(plan) { const result=await request('/api/import/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:plan.token,revision:plan.revision,confirmed:true})}); cache=result.state; },
      backups:()=>request('/api/backups'), createBackup:()=>request('/api/backups/create',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),
      search(query) {
        const q=fold(query), results=[];
        const add=(kind,key,title,detail,content,screen)=>{ if (fold(`${title} ${detail} ${content}`).includes(q)) results.push({kind,key,title,detail,screen}); };
        if (!q) return results;
        cache.offers.filter(item=>!item.archived).forEach(item=>add('Oferta',item.id,item.title,company(item).name,`${item.location} ${item.direction} ${item.description} ${item.mode} ${item.contract}`,'offer'));
        cache.applications.filter(item=>!item.archived).forEach(item=>add('Aplikacja',item.id,offer(item).title,`${company(offer(item)).name} · ${item.status}`,'','detail'));
        cache.tasks.filter(item=>!item.archived).forEach(item=>add('Zadanie',item.id,item.title,applicationLabel(item.applicationId),item.due,'plan'));
        cache.events.filter(item=>!item.archived).forEach(item=>add('Termin',item.id,item.title,applicationLabel(item.applicationId),`${item.start} ${item.place}`,'plan'));
        cache.notes.filter(item=>!item.archived).forEach(item=>add('Notatka',item.applicationId,item.text,applicationLabel(item.applicationId),'','detail'));
        cache.materials.forEach(item=>add('Materiał',item.id,item.title,`wersja ${item.version} · ${item.kind}`,item.description,'materials'));
        return results;
      }
    };
  }
  window.CareerModel={createStore,STATUSES,DIRECTIONS,MODES,CONTRACTS,fold,today,dayOffset,warsawTime,ValidationError};
})();
