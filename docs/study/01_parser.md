# 01. Parser — CloudTrail 레코드를 노드와 간선으로

대상 파일: `ct_graph_v2/parser_node3_v2.py` (773줄)
논문 위치: 3.1 자격증명 식별과 발급 대상의 주체 통합, 3.2 다중 필드 대상 추출, 표 1
관통 예시: n4 (`00_README.md` §2의 Cred1~Cred4)

---

## 0. 한 줄 요약

CloudTrail 레코드를 한 건씩 읽어 **호출한 키 → 대상** 간선을 만든다. 이때 (1) 주체를 ARN이 아니라 accessKeyId로 식별하고, (2) 발급 응답에 새 키가 있으면 `OBTAINS`로 잇고, (3) 대상을 `resources[]`뿐 아니라 요청·응답 필드에서도 찾는다. "이 키가 누구 것인가"처럼 여러 레코드에 걸쳐 성립하는 사실은 따로 모아 `context.csv`에 쌓는다.

파서는 **해석하지 않는다.** 공격인지, 전이인지, 탈취 가능한지는 전부 02(뷰)와 03(조사)이 판단한다. 파서는 로그에 적힌 사실을 잃지 않고 옮기는 것만 한다.

---

## 1. 입력과 출력

```powershell
python parser_node3_v2.py <log.json> -o <출력폴더> [--extract-level 0|1|2|3] [--drop a,b,...] [--max-evidence 20]
```

입력은 `{"Records":[...]}` 형식, 레코드 배열, JSON Lines 모두 받는다 (`load_events`, 455–475행).

출력 CSV 세 개 (컬럼 정의 365–366, 482–485행):

| 파일 | 한 행의 의미 | 컬럼 |
|---|---|---|
| `nodes.csv` | 노드 하나 (id 유일) | `id, labels, actorType, arn, accountId, kind, resourceType, service, name, region, synthetic` |
| `edges.csv` | **이벤트 × 대상** 하나. 한 레코드가 대상 N개면 N행 | `src, dst, rel, actionL2, dstAs, refPath, eventID, eventName, eventSource, eventTime, sourceIP, outcome, errorCode, errorClass, readOnly` |
| `context.csv` | (src, dst, rel) 하나. 여러 레코드의 관측을 한 행으로 집계 | `src, dst, rel, via, evidenceCount, firstSeen, lastSeen, eventIDs` |

`edges.csv`의 `rel` 값은 네 가지다.

| rel | 언제 | dstAs |
|---|---|---|
| `OBTAINS` | 발급 응답에 새 accessKeyId가 있을 때 | `Actor` |
| `ASSUME_ROLE` | 대상이 role이고 eventName에 `assumerole`이 들어갈 때 | `Resource` |
| `ACCESS` | 요청·`resources[]`·serviceEventDetails에서 찾은 대상 | `Resource` 또는 `Service` |
| `PRODUCES` | 응답에만 등장한 대상 (생성된 자산) | `Resource` |

n4에는 `PRODUCES`가 0건이다 (`ACCESS 143 / ASSUME_ROLE 9 / OBTAINS 6`).

---

## 2. main() 흐름 — 레코드 한 건이 지나가는 순서

530–724행의 루프 몸통을 순서대로 요약하면 이렇다. 이 순서를 머리에 넣어두면 나머지 절은 각 단계의 상세다.

```
for event in 레코드들:                                   # 530
    ① 공통 필드 꺼내기: sourceIP, eventTime, readOnly, errorCode …   # 531–549
    ② outcome / errorClass / actionL2 결정                 # 543–549   → §9
    ③ 주체 노드 만들기: parse_actor()                      # 555–556   → §3
    ④ ISSUES: 이 키는 어느 신원 소속인가 (userIdentity)    # 576–605   → §5
    ⑤ RUNS_ON: 이 키는 어느 워크로드에 실렸나 (inScopeOf)  # 607–615   → §6
    ⑥ 부분 실패 항목 수집: harvest_failed_items()          # 621–625   → §9
    ⑦ OBTAINS: 응답에 발급된 키가 있나                     # 627–665   → §7
    ⑧ 대상 후보 수집 → 노드화 → 간선                        # 667–716   → §8
    ⑨ 대상을 하나도 못 찾았으면 Service 노드로 수렴         # 718–724   → §8.5
```

