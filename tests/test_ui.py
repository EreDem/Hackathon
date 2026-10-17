import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from types import ModuleType

from streamlit.testing.v1 import AppTest
from tests import ui_fixtures as f
import ui

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class ChartTests(unittest.TestCase):
    def test_empty_charts_are_valid(self):
        for chart in [ui.timeline([]), ui.pattern_bars([]), ui.trend([]), ui.priority_bars([]),
                      ui.reach_scatter([]), ui.durations([])]:
            self.assertTrue(chart.to_json())

    def test_trend_keeps_zero_and_gap_distinct(self):
        chart = ui.trend(f.TREND['daten'])
        self.assertEqual(list(chart.data[0].y), [5, 0, None, 10, 3])
        self.assertFalse(chart.data[0].connectgaps)

    def test_comparison_groups_and_unknown_reach(self):
        groups = ui.ranking_groups(f.ranking()['daten'])
        self.assertEqual(set(groups), {'BGL:knoten', 'BGL:unbekannt'})
        self.assertEqual(len(ui.reach_scatter(groups['BGL:unbekannt']).data[0].x), 0)
        self.assertEqual(len(ui.reach_scatter(groups['BGL:knoten']).data[0].x), 2)

    def test_nested_evidence_is_retained(self):
        result = {'sql': 'main', 'daten': [], 'meta': {'bereich': f.CATALOG},
                  'belege': [{'name': 'support', 'sql': 'support SQL', 'daten': []}]}
        self.assertEqual([item['sql'] for _, item in ui.evidence_entries(result)],
                         ['main', f.CATALOG['sql'], 'support SQL'])

    def test_person_four_evidence_ids_inputs_and_legacy_support_are_retained(self):
        response = {'text': 'Observed facts [B1].', 'meta': {'status': 'ok'}, 'belege': [
            {'tool': 'search_logs', 'parameter': {'query': 'error'}, 'beleg_id': 'B1',
             'sql': 'SELECT main', 'daten': [], 'zeilen': 0, 'truncated': None,
             'zusatz_belege': [{'zweck': 'Count', 'sql': 'SELECT count(*)', 'daten': [{'n': 5}]}]}]}
        message = ui.agent_message(response)
        record = message['evidence'][0]
        self.assertEqual(record['tool'], 'search_logs')
        self.assertEqual(record['inputs']['query'], 'error')
        self.assertEqual(record['result']['beleg_id'], 'B1')
        self.assertEqual([r['sql'] for _, r in ui.evidence_entries(record['result'])], ['SELECT main', 'SELECT count(*)'])


