-- load.sql – lädt die Ausgabe von prepare.py in SereneDB.
--
-- Voraussetzung: Der Container sieht euren Projektordner unter /data, also mit Volume gestartet:
--   docker compose up -d   (mountet den Repo-Ordner nach /data)
-- Pfade in read_parquet/read_csv sind Pfade IM Container (Server-Seite), nicht auf eurem Rechner.
--
-- Ausführen:  python ingest/run_sql.py ingest/load.sql   (aus dem Repo-Hauptordner)
--
-- ⚠ Syntax stammt aus der SereneDB-Doku (Quick Start, Data Import), lokal noch nicht getestet.
--   Bei Fehlern: Docs-MCP fragen oder in SQL nachschlagen:  SELECT * FROM sdb_docs.search('read_parquet');

-- 1) Tabellen frisch anlegen (Skript kann beliebig oft laufen)
DROP TABLE IF EXISTS logs;
DROP TABLE IF EXISTS templates;
DROP TABLE IF EXISTS ownership;

CREATE TABLE logs      AS SELECT * FROM read_parquet('/data/out/logs.parquet');
CREATE TABLE templates AS SELECT * FROM read_parquet('/data/out/templates.parquet');
CREATE TABLE ownership AS SELECT * FROM read_csv('/data/ingest/ownership.csv', header = true);

-- 2) Volltextindex auf der Nachricht (für search_logs / Engineer)
--    Falls das Wörterbuch schon existiert, die CREATE-Zeile beim zweiten Lauf ggf. auskommentieren.
CREATE TEXT SEARCH DICTIONARY english AS
    split_text(case := 'lower') WITH (frequency, position, offset);
CREATE INDEX logs_idx ON logs USING inverted(id, message english);
VACUUM (REFRESH_TABLE) logs;    -- danach findet die Suche auch die neu geladenen Zeilen

-- 3) Kontrolle
DESCRIBE SELECT * FROM logs;
SELECT dataset, COUNT(*) AS zeilen, COUNT(DISTINCT template_id) AS templates FROM logs GROUP BY dataset;

-- Komponenten ohne Team? (Ergebnis sollte leer sein, sonst ownership.csv ergänzen)
SELECT l.dataset, l.component, COUNT(*) AS n
FROM logs l LEFT JOIN ownership o ON o.dataset = l.dataset AND o.component = l.component
WHERE o.team IS NULL
GROUP BY l.dataset, l.component ORDER BY n DESC;

-- Beispiel Team Lead / Manager: Fehler pro Team
SELECT COALESCE(o.team, 'Unassigned') AS team, COUNT(*) AS errors, COUNT(DISTINCT l.template_id) AS fehlertypen
FROM logs l LEFT JOIN ownership o ON o.dataset = l.dataset AND o.component = l.component
WHERE l.level IN ('ERROR', 'FATAL')
GROUP BY team ORDER BY errors DESC;

-- Beispiel Engineer: Volltextsuche
SELECT id, ts, component, message FROM logs_idx
WHERE message @@ ts_phrase('connection refused') LIMIT 10;
