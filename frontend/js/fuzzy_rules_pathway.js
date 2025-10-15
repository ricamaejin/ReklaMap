/* Pathway Dispute: Fuzzy Association Rules for Recommended Action
   Exposes global: window.PathwayFuzzy with helpers:
   - extractAnswers(rootEl)
   - computeRecommendation(answers)
   - renderRecommendation(result)
*/
(function(){
  function toArray(x){ return Array.isArray(x) ? x : (x != null ? [x] : []); }
  function clamp01(x){ return Math.max(0, Math.min(1, x)); }
  function pct(x){ return Math.round(clamp01(x)*100); }
  function titleCase(s){ return (s||'').split('_').map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(' '); }

  // Keep a last known answer set to allow rendering narrative without re-extraction
  let __lastAnswers = {};

  // --- Membership functions ---
  function urgencyFromQ4(v){
    if(!v) return 0;
    v = v.toLowerCase();
    if(v.includes('fully')) return 1.0;
    if(v.includes('partial')) return 0.65;
    if(v.includes('removed')) return 0.25;
    if(v === 'no') return 0.0;
    return 0.2; // not sure
  }
  function severityFromQ2(v){
    if(!v) return 0;
    v = v.toLowerCase();
    // More granular severity mapping
    if(v.includes('permanent')) return 0.9;            // house extension / wall
    if(v.includes('fence') || v.includes('gate')) return 0.8; 
    if(v.includes('store') || v.includes('business')) return 0.75;
    if(v.includes('vehicle') || v.includes('parked')) return 0.5;  // typically barangay jurisdiction
    if(v.includes('construction') || v.includes('debris') || v.includes('materials')) return 0.45;
    if(v.includes('temporary') || v.includes('chairs') || v.includes('tables') || v.includes('stalls')) return 0.4;
    return 0.4;
  }
  function durationFromQ3(v){
    if(!v) return 0.2;
    v = v.toLowerCase();
    if(v.includes('more than 6')) return 0.8;
    if(v.includes('1-6')) return 0.55;
    if(v.includes('less than 1')) return 0.35;
    if(v.includes('not sure')) return 0.25;
    return 0.3;
  }
  function typeFromQ1(v){
    v = (v||'').toLowerCase();
    return {
      public_sidewalk: v.includes('public sidewalk') || v.includes('pedestrian'),
      common_path: v.includes('common path') || v.includes('alley'),
      gov_easement: v.includes('government-declared') || v.includes('right-of-way') || v.includes('right of way'),
      utilities_path: v.includes('utilities') || v.includes('water lines') || v.includes('drainage')
    };
  }
  function impactFromQ5(arr){
    const list = toArray(arr);
    if(!list.length) return 0;
    let score = 0;
    list.forEach(v => {
      if(!v) return;
      const s = v.toLowerCase();
      if(s.includes('cannot pass')) score += 0.4;
      else if(s.includes('emergency')) score += 0.4;
      else if(s.includes('unsafe') || s.includes('narrow')) score += 0.3;
      else if(s.includes('children') || s.includes('elderly') || s.includes('pwd')) score += 0.3;
      else if(s.includes('forced to walk')) score += 0.25;
    });
    // squash to [0,1]
    return clamp01(score);
  }
  function socialConcernFromQ6Q7(q6, q7){
    let s = 0;
    if(q6 && q6.toLowerCase() === 'yes') s += 0.5; // other residents concerned
    if(q7){
      const t = q7.toLowerCase();
      if(t.includes('barangay')) s += 0.4;
      else if(t.includes('by me')) s += 0.25;
      else if(t === 'no') s += 0.0;
      else s += 0.15; // not sure
    }
    return clamp01(s);
  }
  function authorityFromQ9(arr){
    const list = toArray(arr).map(v => (v||'').toLowerCase());
    return {
      none: list.includes('none'),
      barangay: list.includes('barangay'),
      hoa: list.includes('hoa'),
      ngc: list.includes('ngc'),
      usad: list.includes('usad - phaseland') || list.includes('usad - phaselad') || list.includes('usad')
    };
  }
  function inspectionOrgFromQ10(v){
    v = (v||'').toLowerCase();
    return {
      barangay: v.includes('barangay'),
      hoa: v.includes('hoa'),
      ngc: v.includes('ngc') || v.includes('usad')
    };
  }
  function resultFromQ11(arr){
    const list = toArray(arr).map(v => (v||'').toLowerCase());
    return {
      advised_adjust: list.some(x => x.includes('advised to adjust') || x.includes('vacate')),
      provide_docs: list.some(x => x.includes('provide more documents')),
      under_investigation: list.some(x => x.includes('under investigation')),
      no_action: list.some(x => x.includes('no action')),
      not_applicable: list.some(x => x.includes('not applicable'))
    };
  }

  function evidenceScore(answers){
    // Penalize unknown/none, reward filled & strong signals
    let answered = 0, total = 0, penalty = 0, bonus = 0;
    const keys = Object.keys(answers||{});
    keys.forEach(k => {
      total++;
      const v = answers[k];
      if(v == null) return;
      if(Array.isArray(v)) {
        if(v.length){ answered++; }
        if(v.some(x => /not applicable|not sure/i.test(x))) penalty += 0.05;
        if(v.some(x => /none/i.test(x))) penalty += 0.08; // slightly stronger penalty for "None"
      } else if(typeof v === 'string') {
        if(v.trim()) answered++;
        if(/not applicable|not sure/i.test(v)) penalty += 0.05;
        if(/none/i.test(v)) penalty += 0.08;
      }
    });
    // Core signals
    bonus += urgencyFromQ4(answers.q4)*0.2 + severityFromQ2(answers.q2)*0.12 + impactFromQ5(answers.q5)*0.12;
    const completeness = total ? answered/total : 0.5;
    return clamp01(completeness - penalty + bonus);
  }

  // --- Compute action scores ---
  function computeRecommendation(answers){
    answers = answers || {};
    const type1 = typeFromQ1(answers.q1);
    const urg = urgencyFromQ4(answers.q4);
    const sev = severityFromQ2(answers.q2);
    const dur = durationFromQ3(answers.q3);
    const imp = impactFromQ5(answers.q5);
    const soc = socialConcernFromQ6Q7(answers.q6, answers.q7);
    const auth = authorityFromQ9(answers.q9);
    const inspOrg = inspectionOrgFromQ10(answers.q10);
    const res11 = resultFromQ11(answers.q11);
    const ev = evidenceScore(answers);

    const q12 = (answers.q12||'').toLowerCase();
    const q2 = (answers.q2||'').toLowerCase();
    const q4 = (answers.q4||'').toLowerCase();

    // Strong overrides
    // Vehicles parked long-term → typically barangay/traffic: out of jurisdiction for HOA context
    const parked = q2.includes('vehicle') || q2.includes('parked');
    if(parked) {
      const scores = { inspection: 0.05, mediation: 0.05, assessment: 0.05, out_of_jurisdiction: 0.85 };
      return { action: 'out_of_jurisdiction', confidence: 0.9, scores, reasons: ['Long-term parked vehicles are generally handled by barangay/traffic authorities.'] };
    }
    // Government project / ongoing development strongly suggests outside HOA scope
    if(q12.includes('yes') || type1.gov_easement) {
      const base = 0.8 + (type1.gov_easement?0.1:0) + ((auth.ngc||auth.usad||inspOrg.ngc)?0.05:0);
      const scores = { inspection: 0.05, mediation: 0.05, assessment: 0.1, out_of_jurisdiction: clamp01(base) };
      return { action: 'out_of_jurisdiction', confidence: clamp01(0.85 + (1-0.85)*ev), scores, reasons: ['Government easement or ongoing development indicates external jurisdiction.'] };
    }
    // Obstruction removed (or likely to return) → assessment
    if(q4.includes('removed') || q4 === 'no') {
      const scores = { inspection: 0.1, mediation: 0.15, assessment: 0.7, out_of_jurisdiction: 0.05 };
      return { action: 'assessment', confidence: clamp01(0.8 + 0.15*ev), scores, reasons: ['Obstruction reported removed; verify status and documents through assessment.'] };
    }

    // Base scores
    let inspection = 0, mediation = 0, assessment = 0, ooj = 0;

    // Inspection drivers: present + severe + high impact + long duration
    inspection += urg*0.4 + sev*0.25 + imp*0.25 + dur*0.15;
    if(type1.public_sidewalk || type1.utilities_path) inspection += 0.08; // public/utility access merits verification
    if(res11.no_action) inspection += 0.08;                 // no action taken yet → act
    if(res11.under_investigation) inspection += 0.04;       // keep pressure
    if(inspOrg.barangay || inspOrg.hoa) inspection -= 0.12; // already inspected locally

    // Mediation drivers: social concern, partial obstruction, neighbor-to-neighbor structures, disputes escalating
    const partial = q4.includes('partial');
    const fenceLike = /fence|gate|store|business/.test(q2);
    const escalations = toArray(answers.q8).map(s=>String(s||'').toLowerCase());
    const hasViolence = escalations.some(s => /threats|harassment|altercation|damage/.test(s));
    mediation += soc*0.5 + (partial?0.2:0) + (fenceLike?0.2:0);
    if(auth.barangay || auth.hoa) mediation += 0.08;        // local bodies involved → convene
    if(hasViolence) mediation += 0.12;                       // de-escalate via meeting

    // Assessment drivers: uncertainty + doc requests + prior inspections + complex governance
    const unsure = [answers.q3, answers.q4, answers.q6, answers.q7].some(v => /not sure/i.test(v||''));
    assessment += (unsure?0.18:0) + (res11.provide_docs?0.3:0) + ((inspOrg.barangay||inspOrg.hoa)?0.12:0);
    if(type1.utilities_path) assessment += 0.08; // determine utility easement specifics

    // Out of jurisdiction: weak HOA scope indicators or external agency presence
    const externalAgency = (auth.ngc || auth.usad || inspOrg.ngc);
    ooj += (externalAgency?0.35:0) + (type1.public_sidewalk?0.1:0) + (type1.gov_easement?0.2:0);

    // Normalize
    inspection = clamp01(inspection);
    mediation = clamp01(mediation);
    assessment = clamp01(assessment);
    ooj = clamp01(ooj);
    const raw = { inspection, mediation, assessment, out_of_jurisdiction: ooj };
    const sum = Object.values(raw).reduce((a,b)=>a+b, 1e-6);
    const norm = Object.fromEntries(Object.entries(raw).map(([k,v])=>[k, v/sum]));

    // Pick best & compute confidence using margin and evidence completeness
    const entries = Object.entries(norm).sort((a,b)=>b[1]-a[1]);
    const [bestK, bestV] = entries[0];
    const secondV = (entries[1]||[])[1] || 0;
    const margin = Math.max(0, bestV - secondV); // 0..1
    const confidence = clamp01(0.6*margin + 0.4*ev);

    // Reasons
    const reasons = [];
    if(urg >= 0.8) reasons.push('Pathway is currently fully blocked (high urgency).');
    else if(urg >= 0.6) reasons.push('Pathway is partially blocked (moderate urgency).');
    if(sev >= 0.75) reasons.push('Encroachment is severe (e.g., permanent structure, fence, gate, or store).');
    if(imp >= 0.5) reasons.push('Significant impact on mobility or safety was reported.');
    if(soc >= 0.5) reasons.push('Multiple residents or barangay involvement suggests mediation value.');
    if(res11.provide_docs) reasons.push('Authorities requested more documents — assessment recommended.');
    if(type1.utilities_path) reasons.push('Pathway is used for utilities; verification/assessment may be necessary.');
    if(externalAgency) reasons.push('External agencies (NGC/USAD) are involved.');
    if(type1.public_sidewalk) reasons.push('Public sidewalk involvement may require barangay action.');
    if(confidence < 0.5) reasons.push('Signals are mixed; consider collecting more evidence.');

    return { action: bestK, confidence, scores: norm, reasons };
  }

  // --- Extract answers from injected Pathway Dispute preview/form ---
  function extractAnswers(root){
    const qVal = name => {
      const group = root.querySelectorAll(`input[name="${name}"]`);
      if(!group.length){
        // Try single radio by name with checked attribute preserved
        const any = root.querySelector(`input[name="${name}"][checked]`);
        return any ? any.value : '';
      }
      const checked = Array.from(group).find(i => i.checked);
      return checked ? checked.value : '';
    };
    const qArr = name => Array.from(root.querySelectorAll(`input[name="${name}"]`)).filter(i => i.checked).map(i => i.value);

    // Map Pathway Dispute names
    const answers = {
      q1: qVal('q1'),            // type of pathway (radio)
      q2: qVal('q2'),            // nature (radio)
      q3: qVal('q3'),            // duration (radio)
      q4: qVal('q4'),            // obstruction still present (radio)
      q5: qArr('q5'),            // impacts (checkboxes)
      q6: qVal('q6'),            // others concerned (radio)
      q7: qVal('q7'),            // informed/warned (radio)
      q8: qArr('q8'),            // led to any issues (checkboxes)
      q9: qArr('q9'),            // reported to authority (checkboxes)
      q10: qVal('q10'),          // inspection conducted (radio)
      q11: qArr('q11'),          // result (checkboxes)
      q12: qVal('q12'),          // ongoing development (radio)
      description: (root.querySelector('textarea[name="description"]') || {}).value || ''
    };
    // cache for downstream narrative rendering
    __lastAnswers = answers;
    return answers;
  }

  // --- Stylish UI helpers ---
  const ACTION_LABEL = {
    inspection: 'Inspection',
    mediation: 'Send Invitation',
    assessment: 'Assessment',
    out_of_jurisdiction: 'Out of Jurisdiction'
  };

  const ACTION_COLOR = {
    inspection: '#1a33a0',
    mediation: '#0b8b6a',
    assessment: '#8751b8',
    out_of_jurisdiction: '#a03b2b'
  };

  function confidenceLabel(c){
    const v = clamp01(c);
    if(v >= 0.75) return {label: 'High confidence', color: '#0b8b6a'};
    if(v >= 0.5) return {label: 'Moderate confidence', color: '#e6a100'};
    return {label: 'Low confidence', color: '#a03b2b'};
  }

  function renderScoreBars(scores, primary){
    const keys = ['inspection','mediation','assessment','out_of_jurisdiction'];
    const rows = keys.map(k => {
      const p = Math.round(clamp01(scores[k]||0)*100);
      const color = ACTION_COLOR[k] || '#1f2a4a';
      const isBest = k === primary;
      return `
        <div style="display:flex; align-items:center; gap:8px; margin:6px 0;">
          <div style="width:140px; font-weight:${isBest?'700':'500'}; color:${isBest?color:'#1f2a4a'};">${ACTION_LABEL[k]||titleCase(k)}</div>
          <div style="flex:1; background:#eef2ff; border-radius:999px; height:10px; overflow:hidden;">
            <div style="width:${p}%; height:100%; background:${color}; opacity:${isBest?1:0.6}"></div>
          </div>
          <div style="width:42px; text-align:right; color:${isBest?color:'#51607a'}; font-weight:${isBest?700:500}">${p}%</div>
        </div>`;
    }).join('');
    return `<div style="margin-top:10px;">${rows}</div>`;
  }

  function buildNarrative(answers, result){
    const actionKey = result.action;
    const action = ACTION_LABEL[actionKey] || titleCase(actionKey);
    const confPct = pct(result.confidence);
    const conf = confidenceLabel(result.confidence).label.toLowerCase();

    const bits = [];
    bits.push(`Recommended action: ${action} (${confPct}% ${conf}).`);

    // Contextualize using answers
    const details = [];
    if((answers.q4||'').toLowerCase().includes('fully')) details.push('pathway reportedly fully blocked');
    else if((answers.q4||'').toLowerCase().includes('partial')) details.push('pathway partially obstructed');
    if(/fence|gate|store|business/i.test(answers.q2||'')) details.push('encroachment involves a structure (e.g., fence/gate/store)');
    if((answers.q6||'').toLowerCase()==='yes') details.push('other residents are concerned');
    if(/barangay|hoa/i.test(answers.q7||'')) details.push('matter already raised to local authorities');
    if((answers.q1||'').toLowerCase().includes('government')) details.push('possible government-declared easement/right-of-way');
    if((answers.q12||'').toLowerCase().includes('yes')) details.push('ongoing development in the area');
    if((answers.description||'').trim().length>0) details.push('complaint description provided');
    if(details.length){ bits.push(`Signals considered: ${details.join('; ')}.`); }

    // Rationale
    const reasons = (result.reasons||[]).slice(0,4);
    if(reasons.length){ bits.push(`Why this: ${reasons.join(' ')}.`); }

    // Next steps guidance per action
    const next = [];
    switch(actionKey){
      case 'inspection':
        next.push('Schedule a site visit within 3–5 days.');
        next.push('Capture photos/videos and exact location.');
        next.push('Coordinate with barangay/HOA as needed.');
        break;
      case 'mediation':
        next.push('Invite involved parties to an on-site meeting.');
        next.push('Agree on interim access (e.g., partial clearance).');
        next.push('Document commitments and a follow-up window.');
        break;
      case 'assessment':
        next.push('Request supporting documents (permits, plans, IDs).');
        next.push('Check easement/right-of-way policies for applicability.');
        next.push('Decide whether to escalate to inspection or mediation.');
        break;
      default: // out_of_jurisdiction
        next.push('Prepare a referral letter to the proper authority (e.g., NGC/USAD/Barangay).');
        next.push('Inform complainant about scope and expected timeline.');
        next.push('Attach any collected evidence for continuity.');
        break;
    }
    bits.push(`Next steps: ${next.join(' ')}.`);

    // If confidence moderate/low, encourage evidence
    if(result.confidence < 0.75){
      bits.push('Note: Confidence is not maximal. Additional photos, specific dates, and any received notices can improve the recommendation.');
    }

    return bits.join('\n\n');
  }

  function renderRecommendation(result, answers){
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
      const primary = result.action;
      const action = ACTION_LABEL[primary] || titleCase(primary);
      // Display the top action's score percent to avoid confusion with a different confidence metric
      const primaryScore = clamp01(((result.scores||{})[primary]) || 0);
      const displayPct = pct(primaryScore);
      const confMeta = confidenceLabel(primaryScore);
      const reasons = (result.reasons||[]).slice(0,4).map(r=>`<li>${r}</li>`).join('');

      const header = `
        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; border-bottom: 2px solid #1a33a0; padding-bottom: 4px">
          <div style="font-weight:800; color:#1a33a0; display:flex; align-items:center; gap:10px;">
            <span class="material-icons" style="font-size:18px; color:#1a33a0;">psychology</span>
            System Recommendation
          </div>
          <div style="display:flex; align-items:center; gap:10px;">
            <span style="padding:4px 10px; border-radius:999px; background:${ACTION_COLOR[primary]||'#1a33a0'}10; color:${ACTION_COLOR[primary]||'#1a33a0'}; font-weight:700;">${action}</span>
            <span style="padding:4px 10px; border-radius:999px; background:${confMeta.color}10; color:${confMeta.color}; font-weight:700;">${displayPct}%</span>
          </div>
        </div>`;

      const bars = renderScoreBars(result.scores||{}, primary);

      const why = `
        <div style="margin-top:8px; color:#1f2a4a;">Why this</div>
        <ul style="margin:6px 0 0 18px; color: black;">${reasons || '<li>Signals are mixed; additional details may improve accuracy.</li>'}</ul>`;

      box.innerHTML = header + bars + why;

      // Try to fill the narrative textarea below
      const ans = answers || __lastAnswers || {};
      const narrative = buildNarrative(ans, result);
      const textarea = document.getElementById('recommendText');
      if(textarea){ textarea.value = narrative; }
    } catch (e) {
      // graceful fallback text
      box.innerHTML = '<div style="font-weight:700; color:#a03b2b;">Unable to render detailed recommendation UI.</div>';
    }
  }

  // expose
  window.PathwayFuzzy = {
    extractAnswers,
    computeRecommendation,
    renderRecommendation,
    // also expose helpers for advanced callers
    _buildNarrative: buildNarrative
  };
})();
