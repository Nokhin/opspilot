const examples = {
  policy: 'A Severity 1 digital-service outage has lasted 35 minutes. According to internal policy, who must be notified and within what timeframe?',
  data: 'How many payment-service incidents occurred in the last six months, and what was the median downtime?',
  mixed: 'A customer-facing payment service has been down for 45 minutes and affects more than 500 users. What escalation does policy require, and how does this duration compare with similar incidents over the last year?',
  refusal: 'What exact cash compensation must every affected customer receive?'
};
const byId = (id) => document.getElementById(id);
let investigationPending = false;
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
      'This request could not be completed. No business action was executed. See limitations for scope or provider errors.' :
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
  byId('limitations').open = response.mode === 'chatgpt_subscription' && response.confidence === 'insufficient_evidence';
  list.replaceChildren(...response.limitations.map((text) => node('li', text)));
  byId('outcome').textContent = response.route.replaceAll('_', ' ') + ' · ' + response.evidence_sufficiency;
  byId('raw-response').textContent = JSON.stringify(response, null, 2);
  byId('request-meta').textContent = response.mode + (response.model ? ' · ' + response.model : '') + ' · ' + Math.round(response.latency_ms) + ' ms · Request ' + response.request_id;
  byId('answer').hidden = false;
}
byId('question-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  investigationPending = true;
  byId('submit').disabled = true;
  byId('answer').hidden = true;
  byId('answer-state').textContent = 'Retrieving evidence and calculating incident facts…';
  try {
    if (byId('workflow-mode').value === 'investigation') {
      await createInvestigation();
      return;
    }
    byId('investigation-brief').hidden = true;
    byId('human-input').hidden = true;
    const result = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: byId('question').value.trim(), provider: byId('provider-choice').value})
    });
    const response = await result.json();
    if (!result.ok) throw new Error(typeof response.detail === 'string' ? response.detail : 'Please check the question and try again.');
    render(response);
    byId('answer-state').textContent = '';
  } catch (error) {
    byId('answer-state').textContent = error.message;
  } finally { investigationPending = false; syncComposer(); }
});
document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => {
  byId('question').value = examples[button.dataset.example];
  byId('question').focus();
}));
Promise.all([fetch('/api/health'), fetch('/api/ready')]).then(async ([health, ready]) => {
  const status = await health.json();
  byId('health').textContent = ready.ok ? 'Evidence ready · default: ' + status.mode : 'Evidence unavailable · run bootstrap';
  byId('provider-choice').options[0].textContent = 'Configured baseline (' + (status.configured_mode || status.mode) + ')';
}).catch(() => { byId('health').textContent = 'API unavailable'; });

