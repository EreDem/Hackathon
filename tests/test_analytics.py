"""Ohne DB: python -m unittest tests.test_analytics -v

Mit echter SereneDB (CTE-Fixtures, keine Tabellenänderungen):
    $env:ANALYTICS_TEST_DB='1'
    python -m unittest tests.test_analytics -v
"""
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from types import SimpleNamespace

from tools import analytics as a


class ContractTests(unittest.TestCase):
    def test_invalid_inputs_do_not_query(self):
        calls = [
            lambda: a.top_patterns(None, dataset="other"),
            lambda: a.top_patterns(None, limit=0),
            lambda: a.top_patterns(None, limit=True),
            lambda: a.top_patterns(None, limit=1001),
            lambda: a.top_patterns(""),
            lambda: a.top_patterns(None, von="wrong"),
            lambda: a.top_patterns(None, von="2020-02-02", bis="2020-01-01"),
            lambda: a.pattern_trend(),
            lambda: a.pattern_trend(team="x", intervall="1 hour; DROP TABLE logs"),
            lambda: a.pattern_trend(template_id="OS-1", dataset="BGL"),
            lambda: a.priority_ranking(group_by="anything"),
        ]
        with patch.object(a, "_query") as query:
            for call in calls:
                with self.subTest(call=call), self.assertRaises(ValueError):
                    call()
            query.assert_not_called()

    def test_parameters_and_evidence(self):
        team = "x' OR 1=1 --"
        def query(sql, params, limit):
            self.assertNotIn(team, sql)
            self.assertIn(team, params)
            self.assertNotIn("now()", sql.lower())
            return {"sql": "executed SQL", "zeilen": 0, "daten": []}
        with patch.object(a, "_query", side_effect=query):
            result = a.top_patterns(team, von="2005-01-01", bis="2006-01-01")
        self.assertEqual(result["sql"], "executed SQL")
        self.assertEqual(result["meta"]["bereich"]["sql"], "executed SQL")
        self.assertEqual(result["daten"], [])
        self.assertFalse(result["meta"]["gekuerzt"])
        json.dumps(result, default=str)

    def test_truncation_and_fetch_limit(self):
        responses = [
            {"sql": "main", "zeilen": 2, "daten": [{"_gesamt": 12, "n": 8}, {"_gesamt": 12, "n": 7}]},
            {"sql": "scope", "zeilen": 0, "daten": []},
        ]
        with patch.object(a, "_query", side_effect=responses) as query:
            r = a.top_patterns(None, limit=1)
        self.assertEqual(query.call_args_list[0].args[-1], 2)
        self.assertEqual(r["daten"], [{"n": 8}])
        self.assertEqual(r["zeilen"], 1)
        self.assertEqual(r["meta"]["gruppen_gesamt"], 12)
        self.assertTrue(r["meta"]["gekuerzt"])

    def test_db_failures_are_not_empty_results(self):
        with patch.object(a, "_query", side_effect=ConnectionError("offline")):
            with self.assertRaises(ConnectionError):
                a.priority_ranking()

    def test_missing_helper_is_explicit(self):
        with patch.object(a, "import_module", side_effect=ModuleNotFoundError(name="tools.db")):
            with self.assertRaisesRegex(RuntimeError, "Bereich 2"):
                a.top_patterns(None)

    def test_timezone_normalization(self):
        self.assertEqual(a._date("2005-06-03T02:00:00+02:00", "von"),
                         datetime(2005, 6, 3, tzinfo=timezone.utc))

    def test_shared_helper_contract(self):
        from unittest.mock import Mock
        query = Mock(return_value={"sql": "executed", "daten": [], "zeilen": 0})
        with patch.object(a, "import_module", return_value=SimpleNamespace(query=query)):
            result = a._query("SELECT %s", [12], 17)
        query.assert_called_once_with("SELECT %s", params=[12], limit=17)
        self.assertEqual(result["sql"], "executed")


