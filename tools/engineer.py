from __future__ import annotations

# Import mit Alias, damit es keine Kollision mit dem Parameter 'query' gibt!
from tools.db import query as run_query


def _baue_volltext_bedingung(suchtext: str, modus: str) -> tuple[str, object]:
    """Erzeugt den passenden Volltext-Ausdruck für SereneDB (ts_phrase, ts_all, ts_any)."""
    worte = [w for w in suchtext.strip().split() if w]
    if modus == "all" and len(worte) > 1:
        return "i.message @@ ts_all(%s)", worte
    if modus == "any" and len(worte) > 1:
        return "i.message @@ ts_any(%s)", worte
    return "i.message @@ ts_phrase(%s)", suchtext.strip()


def _baue_filter(
    suchtext: str,
    modus: str,
    dataset: str | None,
    level: str | list[str] | None,
    team: str | None,
    von: str | None,
    bis: str | None,
) -> tuple[str, list]:
    """Baut die WHERE-Klausel nur für tatsächlich gesetzte Filter zusammen."""
    ft_sql, ft_param = _baue_volltext_bedingung(suchtext, modus)
    where_teile = [ft_sql]
    params: list = [ft_param]

    if dataset:
        where_teile.append("i.dataset = %s")
        params.append(dataset)

    if level:
        if isinstance(level, str):
            level_liste = [x.strip().upper() for x in level.split(",") if x.strip()]
        else:
            level_liste = [str(x).strip().upper() for x in level if str(x).strip()]
        if level_liste:
            where_teile.append("i.level = ANY(%s)")
            params.append(level_liste)

    if team:
        where_teile.append("o.team = %s")
        params.append(team)

    if von and bis:
        where_teile.append("i.ts BETWEEN %s AND %s")
        params.extend([von, bis])
    elif von:
        where_teile.append("i.ts >= %s")
        params.append(von)
    elif bis:
        where_teile.append("i.ts <= %s")
        params.append(bis)

    return " AND ".join(where_teile), params


def search_logs(
    query: str,
    dataset: str | None = None,
    level: str | list[str] | None = None,
    team: str | None = None,
    von: str | None = None,
    bis: str | None = None,
    limit: int = 50,
    modus: str = "phrase",
) -> dict:
    """Volltextsuche in den Logs über den invertierten Index logs_idx.

    Args:
        query: Suchbegriff oder Phrase (z. B. "data TLB error interrupt" oder "qemu-img").
        dataset: Optional "BGL" oder "OpenStack".
        level: Optional Log-Level (z. B. "ERROR", "FATAL" oder Liste ["ERROR", "FATAL"]).
        team: Optional Teamname aus der Ownership-Tabelle (z. B. "HPC Kernel", "Cloud Compute").
        von: Optional Startzeitpunkt (ISO-String, z. B. "2005-06-11 00:00:00").
        bis: Optional Endzeitpunkt (ISO-String).
        limit: Maximale Anzahl zurückgegebener Beispiel-Logzeilen (Standard: 50).
        modus: "phrase" (ts_phrase), "all" (ts_all) oder "any" (ts_any).
    """
    where_sql, params = _baue_filter(query, modus, dataset, level, team, von, bis)

    sql = f"""
SELECT i.id, i.ts, i.dataset, i.level, i.component, i.service, o.team,
       i.template_id, i.alert, i.node, i.instance_id, i.request_id, i.message
FROM logs_idx i
JOIN ownership o ON o.dataset = i.dataset AND o.component = i.component
WHERE {where_sql}
ORDER BY i.ts
LIMIT %s
""".strip()

    ergebnis = run_query(sql, params + [limit], limit=limit)
    ergebnis["suchmodus"] = modus

    # Automatischer Fallback: Falls ts_phrase bei mehreren Wörtern 0 Treffer liefert, ts_all probieren
    if ergebnis["zeilen"] == 0 and modus == "phrase" and len(query.strip().split()) > 1:
        where_sql, params = _baue_filter(query, "all", dataset, level, team, von, bis)
        sql = f"""
SELECT i.id, i.ts, i.dataset, i.level, i.component, i.service, o.team,
       i.template_id, i.alert, i.node, i.instance_id, i.request_id, i.message
FROM logs_idx i
JOIN ownership o ON o.dataset = i.dataset AND o.component = i.component
WHERE {where_sql}
ORDER BY i.ts
LIMIT %s
""".strip()
        ergebnis = run_query(sql, params + [limit], limit=limit)
        ergebnis["suchmodus"] = "all"
        ergebnis["hinweis_suche"] = "Keine Phrasentreffer; stattdessen alle Suchwörter gesucht."

    # Zusatz-Aggregation über alle Volltext-Treffer (liefert Gesamtzahl, Templates & Alert-Verteilung)
    try:
        stats_sql = f"""
SELECT i.template_id, ANY_VALUE(t.template) AS template, i.dataset, i.level, i.alert, o.team,
       COUNT(*) AS treffer,
       SUM(COUNT(*)) OVER () AS gesamt_treffer,
       COUNT(DISTINCT NULLIF(NULLIF(i.node, 'NULL'), '-')) AS knoten,
       COUNT(DISTINCT i.instance_id) AS vms,
       MIN(i.ts) AS erstmals, MAX(i.ts) AS zuletzt
FROM logs_idx i
JOIN ownership o ON o.dataset = i.dataset AND o.component = i.component
LEFT JOIN templates t ON t.template_id = i.template_id
WHERE {where_sql}
GROUP BY i.template_id, i.dataset, i.level, i.alert, o.team
ORDER BY treffer DESC
LIMIT 10
""".strip()
        stats = run_query(stats_sql, params, limit=10)
        # Die Top-10-Gruppen sind nur ein Ausschnitt; die Fensterfunktion zählt ALLE.
        gesamt_treffer = int(stats["daten"][0]["gesamt_treffer"]) if stats["daten"] else 0
        ergebnis["gesamt_treffer"] = gesamt_treffer
        ergebnis["muster_zusammenfassung"] = stats["daten"]
        ergebnis["zusatz_belege"] = [{"zweck": "Muster und Gesamttreffer", **stats}]
        ergebnis["truncated"] = gesamt_treffer > ergebnis["zeilen"]
    except Exception:
        ergebnis["hinweis"] = "Zusatzstatistik fehlgeschlagen; Gesamttrefferzahl unbekannt."

    return ergebnis


