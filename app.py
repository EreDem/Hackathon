"""Log Observatory: local, evidence-first investigation workspace."""
from datetime import datetime, time, timezone
from importlib import import_module
import json

from dotenv import load_dotenv
load_dotenv()  # DB_DSN must be available before tools.db is imported.

import streamlit as st
from tools.db import query
from tools.engineer import search_logs, get_context, vm_dauer
from tools.analytics import top_patterns, pattern_trend, priority_ranking
from tools.visuals import search_distribution, period_comparison
import ui

st.set_page_config(page_title='Log Observatory', page_icon=':material/troubleshoot:', layout='wide')

ROLE_COPY = {
    'Engineer': ('Reconstruct the moment.', 'Find the signal, follow the surrounding events, and choose the next diagnostic check.'),
    'Team Lead': ('See the pattern behind the noise.', 'Understand recurrence, ownership and how observed problems evolve over time.'),
    'Manager': ('Put attention where it matters.', 'Compare measured frequency and reach. Make the reasoning behind priorities visible.'),
}
PROMPTS = {
    'Engineer': 'Investigate data TLB error interrupt. What do the logs establish, and what should we check next?',
    'Team Lead': 'Which problems recur for HPC Kernel? Show frequency, reach and a trend before recommending an investigation.',
    'Manager': 'Which BGL problems deserve attention first? Explain frequency versus observed reach and the limitations of the priority score.',
}
CATALOG_SQL = """SELECT l.dataset, COALESCE(o.team, 'Unassigned') AS team,
    COUNT(*) AS logzeilen_gesamt, MIN(l.ts) AS erstmals, MAX(l.ts) AS zuletzt
    FROM logs l LEFT JOIN ownership o ON o.dataset=l.dataset AND o.component=l.component
    GROUP BY l.dataset, o.team ORDER BY l.dataset, o.team"""

for key, default in {'catalog': None, 'catalog_error': None, 'connected_once': False, 'scope': None,
                     'results': {}, 'records': {}, 'conversation': [], 'generation': 0,
                     'tool_error': None, 'role': 'Engineer', 'dataset': 'BGL', 'agent_issue': None}.items():
    if key not in st.session_state:
        st.session_state[key] = default
s = st.session_state


def reset_workspace():
    s.results, s.records, s.conversation = {}, {}, []
    s.generation += 1
    s.tool_error = None
    s.agent_issue = None


def call_tool(slot, tool, function, **inputs):
    # Remove prior output first: a failed refresh must never present stale data as current.
    s.results.pop(slot, None)
    s.records.pop(slot, None)
    s.tool_error = None
    try:
        with st.spinner(f'Running {tool} in SereneDB…'):
            result = function(**inputs)
        s.results[slot] = result
        s.records[slot] = {'tool': tool, 'inputs': inputs, 'result': result}
        return result
    except Exception as exc:
        s.tool_error = f'{tool} failed ({type(exc).__name__}). Check the database and inputs, then retry.'
        st.error(s.tool_error)
        return None


def connect():
    reset_workspace()
    s.scope = None
    try:
        with st.spinner('Reading historical data bounds…'):
            s.catalog = query(CATALOG_SQL, limit=10000)
        s.catalog_error = None
    except Exception as exc:
        s.catalog = None
        s.catalog_error = f'Database unavailable ({type(exc).__name__}). Check DB_DSN and start SereneDB.'
    s.connected_once = True


def scope_inputs():
    return {k: s.scope[k] for k in ('dataset', 'team', 'von', 'bis')}


def inspect_context(identifier, window=600):
    signature = (str(identifier), window)
    if s.get('context_signature') != signature or 'context' not in s.results:
        result = call_tool('context', 'get_context', get_context, log_id=identifier, fenster_sek=window)
        if result is not None:
            s.context_signature = signature