@unittest.skipUnless(os.getenv("ANALYTICS_TEST_DB") == "1", "SereneDB-Test explizit mit ANALYTICS_TEST_DB=1 aktivieren")
class SereneFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.analytics_support import connect, SereneQuery, fixture_ctes
        cls.conn = connect()
        cls.query = SereneQuery(cls.conn, fixture_ctes())

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.mock = patch.object(a, "_query", self.query)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def test_templates_tracebacks_and_default_levels(self):
        result = a.top_patterns(None, limit=100)
        data = {r["template_id"]: r for r in result["daten"]}
        self.assertNotIn("BGL-WARN", data)
        self.assertNotIn("OS-INFO", data)
        self.assertIn("OS-WARN", data)
        self.assertEqual(data["OS-B"]["n"], 2)
        self.assertEqual(data["OS-B"]["ereignisse"], 2)
        self.assertEqual(data["OS-B"]["problem_template_ids"], ["OS-A"])
        self.assertEqual(data["BGL-UNKNOWN"]["knoten"], 0)
        self.assertEqual(data["OS-MISSING"]["ereignisse"], 2)
        counts = {r["dataset"]: r["logzeilen_gesamt"] for r in result["meta"]["bereich"]["daten"]}
        self.assertEqual(counts, {"BGL": 13, "OpenStack": 11})

    def test_filters_and_inclusive_time(self):
        r = a.top_patterns("HPC Kernel", dataset="BGL", von="2005-06-03", bis="2005-06-03")
        self.assertEqual(sum(x["n"] for x in r["daten"]), 2)
        self.assertTrue(all(x["team"] == "HPC Kernel" for x in r["daten"]))
        self.assertEqual(a.top_patterns("missing")["daten"], [])

    def test_trend_zero_is_different_from_gap(self):
        r = a.pattern_trend(template_id="BGL-A", team="HPC Kernel")
        days = {x["zeit"].day: x for x in r["daten"]}
        self.assertEqual(days[4]["n"], 0)
        self.assertFalse(days[4]["datenluecke"])
        self.assertIsNone(days[6]["n"])
        self.assertTrue(days[6]["datenluecke"])
        self.assertEqual(days[7]["n"], 0)

    def test_hourly_events_and_scope(self):
        r = a.pattern_trend(team="Cloud Compute", intervall="1 hour")
        hours = {x["zeit"].hour: x for x in r["daten"]}
        self.assertEqual((hours[0]["n"], hours[0]["ereignisse"]), (3, 1))
        self.assertEqual(hours[3]["n"], 0)
        self.assertEqual(a.pattern_trend(template_id="OS-A", team="HPC Kernel")["daten"], [])

    def test_weekly_and_explicit_empty_edges(self):
        r = a.pattern_trend(team="HPC Kernel", intervall="1 week",
                            von="2005-05-20", bis="2005-06-20")
        self.assertTrue(r["daten"][0]["datenluecke"])
        self.assertTrue(r["daten"][-1]["datenluecke"])
        self.assertEqual(sum(x["n"] or 0 for x in r["daten"]), 11)

    def test_rank_breadth_and_limit_independence(self):
        kwargs = dict(dataset="BGL", von="2005-06-03", bis="2005-06-05T01:00:00Z")
        all_rows = a.priority_ranking(**kwargs)["daten"]
        by_key = {r["gruppe"]: r for r in all_rows}
        self.assertAlmostEqual(by_key["BGL-A"]["score"], 2.0)
        self.assertAlmostEqual(by_key["BGL-B"]["score"], 3.0)
        self.assertLess(by_key["BGL-B"]["rang"], by_key["BGL-A"]["rang"])
        unknown = by_key["BGL-UNKNOWN"]
        self.assertIsNone(unknown["score"])
        self.assertIsNone(unknown["rang"])
        short = a.priority_ranking(**kwargs, limit=1)
        self.assertEqual(short["daten"][0]["score"], all_rows[0]["score"])
        self.assertTrue(short["meta"]["gekuerzt"])

    def test_openstack_ranking_deduplicates(self):
        r = a.priority_ranking(dataset="OpenStack")
        rows = {x["gruppe"]: x for x in r["daten"]}
        self.assertNotIn("OS-B", rows)
        self.assertNotIn("OS-C", rows)
        self.assertEqual(rows["OS-A"]["template_ids"], ["OS-A", "OS-B", "OS-C"])
        self.assertEqual((rows["OS-A"]["n"], rows["OS-A"]["haeufigkeit"]), (6, 2))
        self.assertEqual(rows["OS-A"]["reichweite_typ"], "requests")
        self.assertEqual(rows["OS-WARN"]["reichweite_typ"], "vms")
        self.assertIsNone(rows["OS-MISSING"]["score"])
        teams = a.priority_ranking(group_by="team", dataset="OpenStack")["daten"]
        self.assertEqual((teams[0]["n"], teams[0]["haeufigkeit"]), (10, 6))

    def test_trend_clamp_and_zero_duration(self):
        early = a.priority_ranking(dataset="BGL", von="2005-06-03", bis="2006-01-01")["daten"]
        self.assertTrue(all(x["trendfaktor"] == 0.5 for x in early))
        late = a.priority_ranking(dataset="BGL", von="2000-01-01", bis="2005-06-07")["daten"]
        self.assertTrue(all(x["trendfaktor"] == 1.5 for x in late))
        point = a.priority_ranking(dataset="BGL", von="2005-06-03", bis="2005-06-03")["daten"]
        self.assertTrue(all(x["trendfaktor"] == 1 for x in point))

    def test_midpoint_is_second_half(self):
        r = a.priority_ranking(dataset="BGL", von="2005-06-03", bis="2005-06-05")
        b = next(x for x in r["daten"] if x["gruppe"] == "BGL-B")
        self.assertEqual((b["erste_haelfte"], b["zweite_haelfte"]), (1, 2))

    def test_trend_cap(self):
        r = a.pattern_trend(team="HPC Kernel", intervall="1 hour", von="2000-01-01", bis="2005-06-07")
        self.assertEqual(r["zeilen"], 10000)
        self.assertTrue(r["meta"]["gekuerzt"])
        self.assertGreater(r["meta"]["gruppen_gesamt"], 10000)

    def test_error_representative_wins_over_earlier_warning(self):
        from tests.analytics_support import SereneQuery, fixture_ctes
        extra = [(0, "OpenStack", "2017-05-14 00:00Z", "WARN", "compute",
                  None, 42, "req-0", None, None, "OS-EARLY-WARN")]
        with patch.object(a, "_query", SereneQuery(self.conn, fixture_ctes(extra))):
            result = a.top_patterns("Cloud Compute", limit=100)
        warning = next(r for r in result["daten"] if r["template_id"] == "OS-EARLY-WARN")
        self.assertEqual(warning["problem_template_ids"], ["OS-A"])

    def test_missing_timestamps_do_not_merge(self):
        from tests.analytics_support import SereneQuery, fixture_ctes
        extra = [(id_, "OpenStack", None, "ERROR", "compute", None,
                  99, None, None, None, "OS-NO-TIME") for id_ in [100, 101]]
        with patch.object(a, "_query", SereneQuery(self.conn, fixture_ctes(extra))):
            result = a.priority_ranking(dataset="OpenStack")
        row = next(r for r in result["daten"] if r["gruppe"] == "OS-NO-TIME")
        self.assertEqual(row["ereignisse"], 2)
        self.assertEqual(row["ohne_zeitstempel"], 2)
        self.assertEqual(row["trendfaktor"], 1)
        self.assertIsNone(row["score"])

    def test_unknown_reach_is_after_scored_results(self):
        rows = a.priority_ranking(dataset="OpenStack")["daten"]
        self.assertEqual(rows[-1]["status"], "nicht bewertbar")
        self.assertTrue(all(r["score"] is not None for r in rows[:-1]))


if __name__ == "__main__":
    unittest.main()