def get_context(
    log_id: int | str,
    fenster_sek: int = 600,
    limit: int = 100,
) -> dict:
    """Holt den Kontext rund um ein Ereignis (OpenStack: gleiche VM / gleicher Request; BGL: gleiche Midplane im Zeitfenster).

    Args:
        log_id: ID der Log-Zeile (int), alternativ direkt eine OpenStack instance_id (UUID) oder request_id ("req-...").
        fenster_sek: Zeitfenster in Sekunden vor und nach dem Ereignis für BGL / Tracebacks (Standard: 600).
        limit: Maximale Anzahl zurückgegebener Zeilen (Standard: 100).
    """
    anker = None
    log_id_str = str(log_id).strip()

    # 1. Anker-Zeile bestimmen (per numerischer ID, instance_id oder request_id)
    try:
        num_id = int(log_id_str)
        anker_res = run_query("SELECT * FROM logs WHERE id = %s", [num_id], limit=1)
        if anker_res["daten"]:
            anker = anker_res["daten"][0]
    except ValueError:
        if log_id_str.startswith("req-"):
            anker_res = run_query(
                "SELECT * FROM logs WHERE request_id = %s ORDER BY ts LIMIT 1",
                [log_id_str],
                limit=1,
            )
        else:
            anker_res = run_query(
                "SELECT * FROM logs WHERE instance_id = %s ORDER BY ts LIMIT 1",
                [log_id_str],
                limit=1,
            )
        if anker_res["daten"]:
            anker = anker_res["daten"][0]

    if not anker:
        return {**anker_res, "truncated": False}

    # 2a. OpenStack-Kontext: gleiche VM (instance_id) + zugehörige Requests (request_id) bzw. Traceback
    if anker["dataset"] == "OpenStack":
        inst_id = anker.get("instance_id")
        req_id = anker.get("request_id")

        if inst_id:
            sql = """
SELECT l.id, l.ts, l.level, l.component, l.service, l.node, l.pid,
       l.request_id, l.instance_id, l.template_id, l.message
FROM logs l
WHERE l.dataset = 'OpenStack' AND l.instance_id = %s
ORDER BY l.ts, l.id
LIMIT %s
""".strip()
            ergebnis = run_query(sql, [inst_id, limit], limit=limit)

            # Zusätzlich alle Requests dieser VM auswerten
            try:
                req_sql = """
SELECT l.request_id,
       COUNT(*) AS zeilen_gesamt,
       MIN(l.ts) AS start_ts,
       MAX(l.ts) AS end_ts,
       COUNT(DISTINCT l.service) AS anzahl_services,
       ARRAY_AGG(DISTINCT l.service ORDER BY l.service) AS services
FROM logs l
WHERE l.dataset = 'OpenStack'
  AND l.request_id IN (
      SELECT DISTINCT request_id FROM logs
      WHERE dataset = 'OpenStack' AND instance_id = %s AND request_id IS NOT NULL
  )
GROUP BY l.request_id
ORDER BY start_ts
""".strip()
                req_info = run_query(req_sql, [inst_id], limit=20)
                ergebnis["requests_der_vm"] = req_info["daten"]
                ergebnis.setdefault("zusatz_belege", []).append({"zweck": "Requests der VM", **req_info})

                if req_info["daten"]:
                    # Periodische Sammel-Requests können Tausende fremde VM-Zeilen
                    # enthalten. Den ersten überschaubaren verknüpften Request bevorzugen.
                    kandidat = next((r for r in req_info["daten"] if r["zeilen_gesamt"] <= limit), req_info["daten"][0])
                    haupt_req = kandidat["request_id"]
                    ergebnis["request_auswahl"] = {"request_id": haupt_req,
                        "regel": "Erster verknüpfter Request innerhalb des Zeilenlimits; sonst erster verknüpfter Request."}
                    req_zeilen = run_query(
                        """
SELECT l.id, l.ts, l.level, l.component, l.service, l.request_id, l.instance_id, l.template_id, l.message
FROM logs l
WHERE l.dataset = 'OpenStack' AND l.request_id = %s
ORDER BY l.ts, l.id
LIMIT %s
""".strip(),
                        [haupt_req, limit],
                        limit=limit,
                    )
                    ergebnis["request_verlauf"] = req_zeilen["daten"]
                    ergebnis["zusatz_belege"].append({"zweck": "Request-Verlauf", **req_zeilen})
            except Exception:
                ergebnis["hinweis"] = "Zusätzlicher Request-Kontext konnte nicht vollständig geladen werden."

            return ergebnis

        if req_id:
            sql = """
SELECT l.id, l.ts, l.level, l.component, l.service, l.node, l.pid,
       l.request_id, l.instance_id, l.template_id, l.message
FROM logs l
WHERE l.dataset = 'OpenStack' AND l.request_id = %s
ORDER BY l.ts, l.id
LIMIT %s
""".strip()
            return run_query(sql, [req_id, limit], limit=limit)

        # Fallback für mehrzeilige OpenStack-Tracebacks ohne VM/Request
        sql = """
SELECT l.id, l.ts, l.level, l.component, l.service, l.node, l.pid,
       l.template_id, l.message
FROM logs l
JOIN logs s ON s.id = %s
WHERE l.dataset = 'OpenStack'
  AND l.component = s.component
  AND l.ts BETWEEN s.ts - %s * INTERVAL '1 second' AND s.ts + %s * INTERVAL '1 second'
ORDER BY l.ts, l.id
LIMIT %s
""".strip()
        return run_query(sql, [anker["id"], fenster_sek, fenster_sek, limit], limit=limit)

    # 2b. BGL-Kontext: gleiche Midplane (erste 2 Teile von node, z. B. R20-M0) im Zeitfenster
    sql = """
SELECT l.id, l.ts, l.node, l.level, l.component, l.template_id, l.alert, l.message
FROM logs l JOIN logs s ON s.id = %s
WHERE l.dataset = 'BGL'
  AND l.node LIKE split_part(s.node, '-', 1) || '-' || split_part(s.node, '-', 2) || '%%'
  AND l.ts BETWEEN s.ts - %s * INTERVAL '1 second' AND s.ts + %s * INTERVAL '1 second'
ORDER BY l.ts
LIMIT %s
""".strip()
    ergebnis = run_query(sql, [anker["id"], fenster_sek, fenster_sek, limit], limit=limit)

    # Zusatz: Ausbruch vs. Einzelfall
    try:
        ausbruch_sql = """
SELECT s.template_id,
       COUNT(*) AS vorkommen_im_fenster,
       COUNT(DISTINCT NULLIF(NULLIF(l.node, 'NULL'), '-')) AS knoten_im_fenster,
       MIN(l.ts) AS erstmals_im_fenster,
       MAX(l.ts) AS zuletzt_im_fenster
FROM logs l JOIN logs s ON s.id = %s
WHERE l.dataset = 'BGL'
  AND l.template_id = s.template_id
  AND l.ts BETWEEN s.ts - %s * INTERVAL '1 second' AND s.ts + %s * INTERVAL '1 second'
GROUP BY s.template_id
""".strip()
        ausbruch = run_query(ausbruch_sql, [anker["id"], fenster_sek, fenster_sek], limit=1)
        if ausbruch["daten"]:
            ergebnis["ausbruch_analyse"] = ausbruch["daten"][0]
            ergebnis.setdefault("zusatz_belege", []).append({"zweck": "Ausbruch im Zeitfenster", **ausbruch})
    except Exception:
        ergebnis["hinweis"] = "Zusätzliche Ausbruchstatistik konnte nicht geladen werden."

    return ergebnis