def render_context():
    result = s.results.get('context')
    if result is None:
        return
    with st.container(border=True):
        st.subheader('Event lens', icon=':material/timeline:')
        ui.notices(result)
        st.caption(result.get('meta', {}).get('scope', 'No matching anchor event.'))
        rows = result['daten']
        if not rows:
            st.info('No context found for this identifier.')
            return
        anchor = result.get('meta', {}).get('anchor', {})
        ui.chart(ui.timeline(rows, anchor.get('id')), 'Events by timestamp, component and labeled severity', 'event_timeline')
        st.caption('Markers group log lines by second, component and severity; labels show their counts. Larger marker includes the selected anchor. Hover shows exact first/last times and example IDs; individual messages remain below. Drag to zoom; double-click to reset.')
        selected = st.selectbox('Event details', [r['id'] for r in rows],
                                index=next((i for i, r in enumerate(rows) if r['id'] == anchor.get('id')), 0),
                                key=f"detail_{s.generation}_{anchor.get('id')}")
        event = next(r for r in rows if r['id'] == selected)
        st.badge(event.get('level', 'UNKNOWN'), color='orange' if event.get('level') in ('WARN', 'ERROR', 'FATAL') else 'blue')
        st.code(event.get('message', ''), language=None, wrap_lines=True)
        st.caption(' · '.join(f'{ui.LABELS.get(k, k)}: {event[k]}' for k in ('id', 'ts', 'component', 'node', 'instance_id', 'request_id') if event.get(k) is not None))
        st.dataframe(ui.table(rows), hide_index=True, alt='Chronological context logs')
        if result.get('ausbruch_analyse'):
            outbreak = result['ausbruch_analyse']
            st.caption('Same-pattern observations across all BGL nodes in the context window; this does not confirm a common cause.')
            with st.container(horizontal=True):
                st.metric('Matching log lines', f"{outbreak['vorkommen_im_fenster']:,}", border=True, width=220)
                st.metric('Observed nodes', f"{outbreak['knoten_im_fenster']:,}", border=True, width=220)
        if result.get('request_verlauf'):
            with st.expander('Related request timeline'):
                st.dataframe(ui.table(result['request_verlauf']), hide_index=True, alt='Related request logs')


st.caption('SERENEDB / INVESTIGATION WORKSPACE')
st.title('Log Observatory', anchor=False)

with st.sidebar:
    st.subheader('Observatory', icon=':material/radar:')
    st.caption('One corpus. Three perspectives.')
    role = st.selectbox('Your perspective', list(ROLE_COPY), key='role')
    if st.button('Reconnect / refresh data', icon=':material/sync:', width='stretch'):
        connect()

if not s.connected_once:
    connect()

with st.sidebar:
    st.divider()
    if s.catalog and s.catalog['daten']:
        datasets = sorted({r['dataset'] for r in s.catalog['daten']})
        if s.dataset not in datasets:
            s.dataset = datasets[0]
        dataset = st.selectbox('Dataset', datasets, key='dataset')
        available = [r for r in s.catalog['daten'] if r['dataset'] == dataset]
        teams = sorted({r['team'] for r in available})
        starts = [r['erstmals'] for r in available if r['erstmals'] is not None]
        ends = [r['zuletzt'] for r in available if r['zuletzt'] is not None]
        with st.form('scope_form'):
            team = st.selectbox('Ownership team', ['All teams'] + teams, key=f'team_{dataset}')
            if starts and ends:
                lower, upper = min(starts).date(), max(ends).date()
                dates = st.date_input('Historical date range', value=(lower, upper), min_value=lower, max_value=upper, key=f'dates_{dataset}')
            else:
                dates = ()
                st.caption('No timestamped records available.')
            apply_scope = st.form_submit_button('Apply scope', icon=':material/filter_alt:', width='stretch')
        if s.scope is None or s.scope['dataset'] != dataset or s.scope['role'] != role or apply_scope:
            if len(dates) != 2:
                st.warning('Select both historical dates to apply this scope.')
                if s.scope and (s.scope['dataset'] != dataset or s.scope['role'] != role):
                    reset_workspace()
                    s.scope = None
            else:
                reset_workspace()
                s.scope = dict(role=role, dataset=dataset, team=None if team == 'All teams' else team,
                               von=datetime.combine(dates[0], time.min, timezone.utc),
                               bis=datetime.combine(dates[1], time.max, timezone.utc))
        st.caption('Dates follow the stored timestamp convention. BGL local times were imported as UTC; no timezone correction is applied.')
    else:
        if s.scope is not None:
            reset_workspace()
            s.scope = None
    st.divider()
    st.caption('LOCAL WORKSPACE / READ-ONLY ANALYSIS')
    st.caption('Queries run on action. Chart zoom and display controls reuse results.')

