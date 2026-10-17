"""Read-only chart queries. Reuse the tools' scope, search and event conventions."""
from tools import analytics as a
from tools.engineer import _baue_filter


def _scope(dataset, team, von, bis, intervall):
    if dataset not in ('BGL', 'OpenStack'):
        raise ValueError('Select one dataset for comparable chart units.')
    if not isinstance(intervall, str) or intervall not in a.INTERVALS:
        raise ValueError('Interval must be 1 hour, 1 day or 1 week.')
    von, bis = a._validate(dataset, team, von, bis, 1)
    base, params = a._base(dataset, team, von, bis)
    return base, params, dict(dataset=dataset, team=team, von=von, bis=bis, intervall=intervall)


def _run(sql, params, filters, limit=10000, **meta):
    result = a._query(sql + ' LIMIT %s', params + [limit + 1], limit + 1)
    truncated = len(result['daten']) > limit
    result['daten'] = result['daten'][:limit]
    result['zeilen'] = len(result['daten'])
    result['meta'] = dict(filter=filters, limit=limit, gekuerzt=truncated, **meta)
    return result


def search_distribution(query, dataset, team=None, von=None, bis=None, level=None,
                        modus='phrase', intervall='1 day'):
    """Aggregate ALL matching search lines; time buckets plus top 20 resource rows.

    kind=summary covers all matches, time covers all timestamped matches, cell
    covers top resources only. example_log_id links nonempty buckets to real logs.
    BGL resources are nodes; OpenStack resources are components, never mixed IDs.
    Observation coverage is scoped all-level logs, not service availability.
    """
    base, params, filters = _scope(dataset, team, von, bis, intervall)
    where, search_params = _baue_filter(query, modus, None, level, None, None, None)
    filters.update(query=query, level=level, modus=modus)
    sql = base + """, settings AS (SELECT %s::INTERVAL AS step), matched AS (
        SELECT s.*, CASE WHEN s.dataset='BGL'
            THEN NULLIF(NULLIF(NULLIF(TRIM(s.node), 'NULL'), '-'), '')
            ELSE NULLIF(TRIM(s.component), '') END AS resource
        FROM scope s JOIN logs_idx i ON i.id=s.id WHERE """ + where + """
    ), resources AS (
        SELECT resource, COUNT(*) AS n FROM matched WHERE resource IS NOT NULL
        GROUP BY resource ORDER BY n DESC, resource LIMIT 20
    ), observed AS (
        SELECT time_bucket(step, ts) AS zeit, COUNT(*) AS observed_logs
        FROM scope CROSS JOIN settings WHERE ts IS NOT NULL GROUP BY time_bucket(step, ts)
    ), matches_by_time AS (
        SELECT time_bucket(step, ts) AS zeit, COUNT(*) AS n, MIN(id) AS example_log_id
        FROM matched CROSS JOIN settings WHERE ts IS NOT NULL GROUP BY time_bucket(step, ts)
    ), grid AS (
        SELECT g.zeit FROM bounds b CROSS JOIN settings
        CROSS JOIN LATERAL generate_series(time_bucket(step,b.von),time_bucket(step,b.bis),step) g(zeit)
        WHERE b.von IS NOT NULL AND b.bis IS NOT NULL
    ), combined AS (
        SELECT 'summary' AS kind, NULL::TIMESTAMPTZ AS zeit, NULL::VARCHAR AS resource,
               COUNT(*) AS n, NULL::BIGINT AS observed_logs, MIN(id) AS example_log_id,
               COUNT(DISTINCT resource) AS resources, COUNT(*)-COUNT(resource) AS missing_resource,
               COUNT(*)-COUNT(ts) AS missing_time
        FROM matched
        UNION ALL
        SELECT 'time', g.zeit, NULL, CASE WHEN o.observed_logs IS NOT NULL THEN COALESCE(m.n,0) END,
               COALESCE(o.observed_logs,0), m.example_log_id, NULL,NULL,NULL
        FROM grid g LEFT JOIN observed o ON o.zeit=g.zeit LEFT JOIN matches_by_time m ON m.zeit=g.zeit
        UNION ALL
        SELECT 'cell', time_bucket(step,m.ts), m.resource, COUNT(*), NULL, MIN(m.id), NULL,NULL,NULL
        FROM matched m JOIN resources r ON r.resource=m.resource CROSS JOIN settings
        WHERE m.ts IS NOT NULL GROUP BY time_bucket(step,m.ts), m.resource
    ) SELECT * FROM combined
    ORDER BY CASE kind WHEN 'summary' THEN 0 WHEN 'time' THEN 1 ELSE 2 END, zeit, resource
    """
    return _run(sql, params + [intervall] + search_params, filters,
                resource_limit=20, resource_unit='Node' if dataset == 'BGL' else 'Component')


