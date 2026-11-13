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
