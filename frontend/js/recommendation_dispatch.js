// Dispatcher to unify fuzzy modules and render into the recommendation modal
(function(){
  function tryRender(){
    const modal = document.getElementById('recommendModal');
    if(!modal) return false;

    // Detect complaint type by probing for distinctive fields
  const root = document.querySelector('.complaint-form') || document;

    // Pathway detection: look for pathway-specific labels (avoid generic q1.. names shared by other forms)
    const hasPathwaySignals = (function(){
      const scope = document.querySelector('.complaint-form') || document;
      const nodes = Array.from(scope.querySelectorAll('p, label, legend, h1, h2, h3'));
      return nodes.some(el => /pathway|sidewalk|alley|right[- ]of[- ]way|easement/i.test((el.textContent||'')));
    })();
    const hasLotSignals = (function(){
      // Probe for distinctive labels in field-blocks regardless of wrapper
      const scope = document.querySelector('.complaint-form') || document;
      const blocks = Array.from(scope.querySelectorAll('.field-block p'));
      return blocks.some(p => /How did you come into possession|nature of the ownership conflict|Do they reside on the disputed lot|legal documents/i.test((p.textContent||'')));
    })();
    // Boundary Dispute: detect via distinctive boundary labels present in form/preview
    const hasBoundarySignals = (function(){
      // Strong signal: hidden marker injected by boundary preview partial
      if (document.getElementById('__boundary_form_marker')) return true;
      const scope = document.querySelector('.complaint-form') || document;
      const nodes = Array.from(scope.querySelectorAll('p, label, legend, h1, h2, h3'));
      return nodes.some(el => /nature of the boundary issue|boundary markers|How long has this encroachment existed|encroaching structure|site inspection|mohon|marker/i.test((el.textContent||'')));
    })();
    // Unauthorized Occupation: detect by presence of its unique field names OR label text in preview blocks
    const hasUnauthorizedByName = !!(root.querySelector('input[name="legal_connection"], input[name="occupant_claim"], input[name="result"], input[name="boundary_reported_to[]"]'));
    const hasUnauthorizedByLabel = (function(){
      const scope = document.querySelector('.complaint-form') || document;
      const nodes = Array.from(scope.querySelectorAll('p, label, h1, h2, h3, h4, div'));
      // Keep Unauthorized detection specific to its unique prompts; avoid boundary-shared phrases
      return nodes.some(el => /What is your legal connection|What activities are being done on the property|Have they claimed legal rights|Have you tried to resolve this directly/i.test((el.textContent||'')));
    })();
    const hasUnauthorizedSignals = hasUnauthorizedByName || hasUnauthorizedByLabel;

    try {
      // Prefer Boundary before Pathway to avoid overlap
      if (hasBoundarySignals && window.BoundaryFuzzy) {
        const computed = window.BoundaryFuzzy.computeRecommendation();
        window.BoundaryFuzzy.renderRecommendation(computed);
        // Also expose suggest dataset for downstream selects (module also sets these internally)
        const recData = modal.dataset;
        const primary = computed && computed.choice ? computed.choice.primaryAction : '';
        recData.suggestAssign = (primary === 'Inspection' || primary === 'Invitation') ? primary : '';
        recData.suggestAction = (primary === 'Assessment' || primary === 'Out of Jurisdiction') ? primary : '';
        return true;
      }
      if (hasPathwaySignals && window.PathwayFuzzy) {
        const previewRoot = document.querySelector('.complaint-form') || document;
        const answers = window.PathwayFuzzy.extractAnswers(previewRoot);
        const result = window.PathwayFuzzy.computeRecommendation(answers);
        window.PathwayFuzzy.renderRecommendation(result, answers);
        // Set suggest dataset for downstream preselects (align to existing keys)
        const recData = modal.dataset;
        const actionKey = result.action;
        // Map to Assign vs Action suggestions
        recData.suggestAssign = (actionKey === 'inspection' || actionKey === 'mediation') ? (actionKey === 'inspection' ? 'Inspection' : 'Invitation') : '';
        recData.suggestAction = (actionKey === 'assessment' || actionKey === 'out_of_jurisdiction') ? (actionKey === 'assessment' ? 'Assessment' : 'Out of Jurisdiction') : '';
        return true;
      }
      if (hasLotSignals && window.LotFuzzy) {
        const computed = window.LotFuzzy.computeRecommendation();
        window.LotFuzzy.renderRecommendation(computed);
        return true;
      }
      if (hasUnauthorizedSignals && window.UnauthorizedFuzzy) {
        const computed = window.UnauthorizedFuzzy.computeRecommendation();
        window.UnauthorizedFuzzy.renderRecommendation(computed);
        // Set suggest dataset similar to other flows
        const recData = modal.dataset;
        const primary = computed && computed.choice ? computed.choice.primaryAction : '';
        recData.suggestAssign = (primary === 'Inspection' || primary === 'Invitation') ? primary : '';
        recData.suggestAction = (primary === 'Assessment' || primary === 'Out of Jurisdiction') ? primary : '';
        return true;
      }
    } catch(e){ console.warn('Recommendation dispatcher error:', e); }
    return false;
  }

  // Bounded retry to wait for preview injection without heavy observers
  function runWithRetry(attempt){
    if (tryRender()) return;
    const a = (typeof attempt === 'number') ? attempt : 0;
    if (a < 50) {
      setTimeout(() => runWithRetry(a+1), 100);
    }
  }

  // Expose a hook the page already tries to call
  window.runFuzzyRecommendation = function(){ try { runWithRetry(0); } catch(e){} };

  // Also auto-run when DOM is ready and preview injected
  document.addEventListener('DOMContentLoaded', function(){
    setTimeout(() => runWithRetry(0), 0);

    // When the Recommend modal is opened later, re-attempt rendering
    const recModal = document.getElementById('recommendModal');
    try {
      if (recModal && window.MutationObserver){
        let retried = false;
        const obs = new MutationObserver(() => {
          const visible = recModal.style && recModal.style.display && recModal.style.display !== 'none';
          if (visible && !retried){
            retried = true;
            // Bounded retry after open (up to ~3s)
            let attempts = 0;
            (function kick(){
              if (tryRender()) return;
              if (++attempts < 30) setTimeout(kick, 100);
            })();
          }
        });
        obs.observe(recModal, { attributes: true, attributeFilter: ['style', 'class'] });
      }
    } catch(e) { /* non-fatal */ }
  });
})();
