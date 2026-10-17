"""Presentation helpers for Log Observatory. All measurements come from tools."""
from __future__ import annotations

import json
from math import log10
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

CYAN, AMBER, VIOLET = "#51D6E4", "#FFC66D", "#AFACFF"
LEVELS = {"DEBUG": "#9AAFC8", "INFO": CYAN, "WARN": AMBER, "ERROR": "#FF8A94", "FATAL": "#D3AEFF"}
SYMBOLS = {"DEBUG": "circle-open", "INFO": "circle", "WARN": "diamond", "ERROR": "x", "FATAL": "star"}
LABELS = {
    "id": "Log ID", "ts": "Timestamp", "dataset": "Dataset", "level": "Severity",
    "component": "Component", "service": "Service", "team": "Team", "template_id": "Pattern ID",
    "template": "Pattern", "message": "Message", "node": "Node", "instance_id": "VM ID",
    "request_id": "Request ID", "alert": "Alert label", "n": "Log lines", "ereignisse": "Approx. events",
    "alerts": "Alert lines", "knoten": "Observed nodes", "vms": "Observed VMs", "requests": "Observed requests",
    "komponenten": "Components", "erstmals": "First observed", "zuletzt": "Last observed",
    "gruppe": "Problem / team", "score": "Priority score", "rang": "Rank", "teams": "Teams",
    "reichweite": "Observed reach", "haeufigkeit": "Frequency", "schweregrad": "Severity weight",
    "logzeilen_gesamt": "Scope log lines", "zeitraum_von": "Scope start", "zeitraum_bis": "Scope end",
    "zeit": "Time", "datenluecke": "Observation gap", "beobachtete_logs": "Observed log lines",
    "sek": "Spawn seconds", "median_sek": "Median seconds", "platz": "Rank", "log_id": "Log ID",
}


def table(rows, columns=None):
    frame = pd.DataFrame(rows)
    if columns:
        frame = frame[[c for c in columns if c in frame.columns]]
    return frame.rename(columns=LABELS)


