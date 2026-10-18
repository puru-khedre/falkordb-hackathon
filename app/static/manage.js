let DEFAULT_GRAPH = "contextanchor";
function esc(s){return String(s??"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2600);}
async function j(u,o){const r=await fetch(u,o);let d={};try{d=await r.json();}catch(e){}
  if(!r.ok){let m=d.detail;if(m&&typeof m==="object")m=m.message||JSON.stringify(m);throw new Error(m||r.status);}return d;}

async function loadProjects(){
  const d = await j("/api/projects?counts=true");
  DEFAULT_GRAPH = d.default || DEFAULT_GRAPH;
  const body = document.getElementById("projBody"); body.innerHTML="";
  d.projects.forEach(p=>{
    const c = p.counts||{};
    const isSample = p.kind==="sample";
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td><b>${esc(p.label)}</b><div class="muted mono" style="font-size:11px">${esc(p.graph)}</div></td>
      <td><span class="pill ${isSample?'sample':'repo'}">${isSample?'sample':'repo'}</span></td>
      <td class="counts">${c.functions||0} fns · ${c.files||0} files · ${c.rules||0} rules · ${c.developers||0} devs</td>
      <td class="mono muted" style="font-size:11px;max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(p.repo||"")}</td>
      <td><div class="acts">
        <button class="ghost" data-act="refresh" data-g="${esc(p.graph)}">Refresh</button>
        <button class="danger" data-act="delete" data-g="${esc(p.graph)}" ${isSample?'title="resets to empty; auto-reseeds"':''}>Delete</button>
      </div></td>`;
    body.appendChild(tr);
  });
  if(!d.projects.length) body.innerHTML=`<tr><td colspan="5" class="empty">No projects. Ingest one above.</td></tr>`;
  // rule project selector
  const sel=document.getElementById("ruleProj");const cur=sel.value;sel.innerHTML="";
  d.projects.forEach(p=>{const o=document.createElement("option");o.value=p.graph;o.textContent=p.label;sel.appendChild(o);});
  if([...sel.options].some(o=>o.value===cur))sel.value=cur;
}

async function loadRules(){
  const g=document.getElementById("ruleProj").value;
  const body=document.getElementById("ruleBody");body.innerHTML="";
  if(!g)return;
  const d=await j("/api/rules?project="+encodeURIComponent(g));
  (d.rules||[]).forEach(r=>{
    const tgt=(r.targets||[]).map(t=>t.name).join(", ")||"—";
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td class="mono">${esc(r.id)}</td>
      <td><span class="pill ${esc(r.severity)}">${esc(r.severity)}</span></td>
      <td>${esc(r.rule)}</td>
      <td class="muted">${esc(tgt)}</td>
      <td><div class="acts">
        <button class="ghost" data-ract="edit" data-id="${esc(r.id)}" data-text="${esc(r.rule)}" data-sev="${esc(r.severity)}">Edit</button>
        <button class="danger" data-ract="del" data-id="${esc(r.id)}">Delete</button>
      </div></td>`;
    body.appendChild(tr);
  });
  if(!(d.rules||[]).length) body.innerHTML=`<tr><td colspan="5" class="empty">No rules for this project yet.</td></tr>`;
}

document.getElementById("ingestBtn").onclick=async()=>{
  const src=document.getElementById("src").value.trim();if(!src)return;
  const b=document.getElementById("ingestBtn");b.textContent="…";b.disabled=true;
  try{const d=await j("/api/ingest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:src})});
    const s=d.ingested;toast(`Ingested ${s.project}: ${s.functions} fns, ${(s.languages||[]).join("/")}`);
    document.getElementById("src").value="";await loadProjects();
  }catch(e){toast("Ingest failed: "+e.message);}finally{b.textContent="Ingest";b.disabled=false;}
};

document.getElementById("projBody").onclick=async(e)=>{
  const btn=e.target.closest("button");if(!btn)return;
  const g=btn.dataset.g,act=btn.dataset.act;
  if(act==="refresh"){btn.textContent="…";btn.disabled=true;
    try{await j("/api/project/refresh",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({graph:g})});toast("Refreshed "+g);await loadProjects();await loadRules();}
    catch(err){toast("Refresh failed: "+err.message);}finally{btn.textContent="Refresh";btn.disabled=false;}
  } else if(act==="delete"){
    if(!confirm("Delete project '"+g+"'? This removes its graph.")) return;
    try{await j("/api/project/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({graph:g})});toast("Deleted "+g);await loadProjects();await loadRules();}
    catch(err){toast("Delete failed: "+err.message);}
  }
};

document.getElementById("ruleBody").onclick=async(e)=>{
  const btn=e.target.closest("button");if(!btn)return;
  const id=btn.dataset.id,act=btn.dataset.ract;
  const proj=document.getElementById("ruleProj").value;
  if(act==="edit"){
    document.getElementById("rId").value=id;
    document.getElementById("rText").value=btn.dataset.text;
    document.getElementById("rSev").value=btn.dataset.sev;
    document.getElementById("rText").focus();
  } else if(act==="del"){
    if(!confirm("Delete rule "+id+"?")) return;
    try{await j("/api/rule/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,project:proj})});toast("Deleted "+id);await loadRules();await loadProjects();}
    catch(err){toast("Delete failed: "+err.message);}
  }
};

document.getElementById("saveRule").onclick=async()=>{
  const proj=document.getElementById("ruleProj").value;
  const text=document.getElementById("rText").value.trim();if(!text)return toast("Enter rule text");
  let id=document.getElementById("rId").value.trim()||("RULE-"+Math.random().toString(36).slice(2,6).toUpperCase());
  const sev=document.getElementById("rSev").value, fn=document.getElementById("rFn").value.trim();
  try{await j("/api/rule",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,text,severity:sev,target_fn:fn,project:proj})});
    toast("Saved "+id);document.getElementById("rId").value="";document.getElementById("rText").value="";document.getElementById("rFn").value="";
    await loadRules();await loadProjects();
  }catch(e){toast("Save failed: "+e.message);}
};

document.getElementById("ruleProj").onchange=loadRules;
document.getElementById("refreshRules").onclick=loadRules;


async function loadSettings(){
  try{const d=await j("/api/settings");
    document.getElementById("ghStatus").textContent=d.github.connected?("\u2713 connected "+d.github.token_masked):"not connected";
    document.getElementById("llmStatus").textContent=d.llm.key_set?("\u2713 LLM on "+d.llm.key_masked):"LLM off";
    document.getElementById("llmBase").value=d.llm.base_url||"";
    document.getElementById("llmModel").value=d.llm.model||"";
  }catch(e){}
}
document.getElementById("saveSettings").onclick=async()=>{
  const payload={
    github_token:document.getElementById("ghToken").value.trim(),
    nvidia_api_key:document.getElementById("llmKey").value.trim(),
    nvidia_base_url:document.getElementById("llmBase").value.trim(),
    nvidia_model:document.getElementById("llmModel").value.trim()};
  try{await j("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    toast("Settings saved");document.getElementById("ghToken").value="";document.getElementById("llmKey").value="";await loadSettings();
  }catch(e){toast("Save failed: "+e.message);}
};

(async function(){await loadSettings();await loadProjects();await loadRules();})();
