// Dispatcher to unify fuzzy modules and render into the recommendation modal
(function(){
  function tryRender(){
    const modal = document.getElementById('recommendModal');
    if(!modal) return false;

    // Detect complaint type by probing for distinctive fields
  const root = document.querySelector('.complaint-form') || document;

    // Pathway has radio/checkbox names q1..q12, Lot has distinctive labels in .field-blocks
    const hasPathwaySignals = !!(root.querySelector('input[name="q1"], input[name="q2"], input[name="q3"], input[name="q4"]'));
    const hasLotSignals = (function(){
      // Probe for distinctive labels in field-blocks regardless of wrapper
      const scope = document.querySelector('.complaint-form') || document;
      const blocks = Array.from(scope.querySelectorAll('.field-block p'));
      return blocks.some(p => /How did you come into possession|nature of the ownership conflict|Do they reside on the disputed lot|legal documents/i.test((p.textContent||'')));
    })();
    // Unauthorized Occupation: detect by presence of its unique field names OR label text in preview blocks
    const hasUnauthorizedByName = !!(root.querySelector('input[name="legal_connection"], input[name="occupant_claim"], input[name="result"], input[name="boundary_reported_to[]"]'));
    const hasUnauthorizedByLabel = (function(){
      const scope = document.querySelector('.complaint-form') || document;
      const nodes = Array.from(scope.querySelectorAll('p, label, h1, h2, h3, h4, div'));
      return nodes.some(el => /What is your legal connection|What activities are being done on the property|Have they claimed legal rights|Have you tried to resolve this directly|Have you reported this boundary issue|What was the result of that report/i.test((el.textContent||'')));
    })();
    const hasUnauthorizedSignals = hasUnauthorizedByName || hasUnauthorizedByLabel;

    try {
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
