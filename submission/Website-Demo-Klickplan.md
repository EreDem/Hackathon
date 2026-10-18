# Website-Demo: Klicks und passender Sprechtext

Eine Person liest Englisch vor. Eine zweite Person bedient die App. Alternativ nehmt ihr drei echte App-Clips auf und sprecht den Text anschließend darüber. Zielzeit des gesamten Videos: etwa 4:30 Minuten.

## 0. Vor der Aufnahme

1. Eure bereits geöffnete Log-Observatory-App verwenden. Bei Bedarf laut README starten.
2. **Database connected** und **Agent connected** prüfen. **Reconnect / refresh data** nur vor einem Durchlauf verwenden: Es setzt die Ansicht zurück.
3. In der Seitenleiste **Your perspective**, **Dataset** und **Ownership team** wählen. Den vollständigen voreingestellten historischen Zeitraum behalten. Danach **Apply scope**.
4. Diagramme zuerst vorbereiten. Danach erst die Frage unten im Bereich **Ask the investigator** in das Eingabefeld **Ask about the logs in the active scope…** kopieren und absenden.
5. Für diese Demo **nicht Ask the prepared question verwenden**: Die Engineer-Standardfrage untersucht eine VM statt des Cache Managers. **Run prepared investigation setzt den bisherigen Chat zurück.** Die unten genannten Fach-Buttons verwenden oder vorbereitete Untersuchungen vor dem Chat ausführen.

## Übersicht im fertigen Video

| Zeit | Bild | Text aus dem vorhandenen Skript |
|---|---|---|
| 00:00-00:25 | Folie 1 | Einleitung |
| 00:25-00:50 | Folie 2 | Systemaufbau |
| 00:50-01:45 | Kurz Folie 3, dann Engineer in der App | Engineer-Text unten |
| 01:45-02:35 | Kurz Folie 4, dann Team Lead in der App | Team-Lead-Text unten |
| 02:35-03:25 | Kurz Folie 5, dann Manager in der App | Manager-Text unten |
| 03:25-03:45 | Folie 6, optional echte Claude-Aufnahme | MCP |
| 03:45-04:10 | Folie 7 | Vorgeschlagener Kundenpilot |
| 04:10-04:30 | Folie 8 | Grenzen und Abschluss |

Für die Folienabschnitte 1, 2 und 6-8 bleibt der Sprechtext im bisherigen [Skript](Demo-Script.md) unverändert. Die beiden Appendix-Folien nicht im Video durchsprechen.

## 1. Engineer: Fehler untersuchen (00:50-01:45)

### Vorbereiten und klicken

1. **Your perspective: Engineer**.
2. **Dataset: OpenStack**. **Ownership team: All teams**.
3. Zeitraum **14.-17. Mai 2017** beibehalten und **Apply scope** klicken.
4. Nach unten zu **Ask the investigator** scrollen und diese Frage in das Chatfeld kopieren:

```text
What causes the recurring ComputeManager._run_image_cache_manager_pass failure, and how often does it recur? Inspect the traceback and distinguish observations from hypotheses. Give one next check with log IDs.
```

5. Absenden. Während der Berechnung erscheint ein Spinner. Nach der Antwort zeigt die App den tatsächlichen Status und die Anzahl der Werkzeugaufrufe.
6. Die Antwort kurz zeigen. Danach das **Query evidence · … tool calls** direkt bei dieser Agent-Antwort öffnen. Der andere Belege-Bereich weiter oben gehört zur direkten Analyse.
7. In den Belegen die Abschnitte **search_logs** und **get_context** zeigen. Unter jedem Abschnitt stehen Eingaben, tatsächlich ausgeführte SQL und Ergebnis-Tabelle. Bei mehreren get_context-Aufrufen die vollständige Traceback-Abfrage wählen.
8. Die Meldung **InvalidDiskInfo** und **No such file or directory** zeigen. Im bestätigten Lauf stehen sie in den Logs **4793594 / OS-0063** und **4793598 / OS-0067**. Bei breiten Tabellen zur Message-Spalte horizontal scrollen.

### Dieses Bild passt zu diesen Sätzen

