"""Begrenzter OpenAI-Tool-Calling-Ablauf mit prüfbaren Belegen für Omars UI."""
import json
import os
from pathlib import Path
import re
from typing import Callable

from dotenv import dotenv_values
from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from agent.budget import Budget, BudgetLimit, MODELL
from agent.prompts import GEMEINSAM, ROLLEN, rollenname
from agent.toolkit import BY_NAME, Filter, lade_werkzeuge

ROOT = Path(__file__).resolve().parents[1]
MAX_REQUESTS = 4
MAX_TOOL_CALLS = 6
MAX_OUTPUT_TOKENS = 2400
MAX_INPUT_BYTES = 80000
MAX_TOOL_VIEW_BYTES = 16000


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)


class Agent:
    def __init__(self, client, handlers: dict[str, Callable], budget: Budget,
                 model: str = MODELL, testdaten: bool = False):
        self.client, self.budget, self.model = client, budget, model
        self.handlers = {name: fn for name, fn in handlers.items() if name in BY_NAME}
        self.testdaten = testdaten

    def antworte(self, rolle: str, team: str | None, frage: str, verlauf: list,
                 *, language: str = 'de', scope: dict | None = None) -> dict:
        belege, tool_errors = [], []
        meta = {"modell": self.model, "api_aufrufe": 0, "tool_aufrufe": 0,
                "input_tokens": 0, "output_tokens": 0, "kosten_usd_geschaetzt": 0.0,
                "testdaten": self.testdaten, "fehlende_tools": sorted(set(BY_NAME) - set(self.handlers)),
                "tool_fehler": tool_errors}

        def finish(text: str, status: str) -> dict:
            if self.testdaten:
                text = "TESTDATEN – keine Untersuchung echter Logs.\n\n" + text
            return {"text": text, "belege": belege, "meta": {**meta, "status": status}}

        try:
            role = rollenname(rolle)
            if language not in ('de', 'en'):
                raise ValueError('language must be de or en.')
            scope = Filter.model_validate(scope).model_dump() if scope is not None else None
            if not isinstance(frage, str) or not frage.strip() or len(frage) > 4000:
                raise ValueError("Bitte eine Frage mit höchstens 4000 Zeichen eingeben.")
            if team is not None and (not isinstance(team, str) or not 1 <= len(team) <= 120):
                raise ValueError("Ungültiger Teamname.")
            if not isinstance(verlauf, list):
                raise ValueError("Der Verlauf muss eine Liste sein.")
            history = []
            for message in verlauf[-6:]:
                if (not isinstance(message, dict) or message.get("role") not in ("user", "assistant")
                        or not isinstance(message.get("content"), str) or len(message["content"]) > 4000):
                    raise ValueError("Verlauf: nur kurze user/assistant-Textnachrichten sind erlaubt.")
                history.append({"role": message["role"], "content": message["content"]})
        except ValueError as exc:
            return finish(str(exc), "ungueltige_eingabe")

        if not self.handlers:
            return finish("Die Datenbank-Werkzeuge sind noch nicht angeschlossen. "
                          "Kirdars tools.engineer und Ghazals tools.analytics fehlen. "
                          "Es wurde keine KI-Anfrage ausgeführt.", "tools_fehlen")

        instructions = GEMEINSAM + "\n" + ROLLEN[role]
        if language == 'en':
            instructions = instructions.replace('Antworte auf Deutsch.', 'Answer in English.')
            instructions += '\nAnswer entirely in English, including headings: Question, Evidence, Possible explanation, Next check.'
        if scope is not None:
            instructions += '\nActive dashboard filters, enforced on filterable tools: ' + encode(scope)
            instructions += '\nget_context and vm_dauer may extend outside this scope. Explicitly disclose those exceptions.'
        instructions += "\nAusgewähltes Team (Daten): " + encode(team)
        instructions += "\nNicht verfügbare Werkzeuge: " + encode(meta["fehlende_tools"])
        if self.testdaten:
            instructions += "\nAlle Werkzeugergebnisse sind künstliche Testdaten. Sage dies in der Antwort."
        messages = history + [{"role": "user", "content": frage}]
        schemas = [BY_NAME[name].schema() for name in self.handlers]

        for round_index in range(MAX_REQUESTS):
            final_round = round_index == MAX_REQUESTS - 1
            round_instructions = instructions
            if final_round:
                round_instructions += "\nLetzte Runde: Formuliere jetzt die Antwort aus den vorhandenen Belegen. Benenne verbleibende Lücken."
            request = {"model": self.model, "instructions": round_instructions, "input": messages,
                       "tools": schemas, "tool_choice": "none" if final_round else "required" if round_index == 0 else "auto",
                       "parallel_tool_calls": False, "max_output_tokens": MAX_OUTPUT_TOKENS,
                       "reasoning": {"effort": "medium"}, "service_tier": "default", "store": False}
            payload_bytes = len(encode(request).encode("utf-8"))
            if payload_bytes > MAX_INPUT_BYTES:
                return finish("Der Untersuchungskontext ist zu groß. Bitte Frage oder Zeitraum eingrenzen. "
                              "Bereits erhobene Belege bleiben erhalten.", "kontextlimit")
            try:
                entry = self.budget.reserve(self.model, payload_bytes, MAX_OUTPUT_TOKENS)
                meta["api_aufrufe"] += 1
                response = self.client.responses.create(**request)
                amount = self.budget.settle(entry, self.model, response.usage)
                if amount is not None:
                    meta["kosten_usd_geschaetzt"] += amount
                    meta["input_tokens"] += response.usage.input_tokens
                    meta["output_tokens"] += response.usage.output_tokens
                else:
                    meta["verbrauch_unbekannt"] = True
            except BudgetLimit as exc:
                return finish(str(exc), "budgetlimit")
            except OpenAIError:
                # Keine rohe Fehlermeldung ausgeben: sie könnte Zugangsdaten enthalten.
                meta["verbrauch_unbekannt"] = True
                return finish("OpenAI-Anfrage fehlgeschlagen. Zugang, Guthaben oder Verbindung prüfen. "
                              "Keine automatische Wiederholung; eine Kostenreserve bleibt im Protokoll.", "api_fehler")

            if response.status != "completed":
                return finish("Die Modellantwort wurde nicht vollständig abgeschlossen. "
                              "Bitte die Untersuchung enger eingrenzen.", "unvollstaendig")
            if any(getattr(part, "type", "") == "refusal" for item in response.output
                   for part in (getattr(item, "content", None) or [])):
                return finish("Das Modell hat diese Anfrage abgelehnt.", "abgelehnt")

            calls = [item for item in response.output if item.type == "function_call"]
            messages.extend(item.model_dump(exclude_none=True) for item in response.output)
            if not calls:
                text = response.output_text.strip()
                refs = set(re.findall(r"\[(B\d+)\]", text))
                ids = {item["beleg_id"] for item in belege}
                if not belege or not refs or not refs <= ids:
                    return finish("Es liegt keine ausreichend belegte Antwort vor. "
                                  "Vorhandene Abfragen stehen im Belege-Panel; fehlende Werkzeuge "
                                  "oder Daten müssen ergänzt werden.", "belege_unzureichend")
                return finish(text, "ok")

            for call in calls:
                if meta["tool_aufrufe"] >= MAX_TOOL_CALLS:
                    return finish("Die Werkzeuggrenze wurde erreicht. Bitte die Frage eingrenzen. "
                                  "Vorhandene Belege bleiben erhalten.", "toollimit")
                meta["tool_aufrufe"] += 1
                result = self._execute(call.name, call.arguments, belege, team, scope)
                if "fehler" in result:
                    tool_errors.append({"tool": call.name, "fehler": result["fehler"]})
                messages.append({"type": "function_call_output", "call_id": call.call_id,
                                 "output": encode(result)})

        return finish("Die Grenze von vier Modellaufrufen wurde erreicht. "
                      "Es gibt noch keine abgeschlossene Antwort; vorhandene Belege bleiben erhalten.", "aufruflimit")

    def _execute(self, name: str, arguments: str, belege: list, team: str | None,
                 scope: dict | None = None) -> dict:
        if name not in self.handlers:
            return {"fehler": "Dieses Werkzeug ist nicht verfügbar."}
        try:
            args = BY_NAME[name].args.model_validate_json(arguments)
            values = args.model_dump()
            if "team" in values and values["team"] is None and team:
                values["team"] = team
            if scope is not None:
                values.update({key: value for key, value in scope.items() if key in values and value is not None})
                values = BY_NAME[name].args.model_validate(values).model_dump()
            raw = self.handlers[name](**values)
            if (not isinstance(raw, dict) or not isinstance(raw.get("sql"), str) or not raw["sql"].strip()
                    or not isinstance(raw.get("daten"), list)
                    or not all(isinstance(row, dict) for row in raw["daten"])
                    or type(raw.get("zeilen")) is not int or raw["zeilen"] != len(raw["daten"])
                    or (raw.get("truncated") is not None and type(raw["truncated"]) is not bool)):
                return {"fehler": "Ungültiges Werkzeugergebnis: sql, zeilen und daten müssen zusammenpassen."}
            serialized = encode(raw)
            if len(serialized.encode("utf-8")) > 200000:
                return {"fehler": "Werkzeugergebnis zu groß. Filter oder Trefferlimit enger setzen."}
            evidence = json.loads(serialized)
            evidence.update({"tool": name, "parameter": values, "beleg_id": f"B{len(belege) + 1}",
                             "testdaten": self.testdaten})
            if scope is not None and name in ('get_context', 'vm_dauer'):
                evidence['scope_exception'] = ('Context follows the selected event beyond dashboard filters.'
                    if name == 'get_context' else 'Spawn comparison uses the full OpenStack corpus.')
            if name == "top_patterns":
                evidence["zaehlebene"] = "Jede Zeile zählt ein einzelnes Template. Bei OpenStack nicht mit der vollständigen Problemgruppe verwechseln; dafür priority_ranking verwenden."
            elif name == "priority_ranking":
                evidence["zaehlebene"] = ("Vollständige Problemgruppen einschließlich aller Traceback-Zeilen. n zählt Logzeilen, ereignisse zählt Ereignisnäherungen."
                    if values["group_by"] == "template" else "Gruppierung je Team. n zählt Logzeilen, ereignisse zählt Ereignisnäherungen.")
            evidence.setdefault("truncated", evidence.get("meta", {}).get("gekuerzt"))
            if evidence["truncated"] is None:
                evidence["vollstaendigkeit"] = "Vom Werkzeug nicht angegeben; keine vollständige Treffermenge zugesichert."
            # Originale Belege bleiben im UI erhalten; Modell erhält eine begrenzte Ansicht.
            visible = json.loads(encode(evidence))
            # Lange Analytics-SQL darf nicht die eigentlichen Daten aus dem Kontext drängen.
            # Jede SQL bleibt im vollständigen UI-Beleg, einschließlich Bereichs-/Zusatzabfragen.
            shortened_fields = []
            def compact(value):
                if isinstance(value, dict):
                    result, shortened = {}, {}
                    for key, item in value.items():
                        if key == "sql":
                            result[key] = "Im vollständigen Beleg " + evidence["beleg_id"]
                        elif isinstance(item, list) and len(item) > 8 and all(isinstance(x, str) for x in item):
                            result[key] = item[:8]
                            shortened[key] = {"gesamt": len(item), "gezeigt": 8}
                        else:
                            result[key] = compact(item)
                    if shortened:
                        result["modell_gekuerzte_felder"] = shortened
                        shortened_fields.append(shortened)
                    return result
                if isinstance(value, list):
                    return [compact(item) for item in value]
                return value
            visible = compact(visible)
            if "zusatz_belege" in visible or "belege" in visible:
                for alias in ("muster_zusammenfassung", "requests_der_vm", "request_verlauf", "ausbruch_analyse"):
                    visible.pop(alias, None)
            tables = []
            def collect_tables(value):
                if isinstance(value, dict):
                    if isinstance(value.get("daten"), list):
                        tables.append((value, len(value["daten"])))
                        value["daten"] = value["daten"][:100 if name == "pattern_trend" else 30]
                    for child in value.values():
                        collect_tables(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_tables(child)
            collect_tables(visible)
            while len(encode(visible).encode("utf-8")) > MAX_TOOL_VIEW_BYTES - 500:
                candidates = [table for table, _ in tables if table["daten"]]
                if not candidates:
                    break
                largest = max(candidates, key=lambda table: len(encode(table["daten"])))
                largest["daten"].pop()
            if len(encode(visible).encode("utf-8")) > MAX_TOOL_VIEW_BYTES:
                return {"fehler": "Metadaten des Werkzeugergebnisses sind zu groß."}
            for table, original_count in tables:
                table["modell_zeilen"] = len(table["daten"])
                table["modell_gekuerzt"] = len(table["daten"]) != original_count
            evidence["modell_zeilen"] = visible["modell_zeilen"] = len(visible["daten"])
            evidence["modell_gekuerzt"] = visible["modell_gekuerzt"] = any(
                len(table["daten"]) != count for table, count in tables) or bool(shortened_fields)
            visible["hinweis_darstellung"] = "truncated betrifft die DB-Ergebnisgruppen; modell_gekuerzt kann auch nur gekürzte ID-Listen oder Zusatzdaten bedeuten. Ob Ranglisten-Zeilen fehlen, an zeilen und modell_zeilen prüfen."
            belege.append(evidence)
            return visible
        except (ValidationError, ValueError, TypeError):
            return {"fehler": "Ungültige Argumente oder Ergebnisdaten. Werkzeugbeschreibung und Datentypen prüfen."}
        except Exception:
            return {"fehler": "Werkzeug fehlgeschlagen. Datenbankverbindung und Implementierung prüfen; keine Trefferzahl ableitbar."}


def configuration_status() -> dict:
    """Readiness for the UI; no API call, key disclosure or usage-ledger mutation."""
    cfg = dotenv_values(ROOT / '.env')
    handlers, missing = lade_werkzeuge()
    return {'configured': bool(os.getenv('OPENAI_API_KEY') or cfg.get('OPENAI_API_KEY')) and bool(handlers),
            'key_configured': bool(os.getenv('OPENAI_API_KEY') or cfg.get('OPENAI_API_KEY')),
            'model': os.getenv('OPENAI_MODEL') or cfg.get('OPENAI_MODEL') or MODELL,
            'missing_tools': missing}


def antworte(rolle: str, team: str | None, frage: str, verlauf: list,
             *, language: str = 'de', scope: dict | None = None) -> dict:
    """UI-Einstieg. text/belege sind stabil; meta enthält Status und Verbrauch."""
    handlers, _ = lade_werkzeuge()
    cfg = dotenv_values(ROOT / ".env")
    key = os.getenv("OPENAI_API_KEY") or cfg.get("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL") or cfg.get("OPENAI_MODEL") or MODELL
    if not key:
        return {"text": "OPENAI_API_KEY fehlt in der lokalen .env.", "belege": [],
                "meta": {"status": "konfiguration_fehlt", "api_aufrufe": 0}}
    budget = Budget(ROOT / ".agent-usage.sqlite3")
    if not handlers:
        return Agent(None, handlers, budget, model).antworte(rolle, team, frage, verlauf, language=language, scope=scope)
    with OpenAI(api_key=key, timeout=30, max_retries=0) as client:
        return Agent(client, handlers, budget, model).antworte(rolle, team, frage, verlauf, language=language, scope=scope)
