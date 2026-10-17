"""Bereich 3: belegbare Analytics in SereneDB, ohne Agent- oder UI-Abhängigkeit.

Alle fachlichen Berechnungen finden in SQL statt. Python validiert Eingaben und
verpackt die Ergebnisse. Der gemeinsame DB-Helfer gehört Bereich 2.
"""
from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from time import perf_counter

MAX_LIMIT = 1000
TREND_LIMIT = 10_000
INTERVALS = {"1 hour", "1 day", "1 week"}
DateInput = str | datetime | None
LEVEL_FILTER = "(dataset = 'BGL' AND level IN ('ERROR', 'FATAL')) OR (dataset = 'OpenStack' AND level IN ('WARN', 'ERROR', 'FATAL'))"


def _query(sql: str, params: list, limit: int) -> dict:
    try:
        db = import_module("tools.db")
    except ModuleNotFoundError as exc:
        if exc.name != "tools.db":
            raise
        raise RuntimeError(
            "tools/db.py fehlt. Bitte den gemeinsamen DB-Helfer von Bereich 2 "
            "übernehmen; Analytics enthält bewusst keinen eigenen DB-Client."
        ) from exc
    return db.query(sql, params=params, limit=limit)


def _date(value, name):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} muss ein ISO-Zeitstempel sein.") from exc
    if not isinstance(value, datetime):
        raise ValueError(f"{name} muss ein datetime oder ISO-Zeitstempel sein.")
    # Ohne Offset gilt die im Datenbestand gespeicherte UTC-Konvention.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _validate(dataset, team, von, bis, limit):
    if dataset is not None and dataset not in ("BGL", "OpenStack"):
        raise ValueError("dataset muss BGL, OpenStack oder None sein.")
    if team is not None and (not isinstance(team, str) or not team.strip()):
        raise ValueError("team muss ein nichtleerer Teamname oder None sein.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit muss eine ganze Zahl zwischen 1 und {MAX_LIMIT} sein.")
    von, bis = _date(von, "von"), _date(bis, "bis")
    if von is not None and bis is not None and von > bis:
        raise ValueError("von darf nicht nach bis liegen.")
    return von, bis


def _base(dataset, team, von, bis):
    predicates = ["l.dataset IN ('BGL', 'OpenStack')"]
    params = []
    for expression, value in (("l.dataset = %s", dataset),
                              ("COALESCE(o.team, 'Unassigned') = %s", team),
                              ("l.ts >= %s", von), ("l.ts <= %s", bis)):
        if value is not None:
            predicates.append(expression)
            params.append(value)
    sql = """WITH scope AS (
        SELECT l.*, COALESCE(o.team, 'Unassigned') AS team
        FROM logs l LEFT JOIN ownership o
          ON o.dataset = l.dataset AND o.component = l.component
        WHERE """ + " AND ".join(predicates) + """
    ), bounds AS (
        SELECT dataset, COALESCE(%s::TIMESTAMPTZ, MIN(ts)) AS von,
               COALESCE(%s::TIMESTAMPTZ, MAX(ts)) AS bis
        FROM scope GROUP BY dataset
    )"""
    return sql, params + [von, bis]


# Der numerische Ereignisschlüssel ist eine echte Log-ID, kein fehleranfälliges
# Verkettungsergebnis. Ungültige OpenStack-Schlüssel und BGL bleiben Einzelzeilen.
EVENT_CTES = """, selected AS (
    SELECT * FROM scope WHERE """ + LEVEL_FILTER + """
), event_keys AS (
    SELECT *,
        CASE WHEN dataset = 'OpenStack' AND pid IS NOT NULL AND ts IS NOT NULL
             THEN pid END AS event_pid,
        CASE WHEN dataset = 'OpenStack' AND pid IS NOT NULL AND ts IS NOT NULL
             THEN ts END AS event_ts,
        CASE WHEN dataset = 'OpenStack' AND pid IS NOT NULL AND ts IS NOT NULL
             THEN NULL ELSE id END AS single_id
    FROM selected
), marked AS (
    SELECT *,
        MIN(id) OVER (PARTITION BY dataset, event_pid, event_ts, single_id) AS event_id,
        FIRST_VALUE(template_id) OVER (
            PARTITION BY dataset, event_pid, event_ts, single_id
            ORDER BY CASE WHEN level IN ('ERROR', 'FATAL') THEN 0 ELSE 1 END, id
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS problem_template_id
    FROM event_keys
)"""

