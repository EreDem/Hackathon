import os
import unittest
from unittest.mock import patch

from tools import analytics as a
from tools.visuals import search_distribution, period_comparison
import ui


class VisualTests(unittest.TestCase):
    def test_empty_charts(self):
        for figure in [ui.search_bursts([]), ui.resource_heatmap([]), ui.pareto([]),
                       ui.pattern_comparison({}), ui.pattern_comparison({}, heatmap=True),
                       ui.team_comparison([]), ui.period_bars([])]:
            self.assertTrue(figure.to_json())

    def test_pareto_uses_full_total(self):
        chart = ui.pareto([dict(template_id='A', team='X', n=30, logzeilen_passend_gesamt=100),
                           dict(template_id='B', team='X', n=20, logzeilen_passend_gesamt=100)])
        self.assertEqual(list(chart.data[1].y), [30, 50])

    def test_heatmap_and_comparison_preserve_gaps(self):
        rows = [dict(kind='time', zeit=1, observed_logs=10, n=0),
                dict(kind='time', zeit=2, observed_logs=0, n=None),
                dict(kind='cell', zeit=1, resource='A', n=2)]
        heatmap = ui.resource_heatmap(rows).data[0]
        self.assertEqual(list(heatmap.customdata[0]), [2, None])
        self.assertIsNone(heatmap.z[0][1])
        self.assertGreater(heatmap.z[0][0], 0)
        series = {'A': [dict(zeit=1, n=0, datenluecke=False), dict(zeit=2, n=9, datenluecke=True)]}
        self.assertEqual(list(ui.pattern_comparison(series).data[0].y), [0, None])
        self.assertEqual(list(ui.pattern_comparison(series, heatmap=True).data[0].z[0]), [0, None])

    def test_missing_reach_and_rate_remain_unknown(self):
        chart = ui.team_comparison([dict(gruppe='X', haeufigkeit=10, reichweite=None)])
        self.assertEqual(list(chart.data[1].x), [None])
        chart = ui.period_bars([dict(period='Earlier half', n=0, lines_per_1000=None, coverage_pct=0)])
        self.assertEqual(list(chart.data[1].y), [None])

    def test_validation_before_query(self):
        with patch.object(a, '_query') as query:
            for kwargs in [dict(dataset=None), dict(dataset='BGL', intervall='bad'),
                           dict(dataset='BGL', von='2006-01-01', bis='2005-01-01')]:
                with self.assertRaises(ValueError):
                    period_comparison(**kwargs)
            with self.assertRaises(ValueError):
                search_distribution('x', 'BGL', modus='bad')
            query.assert_not_called()

    def test_extra_row_fetch_exposes_truncation(self):
        with patch.object(a, '_query', return_value={'sql': 'executed', 'daten': [{}]*10001}) as query:
            result = search_distribution('x', 'BGL')
        self.assertTrue(result['meta']['gekuerzt'])
        self.assertEqual(result['zeilen'], 10000)
        self.assertEqual(query.call_args.args[-1], 10001)


@unittest.skipUnless(os.getenv('ANALYTICS_TEST_DB'), 'Requires local SereneDB')
class LiveVisualTests(unittest.TestCase):
    def test_calendar_halves_do_not_duplicate_matches(self):
        from tests.analytics_support import connect, SereneQuery, fixture_ctes
        with connect() as connection, patch.object(a, '_query', SereneQuery(connection, fixture_ctes())):
            result = period_comparison('BGL')
            self.assertEqual(sum(r['n'] for r in result['daten']), 11)
            self.assertTrue(all(0 <= r['coverage_pct'] <= 100 for r in result['daten']))
            patterns = a.top_patterns(None, dataset='BGL', limit=1)
            self.assertEqual(patterns['daten'][0]['logzeilen_passend_gesamt'], 11)

    def test_full_search_distribution_matches_independent_total(self):
        from tests.analytics_support import connect, SereneQuery
        from tools.engineer import search_logs
        with connect() as connection:
            transport = SereneQuery(connection)
            with patch.object(a, '_query', transport), patch('tools.engineer.run_query', transport):
                search = search_logs('data TLB error interrupt', dataset='BGL')
                distribution = search_distribution('data TLB error interrupt', 'BGL')
            self.assertFalse(distribution['meta']['gekuerzt'])
            rows = distribution['daten']
            summary = next(r for r in rows if r['kind'] == 'summary')
            self.assertEqual(summary['n'], search['gesamt_treffer'])
            self.assertEqual(sum(r['n'] or 0 for r in rows if r['kind'] == 'time'), summary['n']-summary['missing_time'])
            self.assertLessEqual(len({r['resource'] for r in rows if r['kind'] == 'cell'}), 20)


if __name__ == '__main__':
    unittest.main()