st.header(ROLE_COPY[role][0], anchor=False)
st.caption(ROLE_COPY[role][1])

if not s.scope:
    st.badge('Database not connected', color='orange', icon=':material/cloud_off:')
    st.info(s.catalog_error or 'Load the BGL and OpenStack corpus, then reconnect to begin.')
    with st.container(border=True):
        st.subheader('Connect your evidence')
        st.markdown('Start the SereneDB container, prepare and load the challenge data, then select **Reconnect / refresh data**. See the repository README for the complete setup.')
        st.code('docker compose up -d\npython ingest/prepare.py data/BGL/BGL.log "data/OpenStack/openstack_*.log"\npython ingest/run_sql.py ingest/load.sql', language='powershell')
    with st.container(horizontal=True):
        for name, icon, copy in [('01 / Engineer', 'troubleshoot', 'Search → event timeline → next check'),
                                 ('02 / Team Lead', 'monitoring', 'Recurring patterns → trends → ownership'),
                                 ('03 / Manager', 'flag', 'Frequency × reach → explainable priorities')]:
            with st.container(border=True, width=300):
                st.subheader(name, icon=f':material/{icon}:')
                st.caption(copy)
else:
    scope = scope_inputs()
    with st.container(horizontal=True):
        st.badge('Database connected', color='green', icon=':material/database:')
        st.badge(scope['dataset'], color='blue')
        st.badge(scope['team'] or 'All teams', color='gray')
    st.caption(f"Active scope: {scope['von']:%d %b %Y} — {scope['bis']:%d %b %Y} · Apply scope to commit sidebar changes.")
    dataset_rows = [r for r in s.catalog['daten'] if r['dataset'] == scope['dataset']]
    with st.container(horizontal=True):
        st.metric('Available dataset log lines', f"{sum(r['logzeilen_gesamt'] for r in dataset_rows):,}", help='Entire dataset before the active team and date filters.', border=True, width=250)
        st.metric('Ownership teams', str(len(dataset_rows)), border=True, width=200)
        st.metric('Evidence source', 'Live SQL', help='No synthetic metrics are displayed.', border=True, width=200)

    if st.button('Run prepared investigation', icon=':material/play_circle:'):
        reset_workspace()
        if role == 'Engineer':
            call_tool('search', 'search_logs', search_logs,
                      query='data TLB error interrupt' if scope['dataset'] == 'BGL' else 'qemu-img', **scope)
        elif role == 'Team Lead':
            call_tool('patterns', 'top_patterns', top_patterns, limit=100, **scope)
        else:
            call_tool('ranking', 'priority_ranking', priority_ranking, group_by='template', limit=1000, **scope)

    if role == 'Engineer':
        with st.form('search_form'):
            text = st.text_input('Search the logs', value='data TLB error interrupt' if scope['dataset'] == 'BGL' else 'qemu-img', key='search_text')
            left, right = st.columns(2)
            with left:
                mode = st.radio('Match mode', ['phrase', 'all', 'any'], horizontal=True)
            with right:
                levels = st.multiselect('Severity', ['DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'], help='Empty includes all levels.')
            submitted = st.form_submit_button('Search evidence', type='primary', icon=':material/search:')
        if submitted:
            s.results.pop('distribution', None)
            s.records.pop('distribution', None)
            s.results.pop('context', None)
            s.records.pop('context', None)
            s.generation += 1
            call_tool('search', 'search_logs', search_logs, query=text, modus=mode or 'phrase', level=levels or None, **scope)
        result = s.results.get('search')
        if result is not None:
            ui.notices(result)
            st.subheader('Search evidence')
            search_inputs = s.records['search']['inputs']
            st.caption(f"Results for: {search_inputs['query']} · effective mode: {result.get('meta', {}).get('modus', search_inputs.get('modus', 'phrase'))}. Edited controls take effect after Search evidence.")
            with st.container(horizontal=True):
                st.metric('Matching log lines', f"{result['gesamt_treffer']:,}" if 'gesamt_treffer' in result else 'Unavailable', border=True, width=220)
                st.metric('Examples returned', str(result['zeilen']), border=True, width=220)
            if not result['daten']:
                st.info('No matching log lines. Try fewer words, another severity, or a wider scope.')
            else:
                event = st.dataframe(ui.table(result['daten'], ['id', 'ts', 'level', 'component', 'message']), hide_index=True,
                                     on_select='rerun', selection_mode='single-row', key=f'logs_{s.generation}',
                                     alt='Search results; select a row to retrieve nearby events')
                selected_rows = event.selection.rows
                ids = [r['id'] for r in result['daten']]
                picker_key = f'log_picker_{s.generation}'
                selection_signature = (s.generation, tuple(selected_rows))
                if selected_rows and s.get('last_table_selection') != selection_signature:
                    s[picker_key] = ids[selected_rows[0]]
                s.last_table_selection = selection_signature
                identifier = st.selectbox('Inspect a log (keyboard alternative to row selection)', ids, index=None, key=picker_key)
                window = st.number_input('Context window in seconds', 1, 86400, 600, key='window')
                if identifier is not None:
                    inspect_context(identifier, int(window))
            st.subheader('Where the signal clusters')
            map_interval = st.selectbox('Map resolution', ['1 hour'] if scope['dataset'] == 'OpenStack' else ['1 day', '1 week'])
            if st.button('Map all matching logs'):
                s.pop(f'map_cell_{s.generation}', None)
                call_tool('distribution', 'search_distribution', search_distribution,
                          **{**search_inputs, 'modus': result.get('meta', {}).get('modus', search_inputs.get('modus', 'phrase'))},
                          intervall=map_interval)
            distribution = s.results.get('distribution')
            if distribution is not None:
                ui.notices(distribution)
                rows = distribution['daten']
                summary = next((r for r in rows if r['kind'] == 'summary'), {})
                ui.chart(ui.search_bursts(rows), 'All search matches over time, with observation gaps', 'bursts')
                ui.chart(ui.resource_heatmap(rows), 'Matching lines by resource and time', 'resource_map')
                st.caption('Coverage strip: cyan = scoped logs recorded, gray = no observation. Heatmap color uses a linear scale for counts up to 20 and a logarithmic scale for larger bursts; hover shows exact counts.')
                st.caption(f"Full-match aggregation; map shows up to 20 {distribution['meta']['resource_unit'].lower()}s. Missing resource: {summary.get('missing_resource', 0):,} lines; missing time: {summary.get('missing_time', 0):,} lines. Blank columns mean no scoped logs, not zero errors. Resolution: {distribution['meta']['filter']['intervall']}.")
                cells = [r for r in rows if r['kind'] == 'cell']
                cell = st.selectbox('Inspect a resource/time cell', range(len(cells)), index=None,
                    format_func=lambda i: f"{cells[i]['resource']} · {cells[i]['zeit']} · {cells[i]['n']:,} lines",
                    key=f'map_cell_{s.generation}')
                if cell is not None and st.button('Open resource event lens',
                        on_click=lambda: s.update({f'log_picker_{s.generation}': None})):
                    inspect_context(cells[cell]['example_log_id'])
        if scope['dataset'] == 'OpenStack':
            with st.expander('VM spawn-duration laboratory', expanded=True, icon=':material/speed:'):
                st.caption('Full OpenStack corpus comparison. Dashboard team/date filters do not apply; counts are spawn log entries, not unique VMs.')
                with st.form('duration_form'):
                    vm = st.text_input('VM identifier (optional)', placeholder='544fd51c-4edc-4780-baae-ba1d80a0acfc')
                    duration_submit = st.form_submit_button('Compare spawn durations')
                if duration_submit:
                    call_tool('durations', 'vm_dauer', vm_dauer, instance_id=vm.strip() or None)
                duration_result = s.results.get('durations')
                if duration_result is not None:
                    ui.notices(duration_result)
                    if duration_result['daten']:
                        ui.chart(ui.durations(duration_result['daten'], duration_result.get('gesuchte_vm', {}).get('instance_id')), 'Spawn observations ranked by duration with corpus median', 'duration_chart')
                        st.dataframe(ui.table(duration_result['daten']), hide_index=True, alt='Exact spawn durations and corpus statistics')
                        vm_choice = st.selectbox('Inspect a spawn observation', [r['log_id'] for r in duration_result['daten']], index=None)
                        if vm_choice is not None and st.button('Open VM event lens'):
                            inspect_context(vm_choice)
                    else:
                        st.info('No recorded spawn durations found.')
        render_context()

    elif role == 'Team Lead':
        if st.button('Analyze recurring patterns', type='primary', icon=':material/monitoring:'):
            for slot in list(s.results):
                if slot.startswith('comparison_'):
                    s.results.pop(slot, None)
                    s.records.pop(slot, None)
            s.results.pop('trend', None)
            s.records.pop('trend', None)
            s.generation += 1
            call_tool('patterns', 'top_patterns', top_patterns, limit=100, **scope)
        result = s.results.get('patterns')
        if result is not None:
            ui.notices(result)
            scope_rows = result['meta']['bereich']['daten']
            st.metric('All log lines in active scope', f"{sum(r['logzeilen_gesamt'] for r in scope_rows):,}", help='All severities, before error/pattern selection.', border=True)
            metric_name = st.radio('Count measure', ['Log lines', 'Approx. events'], horizontal=True)
            metric = 'ereignisse' if metric_name == 'Approx. events' else 'n'
            st.caption('BGL: ERROR/FATAL. OpenStack: WARN/ERROR/FATAL. Approximate events are not confirmed incidents; do not add per-pattern OpenStack event counts.')
            if not result['daten']:
                st.info('No recurring warning/error patterns in this scope.')
            else:
                ui.chart(ui.pattern_bars(result['daten'], metric), 'Most frequent patterns in the active scope (top 15 displayed)', 'pattern_chart')
                with st.expander('Pattern concentration', expanded=True):
                    ui.chart(ui.pareto(result['daten']), 'Pattern log lines and cumulative share of all matching lines', 'pareto')
                    st.caption('Top 15 patterns. Cumulative percentage uses all matching log lines, including patterns outside this display. Approximate OpenStack event counts cannot be added across patterns.')
                st.dataframe(ui.table(result['daten'], ['template_id', 'template', 'team', 'n', 'ereignisse', 'alerts', 'knoten', 'vms', 'requests']), hide_index=True, alt='Pattern counts, ownership and observed identifiers')
                patterns = {f"{r['template_id']} · {r['team']}": r for r in result['daten']}
                chosen = st.selectbox('Follow a pattern', list(patterns), key=f'pattern_{s.generation}')
                pattern = patterns[chosen]
                interval = st.radio('Trend resolution', ['1 hour'] if scope['dataset'] == 'OpenStack' else ['1 day', '1 week'], horizontal=True)
                signature = (pattern['template_id'], pattern['team'], interval)
                if s.get('trend_signature') != signature or 'trend' not in s.results:
                    trend_scope = {**scope, 'team': pattern['team']}
                    if call_tool('trend', 'pattern_trend', pattern_trend, template_id=pattern['template_id'], intervall=interval, **trend_scope) is not None:
                        s.trend_signature = signature
                trend_result = s.results.get('trend')
                if trend_result is not None:
                    st.subheader('Recurrence over time')
                    ui.notices(trend_result)
                    ui.chart(ui.trend(trend_result['daten'], metric), 'Pattern trend with observation gaps preserved', 'trend_chart')
                    st.caption('A gap means no scoped logs were observed; zero means logs were recorded without this matching error. Coverage strip: cyan = recorded logs, gray = no observation. Drag to zoom; double-click to reset.')
                if st.button('Compare leading patterns'):
                    for slot in list(s.results):
                        if slot.startswith('comparison_'):
                            s.results.pop(slot, None)
                            s.records.pop(slot, None)
                    for index, item in enumerate(result['daten'][:4]):
                        call_tool(f'comparison_{index}', 'pattern_trend', pattern_trend,
                            template_id=item['template_id'], intervall=interval,
                            **{**scope, 'team': item['team']})
                comparisons = {f"{record['inputs']['template_id']} · {record['inputs']['team']}": record['result']['daten']
                    for slot, record in s.records.items() if slot.startswith('comparison_')}
                if comparisons:
                    st.subheader('Leading patterns side by side')
                    if len(comparisons) < min(4, len(result['daten'])):
                        st.warning('Some pattern queries failed. Only successful series are shown; missing series do not mean zero observations.')
                    st.caption('Up to four leading patterns by log-line count. Each row uses its ownership team’s observation coverage. Blank periods are gaps; shared axes preserve scale. Apply Compare leading patterns after changing resolution.')
                    ui.chart(ui.pattern_comparison(comparisons, metric), 'Leading pattern trends on shared axes', 'small_multiples')
                    ui.chart(ui.pattern_comparison(comparisons, metric, heatmap=True), 'Leading patterns by time heatmap', 'pattern_heatmap')
                    for slot, record in s.records.items():
                        if slot.startswith('comparison_'):
                            ui.notices(record['result'])

    else:
        with st.form('ranking_form'):
            grouping = st.radio('Prioritize', ['Problems', 'Teams'], horizontal=True)
            ranking_submit = st.form_submit_button('Build priority board', type='primary', icon=':material/flag:')
        if ranking_submit:
            s.generation += 1
            s.results.pop('context', None)
            s.records.pop('context', None)
            call_tool('ranking', 'priority_ranking', priority_ranking, group_by='team' if grouping == 'Teams' else 'template', limit=1000, **scope)
        result = s.results.get('ranking')
        if result is not None:
            ui.notices(result)
            st.caption('Priority scores are heuristics, not measured downtime, financial loss or customer impact. Reach counts observed identifiers.')
            groups = ui.ranking_groups(result['daten'])
            if not groups:
                st.info('No problems to rank in this scope.')
            else:
                group = st.selectbox('Comparison group', list(groups),
                                     format_func=lambda g: g.replace(':knoten', ' · observed nodes').replace(':vms', ' · observed VMs').replace(':requests', ' · observed requests').replace(':unbekannt', ' · unknown reach'),
                                     help='Ranks are comparable only inside the same dataset and reach unit.')
                rows = groups[group]
                scored = [r for r in rows if r.get('score') is not None]
                st.caption(f"Ranking by {s.records['ranking']['inputs']['group_by']} · {group}. Changing form controls takes effect after Build priority board.")
                if scored:
                    left_chart, right_chart = st.columns(2)
                    with left_chart:
                        with st.container(border=True):
                            st.subheader('Attention queue')
                            ui.chart(ui.priority_bars(scored), 'Priority scores within the selected comparison group', 'priority_chart')
                    with right_chart:
                        with st.container(border=True):
                            st.subheader('Frequency × reach')
                            ui.chart(ui.reach_scatter(scored), 'Observed frequency versus reach; bubble size represents severity', 'reach_chart')
                    st.caption('Frequency uses a logarithmic axis so rare problems remain visible. Bubble size = severity weight. Coincident points retain their exact coordinates; hover lists the problems at that position. Charts share this comparison group only.')
                    st.dataframe(ui.table(scored, ['rang', 'gruppe', 'teams', 'n', 'ereignisse', 'haeufigkeit', 'reichweite', 'score']), hide_index=True, alt='Priorities and supporting measurements')
                    chosen = st.selectbox('Explain a priority', [r['gruppe'] for r in scored], key=f'priority_{s.generation}_{group}')
                    item = next(r for r in scored if r['gruppe'] == chosen)
                    priority_signature = (s.generation, group, chosen)
                    if s.get('priority_signature') != priority_signature:
                        s.results.pop('context', None)
                        s.records.pop('context', None)
                        s.priority_signature = priority_signature
                    with st.container(border=True):
                        st.subheader('Why this priority?')
                        st.code('score = frequency_norm × severity × reach_norm × trend × alert', language=None)
                        factor_keys = ['haeufigkeit_norm', 'schweregrad', 'reichweite_norm', 'trendfaktor', 'alertfaktor']
                        st.dataframe([{'Factor': name, 'Value': float(item[k])} for k, name in zip(factor_keys, ['Normalized frequency', 'Severity weight', 'Normalized reach', 'Trend factor', 'Alert factor'])], hide_index=True, alt='All factors contributing to the priority score')
                        st.caption('Trend compares two equal calendar periods. Observation gaps can affect the result; a missing or zero-length period uses a neutral factor.')
                        st.caption('Components: ' + ', '.join(item.get('komponenten') or []))
                        st.caption(f"Frequency: {item['haeufigkeit']:,} · observed reach: {item['reichweite']:,} · log lines: {item['n']:,} · approximate events: {item['ereignisse']:,}")
                        if st.button('Investigate supporting logs', icon=':material/troubleshoot:'):
                            inspect_context(item['example_log_id'])
                unknown = [r for r in result['daten'] if r.get('score') is None]
                if unknown:
                    st.subheader('Insufficient reach data')
                    st.caption('These problems remain visible, but cannot receive a meaningful reach-based score.')
                    st.dataframe(ui.table(unknown, ['dataset', 'gruppe', 'n', 'ereignisse', 'score']), hide_index=True, alt='Unscored problems with missing observed reach')
                render_context()
        st.subheader('Team balance and historical change')
        if st.button('Compare teams and periods'):
            call_tool('team_comparison', 'priority_ranking', priority_ranking, group_by='team', limit=1000, **scope)
            call_tool('period_comparison', 'period_comparison', period_comparison,
                      intervall='1 hour' if scope['dataset'] == 'OpenStack' else '1 day', **scope)
        teams = s.results.get('team_comparison')
        if teams is not None:
            ui.notices(teams)
            team_groups = ui.ranking_groups(teams['daten'])
            if team_groups:
                team_group = st.selectbox('Team comparison unit', list(team_groups))
                ui.chart(ui.team_comparison(team_groups[team_group]), 'Team frequency and observed reach on separate axes within one comparison group', 'team_dots')
                st.caption('Separate axes retain original measurements. Reach counts observed identifiers; missing reach is not zero impact.')
                st.dataframe(ui.table(team_groups[team_group]), hide_index=True, alt='Exact team comparison measurements')
        periods = s.results.get('period_comparison')
        if periods is not None:
            ui.notices(periods)
            ui.chart(ui.period_bars(periods['daten']), 'Two calendar halves: matching lines, normalized line share and observation coverage', 'period_bars')
            st.caption('Two equal calendar periods. BGL matches ERROR/FATAL; OpenStack matches WARN/ERROR/FATAL. Coverage means at least one scoped log in a calendar bucket, not uptime. A blank rate has no observed denominator. Rows without timestamps are excluded.')
            st.dataframe(ui.table(periods['daten']), hide_index=True, alt='Period boundaries, counts and calendar bucket coverage')
    if s.tool_error:
        st.caption(s.tool_error)
    ui.evidence_panel([{'tool': 'Dataset catalog', 'inputs': {}, 'result': s.catalog}] + list(s.records.values()))