⑦(OBTAINS)이 ⑧(대상 추출)보다 먼저라는 점, 그리고 OBTAINS 간선은 ⑧의 `emitted` 개수에 들어가지 않는다는 점을 기억해두면 뒤의 "알아둘 점" 하나가 이해된다.

---

## 3. 주체 식별 — `parse_actor()` (417–452행)

```python
if access_key_id:        p_id = access_key_id             # 427
elif invoked_by:         p_id = f"svc:{invoked_by}"       # 429  AWS 서비스가 대신 호출
elif arn:                p_id = arn                       # 431
else:                    p_id = f"anonymous:{source_ip}"  # 433
```

`kind`는 키 접두사로 정한다: `AKIA`→`LongTermKey`, `ASIA`→`TempKey`, `svc:`→`Service` (436–445행).

### 왜 ARN이 아니라 accessKeyId인가

**ARN → accessKeyId가 1:N이기 때문이다.** 같은 IAM 사용자가 키를 여러 개 가질 수 있고, 같은 역할을 여러 번 위임받으면 세션마다 다른 ASIA 키가 나온다. ARN을 노드 id로 쓰면 그 키들의 활동이 한 노드로 뭉개진다.

n4에서 이게 왜 중요한지 보자. `role/tier2-admin-role`은 두 번 등장한다.

- Cred2가 **대상**으로 건드림 (UpdateAssumeRolePolicy, AssumeRole)
- Cred3이 그 역할의 **세션 키**로 행동함

ARN을 주체 id로 썼다면 "tier2-admin-role이 CreateUser를 했다"가 되고, Cred3이 Cred2로부터 발급됐다는 키 단위 계보가 사라진다. 논문 제안 1("사용자 단위로 뭉개지던 활동을 키 단위 경로로 복원")이 바로 이 줄이다.

### n4 예시

UpdateAssumeRolePolicy (0140e32e)의 `userIdentity`:

```json
"type": "AssumedRole",
"arn": "arn:aws:sts::123456789012:assumed-role/tier1-app-role/appsess",
"accessKeyId": "ASIAEXAMPLE0377HGFVC",
"sessionContext": { "sessionIssuer": { "arn": "arn:aws:iam::123456789012:role/tier1-app-role", ... } }
```

→ 주체 노드 id = `ASIAEXAMPLE0377HGFVC` (Cred2), `kind=TempKey`, `actorType=AssumedRole`.

`svc:` 주체가 생기는 경우도 있다. n4에서 `svc:resource-explorer-2.amazonaws.com`이 AssumeRole을 호출한 레코드는 `userIdentity`에 `accessKeyId` 없이 `invokedBy`만 있어 이렇게 된다.

---

## 4. 멀티라벨 단일 노드 — `NodeStore` (369–410행)

```python
def add(self, node_id, label, props):
    cur = self._n.setdefault(node_id, {'id': node_id, '_labels': set()})
    cur['_labels'].add(label)              # 라벨은 누적
    for k, v in props.items():
        ...
        cur.setdefault(k, v)               # 속성은 먼저 쓴 값을 유지
```

같은 id는 언제나 노드 하나이고, 역할(`Actor`/`Resource`/`Service`)은 라벨로 **겸한다.** 이전 버전(v1)은 Actor 사전과 Resource 사전을 따로 둬서 같은 role ARN이 두 노드로 갈라졌고, AssumeRole은 Resource 쪽에 도착하는데 세션 발급은 Actor 쪽에서 출발해 사슬이 끊겼다 (클래스 docstring).

`synthetic`만 예외 규칙이 있다 (390–394행). 한 번이라도 진짜 ARN으로 관측되면 `false`로 확정된다. 이름만 보고 ARN을 조립한 노드(§8.3)와 로그에 ARN이 그대로 찍힌 노드를 구분하기 위해서다.