COUNTS = """
    COUNT(*) AS n, COUNT(DISTINCT m.event_id) AS ereignisse,
    COUNT(m.alert) AS alerts,
    COUNT(DISTINCT NULLIF(NULLIF(NULLIF(TRIM(m.node), 'NULL'), '-'), '')) AS knoten,
    COUNT(DISTINCT NULLIF(TRIM(m.instance_id), '')) AS vms,
    COUNT(DISTINCT NULLIF(TRIM(m.request_id), '')) AS requests,
    ARRAY_AGG(DISTINCT m.component ORDER BY m.component) AS komponenten,
    MIN(m.id) AS example_log_id, MIN(m.ts) AS erstmals, MAX(m.ts) AS zuletzt
"""


def _run(base, params, sql, extra, limit, filters, **details):
    start = perf_counter()
    result = _query(sql + " LIMIT %s", params + extra + [limit + 1], limit + 1)
    elapsed = perf_counter() - start
    raw = result["daten"]
    total = int(raw[0]["_gesamt"]) if raw else 0
    rows = [{k: v for k, v in row.items() if k != "_gesamt"} for row in raw[:limit]]
    scope_sql = base + """
        SELECT s.dataset, s.team, COUNT(*) AS logzeilen_gesamt,
               MIN(s.ts) AS erstmals, MAX(s.ts) AS zuletzt,
               COUNT(*) - COUNT(s.ts) AS ohne_zeitstempel,
               b.von AS zeitraum_von, b.bis AS zeitraum_bis
        FROM scope s JOIN bounds b ON b.dataset = s.dataset
        GROUP BY s.dataset, s.team, b.von, b.bis
        ORDER BY s.dataset, s.team LIMIT 10001
    """
    scope_start = perf_counter()
    scope = _query(scope_sql, params, 10001)
    scope_elapsed = perf_counter() - scope_start
    scope["gekuerzt"] = len(scope["daten"]) > 10000
    scope["daten"] = scope["daten"][:10000]
    scope["zeilen"] = len(scope["daten"])
    return {
        "sql": result["sql"], "zeilen": len(rows), "daten": rows,
        "meta": {
            "filter": filters, "gruppen_gesamt": total,
            "gekuerzt": total > len(rows), "limit": limit,
            "laufzeit_sek": elapsed, "bereich_laufzeit_sek": scope_elapsed,
            "bereich": scope,
            "level": {"BGL": ["ERROR", "FATAL"], "OpenStack": ["WARN", "ERROR", "FATAL"]},
            "zaehlweise": "n = Logzeilen; ereignisse = BGL-Einzelzeilen bzw. OpenStack-(pid, ts)-Näherung im Filterbereich.",
            "hinweise": [
                "OpenStack-Ereignisse sind eine Näherung, keine bestätigten Vorfälle; Template-Zahlen nicht addieren.",
                "BGL-Ortszeiten wurden beim Import als UTC markiert und werden hier unverändert verwendet.",
                "Bereichsstatistik umfasst alle Level vor dem Template- und Schweregradfilter.",
                "Haupt- und Bereichsabfrage laufen getrennt: während der Analyse keine Daten neu laden.",
            ], **details,
        },
    }


def top_patterns(team: str | None, dataset: str | None = None,
                 von: DateInput = None, bis: DateInput = None, limit: int = 10) -> dict:
    """Häufigste Templates je Team; zählt den vollständigen gefilterten Bestand.

    team: Ownership-Team oder None für alle Teams. dataset: BGL/OpenStack/None.
    von/bis: inklusive ISO-Zeitgrenzen; None verwendet den gesamten Bestand.
    limit: 1..1000 Ergebnisgruppen. Liefert SQL, n, Ereignisse, Reichweite,
    Alerts, Komponenten und repräsentative OpenStack-Problem-Templates.
    """
    von, bis = _validate(dataset, team, von, bis, limit)
    base, params = _base(dataset, team, von, bis)
    sql = base + EVENT_CTES + """, grouped AS (
        SELECT m.dataset, m.team, m.template_id, ANY_VALUE(t.template) AS template,
        """ + COUNTS + """,
        ARRAY_AGG(DISTINCT m.problem_template_id ORDER BY m.problem_template_id) AS problem_template_ids
        FROM marked m LEFT JOIN templates t
          ON t.dataset = m.dataset AND t.template_id = m.template_id
        GROUP BY m.dataset, m.team, m.template_id
    ) SELECT *, COUNT(*) OVER () AS _gesamt FROM grouped
    ORDER BY n DESC, dataset, team, template_id
    """
    return _run(base, params, sql, [], limit,
                dict(team=team, dataset=dataset, von=von, bis=bis))


