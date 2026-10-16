"""
prepare.py – bereitet die rohen BGL- und OpenStack-Logs für SereneDB vor.

Was passiert:
  1. Rohdateien werden ZEILENWEISE gelesen (Streaming, auch 700 MB passen so problemlos)
  2. Jede Zeile wird je nach Datensatz in Felder zerlegt (BGL bzw. OpenStack)
  3. Drain3 ordnet jeder Nachricht ein Template zu (ein Drain pro Datensatz)
  4. Ergebnis wird in Blöcken als Parquet geschrieben:
        out/logs.parquet        eine Zeile pro Log-Eintrag
        out/templates.parquet   eine Zeile pro Template (mit Statistik)
        out/templates.csv       dasselbe zum Anschauen
        out/components.csv      alle Komponenten mit Anzahl (Grundlage für die Ownership-Tabelle)
  5. Danach lädt load.sql alles per read_parquet in SereneDB – kein Python-INSERT nötig.

Benutzung:
    python ingest/prepare.py data/BGL.log "data/openstack_*.log"     (aus dem Repo-Hauptordner)
    python ingest/prepare.py data/BGL.log --limit 200000        # schneller Testlauf
    Optionen: --out out/  --sim-bgl 0.4  --sim-openstack 0.9  --limit N

Installation:
    pip install pyarrow drain3
    (Python 3.13: vorher  pip install "setuptools==69.*" wheel  und dann
     pip install --no-build-isolation drain3  – oder Python 3.11/3.12 nehmen)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

# ---------------------------------------------------------------------------
# 1. Level-Normalisierung (Original bleibt in level_raw erhalten)
# ---------------------------------------------------------------------------

LEVEL_MAP = {
    "DEBUG": "DEBUG", "TRACE": "DEBUG",
    "INFO": "INFO",
    "WARN": "WARN", "WARNING": "WARN",
    "ERROR": "ERROR", "SEVERE": "ERROR",
    "FATAL": "FATAL", "FAILURE": "FATAL", "CRITICAL": "FATAL",
}
LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}


# ---------------------------------------------------------------------------
# 2. Parser je Datensatz
#    Jeder Parser gibt ein dict mit den Spalten der Tabelle `logs` zurück
#    oder None, wenn die Zeile nicht passt.
# ---------------------------------------------------------------------------

def parse_bgl(line: str) -> dict | None:
    """
    BGL (Blue Gene/L Supercomputer), Beispiel:
    - 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
    Felder: Label, Unix-Zeit, Datum, Node, Zeit, Node, Typ, Komponente, Level, Nachricht
    Label '-' = normal, sonst Alert-Kategorie (z. B. KERNDTLB, APPREAD) = echte Störung laut Datensatz
    """
    parts = line.split(maxsplit=9)
    if len(parts) < 9:
        return None
    label, unix_ts, _date, node, ts_text, _node2, typ, component, level = parts[:9]
    message = parts[9] if len(parts) > 9 else ""
    try:
        ts = datetime.strptime(ts_text, "%Y-%m-%d-%H.%M.%S.%f").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            ts = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)
        except ValueError:
            return None
    return {
        "ts": ts,
        "level_raw": level,
        "level": LEVEL_MAP.get(level.upper(), "INFO"),
        "component": component,
        "service": typ,              # RAS / NULL – Ereignistyp
        "node": node,
        "pid": None,
        "request_id": None,
        "instance_id": None,
        "alert": None if label == "-" else label,
        "message": message,
    }


OPENSTACK_RE = re.compile(
    r"^(?P<logrecord>\S+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<pid>\d+)\s+(?P<level>[A-Z]+)\s+(?P<component>\S+)\s*"
    r"(?:\[(?P<addr>[^\]]*)\]\s*)?(?P<content>.*)$"
)
REQ_RE = re.compile(r"req-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
INSTANCE_RE = re.compile(r"\[instance: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]")


def parse_openstack(line: str) -> dict | None:
    """
    OpenStack (Nova), Beispiel:
    nova-api.log.1.2017-05-16_13:53:08 2017-05-16 00:00:00.008 25746 INFO nova.osapi_compute.wsgi.server
        [req-3810... 113d... 54fa... - - -] 10.11.10.1 "GET /v2/.../servers/detail HTTP/1.1" status: 200 len: 1893 time: 0.2477829
    """
    m = OPENSTACK_RE.match(line)
    if not m:
        return None
    g = m.groupdict()
    ts = datetime.fromisoformat(f"{g['date']} {g['time']}").replace(tzinfo=timezone.utc)
    addr = g["addr"] or ""
    content = g["content"]
    req = REQ_RE.search(addr)
    inst = INSTANCE_RE.search(content)
    return {
        "ts": ts,
        "level_raw": g["level"],
        "level": LEVEL_MAP.get(g["level"].upper(), "INFO"),
        "component": g["component"],
        "service": g["logrecord"].split(".log")[0],   # nova-api / nova-compute / nova-scheduler
        "node": None,
        "pid": int(g["pid"]),
        "request_id": req.group(0) if req else None,   # verbindet Zeilen desselben Requests
        "instance_id": inst.group(1) if inst else None,  # verbindet Zeilen derselben VM
        "alert": None,
        "message": content,
    }


PARSERS = {"BGL": parse_bgl, "OpenStack": parse_openstack}


def detect_dataset(path: Path) -> str:
    """Erkennt den Datensatz an der ersten nicht-leeren Zeile."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                if OPENSTACK_RE.match(line.strip()):
                    return "OpenStack"
                if parse_bgl(line.strip()):
                    return "BGL"
                break
    sys.exit(f"Format von {path} nicht erkannt – bitte Parser ergänzen.")


