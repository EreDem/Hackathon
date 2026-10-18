import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tools import engineer as e


def response(rows, sql="executed SQL"):
    return {"sql": sql, "zeilen": len(rows), "daten": rows}


class EngineerTests(unittest.TestCase):
    def test_invalid_inputs_do_not_query(self):
        cases = [lambda: e.search_logs(""), lambda: e.search_logs("x", modus="sql"),
                 lambda: e.search_logs("x", limit=-1), lambda: e.search_logs("x", limit=True),
                 lambda: e.search_logs("x", dataset="other"), lambda: e.search_logs("x", level="DROP"),
                 lambda: e.search_logs("x", von="2006-01-01", bis="2005-01-01"),
                 lambda: e.get_context(1, fenster_sek=0), lambda: e.get_context(True),
                 lambda: e.vm_dauer(limit=1001)]
        with patch.object(e, "run_query") as query:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    case()
            query.assert_not_called()

    def test_full_count_precedes_group_limit_and_evidence_retained(self):
        groups = [{"treffer": 3, "gesamt_treffer": 150, "gruppen_gesamt": 30} for _ in range(10)]
        with patch.object(e, "run_query", side_effect=[response([{"id": 1}, {"id": 2}]), response(groups, "stats SQL")]) as query:
            result = e.search_logs("x", limit=1)
        self.assertEqual(result["gesamt_treffer"], 150)
        self.assertEqual(result["zeilen"], 1)
        self.assertTrue(result["meta"]["gekuerzt"])
        self.assertTrue(result["meta"]["summary_gekuerzt"])
        self.assertEqual(result["belege"][0]["sql"], "stats SQL")
        self.assertIn("SUM(COUNT(*)) OVER ()", query.call_args_list[1].args[0])
        self.assertEqual(query.call_args_list[0].kwargs["limit"], 2)

    def test_partial_statistics_failure_is_visible(self):
        with patch.object(e, "run_query", side_effect=[response([{"id": 1}]), ConnectionError("offline")]):
            result = e.search_logs("x")
        self.assertNotIn("gesamt_treffer", result)
        self.assertIn("partial", result["warnings"][0])

    def test_fallback_retains_original_query_and_mode(self):
        with patch.object(e, "run_query", side_effect=[response([], "phrase SQL"), response([{"id": 1}]), response([])]):
            result = e.search_logs("two words")
        self.assertEqual(result["meta"]["modus"], "all")
        self.assertEqual(result["belege"][0]["sql"], "phrase SQL")

    def test_context_prioritizes_anchor_then_sorts_chronologically(self):
        anchor = {"id": 9, "dataset": "BGL", "ts": datetime(2005, 6, 4, tzinfo=timezone.utc)}
        rows = [anchor, {"id": 8, "ts": datetime(2005, 6, 3, tzinfo=timezone.utc)},
                {"id": 10, "ts": datetime(2005, 6, 5, tzinfo=timezone.utc)}]
        with patch.object(e, "run_query", side_effect=[response([anchor], "anchor SQL"), response(rows), response([])]) as query:
            result = e.get_context(9, limit=2)
        self.assertEqual([r["id"] for r in result["daten"]], [8, 9])
        self.assertTrue(result["meta"]["gekuerzt"])
        self.assertIn("midplane", result["meta"]["scope"])
        self.assertIn("CASE WHEN l.id=s.id THEN 0", query.call_args_list[1].args[0])
        self.assertIn("ABS(EXTRACT", query.call_args_list[1].args[0])
        self.assertEqual(result["belege"][0]["sql"], "anchor SQL")

    def test_vm_context_keeps_supplementary_queries_and_truncation(self):
        anchor = {"id": 1, "ts": None, "dataset": "OpenStack", "instance_id": "vm", "request_id": "req-a"}
        requests = [{"request_id": "req-a"}, {"request_id": "req-b"}]
        with patch.object(e, "run_query", side_effect=[response([anchor]), response([anchor]),
                        response(requests, "requests SQL"), response([{"id": 1}, {"id": 2}], "timeline SQL")]):
            result = e.get_context(1, limit=1)
        self.assertEqual(len(result["belege"]), 3)
        self.assertEqual(result["belege"][2]["sql"], "timeline SQL")
        self.assertTrue(result["belege"][2]["meta"]["gekuerzt"])
        self.assertEqual(result["request_verlauf"], [{"id": 1}])

    def test_request_context_includes_same_event_lines(self):
        ts = datetime(2017, 5, 16, tzinfo=timezone.utc)
        anchor = {"id": 5, "dataset": "OpenStack", "pid": 2931, "ts": ts, "request_id": "req-a", "instance_id": None}
        traceback_line = {"id": 6, "dataset": "OpenStack", "pid": 2931, "ts": ts, "request_id": None}
        with patch.object(e, "run_query", side_effect=[response([anchor]), response([anchor, traceback_line])]) as query:
            result = e.get_context(5)
        sql = query.call_args_list[1].args[0]
        self.assertIn("l.request_id=s.request_id OR (l.pid=s.pid AND l.ts=s.ts)", sql)
        self.assertIn("WHEN l.dataset='OpenStack' AND (l.pid=s.pid AND l.ts=s.ts) THEN 1", sql)
        self.assertIn("same event", result["meta"]["scope"])
        self.assertEqual(result["meta"]["ereignis"]["zeilen_im_ergebnis"], 2)

    def test_no_anchor_keeps_actual_lookup_sql(self):
        with patch.object(e, "run_query", return_value=response([], "lookup SQL")):
            result = e.get_context(404)
        self.assertEqual(result["sql"], "lookup SQL")

    def test_duration_top_n_and_selected_observation_are_bounded(self):
        rows = [{"log_id": 1, "instance_id": "a", "auswahl": 1, "gesamt_vms": 100},
                {"log_id": 2, "instance_id": "selected", "auswahl": 20, "gesamt_vms": 100}]
        with patch.object(e, "run_query", return_value=response(rows)) as query:
            result = e.vm_dauer("selected", limit=1)
        self.assertEqual(result["gesuchte_vm"]["log_id"], 2)
        self.assertIn("MIN(auswahl)", query.call_args.args[0])
        self.assertEqual(query.call_args.args[1], [1, "selected", 3])
        self.assertTrue(result['meta']['gekuerzt'])


@unittest.skipUnless(os.getenv("ANALYTICS_TEST_DB"), "Requires local SereneDB")
class LiveTracebackContextTests(unittest.TestCase):
    def test_cache_manager_traceback_includes_cause(self):
        # Real case from the product review: the cause sits in traceback lines without request ID.
        header = e.run_query("""SELECT id FROM logs WHERE dataset='OpenStack'
            AND message LIKE %s ORDER BY ts, id LIMIT 1""",
            ["Error during ComputeManager._run_image_cache_manager_pass%"], limit=1)["daten"][0]
        result = e.get_context(header["id"], fenster_sek=60, limit=100)
        event = [r for r in result["daten"] if r["pid"] == result["meta"]["anchor"]["pid"]
                 and r["ts"] == result["meta"]["anchor"]["ts"]]
        self.assertEqual(result["meta"]["ereignis"]["zeilen_im_ergebnis"], 24)
        self.assertEqual(sum(r["request_id"] is None for r in event), 23)
        self.assertTrue(any(r["message"].startswith("InvalidDiskInfo") for r in event))


if __name__ == "__main__":
    unittest.main()
