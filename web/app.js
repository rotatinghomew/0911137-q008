const statusNode = document.querySelector('#status');
const filters = document.querySelector('#filters');
let current = null;
let requestGeneration = 0;
let expandedLead = null;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

function text(tag, value) {
  const node = document.createElement(tag);
  if (value === null || value === undefined) node.textContent = '未知';
  else node.textContent = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return node;
}

function table(container, rows) {
  container.replaceChildren();
  if (!rows.length) {
    container.append(text('p', '当前范围没有记录'));
    return;
  }
  const columns = Array.from(new Set(rows.flatMap(row => Object.keys(row))));
  const grid = document.createElement('table');
  const head = document.createElement('tr');
  for (const column of columns) head.append(text('th', column));
  const thead = document.createElement('thead');
  thead.append(head);
  grid.append(thead);
  const body = document.createElement('tbody');
  for (const row of rows) {
    const line = document.createElement('tr');
    for (const column of columns) line.append(text('td', row[column]));
    body.append(line);
  }
  grid.append(body);
  container.append(grid);
}

function labelled(container, pairs) {
  container.replaceChildren();
  for (const [key, value] of pairs) container.append(text('dt', key), text('dd', value));
}

function outcomeLabel(value) {
  return {confirmed: '已结案：需跟进', dismissed: '已结案：已排除', unknown: '未结案：保持未知'}[value] || value;
}

function reviewLabel(value) {
  if (value === null || value === undefined) return '未复核（未知）';
  return {needs_followup: '已结案：需跟进', dismissed: '已结案：已排除'}[value] || value;
}

function leadRow(lead) {
  const line = document.createElement('tr');
  line.className = 'lead-row';
  line.tabIndex = 0;
  line.dataset.lead = lead.lead_id;
  const cells = [
    lead.rank,
    lead.priority,
    lead.claim_ids.join('、'),
    lead.claim_count,
    lead.evidence_count,
    lead.shared_non_public_payees.length ? lead.shared_non_public_payees.join('、') : '无',
    lead.public_service_claim_count ? `${lead.public_service_claim_count} 笔` : '无',
    lead.aggregate_amount.toFixed(2),
    outcomeLabel(lead.outcome),
    lead.correction.affected ? '需重算' : '',
  ];
  for (const cell of cells) line.append(text('td', cell));
  const open = () => {
    expandedLead = expandedLead === lead.lead_id ? null : lead.lead_id;
    renderLeadDetail();
  };
  line.addEventListener('click', open);
  line.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      open();
    }
  });
  return line;
}

function renderLeads() {
  expandedLead = null;
  const container = document.querySelector('#leads');
  container.replaceChildren();
  const leads = current?.result.leads || [];
  if (!leads.length) {
    container.append(text('p', '当前范围没有形成关联线索；这不表示这些记录正常。'));
    renderLeadDetail();
    return;
  }
  const grid = document.createElement('table');
  const head = document.createElement('tr');
  for (const column of ['顺序', '优先级分', '费用单', '单数', '独立证据', '共享非公共服务商', '公共服务商记录', '金额合计', '复核状态', '更正提示']) head.append(text('th', column));
  const thead = document.createElement('thead');
  thead.append(head);
  grid.append(thead);
  const body = document.createElement('tbody');
  for (const lead of leads) body.append(leadRow(lead));
  grid.append(body);
  container.append(grid);
  renderLeadDetail();
}

