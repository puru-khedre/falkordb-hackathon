const NTYPE_COLOR={File:"#5b6b84",Function:"#38bdf8",Endpoint:"#a78bfa",Developer:"#2fe08a",TeamRule:"#ffb224",ADR:"#6aa5ff"};
const GLOW={red:"#ff3b5c",amber:"#ffb224",green:"#2fe08a",blue:"#6aa5ff"};
let cy,pulseTimer=null,currentProject="contextanchor";
const DEFAULT_GRAPH="contextanchor";
if(window.cytoscapeDagre){try{cytoscape.use(window.cytoscapeDagre);}catch(e){}}

function baseStyle(){return[
  {selector:"node",style:{"background-color":n=>NTYPE_COLOR[n.data("ntype")]||"#889","label":"data(label)","color":"#e6edf3","font-size":10,"font-family":"JetBrains Mono, monospace","text-valign":"bottom","text-margin-y":5,"width":22,"height":22,"border-width":2,"border-color":"#1e2836","text-background-color":"#0a0e14","text-background-opacity":0.82,"text-background-padding":3,"text-background-shape":"roundrectangle","text-max-width":"130px","text-wrap":"ellipsis","min-zoomed-font-size":7,"transition-property":"opacity border-color border-width overlay-opacity","transition-duration":"0.2s"}},
  {selector:"node[ntype='Endpoint']",style:{"shape":"round-diamond","width":24,"height":24}},
  {selector:"node[ntype='File']",style:{"shape":"round-rectangle","width":30,"height":20}},
  {selector:"node[ntype='TeamRule']",style:{"shape":"round-tag"}},
  {selector:"node[ntype='ADR']",style:{"shape":"round-pentagon"}},
  {selector:"node[ntype='Developer']",style:{"shape":"ellipse"}},
  {selector:"edge",style:{"width":1.6,"line-color":"#334155","target-arrow-color":"#334155","target-arrow-shape":"triangle","curve-style":"bezier","label":"data(label)","font-size":9,"color":"#64748b","text-rotation":"autorotate","text-outline-width":2,"text-outline-color":"#0a0e14","arrow-scale":0.9,"opacity":0.8}},
  {selector:".dim",style:{"opacity":0.3}},
  {selector:".edim",style:{"opacity":0.18}},
  {selector:".hl",style:{"border-width":3,"overlay-opacity":0.2,"overlay-padding":6,"width":26,"height":26,"font-size":11,"z-index":99}},
  {selector:".hl-red",style:{"border-color":GLOW.red,"overlay-color":GLOW.red}},
  {selector:".hl-amber",style:{"border-color":GLOW.amber,"overlay-color":GLOW.amber}},
  {selector:".hl-green",style:{"border-color":GLOW.green,"overlay-color":GLOW.green}},
  {selector:".hl-blue",style:{"border-color":GLOW.blue,"overlay-color":GLOW.blue}},
  {selector:".epath",style:{"line-color":GLOW.red,"target-arrow-color":GLOW.red,"width":3,"opacity":1}}
];}

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let touring=false;
function tourCap(html){const c=document.getElementById("tourCap");if(html===null){c.classList.add("hidden");return;}c.innerHTML=html;c.classList.remove("hidden");}
async function runTour(){
  if(touring){touring=false;return;}
  touring=true; const btn=document.getElementById("tourBtn"); btn.textContent="■ Stop tour";
  if(currentProject!==DEFAULT_GRAPH){document.getElementById("projectSel").value=DEFAULT_GRAPH;currentProject=DEFAULT_GRAPH;document.getElementById("demoPanel").style.display="block";await loadFns(DEFAULT_GRAPH);}
  const steps=[["1","<b>Scenario 1</b> — Refactoring <b>calculate_discount()</b> → <b>BLOCK</b>: 3 upstream callers and 2 live APIs break, and it hits RULE-4 (max 50% discount)."],["2","<b>Scenario 2</b> — Minting a raw token in <b>issue_token()</b> → <b>BLOCK</b>: violates the OAuth2 architecture rule (RULE-2)."],["3","<b>Scenario 3</b> — Ownership audit of <b>login()</b>: owner from real git history + the ADR behind it."]];
  try{ for(const [sid,cap] of steps){ if(!touring)break; tourCap(cap); await runAnalysis(fetchJson("/api/scenario/"+sid)); await sleep(4200); } }
  finally{ tourCap(null); btn.textContent="▶ Guided demo tour"; touring=false; }
}
async function fetchJson(u,o){const r=await fetch(u,o);const j=await r.json();
  if(!r.ok){let m=j.detail;if(m&&typeof m==="object")m=(m.message||"error")+": "+((m.candidates||[]).map(c=>c.fid).join(" | "));throw new Error(m||r.status);}
  return j;}
