-- Umfang und historische Zeitgrenzen je Datensatz/Team; keine Incident-Zaehlung.
SELECT l.dataset, COALESCE(o.team, 'Unassigned') AS team,
       COUNT(*) AS logzeilen_gesamt, MIN(l.ts) AS erstmals, MAX(l.ts) AS zuletzt
FROM logs l LEFT JOIN ownership o
  ON o.dataset = l.dataset AND o.component = l.component
GROUP BY l.dataset, o.team
ORDER BY l.dataset, o.team
