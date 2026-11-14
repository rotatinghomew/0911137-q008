from collections import Counter, defaultdict
import hashlib
import math
from statistics import median


DEFAULT_WINDOW = 30
DEFAULT_EXCLUDE_PUBLIC = True
DEFAULT_CAPACITY = 20
SCORE_WEIGHTS = {
    'amount_per_100': 1,
    'independent_evidence': 2,
    'shared_non_public_payee': 4,
    'extra_claim': 3,
    'small_split': 3,
    'project_spread': 1,
    'employee_spread': 1,
}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('数值必须为有限实数')
    return value


def selected(value, group):
    return not group or value == group


def latest(rows, key, revision, visible, cutoff):
    result = {}
    for row in rows:
        if row[visible] > cutoff:
            continue
        previous = result.get(row[key])
        if previous is None or row[revision] > previous[revision]:
            result[row[key]] = row
    return list(result.values())


def output(rows, summary, notes):
    return {'rows': rows, 'summary': summary, 'notes': notes}


def active_at(row, cutoff):
    return row['valid_from'] <= cutoff and (row['valid_to'] is None or cutoff < row['valid_to'])


def relation_state(relations, cutoff):
    visible = [(index, row) for index, row in enumerate(relations) if row['recorded_at'] <= cutoff]
    grouped = defaultdict(list)
    for index, row in visible:
        grouped[row['relation']].append((index, row))
    current, previous, history = {}, {}, {}
    for relation_id, items in grouped.items():
        latest_item = items[0]
        for item in items[1:]:
            if item[1]['recorded_at'] > latest_item[1]['recorded_at']:
                latest_item = item
        current[relation_id] = latest_item[1]
        older = [item for item in items if item[1]['recorded_at'] < latest_item[1]['recorded_at']]
        previous[relation_id] = max(older, key=lambda item: (item[1]['recorded_at'], item[0]))[1] if older else latest_item[1]
        history[relation_id] = sorted(items, key=lambda item: (item[1]['recorded_at'], item[0]))
    active = [row for row in current.values() if active_at(row, cutoff)]
    prior = [row for row in previous.values() if active_at(row, cutoff)]
    return {'current': current, 'previous': previous, 'history': history, 'active': active, 'prior_active': prior}


def latest_reviews(reviews, cutoff):
    result = {}
    for row in reviews:
        if row['reviewed_at'] > cutoff:
            continue
        previous = result.get(row['claim'])
        if previous is None or row['reviewed_at'] >= previous['reviewed_at']:
            result[row['claim']] = row
    return result


def corroboration(active_relations):
    return {(row['evidence_id'], row['employee'], row['payee']) for row in active_relations}


def claim_payee_corroborated(claim, pairs):
    return (claim['claim'], claim['employee'], claim['payee']) in pairs


def shared_dimensions(first, second, pairs, payees, exclude_public):
    dimensions = []
    if first['employee'] == second['employee']:
        dimensions.append('employee')
    if first['project'] == second['project']:
        dimensions.append('project')
    if first['payee'] == second['payee'] and claim_payee_corroborated(first, pairs) and claim_payee_corroborated(second, pairs):
        public = payees.get(first['payee'], {}).get('public_service', False)
        if not (exclude_public and public):
            dimensions.append('payee')
    return dimensions


def components(claims, active_relations, payees, exclude_public, window):
    ordered = sorted(claims, key=lambda row: (row['day'], row['claim']))
    pairs = corroboration(active_relations)
    adjacency = defaultdict(set)
    for index, first in enumerate(ordered):
        for second in ordered[index + 1:]:
            if second['day'] - first['day'] > window:
                break
            if len(shared_dimensions(first, second, pairs, payees, exclude_public)) >= 2:
                adjacency[first['claim']].add(second['claim'])
                adjacency[second['claim']].add(first['claim'])
    by_id = {claim['claim']: claim for claim in ordered}
    seen, result = set(), []
    for claim in ordered:
        identifier = claim['claim']
        if identifier in seen:
            continue
        seen.add(identifier)
        pending, group = [identifier], []
        while pending:
            current = pending.pop()
            group.append(by_id[current])
            for neighbour in sorted(adjacency[current], reverse=True):
                if neighbour not in seen:
                    seen.add(neighbour)
                    pending.append(neighbour)
        if len(group) > 1:
            result.append(sorted(group, key=lambda row: (row['day'], row['claim'])))
    return result


