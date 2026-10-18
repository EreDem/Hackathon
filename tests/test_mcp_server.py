"""Kostenlose Protokolltests mit klar kuenstlichen Daten, ohne Datenbank/LLM."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

try:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
except ImportError:
    Client = None

if Client is not None:
    from mcp_server.evidence import EvidenceStore, PREVIEW_BYTES, encode, preview
    from mcp_server.server import create_server, DESCRIPTIONS, GUIDE_URI


def fixture(**kwargs):
    return {"sql": "-- Kuenstlicher Test: keine Datenbankabfrage", "zeilen": 1,
            "daten": [{"id": 42, "message": "Kuenstlicher Test"}], "meta": {"gesamt_treffer": 123}}


@unittest.skipIf(Client is None, "Optionale requirements-mcp.txt nicht installiert")
class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_three_role_prompts_in_both_protocol_modes(self):
        for mode in ("auto", "legacy"):
            async with Client(create_server({"search_logs": fixture}), mode=mode) as client:
                tools = (await client.list_tools()).tools
                self.assertEqual({tool.name for tool in tools}, set(DESCRIPTIONS))
                for tool in tools:
                    self.assertFalse(tool.input_schema["additionalProperties"])
                    self.assertTrue(tool.annotations.read_only_hint)
                    self.assertFalse(tool.annotations.destructive_hint)
                    self.assertGreater(len(tool.description), 100)
                prompts = (await client.list_prompts()).prompts
                self.assertEqual(len(prompts), 3)
                for prompt in prompts:
                    result = await client.get_prompt(prompt.name, {"question": "Testfrage", "dataset": "BGL"})
                    self.assertIn("UNTRUSTED DATA", result.messages[0].content.text)
                    self.assertIn("Testfrage", result.messages[0].content.text)
                guide = await client.read_resource(GUIDE_URI)
                self.assertIn("SQL calculates", guide.contents[0].text)

    async def test_strict_inputs_rejected_before_database(self):
        called = []

        def handler(**kwargs):
            called.append(kwargs)
            return fixture()

        async with Client(create_server({"search_logs": handler, "pattern_trend": handler})) as client:
            for name, args in (("search_logs", {"query": "x", "limit": 1000}),
                               ("search_logs", {"query": "x", "limit": True}),
                               ("search_logs", {"query": "x", "sql": "DROP TABLE logs"}),
                               ("search_logs", {"query": "x", "dataset": "Other"}),
                               ("search_logs", {"query": "x", "von": "tomorrow"}),
                               ("search_logs", {"query": "x", "von": "2017-05-17", "bis": "2017-05-14"}),
                               ("get_context", {"log_id": "../.env"}),
                               ("pattern_trend", {}), ("execute_sql", {"sql": "SELECT 1"})):
                with self.subTest(name=name, args=args):
                    result = await client.call_tool(name, args)
                    self.assertTrue(result.is_error)
            self.assertEqual(called, [])

    async def test_tool_defaults_and_exact_evidence_roundtrip(self):
        called = []

        def handler(**kwargs):
            called.append(kwargs)
            return fixture()

        async with Client(create_server({"search_logs": handler})) as client:
            result = await client.call_tool("search_logs", {"query": "Test"})
            self.assertFalse(result.is_error)
            output = result.structured_content
            self.assertEqual(called[0]["limit"], 20)
            resource = await client.read_resource(output["evidence_uri"])
            full = json.loads(resource.contents[0].text)
            self.assertEqual(full["result"], fixture())
            self.assertEqual(output["result"], fixture())
            self.assertFalse(output["view"]["truncated"])
            self.assertIn(output["evidence_uri"], [r.uri for r in (await client.list_resources(cache_mode="bypass")).resources])
            with self.assertRaises(Exception):
                await client.read_resource("file:///D:/Projekte/Hackathon/.env")

    async def test_failures_are_not_zero_matches_or_secret_disclosures(self):
        def broken(**kwargs):
            raise RuntimeError("password=DO_NOT_DISCLOSE sk-secret-value")

        async with Client(create_server({"search_logs": broken})) as client:
            result = await client.call_tool("search_logs", {"query": "Test"})
            self.assertTrue(result.is_error)
            text = result.content[0].text
            self.assertIn("query_failed", text)
            self.assertNotIn("DO_NOT_DISCLOSE", text)
            self.assertNotIn("sk-secret", text)
            result = await client.call_tool("vm_dauer", {})
            self.assertTrue(result.is_error)
            self.assertIn("tool_unavailable", result.content[0].text)

    async def test_large_result_has_bounded_preview_and_exact_resource(self):
        raw = {"sql": "SELECT synthetic_test", "zeilen": 100,
               "daten": [{"id": n, "message": "untrusted log " * 150} for n in range(100)],
               "meta": {"gekuerzt": True, "matching_lines": 10000}}
        async with Client(create_server({"search_logs": lambda **kw: raw})) as client:
            output = (await client.call_tool("search_logs", {"query": "test"})).structured_content
            self.assertTrue(output["view"]["truncated"])
            self.assertEqual(output["result"]["zeilen"], 100)
            self.assertEqual(output["result"]["meta"]["matching_lines"], 10000)
            self.assertLessEqual(len(encode({"result": output["result"], "view": output["view"]}).encode()), PREVIEW_BYTES)
            resource = await client.read_resource(output["evidence_uri"])
            self.assertEqual(json.loads(resource.contents[0].text)["result"], raw)

    async def test_cache_is_bounded_and_expired_resource_is_explicit_error(self):
        store = EvidenceStore(max_items=1, max_bytes=5000)
        async with Client(create_server({"search_logs": fixture}, store=store)) as client:
            first = (await client.call_tool("search_logs", {"query": "first"})).structured_content["evidence_uri"]
            second = (await client.call_tool("search_logs", {"query": "second"})).structured_content["evidence_uri"]
            with self.assertRaises(Exception):
                await client.read_resource(first)
            self.assertIn("Kuenstlich", (await client.read_resource(second)).contents[0].text)
            self.assertEqual(len(store.items), 1)
            self.assertLessEqual(store.byte_count, 5000)
            with self.assertRaises(ValueError):
                store.put("test", {}, {"data": "x" * 6000})

    async def test_invalid_prompt_and_malformed_handler_are_errors(self):
        async with Client(create_server({"search_logs": lambda **kw: {"daten": []}})) as client:
            self.assertTrue((await client.call_tool("search_logs", {"query": "test"})).is_error)
            for args in ({}, {"question": "x", "dataset": "Other"}, {"question": "x", "sql": "x"}):
                with self.assertRaises(Exception):
                    await client.get_prompt("engineer_investigation", args)

    async def test_oversized_response_is_explicit_error(self):
        raw = {"sql": "SELECT synthetic_test", "zeilen": 1, "daten": [{"message": "x" * (1024 * 1024)}]}
        async with Client(create_server({"search_logs": lambda **kw: raw})) as client:
            result = await client.call_tool("search_logs", {"query": "test"})
            self.assertTrue(result.is_error)
            self.assertIn("result_too_large", result.content[0].text)

    async def test_real_stdio_subprocess_outside_repo_without_database_call(self):
        launcher = Path(__file__).resolve().parents[1] / "mcp_server" / "run.py"
        with TemporaryDirectory() as other_cwd:
            params = StdioServerParameters(command=sys.executable, args=[str(launcher)], cwd=other_cwd)
            for mode in ("legacy", "auto"):
                async with Client(params, mode=mode, read_timeout_seconds=30) as client:
                    self.assertEqual(len((await client.list_tools()).tools), 7)
                    self.assertEqual(len((await client.list_prompts()).prompts), 3)
                    self.assertIn("SQL calculates", (await client.read_resource(GUIDE_URI)).contents[0].text)


if __name__ == "__main__":
    unittest.main()