def vm_dauer(instance_id: str | None = None, limit: int = 10) -> dict:
    """Vergleicht die Spawn-Dauer einer OpenStack-VM mit allen VMs (Rangliste, Median, Maximum).

    Args:
        instance_id: Optionale UUID der VM (z. B. "544fd51c-4edc-4780-baae-ba1d80a0acfc").
                     Wenn leer/None, werden die langsamsten VMs zurückgegeben.
        limit: Anzahl der Top-Verzögerungen in der Rangliste (Standard: 10).
    """
    sql = """
WITH spawns AS (
    SELECT id AS log_id, ts, node, instance_id, request_id,
           CAST(regexp_extract(message, 'Took ([0-9.]+) seconds to spawn', 1) AS DOUBLE) AS sek
    FROM logs
    WHERE message LIKE '%%seconds to spawn%%'
),
kennzahlen AS (
    SELECT COUNT(*) AS gesamt_vms,
           ROUND(MEDIAN(sek), 1) AS median_sek,
           ROUND(AVG(sek), 1) AS schnitt_sek,
           MIN(sek) AS min_sek,
           MAX(sek) AS max_sek
    FROM spawns
    WHERE sek IS NOT NULL
),
rangliste AS (
    SELECT s.log_id, s.ts, s.node, s.instance_id, s.request_id, s.sek,
           RANK() OVER (ORDER BY s.sek DESC) AS platz,
           k.gesamt_vms, k.median_sek, k.schnitt_sek, k.min_sek, k.max_sek
    FROM spawns s
    CROSS JOIN kennzahlen k
    WHERE s.sek IS NOT NULL
)
SELECT * FROM rangliste
WHERE (%s IS NOT NULL AND instance_id = %s) OR platz <= %s
ORDER BY platz ASC
""".strip()

    ergebnis = run_query(sql, [instance_id, instance_id, limit], limit=max(limit + 5, 20))

    if instance_id:
        treffer = [r for r in ergebnis["daten"] if r.get("instance_id") == instance_id]
        if treffer:
            ergebnis["gesuchte_vm"] = treffer[0]

    return ergebnis