n4에서 두 라벨을 동시에 가진 노드는 4개다. 예를 들어 `role/tier2-admin-role`은 `labels=Actor;Resource` — UpdateAssumeRolePolicy의 **대상**(Resource)이면서 Cred3을 발급한 **신원**(Actor, 600·663행에서 부여)이다.

---

## 5. ISSUES — 이 키는 어느 신원 소속인가 (576–605, 659–665행)

### 5.1 userIdentity에서 만드는 ISSUES

키가 **쓰인** 레코드마다, 그 키의 소속 신원을 `userIdentity`에서 읽어 `신원 → 키` 문맥 관계를 쌓는다.

```python
if sess.get("assumedRoot"):      owner = 계정 root,              via='assumed-root'   # 583
elif issuer_arn:                 owner = sessionIssuer.arn,       via='assumed-role' 또는 'federated'  # 587
elif uid_type == 'IAMUser':      owner = userIdentity.arn,        via='iam-user'       # 590
elif uid_type == 'Root':         owner = userIdentity.arn,        via='root'           # 592
# SAML / WebIdentity 등 외부 IdP 세션은 AWS 신원 노드가 없어 잇지 않는다 (한계, 574행 주석)
```

핵심은 **발급 이벤트가 아니라 사용 흔적이 근거**라는 점이다 (566–570행 주석). 그래서 발급 호출이 로그에 없는 키(콘솔 세션, 서비스 연결 역할 세션 등)도 소속은 알 수 있다.

### 5.2 발급 응답에서 만드는 ISSUES

AssumeRole처럼 요청에 `roleArn`이 있으면, 발급 시점에 바로 `role → 새 키` ISSUES를 만든다 (659–665행, `via='assumeRoleResponse'`).

### 5.3 집계 — `add_ctx()` (512–528행)

```python
k = (src, dst, rel)
if 처음:   ctx[k] = {via, evidenceCount:1, firstSeen, lastSeen, _ids:[eid]}
else:      evidenceCount += 1;  firstSeen/lastSeen 갱신;  _ids 는 최대 20개까지만
```

같은 (신원, 키, ISSUES)는 몇 번 관측되든 **한 행**이 된다. 출력할 때 `_ids`를 `|`로 이어 `eventIDs` 컬럼에 넣는다 (733–737행). `src == dst`면 아예 만들지 않는다 (513행).

### 5.4 n4 결과

```
src                              dst     via                 evidenceCount  firstSeen ~ lastSeen
user/deploy-user              → Cred1   iam-user            1              06:13:18 ~ 06:13:18
role/tier1-app-role           → Cred2   assumeRoleResponse  3              06:13:18 ~ 06:13:31
role/tier2-admin-role         → Cred3   assumeRoleResponse  4              06:13:31 ~ 06:13:35
user/apt-chain-e-admin        → Cred4   iam-user            3              06:13:46 ~ 06:13:48
```

`tier1-app-role → Cred2`의 3건은 발급 응답 1건 + Cred2가 쓴 레코드 2건(UpdateAssumeRolePolicy, AssumeRole)의 sessionIssuer다. 세 관측이 한 행으로 합쳐졌다.

n4 전체로는 ISSUES 근거가 된 레코드가 134건이고 `context.csv`는 33행이다.

### 5.5 왜 ISSUES는 간선이 아니라 문맥인가

ISSUES는 "이 호출이 일어났다"는 **사건**이 아니라 "이 키는 이 신원 것"이라는 **상태**다. 게다가 이걸 탐색 간선으로 쓰면 `Cred1 → deploy-user → (deploy-user의 다른 키)`처럼 신원을 경유해 무관한 키끼리 이어진다. 그래서 파일을 분리하고, 조사 전략은 이 파일을 순회하지 않는다. 논문 3.1 셋째 문단의 "문맥 관계는 … 경로 탐색에서는 순회하지 않으므로"가 이것이다.

---

## 6. RUNS_ON — 이 키는 어느 워크로드에 실렸나 (607–615행)