def revisions_of(relation_id, history, cutoff):
    result = []
    items = history.get(relation_id, [])
    for index, (_, row) in enumerate(items):
        result.append({
            'relation': row['relation'],
            'employee': row['employee'],
            'payee': row['payee'],
            'evidence_id': row['evidence_id'],
            'valid_from': row['valid_from'],
            'valid_to': row['valid_to'],
            'recorded_at': row['recorded_at'],
            'active': active_at(row, cutoff),
            'superseded': index < len(items) - 1,
        })
    return result


def evidence_groups(claims, active_relations, history, cutoff, exclude_public, payees):
    claim_ids = {claim['claim'] for claim in claims}
    grouped = defaultdict(list)
    excluded_public = []
    for row in active_relations:
        if row['evidence_id'] not in claim_ids:
            continue
        public = payees.get(row['payee'], {}).get('public_service', False)
        ignored = exclude_public and public
        grouped[row['evidence_id']].append({
            'relation': row['relation'],
            'employee': row['employee'],
            'payee': row['payee'],
            'public_service': public,
            'used_for_linking': not ignored,
        })
        if ignored:
            excluded_public.append({
                'relation': row['relation'],
                'evidence_id': row['evidence_id'],
                'employee': row['employee'],
                'payee': row['payee'],
                'reason': '公共服务商，默认不作为关联依据',
            })
    evidence = []
    for evidence_id in sorted(grouped):
        rows = grouped[evidence_id]
        relation_ids = sorted({row['relation'] for row in rows})
        evidence.append({
            'evidence_id': evidence_id,
            'relation_ids': relation_ids,
            'edge_count': len(rows),
            'payees': sorted({row['payee'] for row in rows}),
            'edges': rows,
            'revisions': [
                revision for relation_id in relation_ids
                for revision in revisions_of(relation_id, history, cutoff)
            ],
        })
    return evidence, excluded_public


def review_entries(claims, reviews):
    entries = []
    for claim in claims:
        review = reviews.get(claim['claim'])
        if review is not None:
            entries.append({'claim': claim['claim'], 'result': review['result'], 'reviewed_at': review['reviewed_at']})
    return entries


def outcome(entries):
    if not entries:
        return 'unknown'
    if any(entry['result'] == 'needs_followup' for entry in entries):
        return 'confirmed'
    return 'dismissed'


def lead_identifier(claims):
    digest = hashlib.sha256('|'.join(sorted(claim['claim'] for claim in claims)).encode()).hexdigest()[:12]
    return 'L-' + digest


