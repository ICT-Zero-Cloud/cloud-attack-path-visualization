// Q2: 선택 이벤트를 수행한 키의 발급 계보와 선택 가능한 추정 연결.
// origin은 제한된 창/홉에서 관측한 선행 키이지 최초 공격자가 아니다.
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
RETURN anchorEventId, anchorTime, anchor.id AS actor,
       origin.id AS origin, hops, inferredHops,
       CASE WHEN hops=0 THEN 'anchor-only'
            WHEN inferredHops=0 THEN 'observed-issuance-path'
            ELSE 'includes-unconfirmed-handoff' END AS evidenceClass,
       [n IN nodes(path) | {key:n.id, account:n.accountId}] AS credentialSequence,
       [r IN relationships(path) |
  {kind:CASE WHEN type(r)='CAN_OBTAIN' THEN 'inferred-ip-overlap' ELSE 'observed-issuance' END,
   from:startNode(r).id, to:endNode(r).id, api:r.eventName, eventID:r.eventID,
   at:CASE WHEN type(r)='CAN_OBTAIN' THEN r.at ELSE r.eventTime END,
   viaWorkloads:r.viaWorkloads}] AS evidence,
       hops=6 AS touchesHopLimit
ORDER BY inferredHops, hops DESC, origin
LIMIT $row_limit;