def finish(fig, x_title=None, y_title=None, height=350):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color="#E6EDF7", size=12),
        margin=dict(l=12, r=20, t=30, b=20), height=height,
        xaxis_title=x_title, yaxis_title=y_title, hoverlabel=dict(bgcolor="#17283E"),
        legend=dict(orientation="h", y=1.16, x=0),
    )
    fig.update_xaxes(gridcolor="#24344A", zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#24344A", zeroline=False, automargin=True)
    return fig


def timeline(rows, anchor_id=None):
    fig = go.Figure()
    for level, color in LEVELS.items():
        group = [r for r in rows if r.get("level") == level and r.get("ts") is not None]
        if not group:
            continue
        fig.add_trace(go.Scatter(
            x=[r["ts"] for r in group], y=[r.get("component") or "Unknown component" for r in group],
            mode="markers", name=level,
            marker=dict(color=color, symbol=SYMBOLS[level], size=[18 if r["id"] == anchor_id else 10 for r in group],
                        line=dict(width=1, color="#E6EDF7")),
            customdata=[[str(r["id"]), level, str(r.get("message", ""))[:240]] for r in group],
            hovertemplate="%{x}<br>%{y}<br>Log %{customdata[0]} · %{customdata[1]}<br>%{customdata[2]}<extra></extra>",
        ))
    fig.update_xaxes(rangeslider_visible=True)
    return finish(fig, "Recorded time", "Component", 390)


def pattern_bars(rows, metric="n"):
    ranked = sorted(rows, key=lambda r: r.get(metric) or 0, reverse=True)[:15]
    labels = [f"{r['template_id']} · {r.get('team', '')}" for r in ranked]
    fig = go.Figure(go.Bar(
        x=[r.get(metric) for r in ranked], y=labels, orientation="h", marker_color=CYAN,
        text=[r.get(metric) for r in ranked], textposition="auto",
        customdata=[[r.get("template", ""), r.get("n"), r.get("ereignisse")] for r in ranked],
        hovertemplate="%{y}<br>%{customdata[0]}<br>Log lines %{customdata[1]}<br>Approx. events %{customdata[2]}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    return finish(fig, LABELS[metric], height=max(300, min(550, len(ranked) * 32)))


def trend(rows, metric="n"):
    fig = go.Figure()
    for index, dataset in enumerate(sorted({r["dataset"] for r in rows})):
        group = sorted([r for r in rows if r["dataset"] == dataset], key=lambda r: str(r["zeit"]))
        fig.add_trace(go.Scatter(
            x=[r["zeit"] for r in group],
            y=[None if r.get("datenluecke") else r.get(metric) for r in group],
            mode="lines+markers", name=dataset, connectgaps=False,
            line=dict(color=[CYAN, VIOLET][index % 2], width=2), marker=dict(size=4),
            customdata=[[r.get("beobachtete_logs"), r.get("ereignisse"), r.get("n")] for r in group],
            hovertemplate="%{x}<br>Value %{y}<br>Observed lines %{customdata[0]}<br>Approx. events %{customdata[1]}<br>Matching lines %{customdata[2]}<extra>%{fullData.name}</extra>",
        ))
    fig.update_xaxes(rangeslider_visible=True)
    return finish(fig, "Recorded time · gaps mean no observation", LABELS[metric], 360)


def ranking_groups(rows):
    """Never combine incompatible dataset/reach units in one ranking."""
    groups = {}
    for row in rows:
        groups.setdefault(row["vergleichsgruppe"], []).append(row)
    return groups


def priority_bars(rows):
    scored = [r for r in rows if r.get("score") is not None][:15]
    fig = go.Figure(go.Bar(
        x=[r["score"] for r in scored], y=[r["gruppe"] for r in scored], orientation="h",
        marker_color=AMBER, text=[f"{r['score']:.3f}" for r in scored], textposition="auto",
        hovertemplate="%{y}<br>Heuristic score %{x:.4f}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    return finish(fig, "Priority score", height=max(300, min(520, len(scored) * 30)))


def reach_scatter(rows):
    scored = [r for r in rows if r.get("score") is not None and r.get("reichweite") is not None]
    fig = go.Figure(go.Scatter(
        x=[r["haeufigkeit"] for r in scored], y=[r["reichweite"] for r in scored], mode="markers",
        marker=dict(size=[12 + 5 * r["schweregrad"] for r in scored], color=[r["score"] for r in scored],
                    colorscale=[[0, "#52758F"], [1, CYAN]], showscale=False, line=dict(color="#E6EDF7", width=1)),
        customdata=[[r["gruppe"], r["score"], r["schweregrad"]] for r in scored],
        hovertemplate="%{customdata[0]}<br>Frequency %{x}<br>Observed reach %{y}<br>Score %{customdata[1]:.4f}<br>Severity weight %{customdata[2]}<extra></extra>",
    ))
    return finish(fig, "Frequency", "Observed identifiers")


def durations(rows, selected=None):
    fig = go.Figure(go.Bar(
        x=[r["sek"] for r in rows], y=[f"#{r['platz']} · {r['instance_id']} · log {r['log_id']}" for r in rows],
        orientation="h", marker_color=[AMBER if r.get("instance_id") == selected else CYAN for r in rows],
        text=[f"{r['sek']:.2f}s" for r in rows], textposition="auto",
        hovertemplate="%{y}<br>Spawn %{x:.3f} seconds<extra></extra>",
    ))
    if rows:
        fig.add_vline(x=rows[0]["median_sek"], line_dash="dash", line_color=VIOLET)
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines',
            line=dict(dash='dash', color=VIOLET), name=f"Corpus median {rows[0]['median_sek']}s"))
    fig.update_yaxes(autorange="reversed", tickmode="array",
                     tickvals=list(fig.data[0].y), ticktext=[f"#{r['platz']} · {str(r['instance_id'])[:8]}…" for r in rows])
    return finish(fig, "Spawn duration in seconds", height=max(300, min(600, len(rows) * 34)))


def chart(fig, name, key):
    st.plotly_chart(fig, key=key, width="stretch", theme=None, alt=name,
                    config={"displaylogo": False, "scrollZoom": False, "responsive": True})


def search_bursts(rows):
    buckets = [r for r in rows if r['kind'] == 'time']
    fig = go.Figure(go.Scatter(x=[r['zeit'] for r in buckets], y=[r['n'] for r in buckets],
        mode='lines+markers', connectgaps=False, line_color=CYAN,
        customdata=[[r['observed_logs']] for r in buckets],
        hovertemplate='%{x}<br>Matching lines %{y}<br>All scoped lines %{customdata[0]}<extra></extra>'))
    fig.update_xaxes(rangeslider_visible=True)
    return finish(fig, 'Recorded time · gaps mean no observation', 'Matching log lines')


def resource_heatmap(rows):
    times = sorted({r['zeit'] for r in rows if r['kind'] == 'time'})
    resources = sorted({r['resource'] for r in rows if r['kind'] == 'cell'})
    cells = {(r['resource'], r['zeit']): r['n'] for r in rows if r['kind'] == 'cell'}
    observed = {r['zeit']: r['observed_logs'] for r in rows if r['kind'] == 'time'}
    counts = [[cells.get((resource, t), 0) if observed.get(t) else None for t in times] for resource in resources]
    ticks = [0, 1, 10, 100, 1000, 10000, 100000]
    fig = go.Figure(go.Heatmap(x=times, y=resources, customdata=counts,
        z=[[log10(n+1) if n is not None else None for n in row] for row in counts],
        colorscale=[[0, '#17283E'], [1, CYAN]],
        colorbar=dict(title='Lines · log', tickvals=[log10(n+1) for n in ticks], ticktext=[str(n) for n in ticks]),
        hovertemplate='%{y}<br>%{x}<br>Matching lines %{customdata}<extra></extra>'))
    return finish(fig, 'Recorded time', 'Top observed resources', max(320, len(resources)*24))


def pareto(rows):
    ranked = sorted(rows, key=lambda r: r['n'], reverse=True)[:15]
    total = rows[0].get('logzeilen_passend_gesamt') if rows else None
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    labels = [f"{r['template_id']} · {r['team']}" for r in ranked]
    fig.add_trace(go.Bar(x=labels, y=[r['n'] for r in ranked], name='Log lines', marker_color=CYAN))
    if total:
        cumulative = pd.Series([r['n'] for r in ranked]).cumsum()*100/total
        fig.add_trace(go.Scatter(x=labels, y=cumulative, name='Cumulative % of all matching lines',
            mode='lines+markers', line_color=AMBER), secondary_y=True)
    fig.update_yaxes(title_text='Cumulative %', range=[0, 100], secondary_y=True)
    return finish(fig, 'Pattern · ownership team', 'Log lines', 440)


def pattern_comparison(series, metric='n', heatmap=False):
    labels = list(series)
    if heatmap:
        times = sorted({r['zeit'] for rows in series.values() for r in rows})
        values = [{r['zeit']: None if r.get('datenluecke') else r.get(metric) for r in rows} for rows in series.values()]
        fig = go.Figure(go.Heatmap(x=times, y=labels, z=[[v.get(t) for t in times] for v in values],
            colorscale=[[0, '#17283E'], [1, CYAN]], colorbar_title=LABELS[metric],
            hovertemplate='%{y}<br>%{x}<br>Count %{z}<extra></extra>'))
    else:
        fig = make_subplots(rows=max(1, len(labels)), cols=1, shared_xaxes=True, shared_yaxes=True, subplot_titles=labels)
        for index, rows in enumerate(series.values(), 1):
            rows = sorted(rows, key=lambda r: r['zeit'])
            fig.add_trace(go.Scatter(x=[r['zeit'] for r in rows],
                y=[None if r.get('datenluecke') else r.get(metric) for r in rows],
                mode='lines+markers', connectgaps=False, line_color=CYAN, showlegend=False), row=index, col=1)
    return finish(fig, 'Recorded time · blank means no observation', LABELS[metric], max(350, len(labels)*145))


def team_comparison(rows):
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, subplot_titles=['Frequency', 'Observed reach'])
    for column, field, color in [(1, 'haeufigkeit', CYAN), (2, 'reichweite', AMBER)]:
        fig.add_trace(go.Scatter(x=[r.get(field) for r in rows], y=[r['gruppe'] for r in rows],
            mode='markers', marker=dict(size=13, color=color), showlegend=False,
            hovertemplate='%{y}<br>%{x}<extra></extra>'), row=1, col=column)
    return finish(fig, height=max(330, len(rows)*35))


def period_bars(rows):
    fig = make_subplots(rows=1, cols=3, subplot_titles=['Matching log lines', 'Matches / 1,000 scoped lines', 'Observed calendar buckets (%)'])
    for column, field in enumerate(['n', 'lines_per_1000', 'coverage_pct'], 1):
        fig.add_trace(go.Bar(x=[r['period'] for r in rows], y=[r[field] for r in rows],
            marker_color=[CYAN, AMBER][:len(rows)], showlegend=False,
            hovertemplate='%{x}<br>%{y}<extra></extra>'), row=1, col=column)
    fig.update_yaxes(range=[0, 100], row=1, col=3)
    return finish(fig, height=370)


def notices(result):
    meta = result.get("meta", {})
    if meta.get("gekuerzt") or result.get('truncated'):
        st.warning(f"Showing a limited result: {result.get('zeilen', 0):,} rows. More results exist.")
    if meta.get("summary_gekuerzt"):
        st.caption("Pattern summary shows the top 10 groups. The matching-line count covers all groups.")
    if meta.get("requested_modus") != meta.get("modus"):
        st.caption("No exact phrase matched. Results use all search words instead.")
    for warning in result.get("warnings", []):
        st.warning(warning)
    if result.get('testdaten'):
        st.warning('Synthetic test evidence — not an investigation of real logs.')
    if result.get('modell_gekuerzt'):
        st.caption(f"The model received a shortened view ({result.get('modell_zeilen', '?')} primary rows). Full query evidence is retained below.")
    if result.get('scope_exception'):
        st.info(result['scope_exception'])
    if 'truncated' in result and result['truncated'] is None:
        st.caption('The tool did not establish whether the result is complete.')


def evidence_entries(result, name="Primary query"):
    yield name, result
    scope = result.get("meta", {}).get("bereich")
    if scope:
        yield "Full scope before severity / pattern filters", scope
    for item in result.get("belege", []):
        yield from evidence_entries(item, item.get("name", "Supporting query"))
    for item in result.get('zusatz_belege', []):
        yield from evidence_entries(item, item.get('zweck', 'Supporting query'))


def evidence_panel(records, key="evidence"):
    with st.expander(f"Query evidence · {len(records)} tool calls", icon=":material/data_object:"):
        if not records:
            st.caption("Run an investigation to collect inspectable evidence.")
            return
        for index, record in enumerate(records):
            reference = record['result'].get('beleg_id', f'{index + 1:02d}')
            st.markdown(f"**{reference} / {record['tool']}**")
            st.code(json.dumps(record.get("inputs", {}), default=str, indent=2), language="json")
            result = record["result"]
            notices(result)
            for name, item in evidence_entries(result):
                st.caption(name)
                st.code(item.get("sql", "No executed SQL supplied"), language="sql")
                st.dataframe(table(item.get("daten", [])), hide_index=True, alt=name + " query results")
                if item is not result:
                    notices(item)
            if result.get("meta"):
                st.json(json.loads(json.dumps(result["meta"], default=str)), expanded=False)
        st.download_button("Download investigation evidence", json.dumps(records, default=str, indent=2),
                           file_name="log-observatory-evidence.json", mime="application/json", key=key,
                           icon=":material/download:")


AGENT_STATUS = {
    'ok': 'Investigation completed',
    'konfiguration_fehlt': 'Add OPENAI_API_KEY to the local .env to connect the agent.',
    'api_fehler': 'Model request failed. Check the API key, account credit and connection. No automatic retry was made.',
    'budgetlimit': 'The local test budget is exhausted. The usage ledger has been preserved.',
    'tools_fehlen': 'Database tools are unavailable. Check the installed dependencies.',
    'ungueltige_eingabe': 'Invalid input. Use a question under 3,500 characters and a valid scope.',
    'kontextlimit': 'The investigation context is too large. Narrow the question or historical period.',
    'unvollstaendig': 'The model response was incomplete. Existing evidence remains available.',
    'abgelehnt': 'The model declined this request.',
    'belege_unzureichend': 'The agent could not produce an answer with valid evidence references.',
    'toollimit': 'The investigation reached its tool-call limit. Narrow the question.',
    'aufruflimit': 'The investigation reached its model-call limit without a final answer.',
}


def agent_message(response):
    """Normalize Person 4's raw evidence without dropping IDs, inputs or metadata."""
    if not isinstance(response, dict) or not isinstance(response.get('text'), str) or not isinstance(response.get('belege'), list):
        raise ValueError('Expected text and belege from agent.')
    evidence = []
    for item in response['belege']:
        if not isinstance(item, dict):
            raise ValueError('Evidence must be dictionaries.')
        record = item if 'result' in item else {
            'tool': item.get('tool', item.get('name', 'Agent tool')),
            'inputs': item.get('parameter', {}), 'result': item}
        if not isinstance(record.get('result'), dict) or not isinstance(record['result'].get('sql'), str) or not isinstance(record['result'].get('daten'), list):
            raise ValueError('Agent evidence must retain executed SQL and data.')
        evidence.append(record)
    meta = response.get('meta', {})
    if not isinstance(meta, dict):
        raise ValueError('Agent metadata must be a dictionary.')
    return {'role': 'assistant', 'content': response['text'], 'evidence': evidence, 'meta': meta}


def agent_status(meta):
    status = meta.get('status', 'ok')
    if status == 'ok':
        st.badge(AGENT_STATUS['ok'], color='green')
    else:
        st.warning(AGENT_STATUS.get(status, 'The investigation did not complete. Review its evidence and metadata.'))
    if meta.get('testdaten'):
        st.warning('Synthetic test run — not real log findings.')
    st.caption(f"Model: {meta.get('modell', 'unspecified')} · API calls: {meta.get('api_aufrufe', 0)} · Tool calls: {meta.get('tool_aufrufe', 0)} · Tokens: {meta.get('input_tokens', 0):,} in / {meta.get('output_tokens', 0):,} out · Estimated cost: ${meta.get('kosten_usd_geschaetzt', 0):.5f}")
    if meta.get('verbrauch_unbekannt'):
        st.warning('Final usage is unknown; the conservative cost reservation remains in the local ledger.')
    if meta.get('tool_fehler'):
        st.warning('Some tool calls failed. Their failures do not establish zero matching logs.')
