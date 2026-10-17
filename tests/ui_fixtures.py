"""Small, explicitly synthetic responses for UI tests only; never loaded by app.py."""
from copy import deepcopy
from datetime import datetime, timezone


def stamp(day=3, hour=0):
    return datetime(2005, 6, day, hour, tzinfo=timezone.utc)


def result(rows, **extra):
    return {'sql': 'SELECT fixture_evidence', 'zeilen': len(rows), 'daten': deepcopy(rows), **extra}


CATALOG = result([
    {'dataset': 'BGL', 'team': 'HPC Kernel', 'logzeilen_gesamt': 150, 'erstmals': stamp(), 'zuletzt': stamp(7)},
    {'dataset': 'OpenStack', 'team': 'Cloud Compute', 'logzeilen_gesamt': 75, 'erstmals': stamp(), 'zuletzt': stamp(7)},
])
LOGS = [dict(id=i, ts=stamp(3, i), dataset='BGL', level=level, component='KERNEL', message=message,
             template_id='BGL-0019', node='R20-M0-N0', instance_id=None, request_id=None)
        for i, level, message in [(1, 'INFO', 'Starting diagnostic check'), (2, 'FATAL', 'data TLB error interrupt'),
                                  (3, 'WARN', 'Diagnostic retry queued')]]
SEARCH = result(LOGS, gesamt_treffer=150, meta={'gekuerzt': True, 'limit': 3}, belege=[])
CONTEXT = result(LOGS, meta={'gekuerzt': False, 'anchor': LOGS[1], 'scope': 'BGL midplane, broader than a single node'},
                 ausbruch_analyse={'vorkommen_im_fenster': 7, 'knoten_im_fenster': 2})
META = {'gekuerzt': False, 'bereich': CATALOG, 'filter': {}, 'hinweise': ['Fixture scope only.']}
PATTERNS = result([
    dict(dataset='BGL', team='HPC Kernel', template_id='BGL-0019', template='data TLB error interrupt', n=80,
         ereignisse=80, alerts=70, knoten=2, vms=0, requests=0),
    dict(dataset='BGL', team='HPC Kernel', template_id='BGL-0119', template='data storage interrupt', n=40,
         ereignisse=40, alerts=40, knoten=20, vms=0, requests=0),
], meta=META)
TREND = result([
    dict(dataset='BGL', zeit=stamp(day), n=count, ereignisse=count, beobachtete_logs=0 if count is None else 30,
         datenluecke=count is None) for day, count in [(3, 5), (4, 0), (5, None), (6, 10), (7, 3)]
], meta=META)


def ranking():
    rows = []
    for index, name, reach, score in [(1, 'BGL-0119', 20, 1.8), (2, 'BGL-0019', 2, .4), (3, 'BGL-UNKNOWN', None, None)]:
        rows.append(dict(dataset='BGL', gruppe=name, teams=['HPC Kernel'], n=100-index*10, ereignisse=100-index*10,
                         haeufigkeit=100-index*10, reichweite=reach, schweregrad=3, score=score, rang=index if score else None,
                         vergleichsgruppe='BGL:knoten' if score else 'BGL:unbekannt',
                         haeufigkeit_norm=.8, reichweite_norm=.5, trendfaktor=1.1, alertfaktor=1.5,
                         trend_hinweis='Observation gaps may affect this comparison.', komponenten=['KERNEL'], example_log_id=2))
    return result(rows, meta=META)


DURATIONS = result([dict(log_id=10+i, instance_id=f'vm-{i}', sek=40-i*5, platz=i+1, auswahl=i+1,
                         median_sek=20, gesamt_vms=100) for i in range(4)], meta={'gekuerzt': False})
