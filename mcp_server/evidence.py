"""Begrenzte Modellansicht und unveraenderte SQL-Belege im Prozessspeicher."""
from collections import OrderedDict
from hashlib import sha256
import json

PREVIEW_BYTES = 32 * 1024
RESOURCE_BYTES = 1024 * 1024
CACHE_BYTES = 8 * 1024 * 1024
CACHE_ITEMS = 24


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False, separators=(",", ":"))


class EvidenceStore:
    """Keine Dateien, Geheimnisse oder frei waehlbaren Ressourcenpfade lesen."""

    def __init__(self, max_items=CACHE_ITEMS, max_bytes=CACHE_BYTES):
        self.items = OrderedDict()
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.byte_count = 0

    def put(self, tool: str, arguments: dict, result: dict) -> tuple[str, str]:
        raw = encode({"tool": tool, "arguments": arguments, "result": result})
        size = len(raw.encode("utf-8"))
        if size > min(RESOURCE_BYTES, self.max_bytes):
            raise ValueError("Ergebnis zu gross; Filter oder Zeitfenster einschraenken.")
        key = sha256(raw.encode("utf-8")).hexdigest()
        uri = "evidence://" + key
        if uri not in self.items:
            while self.items and (len(self.items) >= self.max_items or self.byte_count + size > self.max_bytes):
                _, (old, _, _) = self.items.popitem(last=False)
                self.byte_count -= len(old.encode("utf-8"))
            self.items[uri] = (raw, tool, size)
            self.byte_count += size
        self.items.move_to_end(uri)
        return key, uri

    def get(self, uri: str) -> str:
        if uri not in self.items:
            raise ValueError("Beleg nicht in dieser Sitzung vorhanden oder aus dem Cache verdraengt. Tool erneut ausfuehren.")
        self.items.move_to_end(uri)
        return self.items[uri][0]


def preview(result: dict) -> tuple[dict, dict]:
    """Originalzaehlungen bleiben erhalten; Kuerzungen stehen separat je JSON-Pfad.

    Nicht aus zeilen oder einer sichtbaren Teilliste auf vollstaendige Verteilung
    schliessen. Die Resource bewahrt genau die erhaltenen Tool-Ergebnisse, nicht
    alle Logzeilen der Datenbank. SQL wird erst im letzten Rueckfall gekuerzt.
    """
    for row_limit, text_limit, sql_limit in ((50, 2000, None), (12, 1000, None), (3, 300, 4000), (0, 160, 500)):
        changes = []
        row_budget = [70]

        def visit(value, path="result", name=""):
            if isinstance(value, dict):
                return {key: visit(item, f"{path}.{key}", key) for key, item in value.items()}
            if isinstance(value, list):
                cap = min(row_limit, row_budget[0]) if name == "daten" else 20
                shown = value[:cap]
                if name == "daten":
                    row_budget[0] -= len(shown)
                if len(shown) < len(value):
                    changes.append({"path": path, "returned_items": len(value), "shown_items": len(shown)})
                return [visit(item, f"{path}[{i}]") for i, item in enumerate(shown)]
            if isinstance(value, str):
                limit = sql_limit if name == "sql" else text_limit
                if limit is not None and len(value) > limit:
                    changes.append({"path": path, "returned_chars": len(value), "shown_chars": limit})
                    return value[:limit] + " [MCP preview truncated; read evidence_uri]"
            return value

        compact = visit(result)
        view = {"truncated": bool(changes), "changes": changes,
                "counts": "zeilen and all SQL aggregates retain their original meaning; shown_items describes only this MCP preview.",
                "resource_scope": "Full tool response, including its own SQL limits/truncation; not an export of the entire database."}
        if len(encode({"result": compact, "view": view}).encode("utf-8")) <= PREVIEW_BYTES:
            return compact, view
    # Ungewoehnlich grosse Metadaten: ehrlich nur auf den gespeicherten Beleg verweisen.
    return {}, {"truncated": True, "reason": "Preview too large; read evidence_uri before answering."}