if __name__ == "__main__":
    print("=== Test 1: Engineer Volltextsuche ('data TLB error interrupt') ===")
    r1 = search_logs("data TLB error interrupt", limit=5)
    print("SQL:", r1["sql"])
    print("Zeilen (Limit):", r1["zeilen"], "| Gesamt-Treffer:", r1.get("gesamt_treffer"))
    print("Muster-Zusammenfassung:", r1.get("muster_zusammenfassung"))

    print("\n=== Test 2: Engineer VM Spawn-Dauer ('544fd51c-4edc-4780-baae-ba1d80a0acfc') ===")
    r2 = vm_dauer("544fd51c-4edc-4780-baae-ba1d80a0acfc", limit=5)
    print("Gesuchte VM:", r2.get("gesuchte_vm"))
    print("Top 5 langsamste VMs:")
    for row in r2["daten"][:5]:
        print(f"  Platz {row['platz']}/{row['gesamt_vms']}: VM {row['instance_id']} -> {row['sek']}s (Median: {row['median_sek']}s)")

    print("\n=== Test 3: Engineer Kontext für VM '544fd51c-4edc-4780-baae-ba1d80a0acfc' ===")
    r3 = get_context("544fd51c-4edc-4780-baae-ba1d80a0acfc")
    print("VM-Zeilen:", r3["zeilen"])
    print("Requests der VM:", r3.get("requests_der_vm"))
