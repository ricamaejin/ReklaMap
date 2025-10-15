// ReklaMap Boundary Dispute Fuzzy Recommender (frontend-only)
// Builds on the same structure as fuzzy_rules_lot.js but tuned for boundary disputes

(function(){
  // --- Utils ---
  function $(sel, root=document){ return root.querySelector(sel); }
  function $all(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }
  function text(el){ return (el?.textContent || '').trim(); }
  function normalize(str){ return (str || '').toLowerCase().trim(); }

  // --- Detection & Extraction ---
  // Find a field block by matching a snippet of the question label text
  function findFieldBlock(labelIncludes){
    let blocks = $all('.complaint-form .field-block');
    if (!blocks.length) blocks = $all('.field-block');
    const l = (labelIncludes||'').toLowerCase();
    for (const b of blocks){
      const p = $('p', b) || $('label', b) || $('legend', b);
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
    const inp = $('input[type="radio"]:checked', block) || $('input[type="radio"]', block);
    if (!inp) return '';
    return text(inp.closest('label'));
  }
  function parseTextValue(selector, root=document){
    const el = root.querySelector(selector);
    return el ? (el.value || el.textContent || '').trim() : '';
  }

  // Map form questions to signals for boundary dispute
  function extractSignals(root=document){
    // Questions of interest (based on user's mapping):
    // LOT DETAILS AND CLAIM: Q1, Q3, Q5, Q7, Q8, Q9, Q11 (these map to boundary-specific prompts in boundary_dispute.html)
    // PERSONS INVOLVED: Q3, Q4 (reside and claim docs)
    const signals = {
      // Lot details
      nature_of_issue: [],       // Q1 - checkboxes (what is the nature?)
      duration: '',              // Q2 (less important)
      structure_status: '',      // Q3 - built/under construction
      notice: '',                // Q4 (less important)
      confronted: '',            // Q5 - did you confront other party
      dispute_effects: [],       // Q6 (less important)
      reported_to: [],          // Q7 - have you reported
      site_inspection: '',       // Q8 - was a site inspection done
      site_result: [],           // Q9 - result of report/inspection
      have_docs: '',             // Q10 - do you have docs (important)
      ongoing_development: '',   // Q11 - relevant

      // Persons involved
      persons_involved_list: [], // names / pairs
      persons_reside: '',        // persons involved: do they reside on the disputed boundary? (Q3 in persons)
      persons_claim_docs: '',    // do they claim docs? (Q4 in persons)
      persons_claim_docs_list: []
    };

    // Lot details blocks
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

    // Persons involved
    // We will try to find the dynamic pairs container and check whether listed persons "reside" or "claim docs"
    const pairs = $all('#pairsContainer .pair-row') || $all('.pairs .pair-row') || [];
    if (pairs.length){
      signals.persons_involved_list = pairs.map(r => {
        const name = parseTextValue('input[name="person_name"]', r) || parseTextValue('.pair .name', r) || '';
        const blk = parseTextValue('input[name="blk"]', r) || '';
        const lot = parseTextValue('input[name="lot"]', r) || '';
        return { name, blk, lot };
      });

      // Try to infer persons_reside and claim docs from the form (if there are global radio blocks for these)
      const p_reside_block = findFieldBlock('Do they reside on the disputed lot') || findFieldBlock('Do they reside on or near the disputed boundary');
      const p_claim_block = findFieldBlock('Do they claim to have legal or assignment documents');
      signals.persons_reside = parseSelectedRadioLabel(p_reside_block);
      signals.persons_claim_docs = parseSelectedRadioLabel(p_claim_block);
      if (p_claim_block) signals.persons_claim_docs_list = parseCheckedLabels(p_claim_block);
    }

    return signals;
  }

  // --- Fuzzy Feature Construction ---
  function computeFeatures(s){
    // features are normalized to [0,1]
    const f = {
      doc_strength: 0,        // strength of complainant's documents
      opposing_doc_claim: 0,  // opposing party claiming docs
      physical_encroachment: 0, // presence of built structure encroachment
      urgent_effects: 0,      // threats/harassment/damage
      residency_conflict: 0,  // opposing party resides on disputed lot
      reported_strength: 0,   // if reported and who reported
      site_action_taken: 0,   // site inspection result indicates action
      family_dispute: 0,      // family-related conflict
      basis_weakness: 0       // weak basis for complaint -> OOT
    };

    // Normalizations and helpers
    const nature = (s.nature_of_issue||[]).map(x => normalize(x));
    const effects = (s.dispute_effects||[]).map(x => normalize(x));
    const reported = (s.reported_to||[]).map(x => normalize(x));
    const siteRes = (s.site_result||[]).map(x => normalize(x));
    const personsDocs = (s.persons_claim_docs_list||[]).map(x => normalize(x));
    const haveDocs = normalize(s.have_docs);
    const reside = normalize(s.persons_reside);

    // doc_strength: if user has docs, give weight; if specific doc types are enumerated, boost
    let ds = 0;
    if (haveDocs.includes('yes')) ds = 1;
    if (personsDocs.length && personsDocs.includes('title')) {
      // opposing party directly claims title -> reduce complainant doc confidence
      f.opposing_doc_claim = 0.8;
    }
    f.doc_strength = Math.min(1, ds);

    // physical_encroachment: based on nature and structure_status
    if (nature.some(n => n.includes('structure') || n.includes('fence') || n.includes('encroach'))) f.physical_encroachment = 1;
    if (normalize(s.structure_status).includes('ongoing') || normalize(s.structure_status).includes('partially') ) f.physical_encroachment = Math.max(f.physical_encroachment, 0.8);

    // urgent_effects: threats, harassment, physical altercation, demolition, property damage
    if (effects.some(e => e.includes('threat') || e.includes('harass') || e.includes('physical') || e.includes('demolition') || e.includes('damage'))) f.urgent_effects = 1;

    // residency_conflict
    if (reside === 'yes') f.residency_conflict = 1;
    else if (reside === 'not sure') f.residency_conflict = 0.5;

    // reported_strength: more reporting bodies -> stronger
    f.reported_strength = Math.min(1, reported.length * 0.25);

    // site_action_taken: if site inspection occurred and result suggests action, score higher
    if (s.site_inspection && s.site_inspection.toLowerCase().includes('yes')){
      // site_result could include 'advised to adjust', 'still under investigation', 'no action', 'no valid claim'
      if (siteRes.some(r => r.includes('advised') || r.includes('adjust') || r.includes('asked to provide') )) f.site_action_taken = 0.8;
      if (siteRes.some(r => r.includes('still under') || r.includes('investigation'))) f.site_action_taken = Math.max(f.site_action_taken, 0.4);
      if (siteRes.some(r => r.includes('no action') || r.includes('no valid'))) f.site_action_taken = Math.max(f.site_action_taken, 0.1);
    }

    // family_dispute
    if (nature.some(n => n.includes('family'))) f.family_dispute = 0.8;

    // basis_weakness: combine low docs, low reporting, and clarifications only
    const lowDocs = f.doc_strength < 0.2 ? 1 : 0;
    const lowReported = f.reported_strength < 0.2 ? 1 : 0;
    const clarificationOnly = nature.some(n => n.includes('clarification') || n.includes('not sure')) ? 1 : 0;
    f.basis_weakness = Math.min(1, 0.5*lowDocs + 0.3*lowReported + 0.2*clarificationOnly);

    // Adjust opposing_doc_claim effect if strong opposing doc
    if (f.opposing_doc_claim > 0) {
      // reduce complainant doc_strength influence
      f.doc_strength = Math.max(0, f.doc_strength - 0.3);
    }

    // Final clamping
    Object.keys(f).forEach(k => { f[k] = Math.max(0, Math.min(1, f[k]||0)); });
    return f;
  }

  // --- Association-style Scoring but fuzzy ---
  function scoreActions(f, signals){
    // Higher values = stronger recommendation
    const scores = { Inspection: 0, Invitation: 0, Assessment: 0, 'Out of Jurisdiction': 0 };

    // Early, prioritized rules based on common scenarios (sample cases guidance)
    // 1) Government project -> Out of Jurisdiction
    if (signals && signals.ongoing_development && signals.ongoing_development.toLowerCase().includes('yes')){
      return { Inspection: 0, Invitation: 0, Assessment: 0, 'Out of Jurisdiction': 1 };
    }

    // 2) Encroachment affecting utilities reported to Barangay -> often OOT/Barangay matter
    if (signals && Array.isArray(signals.dispute_effects) && signals.dispute_effects.some(d => /utility|water|drainage|electric/i.test(d)) && Array.isArray(signals.reported_to) && signals.reported_to.some(r => /barangay/i.test(r))){
      return { Inspection: 0, Invitation: 0, Assessment: 0, 'Out of Jurisdiction': 1 };
    }

    // 3) Structure removed but boundary still contested -> favor Invitation (mediation) and Assessment
    if (signals && signals.structure_status && /removed|structure was removed|removed but boundary/i.test(signals.structure_status.toLowerCase())){
      scores.Invitation += 0.7;
      scores.Assessment += 0.4;
    }

    // 4) Documents present + no site inspection -> inspection should be prioritized (S2, S3)
    if (signals && signals.have_docs && signals.have_docs.toLowerCase().includes('yes') && signals.site_inspection && !/yes/i.test(signals.site_inspection)){
      scores.Inspection += 0.6;
    }

    // 5) Reported to USAD/PHASELAD -> prioritize Inspection (USAD should inspect) unless USAD already inspected
    const reportedTo = (signals && Array.isArray(signals.reported_to)) ? signals.reported_to.join(' ').toLowerCase() : '';
    const siteBy = reportedTo || '';
    if (/usad|phaselad/i.test(reportedTo)){
      // if USAD has inspected already (site_inspection yes) then prefer Assessment
      if (signals && signals.site_inspection && /yes/i.test(signals.site_inspection)){
        scores.Assessment += 0.6;
      } else {
        scores.Inspection += 0.6;
      }
    }

    // 6) If site inspection done by HOA or Barangay but not USAD and still under investigation -> prefer Inspection (USAD should inspect)
    if (signals && signals.site_inspection && /yes/i.test(signals.site_inspection) && signals.site_result && Array.isArray(signals.site_result) && signals.site_result.join(' ').toLowerCase().includes('still under')){
      if (/hoa|barangay/i.test(reportedTo) && !/usad/i.test(reportedTo)){
        scores.Inspection += 0.5;
      }
    }

    // 7) Urgent effects with docs -> Invitation/Assessment tie (S5)
    if (f.urgent_effects >= 0.6 && f.doc_strength >= 0.5){
      scores.Invitation += 0.45;
      scores.Assessment += 0.5;
    }

    // 8) If opposing party claims docs and resident resides, favor Inspection to verify on-site
    if (f.opposing_doc_claim >= 0.6 && f.residency_conflict >= 0.6){
      scores.Inspection += 0.5;
    }

    // Continue to base fuzzy scoring below
    
    // Inspection is favored when there's physical encroachment, residency conflict, urgent effects
    scores.Inspection += 0.5*f.physical_encroachment + 0.4*f.residency_conflict + 0.3*f.urgent_effects + 0.2*f.reported_strength + 0.15*f.site_action_taken;

    // Invitation (mediation) is favored when family dispute, low-doc conflict, or non-urgent interpersonal issues
  scores.Invitation += 0.6*f.family_dispute + 0.35*(1 - f.doc_strength) + 0.25*(f.urgent_effects < 0.4 ? 0.5 : 0) + 0.15*f.reported_strength;

    // Assessment suits when there are document inconsistencies or official record problems
  scores.Assessment += 0.6*(1 - f.doc_strength) + 0.5*f.opposing_doc_claim + 0.35*f.site_action_taken + 0.2*f.reported_strength;

    // Out of Jurisdiction when basis_weakness high and no strong physical encroachment or residency
  scores['Out of Jurisdiction'] += 0.7*f.basis_weakness + 0.25*(1 - f.physical_encroachment) + 0.2*(1 - f.residency_conflict);

    // Normalize a bit by ensuring non-negative
    Object.keys(scores).forEach(k => { scores[k] = Math.max(0, scores[k]||0); });
    return scores;
  }

  function chooseRecommendation(scores){
    const entries = Object.entries(scores).sort((a,b)=>b[1]-a[1]);
    const primary = entries[0] || ['Assessment', 0];
    const secondary = entries[1] || [null, 0];
    let primaryAction = primary[0];
    // If primary is Out of Jurisdiction but margin small, prefer next
    if (primaryAction === 'Out of Jurisdiction'){
      const margin = primary[1] - (secondary[1]||0);
      if (margin < 0.12) primaryAction = secondary[0] || primaryAction;
    }
    return { primaryAction, secondaryAction: secondary[0] || null, sorted: entries };
  }

  // --- UI helpers (mirroring lot style) ---
  const ACTION_LABEL = { Inspection: 'Inspection', Invitation: 'Invitation', Assessment: 'Assessment', 'Out of Jurisdiction': 'Out of Jurisdiction' };
  const ACTION_COLOR = { Inspection: '#1a33a0', Invitation: '#0b8b6a', Assessment: '#8751b8', 'Out of Jurisdiction': '#a03b2b' };
  function clamp01(x){ return Math.max(0, Math.min(1, x)); }
  function pct(x){ return Math.round(clamp01(x)*100); }

  function normalizeScores(raw){
    const total = Object.values(raw).reduce((a,b)=>a+b, 0) + 1e-9;
    const norm = {};
    Object.keys(raw).forEach(k => norm[k] = raw[k]/total);
    return norm;
  }

  function buildBullets(features){
    const bullets = [];
    if (features.physical_encroachment >= 0.6) bullets.push('Built structure/fence encroachment detected - field inspection recommended.');
    if (features.residency_conflict >= 0.6) bullets.push('Opposing party resides on the disputed area; inspection or mediation may be needed.');
    if (features.urgent_effects >= 0.6) bullets.push('Violent or damaging incidents reported; prioritize inspection and protective measures.');
    if (features.family_dispute >= 0.6) bullets.push('Family-related dispute; mediation (invitation) may resolve the issue.');
    if (features.doc_strength >= 0.6) bullets.push('Complainant has supporting documents (titles/contracts).');
    if (features.opposing_doc_claim >= 0.6) bullets.push('Opposing party claims ownership documents; consider assessment for verification.');
    if (features.basis_weakness >= 0.6) bullets.push('Weak basis detected (few/unclear documents and low reporting); may be Out of Jurisdiction.');
    if (!bullets.length) bullets.push('Signals are mixed; apply standard assessment and consider further fact-finding.');
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
    if (confPct < 75) bits.push('Note: Confidence is not maximal. Additional documents (titles, contracts) and precise event dates can improve the recommendation.');
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
    // Try to detect boundary form presence
    const hasBoundary = !!findFieldBlock('nature of the boundary issue') || !!findFieldBlock('boundary dispute');
    if(!hasBoundary) return null;
    const signals = extractSignals();
  const features = computeFeatures(signals);
  const scores = scoreActions(features, signals);
    const choice = chooseRecommendation(scores);
    return { signals, features, scores, choice };
  }

  // Public API
  window.BoundaryFuzzy = {
    extractSignals,
    computeFeatures,
    scoreActions,
    chooseRecommendation,
    computeRecommendation: (signals) => {
      const s = signals || extractSignals();
    const f = computeFeatures(s);
    const sc = scoreActions(f, s);
      const ch = chooseRecommendation(sc);
      return { signals: s, features: f, scores: sc, choice: ch };
    },
    renderRecommendation
  };

  // Auto-render when modal exists
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const modal = document.getElementById('recommendModal');
      if (!modal) return;
      const result = computeRecommendationFromDom();
      if (result) renderRecommendation(result);
    } catch (e) { /* no-op */ }
  });

})();
