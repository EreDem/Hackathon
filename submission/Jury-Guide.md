# Log Observatory — jury entry point

Log Observatory turns operational logs into an inspectable next action for an
Engineer, Team Lead and Manager. **SQL calculates; the model explains.** The
prototype uses the full public BGL and OpenStack corpus in local Docker SereneDB.

## Start here

1. [Run from a clean checkout](../README.md#jury-quick-start-windows--powershell).
2. [Read the completed three-role investigation](../docs/worked-investigation.md)
   and its [original agent answers, tool inputs, executed SQL and results](../docs/evidence/worked-investigation.json).
3. [Read the presentation PDF](Log-Observatory-Slides.pdf) separately from the video.
4. For MCP, follow the [local Claude connection and verification guide](../docs/MCP.md).

The final team-voiced video is a separate submission-form link. It is not the
presentation PDF, a recording script, or the synthetic-voice editing draft.

## Submission requirement map

| Requirement | Where to inspect it |
|---|---|
| Working prototype and tools selected by an agent | [Streamlit app](../app.py), [agent](../agent/agent.py), [tool schemas/dispatch](../agent/toolkit.py), [search](../tools/engineer.py), [analytics](../tools/analytics.py) |
| Clean installation, dependencies, database loading, agent start | [README quick-start](../README.md#jury-quick-start-windows--powershell), [full requirements](../requirements.txt), [agent requirements](../requirements-agent.txt) |
| Own schema, parser, SQL loader and fictional ownership | [parser](../ingest/prepare.py), [load SQL](../ingest/load.sql), [ownership CSV](../ingest/ownership.csv), [ownership explanation](../README.md#fictional-team-ownership) |
| Both BGL and OpenStack used | [Executed full-corpus counts and three-role case](../docs/worked-investigation.md#shared-corpus-and-scope): 4,747,963 BGL + 207,820 OpenStack rows |
| Full-text search, historical filters and nearby-event context | Engineer and Manager sections of the [worked investigation](../docs/worked-investigation.md); Engineer VM context follows its lifecycle/request; the current demo additionally investigates a cache-manager traceback |
| Grouped counts and historical trend | Team Lead `top_patterns` and weekly `pattern_trend` calls in the [worked investigation](../docs/worked-investigation.md#team-lead) |
| Aggregation over the whole base corpus, not retrieved examples | Independent `COUNT(*)` by dataset in the worked case, plus full-match search statistics and SQL rankings; tool `LIMIT` affects displayed examples/groups, not the aggregate's input population |
| Three role questions, calls, SQL, results, answers and next actions | [Worked investigation](../docs/worked-investigation.md), with [machine-readable original evidence](../docs/evidence/worked-investigation.json) |
| Scope, dates, filters, truncation and facts versus hypotheses | Stated per investigation and evidence object; [known limitations](../README.md#known-limitations-for-judging) |
| Slides: approach, diagram, tool design, three-role findings, SQL, recommendations and limits | [10-page PDF](Log-Observatory-Slides.pdf): approach/diagram on 1–2, role findings on 3–5, MCP on 6, pilot/limits on 7–8, tools/SQL on 9–10 |
| Video: at most five minutes, real workflow and all three roles' agent evidence | Current app-only cut is about 3:08; [narration and chapter map](Video-Narration-English.md). The final team recording/link remains a separate deliverable |
| Optional MCP connection, real data volume and observed query times | [MCP guide](../docs/MCP.md), [final seven-tool protocol report](evidence/mcp-final-check.json); Claude recording is still pending |

## How the current demo relates to the written investigation

The written case and the video demonstrate the same system with two Engineer
examples. They do not claim to be the same model run.

| Role | Current video / slides | Supporting material |
|---|---|---|
| Engineer | OpenStack cache manager: eight matching failure headers. The inspected traceback contains `InvalidDiskInfo` and `No such file or directory`. Inspect the disk path and lifecycle/storage activity; the underlying cause and other seven reports still require checking | [Actual cache-manager agent run](evidence/presentation-evidence.json), under `cache_manager_live_run`; logs 4793594 and 4793598. The written worked case separately demonstrates an INFO-only slow VM spawn, with baseline and request context |
| Team Lead | HPC Kernel/BGL: TLB 152,734 lines on 541 observed nodes; storage interrupts 63,491 on 22,529. A weekly TLB bucket contains 152,182 lines | [Top-pattern and trend evidence](../docs/evidence/worked-investigation.json), [slide trend evidence](evidence/presentation-evidence.json) |
| Manager | BGL: storage interrupts rank first in the node-reach comparison. Frequency alone would overemphasize the TLB burst; factor values remain inspectable | [Ranking and full-match counts](../docs/evidence/worked-investigation.json), [executed comparison SQL](evidence/bgl-pattern-comparison.sql) |

The comparison above uses **ERROR/FATAL** BGL rows. An all-severity storage
search also includes two INFO rows and therefore returns 63,493 instead of
63,491. This is a scope difference, not an interchangeable total.

## Local execution and verification

The later technical guidance supersedes the original brief's references to a
provided instance/loader: the team supplies its schema, loader and ownership map,
and SereneDB runs locally. Raw logs and generated Parquet files are downloaded/
prepared during setup, rather than committed. The full workflow needs Python
3.12, Docker Desktop, packages and data downloads; see the README for commands.

Direct database exploration does not need a model key. Live web-agent answers
require the judge's own authorized OpenAI API key/model access and incur usage.
There is no shared jury secret or hosted application. The local MCP server
needs only the configured read-only database login; Claude supplies its own model.

The [clean-checkout rehearsal](../docs/clean-checkout-rehearsal.md) documents
an actual independent install/load/reload and three-role UI test, with package
versions and limits of that historical verification. The final submission check
is recorded in [submission verification](evidence/submission-verification.json).
This check does not call the model or replace the previously recorded live runs.

## Interpretation limits and next step

- Ownership is fictional; logs and their timestamps are historical.
- Log lines and heuristic `(pid, ts)` events are not independently confirmed incidents.
- Observed node/VM/request reach is not customer impact, outage duration or money.
- Search/context results and model previews can be shortened; original SQL and
  completeness metadata remain available. Full-match totals come from SQL.
- Priority scores are heuristics within dataset/reach-unit groups, not a global
  ranking of all datasets or measured financial damage.
- The proposed next step is a supervised customer pilot measuring investigation
  time, answer accuracy and cost. Customer savings have not yet been measured.

**MCP award status:** protocol interoperability and real database calls are
recorded. An actual Claude recording/transcript showing its connection and
chosen tools is still pending. The web-agent demo does not establish that step.