```python
scope = identity.get("inScopeOf") or {}
issued_to = scope.get("credentialsIssuedTo", "")
if issued_to:
    wid, wprops = classify_resource(issued_to, ...)
    add_ctx(actor_id, wid, 'RUNS_ON', scope.get('issuerType', 'inScopeOf'), ...)
```

`userIdentity.inScopeOf.credentialsIssuedTo`는 CloudTrail이 **"이 자격증명은 이 EC2 인스턴스에 발급된 것"**이라고 스스로 적어주는 필드다. 워크로드 노드는 이 필드로만 생긴다. "자격증명을 얻을 수 있는 자원" 일반이 아니라, 자격증명이 **실려 돌아가는** 실행 개체다.

| 사례 | RUNS_ON | 워크로드 |
|---|---|---|
| n1 | 1행 (근거 13건) | `instance/i-0e4edeef541a5f212` |
| n2 | 11행 | `instance/i-07eec8fec13e5ed60` (한 인스턴스에 세션 키 11개) |
| n3, n4 | **0행** | 없음 |

n4의 공격은 EC2를 거치지 않으므로 RUNS_ON이 없고, 따라서 02에서 CAN_OBTAIN 후보도 생기지 않는다.

---

## 7. OBTAINS — 발급 응답의 키를 잇는다 (627–665행)

모델의 중심이다. 발급 경로가 두 개다.

```python
creds = resp.get("credentials") or {}
issued_key = creds.get("accessKeyId")                       # STS: AssumeRole, GetFederationToken …
issued_ref = 'responseElements.credentials.accessKeyId'
if not issued_key:
    ak = resp.get("accessKey") or {}
    if ak.get("accessKeyId"):
        issued_key = ak["accessKeyId"]                      # IAM: CreateAccessKey
        issued_kind = 'LongTermKey'
        issued_ref = 'responseElements.accessKey.accessKeyId'
if issued_key:
    nodes.add(issued_key, 'Actor', {...})
    edges.append({**base, 'src': actor_id, 'dst': issued_key,
                  'rel': 'OBTAINS', 'dstAs': 'Actor', 'refPath': issued_ref})
```

**왜 이게 연결을 만드는가:** 발급된 키 노드의 id가 accessKeyId(§3)이고, 그 키가 나중에 호출 주체로 나타나면 `parse_actor()`가 **같은 id**를 돌려준다. `NodeStore`가 같은 id를 한 노드로 합치므로, 발급과 후속 사용이 자동으로 한 노드에서 만난다. 별도의 조인 로직이 없다.

`AKIA…`/`ASIA…`는 ARN도 AWS 리소스 id 패턴도 아니라서, 이 전용 분기가 없으면 §8의 일반 대상 추출로는 **절대** 안 잡힌다 (633행 주석). `DENY_CONTEXTS`에 `credentials`를 넣어 일반 추출에서 빼는 것도 같은 이유다 (116행).

### n4 예시 1 — AssumeRole (f216ac9b)

원본 (필요한 부분만):

```json
"userIdentity": { "type": "IAMUser", "arn": "arn:aws:iam::123456789012:user/deploy-user",
                  "accessKeyId": "AKIAEXAMPLE0SEAZXEHZ" },
"requestParameters": { "roleArn": "arn:aws:iam::123456789012:role/tier1-app-role", "roleSessionName": "appsess" },
"responseElements":  { "credentials": { "accessKeyId": "ASIAEXAMPLE0377HGFVC", ... },
                       "assumedRoleUser": { "arn": "arn:aws:sts::123456789012:assumed-role/tier1-app-role/appsess" } },
"resources": [ { "type": "AWS::IAM::Role", "ARN": "arn:aws:iam::123456789012:role/tier1-app-role" } ],
"readOnly": true
```

→ `edges.csv` 2행 (+ `context.csv`에 ISSUES 2개):

```
src    dst                   rel          actionL2  dstAs     refPath                                   readOnly
Cred1  Cred2                 OBTAINS      ASSUME    Actor     responseElements.credentials.accessKeyId  true
Cred1  role/tier1-app-role   ASSUME_ROLE  ASSUME    Resource  resources[].ARN                           true
```

