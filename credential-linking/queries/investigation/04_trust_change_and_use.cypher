// Q4: 동일 키의 신뢰정책 변경 → 동일 역할 AssumeRole → 발급 키 사용.
// 정책 본문/이전 권한은 모델에 없으므로 권한 상승의 필요조건을 입증하지 않는다.
WITH datetime($from) AS t0, datetime($to) AS t1
MATCH (changer:Credential)-[change:BASE_EVENT]->(role:Identity)
WHERE change.eventName='UpdateAssumeRolePolicy'
  AND change.outcome='SUCCESS' AND role.resourceType='role'
  AND change.eventTime >= t0 AND change.eventTime <= t1
  AND ($account='' OR changer.accountId=$account)
  AND ($resource='' OR role.id=$resource)
MATCH (changer)-[assume:BASE_EVENT]->(role)
WHERE assume.eventName='AssumeRole' AND assume.outcome='SUCCESS'
  AND assume.eventTime >= change.eventTime AND assume.eventTime <= t1
MATCH (changer)-[issued:BASE_EVENT {rel:'OBTAINS'}]->(key:Credential)
WHERE issued.eventID=assume.eventID AND issued.outcome='SUCCESS'
WITH DISTINCT t1, changer, role, key,
     change.eventID AS changeId, change.eventTime AS changedAt,
     assume.eventID AS assumeId, assume.eventTime AS assumedAt
OPTIONAL MATCH (key)-[use:BASE_EVENT]->(target:Node)
WHERE use.outcome='SUCCESS' AND use.dstAs <> 'Service'
  AND use.eventTime >= assumedAt AND use.eventTime <= t1
  AND use.eventName IN $effect_apis
RETURN changer.id AS actor, role.id AS affectedRole,
       changeId, changedAt, assumeId, assumedAt, key.id AS issuedKey,
       count(DISTINCT use.eventID) AS reviewUseEvents,
       collect(DISTINCT CASE WHEN use IS NOT NULL THEN
         {eventID:use.eventID, at:use.eventTime, api:use.eventName,
          target:target.id, readOnly:use.readOnly} END) AS subsequentUses
ORDER BY changedAt, changeId, assumeId, issuedKey
LIMIT $row_limit;
