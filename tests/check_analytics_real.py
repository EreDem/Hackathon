"""Read-only-Abnahme auf vollständig geladenen BGL-/OpenStack-Daten.

    python -m tests.check_analytics_real

Schreibt SQL, Ergebnisse, Laufzeiten und Prüfbefunde nach
out/analytics-validation.json (durch die vorhandene .gitignore ausgeschlossen).
Ohne tools.db wird ausschließlich für diesen Test ein echter SereneDB-Transport
eingesetzt. Eine bestandene SQL-Abnahme ersetzt dann nicht den Integrationstest.
"""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools import analytics
from tests.analytics_support import SereneQuery, connect


def main():
    conn = connect()
    query = SereneQuery(conn)
    shared = importlib.util.find_spec("tools.db") is not None
    report = {"erstellt": datetime.now(timezone.utc).isoformat(),
              "transport": "tools.db" if shared else "Testadapter mit echtem SereneDB/ClientCursor",
              "gemeinsamer_helfer_integriert": shared, "pruefungen": [], "tools": {}}

    def check(name, passed, actual):
        report["pruefungen"].append({"name": name, "bestanden": bool(passed), "ist": actual})
        print(("OK " if passed else "FEHLER ") + name, flush=True)

    try:
        report["server"] = query("SELECT version() AS version")["daten"]
        totals = query("SELECT dataset, COUNT(*) AS n, COUNT(DISTINCT template_id) AS templates, SUM(CASE WHEN parsed THEN 0 ELSE 1 END) AS unparsed FROM logs GROUP BY dataset")["daten"]
        by_dataset = {r["dataset"]: r for r in totals}
        check("Vollständige Datensätze und Templates", all(
            by_dataset.get(ds, {}).get("n") == n and by_dataset[ds]["templates"] == t
            and by_dataset[ds]["unparsed"] == 0
            for ds, n, t in [("BGL", 4747963, 399), ("OpenStack", 207820, 71)]), totals)
        missing = query("SELECT COUNT(*) AS n FROM logs l LEFT JOIN ownership o ON o.dataset=l.dataset AND o.component=l.component WHERE o.team IS NULL")["daten"][0]["n"]
        check("Vollständige Ownership", missing == 0, missing)
        duplicates = query("SELECT dataset, component, COUNT(*) AS n FROM ownership GROUP BY dataset, component HAVING COUNT(*) > 1")["daten"]
        check("Eindeutige Ownership", not duplicates, duplicates)

        # Produktiv bleibt tools.db die einzige DB-Abhängigkeit. Der Patch lebt
        # nur innerhalb dieser Testausführung und ändert keine Repository-Datei.
        target = analytics._query if shared else query
        with patch.object(analytics, "_query", target):
            calls = {
                "top_kernel": lambda: analytics.top_patterns("HPC Kernel", limit=1000),
                "top_compute": lambda: analytics.top_patterns("Cloud Compute", limit=1000),
                "ranking_template": lambda: analytics.priority_ranking(limit=1000),
                "ranking_team": lambda: analytics.priority_ranking(group_by="team", limit=1000),
                "trend_bgl": lambda: analytics.pattern_trend(template_id="BGL-0019"),
                "trend_openstack": lambda: analytics.pattern_trend(team="Cloud Compute", intervall="1 hour"),
            }
            for name, call in calls.items():
                report["tools"][name] = call()
                print(f"Ausgeführt: {name} ({report['tools'][name]['meta']['laufzeit_sek']:.3f} s)", flush=True)
            short = analytics.priority_ranking(limit=1)
            report["tools"]["ranking_limit_1"] = short

        result = report["tools"]
        patterns = {r["template_id"]: r for r in result["top_kernel"]["daten"]}
        check("BGL-0019: 152734 Fehlerzeilen", patterns["BGL-0019"]["n"] == 152734, patterns["BGL-0019"])
        check("BGL-0119: 63491 Fehlerzeilen, 22529 Knoten",
              patterns["BGL-0119"]["n"] == 63491 and patterns["BGL-0119"]["knoten"] == 22529, patterns["BGL-0119"])
        # Der Importbericht enthält auch zwei INFO-Zeilen dieses Templates.
        report["bgl_0119_level"] = query("SELECT level, COUNT(*) AS n FROM logs WHERE template_id='BGL-0119' GROUP BY level ORDER BY level")["daten"]
        rank = {r["gruppe"]: r for r in result["ranking_template"]["daten"]}
        check("Breite BGL-Störung vor konzentriertem Muster",
              rank["BGL-0119"]["rang"] < rank["BGL-0019"]["rang"],
              {k: {x: rank[k][x] for x in ["score", "rang", "knoten"]} for k in ["BGL-0119", "BGL-0019"]})
        cloud = query("SELECT COUNT(*) AS n, COUNT(DISTINCT (l.pid, l.ts)) AS ereignisse FROM logs l JOIN ownership o ON o.dataset=l.dataset AND o.component=l.component WHERE o.team='Cloud Compute' AND l.level IN ('ERROR','FATAL')")["daten"][0]
        check("Cloud Compute: 192 ERROR-Zeilen, acht Ereignisse", cloud == {"n": 192, "ereignisse": 8}, cloud)
        problem = rank["OS-0045"]
        check("Tracebacks im Ranking zu einem Problem zusammengeführt",
              problem["n"] == 192 and problem["ereignisse"] == 8
              and "OS-0063" in problem["template_ids"] and "OS-0063" not in rank, problem)

        control = query("""SELECT l.dataset, o.team, COUNT(*) AS n,
            CASE WHEN l.dataset='BGL' THEN COUNT(*) ELSE COUNT(DISTINCT (l.pid, l.ts)) END AS ereignisse
            FROM logs l JOIN ownership o ON o.dataset=l.dataset AND o.component=l.component
            WHERE (l.dataset='BGL' AND l.level IN ('ERROR','FATAL'))
               OR (l.dataset='OpenStack' AND l.level IN ('WARN','ERROR','FATAL'))
            GROUP BY l.dataset,o.team ORDER BY l.dataset,o.team""")["daten"]
        teams = {(r["dataset"], r["gruppe"]): r for r in result["ranking_team"]["daten"]}
        check("Teamzahlen stimmen mit unabhängiger Kontrollabfrage überein",
              all(teams[(r["dataset"], r["team"])]["n"] == r["n"]
                  and teams[(r["dataset"], r["team"])]["ereignisse"] == r["ereignisse"] for r in control), control)
        check("Zeitreihe BGL summiert auf vollständige Musterzahl",
              sum(r["n"] or 0 for r in result["trend_bgl"]["daten"]) == 152734, 152734)
        compute = teams[("OpenStack", "Cloud Compute")]
        trend_events = sum(r["ereignisse"] or 0 for r in result["trend_openstack"]["daten"])
        check("Zeitreihe OpenStack summiert auf deduplizierte Teamzahl", trend_events == compute["ereignisse"], trend_events)
        check("Score unabhängig vom Rückgabelimit",
              short["meta"]["gekuerzt"] and short["daten"][0]["score"] == result["ranking_template"]["daten"][0]["score"],
              short["daten"][0]["score"])
        scope_total = sum(r["logzeilen_gesamt"] for r in result["ranking_team"]["meta"]["bereich"]["daten"])
        check("Bereichsstatistik berücksichtigt alle 4955783 Zeilen", scope_total == 4955783, scope_total)
        report["sql_abnahme_bestanden"] = all(c["bestanden"] for c in report["pruefungen"])
    except Exception as exc:
        report["sql_abnahme_bestanden"] = False
        report["fehler"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["kontrollabfragen"] = query.evidence
        output = Path("out/analytics-validation.json")
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
        conn.close()
        print(f"Belege: {output}")
    return 0 if report["sql_abnahme_bestanden"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
