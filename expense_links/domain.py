from collections import Counter, defaultdict
import math
from statistics import mean, median


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


def run(data, options):
    cutoff, group = options['cutoff'], options['group']
    claims = [row for row in data['claims'] if row['day'] <= cutoff and selected(row['project'], group)]
    payees = {row['payee']: row for row in data['payees']}
    relations = latest(data['relations'], 'relation', 'recorded_at', 'recorded_at', cutoff)
    reviews = {row['claim']: row for row in data['reviews'] if row['reviewed_at'] <= cutoff}
    rows = []
    for claim in claims:
        evidence = [row for row in relations if row['evidence_id'] == claim['claim'] and row['valid_from'] <= cutoff and (row['valid_to'] is None or cutoff < row['valid_to'])]
        linked = sorted({row['payee'] for row in evidence})
        rows.append(dict(claim=claim['claim'], employee=claim['employee'], project=claim['project'], amount=number(claim['amount']), linked_payees=linked, evidence_count=len({row['evidence_id'] for row in evidence}), public_service=payees.get(claim['payee'], {}).get('public_service', False), review=reviews.get(claim['claim'], {}).get('result')))
    rows.sort(key=lambda row: (-row['amount'], row['claim']))
    return output(rows, {'费用单': len(rows), '金额合计': round(sum(row['amount'] for row in rows), 2), '已经复核': sum(row['review'] is not None for row in rows)}, ['金额排序不是违规结论，未复核记录的状态保持未知。'])
