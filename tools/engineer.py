"""Engineer tools: bounded results, complete counts and inspectable query evidence."""
from __future__ import annotations
from datetime import datetime, timezone
from tools.db import query as run_query


def _validate(limit, dataset=None, von=None, bis=None):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer between 1 and 1000.')
    if dataset is not None and dataset not in ('BGL', 'OpenStack'):
        raise ValueError('dataset must be BGL or OpenStack.')
    dates = []
    for value in (von, bis):
        if value is not None:
            value = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
            if not isinstance(value, datetime):
                raise ValueError('Time bounds must be ISO timestamps or datetimes.')
            value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        dates.append(value)
    if all(v is not None for v in dates) and dates[0] > dates[1]:
        raise ValueError('Start must not follow end.')
    return dates


def _limited(sql, params, limit):
    result = run_query(sql, params + [limit + 1], limit=limit + 1)
    truncated = len(result['daten']) > limit
    result['daten'] = result['daten'][:limit]
    result['zeilen'] = len(result['daten'])
    result['meta'] = {'limit': limit, 'gekuerzt': truncated}
    result['truncated'] = truncated
    return result


def _supplement(result, name, sql, params, limit=20, bounded=False):
    try:
        evidence = _limited(sql, params, limit) if bounded else run_query(sql, params, limit=limit)
        result.setdefault('belege', []).append({'name': name, **evidence})
        return evidence['daten']
    except Exception as exc:
        result.setdefault('warnings', []).append(f'{name} unavailable ({type(exc).__name__}). Results are partial.')
        return None


def _baue_volltext_bedingung(suchtext, modus):
    if not isinstance(suchtext, str) or not suchtext.strip():
        raise ValueError('Search text must not be empty.')
    if modus not in ('phrase', 'all', 'any'):
        raise ValueError('Search mode must be phrase, all or any.')
    words = suchtext.split()
    if modus in ('all', 'any') and len(words) > 1:
        return f'i.message @@ ts_{modus}(%s)', words
    return 'i.message @@ ts_phrase(%s)', suchtext.strip()


