"""Geprüfte Anschlüsse zu den Python-Werkzeugen von Person 2 und 3.

Hier werden keine SQL-Abfragen oder produktiven Testdaten implementiert.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Zeitraum(Args):
    von: str | None = Field(default=None, max_length=40, description="Historischer ISO-Zeitpunkt oder null.")
    bis: str | None = Field(default=None, max_length=40, description="Historischer ISO-Zeitpunkt oder null.")

    @model_validator(mode="after")
    def pruefe_zeitraum(self):
        def utc(value):
            if not value:
                return None
            stamp = datetime.fromisoformat(value)
            return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
        start, end = utc(self.von), utc(self.bis)
        if start and end and start > end:
            raise ValueError("von liegt nach bis")
        return self


class Filter(Zeitraum):
    dataset: Literal["BGL", "OpenStack"] | None = None
    team: str | None = Field(default=None, min_length=1, max_length=120)


class SearchArgs(Filter):
    query: str = Field(min_length=1, max_length=500)
    level: list[Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]] | None = Field(default=None, max_length=5)
    limit: int = Field(default=20, ge=1, le=50)
    modus: Literal["phrase", "all", "any"] = "phrase"


class ContextArgs(Args):
    log_id: int | str = Field(description="Positive Log-ID oder genaue VM-UUID bzw. req-UUID.")
    fenster_sek: int = Field(default=600, ge=1, le=3600)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def pruefe_id(self):
        import re
        if isinstance(self.log_id, int) and self.log_id > 0:
            return self
        if isinstance(self.log_id, str) and re.fullmatch(r"(?:req-)?[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", self.log_id):
            return self
        raise ValueError("Log-ID, VM-UUID oder Request-ID erforderlich")


class VMArgs(Args):
    instance_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
    limit: int = Field(default=5, ge=1, le=20)


class PatternsArgs(Filter):
    limit: int = Field(default=10, ge=1, le=30)


class TrendArgs(Filter):
    template_id: str | None = Field(default=None, pattern=r"^(BGL|OS)-\d+$")
    team: str | None = Field(default=None, min_length=1, max_length=120)
    intervall: Literal["1 hour", "1 day", "1 week"] = "1 day"


class RankingArgs(Filter):
    group_by: Literal["template", "team"] = "template"
    limit: int = Field(default=20, ge=1, le=100)


@dataclass(frozen=True)
class Tool:
    name: str
    module: str
    args: type[Args]
    description: str

    def schema(self) -> dict:
        schema = self.args.model_json_schema()
        # Responses strict mode verlangt alle Felder; optionale Werte sind null.
        schema["required"] = list(schema["properties"])
        for field in schema["properties"].values():
            field.pop("default", None)
        return {"type": "function", "name": self.name, "description": self.description,
                "parameters": schema, "strict": True}


TOOLS = (
    Tool("search_logs", "tools.engineer", SearchArgs,
         "Volltextsuche mit optionalen Filtern. Liefert begrenzte Logtreffer mit IDs, ausgeführte SQL und bei erfolgreicher Zusatzstatistik gesamt_treffer über alle passenden Logzeilen; keine Incident-Zahl."),
    Tool("get_context", "tools.engineer", ContextArgs,
         "Kontext zu einer zuvor gefundenen Log-ID: benachbarte Ereignisse, Request/VM oder BGL-Knoten/Midplane. "
         "Bei OpenStack inklusive aller Zeilen desselben Ereignisses (pid, ts), z. B. eines mehrzeiligen Tracebacks. Liefert Logzeilen und SQL."),
    Tool("vm_dauer", "tools.engineer", VMArgs,
         "Spawn-Dauer einer OpenStack-VM und Vergleichswerte aus SQL; auch INFO-Logs können auffällig sein."),
    Tool("top_patterns", "tools.analytics", PatternsArgs,
         "Aggregierte wiederkehrende Muster nach Team/Datensatz/Zeitraum. Liefert gezählte Zeilen bzw. Ereignisse, Reichweite und SQL."),
    Tool("pattern_trend", "tools.analytics", TrendArgs,
         "Zeitreihe eines Templates oder Teams im gewählten Intervall. Liefert berechnete Zeitpunkte, Werte und SQL; nutze den tatsächlichen Zeitraum des Ergebnisses."),
    Tool("priority_ranking", "tools.analytics", RankingArgs,
         "SQL-Priorisierung nach Team oder Template im Zeitraum. Liefert Rangliste mit einzelnen Score-Faktoren und SQL; keine finanziellen Schäden."),
)
BY_NAME = {tool.name: tool for tool in TOOLS}


def lade_werkzeuge() -> tuple[dict[str, Callable], list[str]]:
    handlers, fehlend = {}, []
    for spec in TOOLS:
        try:
            handler = getattr(import_module(spec.module), spec.name)
            if not callable(handler):
                raise AttributeError(spec.name)
            handlers[spec.name] = handler
        except (ImportError, AttributeError):
            fehlend.append(spec.name)
    return handlers, fehlend
