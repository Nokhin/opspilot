const examples = {
  policy: 'A Severity 1 digital-service outage has lasted 35 minutes. According to internal policy, who must be notified and within what timeframe?',
  data: 'How many payment-service incidents occurred in the last six months, and what was the median downtime?',
  mixed: 'A customer-facing payment service has been down for 45 minutes and affects more than 500 users. What escalation does policy require, and how does this duration compare with similar incidents over the last year?',
  refusal: 'What exact cash compensation must every affected customer receive?'
};
const byId = (id) => document.getElementById(id);
function node(tag, content, className = '') {
  const element = document.createElement(tag);
  element.textContent = content;
  element.className = className;
  return element;
}
function render(response) {
  byId('facts').replaceChildren();
  if (response.confidence === 'insufficient_evidence') {
    byId('facts').append(node('p', response.route === 'unsupported' ?
      'This request is outside read-only incident investigation. No business action was executed.' :
      'Insufficient evidence for part or all of this request. Supported findings are shown below.', 'notice'));
  }
  const kinds = {policy_requirement: 'POLICY REQUIREMENT', historical_fact: 'HISTORICAL FACT', interpretation: 'INTERPRETATION'};
  for (const fact of response.facts) {
    const card = node('article', '', 'fact ' + fact.kind);
    card.append(node('h3', kinds[fact.kind]), node('p', fact.text));
    for (const id of fact.evidence_ids) {
      const ref = response.evidence.find((item) => item.evidence_id === id);
      const link = node('a', ref ? ref.title + ' · ' + ref.section : id, 'citation');
      link.href = '#source-' + encodeURIComponent(id);
      card.append(link);
    }
    byId('facts').append(card);
  }
  byId('sources').replaceChildren();
  byId('sources').className = '';
  for (const ref of response.evidence) {
    const detail = node('details', '', 'source');
    detail.id = 'source-' + encodeURIComponent(ref.evidence_id);
    const summary = node('summary', '');
    summary.append(node('span', ref.source_type === 'internal_policy' ? 'INTERNAL POLICY' : 'INCIDENT DATABASE', 'source-type'), node('strong', ref.title), node('span', ref.section, 'muted'));
    detail.append(summary, node('p', ref.excerpt, 'excerpt'), node('p', ref.chunk_id || ref.evidence_id, 'source-id'));
    if (ref.version) detail.append(node('p', 'Version ' + ref.version + ' · Effective ' + ref.effective_date, 'muted'));
    byId('sources').append(detail);
  }
  if (!response.evidence.length) byId('sources').append(node('p', 'No supporting evidence was used.', 'empty'));
  byId('source-count').textContent = response.evidence.length + ' references';
  byId('trace').replaceChildren();
  for (const trace of response.tool_trace) {
    const detail = node('details', '', 'tool');
    detail.append(node('summary', trace.tool_name + ' · ' + trace.status), node('p', trace.summary), node('pre', JSON.stringify(trace.arguments, null, 2)));
    byId('trace').append(detail);
  }
  if (!response.tool_trace.length) byId('trace').append(node('p', 'No tools were executed.', 'empty'));
  const list = byId('limitations').querySelector('ul');
  list.replaceChildren(...response.limitations.map((text) => node('li', text)));
  byId('outcome').textContent = response.route.replaceAll('_', ' ') + ' · ' + response.evidence_sufficiency;
  byId('raw-response').textContent = JSON.stringify(response, null, 2);
  byId('request-meta').textContent = response.mode + ' mode · ' + Math.round(response.latency_ms) + ' ms · Request ' + response.request_id;
  byId('answer').hidden = false;
}
byId('question-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  byId('submit').disabled = true;
  byId('answer').hidden = true;
  byId('answer-state').textContent = 'Retrieving evidence and calculating incident facts…';
  try {
    const result = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: byId('question').value.trim()})
    });
    const response = await result.json();
    if (!result.ok) throw new Error(typeof response.detail === 'string' ? response.detail : 'Please check the question and try again.');
    render(response);
    byId('answer-state').textContent = '';
  } catch (error) {
    byId('answer-state').textContent = error.message;
  } finally { byId('submit').disabled = false; }
});
document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => {
  byId('question').value = examples[button.dataset.example];
  byId('question').focus();
}));
Promise.all([fetch('/api/health'), fetch('/api/ready')]).then(async ([health, ready]) => {
  const status = await health.json();
  byId('health').textContent = ready.ok ? 'Evidence ready · ' + status.mode + ' mode' : 'Evidence unavailable · run bootstrap';
}).catch(() => { byId('health').textContent = 'API unavailable'; });
