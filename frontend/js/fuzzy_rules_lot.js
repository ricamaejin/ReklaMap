// ReklaMap Lot Dispute Fuzzy Recommender (frontend-only)
// Retains existing logic but adopts the same structure/UI as fuzzy_rules_pathway.js

(function(){
  // --- Utils ---
  function $(sel, root=document){ return root.querySelector(sel); }
  function $all(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }
  function text(el){ return (el?.textContent || '').trim(); }
  function normalize(str){ return (str || '').toLowerCase().trim(); }

  // --- Detection & Extraction ---
  function findFieldBlock(labelIncludes){
    // Support previews injected without a .complaint-form wrapper
    let blocks = $all('.complaint-form .field-block');
    if (!blocks.length) blocks = $all('.field-block');
    const l = (labelIncludes||'').toLowerCase();
    for (const b of blocks){
      const p = $('p', b);
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
    const signals = {
      q1_possession: '',
      q2_nature: [],
      q4_reason: [],
      q5_reported: [],
      q6_site_result: [],
      q10_reside: '',
      q9_claim_docs: '',
      q9_docs_list: []
    };

    // Lot Details
    const q1Block = findFieldBlock('How did you come into possession');
    const q2Block = findFieldBlock('nature of the ownership conflict');
    const q4Block = findFieldBlock('What led you to raise this complaint');
    const q5Block = findFieldBlock('Have you reported');
    const q6Block = findFieldBlock('result of the report');

    signals.q1_possession = parseSelectedRadioLabel(q1Block);
    signals.q2_nature = parseCheckedLabels(q2Block);
    signals.q4_reason = parseCheckedLabels(q4Block);
    signals.q5_reported = parseCheckedLabels(q5Block);
    signals.q6_site_result = parseCheckedLabels(q6Block);

    // Persons Involved
    const q10Block = findFieldBlock('Do they reside on the disputed lot');
    const q9Block = findFieldBlock('Do they claim to have legal documents');
    signals.q10_reside = parseSelectedRadioLabel(q10Block);
    signals.q9_claim_docs = parseSelectedRadioLabel(q9Block);
    if (q9Block){ signals.q9_docs_list = parseCheckedLabels(q9Block); }

    return signals;
  }

  // --- Features & Scoring (retain existing logic) ---
  function computeFeatures(s){
    const f = {
      doc_strength: 0, family_dispute: 0, record_error: 0, duplicate_contract: 0,
      someone_claiming: 0, illegal_sale: 0, urgency: 0, occupancy_conflict: 0,
      reported_strength: 0, site_investigation_pending: 0, site_no_action: 0, basis_weakness: 0
    };

    const possession = normalize(s.q1_possession);
    const nature = (s.q2_nature||[]).map(x => normalize(x));
    const reason = (s.q4_reason||[]).map(x => normalize(x));
    const reported = (s.q5_reported||[]).map(x => normalize(x));
    const site = (s.q6_site_result||[]).map(x => normalize(x));
    const reside = normalize(s.q10_reside);
    const claimDocs = normalize(s.q9_claim_docs);
    const docs = (s.q9_docs_list||[]).map(x => normalize(x));

    const docWeight = { 'title': 1.0, 'contract to sell': 0.7, 'certificate of full payment': 0.6, 'pre-qualification stub': 0.4, 'contract/agreement': 0.5, 'deed of sale': 0.6 };
    let ds = 0; for (const d of docs){ ds += (docWeight[d] || 0); }
    f.doc_strength = Math.min(1, ds);
    if (claimDocs === 'yes' && f.doc_strength === 0) f.doc_strength = 0.3;
    if (claimDocs === 'not sure') f.doc_strength = Math.max(f.doc_strength, 0.2);
    if (claimDocs === 'no') f.doc_strength = 0;

    f.family_dispute = nature.some(n => n.includes('family')) ? 0.8 : 0;
    f.record_error = nature.some(n => n.includes('masterlist') || n.includes('details incorrect') || n.includes('name removed')) ? 0.75 : 0;
    f.duplicate_contract = nature.some(n => n.includes('someone else has a contract')) ? 0.8 : 0;
    f.someone_claiming = nature.some(n => n.includes('someone else is claiming') || n.includes('someone else claiming')) ? 0.7 : 0;
    f.illegal_sale = (nature.some(n => n.includes('illegally sold')) || possession.includes('purchased from another')) ? 0.8 : 0;

    const addIf = (cond, w) => { if (cond) f.urgency += w; };
    addIf(reason.some(r => r.includes('vacate')), 0.6);
    addIf(reason.some(r => r.includes('denied access')), 0.5);
    addIf(reason.some(r => r.includes('stopped from building')), 0.6);
    addIf(reason.some(r => r.includes('received notice')), 0.4);
    addIf(reason.some(r => r.includes('duplicate record')), 0.3);
    f.urgency = Math.min(1, f.urgency);

    f.occupancy_conflict = reside === 'yes' ? 0.8 : reside === 'not sure' ? 0.4 : 0.1;
    const effectiveReports = reported.filter(v => v !== 'none');
    f.reported_strength = Math.min(0.6, effectiveReports.length * 0.2);
    f.site_investigation_pending = site.some(v => v.includes('under investigation')) ? 0.3 : 0;
    f.site_no_action = site.some(v => v.includes('no action')) ? 0.3 : 0;

    const clarificationOnly = reason.some(r => r.includes('clarification')) ? 1 : 0;
    const lowDocs = f.doc_strength < 0.2 ? 1 : 0;
    const lowReport = f.reported_strength < 0.2 ? 1 : 0;
    const uncertainReside = reside === 'not sure' ? 1 : 0;
    f.basis_weakness = Math.min(1, 0.45*lowDocs + 0.25*lowReport + 0.2*clarificationOnly + 0.1*uncertainReside);

    if (possession.includes('passed on by a family')) f.family_dispute = Math.max(f.family_dispute, 0.7);
    if (possession.includes('verbal promise')) f.basis_weakness = Math.min(1, f.basis_weakness + 0.25);
    if (possession.includes('relocated')) f.record_error = Math.max(f.record_error, 0.4);
    return f;
  }
  function scoreActions(f){
    const scores = { Inspection: 0, Invitation: 0, Assessment: 0, 'Out of Jurisdiction': 0 };
    scores.Inspection = 0.5*f.occupancy_conflict + 0.4*f.urgency + 0.3*f.someone_claiming + 0.2*f.illegal_sale + 0.1*f.duplicate_contract + 0.15*f.site_investigation_pending + 0.15*f.site_no_action + 0.1*f.reported_strength;
    scores.Invitation = 0.6*f.family_dispute + 0.4*f.someone_claiming + 0.25*(f.doc_strength > 0.4 ? 1 : 0) + 0.2*(f.site_no_action > 0 ? 1 : 0) + 0.15*(f.duplicate_contract > 0 ? 1 : 0) + 0.1*f.urgency;
    scores.Assessment = 0.6*f.record_error + 0.5*f.doc_strength + 0.35*f.illegal_sale + 0.25*(f.basis_weakness > 0.3 ? 1 : 0) + 0.2*(f.duplicate_contract > 0 ? 1 : 0);
    scores['Out of Jurisdiction'] = 0.6*f.basis_weakness + 0.25*(f.doc_strength < 0.2 ? 1 : 0) + 0.2*(f.reported_strength < 0.2 ? 1 : 0) + 0.15*(f.urgency < 0.2 ? 1 : 0);
    return scores;
  }
  function chooseRecommendation(scores){
    const entries = Object.entries(scores).sort((a,b)=>b[1]-a[1]);
    const [primary, secondary] = entries;
    let primaryAction = primary ? primary[0] : 'Assessment';
    if (primaryAction === 'Out of Jurisdiction'){
      const margin = (primary ? primary[1] : 0) - (secondary ? secondary[1] : 0);
      if (margin < 0.1) primaryAction = (secondary ? secondary[0] : 'Assessment');
    }
    return { primaryAction, secondaryAction: secondary ? secondary[0] : null, sorted: entries };
  }

  // --- UI helpers (mirroring pathway style) ---
  const ACTION_LABEL = { Inspection: 'Inspection', Invitation: 'Invitation', Assessment: 'Assessment', 'Out of Jurisdiction': 'Out of Jurisdiction' };
  const ACTION_COLOR = { Inspection: '#1a33a0', Invitation: '#0b8b6a', Assessment: '#8751b8', 'Out of Jurisdiction': '#a03b2b' };
  function clamp01(x){ return Math.max(0, Math.min(1, x)); }
  function pct(x){ return Math.round(clamp01(x)*100); }

  function normalizeScores(raw){
    const total = Object.values(raw).reduce((a,b)=>a+b, 0) + 1e-6;
    const norm = {};
    Object.keys(raw).forEach(k => norm[k] = raw[k]/total);
    return norm;
  }
  function topAction(norm){
    let bestKey = 'Assessment'; let bestVal = -1;
    Object.keys(norm).forEach(k => { if (norm[k] > bestVal){ bestVal = norm[k]; bestKey = k; } });
    return { action: bestKey, confidence: clamp01(bestVal) };
  }
  function buildBullets(features){
    const bullets = [];
    if (features.occupancy_conflict >= 0.6) bullets.push('Opposing party resides on the disputed lot (strong occupancy signal).');
    if (features.urgency >= 0.6) bullets.push('High urgency indicators (asked to vacate / denied access / stopped from building).');
    if (features.family_dispute >= 0.6) bullets.push('Family-related claim indicates mediation may be effective.');
    if (features.record_error >= 0.6) bullets.push('Record inconsistency detected (masterlist/name/lot details).');
    if (features.doc_strength >= 0.6) bullets.push('Opposing party claims strong documents (e.g., Title/Contract to Sell).');
    if (features.illegal_sale >= 0.6) bullets.push('Possible irregular transfer/illegal sale involved.');
    if (features.basis_weakness >= 0.6) bullets.push('Weak basis (low documents/reporting and clarification-only).');
    if (!bullets.length) bullets.push('No strong single indicator; applying best-effort fuzzy match.');
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

  function buildNarrative(signals, norm, primaryKey){
    const action = ACTION_LABEL[primaryKey] || primaryKey;
    const confPct = pct(norm[primaryKey]||0);
    const confLabel = confPct >= 75 ? 'high confidence' : (confPct >= 50 ? 'moderate confidence' : 'low confidence');

    const features = computeFeatures(signals);
    const bullets = buildBullets(features);
    const bits = [];
    bits.push(`Recommended action: ${action} (${confPct}% ${confLabel}).`);
    if (bullets.length){ bits.push(`Why this: ${bullets.join(' ')}`); }
    if (confPct < 75) bits.push('Note: Confidence is not maximal. Additional documents (e.g., titles, contracts) and precise event dates can improve the recommendation.');
    return bits.join('\n\n');
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
    try {
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
        <ul style="margin:6px 0 0 18px; color: #00030dff">${reasons || '<li>Signals are mixed; additional details may improve accuracy.</li>'}</ul>`;
      box.innerHTML = header + bars + why;

      // Fill the narrative textarea if present
      const textarea = document.getElementById('recommendText') || modal.querySelector('textarea');
      if (textarea){ textarea.value = buildNarrative(result.signals, norm, primary); }

      // Suggest next-step routing for modal usage
      modal.dataset.suggestAssign = (primary === 'Inspection' || primary === 'Invitation') ? primary : (result.choice.secondaryAction === 'Inspection' || result.choice.secondaryAction === 'Invitation' ? result.choice.secondaryAction : '');
      modal.dataset.suggestAction = (primary === 'Assessment' || primary === 'Out of Jurisdiction') ? primary : (result.choice.secondaryAction === 'Assessment' || result.choice.secondaryAction === 'Out of Jurisdiction' ? result.choice.secondaryAction : '');
    } catch (e) {
      box.innerHTML = '<div style="font-weight:700; color:#a03b2b;">Unable to render detailed recommendation UI.</div>';
    }
  }

  function computeRecommendationFromDom(){
    const hasLot = !!findFieldBlock('How did you come into possession');
    if(!hasLot) return null;
    const signals = extractSignals();
    const features = computeFeatures(signals);
    const scores = scoreActions(features);
    const choice = chooseRecommendation(scores);
    return { signals, features, scores, choice };
  }

  // Public API (mirrors pathway style)
  window.LotFuzzy = {
    extractSignals,
    computeFeatures,
    scoreActions,
    chooseRecommendation,
    computeRecommendation: (signals) => {
      const s = signals || extractSignals();
      const f = computeFeatures(s);
      const sc = scoreActions(f);
      const ch = chooseRecommendation(sc);
      return { signals: s, features: f, scores: sc, choice: ch };
    },
    renderRecommendation
  };

  // Optional: Single-shot render on DOM ready (dispatcher will also render on open)
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const modal = document.getElementById('recommendModal');
      if (!modal) return;
      const result = computeRecommendationFromDom();
      if (result) renderRecommendation(result);
    } catch (e) { /* no-op */ }
  });
})();
