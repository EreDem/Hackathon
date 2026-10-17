"""Kostenlose Regressionstests für die Schnittstellen von Agent und Team-Werkzeugen."""
import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent.agent import Agent
from agent.budget import Budget
from agent.toolkit import BY_NAME, lade_werkzeuge
from tools import engineer


class IntegrationTests(unittest.TestCase):
    def test_all_tool_signatures_match_agent(self):
        handlers, missing = lade_werkzeuge()
        self.assertEqual(missing, [])
        samples = {
            "search_logs": {"query": "error"},
            "get_context": {"log_id": "544fd51c-4edc-4780-baae-ba1d80a0acfc"},
            "vm_dauer": {}, "top_patterns": {},
            "pattern_trend": {"team": "Cloud Compute", "dataset": "OpenStack", "intervall": "1 hour"},
            "priority_ranking": {"team": "HPC Kernel", "dataset": "BGL", "limit": 5},
        }
        for name, arguments in samples.items():
            with self.subTest(tool=name):
                values = BY_NAME[name].args.model_validate(arguments).model_dump()
                inspect.signature(handlers[name]).bind(**values)

    def test_full_count_does_not_sum_only_top_groups(self):
        def query(sql, params, limit):
            if "GROUP BY" in sql:
                self.assertIn("SUM(COUNT(*)) OVER () AS gesamt_treffer", sql)
                return {"sql": sql, "zeilen": 1, "daten": [{"treffer": 10, "gesamt_treffer": 70}]}
            return {"sql": sql, "zeilen": 1, "daten": [{"id": 1}]}
        with patch.object(engineer, "run_query", side_effect=query):
            result = engineer.search_logs("error", limit=1)
        self.assertEqual(result["gesamt_treffer"], 70)
        self.assertTrue(result["truncated"])
        self.assertIn("GROUP BY", result["zusatz_belege"][0]["sql"])

    def test_empty_context_keeps_executed_sql(self):
        result = {"sql": "SELECT * FROM logs WHERE id = 42", "zeilen": 0, "daten": []}
        with patch.object(engineer, "run_query", return_value=result):
            self.assertEqual(engineer.get_context(42)["sql"], result["sql"])

    def test_analytics_sql_does_not_displace_data(self):
        raw = {"sql": "SELECT " + "x" * 18000, "zeilen": 1, "daten": [{"n": 42}],
               "meta": {"gekuerzt": True, "bereich": {"sql": "SELECT " + "x" * 6000,
                        "zeilen": 1, "daten": [{"logzeilen_gesamt": 100}]}}}
        with TemporaryDirectory() as directory:
            agent = Agent(None, {"top_patterns": lambda **kw: raw}, Budget(Path(directory) / "budget.sqlite3"))
            evidence = []
            result = agent._execute("top_patterns", json.dumps({"team": "HPC Kernel"}), evidence, None)
        self.assertNotIn("fehler", result)
        self.assertEqual(result["daten"], [{"n": 42}])
        self.assertTrue(result["truncated"])
        self.assertEqual(evidence[0]["sql"], raw["sql"])
        self.assertEqual(evidence[0]["meta"]["bereich"]["sql"], raw["meta"]["bereich"]["sql"])

    def test_nested_evidence_is_bounded_without_losing_originals(self):
        rows = [{"id": i, "message": "x" * 900} for i in range(70)]
        raw = {"sql": "SELECT main", "zeilen": 1, "daten": [{"id": 1}],
               "zusatz_belege": [{"sql": "SELECT extra", "zeilen": 70, "daten": rows}]}
        with TemporaryDirectory() as directory:
            agent = Agent(None, {"get_context": lambda **kw: raw}, Budget(Path(directory) / "budget.sqlite3"))
            evidence = []
            result = agent._execute("get_context", '{"log_id": 1}', evidence, None)
        self.assertNotIn("fehler", result)
        self.assertTrue(result["modell_gekuerzt"])
        self.assertLess(len(json.dumps(result)), 16000)
        self.assertEqual(len(evidence[0]["zusatz_belege"][0]["daten"]), 70)
        self.assertTrue(result["zusatz_belege"][0]["modell_gekuerzt"])


if __name__ == "__main__":
    unittest.main()