한 레코드에서 대상이 두 개(발급된 키, 위임한 역할) 나왔으므로 간선이 두 개이고, **eventID는 같다.** 이벤트를 셀 때 eventID로 중복 제거해야 하는 이유다 (논문 3.1 둘째 문단).

`readOnly`가 `true`인 점에 주목하자. CloudTrail은 AssumeRole을 읽기 호출로 분류한다. 02의 advances 규칙이 `rel=='OBTAINS'`를 따로 허용하는 이유가 이것이다.

### n4 예시 2 — CreateAccessKey (4b056976)

```json
"userIdentity":      { "accessKeyId": "ASIAEXAMPLE07QBHVZLC", ... },
"requestParameters": { "userName": "apt-chain-e-admin" },
"responseElements":  { "accessKey": { "userName": "apt-chain-e-admin", "accessKeyId": "AKIAEXAMPLE0ZCUWMCHR", ... } }
```

→

```
Cred3  Cred4                       OBTAINS  CREATE  Actor     responseElements.accessKey.accessKeyId
Cred3  user/apt-chain-e-admin      ACCESS   CREATE  Resource  requestParameters.userName
```

STS가 아니라 IAM 경로로 발급된 **장기 키**도 같은 OBTAINS로 잇는다. 이걸 빠뜨리면 백도어 키 발급(T1098)의 결정적 산출물이 그래프에 없다 (632행 주석).

---

## 8. 대상 추출 (667–716행) — 논문 3.2의 본체

### 8.1 후보 수집 순서

```python
targets = []
for r in event["resources"]:                        targets.append(('resources[].ARN', arn, None, 'ACCESS'))   # 669
if EXTRACT_LEVEL >= 1:  harvest_refs(requestParameters)    → 'ACCESS'                                           # 673
if EXTRACT_LEVEL >= 1:  harvest_refs(serviceEventDetails)  → 'ACCESS'                                           # 676
if EXTRACT_LEVEL >= 1:  harvest_refs(responseElements)     → 'PRODUCES'  (unsuccessful 블록 제외)               # 679
```

순서가 곧 우선순위다. 같은 대상이 요청과 응답에 모두 나오면(응답이 요청을 echo하는 경우) 먼저 나온 요청 쪽 `ACCESS`만 남고 응답 쪽은 버려진다 (696–704행, `seen` 집합).

### 8.2 `harvest_refs()` — 중첩 JSON에서 식별자 찾기 (161–201행)

`walk_leaves()`(150–158행)로 JSON을 끝까지 내려가 `(경로, 값)` 쌍을 만들고, 값마다 아래 규칙을 **위에서부터** 적용한다.

| 순서 | 조건 | 결과 | 필요 레벨 |
|---|---|---|---|
| 1 | 값이 ARN 정규식(49행) 또는 AWS id 정규식(50–53행, `i-`, `snap-`, `fl-`, `sg-` …) | 수집 (타입 힌트 없음) | L1 |
| 2 | 경로에 `DENY_CONTEXTS`(110–117행: tagSet, filterSet, instanceState, credentials …)가 있음 | 버림 | — |
| 3 | 마지막 키가 `NAME_KEYS`(72–94행: bucketName, roleName, userName, snapshotId, secretId …) | 수집 + 키 이름으로 타입 힌트 | L2는 `CORE_NAME_KEYS` 6개만, L3는 전체 |
| 4 | 마지막 키가 `content`/`value`이고 부모 키가 화이트리스트 | 부모 키로 판단 (`{"tag":1,"content":"…"}` 래퍼) | L3 (핵심 키면 L2) |
| 5 | 마지막 키가 `name`이고 최상위 바로 아래 (`requestParameters.name`) | 수집 (문맥 키) | L3 |

**왜 경로(refPath)를 남기나** (163–166행 docstring): `filterSet` 안의 vpc-id는 "질의 조건"이고 `routeTableIdSet` 안의 값은 "명시적 대상"이다. 이 구분은 해석이라 파서가 결정하지 않고 출처만 남긴다.

