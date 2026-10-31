// Q3: 선택 이벤트 이후, 키 발급 경로로 연결되는 검토 대상 행위.
// 같은 리소스를 사용한 다른 주체로 역방향 확장하지 않는다.
// 동일 eventID+actor+target은 한 행. 관측 경로 우선, 이후 최단 설명 선택.
WITH datetime($from) AS t0, datetime($to) AS t1
MATCH (anchor:Credential)-[seed:BASE_EVENT]->(:Node)
WHERE seed.eventID = $event_id
  AND seed.eventTime >= t0 AND seed.eventTime <= t1
  AND ($account = '' OR anchor.accountId = $account)
WITH DISTINCT t0, t1, anchor, seed.eventID AS anchorEventId,
              seed.eventTime AS anchorTime
MATCH path=(anchor)-[:BASE_EVENT|CAN_OBTAIN*0..6]->(actor:Credential)
WHERE all(n IN nodes(path) WHERE n:Credential)
  AND all(n IN nodes(path) WHERE single(m IN nodes(path) WHERE m = n))
  AND all(r IN relationships(path) WHERE
    (type(r) = 'BASE_EVENT' AND r.rel = 'OBTAINS' AND r.outcome = 'SUCCESS')
    OR (type(r) = 'CAN_OBTAIN' AND $include_inferred
        AND coalesce(r.exercised, false)))
WITH t0, t1, anchor, anchorEventId, anchorTime, actor, path, [r IN relationships(path) | CASE WHEN type(r) = 'CAN_OBTAIN' THEN r.at ELSE r.eventTime END] AS times
WHERE all(t IN times WHERE t >= anchorTime AND t <= t1)
  AND all(i IN range(1, size(times)-1) WHERE times[i-1] <= times[i])
WITH t1, anchor, anchorEventId, actor, path,
     CASE WHEN size(times)=0 THEN anchorTime ELSE last(times) END AS arrival,
     size([r IN relationships(path) WHERE type(r)='CAN_OBTAIN']) AS inferredHops
MATCH (actor)-[effect:BASE_EVENT]->(target:Node)
WHERE effect.eventTime >= arrival AND effect.eventTime <= t1
  AND effect.outcome='SUCCESS' AND effect.dstAs <> 'Service'
  AND effect.eventID <> anchorEventId
  AND effect.eventName IN $effect_apis
  AND ($target_resource='' OR target.id=$target_resource)
WITH anchorEventId, actor, target, effect.eventID AS effectId,
     path, effect, inferredHops
ORDER BY inferredHops, length(path), effect.eventTime,
         [r IN relationships(path) | coalesce(r.eventID, startNode(r).id+'>'+endNode(r).id)]
WITH anchorEventId, actor, target, effectId, count(*) AS alternativeRows,
     head(collect({path:path, effect:effect, inferredHops:inferredHops})) AS chosen
WITH anchorEventId, actor, target, effectId, alternativeRows,
     chosen.path AS path, chosen.effect AS effect, chosen.inferredHops AS inferredHops
RETURN anchorEventId, effectId, effect.eventTime AS at, effect.eventName AS api,
       actor.id AS actor, actor.accountId AS actorAccount,
       target.id AS target, target.accountId AS targetAccount,
       CASE WHEN coalesce(actor.accountId,'')='' OR coalesce(target.accountId,'')=''
            THEN 'unknown'
            WHEN actor.accountId=target.accountId THEN 'same-account'
            ELSE 'cross-account-observation' END AS accountRelation,
       effect.readOnly AS readOnly, effect.sourceIP AS source,
       inferredHops, alternativeRows,
       [n IN nodes(path) | n.id] AS credentialSequence,
       [r IN relationships(path) |
  {kind:CASE WHEN type(r)='CAN_OBTAIN' THEN 'inferred-ip-overlap' ELSE 'observed-issuance' END,
   from:startNode(r).id, to:endNode(r).id, api:r.eventName, eventID:r.eventID,
   at:CASE WHEN type(r)='CAN_OBTAIN' THEN r.at ELSE r.eventTime END,
   viaWorkloads:r.viaWorkloads}] AS connectingEvidence,
       effect.refPath AS targetField,
       length(path)=6 AS touchesHopLimit
ORDER BY at, effectId, target
LIMIT $row_limit;
