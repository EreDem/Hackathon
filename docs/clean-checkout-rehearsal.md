# Clean-checkout rehearsal

**Result: passed.** This is an executed rehearsal, not a proposed checklist.

Started 2026-10-17T16:02:30.733448+00:00; finished 2026-10-17T16:20:20.586726+00:00.

A fresh local Git clone of `c3ec867541cf69a16c00dd1758b7e7c0af515ce1` received the candidate source changes. It began without `.env`, `.venv`, raw datasets, Parquet output, a model key or a usage ledger. The machine-readable report records SHA-256 hashes of the candidate source files actually tested, including the graph and setup fixes.

[Machine-readable run report](evidence/clean-checkout-rehearsal.json) · [Resolved package versions](evidence/rehearsal-packages.txt)

## What ran

| Step | Result | Seconds |
|---|---|---:|
| Fresh Python 3.12 virtual environment | PASS | 19.98 |
| Upgrade pip | PASS | 17.18 |
| Install all declared requirements | PASS | 275.92 |
| Check dependency consistency | PASS | 3.75 |
| Prepare full BGL and OpenStack corpus from raw logs | PASS | 455.52 |
| Start isolated disposable SereneDB | PASS | 1.27 |
| Load full corpus and full-text index | PASS | 12.19 |
| Reload full corpus into recreated disposable database | PASS | 12.34 |
| Create read-only app login with individual table grants | PASS | 0.83 |
| Final regression suite with real SQL fixtures | PASS | 34.48 |
| Full-corpus analytics acceptance | PASS | 6.07 |
| Three-role real-data Streamlit acceptance without model key | PASS | 19.06 |
| Verify missing model key, exact corpus counts and read-only privileges | PASS | 3.51 |

The final regression run passed **87 tests** with real SQL fixtures enabled. All **13 full-corpus analytics assertions** passed. The real-data Streamlit AppTest completed Engineer, Team Lead and Manager investigations, including the new visualization controls, without a model key.

The documented `python -m streamlit run app.py` entry point also started in the new environment, bound to localhost, and returned HTTP 200 / `ok` from its health endpoint.

## Data and isolation

- The original official Zenodo ZIP/tar archives were reused as a download cache, extracted afresh and hashed in the report. The run did not re-download those archives over the network.
- The full parser/Drain3 pipeline generated new Parquet files from raw BGL and OpenStack logs. No production Parquet or database files were copied. The setup retry reused only these newly generated rehearsal files.
- The isolated database loaded **4,747,963 BGL + 207,820 OpenStack = 4,955,783 lines**, with 399/71 templates, zero unparsed lines and complete, unique ownership mapping.
- A temporary SereneDB container listened only on `127.0.0.1:7891`; the existing project instance on port 7890 was untouched.
- The setup helper created a password-protected `log_observatory` login. An actual query confirmed SELECT access and denied INSERT access. Its generated credentials stayed in the ignored rehearsal `.env` and were not printed.
- No model API calls were made in this rehearsal. The separate worked investigation records real model-assisted answers using public challenge logs.
- The temporary database/container and test Streamlit server were removed after verification. The source clone remains under ignored `out/clean-checkout` for local inspection; no test credentials belong in the submission.

## Issue found and fixed during the rehearsal

The initial login helper tried `GRANT SELECT ON logs, templates, ownership ...`. SereneDB rejected the comma-separated table list. The helper now sends one GRANT per table, matching the documented individual-object syntax. A newly recreated isolated database then passed login setup and all subsequent acceptance checks. A regression assertion prevents reintroducing the unsupported combined statement.

## Reproduce

Follow the README jury quick-start in a new checkout with Python 3.12 and Docker Desktop. Run the loader only against a fresh challenge database: it recreates the three tables. Create the read-only login after loading, then run the regression, analytics and UI commands shown there. The later technical guidance provides no shared instance or loader; use the repository's local Docker and ingestion workflow.

## Limits of this result

- Environment tested: Windows / PowerShell, Python 3.12.14, Streamlit 1.66.0 and Plotly 7.1.0. Other operating systems were not rehearsed.
- This tested candidate source changes applied to a clean clone; the recorded base commit alone predates these changes. Source hashes identify the tested code.
- Package downloads may use pip cache; raw-data archives used the verified local download cache. A new machine still needs registry/Zenodo connectivity.
- Requirements and the Docker tag are not fully locked. The report records resolved package versions and the exact local image ID; future upgrades may need another rehearsal.
- Browser charts were checked separately at desktop and 420px chart widths. This is not a physical-mobile-device or cross-browser certification.

No credentials, `.env`, data archives, generated Parquet files or usage ledgers are included in the public evidence report.