def pattern_trend(template_id: str | None = None, team: str | None = None,
                  intervall: str = "1 day", *, dataset: str | None = None,
                  von: DateInput = None, bis: DateInput = None) -> dict:
    """Zeitreihe für Template und/oder Team, einschließlich sichtbarer Datenlücken.

    Filter werden geschnitten. Intervalle: 1 hour, 1 day, 1 week.
    Für OpenStack ausdrücklich 1 hour verwenden. datenluecke=True bedeutet:
    kein Log im gewählten Bereich beobachtet; n/ereignisse/alerts bleiben NULL.
    Bei beobachteten Logs ohne passende Fehler sind diese Werte dagegen 0.
    """
    von, bis = _validate(dataset, team, von, bis, 1)
    if template_id is None and team is None:
        raise ValueError("Mindestens template_id oder team ist erforderlich.")
    if template_id is not None:
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError("template_id muss eine nichtleere Zeichenkette sein.")
        inferred = "BGL" if template_id.startswith("BGL-") else "OpenStack" if template_id.startswith("OS-") else None
        if inferred is None:
            raise ValueError("template_id muss mit BGL- oder OS- beginnen.")
        if dataset is not None and dataset != inferred:
            raise ValueError("template_id und dataset widersprechen sich.")
        dataset = inferred
    if not isinstance(intervall, str) or intervall not in INTERVALS:
        raise ValueError("intervall muss 1 hour, 1 day oder 1 week sein.")
    base, params = _base(dataset, team, von, bis)
    template_filter = " AND template_id = %s" if template_id is not None else ""
    sql = base + EVENT_CTES + """, settings AS (
        SELECT %s::INTERVAL AS step
    ), observed AS (
        SELECT dataset, time_bucket(step, ts) AS zeit, COUNT(*) AS beobachtete_logs
        FROM scope CROSS JOIN settings WHERE ts IS NOT NULL
        GROUP BY dataset, time_bucket(step, ts)
    ), matching AS (
        SELECT dataset, time_bucket(step, ts) AS zeit, COUNT(*) AS n,
               COUNT(DISTINCT event_id) AS ereignisse, COUNT(alert) AS alerts
        FROM marked CROSS JOIN settings WHERE ts IS NOT NULL
        """ + template_filter + """
        GROUP BY dataset, time_bucket(step, ts)
    ), grid AS (
        SELECT b.dataset, g.zeit
        FROM bounds b CROSS JOIN settings
        CROSS JOIN LATERAL generate_series(
            time_bucket(step, b.von), time_bucket(step, b.bis), step
        ) AS g(zeit)
        WHERE b.von IS NOT NULL AND b.bis IS NOT NULL
    )
    SELECT g.dataset, g.zeit,
           COALESCE(o.beobachtete_logs, 0) AS beobachtete_logs,
           o.beobachtete_logs IS NULL AS datenluecke,
           CASE WHEN o.beobachtete_logs IS NOT NULL THEN COALESCE(m.n, 0) END AS n,
           CASE WHEN o.beobachtete_logs IS NOT NULL THEN COALESCE(m.ereignisse, 0) END AS ereignisse,
           CASE WHEN o.beobachtete_logs IS NOT NULL THEN COALESCE(m.alerts, 0) END AS alerts,
           COUNT(*) OVER () AS _gesamt
    FROM grid g LEFT JOIN observed o ON o.dataset = g.dataset AND o.zeit = g.zeit
    LEFT JOIN matching m ON m.dataset = g.dataset AND m.zeit = g.zeit
    ORDER BY g.zeit, g.dataset
    """
    extra = [intervall] + ([template_id] if template_id is not None else [])
    return _run(base, params, sql, extra, TREND_LIMIT,
                dict(template_id=template_id, team=team, dataset=dataset, von=von, bis=bis),
                intervall=intervall)