| Während ihr zeigt … | Dazu sprechen … |
|---|---|
| Die eingegebene Frage und den Beginn der Antwort | “The engineer asks why the image cache manager keeps failing. The agent searches the message and retrieves context.” |
| search_logs und die Suchaggregation | “It finds eight matching failure messages.” |
| get_context, Traceback und Message-Spalte | “The traceback identifies InvalidDiskInfo. The qemu-img command cannot open an instance disk: the path does not exist.” |
| Ausgeführte SQL und Log-IDs | “We can inspect the exact log IDs and SQL.” |
| Empfehlung in der Antwort oder noch einmal Folie 3 | “Next, check the disk path and related deletion or storage activity. This explains the inspected failure. The other seven reports still need checking.” |

### Vollständiger Sprechtext, unverändert

> The engineer asks why the image cache manager keeps failing. The agent searches the message and retrieves context. It finds eight matching failure messages. The traceback identifies InvalidDiskInfo. The qemu-img command cannot open an instance disk: the path does not exist. We can inspect the exact log IDs and SQL. Next, check the disk path and related deletion or storage activity. This explains the inspected failure. The other seven reports still need checking.

## 2. Team Lead: Muster und Verlauf (01:45-02:35)

### Erst die Diagramme vorbereiten

1. **Your perspective: Team Lead**. **Dataset: BGL**. **Ownership team: HPC Kernel**.
2. Vollständigen Zeitraum **3. Juni 2005 bis 4. Januar 2006** behalten. **Apply scope** klicken.
3. Oben **Analyze recurring patterns** klicken. Die App zeigt Häufigkeiten und die Tabelle mit Mustern und Reichweite.
4. Unter **Follow a pattern** den Eintrag **BGL-0019 · HPC Kernel** wählen.
5. **Trend resolution: 1 week** wählen. Das ist wichtig, weil der Sprechtext einen Wochenwert nennt. Darunter erscheint **Recurrence over time**.
6. Optional **Compare leading patterns** anklicken, wenn ihr mehrere Verläufe nebeneinander zeigen möchtet.
7. Erst jetzt im Bereich **Ask the investigator** die folgende Frage absenden:

```text
Which problems recur for HPC Kernel across the recorded BGL period? Compare full aggregate frequency and observed node reach for data TLB error interrupt and data storage interrupt. Inspect the weekly trend of BGL-0019 and recommend a next investigation. Cite evidence and disclose truncation.
```

8. Antwort und das dazugehörige **Query evidence** öffnen. Die Werkzeugnamen **top_patterns** und **pattern_trend**, SQL und Ergebnisse zeigen. Danach zu den bereits vorbereiteten Diagrammen hochscrollen. **Run prepared investigation jetzt nicht mehr drücken.**

### Dieses Bild passt zu diesen Sätzen

| Während ihr zeigt … | Dazu sprechen … |
|---|---|
| Rolle, Team und Agent-Antwort | “The team lead compares patterns across HPC Kernel.” |
| Tabelle und top_patterns-Belege | “SQL finds around one hundred fifty-three thousand TLB error lines.” |
| Wochenverlauf von BGL-0019 | “The trend shows a concentrated burst: more than one hundred fifty-two thousand in one weekly bucket.” |
| Häufigkeit und Knotenreichweite beider Muster | “Storage interrupts occur less often, but reach more nodes.” |
| Empfehlung oder Folie 4 | “Investigate that wider pattern and check the localized burst. These are log counts and observed nodes, not confirmed incidents or affected customers.” |

### Vollständiger Sprechtext, unverändert

> The team lead compares patterns across HPC Kernel. SQL finds around one hundred fifty-three thousand TLB error lines. The trend shows a concentrated burst: more than one hundred fifty-two thousand in one weekly bucket. Storage interrupts occur less often, but reach more nodes. Investigate that wider pattern and check the localized burst. These are log counts and observed nodes, not confirmed incidents or affected customers.

## 3. Manager: Prioritäten begründen (02:35-03:25)

### Erst die Prioritätsansicht vorbereiten

