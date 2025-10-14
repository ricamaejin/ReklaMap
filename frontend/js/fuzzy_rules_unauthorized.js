// ReklaMap Unauthorized Occupation Fuzzy Recommender (frontend-only)
// Mirrors Lot/Pathway structure and UI. No backend changes.
// Exposes: window.UnauthorizedFuzzy { extractSignals, computeFeatures, scoreActions, chooseRecommendation, computeRecommendation, renderRecommendation }

(function(){
  // --- Utils ---
  function $(sel, root=document){ return root.querySelector(sel); }
  function $all(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }
  function text(el){ return (el?.textContent || '').trim(); }
  function normalize(str){ return (str || '').toLowerCase().trim(); }
  function clamp01(x){ return Math.max(0, Math.min(1, x)); }

  // Helpers for reading inputs safely (works in previewed form or full page)
  function valRadio(name, root=document){
    const nodes = $all(`input[name="${name}"]`, root);
    const picked = nodes.find(n => n.checked);
    return picked ? picked.value : '';
  }
  function valsCheckbox(name, root=document){
    return $all(`input[name="${name}"]`, root).filter(n => n.checked).map(n => n.value);
  }
  function labelOfInput(input){
    if (!input) return '';
    const lab = input.closest('label') || (input.id ? document.querySelector(`label[for="${input.id}"]`) : null);
    return text(lab) || '';
  }

  // Q4 has one checkbox missing name/value ("Renting it out...") and we also need label text fallback.
  function getActivities(root=document){
    // Gather named checkboxes first
    const named = $all('input[type="checkbox"][name="activities"]', root)
      .filter(cb => cb.checked)
      .map(cb => cb.value);
    // Include any adjacent unlabeled checkbox that contains the word "Renting"
    const strayCbs = $all('input[type="checkbox"]', root)
      .filter(cb => !cb.name || cb.name !== 'activities')
      .filter(cb => cb.checked)
      .filter(cb => /renting/i.test(labelOfInput(cb)));
    if (strayCbs.length) named.push('renting');
    return named;
  }

  // Q7 has duplicate value for USAD presented as NGC; disambiguate by label text
  function getReportedTo(root=document){
    const cbs = $all('input[type="checkbox"][name="boundary_reported_to[]"]', root);
    const out = [];
    cbs.forEach(cb => {
      if (!cb.checked) return;
      const lbl = labelOfInput(cb).toLowerCase();
      if (/usad/.test(lbl)) out.push('USAD');
      else if (/ngc/.test(lbl)) out.push('NGC');
      else if (/barangay/.test(lbl)) out.push('Barangay');
      else if (/hoa/.test(lbl)) out.push('HOA');
      else if (/none/.test(lbl)) out.push('none');
      else if (cb.value) out.push(cb.value);
    });
    return out;
  }

  // --- Detection & Extraction ---
  function extractSignals(root=document){
    const s = {
      q1_legal_connection: valRadio('legal_connection', root),
      q4_activities: getActivities(root),
      q5_claim_type: valRadio('occupant_claim', root),
      q5_docs_list: valsCheckbox('occupant_documents[]', root),
      q6_approach: valRadio('approach', root),
      q6_approach_details: '', // derive from approach_details or approachNoDetails
      q7_reported_to: getReportedTo(root),
      q8_result: valRadio('result', root),
      description: (root.querySelector('textarea[name="description"]') || {}).value || ''
    };
    const adYes = valRadio('approach_details', root);
    const adNo = valRadio('approachNoDetails', root);
    s.q6_approach_details = adYes || adNo || '';
    return s;
  }

  // --- Features & Memberships ---
  function computeFeatures(s){
    const f = {
      doc_strength: 0,
      occupancy_intensity: 0,
      construction_activity: 0,
      claim_strength: 0,
      resistance_level: 0,
      engagement_attempted: 0,
      prior_reporting_strength: 0,
      action_progress: 0,
      legal_connection_weight: 0,
      jurisdiction_flag: 0,
      urgency: 0,
      basis_weakness: 0
    };

    // Q5 documents strength
    const docW = {
      'title': 1.0,
      'contract_to_sell': 0.7,
      'certificate_full_payment': 0.6,
      'qualification_stub': 0.4,
      'contract_agreement': 0.5,
      'deed_of_sale': 0.6
    };
    let ds = 0;
    (s.q5_docs_list||[]).forEach(k => { ds += (docW[normalize(k)] || 0); });
    const claimType = normalize(s.q5_claim_type);
    if (claimType === 'docs' && ds === 0) ds = 0.3; // claims docs but none selected
    if (claimType === 'verbal') ds = Math.max(ds, 0.3);
    if (claimType === 'unknown') ds = Math.max(ds, 0.15);
    if (claimType === 'none') ds = 0;
    f.doc_strength = clamp01(ds);

    // Q4 occupancy & construction
    const acts = (s.q4_activities||[]).map(a => normalize(a));
    const actW = { living: 0.4, built_structure: 0.35, fenced: 0.3, utilities: 0.25, storing: 0.15, renting: 0.35 };
    f.occupancy_intensity = clamp01(acts.reduce((acc,a)=>acc + (actW[a]||0), 0));
    f.construction_activity = Math.max(acts.includes('built_structure')?0.7:0, acts.includes('fenced')?0.6:0, acts.includes('utilities')?0.5:0);

    // Q5 + approach_details for claim strength
    let cl = f.doc_strength;
    if (/claim_owner/.test(s.q6_approach_details||'')) cl = Math.max(cl, 0.2 + f.doc_strength);
    if (claimType === 'verbal') cl = Math.max(cl, 0.3);
    f.claim_strength = clamp01(cl);

    // Q6 approach & resistance
    const ad = normalize(s.q6_approach_details);
    if (ad === 'hostile') f.resistance_level = 0.6;
    else if (ad === 'refused_leave') f.resistance_level = 0.5;
    else if (ad === 'claim_owner') f.resistance_level = 0.4;
    else if (ad === 'ignored') f.resistance_level = 0.3;
    else if (ad === 'no_docs') f.resistance_level = 0.15;
    else f.resistance_level = 0;
    f.engagement_attempted = normalize(s.q6_approach) === 'yes' ? 1 : 0;

    // Q7 reporting strength with hierarchy (NGC > USAD > Barangay/HOA)
    const rt = (s.q7_reported_to||[]).map(x=>normalize(x));
    let pr = 0;
    rt.forEach(x => {
      if (x === 'ngc') pr += 0.25;
      else if (x === 'usad') pr += 0.2;
      else if (x === 'barangay' || x === 'hoa') pr += 0.15;
      else if (x === 'none') pr += 0;
    });
    f.prior_reporting_strength = Math.min(0.6, pr);

    // Q8 action progress
    const res = normalize(s.q8_result);
    if (res === 'asked_to_leave') f.action_progress = 0.6;
    else if (res === 'provide_docs') f.action_progress = 0.5;
    else if (res === 'investigation') f.action_progress = 0.4;
    else if (res === 'pending') f.action_progress = 0.3;
    else if (res === 'no_action') f.action_progress = 0.2;
    else if (res === 'no_valid_claim') f.action_progress = 0.15;
    else if (res === 'not_applicable') f.action_progress = 0.1;
    else f.action_progress = 0;

    // Q1 legal connection weighing
    const lc = normalize(s.q1_legal_connection);
    if (lc === 'beneficiary') f.legal_connection_weight = 0.6;
    else if (lc === 'heir') f.legal_connection_weight = 0.55;
    else if (lc === 'purchaser') f.legal_connection_weight = 0.5;
    else if (lc === 'hoa_officer') f.legal_connection_weight = 0.4;
    else if (lc === 'lessee' || lc === 'representative') f.legal_connection_weight = 0.35;
    else f.legal_connection_weight = 0.3;

    // Jurisdiction heuristic
    const lowActs = f.occupancy_intensity < 0.25;
    const noReport = f.prior_reporting_strength === 0;
    if ((lc === 'representative' || lc === 'lessee') && f.doc_strength < 0.2 && noReport && lowActs) {
      f.jurisdiction_flag = 1;
    }

    // Urgency: keep inspection high even if investigation is ongoing
    const invOrPending = (res === 'investigation' || res === 'pending' || res === 'no_action') ? 1 : 0;
    f.urgency = clamp01(0.5*f.occupancy_intensity + 0.3*f.resistance_level + 0.2*invOrPending);

    // Basis weakness
    const claimWeak = (claimType === 'none' || claimType === 'unknown') ? 1 : 0;
    const approachNo = normalize(s.q6_approach) === 'no' ? 1 : 0;
    const approachWeakReason = /(not_residing|dont_know)/.test(s.q6_approach_details||'') ? 1 : 0;
    const resWeak = (res === 'not_applicable' || res === 'no_valid_claim') ? 1 : 0;
    f.basis_weakness = clamp01(0.35*(f.doc_strength < 0.2 ? 1 : 0) + 0.25*(f.prior_reporting_strength < 0.2 ? 1 : 0) + 0.2*claimWeak + 0.1*approachNo + 0.1*approachWeakReason + 0.15*resWeak);

    return f;
  }

  // --- Scoring & Choice ---
  function scoreActions(f){
    const scores = { Inspection: 0, Invitation: 0, Assessment: 0, 'Out of Jurisdiction': 0 };

    // Inspection: urgency + construction + resistance + limited prior action
    scores.Inspection = 0.45*f.urgency + 0.25*f.construction_activity + 0.2*f.resistance_level + 0.15*(f.prior_reporting_strength < 0.2 ? 1 : 0) + 0.15*((f.action_progress>=0.2 && f.action_progress<=0.4)?1:0) + 0.1*f.legal_connection_weight;

    // Invitation: claim + resistance + prior reporting + asked_to_leave + engagement
    const askedToLeave = normalize ? (normalize((f._res_key||'')) === 'asked_to_leave') : false; // placeholder (not used)
    scores.Invitation = 0.4*f.claim_strength + 0.35*f.resistance_level + 0.25*(f.prior_reporting_strength > 0.2 ? 1 : 0) + 0.2*(f.action_progress >= 0.6 ? 1 : 0) + 0.15*(f.engagement_attempted ? 1 : 0);

    // Assessment: documents + claim + prior reporting + provide_docs + legal connection + mid weakness
    scores.Assessment = 0.5*f.doc_strength + 0.3*f.claim_strength + 0.25*f.prior_reporting_strength + 0.2*(f.action_progress >= 0.5 && f.action_progress < 0.6 ? 1 : 0) + 0.2*f.legal_connection_weight + 0.15*((f.basis_weakness>0.3 && f.basis_weakness<0.6)?1:0);

    // Out of Jurisdiction: weak basis + no docs + no reporting + heuristic flag
    scores['Out of Jurisdiction'] = 0.5*f.basis_weakness + 0.25*(f.doc_strength < 0.2 ? 1 : 0) + 0.2*(f.prior_reporting_strength === 0 ? 1 : 0) + 0.15*(f.jurisdiction_flag ? 1 : 0);

    return scores;
  }

  function chooseRecommendation(scores){
    const entries = Object.entries(scores).sort((a,b)=>b[1]-a[1]);
    const [primary, secondary] = entries;
    let primaryAction = primary ? primary[0] : 'Assessment';
    // Avoid over-eager Out of Jurisdiction if margin is tiny
    if (primaryAction === 'Out of Jurisdiction'){
      const margin = (primary ? primary[1] : 0) - (secondary ? secondary[1] : 0);
      if (margin < 0.1 && secondary){ primaryAction = secondary[0]; }
    }
    return { primaryAction, secondaryAction: secondary ? secondary[0] : null, sorted: entries };
  }

  // --- UI helpers (mirroring Lot/Pathway) ---
  const ACTION_LABEL = { Inspection: 'Inspection', Invitation: 'Invitation', Assessment: 'Assessment', 'Out of Jurisdiction': 'Out of Jurisdiction' };
  const ACTION_COLOR = { Inspection: '#1a33a0', Invitation: '#0b8b6a', Assessment: '#8751b8', 'Out of Jurisdiction': '#a03b2b' };
  function pct(x){ return Math.round(clamp01(x)*100); }

  function normalizeScores(raw){
    const total = Object.values(raw).reduce((a,b)=>a+b, 0) + 1e-6;
    const norm = {}; Object.keys(raw).forEach(k => norm[k] = raw[k]/total); return norm;
  }

  function buildBullets(f){
    const bullets = [];
    if (f.occupancy_intensity >= 0.6) bullets.push('Strong on-site presence (living/structure/fenced/utilities).');
    if (f.construction_activity >= 0.5) bullets.push('Construction or enclosure detected (structure/fence/utilities).');
    if (f.resistance_level >= 0.5) bullets.push('Occupant shows resistance (hostile/refused to leave).');
    if (f.doc_strength >= 0.6) bullets.push('Respondent claims strong documents (e.g., Title/Contract).');
    if (f.prior_reporting_strength >= 0.4) bullets.push('Matter already raised to authorities (e.g., NGC/USAD/Barangay/HOA).');
    if (f.action_progress >= 0.6) bullets.push('Authority already asked occupant to leave — proceed to mediation.');
    if (f.basis_weakness >= 0.6) bullets.push('Basis appears weak (low docs/reporting and uncertain claims).');
    if (!bullets.length) bullets.push('Signals are mixed; applying best-effort fuzzy match.');
    return bullets;
  }

  function renderScoreBars(scores, primary){
    const keys = ['Inspection','Invitation','Assessment','Out of Jurisdiction'];
    const rows = keys.map(k => {
      const p = Math.round(clamp01(scores[k]||0)*100);
      const color = ACTION_COLOR[k] || '#1f2a4a';
      const isBest = k === primary;
      return `
        <div style="display:flex; align-items:center; gap:8px; margin:6px 0;">
          <div style="width:140px; font-weight:${isBest?'700':'500'}; color:${isBest?color:'#1f2a4a'};">${ACTION_LABEL[k]||k}</div>
          <div style="flex:1; background:#eef2ff; border-radius:999px; height:10px; overflow:hidden;">
            <div style="width:${p}%; height:100%; background:${color}; opacity:${isBest?1:0.6}"></div>
          </div>
          <div style="width:42px; text-align:right; color:${isBest?color:'#51607a'}; font-weight:${isBest?700:500}">${p}%</div>
        </div>`;
    }).join('');
    return `<div style="margin-top:10px;">${rows}</div>`;
  }

  function renderRecommendation(result){
    const modal = document.getElementById('recommendModal');
    if(!modal) return;
    const container = modal.querySelector('.modal, .warning-modal') || modal;
    let box = container.querySelector('#autoRecommendation');
    if(!box){
      box = document.createElement('div');
      box.id = 'autoRecommendation';
      box.style.border = '1px solid rgba(26,51,160,0.18)';
      box.style.borderRadius = '12px';
      box.style.padding = '14px 16px';
      box.style.margin = '10px 0 16px';
      box.style.background = '#f7f9ff';
      box.style.color = '#1f2a4a';
      box.style.fontSize = '14px';
      container.insertBefore(box, container.firstChild);
    }
    try{
      const primary = result.choice.primaryAction;
      const primaryColor = ACTION_COLOR[primary] || '#1a33a0';
      const norm = normalizeScores(result.scores);
      const confPct = pct(norm[primary]||0);
      const reasons = buildBullets(result.features).slice(0,4).map(r=>`<li>${r}</li>`).join('');

      const header = `
      <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; border-bottom: 2px solid #1a33a0;">
        <div style="font-weight:800; color:#1a33a0; display:flex; align-items:center; gap:10px; padding-bottom: 4px;">
          <span class="material-icons" style="font-size:18px; color:#1a33a0;">psychology</span>
          System Recommendation
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="padding:4px 10px; border-radius:999px; background:${primaryColor}10; color:${primaryColor}; font-weight:700;">${ACTION_LABEL[primary]||primary}</span>
          <span style="padding:4px 10px; border-radius:999px; background:${primaryColor}10; color:${primaryColor}; font-weight:700;">${confPct}%</span>
        </div>
      </div>`;

      const bars = renderScoreBars(norm, primary);
      const why = `
        <div style="margin-top:8px; color:#1f2a4a;">Why this</div>
        <ul style="margin:6px 0 0 18px; color:#00030dff">${reasons || '<li>Signals are mixed; additional details may improve accuracy.</li>'}</ul>`;
      box.innerHTML = header + bars + why;

      // Optional: fill narrative textarea
      const textarea = document.getElementById('recommendText') || modal.querySelector('textarea');
      if (textarea){
        const lines = [];
        lines.push(`Recommended action: ${ACTION_LABEL[primary]||primary} (${confPct}% confidence).`);
        const blt = buildBullets(result.features).slice(0,4);
        if (blt.length){ lines.push(`Why: ${blt.join(' ')}`); }
        if (confPct < 75) lines.push('Note: Evidence is moderate; stronger documents and/or additional reporting can improve confidence.');
        textarea.value = lines.join('\n\n');
      }

      // Provide hints to the modal host (optional)
      const recModal = document.getElementById('recommendModal');
      if (recModal && recModal.dataset) {
        recModal.dataset.suggestAction = primary === 'Assessment' ? 'Assessment' : 'Mediation';
        recModal.dataset.suggestAssign = primary === 'Inspection' ? 'Inspection' : (primary === 'Invitation' ? 'Invitation' : '');
      }
    } catch(e){ console.warn('Unauthorized recommendation render failed:', e); }
  }

  function computeRecommendationFromDom(){
    const signals = extractSignals();
    const features = computeFeatures(signals);
    const scores = scoreActions(features);
    const choice = chooseRecommendation(scores);
    return { signals, features, scores, choice };
  }

  // Public API
  window.UnauthorizedFuzzy = {
    extractSignals,
    computeFeatures,
    scoreActions,
    chooseRecommendation,
    computeRecommendation: (signals)=>{
      const s = signals || extractSignals();
      const f = computeFeatures(s);
      const sc = scoreActions(f);
      const ch = chooseRecommendation(sc);
      return { signals: s, features: f, scores: sc, choice: ch };
    },
    renderRecommendation
  };

  // Optional auto-render (dispatcher may also call render on modal open)
  document.addEventListener('DOMContentLoaded', () => {
    try { /* no-op */ } catch (e) {}
  });
})();