st.divider()
st.subheader('Ask the investigator', icon=':material/forum:')
st.caption('The assistant explains tool evidence and recommends the next check. Direct exploration above works without an AI API key.')
try:
    agent = import_module('agent.agent')
    answer = getattr(agent, 'antworte')
    agent_error = None
    readiness = agent.configuration_status() if hasattr(agent, 'configuration_status') else {'configured': True}
except ModuleNotFoundError as exc:
    answer = None
    agent_error = 'Agent not connected' if exc.name == 'agent.agent' else f'Agent dependency unavailable ({exc.name}).'
except (ImportError, AttributeError) as exc:
    answer, agent_error = None, f'Agent initialization failed ({type(exc).__name__}).'
except Exception as exc:
    answer, agent_error = None, f'Agent initialization failed ({type(exc).__name__}). Check the agent configuration.'

if answer is None:
    st.badge(agent_error, color='orange', icon=':material/link_off:')
    st.caption('Person 4 can connect agent.agent.antworte without changing the UI. Chat stays disabled until then.')
elif not readiness['configured']:
    st.warning('Agent installed. Add OPENAI_API_KEY to the local .env to enable chat.' if not readiness.get('key_configured')
               else 'Agent installed, but its database tools are unavailable.')
else:
    st.badge('Agent connected', color='green', icon=':material/link:')
    st.caption(f"{readiness.get('model', 'Configured model')} · Up to 4 model requests / 6 tool calls per investigation · Local $5 test ledger.")