1. **Your perspective: Manager**. **Dataset: BGL**. **Ownership team: All teams**.
2. Vollständigen historischen BGL-Zeitraum behalten und **Apply scope** klicken.
3. Unter **Prioritize: Problems** auswählen und **Build priority board** klicken.
4. Falls eine Auswahl erscheint: **Comparison group** auf BGL mit beobachteten Knoten setzen. Die Roh-Bezeichnung dieser Gruppe ist **BGL:knoten**.
5. Unter **Explain a priority** den Eintrag **BGL-0119** wählen. Bei **Why this priority?** stehen die Formel und die einzelnen Faktoren.
6. Jetzt im Chat die folgende Frage absenden:

```text
Should we investigate data storage interrupt or data TLB error interrupt first? Use exact-phrase search aggregations for both and BGL priority_ranking. Compare full matching-line totals and observed node reach. Explain the score factors and recommend one next check. Do not invent economic impact or a score for a group outside the returned ranking.
```

7. Antwort und das zugehörige **Query evidence** öffnen. Beide **search_logs**-Belege und **priority_ranking** zeigen. Für die Gesamtzahlen in den Suchbelegen zur unterstützenden Aggregation scrollen: Die begrenzte Beispieltabelle allein beweist keinen vollständigen Gesamtwert.
8. Danach bei Bedarf zum vorbereiteten **Attention queue**, **Frequency × reach** oder **Why this priority?** hochscrollen.

### Dieses Bild passt zu diesen Sätzen

| Während ihr zeigt … | Dazu sprechen … |
|---|---|
| Manager-Ansicht und Agent-Antwort | “The manager compares frequency and reach.” |
| Vollständige Suchaggregationen beider Muster | “TLB errors produce more lines, but appear on five hundred forty-one nodes. Storage interrupts appear on twenty-two thousand five hundred twenty-nine nodes.” |
| Why this priority? und die Faktor-Tabelle | “Our score combines frequency, severity, reach, trend and alerts.” |
| Rangliste mit BGL-0119 an erster Stelle | “Storage interrupts rank first in this BGL comparison.” |
| Empfehlung oder Folie 5 | “We recommend investigating them first. The score supports prioritization. It does not measure financial damage.” |

### Vollständiger Sprechtext, unverändert

> The manager compares frequency and reach. TLB errors produce more lines, but appear on five hundred forty-one nodes. Storage interrupts appear on twenty-two thousand five hundred twenty-nine nodes. Our score combines frequency, severity, reach, trend and alerts. Storage interrupts rank first in this BGL comparison. We recommend investigating them first. The score supports prioritization. It does not measure financial damage.

## So bleibt es verständlich und unter fünf Minuten

- Pro Rolle zuerst die Frage, dann die Antwort, dann die überprüfbaren Belege zeigen. Diagramme nur passend zur Aussage einblenden.
- Die App zeigt die Werkzeugnamen und tatsächlichen Aufrufparameter nach der Antwort im Belege-Panel. Es gibt keine separate Taste für einen frei erfundenen SQL-Text.
- SQL nicht komplett vorlesen. Ein paar Sekunden sichtbar lassen und die Ergebniszeilen zeigen. Der Agent muss seine Zahlen durch diese Ergebnisse stützen.
- Nur tatsächliche Ladepausen herausschneiden. Keine erfolgreichen Antworten nachstellen und keine anderen Ergebnisse mit dem Skript übersprechen.
- Wenn ein Lauf andere Zahlen oder eine unvollständige Antwort liefert: Scope und Status prüfen, passende Belege zeigen und den Sprechtext anpassen.
- Lieber drei getrennte App-Clips aufnehmen. Den englischen Text anschließend ruhig darüber sprechen und mit den Folien auf etwa 4:30 Minuten schneiden.
- Anschließend zu Folie 6, 7 und 8 wechseln. Den bisherigen MCP-, Pilot- und Abschlusstext verwenden. Eine noch nicht aufgenommene Claude-Antwort nicht als getestet darstellen.
- Die fertige MP4 einmal vollständig ansehen: unter 5 Minuten, lesbare Schrift, klarer Ton, alle drei Rollen mit Werkzeugen, SQL und Ergebnissen.