# ---------------------------------------------------------------------------
# 3. Drain3 – Masking-Regeln (spezifisch -> allgemein)
# ---------------------------------------------------------------------------

MASKS: list[tuple[str, str]] = [
    (r"req-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "REQ"),
    (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "UUID"),
    (r"\bR\d{2}-M\d(?:-[A-Z0-9]+)*(?:-[A-Z]:J\d{2}-U\d{2}|-[A-Z]:J\d{2})?", "NODE"),     # BGL-Knoten
    (r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?(?![\d.])", "IP"),
    (r"\b0x[0-9a-fA-F]+\b", "HEX"),
    (r"\b(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{16,}\b", "ID"),                               # Hashes, lange IDs
    (r"(?<![\w/])/(?:[\w.\-]+/)+[\w.\-]*", "PATH"),
    (r"(?<![A-Za-z_])-?\d+(?:\.\d+)?(?:ms|s|kb|mb|gb|%)?(?![A-Za-z_])", "NUM"),
]


def build_miner(sim_th: float) -> TemplateMiner:
    cfg = TemplateMinerConfig()
    cfg.drain_sim_th = sim_th
    cfg.drain_depth = 4
    cfg.drain_max_children = 100
    cfg.parametrize_numeric_tokens = True
    cfg.masking_instructions = [MaskingInstruction(p, n) for p, n in MASKS]
    cfg.snapshot_interval_minutes = 0
    return TemplateMiner(config=cfg)


@dataclass
class TemplateStats:
    count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    max_level: str = "DEBUG"
    alerts: int = 0
    components: Counter = field(default_factory=Counter)
    example_log_id: int | None = None


# ---------------------------------------------------------------------------
# 4. Parquet-Schema = Tabelle `logs`
# ---------------------------------------------------------------------------

LOG_SCHEMA = pa.schema([
    ("id", pa.int64()),
    ("dataset", pa.string()),
    ("ts", pa.timestamp("us", tz="UTC")),
    ("level", pa.string()),
    ("level_raw", pa.string()),
    ("component", pa.string()),
    ("service", pa.string()),
    ("node", pa.string()),
    ("pid", pa.int64()),
    ("request_id", pa.string()),
    ("instance_id", pa.string()),
    ("alert", pa.string()),
    ("message", pa.string()),
    ("template_id", pa.string()),
    ("source_file", pa.string()),
    ("parsed", pa.bool_()),
])

BATCH = 100_000


# ---------------------------------------------------------------------------
# 5. Hauptablauf
# ---------------------------------------------------------------------------

def run(files: list[Path], out: Path, sims: dict[str, float], limit: int | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(out / "logs.parquet", LOG_SCHEMA, compression="zstd")
    miners: dict[str, TemplateMiner] = {}
    stats: dict[str, TemplateStats] = defaultdict(TemplateStats)
    report: dict[str, Counter] = defaultdict(Counter)
    curves: dict[str, list[tuple[int, int]]] = defaultdict(list)
    components: Counter = Counter()

    buf: dict[str, list] = {name: [] for name in LOG_SCHEMA.names}
    next_id = 1
    t0 = time.time()

    def flush() -> None:
        if buf["id"]:
            writer.write_table(pa.table(buf, schema=LOG_SCHEMA))
            for v in buf.values():
                v.clear()

    for path in files:
        ds = detect_dataset(path)
        parse = PARSERS[ds]
        miner = miners.setdefault(ds, build_miner(sims[ds]))
        prefix = "BGL" if ds == "BGL" else "OS"
        print(f"\n> {path.name}  ({ds})")

        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line.strip():
                    continue
                if limit and report[ds]["entries"] >= limit:
                    break
                rep = report[ds]
                rep["entries"] += 1

                row = parse(line)
                if row is None:
                    rep["unparsed"] += 1
                    row = {"ts": None, "level_raw": None, "level": "INFO", "component": None,
                           "service": None, "node": None, "pid": None, "request_id": None,
                           "instance_id": None, "alert": None, "message": line}
                    parsed = False
                else:
                    parsed = True

                # Drain bekommt nur die Nachricht (erste Zeile) – IDs bleiben stabil
                text = row["message"].split("\n", 1)[0].strip()
                text = INSTANCE_RE.sub("", text).strip() or "<EMPTY>"   # VM-ID steht schon in instance_id
                cid = miner.add_log_message(text)["cluster_id"]
                tid = f"{prefix}-{cid:04d}"

                # Statistik pro Template (laufend, kein zweites Einlesen nötig)
                s = stats[tid]
                s.count += 1
                if s.example_log_id is None:
                    s.example_log_id = next_id
                ts = row["ts"]
                if ts:
                    if s.first_seen is None or ts < s.first_seen:
                        s.first_seen = ts
                    if s.last_seen is None or ts > s.last_seen:
                        s.last_seen = ts
                if LEVEL_RANK[row["level"]] > LEVEL_RANK[s.max_level]:
                    s.max_level = row["level"]
                if row["alert"]:
                    s.alerts += 1
                    rep["alerts"] += 1
                if row["component"]:
                    s.components[row["component"]] += 1
                    components[(ds, row["component"])] += 1
                rep[f"level_{row['level']}"] += 1

                for k, v in row.items():
                    buf[k].append(v)
                buf["id"].append(next_id)
                buf["dataset"].append(ds)
                buf["template_id"].append(tid)
                buf["source_file"].append(path.name)
                buf["parsed"].append(parsed)
                next_id += 1

                if rep["entries"] % 50_000 == 0:
                    curves[ds].append((rep["entries"], len(miner.drain.clusters)))
                if len(buf["id"]) >= BATCH:
                    flush()
                    rate = (next_id - 1) / (time.time() - t0)
                    print(f"  {next_id - 1:>10,} Zeilen  | {rate:,.0f} Zeilen/s  | "
                          f"{len(miner.drain.clusters)} Templates ({ds})", flush=True)
        curves[ds].append((report[ds]["entries"], len(miner.drain.clusters)))

    flush()
    writer.close()

    # --- Templates mit FINALEM Text schreiben ------------------------------------
    rows = []
    for ds, miner in miners.items():
        prefix = "BGL" if ds == "BGL" else "OS"
        for c in miner.drain.clusters:
            tid = f"{prefix}-{c.cluster_id:04d}"
            s = stats[tid]
            rows.append({
                "template_id": tid, "dataset": ds, "template": c.get_template(),
                "count": s.count, "first_seen": s.first_seen, "last_seen": s.last_seen,
                "max_level": s.max_level, "alerts": s.alerts,
                "main_component": s.components.most_common(1)[0][0] if s.components else None,
                "example_log_id": s.example_log_id,
            })
    rows.sort(key=lambda r: (r["dataset"], -r["count"]))
    tpl_schema = pa.schema([
        ("template_id", pa.string()), ("dataset", pa.string()), ("template", pa.string()),
        ("count", pa.int64()), ("first_seen", pa.timestamp("us", tz="UTC")),
        ("last_seen", pa.timestamp("us", tz="UTC")), ("max_level", pa.string()),
        ("alerts", pa.int64()), ("main_component", pa.string()), ("example_log_id", pa.int64()),
    ])
    pq.write_table(pa.Table.from_pylist(rows, schema=tpl_schema), out / "templates.parquet")
    with (out / "templates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=tpl_schema.names)
        w.writeheader()
        w.writerows(rows)
    with (out / "components.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "component", "count"])
        for (ds, comp), n in components.most_common():
            w.writerow([ds, comp, n])

    print_report(report, rows, curves, time.time() - t0, out)


# ---------------------------------------------------------------------------
# 6. Qualitätsbericht
# ---------------------------------------------------------------------------

def print_report(report, rows, curves, secs, out: Path) -> None:
    print("\n" + "=" * 70)
    print(f"BERICHT  ({secs:,.0f} s)")
    print("=" * 70)
    for ds, rep in report.items():
        n = rep["entries"]
        tpls = [r for r in rows if r["dataset"] == ds]
        top10 = sum(r["count"] for r in tpls[:10])
        levels = {k[6:]: v for k, v in rep.items() if k.startswith("level_")}
        print(f"\n[{ds}]  Einträge: {n:,}   nicht erkannt: {rep['unparsed']:,} ({rep['unparsed'] / max(n, 1):.2%})")
        print(f"  Level: {levels}")
        if ds == "BGL":
            print(f"  Alert-Zeilen (Label != '-'): {rep['alerts']:,}")
        print(f"  Templates: {len(tpls)}   davon ERROR/FATAL: "
              f"{sum(1 for r in tpls if LEVEL_RANK[r['max_level']] >= 3)}   "
              f"Top 10 decken {top10 / max(n, 1):.0%} ab")
        print("  Sättigung: " + "  ".join(f"{a:,}:{b}" for a, b in curves[ds][-8:]))
        print(f"  {'ID':<9} {'Anzahl':>9} {'Level':<6} Template")
        for r in tpls[:12]:
            print(f"  {r['template_id']:<9} {r['count']:>9,} {r['max_level']:<6} {r['template'][:80]}")
    print(f"\nGeschrieben nach {out}/: logs.parquet, templates.parquet, templates.csv, components.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="BGL/OpenStack -> Parquet + Drain3-Templates")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out"))
    # Getestet gegen die Loghub-Referenz-Templates (je 2.000 Zeilen):
    #   BGL 0.4 -> 97 % korrekt gruppiert. OpenStack braucht 0.9, sonst verschmelzen
    #   kurze Meldungen wie "VM Paused" / "VM Resumed" oder GET / POST.
    ap.add_argument("--sim-bgl", type=float, default=0.4, help="Drain-Schwelle für BGL")
    ap.add_argument("--sim-openstack", type=float, default=0.9, help="Drain-Schwelle für OpenStack")
    ap.add_argument("--limit", type=int, help="max. Zeilen pro Datensatz (für Testläufe)")
    a = ap.parse_args()
    # Platzhalter selbst auflösen (PowerShell/cmd machen das nicht): "data/openstack_*.log"
    files = []
    for f in a.files:
        matches = sorted(Path().glob(str(f))) if any(ch in str(f) for ch in "*?[") else [f]
        if not matches:
            sys.exit(f"Keine Datei gefunden für {f}")
        files.extend(matches)
    run(files, a.out, {"BGL": a.sim_bgl, "OpenStack": a.sim_openstack}, a.limit)