chat_ready = answer is not None and readiness['configured'] and s.scope is not None

st.caption('Prepared question for this perspective')
prepared = PROMPTS[role]
if s.scope and s.scope['dataset'] == 'OpenStack':
    prepared = {
        'Engineer': 'Investigate VM 544fd51c-4edc-4780-baae-ba1d80a0acfc. Compare its spawn duration with the recorded baseline and inspect its context.',
        'Team Lead': 'Which problems recur in the selected OpenStack scope? Distinguish log lines from approximate events and inspect their historical trend.',
        'Manager': 'Which OpenStack problems should we investigate first within this scope? Explain observed reach, frequency, score factors and missing data.'}[role]
elif s.scope and role == 'Team Lead':
    prepared = f"Which problems recur for {s.scope['team'] or 'the selected BGL scope'}? Show frequency, reach and a trend before recommending an investigation."
st.code(prepared, language=None, wrap_lines=True)
if chat_ready and st.button('Ask the prepared question', icon=':material/play_arrow:'):
    s.pending_question = prepared
for index, message in enumerate(s.conversation):
    with st.chat_message(message['role']):
        st.markdown(message['content'])
        if message.get('meta'):
            ui.agent_status(message['meta'])
        if message.get('evidence'):
            ui.evidence_panel(message['evidence'], key=f'chat_evidence_{index}')