def period_comparison(dataset, team=None, von=None, bis=None, intervall='1 day'):
    """Compare two calendar halves with measured log coverage and line share.

    A bucket is observed if at least one scoped log exists in that half/bucket.
    Matching-line share is per 1,000 observed log lines, not an incident rate.
    Midpoint belongs only to the later half; the final bound is inclusive.
    """
    base, params, filters = _scope(dataset, team, von, bis, intervall)
    sql = base + a.EVENT_CTES + """, settings AS (SELECT %s::INTERVAL AS step), periods AS (
        SELECT dataset, 'Earlier half' AS period, von AS starts,
               von+(bis-von)/2 AS ends, von+(bis-von)/2-INTERVAL '1 microsecond' AS grid_end
        FROM bounds WHERE von IS NOT NULL AND bis IS NOT NULL
        UNION ALL
        SELECT dataset, 'Later half', von+(bis-von)/2, bis, bis
        FROM bounds WHERE von IS NOT NULL AND bis IS NOT NULL
    ), expected AS (
        SELECT p.period, COUNT(g.zeit) AS expected_buckets
        FROM periods p CROSS JOIN settings
        LEFT JOIN LATERAL generate_series(time_bucket(step,p.starts),time_bucket(step,p.grid_end),step) g(zeit)
          ON p.starts<=p.grid_end
        GROUP BY p.period
    ), observed AS (
        SELECT CASE WHEN s.ts<b.von+(b.bis-b.von)/2 THEN 'Earlier half' ELSE 'Later half' END AS period,
               COUNT(*) AS observed_logs, COUNT(DISTINCT time_bucket(step,s.ts)) AS observed_buckets
        FROM scope s JOIN bounds b ON b.dataset=s.dataset CROSS JOIN settings
        WHERE s.ts IS NOT NULL GROUP BY period
    ), matches AS (
        SELECT CASE WHEN m.ts<b.von+(b.bis-b.von)/2 THEN 'Earlier half' ELSE 'Later half' END AS period,
               COUNT(*) AS n, COUNT(DISTINCT m.event_id) AS ereignisse
        FROM marked m JOIN bounds b ON b.dataset=m.dataset WHERE m.ts IS NOT NULL GROUP BY period
    ) SELECT p.period, p.starts, p.ends, COALESCE(m.n,0) AS n,
        COALESCE(m.ereignisse,0) AS ereignisse, COALESCE(o.observed_logs,0) AS observed_logs,
        COALESCE(o.observed_buckets,0) AS observed_buckets, e.expected_buckets,
        COALESCE(m.n,0)*1000.0/NULLIF(o.observed_logs,0) AS lines_per_1000,
        COALESCE(o.observed_buckets,0)*100.0/NULLIF(e.expected_buckets,0) AS coverage_pct
    FROM periods p JOIN expected e ON e.period=p.period
    LEFT JOIN observed o ON o.period=p.period LEFT JOIN matches m ON m.period=p.period
    ORDER BY p.period
    """
    return _run(sql, params + [intervall], filters,
                notes='Coverage means any recorded log in a calendar bucket, not uptime. Rows without timestamps cannot be assigned to a half.')