def priority_ranking(von: DateInput = None, bis: DateInput = None,
                     group_by: str = "template", *, dataset: str | None = None,
                     team: str | None = None, limit: int = 100) -> dict:
    """Prioritäten mit allen Score-Faktoren, getrennt nach Datensatz/Reichweitenart.

    group_by: template (OpenStack: repräsentatives Problem-Template) oder team.
    Fehlende Reichweite ergibt score/rang=None, nicht null Auswirkung.
    Häufigkeit und Reichweite werden VOR dem Ergebnislimit normalisiert.
    """
    von, bis = _validate(dataset, team, von, bis, limit)
    if group_by not in ("template", "team"):
        raise ValueError("group_by muss template oder team sein.")
    base, params = _base(dataset, team, von, bis)
    # Nur diese intern ausgewählten SQL-Fragmente werden interpoliert, nie Nutzereingaben.
    group_key = "m.problem_template_id" if group_by == "template" else "m.team"
    sql = base + EVENT_CTES + """, grouped AS (
        SELECT m.dataset, """ + group_key + """ AS gruppe,
               ARRAY_AGG(DISTINCT m.team ORDER BY m.team) AS teams,
               ARRAY_AGG(DISTINCT m.template_id ORDER BY m.template_id) AS template_ids,
               """ + COUNTS + """,
               MAX(CASE m.level WHEN 'FATAL' THEN 3 WHEN 'ERROR' THEN 2 ELSE 1 END) AS schweregrad,
               b.von, b.bis,
               COUNT(DISTINCT CASE WHEN m.ts < b.von + (b.bis - b.von) / 2 THEN m.event_id END) AS erste_haelfte,
               COUNT(DISTINCT CASE WHEN m.ts >= b.von + (b.bis - b.von) / 2 THEN m.event_id END) AS zweite_haelfte,
               COUNT(*) - COUNT(m.ts) AS ohne_zeitstempel
        FROM marked m JOIN bounds b ON b.dataset = m.dataset
        GROUP BY m.dataset, """ + group_key + """, b.von, b.bis
    ), measured AS (
        SELECT *, CASE WHEN dataset = 'BGL' THEN n ELSE ereignisse END AS haeufigkeit,
               CASE WHEN dataset = 'BGL' AND knoten > 0 THEN 'knoten'
                    WHEN dataset = 'OpenStack' AND vms > 0 THEN 'vms'
                    WHEN dataset = 'OpenStack' AND requests > 0 THEN 'requests'
                    ELSE 'unbekannt' END AS reichweite_typ,
               CASE WHEN dataset = 'BGL' THEN NULLIF(knoten, 0)
                    WHEN vms > 0 THEN vms ELSE NULLIF(requests, 0) END AS reichweite,
               CASE WHEN von IS NULL OR von = bis OR ohne_zeitstempel > 0 THEN 1.0
                    ELSE 1.0 + GREATEST(-0.5, LEAST(0.5,
                         (zweite_haelfte - erste_haelfte) * 1.0 / NULLIF(ereignisse, 0))) END AS trendfaktor,
               CASE WHEN dataset = 'BGL' THEN 1.0 + alerts * 1.0 / NULLIF(n, 0)
                    ELSE 1.0 END AS alertfaktor,
               CASE WHEN von IS NULL OR von = bis OR ohne_zeitstempel > 0
                    THEN 'neutral: Zeitraum fehlt, hat keine Ausdehnung oder Zeitstempel fehlen'
                    ELSE 'Vergleich zweier gleich langer Kalenderzeiträume; Datenlücken können den Trend beeinflussen'
               END AS trend_hinweis
        FROM grouped
    ), normalized AS (
        SELECT *, MAX(haeufigkeit) OVER (PARTITION BY dataset, reichweite_typ) AS max_haeufigkeit,
               MAX(reichweite) OVER (PARTITION BY dataset, reichweite_typ) AS max_reichweite,
               haeufigkeit * 1.0 / NULLIF(MAX(haeufigkeit) OVER (PARTITION BY dataset, reichweite_typ), 0) AS haeufigkeit_norm,
               reichweite * 1.0 / NULLIF(MAX(reichweite) OVER (PARTITION BY dataset, reichweite_typ), 0) AS reichweite_norm
        FROM measured
    ), scored AS (
        SELECT *, haeufigkeit_norm * schweregrad * reichweite_norm * trendfaktor * alertfaktor AS score,
               dataset || ':' || reichweite_typ AS vergleichsgruppe,
               CASE WHEN reichweite IS NULL THEN 'nicht bewertbar' ELSE 'bewertbar' END AS status
        FROM normalized
    )
    SELECT *,
           CASE WHEN score IS NOT NULL THEN ROW_NUMBER() OVER (
               PARTITION BY dataset, reichweite_typ ORDER BY score DESC NULLS LAST, gruppe
           ) END AS rang,
           COUNT(*) OVER () AS _gesamt,
           SUM(CASE WHEN score IS NULL THEN 1 ELSE 0 END) OVER () AS nicht_bewertbar_gesamt
    FROM scored ORDER BY dataset, CASE WHEN score IS NULL THEN 1 ELSE 0 END,
                         reichweite_typ, score DESC NULLS LAST, gruppe
    """
    return _run(base, params, sql, [], limit,
                dict(group_by=group_by, dataset=dataset, team=team, von=von, bis=bis),
                score_formel="haeufigkeit_norm * schweregrad * reichweite_norm * trendfaktor * alertfaktor",
                vergleich="Ränge gelten nur innerhalb derselben vergleichsgruppe; kein globaler Rang.")