**`DENY_CONTEXTS`는 왜 필요한가:** 태그 키, 필터 이름, 상태 문자열(`running` 등)을 노드로 만들면 그래프가 오염된다. 단, 규칙 1(ARN·id 패턴)은 규칙 2보다 **먼저** 검사하므로 deny 경로 안에 있어도 패턴이 맞으면 수집된다 (`credentials` 안만 예외, 180행).

### 8.3 `classify_resource()` — 문자열을 노드 id로 (204–265행)

id 우선순위: **정규 ARN > 계정·리전을 붙여 조립한 ARN > `service:name`**

| 입력 | 처리 | 예 |
|---|---|---|
| S3 ARN | bucket / object 구분 (218–225) | `arn:aws:s3:::bucket/key` → object |
| assumed-role ARN | **role ARN으로 정규화** (229–233) | `arn:aws:sts::…:assumed-role/tier1-app-role/appsess` → `arn:aws:iam::…:role/tier1-app-role` |
| 그 밖의 ARN | 그대로 | |
| AWS id (`snap-…`) | EC2 ARN 조립, `synthetic=true` (240–245) | `snap-0ecc…` → `arn:aws:ec2:ap-northeast-2:949…:snapshot/snap-0ecc…` |
| 이름 + 힌트 `iam-user`/`role` | IAM ARN 조립 (254–257) | `apt-chain-e-admin` → `arn:aws:iam::949…:user/apt-chain-e-admin` |
| 이름 + 기타 힌트 | `arn:aws:{svc}:{region}:{account}:{type}/{name}` (259–262) | |

assumed-role 정규화가 중요하다. 이게 없으면 같은 역할이 "세션 ARN 노드"와 "역할 ARN 노드"로 갈라져, 정책 부착 대상과 세션 발급자가 다른 노드가 된다.

### 8.4 n4 예시 — UpdateAssumeRolePolicy (0140e32e), 표 2의 n4 행

```json
"requestParameters": { "roleName": "tier2-admin-role", "policyDocument": "{…}" },
"responseElements": null
```

**`resources[]` 필드가 아예 없다.** 그래서:

- **L0 (resources[]만):** 대상 후보 0개 → §8.5에 따라 `iam.amazonaws.com` 서비스 노드로 수렴. "Cred2가 IAM에 뭔가 했다"만 남는다.
- **L3:** 규칙 3 — `roleName`이 `NAME_KEYS`에 있고 힌트는 `role` → `classify_resource('tier2-admin-role', hint='role')` → `arn:aws:iam::123456789012:role/tier2-admin-role`.

```
Cred2  role/tier2-admin-role  ASSUME_ROLE  ASSUME  Resource  requestParameters.roleName  readOnly=false
```

(`rel`이 ASSUME_ROLE로 찍히는 건 버그에 가깝다 → §11 알아둘 점 1)

그런데 L0에서도 `role/tier2-admin-role` **노드 자체는 존재한다.** 뒤이은 AssumeRole(792f3408)의 `resources[]`에 이 역할 ARN이 있기 때문이다. 그래서 표 2에서 n4는 **자원 3/3, 접근 2/3**이다. 노드는 있는데 "Cred2가 그 역할의 신뢰정책을 바꿨다"는 간선이 없다. 논문 4.3이 자원 식별과 접근 근거를 따로 세는 이유가 이 한 줄이다.

### 8.5 Service 수렴 (718–724행)

```python
if emitted == 0 and event_source:
    edges.append({... 'dst': event_source, 'rel': 'ACCESS', 'dstAs': 'Service', 'refPath': 'eventSource'})
```

대상을 **하나도** 못 찾았을 때만 `ec2.amazonaws.com` 같은 서비스 노드로 간선을 보낸다. 레코드를 버리지 않기 위한 장치다. 파서가 끝에 출력하는 "Service 수렴 %"가 대상 추출의 품질 지표다 (낮을수록 좋음).

---

## 9. 행위·결과 분류

### 9.1 `derive_action_l2()` — 의도 (272–290행)

