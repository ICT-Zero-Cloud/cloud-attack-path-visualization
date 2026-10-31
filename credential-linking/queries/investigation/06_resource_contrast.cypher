// Q6: 같은 자원에 접근한 다른 주체를 전부 연루시키지 않는 대조 타임라인.
// $target_resource는 필수. account는 anchor 키에만 적용하고 경유/대상 계정은 자르지 않는다.
WITH datetime($from) AS t0, datetime($to) AS t1
MATCH (anchor:Credential)-[seed:BASE_EVENT]->(:Node)
WHERE seed.eventID = $event_id
  AND seed.eventTime >= t0 AND seed.eventTime <= t1
  AND ($account = '' OR anchor.accountId = $account)
WITH DISTINCT t0, t1, anchor, seed.eventID AS anchorEventId,
              seed.eventTime AS anchorTime
MATCH (a:Credential)-[e:BASE_EVENT]->(target:Node {id:$target_resource})
WHERE e.eventTime >= t0 AND e.eventTime <= t1
WITH anchor, anchorEventId, anchorTime, a, e, target,
     EXISTS {
       MATCH path=(anchor)-[:BASE_EVENT*1..6]->(a)
       WHERE all(n IN nodes(path) WHERE n:Credential)
         AND all(n IN nodes(path) WHERE single(m IN nodes(path) WHERE m=n))
         AND all(r IN relationships(path) WHERE r.rel='OBTAINS' AND r.outcome='SUCCESS'
                 AND r.eventTime >= anchorTime AND r.eventTime <= e.eventTime)
       WITH path, [r IN relationships(path) | r.eventTime] AS times
       WHERE all(i IN range(1,size(times)-1) WHERE times[i-1] <= times[i])
     } AS issuedDescendant
RETURN DISTINCT anchorEventId, e.eventID AS eventId, e.eventTime AS at,
       a.id AS actor, a.accountId AS actorAccount, target.accountId AS targetAccount,
       target.id AS target, e.eventName AS api, e.outcome AS outcome,
       CASE WHEN a=anchor AND e.eventTime >= anchorTime THEN 'anchor-key'
            WHEN a=anchor THEN 'anchor-key-before-seed'
            WHEN issuedDescendant THEN 'observed-issued-descendant'
            ELSE 'not-linked-by-selected-issuance-rule' END AS relationToAnchor
ORDER BY at, eventId, actor
LIMIT $row_limit;

