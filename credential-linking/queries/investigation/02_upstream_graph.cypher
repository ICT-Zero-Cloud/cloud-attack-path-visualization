// Q2 graph: Q2와 같은 경로 선택. 표의 evidenceClass를 함께 확인.
WITH datetime($from) AS t0, datetime($to) AS t1
MATCH (anchor:Credential)-[seed:BASE_EVENT]->(:Node)
WHERE seed.eventID = $event_id
  AND seed.eventTime >= t0 AND seed.eventTime <= t1
  AND ($account = '' OR anchor.accountId = $account)
WITH DISTINCT t0, t1, anchor, seed.eventID AS anchorEventId,
              seed.eventTime AS anchorTime
MATCH path=(origin:Credential)-[:BASE_EVENT|CAN_OBTAIN*0..6]->(anchor)
WHERE all(n IN nodes(path) WHERE n:Credential)
  AND all(n IN nodes(path) WHERE single(m IN nodes(path) WHERE m = n))
  AND all(r IN relationships(path) WHERE
    (type(r) = 'BASE_EVENT' AND r.rel = 'OBTAINS' AND r.outcome = 'SUCCESS')
    OR (type(r) = 'CAN_OBTAIN' AND $include_inferred
        AND coalesce(r.exercised, false)))
WITH t0, t1, anchor, anchorEventId, anchorTime, origin, path, [r IN relationships(path) | CASE WHEN type(r) = 'CAN_OBTAIN' THEN r.at ELSE r.eventTime END] AS times
WHERE all(t IN times WHERE t >= t0 AND t <= anchorTime)
  AND all(i IN range(1, size(times)-1) WHERE times[i-1] <= times[i])
WITH anchor, anchorEventId, anchorTime, origin, path,
     size([r IN relationships(path) WHERE type(r)='CAN_OBTAIN']) AS inferredHops,
     length(path) AS hops
RETURN path, anchor, anchorEventId, inferredHops, hops=6 AS touchesHopLimit
ORDER BY inferredHops, hops DESC, origin.id
LIMIT $row_limit;