def describe_lead(claims, active_relations, history, cutoff, payees, reviews, threshold, exclude_public):
    ordered = sorted(claims, key=lambda row: (row['day'], row['claim']))
    pairs = corroboration(active_relations)
    evidence, excluded_public = evidence_groups(ordered, active_relations, history, cutoff, exclude_public, payees)
    evidence_count = len(evidence)
    relation_edge_count = sum(item['edge_count'] for item in evidence)
    employees = sorted({claim['employee'] for claim in ordered})
    projects = sorted({claim['project'] for claim in ordered})
    payee_counts = Counter(claim['payee'] for claim in ordered)
    corroborated_claims = [claim for claim in ordered if claim_payee_corroborated(claim, pairs)]
    shared_non_public = sorted(
        payee for payee, count in payee_counts.items()
        if count >= 2 and not payees.get(payee, {}).get('public_service', False)
        and sum(1 for claim in corroborated_claims if claim['payee'] == payee) >= 2
    )
    public_payees = sorted(
        payee for payee, count in payee_counts.items()
        if count >= 2 and payees.get(payee, {}).get('public_service', False)
    )
    public_claims = [claim for claim in ordered if payees.get(claim['payee'], {}).get('public_service', False)]
    amounts = [number(claim['amount']) for claim in ordered]
    aggregate = round(sum(amounts), 2)
    maximum = max(amounts)
    small_count = sum(1 for amount in amounts if amount <= threshold) if threshold is not None else 0
    entries = review_entries(ordered, reviews)
    reasons = [{'code': 'multiple_claims', 'label': '多笔费用单形成关联组'}]
    if small_count >= 2:
        reasons.append({'code': 'small_split', 'label': '组内多笔金额不高于当前范围中位数'})
    if shared_non_public:
        reasons.append({'code': 'shared_non_public_payee', 'label': '存在多笔共享的非公共服务商'})
    if len(projects) > 1:
        reasons.append({'code': 'cross_project', 'label': '关联组跨项目'})
    if len(employees) > 1:
        reasons.append({'code': 'cross_employee', 'label': '关联组跨员工'})
    if evidence_count > 1:
        reasons.append({'code': 'independent_evidence', 'label': '独立原始凭证不止一份'})
    parts = {
        'amount': round(aggregate / 100 * SCORE_WEIGHTS['amount_per_100'], 2),
        'independent_evidence': SCORE_WEIGHTS['independent_evidence'] * evidence_count,
        'shared_non_public_payee': SCORE_WEIGHTS['shared_non_public_payee'] * len(shared_non_public),
        'extra_claims': SCORE_WEIGHTS['extra_claim'] * (len(ordered) - 1),
        'small_split': SCORE_WEIGHTS['small_split'] if small_count >= 2 else 0,
        'project_spread': SCORE_WEIGHTS['project_spread'] * max(0, len(projects) - 1),
        'employee_spread': SCORE_WEIGHTS['employee_spread'] * max(0, len(employees) - 1),
    }
    return {
        'lead_id': lead_identifier(ordered),
        'claims': [
            {
                'claim': claim['claim'],
                'employee': claim['employee'],
                'payee': claim['payee'],
                'project': claim['project'],
                'amount': number(claim['amount']),
                'day': claim['day'],
                'payee_corroborated': claim_payee_corroborated(claim, pairs),
                'public_service': payees.get(claim['payee'], {}).get('public_service', False),
                'review': reviews.get(claim['claim'], {}).get('result'),
            }
            for claim in ordered
        ],
        'claim_ids': [claim['claim'] for claim in ordered],
        'claim_count': len(ordered),
        'employee_count': len(employees),
        'employees': employees,
        'payees': sorted(payee_counts),
        'projects': projects,
        'shared_non_public_payees': shared_non_public,
        'public_service_payees': public_payees,
        'public_service_claim_count': len(public_claims),
        'aggregate_amount': aggregate,
        'max_single_amount': round(maximum, 2),
        'small_claim_count': small_count,
        'evidence': evidence,
        'evidence_count': evidence_count,
        'relation_edge_count': relation_edge_count,
        'excluded_public_relations': excluded_public,
        'reasons': reasons,
        'score_parts': parts,
        'priority': round(sum(parts.values()), 2),
        'reviews': entries,
        'outcome': outcome(entries),
        'correction': {'affected': False, 'relation_ids': [], 'changes': []},
    }


def wilson_interval(proportion, total, z=1.96):
    if total == 0:
        return None
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0, centre - margin), 4), round(min(1, centre + margin), 4)]


def evaluate(leads, capacity):
    def snapshot(selection):
        reviewed = [lead for lead in selection if lead['outcome'] != 'unknown']
        confirmed = sum(lead['outcome'] == 'confirmed' for lead in reviewed)
        proportion = confirmed / len(reviewed) if reviewed else None
        return {
            'evaluated': len(reviewed),
            'confirmed': confirmed,
            'precision': round(proportion, 4) if proportion is not None else None,
            'wilson': wilson_interval(proportion, len(reviewed)) if proportion is not None else None,
        }
    points = []
    for k in sorted({5, 10, 20, 50, capacity}):
        if k > len(leads):
            continue
        points.append({'k': k, **snapshot(leads[:k])})
    top = leads[:capacity]
    summary = snapshot(top)
    baseline = sorted(leads, key=lambda lead: (-lead['max_single_amount'], lead['lead_id']))
    baseline_summary = snapshot(baseline[:capacity])
    return {
        'capacity': capacity,
        'lead_count': len(leads),
        'reviewed_in_top': summary['evaluated'],
        'confirmed_in_top': summary['confirmed'],
        'precision': summary['precision'],
        'precision_wilson': summary['wilson'],
        'batch_size': len(top),
        'reviewed_share': round(summary['evaluated'] / len(top), 4) if top else None,
        'unreviewed_in_top': len(top) - summary['evaluated'],
        'points': points,
        'baseline': {
            'name': '线索内单笔最大金额排序',
            **baseline_summary,
        },
        'next_batch': {
            'lead_ids': [lead['lead_id'] for lead in top if lead['outcome'] == 'unknown'],
            'count': sum(lead['outcome'] == 'unknown' for lead in top),
            'note': '按当前排序优先复核；尚未复核保持未知，不等于正常。',
        },
        'method': '按线索统计：组内任一已结案记录为需跟进即记为正例，组内全部已结案记录均为已排除才记为负例；组内没有已结案记录时为未知，不计入分母，也不当作正常。',
        'selection_bias': '已结案记录只来自有限人力抽中的案件，精确率与覆盖率只描述这个已复核子集，不能外推为全部线索的准确率，也不能把未复核线索当作负例。',
    }