if s.agent_issue:
    ui.agent_status(s.agent_issue['meta'])
    ui.evidence_panel(s.agent_issue['evidence'], key='failed_agent_evidence')
with st.container():
    question = st.chat_input('Ask about the logs in the active scope…', disabled=not chat_ready, max_chars=3500)
question = question or s.pop('pending_question', None)
if question and chat_ready:
    history = [{'role': m['role'], 'content': m['content']} for m in s.conversation]
    try:
        if len(question) > 3500:
            raise ValueError('Question too long.')
        s.agent_issue = None
        with st.spinner('Agent is investigating…'):
            response = answer(rolle=role, team=s.scope['team'], frage=question, verlauf=history,
                              language='en', scope=json.loads(json.dumps(scope_inputs(), default=str)))
        message = ui.agent_message(response)
        if message['meta'].get('status', 'ok') == 'ok':
            s.conversation.extend([{'role': 'user', 'content': question}, message])
            s.conversation = s.conversation[-20:]
        else:
            s.agent_issue = message
        st.rerun()
    except Exception as exc:
        st.error(f'Agent request failed ({type(exc).__name__}). No answer was substituted. Retry after checking the agent configuration.')
st.caption('LOG OBSERVATORY / Facts → hypotheses → next checks. Log entries are not automatically incidents.')
