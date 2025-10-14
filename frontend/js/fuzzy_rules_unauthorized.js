// ReklaMap Unauthorized Occupation Fuzzy-Association Recommender (frontend-only)
// Mirrors the structure used by Lot/Pathway recommenders, without altering other files.
// Exposes `window.UnauthorizedFuzzy` with compute + render methods.

(function(){
  // --- Utils ---
  function $(sel, root=document){ return root.querySelector(sel); }
  function $all(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }
  function text(el){ return (el?.textContent || '').trim(); }
  function normalize(str){ return (str || '').toLowerCase().trim(); }

  // --- Detection & Extraction ---
  // We try to work against the rendered complaint form preview (#complaintFormContainer replaced by server HTML)
  // Labels are matched by includes to be resilient to minor copy changes
  function findFieldBlock(labelIncludes){
    // support previews injected without a .complaint-form wrapper
    let blocks = $all('.complaint-form .field-block');
    if (!blocks.length) blocks = $all('.field-block');
    const l = (labelIncludes||'').toLowerCase();
    for (const b of blocks){
      const p = $('p', b) || $('label', b) || b.firstElementChild;
      if (!p) continue;
      if (text(p).toLowerCase().includes(l)) return b;
    }
    return null;
  }
  function parseCheckedLabels(block){
    if (!block) return [];
    return $all('label input:checked', block).map(inp => text(inp.closest('label')).replace(/^[\s\S]*?\)\s*/, '').trim());
  }
  function parseSelectedRadioLabel(block){
    if (!block) return '';
    const inp = $('input[type="radio"]:checked', block);
    if (!inp) return '';
    return text(inp.closest('label'));
  }

  function extractSignals(root=document){
    // Signals tailored for Unauthorized Occupation
    const s = {
      possession_status: '',         // e.g., "squatter", "caretaker", "unknown"
      structure_status: '',          // e.g., "constructed", "temporary", "none"
      reported_to: [],               // list of entities reported to
      site_result: [],               // outcomes from site visit/report
      presence_of_threat: [],        // e.g., asked to vacate, denied access
      resides_on_lot: '',            // yes/no/not sure
      claim_has_docs: '',            // yes/no/not sure
      docs_list: []                  // which docs
    };

    const qPossession = findFieldBlock('How did you come into possession');
    const qStruct = findFieldBlock('structure');
    const qReported = findFieldBlock('reported');
    const qSite = findFieldBlock('result of the report');
    const qThreat = findFieldBlock('What led you to raise this complaint');
    const qReside = findFieldBlock('reside on the disputed lot');
    const qDocs = findFieldBlock('claim to have legal documents');

    s.possession_status = parseSelectedRadioLabel(qPossession);
    s.structure_status = parseSelectedRadioLabel(qStruct);
    s.reported_to = parseCheckedLabels(qReported);
    s.site_result = parseCheckedLabels(qSite);
    s.presence_of_threat = parseCheckedLabels(qThreat);
    s.resides_on_lot = parseSelectedRadioLabel(qReside);
    s.claim_has_docs = parseSelectedRadioLabel(qDocs);
    if (qDocs) s.docs_list = parseCheckedLabels(qDocs);

    return s;
  }

  // --- Fuzzy Features ---
  function computeFeatures(s){
    const f = {
      occupancy_conflict: 0,   // strength that someone occupies disputed lot
      urgency: 0,              // threat/pressure indicators
      doc_strength: 0,         // claimed documents strength
      structure_risk: 0,       // permanence of structure
      reported_strength: 0,    // prior reporting weight
      site_pending: 0          // site investigation pending/no action
    };

    const reside = normalize(s.resides_on_lot);
    f.occupancy_conflict = reside === 'yes' ? 0.9 : reside === 'not sure' ? 0.5 : 0.1;

    const threats = (s.presence_of_threat||[]).map(normalize);
    const urgentKeys = ['vacate', 'denied access', 'stopped from building', 'harass', 'threat'];
    f.urgency = Math.min(1, threats.reduce((acc, t)=>acc + (urgentKeys.some(k=>t.includes(k))?0.4:0), 0));

    const docs = (s.docs_list||[]).map(normalize);
    const docWeight = { 'title': 1.0, 'contract to sell': 0.7, 'deed of sale': 0.6, 'agreement': 0.4, 'certificate of full payment': 0.6 };
    let ds = 0; for (const d of docs){ ds += (docWeight[d] || 0.2); }
    const claimDocs = normalize(s.claim_has_docs);
    if (claimDocs === 'yes' && ds === 0) ds = 0.3;
    if (claimDocs === 'not sure') ds = Math.max(ds, 0.2);
    f.doc_strength = Math.min(1, ds);

    const struct = normalize(s.structure_status);
    f.structure_risk = struct.includes('constructed') || struct.includes('permanent') ? 0.8 : struct.includes('temporary') ? 0.4 : 0.1;

    const reported = (s.reported_to||[]).map(normalize).filter(v=>v && v !== 'none');
    f.reported_strength = Math.min(0.6, reported.length * 0.2);

    const site = (s.site_result||[]).map(normalize);
    f.site_pending = site.some(v => v.includes('under investigation')) || site.some(v => v.includes('no action')) ? 0.3 : 0;

    return f;
  }

  // --- Association-like rule layer over fuzzy features ---
  // Produces action scores similar to other recommenders
  function scoreActions(f){
    const scores = { Inspection: 0, Invitation: 0, Assessment: 0, 'Out of Jurisdiction': 0 };

    // Inspection: strong for occupancy + urgency + site pending
    scores.Inspection = 0.5*f.occupancy_conflict + 0.35*f.urgency + 0.2*f.structure_risk + 0.15*f.site_pending + 0.1*f.reported_strength;

    // Invitation (mediation cue): moderate docs and presence, lower urgency
    scores.Invitation = 0.45*f.doc_strength + 0.25*f.occupancy_conflict + 0.15*(f.urgency < 0.5 ? 1 : 0) + 0.15*f.reported_strength;

    // Assessment: doc vs structure inconsistencies or unclear basis
    const basisWeak = (f.doc_strength < 0.2 ? 0.4 : 0) + (f.reported_strength < 0.2 ? 0.2 : 0);
    scores.Assessment = 0.5*basisWeak + 0.35*f.doc_strength + 0.25*f.structure_risk;

    // Out of Jurisdiction: weak basis and low urgency
    scores['Out of Jurisdiction'] = 0.6*basisWeak + 0.25*(f.urgency < 0.2 ? 1 : 0);

    return scores;
  }

  function chooseRecommendation(scores){
    const entries = Object.entries(scores).sort((a,b)=>b[1]-a[1]);
    const [primary, secondary] = entries;
    let primaryAction = primary ? primary[0] : 'Assessment';
    return { primaryAction, secondaryAction: secondary ? secondary[0] : null, sorted: entries };
  }

  // --- UI helpers (mirrors other files) ---
  const ACTION_LABEL = { Inspection: 'Inspection', Invitation: 'Invitation', Assessment: 'Assessment', 'Out of Jurisdiction': 'Out of Jurisdiction' };
  const ACTION_COLOR = { Inspection: '#1a33a0', Invitation: '#0b8b6a', Assessment: '#8751b8', 'Out of Jurisdiction': '#a03b2b' };
  function clamp01(x){ return Math.max(0, Math.min(1, x)); }
  function pct(x){ return Math.round(clamp01(x)*100); }

  function normalizeScores(raw){
    const total = Object.values(raw).reduce((a,b)=>a+b, 0) + 1e-6;
    const norm = {}; Object.keys(raw).forEach(k => norm[k] = raw[k]/total); return norm;
  }

  function buildBullets(f){
    const bullets = [];
    if (f.occupancy_conflict >= 0.6) bullets.push('Opposing party resides on the disputed lot (strong occupancy signal).');
    if (f.urgency >= 0.6) bullets.push('High urgency indicators (asked to vacate / denied access / threats).');
    if (f.structure_risk >= 0.6) bullets.push('Permanent structure suggests on-site verification.');
    if (f.doc_strength >= 0.6) bullets.push('Opposing party claims strong documents.');
    if ((f.doc_strength < 0.2) && (f.urgency < 0.2)) bullets.push('Weak basis and low urgency may indicate alternative channels.');
    if (!bullets.length) bullets.push('No strong single indicator; applying best-effort fuzzy match.');
    return bullets;
  }

  function renderScoreBars(scores, primary){
    const keys = ['Inspection','Invitation','Assessment','Out of Jurisdiction'];
    return `<div style="margin-top:10px;">${keys.map(k=>{
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
    }).join('')}</div>`;
  }

  function renderRecommendation(result){
    const modal = document.getElementById('recommendModal');
    if(!modal) return;
    const container = modal.querySelector('.modal, .warning-modal') || modal;
    let box = container.querySelector('#autoRecommendation');
    if(!box){
      box = document.createElement('div');
      box.id = 'autoRecommendation';
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
      const body = `
        <div style="margin-top:12px; color:#1f2a4a;">
          <div style="font-weight:700; margin-bottom:8px;">Why this?</div>
          <ul style="margin:0 0 8px 18px;">${reasons}</ul>
        </div>`;

      box.style.border = '1px solid rgba(26,51,160,0.18)';
      box.style.borderRadius = '12px';
      box.style.padding = '14px 16px';
      box.style.margin = '10px 0 16px';
      box.style.background = '#f7f9ff';
      box.style.color = '#1f2a4a';
      box.style.fontSize = '14px';

      box.innerHTML = `${header}${bars}${body}`;

      // Store suggested actions on the modal dataset for pre-selection in next steps
      const recModal = document.getElementById('recommendModal');
      if (recModal && recModal.dataset) {
        recModal.dataset.suggestAction = result.choice.primaryAction === 'Assessment' ? 'Assessment' : 'Mediation';
        recModal.dataset.suggestAssign = result.choice.primaryAction === 'Inspection' ? 'Inspection' : (result.choice.primaryAction === 'Invitation' ? 'Invitation' : '');
      }
    } catch(e){
      console.warn('Unauthorized recommendation render failed:', e);
    }
  }

  function computeRecommendationFromDom(){
    const s = extractSignals();
    const f = computeFeatures(s);
    const scores = scoreActions(f);
    const choice = chooseRecommendation(scores);
    return { signals: s, features: f, scores, choice };
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

  // Optional auto-render if the complaint form is already present
  document.addEventListener('DOMContentLoaded', () => {
    try{
      // Leave orchestration to dispatcher if present
    }catch(e){}
  });
})();
