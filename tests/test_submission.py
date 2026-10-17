"""The committed worked case must contain real, inspectable three-role evidence."""
import json
from pathlib import Path
import re
import unittest


class SubmissionEvidenceTests(unittest.TestCase):
    def test_worked_case_has_three_completed_roles_and_executed_evidence(self):
        root = Path(__file__).resolve().parents[1]
        report = json.loads((root / 'docs/evidence/worked-investigation.json').read_text(encoding='utf-8'))
        self.assertEqual({case['role'] for case in report['cases']}, {'Engineer', 'Team Lead', 'Manager'})
        self.assertEqual({r['dataset']: r['log_lines'] for r in report['corpus']['daten']},
                         {'BGL': 4747963, 'OpenStack': 207820})
        tools = set()
        for case in report['cases']:
            self.assertEqual(case['meta']['status'], 'ok')
            self.assertFalse(case['meta']['testdaten'])
            self.assertTrue(case['belege'])
            ids = {item['beleg_id'] for item in case['belege']}
            self.assertTrue(set(re.findall(r'\bB\d+\b', case['text'])) <= ids)
            for evidence in case['belege']:
                tools.add(evidence['tool'])
                self.assertTrue(evidence['sql'].strip())
                self.assertNotRegex(evidence['sql'], r'%s\b')
                self.assertEqual(evidence['zeilen'], len(evidence['daten']))
                self.assertIsInstance(evidence['parameter'], dict)
        self.assertTrue({'search_logs', 'get_context', 'vm_dauer', 'top_patterns', 'pattern_trend', 'priority_ranking'} <= tools)
