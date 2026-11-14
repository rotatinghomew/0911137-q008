import copy
import json
import unittest

from expense_links.application import ROOT
from expense_links.domain import run


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((ROOT / 'fixtures/data.json').read_text())
        self.data = {key: [] for key in self.fixture['tables']}

    def test_fixture_is_deterministic_and_not_mutated(self):
        original = copy.deepcopy(self.fixture['tables'])
        options = {'cutoff': self.fixture['meta']['default_cutoff'], 'group': ''}
        first = run(self.fixture['tables'], options)
        second = run(self.fixture['tables'], options)
        self.assertEqual(first, second)
        self.assertEqual(original, self.fixture['tables'])
        self.assertTrue(first['rows'])
        json.dumps(first, allow_nan=False)

    def sample(self):
        self.data['claims'] = [dict(claim='x', employee='e', payee='p', project='甲', amount=150, day=1)]
        self.data['payees'] = [dict(payee='p', public_service=True)]
        first = dict(relation='r', employee='e', payee='p', evidence_id='x', valid_from=1, valid_to=None, recorded_at=1)
        self.data['relations'] = [first, {**first, 'relation': 'copy'}, {**first, 'valid_to': 15, 'recorded_at': 20}]
        self.data['reviews'] = [dict(claim='x', result='dismissed', reviewed_at=25)]

    def test_evidence_deduplicates_and_public_payee_is_visible(self):
        self.sample()
        row = run(self.data, {'cutoff': 10, 'group': ''})['rows'][0]
        self.assertEqual(row['evidence_count'], 1)
        self.assertTrue(row['public_service'])
        self.assertIsNone(row['review'])

    def test_correction_applies_only_when_known(self):
        self.sample()
        self.data['relations'] = [row for row in self.data['relations'] if row['relation'] != 'copy']
        early = run(self.data, {'cutoff': 16, 'group': ''})['rows'][0]
        later = run(self.data, {'cutoff': 20, 'group': ''})['rows'][0]
        self.assertEqual(early['linked_payees'], ['p'])
        self.assertEqual(later['linked_payees'], [])

    def test_reviews_are_selectively_available(self):
        self.sample()
        result = run(self.data, {'cutoff': 25, 'group': '甲'})
        self.assertEqual(result['summary']['已经复核'], 1)
        self.assertEqual(result['rows'][0]['review'], 'dismissed')

    def cluster(self, second_payee='p', first_project='甲', second_project='甲', public=False, corrections=()):
        self.data['claims'] = [
            dict(claim='x', employee='e', payee='p', project=first_project, amount=40, day=1),
            dict(claim='y', employee='e', payee=second_payee, project=second_project, amount=60, day=8),
        ]
        self.data['payees'] = [
            dict(payee=payee, public_service=public and payee == 'p')
            for payee in {second_payee, 'p'}
        ]
        shared = dict(relation='r', employee='e', payee='p', evidence_id='x', valid_from=1, valid_to=None, recorded_at=1)
        other = {**shared, 'relation': 'r2', 'payee': second_payee, 'evidence_id': 'y', 'valid_from': 8, 'recorded_at': 8}
        self.data['relations'] = [shared, other, *corrections]
        self.data['reviews'] = [dict(claim='y', result='dismissed', reviewed_at=20)]

    def test_shared_dimensions_form_a_lead_and_evidence_is_counted_once(self):
        self.cluster()
        result = run(self.data, {'cutoff': 20, 'group': ''})
        self.assertEqual(len(result['leads']), 1)
        lead = result['leads'][0]
        self.assertEqual(lead['claim_ids'], ['x', 'y'])
        self.assertEqual(lead['evidence_count'], 2)
        first = lead['evidence'][0]
        self.assertEqual(first['evidence_id'], 'x')
        self.assertEqual(first['relation_ids'], ['r'])
        self.assertEqual(first['edge_count'], 1)
        self.assertFalse(lead['correction']['affected'])

    def test_public_service_is_excluded_from_linking_by_default(self):
        self.cluster(second_project='乙', public=True)
        hidden = run(self.data, {'cutoff': 20, 'group': ''})
        visible = run(self.data, {'cutoff': 20, 'group': '', 'exclude_public': False})
        self.assertEqual(hidden['leads'], [])
        self.assertEqual(len(visible['leads']), 1)
        self.assertEqual(visible['leads'][0]['public_service_payees'], ['p'])
        self.assertTrue(all(claim['public_service'] for claim in visible['leads'][0]['claims']))

    def test_isolated_claim_is_not_a_lead_and_window_bounds_pairs(self):
        self.cluster()
        narrow = run(self.data, {'cutoff': 20, 'group': '', 'window': 3})
        self.assertEqual(narrow['leads'], [])
        self.assertTrue(narrow['notes'])

    def test_unknown_review_is_not_a_negative(self):
        self.cluster()
        self.data['reviews'] = []
        result = run(self.data, {'cutoff': 20, 'group': ''})
        evaluation = result['evaluation']
        self.assertEqual(result['leads'][0]['outcome'], 'unknown')
        self.assertEqual(evaluation['reviewed_in_top'], 0)
        self.assertIsNone(evaluation['precision'])
        self.assertEqual(evaluation['next_batch']['count'], 1)
        self.assertIn('不等于正常', evaluation['next_batch']['note'])

    def test_review_outcome_and_batch_evaluation(self):
        self.cluster()
        result = run(self.data, {'cutoff': 20, 'group': '', 'capacity': 1})
        evaluation = result['evaluation']
        self.assertEqual(result['leads'][0]['outcome'], 'dismissed')
        self.assertEqual(evaluation['reviewed_in_top'], 1)
        self.assertEqual(evaluation['precision'], 0.0)
        self.assertEqual(evaluation['next_batch']['count'], 0)
        self.assertEqual(evaluation['baseline']['name'], '线索内单笔最大金额排序')

    def test_correction_is_traced_and_old_lead_kept(self):
        self.cluster(second_project='乙', corrections=[dict(relation='r2', employee='e', payee='p', evidence_id='y', valid_from=8, valid_to=15, recorded_at=25)])
        early = run(self.data, {'cutoff': 20, 'group': ''})
        later = run(self.data, {'cutoff': 25, 'group': ''})
        self.assertEqual(len(early['leads']), 1)
        self.assertEqual(early['leads'][0]['outcome'], 'dismissed')
        self.assertEqual(later['leads'], [])
        material = later['correction']['material_corrections']
        self.assertEqual([item['relation'] for item in material], ['r2'])
        self.assertFalse(material[0]['active_now'])
        retired = later['correction']['retired_leads']
        self.assertEqual(len(retired), 1)
        self.assertEqual(retired[0]['claim_ids'], ['x', 'y'])
        self.assertIn('不再成立', '；'.join(retired[0]['correction']['changes']))
        self.assertEqual(retired[0]['correction']['relation_ids'], ['r2'])
        self.assertIn('dismissed', [entry['result'] for entry in retired[0]['reviews']])
        self.assertEqual(retired[0]['evidence'][1]['relation_ids'], ['r2'])
        self.assertEqual(retired[0]['evidence'][1]['revisions'][-1]['valid_to'], 15)

