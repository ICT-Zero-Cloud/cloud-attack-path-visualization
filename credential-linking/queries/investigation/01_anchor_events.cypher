// Q1: 조사 시작 이벤트와 선택 근거. 공격 판정 점수가 아니다.
WITH datetime($from) AS t0, datetime($to) AS t1
MATCH (a:Credential)-[e:BASE_EVENT]->(target:Node)
WHERE e.eventTime >= t0 AND e.eventTime <= t1
  AND e.outcome = 'SUCCESS' AND e.dstAs <> 'Service'
  AND e.eventName IN $anchor_apis
  AND ($account = '' OR a.accountId = $account)
  AND ($resource = '' OR target.id = $resource)
WITH t0, t1, a, e.eventID AS eventId, e.eventTime AS at,
     e.eventName AS api, collect(DISTINCT target.id) AS targets,
     collect(DISTINCT e.sourceIP) AS sources
CALL {
  WITH a, at, t0
  MATCH (parent:Credential)-[issued:BASE_EVENT {rel:'OBTAINS'}]->(a)
  WHERE issued.outcome = 'SUCCESS' AND issued.eventTime >= t0 AND issued.eventTime <= at
  RETURN collect(DISTINCT {issuer:parent.id, eventID:issued.eventID,
                           at:issued.eventTime}) AS priorIssuance
}
CALL {
  WITH a, at, t1
  MATCH (a)-[issued:BASE_EVENT {rel:'OBTAINS'}]->(child:Credential)
  WHERE issued.outcome = 'SUCCESS' AND issued.eventTime >= at AND issued.eventTime <= t1
  RETURN count(DISTINCT issued.eventID) AS laterIssuanceEvents
}
RETURN eventId, at, a.id AS actor, a.accountId AS actorAccount, api, targets, sources,
       CASE
         WHEN api IN ['StopLogging','DeleteTrail','DeleteFlowLogs'] THEN 'audit-configuration-change'
         WHEN api = 'UpdateAssumeRolePolicy' THEN 'role-trust-change'
         WHEN api = 'CreateAccessKey' THEN 'credential-issuance'
         WHEN api IN ['GetSecretValue','GetParameter','GetParameters'] THEN 'sensitive-read-review'
         ELSE 'analyst-selected-operation'
       END AS reviewReason,
       priorIssuance, laterIssuanceEvents
ORDER BY laterIssuanceEvents DESC, at, eventId
LIMIT $row_limit;

