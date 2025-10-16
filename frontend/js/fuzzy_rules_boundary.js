// ReklaMap Boundary Dispute Fuzzy Recommender (frontend-only)
// Builds on the same structure as fuzzy_rules_lot.js but tuned for boundary disputes
(function(){
  // --- Utils ---
  function $(sel, root=document){ return root.querySelector(sel); }
  function $all(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }
  function text(el){ return (el?.textContent || '').trim(); }
  function normalize(str){ return (str || '').toLowerCase().trim(); }

  // --- Detection & Extraction ---
  function findFieldBlock(labelIncludes){
    // Try structured blocks first
    let blocks = $all('.complaint-form .field-block');
    if (!blocks.length) blocks = $all('.field-block');
    const l = (labelIncludes||'').toLowerCase();
    for (const b of blocks){
      const p = $('p', b) || $('label', b) || $('legend', b);
      if (!p) continue;
      if (text(p).toLowerCase().includes(l)) return b;
    }
    // Fallback: admin preview markup has no .field-block; find the <p> label and then its following group with inputs
    const candidates = $all('p, label, legend');
    for (const el of candidates){
      if (!el || !text(el)) continue;
      if (text(el).toLowerCase().includes(l)){
        // Prefer the immediate next sibling that contains inputs
        let sib = el.nextElementSibling;
        while (sib && !sib.querySelector('input')) sib = sib.nextElementSibling;
        if (sib && sib.querySelector('input')) return sib;
        // Otherwise the nearest parent section that contains inputs
        let scope = el.parentElement;
        while (scope && scope !== document && !scope.querySelector('input')) scope = scope.parentElement;
        if (scope && scope.querySelector('input')) return scope;
        return el.parentElement || el; // last resort
      }
    }
    return null;
  }

  function parseCheckedLabels(block){
    if (!block) return [];
    return $all('label input:checked', block).map(inp => text(inp.closest('label')).replace(/^[\s\S]*?\)\s*/, '').trim());
  }
  function parseSelectedRadioLabel(block){
    if (!block) return '';
    const inp = $('input[type="radio"]:checked', block) || $('input[type="radio"]', block);
    if (!inp) return '';
    return text(inp.closest('label'));
  }
  function parseTextValue(selector, root=document){
    const el = root.querySelector(selector);
    return el ? (el.value || el.textContent || '').trim() : '';
  }

  // --- Extract boundary signals ---
  function extractSignals(root=document){
    const signals = {
      nature_of_issue: [], duration: '', structure_status: '', notice: '', confronted: '',
      dispute_effects: [], reported_to: [], site_inspection: '', site_result: [],
      have_docs: '', ongoing_development: '',
      persons_involved_list: [], persons_reside: '', persons_claim_docs: '', persons_claim_docs_list: []
    };

    const q1 = findFieldBlock('nature of the boundary issue');
    const q2 = findFieldBlock('How long has this encroachment existed');
    const q3 = findFieldBlock('Has the encroaching structure already been built');
    const q4 = findFieldBlock('Were you given any prior notice');
    const q5 = findFieldBlock('Have you discussed or confronted');
    const q6 = findFieldBlock('Has the dispute led to any of the following');
    const q7 = findFieldBlock('Have you reported this boundary issue');
    const q8 = findFieldBlock('Was there any site inspection');
    const q9 = findFieldBlock('What was the result of the report or inspection');
    const q10 = findFieldBlock('Do you have any documents or proof');
    const q11 = findFieldBlock('Is there an ongoing development');

    signals.nature_of_issue = parseCheckedLabels(q1);
    signals.duration = parseSelectedRadioLabel(q2);
    signals.structure_status = parseSelectedRadioLabel(q3);
    signals.notice = parseSelectedRadioLabel(q4);
    signals.confronted = parseSelectedRadioLabel(q5);
    signals.dispute_effects = parseCheckedLabels(q6);
    signals.reported_to = parseCheckedLabels(q7);
    signals.site_inspection = parseSelectedRadioLabel(q8);
    signals.site_result = parseCheckedLabels(q9);
    signals.have_docs = parseSelectedRadioLabel(q10);
    signals.ongoing_development = parseSelectedRadioLabel(q11);

    // Persons involved parsing: accept any ".pair-row" (preview may omit containers)
    const rows = $all('#pairsContainer .pair-row, .pairs .pair-row, .pair-row');
    if (rows.length){
      function findInp(row, re){
        const ins = $all('input', row);
        for (const inp of ins){
          const ph = (inp.placeholder||'').toLowerCase();
          const nm = (inp.name||'').toLowerCase();
          const lb = inp.previousElementSibling && inp.previousElementSibling.tagName.toLowerCase()==='label' ? text(inp.previousElementSibling).toLowerCase() : '';
          if (re.test(ph) || re.test(nm) || re.test(lb)) return inp;
        }
        return null;
      }
      signals.persons_involved_list = rows.map(r => ({
        name: (findInp(r, /name|person/)? findInp(r, /name|person/).value : '').trim(),
        blk: (findInp(r, /block|blk/)? findInp(r, /block|blk/).value : '').trim(),
        lot: (findInp(r, /lot/)? findInp(r, /lot/).value : '').trim()
      })).filter(x=>x.name||x.blk||x.lot);

      const p_reside_block = findFieldBlock('Do they reside on the disputed lot') || findFieldBlock('Do they reside on or near the disputed boundary');
      const p_claim_block = findFieldBlock('Do they claim to have legal or assignment documents');
      signals.persons_reside = parseSelectedRadioLabel(p_reside_block);
      signals.persons_claim_docs = parseSelectedRadioLabel(p_claim_block);
      if (p_claim_block) signals.persons_claim_docs_list = parseCheckedLabels(p_claim_block);
    }
    return signals;
  }

  // --- Feature Construction ---
  function computeFeatures(s){
    const f = {
      doc_strength: 0, opposing_doc_claim: 0, physical_encroachment: 0,
      urgent_effects: 0, residency_conflict: 0, reported_strength: 0,
      site_action_taken: 0, family_dispute: 0, basis_weakness: 0, doc_conflict_strength: 0
    };

    const nature = (s.nature_of_issue||[]).map(x => normalize(x));
    const effects = (s.dispute_effects||[]).map(x => normalize(x));
    const reported = (s.reported_to||[]).map(x => normalize(x));
    const siteRes = (s.site_result||[]).map(x => normalize(x));
    const personsDocs = (s.persons_claim_docs_list||[]).map(x => normalize(x));
    const haveDocs = normalize(s.have_docs);
    const reside = normalize(s.persons_reside);

    // Documents
    if (haveDocs.includes('yes')) f.doc_strength = 1;
    if (personsDocs.includes('title') || personsDocs.includes('survey')) f.opposing_doc_claim = 0.8;
    if (f.doc_strength > 0 && f.opposing_doc_claim > 0) f.doc_conflict_strength = 0.6;

    // Encroachment indicators
    if (nature.some(n => n.includes('fence') || n.includes('wall') || n.includes('encroach') || n.includes('structure'))) f.physical_encroachment = 1;
    if (/ongoing|partial/.test(normalize(s.structure_status))) f.physical_encroachment = Math.max(0.8, f.physical_encroachment);
    if (/mohon|marker/.test(nature.join(' '))) f.physical_encroachment = Math.max(0.9, f.physical_encroachment);

    // Urgent effects
    if (effects.some(e => /threat|harass|physical|damage|altercation/.test(e))) f.urgent_effects = 1;

    // Residency
    if (reside === 'yes') f.residency_conflict = 1;
    else if (reside === 'not sure') f.residency_conflict = 0.5;

    // Reporting
    f.reported_strength = Math.min(1, reported.length * 0.25);

    // Site inspection action
    if (/yes/.test(normalize(s.site_inspection))){
      if (siteRes.some(r => /advised|adjust|vacate/.test(r))) f.site_action_taken = 0.8;
      if (siteRes.some(r => /still under|investigation/.test(r))) f.site_action_taken = Math.max(f.site_action_taken, 0.4);
      if (siteRes.some(r => /no action|no valid/.test(r))) f.site_action_taken = Math.max(f.site_action_taken, 0.1);
    }

    // Family dispute
    if (nature.some(n => n.includes('family'))) f.family_dispute = 0.8;

    // Weak basis → low docs, low reports
    const lowDocs = f.doc_strength < 0.2 ? 1 : 0;
    const lowReported = f.reported_strength < 0.2 ? 1 : 0;
    f.basis_weakness = Math.min(1, 0.6*lowDocs + 0.3*lowReported);

    Object.keys(f).forEach(k => f[k] = Math.max(0, Math.min(1, f[k])));
    return f;
  }

  // --- Fuzzy scoring ---
  function scoreActions(f, s){
    const sc = { Inspection: 0, Invitation: 0, Assessment: 0, 'Out of Jurisdiction': 0 };
    const q11 = normalize(s.ongoing_development);
    const q1 = (s.nature_of_issue||[]).map(normalize).join(' ');
    const q4 = normalize(s.notice);

    // S1 logic – government project ambiguity
    if (q11.includes('yes')){
      if (/neighbor|fence|wall/.test(q1) && /no/.test(q4)){
        sc['Out of Jurisdiction'] += 0.7;
        sc.Inspection += 0.4; sc.Assessment += 0.3; // verify if truly gov-related
      } else {
        sc['Out of Jurisdiction'] += 1.0;
      }
    }

    // Weak basis → Inspection instead of OOT
    if (f.basis_weakness >= 0.6 && f.doc_strength < 0.5){
      sc.Inspection += 0.8;
    }

    // Multi-block → Out of Jurisdiction
    const blkCount = (s.persons_involved_list||[]).filter(p => p.blk).length;
    if (blkCount > 3){ sc['Out of Jurisdiction'] += 0.8; }

    // S2–S3 logic: documents but no inspection yet
    if (s.have_docs && /yes/i.test(s.have_docs) && (!/yes/i.test(s.site_inspection))){
      sc.Inspection += 0.6;
    }

    // S5 urgent threats or harassment
    if (f.urgent_effects >= 0.8){
      sc.Invitation += 0.5; sc.Assessment += 0.4;
    }

    // S6 if USAD already inspected → move to Assessment
    const rep = (s.reported_to||[]).join(' ').toLowerCase();
    if (/usad|phaselad/.test(rep)){
      if (/yes/i.test(s.site_inspection)) sc.Assessment += 0.6;
      else sc.Inspection += 0.6;
    }

    // S7 mohon / marker moved
    if (/mohon|marker/.test(q1)) sc.Inspection += 0.5;

    // Removed structure → Invitation
    if (/removed/.test(normalize(s.structure_status))) sc.Invitation += 0.7;

    // Opposing docs + residency conflict → Assessment
    if (f.opposing_doc_claim >= 0.6 && f.residency_conflict >= 0.6){
      sc.Assessment += 0.5;
    }

    // Base fuzzy weightings
    sc.Inspection += 0.5*f.physical_encroachment + 0.4*f.residency_conflict + 0.3*f.urgent_effects + 0.2*f.reported_strength;
    sc.Invitation += 0.6*f.family_dispute + 0.25*(1 - f.doc_strength);
    sc.Assessment += 0.6*f.opposing_doc_claim + 0.35*f.site_action_taken + 0.2*f.doc_conflict_strength;
    sc['Out of Jurisdiction'] += 0.6*f.basis_weakness + 0.2*(1 - f.physical_encroachment);

    Object.keys(sc).forEach(k => sc[k] = Math.max(0, sc[k]||0));
    return sc;
  }

  function chooseRecommendation(scores){
    const arr = Object.entries(scores).sort((a,b)=>b[1]-a[1]);
    const [pKey, pVal] = arr[0]; const [sKey, sVal] = arr[1]||[];
    let primary = pKey;
    if (pKey === 'Out of Jurisdiction' && (pVal - (sVal||0)) < 0.15) primary = sKey;
    return { primaryAction: primary, secondaryAction: sKey||null, sorted: arr };
  }

  // --- UI helpers ---
  const ACTION_COLOR = { Inspection:'#1a33a0', Invitation:'#0b8b6a', Assessment:'#8751b8', 'Out of Jurisdiction':'#a03b2b' };
  function clamp01(x){ return Math.max(0, Math.min(1, x)); }
  function pct(x){ return Math.round(clamp01(x)*100); }

  function normalizeScores(raw){
    const total = Object.values(raw).reduce((a,b)=>a+b,0)+1e-9;
    const norm={}; Object.keys(raw).forEach(k=>norm[k]=raw[k]/total); return norm;
  }

  function buildBullets(f){
    const r=[];
    if (f.physical_encroachment>=0.6) r.push('Structure or fence encroachment detected — field inspection required.');
    if (f.residency_conflict>=0.6) r.push('Respondent resides near boundary — inspection can verify encroachment.');
    if (f.urgent_effects>=0.8) r.push('Threats /Altercation reported /Property damage — mediation (Invitation) needed.');
    if (f.opposing_doc_claim>=0.6) r.push('Both sides claim documents — assessment required to validate.');
    if (f.basis_weakness>=0.6) r.push('Weak evidence — inspection to verify facts before jurisdiction decision.');
    return r.length?r:['Signals mixed; further inspection recommended.'];
  }

  function renderScoreBars(scores, primary){
    const keys=['Inspection','Invitation','Assessment','Out of Jurisdiction'];
    return `<div style="margin-top:10px;">${keys.map(k=>{
      const p=Math.round(clamp01(scores[k])*100);
      const c=ACTION_COLOR[k]; const bold=k===primary;
      return `<div style="display:flex;align-items:center;gap:8px;margin:6px 0;">
        <div style="width:140px;font-weight:${bold?'700':'500'};color:${bold?c:'#1f2a4a'};">${k}</div>
        <div style="flex:1;background:#eef2ff;border-radius:999px;height:10px;overflow:hidden;">
          <div style="width:${p}%;height:100%;background:${c};opacity:${bold?1:0.6}"></div>
        </div>
        <div style="width:42px;text-align:right;color:${bold?c:'#51607a'};font-weight:${bold?700:500}">${p}%</div>
      </div>`;
    }).join('')}</div>`;
  }

  function buildNarrative(s, norm, p){
    const conf=pct(norm[p]); const label=conf>=75?'high':conf>=50?'moderate':'low';
    const f=computeFeatures(s); const bullets=buildBullets(f);
    return `Recommended action: ${p} (${conf}% ${label} confidence).\n\nReasoning:\n- ${bullets.join('\n- ')}\n\nConfidence may improve with more documents or inspection results.`;
  }

  function renderRecommendation(result){
    const modal=document.getElementById('recommendModal'); if(!modal)return;
    const container=modal.querySelector('.modal, .warning-modal')||modal;
    let box=container.querySelector('#autoRecommendation');
    if(!box){
      box=document.createElement('div'); box.id='autoRecommendation';
      box.style.cssText='border:1px solid rgba(26,51,160,0.18);border-radius:12px;padding:14px 16px;margin:10px 0 16px;background:#f7f9ff;color:#1f2a4a;font-size:14px;';
      container.insertBefore(box,container.firstChild);
    }
    try{
      const p=result.choice.primaryAction;
      const norm=normalizeScores(result.scores);
      const conf=pct(norm[p]);
      const color=ACTION_COLOR[p];
      const reasons=buildBullets(result.features).map(x=>`<li>${x}</li>`).join('');
      box.innerHTML=`
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:2px solid ${color};">
          <div style="font-weight:800;color:${color};display:flex;align-items:center;gap:10px;padding-bottom:4px;">
            <span class="material-icons" style="font-size:18px;color:${color};">psychology</span>System Recommendation
          </div>
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="padding:4px 10px;border-radius:999px;background:${color}10;color:${color};font-weight:700;">${p}</span>
            <span style="padding:4px 10px;border-radius:999px;background:${color}10;color:${color};font-weight:700;">${conf}%</span>
          </div>
        </div>
        ${renderScoreBars(norm,p)}
        <div style="margin-top:8px;color:#1f2a4a;">Reasoning</div>
        <ul style="margin:6px 0 0 18px;color:#00030dff">${reasons}</ul>`;
      const t=document.getElementById('recommendText')||modal.querySelector('textarea');
      if(t)t.value=buildNarrative(result.signals,norm,p);
      modal.dataset.suggestAssign=(p==='Inspection'||p==='Invitation')?p:(result.choice.secondaryAction||'');
      modal.dataset.suggestAction=(p==='Assessment'||p==='Out of Jurisdiction')?p:(result.choice.secondaryAction||'');
    }catch(e){ box.innerHTML='<div style="font-weight:700;color:#a03b2b;">Unable to render recommendation.</div>'; }
  }

  function computeRecommendationFromDom(){
    const signals=extractSignals();
    const features=computeFeatures(signals);
    const scores=scoreActions(features,signals);
    const choice=chooseRecommendation(scores);
    return {signals,features,scores,choice};
  }

  window.BoundaryFuzzy={
    extractSignals,computeFeatures,scoreActions,chooseRecommendation,
    computeRecommendation:(sig)=>{const s=sig||extractSignals();const f=computeFeatures(s);const sc=scoreActions(f,s);const ch=chooseRecommendation(sc);return{signals:s,features:f,scores:sc,choice:ch};},
    renderRecommendation
  };

  document.addEventListener('DOMContentLoaded',()=>{
    const modal=document.getElementById('recommendModal');
    if(!modal)return;
    const recompute=()=>{const r=computeRecommendationFromDom();if(r)renderRecommendation(r);};
    recompute();
    const obs=new MutationObserver(()=>{if(modal.style.display!=='none')recompute();});
    obs.observe(modal,{attributes:true,attributeFilter:['style','class']});
  });
})();
