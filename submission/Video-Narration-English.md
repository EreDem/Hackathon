# Kürzere Demo mit fortlaufenden Bedien-Clips

**Dauer: 03:08 Minuten.** Englische synthetische Entwurfsstimme. Keine Folien.

Die Clips erfassen während der Bedienung fortlaufend das Browserbild (typischerweise 9–11 neue Bilder/Sekunde; Ausgabe 25 fps). Klicks, Menüänderungen, Texteingaben, Scrollen und Ergebnisänderungen wurden in der laufenden App aufgenommen. Der gut sichtbare Cursor ist nachträglich aus den protokollierten Klick- und Scrollkoordinaten gezeichnet. Ladepausen und Wartezeiten zwischen den Aufnahmeschritten sind entfernt. Die Kapitel haben leicht angepasste Wiedergabegeschwindigkeiten. Es gibt keine künstlichen Standbild-Haltezeiten.

## 00:00–00:18 · Problem and product

We built Log Observatory to help operations teams turn millions of log lines into a useful next action. Engineers investigate failures, team leads track patterns, and managers compare priorities. SereneDB calculates the evidence; the agent explains it.

## 00:18–01:03 · Engineer: search, question and evidence

The engineer selects OpenStack and the historical period. We search the recurring cache manager message and find eight matches. We scroll to the investigator and paste our question about the cause, recurrence and next check. Then we send the question and let the agent investigate. The inspected traceback identifies InvalidDiskInfo: the instance disk path cannot be opened. Standard error says, No such file or directory. A lifecycle or storage problem is a hypothesis to check. We open Query evidence and inspect the actual tool call, executed SQL and returned rows. Other occurrences still need checking.

## 01:03–01:51 · Team Lead: patterns and weekly trend

For the team lead, we switch perspectives, choose the BGL dataset and assign the investigation to HPC Kernel. We apply the historical scope and click Analyze recurring patterns. TLB errors lead by frequency: one hundred fifty-two thousand seven hundred thirty-four log lines. Storage interrupts occur less often. We select weekly resolution. The TLB pattern has a concentrated burst, rather than sustained growth. Now we ask the agent to compare frequency and observed node reach. It explains the contrast and recommends an investigation, citing its tools. The SQL evidence remains inspectable. Log counts and observed nodes are not automatically confirmed incidents or affected customers.

## 01:51–02:47 · Manager: priorities and score factors

The manager switches to all teams in BGL and applies the scope. We build the priority board. Its error and fatal comparison weighs frequency, severity, observed reach, trend and alerts. Storage interrupts rank first. We open the selected problem and inspect each factor, so the recommendation is reviewable. Next, we ask the agent which problem deserves attention first. It compares five hundred forty-one nodes for TLB errors with twenty-two thousand five hundred twenty-nine for storage interrupts, and recommends investigating storage first. We open Query evidence and follow the ranking query to its returned rows. The score is a prioritization heuristic, not measured financial damage.

## 02:47–03:08 · Next step and limits

The next step is a supervised operations pilot, measuring investigation time and answer quality. Customer savings still need validation. Ownership is fictional, and people verify recommendations before acting. Log Observatory connects questions to evidence, and evidence to the next check.

## Eigene Stimme einsetzen

`Log-Observatory-Demo-Clips-No-Audio.mp4` ins Schnittprogramm laden und den Text anhand der Kapitelzeiten einsprechen. `Demo-Clips-Narration-English.mp3` ist eine separate Tempo-Vorlage. Die englischen Untertitel können optional importiert werden.

Alle drei Antworten wurden für diese Fassung neu über den Agent-Chat erzeugt. Historische Daten, fiktive Ownership und heuristische Scores bleiben offen benannte Grenzen. Dieses Video zeigt keine Claude-Sitzung für den MCP-Sonderpreis.
