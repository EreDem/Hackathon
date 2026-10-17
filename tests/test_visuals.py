import os
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch

from tools import analytics as a
from tools.visuals import search_distribution, period_comparison
import ui


class VisualTests(unittest.TestCase):
    def test_same_second_events_are_counted_and_anchor_is_retained(self):
        start = datetime(2017, 5, 16, 3, 19, 45, 356000, tzinfo=timezone.utc)
        rows = [dict(id=i, ts=start+timedelta(microseconds=i), component='worker', level='ERROR') for i in range(12)]
        figure = ui.timeline(rows, anchor_id=5)
        self.assertEqual(len(figure.data[0].x), 1)
        self.assertEqual(figure.data[0].customdata[0][0], 12)
        self.assertEqual(figure.data[0].marker.size[0], 20)
        self.assertIn('ERROR ×12', figure.data[0].text)
        self.assertGreaterEqual(figure.layout.xaxis.range[1]-figure.layout.xaxis.range[0], timedelta(seconds=2))
        self.assertFalse(figure.layout.xaxis.rangeslider.visible)

    def test_time_views_show_coverage_without_turning_gaps_into_zero(self):
        start = datetime(2017, 5, 16, tzinfo=timezone.utc)
        rows = [dict(dataset='OpenStack', zeit=start+timedelta(hours=i), n=n,
                     datenluecke=n is None, beobachtete_logs=0 if n is None else 20)
                for i, n in enumerate([3, 0, None])]
        figure = ui.trend(rows)
        self.assertEqual(list(figure.data[0].y), [3, 0, None])
        self.assertEqual(list(figure.data[-1].z[0]), [1, 1, 0])
        self.assertFalse(figure.layout.xaxis.rangeslider.visible)
        self.assertEqual(figure.layout.xaxis.range[1]-figure.layout.xaxis.range[0], timedelta(hours=3))

    def test_scatter_log_axis_preserves_exact_coordinates_and_duplicates(self):
        rows = [dict(gruppe=name, haeufigkeit=n, reichweite=reach, score=.5, schweregrad=2)
                for name, n, reach in [('A', 1, 1), ('B', 1, 1), ('C', 3000, 2)]]
        figure = ui.reach_scatter(rows)
        self.assertEqual(figure.layout.xaxis.type, 'log')
        self.assertEqual(list(figure.data[0].x), [1, 1, 3000])
        self.assertIn('A, B', figure.data[0].customdata[0])
        self.assertEqual(list(figure.data[0].text), ['2 problems', '', ''])
        self.assertEqual(figure.layout.yaxis.dtick, 1)

    def test_sparse_heatmap_uses_complete_integer_legend(self):
        rows = [dict(kind='time', zeit=datetime(2017, 5, 16, tzinfo=timezone.utc), observed_logs=10, n=3),
                dict(kind='cell', zeit=datetime(2017, 5, 16, tzinfo=timezone.utc), resource='A', n=3)]
        figure = ui.resource_heatmap(rows)
        self.assertEqual(list(figure.data[0].colorbar.ticktext), ['0', '1', '2', '3'])
        self.assertLessEqual(figure.layout.height, 250)

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