function renderLeadDetail() {
  const container = document.querySelector('#lead-detail');
  const lead = current?.result.leads?.find(item => item.lead_id === expandedLead);
  if (!lead) {
    container.hidden = true;
    container.replaceChildren();
    return;
  }
  container.hidden = false;
  const heading = text('h3', `线索 ${lead.lead_id}`);
  const summary = document.createElement('dl');
  labelled(summary, [
    ['提出原因', lead.reasons.map(reason => reason.label).join('；')],
    ['评分构成', Object.entries(lead.score_parts).map(([key, value]) => `${key}=${value}`).join('，')],
    ['判定口径', '组内任一已结案为需跟进即记正例；全部已结案均为已排除才记负例；没有已结案记录为未知'],
  ]);
  const claimsHeading = text('h4', '涉及费用单');
  const claims = document.createElement('div');
  table(claims, lead.claims.map(claim => ({
    claim: claim.claim, employee: claim.employee, project: claim.project, payee: claim.payee,
    amount: claim.amount, day: claim.day, payee_corroborated: claim.payee_corroborated,
    public_service: claim.public_service, review: reviewLabel(claim.review),
  })));
  const evidenceHeading = text('h4', '独立原始凭证与支撑关系');
  const evidence = document.createElement('div');
  table(evidence, lead.evidence.map(item => ({
    evidence_id: item.evidence_id,
    独立证据: 1,
    关系边: item.edge_count,
    关系编号: item.relation_ids.join('、'),
    涉及收款标识: item.payees.join('、'),
    修订次数: item.revisions.length,
  })));
  const revisionHeading = text('h4', '关系修订');
  const revisions = document.createElement('div');
  const revisionRows = lead.evidence.flatMap(item => item.revisions.map(revision => ({
    evidence_id: item.evidence_id, 关系: revision.relation, employee: revision.employee,
    payee: revision.payee, valid_from: revision.valid_from,
    valid_to: revision.valid_to ?? '持续', recorded_at: revision.recorded_at,
    时点内有效: revision.active, 已被后续修订取代: revision.superseded,
  })));
  table(revisions, revisionRows);
  const excludedHeading = text('h4', '被排除的公共服务商关系');
  const excluded = document.createElement('div');
  table(excluded, lead.excluded_public_relations.map(item => ({
    relation: item.relation, evidence_id: item.evidence_id, payee: item.payee, 原因: item.reason,
  })));
  const correctionHeading = text('h4', '关系更正影响');
  const correction = text('p', lead.correction.affected
    ? `需重算：${lead.correction.changes.join('；')}${lead.correction.relation_ids.length ? `（关系 ${lead.correction.relation_ids.join('、')}）` : ''}`
    : '当前可见关系没有影响本线索的更正。');
  const close = text('button', '收起');
  close.type = 'button';
  close.addEventListener('click', () => { expandedLead = null; renderLeadDetail(); });
  container.replaceChildren(heading, close, summary, claimsHeading, claims, evidenceHeading, evidence, revisionHeading, revisions, excludedHeading, excluded, correctionHeading, correction);
}

function renderEvaluation() {
  const evaluation = current?.result.evaluation;
  if (!evaluation) return;
  labelled(document.querySelector('#evaluation-summary'), [
    ['计划批次容量', evaluation.capacity],
    ['线索总数', evaluation.lead_count],
    ['批次内已结案', evaluation.reviewed_in_top],
    ['批次内确认需跟进', evaluation.confirmed_in_top],
    ['已复核子集精确率', evaluation.precision === null ? '无已结案线索，无法估计' : evaluation.precision],
    ['精确率置信区间', evaluation.precision_wilson ? `${evaluation.precision_wilson[0]} – ${evaluation.precision_wilson[1]}` : '无'],
    ['批次内已复核占比', evaluation.reviewed_share === null ? '无' : `${evaluation.reviewed_share}`],
    ['批次内未复核', `${evaluation.unreviewed_in_top}（保持未知，不当作正常）`],
    ['对照：单笔最大金额排序', `${evaluation.baseline.name}，精确率 ${evaluation.baseline.precision ?? '无'}`],
  ]);
  document.querySelector('#evaluation-notes').replaceChildren(
    text('li', evaluation.method),
    text('li', evaluation.selection_bias),
  );
  table(document.querySelector('#evaluation-points'), evaluation.points.map(point => ({
    前K条: point.k, 已结案: point.evaluated, 确认: point.confirmed,
    精确率: point.precision, 置信区间: point.wilson ? point.wilson.join(' – ') : '无',
  })));
  const next = document.querySelector('#next-batch');
  next.replaceChildren(
    text('h3', `下一批线索（${evaluation.next_batch.count} 条）`),
    text('p', evaluation.next_batch.lead_ids.join('、') || '当前批次没有未复核线索'),
    text('p', evaluation.next_batch.note),
  );
}

function renderCorrection() {
  const correction = current?.result.correction;
  const container = document.querySelector('#correction');
  container.replaceChildren();
  if (!correction) return;
  const heading = text('h3', '已可见的关系更正');
  container.append(heading);
  if (!correction.material_corrections.length) {
    container.append(text('p', '当前时点没有可见的关系更正。'));
  } else {
    table(container, correction.material_corrections.map(item => ({
      关系: item.relation, 证据: item.evidence_id,
      上一条修订: `有效期 ${item.previous.valid_from}–${item.previous.valid_to ?? '持续'}，记录于 ${item.previous.recorded_at}`,
      当前修订: `有效期 ${item.current.valid_from}–${item.current.valid_to ?? '持续'}，记录于 ${item.current.recorded_at}`,
      更正前有效: item.active_before, 更正后有效: item.active_now,
    })));
  }
  container.append(text('h3', `需重算线索（${correction.affected_leads.length} 条）`));
  if (!correction.affected_leads.length) {
    container.append(text('p', '没有线索受当前可见关系更正影响。'));
  } else {
    const list = document.createElement('ul');
    for (const identifier of correction.affected_leads) {
      const lead = current.result.leads.find(item => item.lead_id === identifier);
      const item = document.createElement('li');
      const button = text('button', `${identifier}：${lead?.claim_ids.join('、') ?? ''}`);
      button.type = 'button';
      button.addEventListener('click', () => {
        expandedLead = identifier;
        renderLeadDetail();
        document.querySelector('#lead-detail').scrollIntoView({block: 'nearest'});
      });
      item.append(button, text('small', lead?.correction.changes.join('；') ?? ''));
      list.append(item);
    }
    container.append(list);
  }
  container.append(text('h3', `已不再成立的旧线索（${correction.retired_leads.length} 条）`));
  if (!correction.retired_leads.length) {
    container.append(text('p', '没有旧线索因更正失效。'));
  } else {
    for (const lead of correction.retired_leads) {
      const details = document.createElement('details');
      details.append(text('summary', `旧线索 ${lead.lead_id}：${lead.claim_ids.join('、')}`));
      details.append(text('p', `当时提出原因：${lead.reasons.map(reason => reason.label).join('；')}`));
      details.append(text('p', `失效原因：${lead.correction.changes.join('；')}`));
      const evidence = document.createElement('div');
      table(evidence, lead.evidence.map(item => ({
        evidence_id: item.evidence_id, 关系编号: item.relation_ids.join('、'), 涉及收款标识: item.payees.join('、'),
      })));
      details.append(evidence);
      container.append(details);
    }
  }
  container.append(text('p', correction.note));
}