class AppTests(unittest.TestCase):
    def setUp(self):
        absent_agent = patch.dict('sys.modules', {'agent.agent': None})
        absent_agent.start()
        self.addCleanup(absent_agent.stop)
        responses = {'tools.db.query': f.CATALOG, 'tools.engineer.search_logs': f.SEARCH,
                     'tools.engineer.get_context': f.CONTEXT, 'tools.engineer.vm_dauer': f.DURATIONS,
                     'tools.analytics.top_patterns': f.PATTERNS, 'tools.analytics.pattern_trend': f.TREND,
                     'tools.analytics.priority_ranking': f.ranking()}
        responses.update({'tools.visuals.search_distribution': {
            'sql': 'distribution SQL', 'daten': [
                dict(kind='summary', n=3, missing_resource=0, missing_time=0),
                dict(kind='time', zeit=f.TREND['daten'][0]['zeit'], n=3, observed_logs=10),
                dict(kind='cell', zeit=f.TREND['daten'][0]['zeit'], resource='A', n=3, example_log_id=2)],
            'zeilen': 3, 'meta': {'resource_unit': 'Node', 'filter': {'intervall': '1 day'}}},
            'tools.visuals.period_comparison': {'sql': 'period SQL', 'daten': [], 'zeilen': 0, 'meta': {}}})
        self.mocks = {}
        for name, response in responses.items():
            patcher = patch(name, side_effect=lambda *a, _result=response, **kw: deepcopy(_result))
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        self.app = AppTest.from_file(APP, default_timeout=15).run()
        self.assertFalse(self.app.exception)

    def button(self, label):
        return next(b for b in self.app.button if b.label == label)

    def selectbox(self, label):
        return next(b for b in self.app.selectbox if b.label == label)

    def test_agent_unavailable_and_no_unprompted_search(self):
        self.assertTrue(self.app.chat_input[0].disabled)
        self.mocks['tools.engineer.search_logs'].assert_not_called()
        self.assertTrue(any(b.label == 'Run prepared investigation' for b in self.app.button))

    def test_resource_map_is_explicit_and_cell_opens_context(self):
        self.button('Search evidence').click().run()
        self.mocks['tools.visuals.search_distribution'].assert_not_called()
        self.button('Map all matching logs').click().run()
        self.assertFalse(self.app.exception)
        self.selectbox('Inspect a resource/time cell').select(0).run()
        self.button('Open resource event lens').click().run()
        self.assertFalse(self.app.exception)
        self.mocks['tools.engineer.get_context'].assert_called_once()
        self.app.run()
        self.mocks['tools.visuals.search_distribution'].assert_called_once()

    def test_pattern_comparison_is_explicit_and_reuses_queries(self):
        self.selectbox('Your perspective').select('Team Lead').run()
        self.button('Analyze recurring patterns').click().run()
        before = self.mocks['tools.analytics.pattern_trend'].call_count
        self.button('Compare leading patterns').click().run()
        self.assertFalse(self.app.exception)
        after = self.mocks['tools.analytics.pattern_trend'].call_count
        self.assertEqual(after-before, min(4, len(f.PATTERNS['daten'])))
        self.app.run()
        self.assertEqual(self.mocks['tools.analytics.pattern_trend'].call_count, after)

    def test_manager_comparisons_are_explicit_and_scope_resets(self):
        self.selectbox('Your perspective').select('Manager').run()
        self.mocks['tools.visuals.period_comparison'].assert_not_called()
        self.button('Compare teams and periods').click().run()
        self.assertFalse(self.app.exception)
        self.assertIn('team_comparison', self.app.session_state['results'])
        self.app.run()
        self.mocks['tools.visuals.period_comparison'].assert_called_once()
        self.selectbox('Your perspective').select('Engineer').run()
        self.assertEqual(self.app.session_state['results'], {})

    def test_search_selection_does_not_repeat_queries_on_rerender(self):
        self.button('Search evidence').click().run()
        self.assertFalse(self.app.exception)
        self.selectbox('Inspect a log (keyboard alternative to row selection)').select(2).run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.mocks['tools.engineer.get_context'].call_count, 1)
        self.app.run()
        self.assertEqual(self.mocks['tools.engineer.search_logs'].call_count, 1)
        self.assertEqual(self.mocks['tools.engineer.get_context'].call_count, 1)
        self.assertTrue(any(e.value == 'Event lens' for e in self.app.subheader))

    def test_role_switch_clears_incompatible_results(self):
        self.button('Run prepared investigation').click().run()
        self.selectbox('Your perspective').select('Team Lead').run()
        self.assertEqual(self.app.session_state['results'], {})
        self.button('Analyze recurring patterns').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.mocks['tools.analytics.pattern_trend'].call_count, 1)
        self.app.run()
        self.assertEqual(self.mocks['tools.analytics.pattern_trend'].call_count, 1)
        next(r for r in self.app.radio if r.label == 'Count measure').set_value('Approx. events').run()
        self.assertEqual(self.mocks['tools.analytics.pattern_trend'].call_count, 1)

    def test_scope_apply_clears_results(self):
        self.button('Run prepared investigation').click().run()
        self.selectbox('Ownership team').select('HPC Kernel')
        self.assertIn('search', self.app.session_state['results'])
        self.button('Apply scope').click().run()
        self.assertEqual(self.app.session_state['results'], {})
        self.assertEqual(self.app.session_state['scope']['team'], 'HPC Kernel')
        self.mocks['tools.engineer.search_logs'].assert_called_once()

    def test_manager_ranking_drills_into_context(self):
        self.selectbox('Your perspective').select('Manager').run()
        self.button('Build priority board').click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(any(e.value == 'Insufficient reach data' for e in self.app.subheader))
        self.button('Investigate supporting logs').click().run()
        self.assertFalse(self.app.exception)
        self.mocks['tools.engineer.get_context'].assert_called_once()

    def test_openstack_duration_view(self):
        self.selectbox('Dataset').select('OpenStack').run()
        self.button('Compare spawn durations').click().run()
        self.assertFalse(self.app.exception)
        self.mocks['tools.engineer.vm_dauer'].assert_called_once()

    def test_db_failure_remains_a_usable_page(self):
        self.mocks['tools.db.query'].side_effect = ConnectionError('fixture offline')
        self.button('Reconnect / refresh data').click().run()
        self.assertFalse(self.app.exception)
        self.assertIsNone(self.app.session_state['scope'])
        self.assertTrue(self.app.chat_input[0].disabled)

    def test_failed_refresh_does_not_keep_old_results(self):
        self.button('Search evidence').click().run()
        self.mocks['tools.engineer.search_logs'].side_effect = ConnectionError('fixture offline')
        self.button('Search evidence').click().run()
        self.assertNotIn('search', self.app.session_state['results'])
        self.assertTrue(self.app.error)

    def test_agent_contract_passes_english_scope_and_keeps_evidence(self):
        from unittest.mock import Mock
        agent = ModuleType('agent.agent')
        agent.antworte = Mock(return_value={'text': 'Observed facts. Possible cause. Next check.',
                                           'belege': [deepcopy(f.SEARCH)]})
        with patch.dict('sys.modules', {'agent.agent': agent}):
            self.app.run()
            self.assertFalse(self.app.chat_input[0].disabled)
            self.button('Ask the prepared question').click().run()
        self.assertFalse(self.app.exception)
        inputs = agent.antworte.call_args.kwargs
        self.assertEqual(inputs['rolle'], 'Engineer')
        self.assertEqual(inputs['language'], 'en')
        self.assertEqual(inputs['scope']['dataset'], 'BGL')
        self.assertEqual(len(self.app.session_state['conversation']), 2)
        self.assertEqual(self.app.session_state['conversation'][1]['evidence'][0]['result']['sql'], f.SEARCH['sql'])

    def test_agent_failure_is_not_an_empty_answer(self):
        from unittest.mock import Mock
        agent = ModuleType('agent.agent')
        agent.antworte = Mock(side_effect=ConnectionError('fixture failed'))
        with patch.dict('sys.modules', {'agent.agent': agent}):
            self.app.run()
            self.button('Ask the prepared question').click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.session_state['conversation'], [])

    def test_agent_status_failure_preserves_evidence_without_fake_answer(self):
        from unittest.mock import Mock
        agent = ModuleType('agent.agent')
        agent.antworte = Mock(return_value={'text': 'Budgetfehler', 'belege': [deepcopy(f.SEARCH)],
                                           'meta': {'status': 'budgetlimit'}})
        with patch.dict('sys.modules', {'agent.agent': agent}):
            self.app.run()
            self.button('Ask the prepared question').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['conversation'], [])
        self.assertEqual(len(self.app.session_state['agent_issue']['evidence']), 1)
        self.assertTrue(any('budget' in w.value.lower() for w in self.app.warning))

    def test_installed_agent_without_key_disables_chat(self):
        from unittest.mock import Mock
        agent = ModuleType('agent.agent')
        agent.antworte = Mock()
        agent.configuration_status = Mock(return_value={'configured': False, 'key_configured': False})
        with patch.dict('sys.modules', {'agent.agent': agent}):
            self.app.run()
        self.assertTrue(self.app.chat_input[0].disabled)
        agent.antworte.assert_not_called()


if __name__ == '__main__':
    unittest.main()
