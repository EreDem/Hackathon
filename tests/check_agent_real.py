"""Abnahme des Agent-Anschlusses auf echten Logs; OpenAI nur mit --live.

    python -m tests.check_agent_real
    python -m tests.check_agent_real --live

Ergebnisse und vollständige Belege: out/agent-validation.json (nicht im Git).
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from agent.agent import Agent, antworte
from agent.budget import Budget
from agent.toolkit import lade_werkzeuge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Drei kostenpflichtige OpenAI-Falltests ausführen")
    args = parser.parse_args()
    handlers, missing = lade_werkzeuge()
    assert not missing, f"Werkzeuge fehlen: {missing}"
    agent = Agent(None, handlers, Budget(Path('.agent-usage.sqlite3')))
    vm = "544fd51c-4edc-4780-baae-ba1d80a0acfc"
    calls = {
        "search_logs": {"query": "data TLB error interrupt", "dataset": "BGL", "limit": 5},
        "get_context": {"log_id": vm},
        "vm_dauer": {"instance_id": vm},
        "top_patterns": {"team": "Cloud Compute", "limit": 5},
        "pattern_trend": {"team": "Cloud Compute", "dataset": "OpenStack", "intervall": "1 hour"},
        "priority_ranking": {"group_by": "team", "limit": 20},
    }
    report = {"erstellt": datetime.now(timezone.utc).isoformat(), "belege": [], "modellansichten": {}, "live": []}
    try:
        for name, values in calls.items():
            result = agent._execute(name, json.dumps(values), report["belege"], None)
            report["modellansichten"][name] = result
            assert "fehler" not in result, f"{name}: {result}"
            assert result["daten"], f"{name}: keine sichtbaren Daten"
            print(f"OK {name}: {result['modell_zeilen']} Modellzeilen", flush=True)
        search = report["modellansichten"]["search_logs"]
        assert search["gesamt_treffer"] == 152734
        assert report["modellansichten"]["get_context"]["zeilen"] == 25
        duration = report["modellansichten"]["vm_dauer"]["gesuchte_vm"]
        assert round(duration["sek"], 1) == 41.8 and duration["platz"] == 2
        assert duration["gesamt_vms"] == 2066
        slowest = agent._execute("vm_dauer", json.dumps({"limit": 4}), report["belege"], None)
        assert "fehler" not in slowest
        labels = Path("data/OpenStack/anomaly_labels.txt").read_text().splitlines()
        known = {line.strip() for line in labels if len(line.strip()) == 36}
        assert {row["instance_id"] for row in slowest["daten"]} == known
        report["vier_anomalie_vms_erkannt"] = True
        ranking = report["modellansichten"]["priority_ranking"]
        assert {r["dataset"] for r in ranking["daten"]} == {"BGL", "OpenStack"}
        assert sum(r["logzeilen_gesamt"] for r in ranking["meta"]["bereich"]["daten"]) == 4955783
        report["anschluss_bestanden"] = True
        if args.live:
            scenarios = [
                ("Engineer", None, f"Warum ist VM {vm} auffällig? Prüfe Dauer und Kontext und empfehle einen nächsten Diagnoseschritt."),
                ("Team Lead", "Cloud Compute", "Was kommt bei uns immer wieder? Unterscheide Logzeilen und Ereignisse und prüfe die Entwicklung im historischen Zeitraum."),
                ("Manager", None, "Welches Problem sollten wir zuerst untersuchen? Berücksichtige BGL und OpenStack und erkläre die Grenzen des Vergleichs."),
            ]
            for role, team, question in scenarios:
                result = antworte(role, team, question, [])
                report["live"].append({"rolle": role, "team": team, "frage": question, **result})
                print(f"{role}: {result['meta']['status']}, Kosten ~{result['meta'].get('kosten_usd_geschaetzt', 0):.5f} USD", flush=True)
                print(result["text"], flush=True)
            report["live_ablauf_bestanden"] = all(r["meta"]["status"] == "ok" for r in report["live"])
    finally:
        output = Path("out/agent-validation.json")
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        print(f"Belege: {output}", flush=True)
    return 0 if report.get("anschluss_bestanden") and report.get("live_ablauf_bestanden", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
