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
  });
})();