function showEmpty(on){document.getElementById("emptyState").classList.toggle("hidden",!on);}
function escAttr(s){return esc(s).replace(/"/g,"&quot;");}
async function renderOverview(){
  try{
    const o=await(await fetch("/api/overview?project="+encodeURIComponent(currentProject))).json();
    const c=o.counts||{};
    const chips=(o.chokepoints||[]).map(k=>`<button class="ovchip" data-fid="${escAttr(k.fid)}">${esc(k.function)}() <span class="muted">${esc(k.score)}</span></button>`).join("");
    document.getElementById("overviewCard").innerHTML=`
      <h3>${esc(o.label||currentProject)}</h3>
      <div class="ovstats">
        <span><b>${c.functions||0}</b> functions</span>
        <span><b>${c.files||0}</b> files</span>
        <span><b>${c.rules||0}</b> rules</span>
        <span><b>${c.developers||0}</b> devs</span>
      </div>
      <p class="muted" style="margin-top:16px">Riskiest chokepoints  click to inspect impact:</p>
      <div class="ovchips">${chips||'<span class="muted">No functions yet  ingest a repo.</span>'}</div>
      <p class="muted" style="font-size:12px;margin-top:16px">\u2026 or pick any function on the left, or try a sample scenario.</p>`;
  }catch(e){}
}

function renderViz(viz){
  showEmpty(false);
  if(cy)cy.destroy();
  cy=cytoscape({container:document.getElementById("cy"),
    elements:{nodes:viz.nodes,edges:viz.edges},style:baseStyle(),
    minZoom:0.25,maxZoom:1.5,wheelSensitivity:0.25});
  const useDagre=!!window.cytoscapeDagre;
  const opts=useDagre
    ?{name:"dagre",rankDir:"TB",nodeSep:42,rankSep:80,edgeSep:14,padding:40}
    :{name:"breadthfirst",directed:true,spacingFactor:1.4,padding:40};
  cy.layout(opts).run();
  cy.fit(cy.elements(),55);
}

function pulse(nodes){if(pulseTimer)clearInterval(pulseTimer);let up=true;
  pulseTimer=setInterval(()=>{nodes.animate({style:{"overlay-opacity":up?0.42:0.12}},{duration:640});up=!up;},660);}

function applyHighlights(h){
  if(!cy)return;
  if(pulseTimer){clearInterval(pulseTimer);pulseTimer=null;}
  cy.nodes().addClass("dim");cy.edges().addClass("edim");
  let hot=cy.collection();
  [["red","hl-red"],["amber","hl-amber"],["green","hl-green"],["blue","hl-blue"]].forEach(([k,cls])=>{
    (h[k]||[]).forEach(id=>{const n=cy.getElementById(id);if(n.nonempty()){n.removeClass("dim").addClass("hl "+cls);hot=hot.union(n);}});
  });
  const reds=(h.red||[]).map(id=>cy.getElementById(id)).filter(n=>n.nonempty());
  const rc=cy.collection(reds);
  rc.connectedEdges().forEach(e=>{if(rc.contains(e.source())&&rc.contains(e.target()))e.removeClass("edim").addClass("epath");});
  hot.connectedEdges().removeClass("edim");
  if(hot.nonempty())pulse(rc.nonempty()?rc:hot);
}

function showBanner(v){const b=document.getElementById("banner");
  const m={BLOCK:["block"," BLOCK  high-impact change"],REVIEW:["review"," REVIEW  needs sign-off"],SAFE:["safe"," SAFE to change"]};
  const[c,t]=m[v]||["",v];b.className="banner "+c;b.textContent=t;b.classList.remove("hidden");}

function esc(s){return String(s??"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

function renderReport(r){
  document.getElementById("reportEmptyPanel").classList.add("hidden");
  const el=document.getElementById("reportBody");el.classList.remove("hidden");
  const v=r.verdict.toLowerCase();
  const scn=r.scenario?`<div class="subtitle">${esc(r.scenario.prompt)}</div>`:"";
  const aff=r.blast_radius.affected_functions,apis=r.blast_radius.impacted_apis,own=r.ownership||{};
  let affHtml=aff.length?aff.map(a=>`<div class="item"><span class="mono">${esc(a.function)}()</span><span class="hops">${a.hops} hop${a.hops>1?"s":""}</span><div class="muted">${esc(a.file)}</div></div>`).join(""):`<div class="item muted">No upstream callers  leaf function.</div>`;
  let apiHtml=apis.length?apis.map(a=>`<div class="item"><span class="mono">${esc(a.method)} ${esc(a.route)}</span></div>`).join(""):`<div class="item muted">No API endpoint reaches this.</div>`;
  let ruleHtml=r.team_rules.length?r.team_rules.map(x=>`<div class="item rule"><b>${esc(x.id)}</b><span class="chip ${esc(x.severity)}">${esc(x.severity)}</span><div style="margin-top:4px">${esc(x.rule)}</div><div class="muted" style="font-size:11px;margin-top:3px">recorded ${esc(x.created_at)}</div></div>`).join(""):`<div class="item muted">No team rule governs this function.</div>`;
  let ownHtml="";
  if(own.author){const a=own.author;ownHtml+=`<div class="item owner"><b>${esc(a.name)}</b> <span class="muted">${esc(a.role||"")}</span><div class="muted" style="font-size:12px;margin-top:3px">${esc(a.commits)} commits · last ${esc(a.last_touched||"?")} · ${esc(a.email||"")}</div></div>`;}
  if(own.adr){const d=own.adr;ownHtml+=`<div class="item adr"><b>${esc(d.id)}</b>  ${esc(d.title)}<div class="muted" style="margin-top:4px">${esc(d.decision)}</div></div>`;}
  if(!ownHtml)ownHtml=`<div class="item muted">No owner / ADR on record.</div>`;
  const choke=r.chokepoint?`<div class="item"><span class="mono">${esc(r.chokepoint.function)}()</span> <span class="hops">score ${esc(r.chokepoint.score)}</span><div class="muted" style="font-size:11px">${esc(r.chokepoint.method)}</div></div>`:"";
  el.innerHTML=`
    <div class="verdict ${v}">${r.verdict}</div>
    <div style="font-family:JetBrains Mono,monospace;font-size:14px;margin:4px 0 2px">${esc(r.function)}()</div>
    ${r.doc?`<div class="muted" style="font-size:12px;margin:2px 0 4px">${esc(r.doc)}</div>`:""}
    <div class="muted" style="font-size:11px;font-family:JetBrains Mono,monospace">project: ${esc(r.project||currentProject)}</div>
    ${scn}
    <div class="sect"><h4>AI impact review <span class="srcpill">${esc(r.narration.source)}</span></h4><div class="narr">${esc(r.narration.text)}</div></div>
    <div class="sect"><h4> Blast radius · ${aff.length} affected</h4>${affHtml}</div>
    <div class="sect"><h4> Impacted live APIs</h4>${apiHtml}</div>
    <div class="sect"><h4> Team rules</h4>${ruleHtml}</div>
    <div class="sect"><h4> Ownership &amp; architecture</h4>${ownHtml}</div>
    <div class="sect"><h4> Global chokepoint (betweenness)</h4>${choke}</div>`;
}

async function runAnalysis(promise){
  try{const r=await promise;
    if(r.viz&&r.viz.nodes&&r.viz.nodes.length)renderViz(r.viz);
    applyHighlights(r.highlights);showBanner(r.verdict);renderReport(r);
  }catch(e){alert("Request failed: "+e.message);}
}

async function loadProjects(){
  const j=await(await fetch("/api/projects")).json();
  const sel=document.getElementById("projectSel");sel.innerHTML="";
  j.projects.forEach(p=>{const o=document.createElement("option");o.value=p.graph;o.textContent=p.label+(p.kind==="sample"?"  (demo)":"");sel.appendChild(o);});
  if(![...sel.options].some(o=>o.value===currentProject))currentProject=j.active||DEFAULT_GRAPH;
  sel.value=currentProject;
  document.getElementById("demoPanel").style.display = currentProject===DEFAULT_GRAPH?"block":"none";
}

async function loadFns(project){
  try{const j=await(await fetch("/api/functions?project="+encodeURIComponent(project))).json();
    const sel=document.getElementById("fnInput");
    sel.innerHTML='<option value="">Select a function…</option>';
    j.functions.forEach(f=>{const o=document.createElement("option");o.value=f.fid||f.name;o.textContent=f.name+"  ·  "+f.file;sel.appendChild(o);});
  }catch(e){}
}

function resetView(){if(cy){cy.destroy();cy=null;}document.getElementById("banner").classList.add("hidden");showEmpty(true);renderOverview();}

function wire(){
  document.getElementById("tourBtn").onclick=runTour;
  document.getElementById("overviewCard").addEventListener("click",e=>{
    const back=e.target.closest(".ovback");if(back){renderOverview();return;}
    const b=e.target.closest(".ovchip");if(!b||!b.dataset.fid)return;
    runAnalysis(fetchJson("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({function:b.dataset.fid,project:currentProject})}));
  });
  document.getElementById("projectSel").onchange=async e=>{
    currentProject=e.target.value;document.getElementById("demoPanel").style.display=currentProject===DEFAULT_GRAPH?"block":"none";
    await loadFns(currentProject);resetView();
  };
  document.getElementById("analyzeBtn").onclick=()=>{
    const fn=document.getElementById("fnInput").value.trim();
    if(fn)runAnalysis(fetchJson("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({function:fn,project:currentProject})}));
  };
  document.getElementById("fnInput").addEventListener("keydown",e=>{if(e.key==="Enter")document.getElementById("analyzeBtn").click();});

  document.getElementById("askBtn").onclick=async()=>{
    const q=document.getElementById("askInput").value.trim();if(!q)return;
    if(cy){cy.destroy();cy=null;}
    document.getElementById("banner").classList.add("hidden");showEmpty(true);
    const card=document.getElementById("overviewCard");
    card.innerHTML=`<h3>Ask</h3><p class="muted">${esc(q)}</p><div class="narr" style="text-align:left;margin-top:12px">… thinking</div>`;
    try{const r=await fetchJson("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q,project:currentProject})});
      card.innerHTML=`<h3>Ask <span class="srcpill">${esc(r.source)}</span></h3><p class="muted">${esc(q)}</p><div class="narr" style="text-align:left;margin-top:12px">${esc(r.answer)}</div><div style="margin-top:14px"><button class="ovchip ovback">← Project overview</button></div>`;
    }catch(e){card.innerHTML=`<div class="item muted">Ask failed: ${esc(e.message)}</div><div style="margin-top:12px"><button class="ovchip ovback">← Back</button></div>`;}
  };
  document.getElementById("askInput").addEventListener("keydown",e=>{if(e.key==="Enter")document.getElementById("askBtn").click();});
  document.querySelectorAll(".chip-btn[data-sid]").forEach(b=>{b.onclick=()=>{
    if(currentProject!==DEFAULT_GRAPH){document.getElementById("projectSel").value=DEFAULT_GRAPH;currentProject=DEFAULT_GRAPH;document.getElementById("demoPanel").style.display="block";loadFns(DEFAULT_GRAPH);}
    runAnalysis(fetchJson("/api/scenario/"+b.dataset.sid));};});
  document.getElementById("ingestBtn").onclick=async()=>{
    const src=document.getElementById("sourceInput").value.trim();if(!src)return;
    const btn=document.getElementById("ingestBtn");btn.textContent="";btn.disabled=true;
    try{const j=await fetchJson("/api/ingest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:src})});
      const s=j.ingested;currentProject=s.graph;await loadProjects();await loadFns(s.graph);resetView();
      alert(`Ingested "${s.project}": ${s.functions} functions, ${s.calls} calls, ${s.endpoints} endpoints, ${s.developers} git authors.\nNow type a function name on the left to check its impact.`);
    }catch(e){alert("Ingest failed: "+e.message);}finally{btn.textContent="Ingest";btn.disabled=false;}
  };
  document.getElementById("reseedBtn").onclick=async()=>{await fetchJson("/api/reseed",{method:"POST"});currentProject=DEFAULT_GRAPH;await loadProjects();await loadFns(DEFAULT_GRAPH);resetView();};
  document.getElementById("exportBtn").onclick=()=>window.open("/api/export/rules?format=claude&project="+encodeURIComponent(currentProject),"_blank");
  document.getElementById("ruleBtn").onclick=async()=>{
    const text=document.getElementById("ruleText").value.trim();if(!text)return;
    const fn=document.getElementById("ruleFn").value.trim(),sev=document.getElementById("ruleSev").value;
    const id="RULE-"+Math.random().toString(36).slice(2,6).toUpperCase();
    try{await fetchJson("/api/rule",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,text,severity:sev,target_fn:fn,project:currentProject})});
      document.getElementById("ruleText").value="";document.getElementById("ruleFn").value="";alert("Saved "+id+" to the graph.");
    }catch(e){alert("Could not save rule: "+e.message);}
  };
}

async function health(){const el=document.getElementById("health");
  try{const h=await(await fetch("/api/health")).json();el.className="health ok";
    el.textContent="FalkorDB live · LLM "+(h.llm?"on":"off")+" · GH "+(h.github?"on":"off")+" · "+h.projects+" proj";
  }catch(e){el.className="health down";el.textContent="FalkorDB unreachable";}}

(async function(){await loadProjects();await loadFns(currentProject);wire();health();showEmpty(true);renderOverview();})();