def _baue_filter(suchtext, modus, dataset, level, team, von, bis):
    expression, text = _baue_volltext_bedingung(suchtext, modus)
    predicates, params = [expression], [text]
    if level:
        levels = level.split(',') if isinstance(level, str) else level
        if not isinstance(levels, (list, tuple)) or any(not isinstance(v, str) for v in levels):
            raise ValueError('level must be a severity string or list.')
        levels = [v.strip().upper() for v in levels]
        if any(v not in ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL') for v in levels):
            raise ValueError('Unknown severity.')
        predicates.append('i.level = ANY(%s)')
        params.append(levels)
    for expression, value in (('i.dataset = %s', dataset), ('o.team = %s', team),
                              ('i.ts >= %s', von), ('i.ts <= %s', bis)):
        if value is not None:
            predicates.append(expression)
            params.append(value)
    return ' AND '.join(predicates), params


def search_logs(query: str, dataset: str | None = None, level: str | list[str] | None = None,
                team: str | None = None, von: str | None = None, bis: str | None = None,
                limit: int = 50, modus: str = 'phrase') -> dict:
    """Search logs by phrase/all/any with dataset, severity, team and ISO time filters.

    Returns at most 1..1000 examples, full matching log-line count, SQL and warnings.
    Empty phrase searches retry all words; metadata records the effective mode.
    """
    von, bis = _validate(limit, dataset, von, bis)
    where, params = _baue_filter(query, modus, dataset, level, team, von, bis)
    select = """SELECT i.id, i.ts, i.dataset, i.level, i.component, i.service,
        COALESCE(o.team, 'Unassigned') AS team, i.template_id, i.alert, i.node,
        i.instance_id, i.request_id, i.message
        FROM logs_idx i LEFT JOIN ownership o ON o.dataset=i.dataset AND o.component=i.component
        WHERE """
    result = _limited(select + where + ' ORDER BY i.ts, i.id LIMIT %s', params, limit)
    result['belege'] = []
    effective_mode = modus
    if not result['daten'] and modus == 'phrase' and len(query.split()) > 1:
        initial = {'name': 'Original phrase search', **result}
        initial.pop('belege')
        where, params = _baue_filter(query, 'all', dataset, level, team, von, bis)
        result = _limited(select + where + ' ORDER BY i.ts, i.id LIMIT %s', params, limit)
        result['belege'] = [initial]
        effective_mode = 'all'
    result['meta'].update(filter=dict(query=query, dataset=dataset, level=level, team=team, von=von, bis=bis),
                          modus=effective_mode, requested_modus=modus)
    result['suchmodus'] = effective_mode
    if effective_mode != modus:
        result['hinweis_suche'] = 'No phrase matches; searched for all words instead.'
    stats_sql = """SELECT i.template_id, ANY_VALUE(t.template) AS template, i.dataset,
        i.level, i.alert, COALESCE(o.team, 'Unassigned') AS team, COUNT(*) AS treffer,
        SUM(COUNT(*)) OVER () AS gesamt_treffer, COUNT(*) OVER () AS gruppen_gesamt,
        COUNT(DISTINCT NULLIF(NULLIF(i.node, 'NULL'), '-')) AS knoten,
        COUNT(DISTINCT i.instance_id) AS vms, MIN(i.ts) AS erstmals, MAX(i.ts) AS zuletzt
        FROM logs_idx i LEFT JOIN ownership o ON o.dataset=i.dataset AND o.component=i.component
        LEFT JOIN templates t ON t.dataset=i.dataset AND t.template_id=i.template_id
        WHERE """ + where + """ GROUP BY i.template_id, i.dataset, i.level, i.alert, o.team
        ORDER BY treffer DESC, i.template_id LIMIT 10"""
    stats = _supplement(result, 'Search statistics (top 10 groups; full matching count)', stats_sql, params, 10)
    if stats is not None:
        result['gesamt_treffer'] = int(stats[0]['gesamt_treffer']) if stats else 0
        result['muster_zusammenfassung'] = stats
        result['meta']['summary_gekuerzt'] = bool(stats and stats[0].get('gruppen_gesamt', len(stats)) > len(stats))
        result['truncated'] = result['meta']['gekuerzt'] = result['gesamt_treffer'] > result['zeilen']
    return result


def get_context(log_id: int | str, fenster_sek: int = 600, limit: int = 100) -> dict:
    """Get nearby logs for a numeric ID, VM UUID or req-UUID, with executed evidence.

    BGL uses the broader midplane; unlinked OpenStack errors use their component.
    Window: 1..86400 seconds. VM/request context spans all recorded times.
    limit: 1..1000; retain the anchor and nearest rows, then display chronologically.
    """
    _validate(limit)
    if isinstance(fenster_sek, bool) or not isinstance(fenster_sek, int) or not 1 <= fenster_sek <= 86400:
        raise ValueError('Context window must be 1..86400 seconds.')
    if isinstance(log_id, bool) or not isinstance(log_id, (int, str)) or not str(log_id).strip():
        raise ValueError('A numeric log ID, VM UUID or request ID is required.')
    identifier = str(log_id).strip()
    if identifier.isdigit():
        anchor_result = run_query('SELECT * FROM logs WHERE id = %s', [int(identifier)], limit=1)
    else:
        field = 'request_id' if identifier.startswith('req-') else 'instance_id'
        anchor_result = run_query(f"SELECT * FROM logs WHERE dataset='OpenStack' AND {field}=%s ORDER BY ts, id LIMIT 1",
                                  [identifier], limit=1)
    if not anchor_result['daten']:
        return {**anchor_result, 'meta': {'gekuerzt': False, 'limit': limit}, 'belege': []}
    anchor = anchor_result['daten'][0]
    params = [anchor['id']]
    if anchor['dataset'] == 'BGL':
        scope = 'BGL midplane (broader than a single node) within the time window'
        # Missing node identifiers must not match unrelated missing-node rows.
        predicate = """l.dataset='BGL' AND (l.id=s.id OR (
            s.node IS NOT NULL AND s.node NOT IN ('NULL', '-', '')
            AND l.node LIKE split_part(s.node, '-', 1) || '-' || split_part(s.node, '-', 2) || '%%'
            AND l.ts BETWEEN s.ts - %s * INTERVAL '1 second' AND s.ts + %s * INTERVAL '1 second'))"""
        params += [fenster_sek, fenster_sek]
    elif anchor.get('instance_id'):
        scope, predicate = 'OpenStack VM lifecycle (all recorded times)', "l.dataset='OpenStack' AND l.instance_id=s.instance_id"
    elif anchor.get('request_id'):
        scope, predicate = 'OpenStack request lifecycle (all recorded times)', "l.dataset='OpenStack' AND l.request_id=s.request_id"
    else:
        scope = 'OpenStack component within the time window; may include other processes'
        predicate = """l.dataset='OpenStack' AND (l.id=s.id OR (l.component=s.component
            AND l.ts BETWEEN s.ts - %s * INTERVAL '1 second' AND s.ts + %s * INTERVAL '1 second'))"""
        params += [fenster_sek, fenster_sek]
    sql = """SELECT l.id, l.ts, l.dataset, l.level, l.component, l.service, l.node, l.pid,
        l.request_id, l.instance_id, l.template_id, l.alert, l.message
        FROM logs l JOIN logs s ON s.id=%s WHERE """ + predicate + """
        ORDER BY CASE WHEN l.id=s.id THEN 0 ELSE 1 END,
                 ABS(EXTRACT(EPOCH FROM (l.ts-s.ts))) NULLS LAST, l.id LIMIT %s"""
    result = _limited(sql, params, limit)
    result['daten'].sort(key=lambda r: (str(r.get('ts') or ''), r['id']))
    result['meta'].update(scope=scope, anchor=anchor, fenster_sek=fenster_sek)
    result['belege'] = [{'name': 'Anchor lookup', **anchor_result}]
    if anchor['dataset'] == 'BGL':
        stats = _supplement(result, 'Same-template outbreak across all BGL nodes', """
            SELECT s.template_id, COUNT(*) AS vorkommen_im_fenster,
                   COUNT(DISTINCT NULLIF(NULLIF(l.node, 'NULL'), '-')) AS knoten_im_fenster,
                   MIN(l.ts) AS erstmals_im_fenster, MAX(l.ts) AS zuletzt_im_fenster
            FROM logs l JOIN logs s ON s.id=%s
            WHERE l.dataset='BGL' AND l.template_id=s.template_id
              AND l.ts BETWEEN s.ts - %s * INTERVAL '1 second' AND s.ts + %s * INTERVAL '1 second'
            GROUP BY s.template_id""", [anchor['id'], fenster_sek, fenster_sek], 1)
        if stats:
            result['ausbruch_analyse'] = stats[0]
    elif anchor.get('instance_id'):
        requests = _supplement(result, 'Requests associated with the VM', """
            SELECT request_id, COUNT(*) AS zeilen_gesamt, MIN(ts) AS start_ts, MAX(ts) AS end_ts,
                   COUNT(DISTINCT service) AS anzahl_services,
                   ARRAY_AGG(DISTINCT service ORDER BY service) AS services
            FROM logs WHERE dataset='OpenStack' AND request_id IN (
                SELECT DISTINCT request_id FROM logs WHERE dataset='OpenStack'
                AND instance_id=%s AND request_id IS NOT NULL)
            GROUP BY request_id ORDER BY start_ts, request_id LIMIT %s""",
            [anchor['instance_id']], 20, bounded=True)
        if requests is not None:
            result['requests_der_vm'] = requests
        if requests:
            candidate = next((r for r in requests if r.get('zeilen_gesamt', limit + 1) <= limit), requests[0])
            request_id = candidate['request_id']
            result['request_auswahl'] = {'request_id': request_id,
                'regel': 'First linked request within the row limit; otherwise first linked request.'}
            rows = _supplement(result, 'Related request timeline', """
                SELECT id, ts, level, component, service, request_id, instance_id, template_id, message
                FROM logs WHERE dataset='OpenStack' AND request_id=%s ORDER BY ts, id LIMIT %s""",
                [request_id], limit, bounded=True)
            if rows is not None:
                result['request_verlauf'] = rows
    return result


def vm_dauer(instance_id: str | None = None, limit: int = 10) -> dict:
    """Rank OpenStack spawn observations against the full corpus median, retaining a selected VM.

    limit: 1..1000 top observations, plus the selected observation when supplied.
    Counts represent spawn log entries, not distinct VMs. Dashboard scope does not apply.
    """
    _validate(limit)
    if instance_id is not None and (not isinstance(instance_id, str) or not instance_id.strip()):
        raise ValueError('instance_id must be a nonempty string.')
    sql = """WITH spawns AS (
        SELECT id AS log_id, ts, node, instance_id, request_id,
            CAST(regexp_extract(message, 'Took ([0-9.]+) seconds to spawn', 1) AS DOUBLE) AS sek
        FROM logs WHERE dataset='OpenStack' AND message LIKE '%%seconds to spawn%%'
    ), kennzahlen AS (
        SELECT COUNT(*) AS gesamt_vms, ROUND(MEDIAN(sek), 1) AS median_sek,
            ROUND(AVG(sek), 1) AS schnitt_sek, MIN(sek) AS min_sek, MAX(sek) AS max_sek
        FROM spawns WHERE sek IS NOT NULL
    ), rangliste AS (
        SELECT s.*, RANK() OVER (ORDER BY sek DESC) AS platz,
            ROW_NUMBER() OVER (ORDER BY sek DESC, log_id) AS auswahl,
            k.gesamt_vms, k.median_sek, k.schnitt_sek, k.min_sek, k.max_sek
        FROM spawns s CROSS JOIN kennzahlen k WHERE sek IS NOT NULL
    ) SELECT * FROM rangliste
    WHERE auswahl<=%s OR auswahl=(SELECT MIN(auswahl) FROM rangliste WHERE instance_id=%s)
    ORDER BY auswahl LIMIT %s"""
    result = _limited(sql, [limit, instance_id], limit + 1 if instance_id else limit)
    result['daten'].sort(key=lambda row: row['auswahl'])
    total = int(result['daten'][0]['gesamt_vms']) if result['daten'] else 0
    result['meta'].update(gekuerzt=total > result['zeilen'], total_observations=total)
    result['truncated'] = total > result['zeilen']
    if instance_id:
        matches = [r for r in result['daten'] if r.get('instance_id') == instance_id]
        if matches:
            result['gesuchte_vm'] = matches[0]
        else:
            result['warnings'] = ['No spawn observation matched the requested VM. Showing the top observations instead.']
    result['meta'].update(scope='Full OpenStack corpus; active dashboard time/team filters do not apply.',
                          count_unit='Spawn log entries, not distinct VMs')
    return result
