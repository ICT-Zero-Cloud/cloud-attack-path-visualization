# CloudTrail 조사 쿼리 — 사건의 근거와 범위를 설명하기

이 문서는 기존의 “수상 점수·도달 개수” 중심 쿼리를 사건 중심 조사 흐름으로 개편한 것이다. 실행용 쿼리는 `queries/investigation/`에 있다. 모든 쿼리는 읽기 전용이며, 기존 파서·적재 구조를 사용한다.

## 1. ORTHRUS에서 가져온 관점과 이번 설계

ORTHRUS의 §2는 같은 이웃·시간대·후손이라는 이유로 정상 활동까지 공격 관련으로 분류하는 문제를 지적한다. §4.5는 선택된 의심 노드 주변의 시간창에서 앞뒤 의존 관계를 추적하고 핵심 연결을 제시한다. §5.2는 분석가가 검토할 결과의 관련성을 다룬다. 본 쿼리는 이 조사 관점을 CloudTrail에 적용한다. ORTHRUS의 GNN·이상 점수·중요도 산식·노드 버전화를 구현한 것은 아니다. [ORTHRUS 원문, USENIX Security 2025](https://www.usenix.org/system/files/usenixsecurity25-jiang-baoxiang.pdf)

우리의 구체적 설계는 **검토할 이벤트를 선택하고 → 그 이벤트의 발급 계보를 설명하고 → 이후 연결되는 행위를 보여주며 → 공유 자원이나 약한 추론 때문에 섞인 결과를 구분하는 것**이다. 아래의 API 분류, 키 중심 경로, 원본 이벤트 연결, IP 후보 점검은 이번 프로젝트를 위한 설계이다. 논문에는 “ORTHRUS의 조사 관점에서 착안한 규칙 기반 질의”로 기술한다.

| 조사 질문 | 쿼리 | 결과에서 읽을 내용 | 필요한 모델 요소 |
| --- | --- | --- | --- |
| 어느 이벤트부터 살펴볼까? | Q1 | 검토 이유, 발급 이력, 이후 발급 활동 | 이벤트 속성·키 통합 |
| 이 행위를 수행한 키는 어디에서 발급되었나? | Q2 | 선행 키의 순서, 발급 이벤트와 추정 연결의 구분 | OBTAINS·자격증명 노드 |
| 이 사건 이후 어떤 키와 자원으로 활동이 이어졌나? | Q3 | 키 연쇄 + 후속 작업 + 대상·계정·근거 필드 | 발급 연결·종단 자원 추출 |
| 역할 정책 변경이 실제 역할 발급 및 사용과 연결되는가? | Q4 | 변경→동일 역할 위임→발급 키 사용의 증거 묶음 | 주체–객체 통합·eventID |
| 획득 후보는 시간창 내 어떤 근거를 갖는가? | Q5 | 후보별 실행 이벤트·후속 사용·출처 일치/불일치 | RUNS_ON·CAN_OBTAIN·sourceIP |
| 같은 자원을 쓴 다른 주체도 연결되는가? | Q6 | 동일 자원의 활동과 선택한 발급 계보의 연결 여부 | 자원·계정·시간·키 식별 |

## 2. 준비 및 실행

전제는 Neo4j 5.x에서 `load_3node_v2.cypher`와 `enrich_views.cypher`로 모델을 적재한 상태이다. 새 쿼리 자체에는 APOC 호출이 없다. `eventTime`과 `CAN_OBTAIN.at`은 datetime, `exercised`는 boolean, `viaWorkloads`는 목록이어야 한다. 적재 스크립트에는 초기화문이 있으므로 쿼리 실행을 위해 다시 적재할 필요는 없다.

1. Q1로 검토 대상 eventId를 고르거나, 이미 가진 CloudTrail eventID를 사용한다.
2. 아래 파라미터를 설정하고 Q2·Q3을 실행한다.
3. 신뢰정책 사건이면 Q4, 워크로드 획득 후보면 Q5를 추가한다.
4. Q3의 자원 하나를 `target_resource`로 지정하여 Q6으로 다른 주체의 활동을 대조한다.

Neo4j Browser에서 아래 명령을 **각각 실행**한다. 예시는 저장된 n4의 신뢰정책 변경 이벤트를 사용한다. n1~n3을 적재했다면 시간과 eventID를 해당 데이터에 맞춰 바꾼다. JSON 파라미터 파일은 [params.n4.example.json](../../queries/investigation/params.n4.example.json)이다.

```text
:param from => '2026-09-10T06:13:00Z'
:param to => '2026-09-10T06:14:00Z'
:param account => ''
:param resource => ''
:param target_resource => ''
:param event_id => '0140e32e-f328-4fc5-8984-63326b68a8df'
:param key => ''
:param include_inferred => false
:param row_limit => 100
:param anchor_apis => ['StopLogging','DeleteTrail','DeleteFlowLogs','UpdateAssumeRolePolicy','CreateAccessKey','GetSecretValue','ModifySnapshotAttribute','DeleteObject','DeleteObjects']
:param effect_apis => ['AssumeRole','CreateAccessKey','CreateUser','AttachUserPolicy','PutUserPolicy','UpdateAssumeRolePolicy','StopLogging','DeleteTrail','DeleteFlowLogs','GetSecretValue','GetParameter','GetParameters','ModifySnapshotAttribute','DeleteObject','DeleteObjects']
:param control_apis => ['SendCommand','SendSSHPublicKey']
```

[Browser 파라미터 문법](https://neo4j.com/docs/browser/operations/query-parameters/)

### 선택 축의 정확한 의미

- **시간**: `from`~`to`는 양끝을 포함한다. Q2는 선택 이벤트 이전, Q3는 선택 이벤트 시각 이후를 본다. Q2·Q3·Q6의 키 연쇄는 간선 시각이 비감소해야 한다. 같은 초의 선후관계는 구분하지 못한다.
- **계정**: `account`는 조사 시작 주체의 `accountId`다. Q1·Q4·Q5는 각각 이벤트 주체·정책 변경자·후보 출발 키에 적용한다. Q2·Q3·Q6에서는 시작 키만 필터링하고 경유 키와 대상 계정은 남긴다. 계정 필터로 계정 간 연결을 잘라내지 않는다.
- **자원**: `resource`는 Q1의 사건 대상 또는 Q4의 역할을 고르는 값이다. `target_resource`는 Q3의 최종 대상 필터이며 Q6에서는 필수이다. 모두 그래프의 정확한 `id`를 사용한다.
- **추정 연결**: `include_inferred=false`가 기본이다. true이면 Q2·Q3에 기존 `exercised=true` 후보도 포함하되 `inferredHops`와 개별 근거를 표시한다. 이는 Q5의 재점검을 통과했다는 뜻이 아니다.
- **검토 API**: API 목록은 분석가가 정하는 조사 범위이며 악성 판정 목록이 아니다. 삭제·발급·비밀 읽기의 정상 운영 사례도 포함될 수 있다. 서비스 전체를 지원하는 탐지기라고 주장하지 않는다.
- **계정 표시**: Q3·Q6의 대상 계정은 파서가 저장한 `accountId`다. 미상은 unknown으로 남기며 권한 상승·외부 공유를 증명하는 필드는 아니다. S3 등의 계정 정보는 원본/파서의 보완 방식도 확인해야 한다.

## 3. Q1 — 조사 시작 이벤트와 근거 카드

[01_anchor_events.cypher](../../queries/investigation/01_anchor_events.cypher)

기존의 임의 가중치 합계 대신 `reviewReason`, 선택 이벤트의 대상들, 선행 발급 이벤트, 이후 발급 횟수를 돌려준다. 예를 들어 정책 변경 이벤트가 “발급받은 키가 수행했고, 그 뒤 새 키를 발급했다”는 맥락을 한 행에서 볼 수 있다. 발급 횟수는 같은 `eventID`를 중복 계산하지 않는다.

`laterIssuanceEvents` 우선 정렬은 검토 순서를 위한 단순 규칙이며 ORTHRUS의 anomaly/criticality score가 아니다. Q1은 원인을 알 수 없는 침해를 자동 탐지하는 단계가 아니라, 명시적인 조사 기준으로 시작 이벤트를 고르는 단계다.

## 4. Q2 — 발급 계보와 근거 경로

[표 쿼리](../../queries/investigation/02_upstream_evidence.cypher) · [그래프 쿼리](../../queries/investigation/02_upstream_graph.cypher)

선택한 이벤트를 수행한 키까지 이어지는 선행 자격증명을 찾는다. 경로에는 성공한 `OBTAINS`와 선택적으로 허용한 획득 후보만 들어간다. 동일 자원·역할에 접근했다는 이유로 다른 키를 끌어오지 않는다.

결과는 `credentialSequence`, `evidence`, `inferredHops`, `evidenceClass`를 포함한다. 발급 연결에는 eventID와 API가, 추정 연결에는 경유 워크로드와 후보 시각이 표시된다. 그래프 버전은 표와 같은 조건으로 선택한 경로 자체를 그린다.

```cypher
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
```

`origin`은 창과 6홉 제한 안에서 찾은 선행 키다. 최상류라고 실제 최초 침입 키로 단정하지 않는다. `anchor-only`는 연결을 찾지 못했을 때도 출발 이벤트를 잃지 않기 위한 0홉 행이다. n4의 SSM 저장 키 획득처럼 로그에서 이어지지 않는 구간이 있으면 그대로 경계로 남긴다.

## 5. Q3 — 사건 이후의 활동을 근거와 함께 요약

[표 쿼리](../../queries/investigation/03_downstream_evidence.cypher) · [그래프 쿼리](../../queries/investigation/03_downstream_graph.cypher)

결과 한 행은 **선택 사건 → 자격증명 연쇄 → 후속 이벤트 → 대상 자원**이다. 단순 도달 자원 목록과 달리 다음을 함께 반환한다.

- 어느 키가 어느 발급/추정 연결을 거쳐 행위 주체가 되었는지
- 어떤 API가 언제 성공했고 읽기인지 변경인지
- 자원을 어느 원본 필드에서 추출했는지(`targetField`)
- 시작 주체와 대상의 계정 정보 및 추정 연결 포함 여부

중간 경로는 자격증명 사이만 허용하고, 자원은 마지막 행위의 대상으로 둔다. 따라서 공용 자원을 경유해 정상 주체까지 확장하지 않는다. 선택 이벤트 자체는 후속 결과에서 제외한다.

동일 `eventID+actor+target`은 한 행으로 합친다. 설명 경로가 여러 개면 추정 연결이 적은 경로를 우선하고, 그 안에서 가장 짧은 경로를 선택한다. 이는 **대표 설명 경로**이지 모든 대안의 완전한 보고가 아니다. `alternativeRows`는 선택 전 후보 행 수(중복 필드 행 포함)이며, 독립 경로 개수나 신뢰 점수가 아니다.

## 6. Q4 — 신뢰정책 변경이 역할 발급과 사용으로 이어졌는가?

[04_trust_change_and_use.cypher](../../queries/investigation/04_trust_change_and_use.cypher)

이번 구성에서 논문 본문에 넣기 좋은 사례다. `UpdateAssumeRolePolicy` 한 건, `AssumeRole` 한 건, 이후 작업을 각각 나열하는 대신 **변경된 바로 그 역할**과 **그 위임 호출에서 발급된 바로 그 키**를 기준으로 연결한다. 주체–객체 통합과 `eventID`를 보존한 모델의 활용을 보여준다.

```cypher
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
```

결과의 `changeId`·`assumeId`·`subsequentUses[].eventID`로 원본 이벤트를 확인할 수 있다. 이 쿼리는 같은 키가 변경과 위임을 수행하는 패턴을 대상으로 하며, 다른 키가 변경한 정책을 이용하는 모든 사례를 포괄하지 않는다. 정책의 이전 상태와 본문을 분석하지 않으므로 “이 변경이 위임을 가능하게 만들었다”는 필요조건까지 입증하지는 않는다.

## 7. Q5 — 획득 후보별 증거 점검

[05_handoff_evidence_audit.cypher](../../queries/investigation/05_handoff_evidence_audit.cypher)

기존 `exercised=true`는 전체 로그의 출처 값 중복이다. Q5는 이를 그대로 탈취 판정으로 사용하지 않고, 선택 시간창에서 **명시한 실행/접근 API → 해당 워크로드의 후보 키 사용**이 순서대로 존재하는지 조회한다. 실행 API 목록의 초기값은 `SendCommand`와 `SendSSHPublicKey`이며, 성공이 OS 실행 또는 IMDS 획득의 성공을 보장하지는 않는다.

| evidenceStatus | 분석가가 확인할 사항 |
| --- | --- |
| no-selected-control-evidence-in-window | 선택한 창과 API 목록에 실행·접근 근거가 없음 |
| no-later-successful-use-in-window | 근거 이후 후보 키의 성공 사용이 관측되지 않음 |
| later-use-without-matching-control-source | 후속 사용은 있지만 실행 호출 출처와 일치하지 않음 |
| ordered-control-and-same-source-use | 실행 후 같은 출처의 키 사용이 관측됨. 탈취는 여전히 확인 필요 |

`checks`에는 워크로드 ID, 실행 이벤트 ID, 시각, 출처, 후속 키 사용 이벤트 ID가 들어간다. 나쁜 후보를 조용히 삭제하지 않고 **남겨야 할 후보와 추가 증거가 필요한 후보의 차이**를 보여준다. Q5는 기존 후보 집합의 증거 점검이며 새로운 후보를 생성하거나 `CAN_OBTAIN`을 수정하지 않는다. n4처럼 후보가 없는 데이터에서 0행은 정상이다.

## 8. Q6 — 같은 자원의 다른 접근을 대조

[06_resource_contrast.cypher](../../queries/investigation/06_resource_contrast.cypher)

Q3에서 관심 자원의 ID를 골라 `target_resource`로 설정한다. 예를 들어 n4에서는 다음 값을 사용할 수 있다.

```text
:param target_resource => 'arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:prod/db-master-8DQ43E'
```

같은 자원의 시간창 내 접근을 모두 반환하면서, 선택한 사건 주체의 활동인지·관측된 후속 발급 키의 활동인지·선택한 발급 규칙으로는 연결되지 않는지를 구분한다. 실패 호출도 남긴다. Q6은 추정 연결을 사용하지 않는다. `not-linked-by-selected-issuance-rule`은 정상 판정이 아니라, 같은 자원을 썼다는 이유만으로 해당 사건에 합치지 않았다는 뜻이다.

다른 키의 접근이 실제 데이터에 없다면 결과는 작을 수 있다. 설명력을 높이기 위해 관련 없는 이벤트를 인위적으로 추가하지 않는다. 같은 자원·같은 IP를 공유하는 정상 활동이 있는 자료에서 이 쿼리의 대조 기능이 잘 드러난다.

## 9. 읽기 쉬운 결과를 유지하는 공통 규칙

1. 6홉은 조사 범위다. `touchesHopLimit`가 true이면 더 긴 연쇄가 잘릴 가능성을 검토한다. 이 값이 false여도 로그·시간창 자체의 완전성은 보장하지 않는다.
2. `row_limit`은 표시 제한이며 결과의 완전성을 보장하지 않는다. 반환 행 수가 제한과 같으면 제한을 높여 확인한다. LIMIT는 경로 탐색 비용을 상한으로 제한하지 않으므로 큰 그래프에서는 시간창과 시작 eventID를 먼저 좁힌다.
3. Q2·Q3은 0~6홉의 단순 자격증명 경로를 사용한다. 같은 노드를 반복하는 경로는 제외한다. 이는 ORTHRUS의 버전별 DAG 변환과 다르다.
4. 원본 이벤트는 `eventID`, 대상은 `id`로 대조한다. API 호출 한 건이 여러 간선을 만들 수 있으므로 이벤트 개수는 `count(DISTINCT eventID)`로 센다.
5. sourceIP·같은 계정·같은 자원만으로 사건 관련성을 확정하지 않는다. 관측된 발급과 추정 연결을 결과에서 분리한다.
6. Q3에서 제외한 API가 없어진 로그는 아니다. 조사 목록 밖의 일반 활동이 필요하면 원본 이벤트나 Q6의 자원별 기록을 함께 본다.

## 10. 논문에 넣을 활용 설명

> 제안 모델은 자격증명 발급 연결과 대상 자원 식별을 이용하여 사건 중심의 조사 질의를 지원한다. 조사자는 시간창과 계정·자원 조건으로 검토 이벤트를 선택하고, 선행 발급 계보와 후속 행위를 이벤트 단위 근거와 함께 조회할 수 있다. 특히 신뢰정책 변경 대상 역할과 후속 위임 호출을 연결하고, 해당 호출의 발급 키로 수행된 행위를 함께 제시한다. 또한 워크로드 획득 후보의 실행·사용 정황을 별도로 점검하여, 관측된 관계와 추가 확인이 필요한 추론을 구분한다.

본 문단은 지원 기능의 설명이다. 2026-09-14의 Python 조사 전략 평가는 `experiment_measurement.md`에 별도로 기록했다. 아래의 미측정 설명은 기존 개별 Cypher의 직접 실행에 관한 것이다. “조사 시간이 단축되었다”, “QoA가 향상되었다”, “불필요한 노드가 몇 % 감소했다”는 실험 결과를 아직 주장하지 않는다. 향후 검증은 이런 결과에 필요한 근거가 남는지와 잘못 포함된 근거를 확인하면 된다. 이번 작업은 우선 활용 가능한 쿼리 설계를 구체화하는 데 초점을 두었다.

## 11. 저장 데이터로 본 설명 예시

아래는 별도의 CSV 조회로 쿼리의 선택 규칙을 확인한 예시이며, Neo4j 실행 결과나 새 성능 실험은 아니다. n4의 정책 변경 이벤트를 시작점으로 두면 Q3의 규칙은 다음 맥락을 연결한다. 키는 가독성을 위해 뒤 8자리로 표시했다.

| UTC 시각 | 관측된 행위 | 설명에 포함되는 키 연쇄 |
| --- | --- | --- |
| 06:13:19 | tier2-admin-role 신뢰정책 변경: 조사 시작 이벤트 | 377HGFVC |
| 06:13:31 | 같은 역할 AssumeRole 및 임시 키 발급 | 377HGFVC → 7QBHVZLC |
| 06:13:32~35 | 사용자 생성·정책 부착·장기 키 발급 | 377HGFVC → 7QBHVZLC → ZCUWMCHR |
| 06:13:47~48 | 두 시크릿 GetSecretValue | 377HGFVC → 7QBHVZLC → ZCUWMCHR |

Q4의 동일 역할 대조에서는 변경 이벤트 `0140e32e-f328-4fc5-8984-63326b68a8df`와 위임 이벤트 `792f3408-70f0-4c9d-ab19-f985cd6fe616`가 연결되었다. Q3는 발급된 키의 다음 발급까지 따라가 최종 시크릿 접근을 설명한다. 따라서 둘은 같은 사건을 반복해서 나열하는 것이 아니라 **권한 관련 변경의 사용 정황**과 **후속 자격증명 연쇄의 행위**를 나누어 보여준다.

n2의 전체 관측 시간창에서는 후보 11개 중 1개에 실행 이후 동일 출처 사용이 있었고, 나머지 10개에는 후속 사용은 있으나 선택한 실행 호출 출처와의 일치가 없었다. 이것은 기존 0/10이라는 요약보다 각 후보의 차이를 설명해준다. 정상·공격의 독립 정답을 추가한 정확도 검증은 아니다.

전체 이벤트 ID와 대상은 [n4 설명용 조회 결과](../../queries/investigation/preview.n4.csv-rules.json), [n2 후보 근거 조회 결과](../../queries/investigation/preview.n2.csv-rules.json)에 기록되어 있다.

## 12. 확인 상태

2026-09-11 기준으로 프로젝트의 CSV·적재 스키마를 읽고 쿼리를 작성하였다. 현재 Docker의 Neo4j 실행 환경이 꺼져 있어 **실제 Neo4j에서의 파싱·실행 및 수행시간은 확인하지 않았다**. 저장된 CSV에 대한 별도 예시는 선택 규칙의 설명용이며 Cypher 실행 결과나 유용성 평가를 대신하지 않는다.

기존 `query.md`는 `work/orthrus_queries_20260911/query.before.*.md`에 보관했다. 기존 스코어카드·모티프를 새 쿼리의 판정 근거로 자동 결합하지 않았다.



## 공통 조사 모드 (2026-09-14 반영)

공통 질의는 `queries/investigation/07_common_investigation.cypher`이며 예시 입력은 `params.common.n4.json`이다. Q2~Q6은 기존 개별 조사 질의로 유지한다. 공통 질의는 고정 공격 순서 없이 상류·하류를 탐색하며, `include_inferred=false`는 관측 발급만, `true`는 워크로드 이동 후보까지 포함한다.

- 시간: `from`~`to`, 경로 내부 시간순 적용.
- 계정: `account`는 앵커 계정 조건이며 중간 타 계정 경로는 유지한다.
- 자원: `target_resource`는 후속 접근 대상 조건이며 중간 연결 근거는 유지한다.
- API: `effect_apis=[]`이면 성공한 대상 특정 행위를 모두 포함한다.
- 후보: `control_apis`로 지정한 워크로드 제어, RUNS_ON, 이후 대상 키 사용을 결합한다. `require_same_source=true`가 기본이며 동일 출처 근거를 요구한다.
- 후보 연결은 제어 시각과 후속 사용 시각을 모두 갖는다. 이전 홉 도달 이후에 제어가 있어야 하며, 다음 홉은 후속 사용 시각 이후부터 탐색한다. 집계 `at`·`exercised`만으로 연결하지 않는다.
- 반환: 앵커, 키 경로, 각 홉의 관측/후보 구분, 제어·사용 eventID, 워크로드, 후속 자원 접근. LIMIT 없이 반환한다.

측정 코드는 `--mode observed|inferred|both`를 지원한다(기본 observed). inferred/both에는 `canobtain.csv`가 있는 view 디렉터리를 지정한다. `--allow-different-source`는 동일 출처 요구를 해제한다. `--account`, `--target-resource`, 반복 가능한 `--effect-api`로 범위를 설정한다. 계정은 앵커 확인 조건이고 자원/API는 후속 행위 조건이다. 범위를 변경해 정확성을 비교할 때는 해당 조사 질문에 맞는 GT를 사용한다.

```powershell
python -X utf8 "scripts/measure_investigation.py" --gt groundtruth_json/aws.5_chain_n4.common.json --csv csv/aws.5_chain_n4_view --mode both --output results/common_investigation_n4.json
```

`proposed`는 관측 모드, `proposed_inferred`는 후보 모드다. 후보 모드 비교용 `k1_inferred`~`k3_inferred`도 동일한 후보 연결을 탐색하며, 후보를 만났을 때 원본 제어·사용 근거를 반환량에 포함한다. 가상 후보 자체를 새 CloudTrail 이벤트로 세지 않는다. 후보 목록과 개체쌍 수는 `inferred_handoffs`, `inferred_handoff_pairs`에 별도 저장한다. 현재 P/R/F1은 원본 이벤트·원본 근거 연결을 채점하며 후보 자체의 정답률은 포함하지 않는다.

Python은 선택한 경로 근거를 합쳐 중복 제거하고 발급 이벤트의 동반 대상 간선을 보존한다. Cypher는 경로별 근거를 반환한다. 새 Cypher는 읽기 전용으로 작성했으며 실제 Neo4j 실행·반환 집합 대조는 아직 수행하지 않았다.


## 13. ‘기존 질의를 바탕으로 했다’의 정확한 의미

### 13.1 문서·질의·측정 코드의 관계

여기서 ‘바탕으로 했다’는 **기존 Q2·Q3·Q5에 정의한 조사 규칙을 참고해 새로운 통합 질의와 Python 탐색 코드를 작성했다**는 뜻이다. 기존 Cypher 파일을 Python에서 호출하거나, Q2·Q3·Q5의 실행 결과를 합쳐 표를 만든 것이 아니다. Cypher를 자동으로 Python으로 번역한 것도 아니다.

```text
query.md에 설명된 개별 질의
  Q2: 상류 발급 계보
  Q3: 하류 발급 경로와 후속 행위
  Q5: 워크로드 후보의 제어·사용 근거 확인
                ↓ 규칙을 참고하고 통합·수정
  ┌──────────────────────────────────────────────────┐
  │ 07_common_investigation.cypher                    │
  │ Neo4j용 새 통합 질의: 경로별 근거를 반환          │
  └──────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────┐
  │ measure_investigation.py                          │
  │ CSV용 별도 구현: 선택 근거를 합쳐 중복 제거·채점 │
  └──────────────────────────────────────────────────┘
                ↓ 실제로 실행한 쪽은 Python
  measure_investigation_batch.py → n1~n4 결과 JSON·표
```

두 구현은 같은 조사 방향을 공유하지만 실행 경로나 출력 형식이 동일한 프로그램은 아니다. 따라서 현재 결과를 설명할 때는 **‘공통 조사 전략을 Python으로 구현하여 CSV에서 평가했다’**라고 쓴다. ‘Q2·Q3·Q5를 Neo4j에서 실행한 결과’, ‘07 Cypher의 직접 실행 결과’라고 쓰지 않는다.

### 13.2 Q2에서 가져온 규칙 — 이 키는 어디에서 왔는가

원본: `queries/investigation/02_upstream_evidence.cypher`.

Q2는 선택한 eventID를 실행한 Credential을 찾고, 그 키로 들어오는 자격증명 경로를 따라 이전 키들을 조사한다. 성공한 OBTAINS를 발급 근거로 사용하고, 최대 6홉·키 반복 금지·앵커 이전 시간순 조건을 적용한다.

공통 구현은 이 상류 조사 개념을 가져왔다. Python에서는 `proposed()`의 `obt_in`과 상류 반복문이 이를 수행한다. 예를 들어 `키 A → 키 B → 앵커 호출`이면 A에서 B를 발급한 근거를 반환한다. 공격 이름이나 고정 역할명이 탐색 조건은 아니다.

차이도 있다. 기존 Q2의 후보 확장은 CAN_OBTAIN의 집계 `exercised`와 `at`를 사용한다. 새 공통 구현은 Q5 방식의 원본 제어·사용 근거로 후보의 시작·도달 시각을 다시 구성한다.

### 13.3 Q3에서 가져온 규칙 — 이후 어떤 키와 자원으로 이어졌는가

원본: `queries/investigation/03_downstream_evidence.cypher`.

Q3는 앵커 호출 키에서 하류 발급 경로를 따라가고, 각 키에 도달한 시각 이후의 성공·대상 특정 행위를 찾는다. 예를 들어 `앵커 키 → 새 키 → 시크릿 접근`이면 새 키 발급과 시크릿 접근 근거를 함께 보여준다.

공통 구현은 이 하류 탐색과 ‘도달 이후 사용’ 조건을 가져왔다. Python에서는 `proposed()`의 하류 반복문, `arrivals`, 후속 `effect` 선택 부분이다. 대상 자원 조건은 후속 접근에 적용하고 중간 발급 근거를 남기는 것도 이 조사 흐름에 해당한다.

변경점은 다음과 같다.

- 기존 Q3는 `effect_apis` 목록에 든 API만 반환한다. 공통 구현은 빈 목록이면 모든 성공·대상 특정 행위를 허용한다.
- 기존 Q3는 같은 actor/eventID/target에 대해 관측 경로 우선·최단 경로를 대표로 선택한다. 새 공통 Cypher는 유효 경로별 근거를 반환하고 Python은 탐색한 근거를 합친다.
- Python은 선택한 발급 이벤트의 역할·사용자 등 동반 대상 간선도 보존하고 앵커 원본 행도 포함한다. 이것은 기존 Q3의 출력 행을 그대로 복제한 동작이 아니다.

### 13.4 Q5에서 가져온 규칙 — 이동 후보를 뒷받침하는 실제 근거가 있는가

원본: `queries/investigation/05_handoff_evidence_audit.cypher`.

Q5는 다음 근거를 대조하는 후보 점검 질의다.

```text
키 A ──제어 이벤트──> 워크로드 W <──RUNS_ON── 키 B
                                            │
                                            └──제어 이후 사용 이벤트
```

Q5는 제어·후속 사용이 있는지, 두 호출의 출처가 같은지를 확인하고 상태를 보고한다. 그 자체로 후보를 따라 다른 키까지 재귀적으로 조사하는 질의는 아니다.

새 공통 구현에서는 이 **점검 규칙을 후보 탐색의 허용 조건으로 사용**한다. Python의 `candidate_handoffs()`가 후보 증거를 만들고, `proposed()`가 발급 관계와 함께 이를 탐색한다. 기본 모드에서는 제어 이후 동일 출처의 사용이 있어야 한다. 새 구현은 이 사용 근거에도 성공·대상 특정 조건을 적용한다. 기존 Q5의 후속 사용 확인은 서비스 대상 행위를 포함할 수 있으므로 완전히 같은 조건은 아니다.

또한 후보에 두 시각을 둔다.

- 시작 시각: A가 W를 제어한 시각.
- 도달 시각: B의 후속 사용이 확인된 시각.

예를 들어 제어가 10:00, B 사용이 10:02라면, 그 후보 뒤의 탐색은 10:02 이후부터 이어진다. Q5의 결과를 단순 첨부하는 것보다 경로의 시간순에 통합한 형태다. 반환 근거에는 제어·사용 eventID와 워크로드를 남기며 후보를 관측 발급으로 바꾸어 표현하지 않는다.

### 13.5 Q1·Q4·Q6은 어떻게 사용했는가

- Q1: 시작 사건을 검토하는 별도 도구다. 이번 측정에서는 Q1로 앵커를 자동 검출하지 않고 시나리오 실행 기록에서 앵커를 지정했다.
- Q4: 신뢰정책 변경→동일 역할 위임이라는 질문별 질의다. 이 공격 순서를 공통 탐색에 넣지 않았다. n4 평가의 동일 역할 검사는 정답 채점 조건이며 결과를 선택하는 공통 탐색 규칙이 아니다.
- Q6: 같은 자원에 접근한 다른 주체를 대조하는 별도 도구다. 이번 표의 시간창·k홉 비교는 Q6를 실행한 것이 아니다. 측정 코드가 비교 전략을 별도로 구현한다.

### 13.6 실제 구현 대응표

| 조사 기능 | 원래 참고한 질의 | 새 Cypher의 구현 | Python의 구현 |
| :--- | :--- | :--- | :--- |
| 시작 이벤트의 호출 키 선택 | Q2·Q3 | anchor와 seed 매칭 | proposed의 anchors |
| 상류 발급 탐색 | Q2 | upstream 경로 | obt_in과 상류 탐색 |
| 하류 발급 탐색 | Q3 | downstream 경로 | obt_out과 하류 탐색 |
| 후보 제어·사용 검증 | Q5 | RUNS_ON·control·use 결합 | candidate_handoffs |
| 후보를 포함한 시간순 | Q2·Q3·Q5를 통합·수정 | begin/arrival 상태 연결 | eventTime/arrivalTime 및 탐색 시각 경계 |
| 후속 대상 행위 | Q3 | effect 선택 | arrivals 이후 effect 선택 |
| 원본 행 합집합·동반 간선 | 측정용 추가 규칙 | 경로별 ID 반환; 동일 집계 구현 아님 | addedge·issue_events |
| 정답 대조·시간창·k홉 비교 | 실험용 신규 코드 | 구현하지 않음 | evaluate·khop·main |

### 13.7 현재 결과와 검증 상태

n1~n4 표는 `measure_investigation_batch.py`가 `measure_investigation.py`를 네 번 실행해 얻었다. 배치 코드는 `.cypher`를 읽거나 Neo4j에 전송하지 않는다. 입력은 view CSV와 고정 조사 GT이며 출력은 `results/common_investigation_n*.json`이다.

Python 결과는 원본 이벤트와 원본 연결 튜플의 집합으로 평가한다. 후보 연결은 증거 목록으로 별도 저장한다. 새 Cypher는 경로별 결과를 반환하므로, 같은 근거 집합인지 확인하려면 실제 실행 후 집계·동반 간선 처리 규칙을 맞추고 전체 eventID·연결 집합을 비교해야 한다. 이 동등성 대조는 아직 수행하지 않았다.

이 문서의 ‘기반’은 **설계 규칙의 계승**을 의미하며, **동일 코드 실행이나 동일 결과의 입증**을 의미하지 않는다.
