"""Echter stdio-/SQL-Nachweis, ohne LLM/API-Key. Start: python -m mcp_server.check."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from mcp_server.evidence import encode

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("corpus_overview", {}),
    ("search_logs", {"query": "data TLB error interrupt", "dataset": "BGL", "limit": 3}),
    ("get_context", {"log_id": "544fd51c-4edc-4780-baae-ba1d80a0acfc", "limit": 30}),
    ("vm_dauer", {"instance_id": "544fd51c-4edc-4780-baae-ba1d80a0acfc", "limit": 4}),
    ("top_patterns", {"team": "HPC Kernel", "dataset": "BGL", "limit": 5}),
    ("pattern_trend", {"template_id": "BGL-0019", "dataset": "BGL", "intervall": "1 week"}),
    ("priority_ranking", {"dataset": "BGL", "group_by": "template", "limit": 5}),
]


async def check(mode="legacy") -> dict:
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "transport": "stdio subprocess",
              "client": "official MCP Python SDK; not a Claude Desktop end-to-end test",
              "requested_mode": mode, "llm_calls": 0, "cases": []}
    # Absichtlich ausserhalb des Repos starten, genau wie ein Desktop-Host.
    with TemporaryDirectory(prefix="logs-mcp-check-") as cwd:
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "run.py")], cwd=cwd)
        async with Client(params, mode=mode, read_timeout_seconds=120) as client:
            report["protocol_version"] = client.protocol_version
            tools = (await client.list_tools()).tools
            report["discovered_tools"] = [tool.name for tool in tools]
            assert set(report["discovered_tools"]) == {name for name, _ in CASES}, "Werkzeuge fehlen"
            report["prompts"] = []
            for prompt in (await client.list_prompts()).prompts:
                response = await client.get_prompt(prompt.name, {"question": "Inspect the historical logs with SQL evidence."})
                assert response.messages, "Prompt ist leer"
                report["prompts"].append(prompt.name)
            for name, args in CASES:
                start = perf_counter()
                response = await client.call_tool(name, args)
                if response.is_error:
                    raise RuntimeError(f"{name}: {response.content[0].text}")
                output = response.structured_content
                resource = await client.read_resource(output["evidence_uri"])
                full = json.loads(resource.contents[0].text)
                assert full["tool"] == name and full["result"]["sql"].strip()
                assert full["result"]["daten"], f"{name}: unerwartet leeres Ergebnis"
                report["cases"].append({"tool": name, "arguments": args, "seconds": round(perf_counter() - start, 3),
                    "resource_roundtrip": True, "response": output, "full_response_bytes": len(resource.contents[0].text.encode("utf-8"))})
            overview = report["cases"][0]["response"]["result"]["daten"]
            counts = {dataset: sum(row["logzeilen_gesamt"] for row in overview if row["dataset"] == dataset)
                      for dataset in ("BGL", "OpenStack")}
            assert counts == {"BGL": 4747963, "OpenStack": 207820}, f"Unvollstaendige Daten: {counts}"
            report["corpus_counts"] = counts
            outputs = {case["tool"]: case["response"]["result"] for case in report["cases"]}
            assert int(outputs["search_logs"]["gesamt_treffer"]) == 152734, "Volltext-Gesamtzahl stimmt nicht"
            vm = outputs["vm_dauer"]["gesuchte_vm"]
            assert (vm["sek"], vm["median_sek"], vm["platz"], vm["gesamt_vms"]) == (41.81, 19.7, 2, 2066)
            assert outputs["priority_ranking"]["daten"][0]["gruppe"] == "BGL-0119", "Reichweiten-Priorisierung stimmt nicht"
            # Erens Korrektur: NULL-request_id-Zeilen des Tracebacks muessen mitkommen.
            traceback = await client.call_tool("get_context", {"log_id": 4793576, "limit": 30})
            assert not traceback.is_error, "Traceback-Abfrage fehlgeschlagen"
            trace_output = traceback.structured_content
            trace_resource = await client.read_resource(trace_output["evidence_uri"])
            trace_raw = json.loads(trace_resource.contents[0].text)["result"]
            ids = {row["id"] for row in trace_raw["daten"]}
            assert {4793576, 4793594, 4793598} <= ids, "Traceback-Kontext verliert Fehlerursache"
            report["regressions"] = {"full_text_count": 152734, "selected_spawn_seconds": vm["sek"],
                "spawn_median_seconds": vm["median_sek"], "spawn_rank": vm["platz"], "spawn_observations": vm["gesamt_vms"],
                "highest_bgl_priority": "BGL-0119", "traceback_context_includes_cause": True,
                "traceback_evidence_uri": trace_output["evidence_uri"], "traceback_sql": trace_raw["sql"],
                "traceback_event": trace_raw["meta"].get("ereignis"),
                "traceback_cause_rows": [row for row in trace_raw["daten"] if row["id"] in {4793594, 4793598}]}
            # Ein kaputter Aufruf muss eine Fehlermeldung sein, keine leere Trefferliste.
            invalid = await client.call_tool("search_logs", {"query": "x", "limit": 99999})
            assert invalid.is_error
            report["invalid_limit_rejected"] = True
    report["status"] = "passed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("legacy", "auto"), default="legacy")
    parser.add_argument("--output", type=Path, default=ROOT / "out" / "mcp-protocol-check.json")
    args = parser.parse_args()
    report = anyio.run(check, args.mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(encode({"status": report["status"], "protocol": report["protocol_version"],
                  "tools": len(report["cases"]), "llm_calls": 0, "report": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