let subscription = {active: null, profiles: []};
let modelReady = false;
function syncComposer() {
  const selected = byId('workflow-mode').value === 'chat' ? byId('provider-choice').value : byId('investigation-mode').value;
  byId('submit').disabled = investigationPending || (selected === 'chatgpt_subscription' && !modelReady);
}
function syncProviderControls() {
  const v2 = byId('workflow-mode').value === 'investigation';
  byId('provider-choice').hidden = v2;
  document.querySelector('label[for="provider-choice"]').hidden = v2;
  byId('provider-controls').hidden = !subscription.enabled || (v2 && byId('investigation-mode').value !== 'chatgpt_subscription');
  byId('subscription-controls').hidden = (v2 ? byId('investigation-mode').value : byId('provider-choice').value) !== 'chatgpt_subscription';
  syncComposer();
}
async function subscriptionAPI(path, body) {
  const result = await fetch('/api/chatgpt/' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const response = await result.json();
  if (!result.ok) throw new Error(typeof response.detail === 'string' ? response.detail : 'ChatGPT connection failed. Please reconnect.');
  return response;
}
function subscriptionMessage(text) { byId('subscription-state').textContent = text; }
async function loadSubscription() {
  modelReady = false;
  syncComposer();
  subscription = await subscriptionAPI('status');
  byId('investigation-mode').querySelector('[value="chatgpt_subscription"]').disabled = !subscription.enabled;
  syncProviderControls();
  if (!subscription.enabled) return;
  byId('provider-controls').hidden = false;
  const remembered = sessionStorage.getItem('opspilot_provider');
  byId('provider-choice').value = ['configured', 'chatgpt_subscription'].includes(remembered) ? remembered : (subscription.default_provider || 'configured');
  syncProviderControls();
  const selector = byId('chatgpt-account');
  selector.replaceChildren(node('option', 'Select an account'));
  selector.firstChild.value = '';
  for (const profile of subscription.profiles) {
    const option = node('option', profile.label + ' · ' + profile.registration);
    option.value = profile.id;
    selector.append(option);
  }
  selector.value = subscription.active || '';
  const profile = subscription.profiles.find(p => p.id === subscription.active);
  byId('chatgpt-logout').disabled = !profile?.connected;
  if (profile?.connected && profile.plan_enabled) {
    if (!profile.welcome_acknowledged && !byId('chatgpt-welcome').open) byId('chatgpt-welcome').showModal();
    await loadModels();
  } else {
    byId('chatgpt-model').replaceChildren(node('option', 'Sign in and allow ChatGPT plan usage'));
    byId('chatgpt-model').firstChild.value = '';
    subscriptionMessage(profile?.connected ? 'Reconnect and enable ChatGPT plan usage to continue.' : 'Continue with ChatGPT to load your available models.');
  }
  syncComposer();
}
async function loadModels() {
  modelReady = false;
  syncComposer();
  const profile = subscription.profiles.find(p => p.id === subscription.active);
  const result = await subscriptionAPI('models');
  const selector = byId('chatgpt-model');
  selector.replaceChildren(node('option', 'Choose an available model'));
  selector.firstChild.value = '';
  for (const model of result.models) {
    const option = node('option', model.name);
    option.value = model.id;
    selector.append(option);
  }
  selector.value = result.models.some(m => m.id === profile?.model) ? profile.model : '';
  modelReady = Boolean(selector.value);
  subscriptionMessage(result.models.length ? 'Using ChatGPT plan · Choose a model, then investigate.' : 'No models are available for this account.');
  syncComposer();
}
async function subscriptionAction(action) {
  try { await action(); }
  catch (error) { modelReady = false; subscriptionMessage(error.message); syncComposer(); }
}
byId('provider-choice').addEventListener('change', () => {
  sessionStorage.setItem('opspilot_provider', byId('provider-choice').value);
  syncProviderControls();
});
byId('chatgpt-login').addEventListener('click', () => subscriptionAction(async () => {
  sessionStorage.setItem('opspilot_provider', 'chatgpt_subscription');
  const result = await subscriptionAPI('login', {profile_id: subscription.active || null});
  window.location.assign(result.authorization_url);
}));
byId('chatgpt-add').addEventListener('click', () => subscriptionAction(async () => {
  sessionStorage.setItem('opspilot_provider', 'chatgpt_subscription');
  const result = await subscriptionAPI('login', {});
  window.location.assign(result.authorization_url);
}));
byId('chatgpt-account').addEventListener('change', () => subscriptionAction(async () => {
  modelReady = false; syncComposer();
  await subscriptionAPI('account', {profile_id: byId('chatgpt-account').value});
  await loadSubscription();
}));
byId('chatgpt-model').addEventListener('change', () => subscriptionAction(async () => {
  modelReady = false; syncComposer();
  await subscriptionAPI('model', {model: byId('chatgpt-model').value});
  modelReady = true; syncComposer();
  subscriptionMessage('Using ChatGPT plan · ' + byId('chatgpt-model').selectedOptions[0].textContent);
}));
byId('chatgpt-refresh').addEventListener('click', () => subscriptionAction(loadSubscription));
byId('chatgpt-logout').addEventListener('click', () => subscriptionAction(async () => {
  const result = await subscriptionAPI('logout', {});
  modelReady = false;
  await loadSubscription();
  if (!result.remote_revocation_confirmed) subscriptionMessage('Signed out locally. Remote revocation was not confirmed; disconnect OpsPilot in ChatGPT Settings → Security and login.');
}));
byId('chatgpt-welcome-ok').addEventListener('click', () => subscriptionAction(async () => {
  await subscriptionAPI('welcome', {});
  byId('chatgpt-welcome').close();
}));
byId('chatgpt-welcome').addEventListener('cancel', () => subscriptionAction(async () => {
  await subscriptionAPI('welcome', {});
}));
subscriptionAction(loadSubscription);


// V2 capability tokens stay in this browser tab, never in URLs or displayed JSON.
let activeInvestigation = null;
function rememberInvestigation(value) {
  activeInvestigation = value;
  sessionStorage.setItem('opspilot_investigation', JSON.stringify(value));
  byId('restore-investigation').hidden = false;
}
async function investigationAPI(path, body, token) {
  const headers = {'Content-Type': 'application/json'};
  if (token) headers.Authorization = 'Bearer ' + token;
  const result = await fetch('/api/investigations' + path, {
    method: body === undefined ? 'GET' : 'POST', headers,
    ...(body === undefined ? {} : {body: JSON.stringify(body)})
  });
  const response = await result.json();
  if (!result.ok) throw new Error(typeof response.detail === 'string' ? response.detail : 'Investigation request was rejected.');
  return response;
}
function renderInvestigation(response) {
  const brief = response.investigation_brief;
  const pending = response.clarification_request;
  const facts = brief?.key_findings || pending?.findings || [];
  const evidence = brief?.source_citations || pending?.sources || [];
  const gaps = brief?.evidence_gaps || response.verification_result?.gaps || [];
  const limits = brief?.limitations || ['Fictional synthetic data. All business tools are read-only.'];
  render({
    facts, evidence, limitations: limits, route: response.route,
    confidence: ['completed', 'awaiting_human'].includes(response.completion_status) ? 'medium' : 'insufficient_evidence',
    evidence_sufficiency: response.completion_status, tool_trace: response.tool_traces,
    mode: response.mode, model: response.model, latency_ms: response.latency_ms, request_id: response.investigation_id
  });
  if (pending?.kind === 'clarify') byId('outcome').textContent = 'Awaiting clarification';
  for (const card of byId('facts').querySelectorAll('.policy_requirement')) {
    const text = card.querySelector('p');
    const detail = node('details', '');
    detail.append(node('summary', 'Read cited policy requirement'), text);
    card.append(detail);
  }
  const area = byId('investigation-brief');
  area.replaceChildren(node('h3', 'INVESTIGATION BRIEF'), node('p', brief?.executive_summary || (pending ? 'Investigation paused for human input.' : response.error || 'Investigation in progress.')));
  if (brief || pending?.kind === 'review') {
    let contextText = brief?.incident_context_and_severity || 'Review the cited incident facts and proposed actions below.';
    const start = contextText.indexOf('{');
    if (start >= 0) {
      try {
        const context = JSON.parse(contextText.slice(start));
        contextText = [context.incident_id || 'Supplied incident', context.category?.replaceAll('_', ' '),
          context.severity ? 'Recorded/reported severity: ' + context.severity : null,
          context.downtime_minutes !== undefined ? 'Downtime: ' + context.downtime_minutes + ' minutes' : null,
          context.customer_impact_count !== undefined ? 'Customer-impact exposures: ' + context.customer_impact_count : null,
          context.source === 'incident_snapshot' ? 'Source: synthetic incident snapshot' : 'Source: user-reported context'
        ].filter(Boolean).join(' · ');
      } catch (_) { /* Preserve the server-supplied context if it is not JSON. */ }
    }
    area.append(node('h3', 'Incident context and severity'), node('p', contextText));
    area.append(node('h3', 'Proposed next steps'));
    const actions = node('ul', '');
    const proposed = brief?.recommended_next_steps || pending?.proposed_actions || [];
    for (const item of proposed) {
      const row = node('li', item.text);
      row.append(node('p', 'Owner role: ' + item.owner_role + ' · Trigger: ' + item.trigger, 'muted'));
      if (item.deadline_minutes !== null) row.append(node('p', 'Relative timing: ' + item.deadline_minutes + ' minutes from ' + item.deadline_basis, 'muted'));
      if (item.due_at) row.append(node('p', 'Evidence-based deadline: ' + item.due_at, 'muted'));
      for (const id of item.evidence_ids) {
        const ref = evidence.find(e => e.evidence_id === id);
        const link = node('a', ref ? ref.title + ' · ' + ref.section : id, 'citation');
        link.href = '#source-' + encodeURIComponent(id); row.append(link);
      }
      actions.append(row);
    }
    if (!proposed.length) actions.append(node('li', 'No evidence-backed operational action proposed.'));
    area.append(actions);
  }
  const assessment = response.severity_assessment || pending?.severity_assessment;
  if (assessment && assessment.status !== 'not_requested') {
    const box = node('section', '', 'severity-assessment');
    box.append(node('h3', 'Severity assessment'), node('p', 'Recorded: ' + (assessment.recorded_severity || 'Not available') + ' · Reported: ' + (assessment.reported_severity || 'Not supplied') + ' · Proposed: ' + (assessment.proposed_severity || 'Insufficient evidence') + ' (' + assessment.status + ')'));
    const basis = node('ul', '');
    for (const text of assessment.basis) basis.append(node('li', text));
    box.append(basis);
    if (assessment.missing_fields.length) box.append(node('p', 'Unknown: ' + assessment.missing_fields.map(f => f.replaceAll('_', ' ')).join(', '), 'notice'));
    for (const id of assessment.evidence_ids) {
      const ref = evidence.find(e => e.evidence_id === id);
      const link = node('a', ref ? ref.title + ' · ' + ref.section : id, 'citation');
      link.href = '#source-' + encodeURIComponent(id); box.append(link);
    }
    area.append(box);
  }
  if (response.verification_result?.dimension_coverage?.length) {
    const detail = node('details', ''); detail.append(node('summary', 'Requested evidence dimensions'));
    const list = node('ul', '');
    for (const dimension of response.verification_result.dimension_coverage) list.append(node('li', dimension.dimension_id.replaceAll('_', ' ') + ' · ' + dimension.status));
    detail.append(list); area.append(detail);
  }
  if (gaps.length) {
    area.append(node('h3', 'Evidence gaps / uncertainties'));
    const list = node('ul', '');
    for (const gap of gaps) list.append(node('li', gap.description));
    area.append(list);
  }
  const workflow = node('details', '');
  workflow.append(node('summary', 'Workflow trace'), node('p', response.workflow_trace.join(' → '), 'workflow-trace'));
  area.append(workflow);
  area.append(node('p', 'Corrective retrieval: ' + response.retry_count + '/1 · Human review: ' + response.human_review_status, 'muted'));
  area.append(node('p', 'Planning calls: ' + response.provider_call_count + '/1 · Input/output tokens: ' + response.usage.input_tokens + '/' + response.usage.output_tokens + (response.usage_complete ? '' : ' · Usage may be incomplete'), 'muted'));
  area.hidden = false;
  byId('human-input').hidden = !pending;
  byId('human-message').textContent = pending?.message || '';
  byId('clarification-form').hidden = pending?.kind !== 'clarify';
  byId('review-actions').hidden = pending?.kind !== 'review';
  if (pending?.kind === 'clarify') renderClarification(pending);
  const {owner_token, ...safeResponse} = response;
  byId('raw-response').textContent = JSON.stringify(safeResponse, null, 2);
  byId('answer-state').textContent = '';
}
async function createInvestigation() {
  const response = await investigationAPI('', {
    user_request: byId('question').value.trim(),
    require_review: byId('require-review').checked,
    mode: byId('investigation-mode').value
  });
  rememberInvestigation({id: response.investigation_id, token: response.owner_token});
  renderInvestigation(response);
}
async function resumeInvestigation(payload) {
  if (!activeInvestigation || investigationPending) return;
  investigationPending = true;
  syncComposer();
  for (const id of ['clarify-submit', 'review-accept', 'review-decline']) byId(id).disabled = true;
  byId('answer-state').textContent = 'Resuming the saved investigation…';
  try {
    const response = await investigationAPI('/' + activeInvestigation.id + '/resume', payload, activeInvestigation.token);
    renderInvestigation(response);
  } catch (error) { byId('answer-state').textContent = error.message; byId('clarification-error').textContent = error.message; }
  finally {
    investigationPending = false;
    for (const id of ['clarify-submit', 'review-accept', 'review-decline']) byId(id).disabled = false;
    syncComposer();
  }
}
byId('workflow-mode').addEventListener('change', () => {
  byId('v2-options').hidden = byId('workflow-mode').value !== 'investigation';
  syncProviderControls();
});
byId('investigation-mode').addEventListener('change', syncProviderControls);
const fieldLabels = {
  incident_id: 'Incident ID', category: 'Incident category', severity: 'Reported severity',
  downtime_minutes: 'Continuous downtime (minutes)', customer_impact_count: 'Affected customers',
  customer_facing: 'Customer-facing service', immediate_danger: 'Immediate danger to people',
  multi_site_essential_closure: 'Multi-site essential-service closure', single_site_disruption: 'Single-site disruption',
  duplicate_capture_confirmed: 'Confirmed duplicate capture', workaround_available: 'Safe workaround available',
  integrity_concern: 'Safety or financial-integrity concern', no_customer_interruption: 'No current customer interruption',
  local_degradation: 'Local degradation', minor_operational_defect: 'Minor operational defect',
  threshold_detected_at: 'Threshold detection time (with timezone)'
};
let clarificationFields = [];
function validateClarification(input, field) {
  let message = '';
  if (field === 'threshold_detected_at' && input.value && (!/(Z|[+-]\d{2}:\d{2})$/.test(input.value) || Number.isNaN(Date.parse(input.value)))) message = 'Use an ISO 8601 time with Z or an explicit UTC offset.';
  if (['downtime_minutes', 'customer_impact_count'].includes(field) && input.value && (!Number.isSafeInteger(Number(input.value)) || !input.checkValidity())) message = 'Enter a whole number within the displayed range, or leave unknown.';
  if (field === 'incident_id' && input.value && !/^INC-[0-9]{3}$/.test(input.value)) message = 'Use an incident ID such as INC-001, or leave unknown.';
  input.setCustomValidity(message);
  input.setAttribute('aria-invalid', String(Boolean(message)));
  byId(input.id + '-error').textContent = message;
  return !message;
}
function renderClarification(pending) {
  clarificationFields = pending.accepted_fields;
  const area = byId('clarification-fields'); area.replaceChildren();
  byId('clarification-error').textContent = '';
  for (const question of pending.questions || []) {
    const field = question.field;
    if (!fieldLabels[field]) continue;
    const id = 'clarify-' + field;
    const row = node('div', '', 'clarification-field');
    const label = node('label', fieldLabels[field]); label.htmlFor = id;
    const isNumber = ['downtime_minutes', 'customer_impact_count'].includes(field);
    const isText = ['incident_id', 'threshold_detected_at'].includes(field);
    const input = node(isNumber || isText ? 'input' : 'select', ''); input.id = id;
    if (isNumber) { input.type = 'number'; input.min = '0'; input.max = field === 'downtime_minutes' ? '100000' : '10000000'; input.step = '1'; input.placeholder = 'Unknown'; }
    else if (isText) { input.type = 'text'; input.placeholder = field === 'incident_id' ? 'INC-001 or unknown' : '2026-09-29T10:00:00Z or unknown'; input.maxLength = field === 'incident_id' ? 7 : 40; }
    else {
      const unknown = node('option', 'Unknown / not verified'); unknown.value = ''; input.append(unknown);
      const options = field === 'category' ? ['digital_outage','payment_failure','facility_disruption','customer_impact','data_integrity','vendor_disruption'] : field === 'severity' ? ['SEV1','SEV2','SEV3','SEV4'] : ['true','false'];
      for (const value of options) { const option = node('option', value === 'true' ? 'Yes' : value === 'false' ? 'No' : value.replaceAll('_', ' ')); option.value = value; input.append(option); }
    }
    const hint = node('p', question.question + ' Blank/Unknown means unverified, never zero or No.', 'muted'); hint.id = id + '-hint';
    const error = node('p', '', 'form-error'); error.id = id + '-error';
    input.setAttribute('aria-describedby', hint.id + ' ' + error.id);
    input.addEventListener('blur', () => validateClarification(input, field));
    input.addEventListener('input', () => { input.setCustomValidity(''); byId(error.id).textContent = ''; input.setAttribute('aria-invalid','false'); });
    row.append(label, input, hint, error); area.append(row);
  }
}
byId('clarification-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const context = {}, unknown = []; let valid = true;
  for (const field of clarificationFields) {
    const input = byId('clarify-' + field); if (!input) continue;
    if (!validateClarification(input, field)) valid = false;
    const value = input.value.trim();
    if (!value) unknown.push(field);
    else if (['downtime_minutes','customer_impact_count'].includes(field)) context[field] = Number(value);
    else if (value === 'true' || value === 'false') context[field] = value === 'true';
    else context[field] = value;
  }
  if (!valid) { byId('clarification-error').textContent = 'Check the highlighted incident facts.'; byId('clarification-error').focus(); return; }
  resumeInvestigation({action: 'clarify', ...(Object.keys(context).length ? {incident_context: context} : {}), unknown_fields: unknown});
});
byId('review-accept').addEventListener('click', () => resumeInvestigation({action: 'review', decision: 'accept'}));
byId('review-decline').addEventListener('click', () => resumeInvestigation({action: 'review', decision: 'decline'}));
byId('restore-investigation').hidden = !sessionStorage.getItem('opspilot_investigation');
byId('restore-investigation').addEventListener('click', async () => {
  if (investigationPending) return;
  investigationPending = true;
  syncComposer();
  try {
    const saved = JSON.parse(sessionStorage.getItem('opspilot_investigation'));
    if (!saved?.id || !saved?.token) throw new Error('No saved investigation in this browser tab.');
    activeInvestigation = saved;
    byId('workflow-mode').value = 'investigation';
    byId('v2-options').hidden = false;
    const response = await investigationAPI('/' + saved.id, undefined, saved.token);
    byId('investigation-mode').value = response.mode;
    syncProviderControls();
    renderInvestigation(response);
  } catch (error) { byId('answer-state').textContent = error.message; }
  finally { investigationPending = false; syncComposer(); }
});