```python
if "assumerole" in n or event_name == "GetFederationToken": return "ASSUME"
if read_only:                                              return "READ"
if n.startswith(create/run/put/insert/start):              return "CREATE"
if n.startswith(delete/terminate/remove/drop):             return "DELETE"
if n.startswith(update/modify/set/attach/detach):          return "MODIFY"
return "EXECUTE"
```

**의도만** 담는다. 성공/실패는 `outcome`/`errorClass`가 따로 가진다. 초판은 실패를 `DENY`로 덮어써서 "실패한 삭제 시도"가 질의되지 않았다 (275–277행). 지금은 실패한 DeleteBucket도 `DELETE + FAILURE`로 남는다.

### 9.2 `outcome`과 `classify_error()` (543–548, 336–358행)

`errorCode` 또는 `errorMessage`가 있으면 `FAILURE`. `errorClass`는 세 갈래로만 접는다: `DENIED`(권한 없음), `NOT_FOUND`(대상 없음), `FAULT`(그 밖). 원문 `errorCode`는 별도 컬럼에 그대로 둔다. n4의 실패는 `DENIED 4 / FAULT 3`.

### 9.3 `harvest_failed_items()` — 배치 API 부분 실패 (293–333행) `[논문 미사용]`

`DeleteFlowLogs` 같은 EC2 배치 API는 최상위 `errorCode` 없이 `responseElements.….unsuccessful`에만 실패 항목을 담는다. `errorCode`만 보면 실패한 로깅 삭제가 SUCCESS로 기록돼 "공격자가 로깅을 껐다"는 정반대 결론이 난다. 이 함수로 실패한 대상만 골라 **그 대상 간선만** FAILURE로 뒤집는다 (710–713행). 간선이 "이벤트 × 대상" 단위라 가능한 일이다. n1~n4에서는 발동하지 않았다.

---

## 10. 절제 옵션

### 10.1 `--extract-level` — 표 2가 쓰는 스위치

| 레벨 | 추가되는 것 | 코드상 관문 |
|---|---|---|
| **L0** (= 논문 R-전용) | `resources[]`만 | 673·676·679행의 `EXTRACT_LEVEL >= 1` 전부 막힘 |
| L1 | + ARN·AWS id 정규식 | 182행 |
| L2 | + 핵심 이름 키 6개 | 185·188행 |
| **L3** (= 논문 다중 필드, 기본값) | + 전체 화이트리스트, 래퍼, 문맥 키 `name` | 188·193·196행 |

**레벨과 무관하게 항상 켜진 것:** 주체 식별, OBTAINS(636행 분기에 레벨 조건 없음), ISSUES, RUNS_ON. 논문 4.3의 "두 구성에서 호출 주체 식별, OBTAINS, 신원·워크로드 문맥 등 다른 기능은 동일하게 유지한다"가 코드상 이렇게 보장된다.

표 2는 L0과 L3만 비교했다. L1·L2는 쓰지 않았다.

| 사례 | 노드 L0 → L3 | 간선 L0 → L3 | Service 수렴 L0 → L3 |
|---|---|---|---|
| n1 | 92 → 108 | 195 → 215 | 14.9% → 7.9% |
| n2 | 58 → 64 | 169 → 199 | 68.0% → 52.3% |
| n3 | 25 → 34 | 144 → 148 | 79.9% → 35.1% |
| n4 | 71 → 77 | 146 → 158 | 78.8% → 62.0% |

(출처: `results/target_extraction/n*_L*/parser_output.txt`)

### 10.2 `--drop` `[논문 미사용]`

`sourceIP, runsOn, issues, readOnly, errorClass, obtains, responseElements, resources, refPath` 중 골라 끈다 (496–498행). 이전 연구 방향(필드 leave-one-out)에서 쓰던 옵션이다.

---

## 11. 알아둘 점

