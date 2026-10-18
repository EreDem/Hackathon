SELECT template_id, COUNT(*) AS log_lines,
       COUNT(DISTINCT NULLIF(NULLIF(node, 'NULL'), '-')) AS nodes
FROM logs
WHERE dataset = 'BGL' AND level IN ('ERROR', 'FATAL')
  AND message IN ('data TLB error interrupt', 'data storage interrupt')
GROUP BY template_id
ORDER BY log_lines DESC;