function render(value, savedTitle = '') {
  current = value;
  const summary = document.querySelector('#summary');
  labelled(summary, Object.entries(value.result.summary));
  document.querySelector('#notes').replaceChildren(...value.result.notes.map(note => text('li', note)));
  document.querySelector('#digest').textContent = `资料指纹：${value.digest}`;
  renderLeads();
  renderEvaluation();
  renderCorrection();
  table(document.querySelector('#results'), value.result.rows);
  statusNode.textContent = savedTitle ? `正在查看保存的分析：${savedTitle}` : '分析已更新';
  filters.elements.cutoff.value = value.options.cutoff;
  filters.elements.group.value = value.options.group;
  if (value.options.window !== undefined) filters.elements.window.value = value.options.window;
  if (value.options.capacity !== undefined) filters.elements.capacity.value = value.options.capacity;
  if (value.options.exclude_public !== undefined) filters.elements.exclude_public.checked = value.options.exclude_public;
}

async function refresh() {
  const generation = ++requestGeneration;
  const query = new URLSearchParams(new FormData(filters));
  query.set('exclude_public', filters.elements.exclude_public.checked ? 'true' : 'false');
  statusNode.textContent = '正在分析';
  try {
    const result = await api(`/api/view?${query}`);
    if (generation === requestGeneration) render(result);
  } catch (error) {
    if (generation === requestGeneration) {
      current = null;
      statusNode.textContent = error.message;
    }
  }
}

async function history() {
  const entries = await api('/api/analyses');
  const list = document.querySelector('#history');
  list.replaceChildren();
  for (const entry of entries) {
    const item = document.createElement('li');
    const button = text('button', entry.title);
    button.type = 'button';
    button.addEventListener('click', async () => {
      const generation = ++requestGeneration;
      try {
        const saved = await api(`/api/analyses/${entry.id}`);
        if (generation === requestGeneration) render(saved, saved.title);
      } catch (error) {
        statusNode.textContent = error.message;
      }
    });
    item.append(button, text('small', entry.created_at));
    list.append(item);
  }
}

filters.addEventListener('submit', event => {
  event.preventDefault();
  refresh();
});

document.querySelector('#save').addEventListener('submit', async event => {
  event.preventDefault();
  if (!current) return;
  try {
    const saved = await api('/api/analyses', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: event.target.elements.title.value, options: current.options})});
    render(saved, saved.title);
    await history();
  } catch (error) {
    statusNode.textContent = error.message;
  }
});

document.querySelector('#source').addEventListener('click', async () => {
  try {
    const data = await api(`/api/source?table=${encodeURIComponent(document.querySelector('#tables').value)}`);
    table(document.querySelector('#raw'), data.rows);
  } catch (error) {
    statusNode.textContent = error.message;
  }
});

async function start() {
  const catalog = await api('/api/catalog');
  document.querySelector('#description').textContent = catalog.description;
  filters.elements.cutoff.min = catalog.min_cutoff;
  filters.elements.cutoff.max = catalog.max_cutoff;
  filters.elements.cutoff.value = catalog.default_cutoff;
  filters.elements.window.value = catalog.link_defaults.window;
  filters.elements.capacity.value = catalog.link_defaults.capacity;
  filters.elements.exclude_public.checked = catalog.link_defaults.exclude_public;
  const groups = [['', '全部'], ...catalog.groups.map(group => [group, group])];
  for (const [key, label] of groups) {
    const option = text('option', label);
    option.value = key;
    filters.elements.group.append(option);
  }
  for (const name of Object.keys(catalog.tables)) {
    const option = text('option', `${name}（${catalog.tables[name]}）`);
    option.value = name;
    document.querySelector('#tables').append(option);
  }
  await refresh();
  await history();
}

start().catch(error => { statusNode.textContent = error.message; });