1. **UpdateAssumeRolePolicy가 `actionL2=ASSUME`, `rel=ASSUME_ROLE`로 찍힌다.** 280행 `"assumerole" in n`과 705행 `'assumerole' in event_name.lower()`가 부분 문자열 검사라 `UpdateAssumeRolePolicy`에도 걸린다. 의도는 `MODIFY` / `ACCESS`다.
   - 실험 수치에는 **영향 없다.** 전이 판정(02의 advances)은 `readOnly=false`로 맞게 true가 되고, 조사 채점(03의 `rel_cat()`)은 eventName으로 따로 `CHANGE`를 붙인다.
   - 다만 Neo4j 화면에서 이 간선을 "위임"으로 읽을 수 있으니 시연 때 주의.

2. **같은 SSM 파라미터가 노드 두 개로 갈린다.** n4의 GetParameter(f466bb81)에서
   - `resources[]` → `arn:aws:ssm:…:parameter/app/prod/deploy-key`
   - `requestParameters.name` → `arn:aws:ssm:…:unknown//app/prod/deploy-key`

   문맥 키 `name`(규칙 5)은 타입 힌트가 없고, `ssm`이 `SERVICE_PRIMARY_TYPE`(123–127행)에 없어서 타입이 `unknown`이 된다. 691행 주석이 경계하던 바로 그 종류의 분열이다. 진입점 이벤트라 실험에는 영향이 없다.

3. **GetSigninToken은 자기 자신에게 OBTAINS를 만든다** (n3). 응답의 `credentials.accessKeyId`가 호출 키와 같은 값을 echo하는데, OBTAINS 분기(655행)에는 `src != dst` 검사가 없다. 게다가 OBTAINS는 `emitted`에 안 세서 같은 레코드에 Service 수렴 간선도 하나 더 생긴다. 조사 전략의 `succ()`가 `src != dst`를 요구해 둘 다 걸러지고, 이게 n3에서 필수 근거가 빠진 4건 중 하나다 (04 문서 §3.6).

4. **n4의 Service 수렴률은 62%로 높지만,** 수렴한 98건은 **전부 `readOnly=true`**이고 공격 키가 보낸 건 1건뿐이다 (콘솔의 ListManagedNotificationEvents, GetAccountPlanState 등). 상태를 바꾼 호출 중 대상을 놓친 건 없다.

5. **ISSUES의 `via`는 처음 본 값으로 고정된다.** `add_ctx()`가 두 번째부터는 `via`를 갱신하지 않는다. `tier1-app-role → Cred2`가 발급 응답(`assumeRoleResponse`)과 사용 흔적(`assumed-role`) 두 경로로 관측돼도 `via`에는 먼저 온 것만 남는다.

6. 40행 주석은 "L2 = 핵심 이름 키 5개"라고 하지만 `CORE_NAME_KEYS`(46–47행)는 6개다.

---

## 12. 직접 해보기

```powershell
# n4 파싱 — 기대 출력
python parser_node3_v2.py ..\stratus-red-team\log_json\aws.5_chain_n4.json -o $env:TEMP\n4
#   이벤트 140 / 노드 77 (Actor 35, Resource 20, Service 18, Actor;Resource 4)
#   BASE_EVENT 158 (ACCESS 143, ASSUME_ROLE 9, OBTAINS 6) / Service 수렴 98 (62.0%)
#   CONTEXT 33 / OBTAINS 6 / RUNS_ON 0 / ISSUES 근거 134

# 같은 로그를 L0으로 — UpdateAssumeRolePolicy가 어디로 가는지 비교
python parser_node3_v2.py ..\stratus-red-team\log_json\aws.5_chain_n4.json -o $env:TEMP\n4_L0 --extract-level 0
```

PowerShell에서 결과 확인:

```powershell
Import-Csv $env:TEMP\n4\edges.csv    | ? eventID -like '0140e32e*' | ft src,dst,rel,refPath
Import-Csv $env:TEMP\n4_L0\edges.csv | ? eventID -like '0140e32e*' | ft src,dst,rel,refPath
# L3: dst = arn:aws:iam::123456789012:role/tier2-admin-role   refPath = requestParameters.roleName
# L0: dst = iam.amazonaws.com                                  refPath = eventSource
```