def run(data, options):
    cutoff, group = options['cutoff'], options['group']
    window = options.get('window', DEFAULT_WINDOW)
    exclude_public = options.get('exclude_public', DEFAULT_EXCLUDE_PUBLIC)
    capacity = options.get('capacity', DEFAULT_CAPACITY)
    claims = [row for row in data['claims'] if row['day'] <= cutoff and selected(row['project'], group)]
    payees = {row['payee']: row for row in data['payees']}
    reviews = latest_reviews(data['reviews'], cutoff)
    state = relation_state(data['relations'], cutoff)
    active = state['active']
    visible_relations = latest(data['relations'], 'relation', 'recorded_at', 'recorded_at', cutoff)
    rows = []
    for claim in claims:
        evidence = [row for row in visible_relations if row['evidence_id'] == claim['claim'] and active_at(row, cutoff)]
        linked = sorted({row['payee'] for row in evidence})
        rows.append(dict(claim=claim['claim'], employee=claim['employee'], project=claim['project'], amount=number(claim['amount']), linked_payees=linked, evidence_count=len({row['evidence_id'] for row in evidence}), public_service=payees.get(claim['payee'], {}).get('public_service', False), review=reviews.get(claim['claim'], {}).get('result')))
    rows.sort(key=lambda row: (-row['amount'], row['claim']))
    amounts = sorted(number(row['amount']) for row in claims)
    threshold = median(amounts) if amounts else None
    current_groups = components(claims, active, payees, exclude_public, window)
    leads = [describe_lead(group, active, state['history'], cutoff, payees, reviews, threshold, exclude_public) for group in current_groups]
    prior_groups = components(claims, state['prior_active'], payees, exclude_public, window)
    prior = [describe_lead(group, state['prior_active'], state['history'], cutoff, payees, reviews, threshold, exclude_public) for group in prior_groups]
    prior_by_key = {tuple(lead['claim_ids']): lead for lead in prior}
    prior_of_claim = {}
    for old in prior:
        for claim_id in old['claim_ids']:
            prior_of_claim[claim_id] = old
    current_keys = {tuple(lead['claim_ids']) for lead in leads}
    material_corrections = []
    for relation_id, latest_row in state['current'].items():
        if relation_id not in state['previous']:
            continue
        previous_row = state['previous'][relation_id]
        revisions = revisions_of(relation_id, state['history'], cutoff)
        if len(revisions) < 2:
            continue
        material = (
            previous_row['valid_to'] != latest_row['valid_to'] or previous_row['valid_from'] != latest_row['valid_from']
            or previous_row['employee'] != latest_row['employee'] or previous_row['payee'] != latest_row['payee']
            or previous_row['evidence_id'] != latest_row['evidence_id'] or active_at(previous_row, cutoff) != active_at(latest_row, cutoff)
        )
        if material:
            material_corrections.append({
                'relation': relation_id,
                'evidence_id': latest_row['evidence_id'],
                'revisions': revisions,
                'current': {key: latest_row[key] for key in ('employee', 'payee', 'evidence_id', 'valid_from', 'valid_to', 'recorded_at')},
                'previous': {key: previous_row[key] for key in ('employee', 'payee', 'evidence_id', 'valid_from', 'valid_to', 'recorded_at')},
                'active_now': active_at(latest_row, cutoff),
                'active_before': active_at(previous_row, cutoff),
            })
    material_ids = {item['relation'] for item in material_corrections}
    material_evidence = {item['evidence_id']: item['relation'] for item in material_corrections}

    def corrections_for(claim_ids, old):
        related = set()
        if old is not None:
            related.update(
                relation_id
                for evidence in old['evidence']
                for relation_id in evidence['relation_ids']
                if relation_id in material_ids
            )
        symmetric = set(claim_ids) ^ set(old['claim_ids']) if old is not None else set(claim_ids)
        for claim_id in symmetric:
            if claim_id in material_evidence:
                related.add(material_evidence[claim_id])
        return sorted(related)

    retired = []
    for old in prior:
        if tuple(old['claim_ids']) not in current_keys:
            current_overlap = [
                new for new in leads
                if set(new['claim_ids']) & set(old['claim_ids'])
            ]
            changes = ['关系更正后该关联组不再成立']
            for new in current_overlap:
                remaining = sorted(set(old['claim_ids']) - set(new['claim_ids']))
                added = sorted(set(new['claim_ids']) - set(old['claim_ids']))
                if remaining:
                    changes.append('不再包含费用单 ' + '、'.join(remaining))
                if added:
                    changes.append('新增费用单 ' + '、'.join(added))
            old['correction'] = {
                'affected': True,
                'relation_ids': corrections_for(old['claim_ids'], old),
                'changes': changes,
            }
            retired.append(old)
    retired.sort(key=lambda lead: (-lead['priority'], lead['lead_id']))
    for lead in leads:
        old = prior_by_key.get(tuple(lead['claim_ids']))
        changes = []
        if old is None:
            candidate = prior_of_claim.get(lead['claim_ids'][0])
            if candidate is None:
                changes.append('该关联组只在关系更正后成立')
            else:
                changes.append('关联组组成变化')
                old = candidate
            if old is not None:
                remaining = sorted(set(old['claim_ids']) - set(lead['claim_ids']))
                added = sorted(set(lead['claim_ids']) - set(old['claim_ids']))
                if remaining:
                    changes.append('不再包含费用单 ' + '、'.join(remaining))
                if added:
                    changes.append('新增费用单 ' + '、'.join(added))
        else:
            if sorted(item['evidence_id'] for item in old['evidence']) != sorted(item['evidence_id'] for item in lead['evidence']):
                changes.append('独立证据集合变化')
            if old['claim_count'] != lead['claim_count']:
                changes.append('关联组费用单数量变化')
            if old['shared_non_public_payees'] != lead['shared_non_public_payees']:
                changes.append('共享非公共服务商变化')
            if old['public_service_payees'] != lead['public_service_payees']:
                changes.append('公共服务商分布变化')
        relation_ids = corrections_for(lead['claim_ids'], old)
        if not changes and relation_ids:
            changes.append('支撑关系发生更正，需按当前版本重算')
        if changes:
            lead['reasons'].append({'code': 'correction_affected', 'label': '关系更正后线索需重算'})
            lead['correction'] = {'affected': True, 'relation_ids': relation_ids, 'changes': changes}
    correction = {
        'material_corrections': material_corrections,
        'affected_leads': [lead['lead_id'] for lead in leads if lead['correction']['affected']],
        'retired_leads': retired,
        'note': '重算比较当前可见版本与同一条关系的上一条修订。保存过的分析版本保留提出时的线索、原因和支撑记录，可直接回看旧案件。',
    }
    leads.sort(key=lambda lead: (-lead['priority'], lead['lead_id']))
    for rank, lead in enumerate(leads, 1):
        lead['rank'] = rank
    evaluation = evaluate(leads, capacity)
    summary = {
        '费用单': len(rows),
        '金额合计': round(sum(row['amount'] for row in rows), 2),
        '已经复核': sum(row['review'] is not None for row in rows),
        '关联线索': len(leads),
        '已结案线索': sum(lead['outcome'] != 'unknown' for lead in leads),
    }
    notes = [
        '关联线索按金额、独立证据数、共享非公共服务商等固定权重排序；线索不是违规结论，也不针对个人。',
        '同一原始凭证的多条关系边只计一份独立证据，相关系统一并列出。',
        '公共服务商默认不作为关联依据；筛选里可关闭排除，以便查看影响，但不应据此给个人贴标签。',
        '未复核线索保持未知，不能当作正常；已结案反馈来自抽中案件，精确率只描述已复核子集，不能外推为全部线索的准确率。',
        '关系更正后，页面列出需重算线索和已不再成立的旧线索，并保留旧线索的提出原因与支撑记录。',
    ]
    if exclude_public:
        notes.append('当前已排除公共服务商作为关联维度。')
    if material_corrections:
        notes.append(f'当前可见 {len(material_corrections)} 条关系更正，影响 {len(correction["affected_leads"])} 条线索，另有 {len(retired)} 条旧线索不再成立。')
    result = output(rows, summary, notes)
    result.update({
        'leads': leads,
        'evaluation': evaluation,
        'correction': correction,
        'options': {'cutoff': cutoff, 'group': group, 'window': window, 'exclude_public': exclude_public, 'capacity': capacity},
        'score_weights': SCORE_WEIGHTS,
    })
    return result
