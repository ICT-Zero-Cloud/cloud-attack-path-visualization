# 03. 쿼리 — 공통 조사 전략

대상 파일:

- `scripts/measure_investigation.py` (241줄) 중 **전략 부분**: `proposed()`, `candidate_handoffs()`, 보조 함수 — **논문 수치를 만든 구현**
- `queries/investigation/07_common_investigation.cypher` (84줄) — 같은 전략의 Neo4j 판 (수치 산출에는 안 씀)
- `queries/investigation/01~06_*.cypher` — 개별 조사 질의 (시연용)

채점 부분(`evaluate()`, `khop()`, `main()`)은 04 문서에서 다룬다.

논문 위치: 3.4 공통 조사 전략, 4.4 첫 문단의 절차 설명
관통 예시: n4 (관측 발급만으로 완성), 후보 모드는 n1

---

## 0. 한 줄 요약

**시작 이벤트 하나 + 시간창**을 받아서

1. 그 이벤트를 호출한 키를 찾고,
2. 그 키로 **들어온** OBTAINS를 시간을 거슬러 따라가 발급 계보를 모으고 (상류),
3. 그 키에서 **나간** OBTAINS를 시간 순서대로 따라가 후속 키를 모으고 (하류),
4. 하류의 각 키가 **도달한 시각 이후에** 한 성공·대상 특정 행위를 모은다.

공격 유형별 규칙이 없다. 어떤 API가 공격인지, 어떤 역할 이름이 중요한지 코드에 없다. 시작 이벤트만 바꾸면 같은 규칙이 n1~n4 모두에 적용된다. 이것이 논문이 말하는 "공통"의 의미다.

---

## 1. 누가 수치를 만들었나 — Python과 Cypher의 관계

```
query.md의 개별 질의 Q2(상류) · Q3(하류) · Q5(후보 근거 점검)
                 │ 규칙을 참고해 통합·수정
      ┌──────────┴───────────┐
      ▼                      ▼
07_common_investigation.cypher      measure_investigation.py
(Neo4j, 경로별 근거 반환)           (CSV, 근거를 합쳐 채점)
                                     │  ← 실제로 실행한 쪽
                                     ▼
                         measure_investigation_batch.py → 표 3
```

논문 4.1의 "조사 전략은 제안 모델이 생성한 CSV 그래프에서 Python으로 실행하였으며"가 이 구조다. 두 구현이 **같은 결과를 낸다는 대조는 아직 하지 않았다** (query.md §13.7). 발표에서 "Neo4j로 돌린 결과"라고 말하면 안 된다.

---

## 2. 보조 함수 (measure_investigation.py 19–36행)

```python
def is_cred(nid):   return re.match(r'^(AKIA|ASIA)', nid)                        # 키 노드인가
def within(t,f,to): return f <= t <= to                                          # 시간창 안인가
def succ(r):        return (r['outcome']=='SUCCESS' and r['dstAs']!='Service'
                            and r['src']!=r['dst'])                              # 성공 ∧ 대상 특정 ∧ 자기 자신 아님
def is_obtains(r):  return r['rel']=='OBTAINS' and r['outcome']=='SUCCESS'
def rel_cat(r):                                                                  # 연결 튜플의 "관계 종류"
    if r['rel'] in ('OBTAINS','CAN_OBTAIN'): return r['rel']
    if r['eventName']=='UpdateAssumeRolePolicy': return 'CHANGE'
    return 'USE'
```

**`succ()`가 이 전략의 필터 전부다.** 02 문서의 `advances`와 비교하면:

| | `advances` (뷰) | `succ` (조사) |
|---|---|---|
| 성공 | ✔ | ✔ |
| 대상 특정 (Service 아님) | ✔ | ✔ |
| 상태 변경 또는 OBTAINS | ✔ | **요구 안 함** — 읽기도 통과 |
| 자기 자신 아님 | — | ✔ |

조사 전략은 **읽기도 모은다.** GetSecretValue(시크릿 읽기)가 공격의 목적지이기 때문이다. 논문 초기 리뷰에서 "전이 규칙과 시크릿 접근 사이에 틈이 있다"는 지적이 있었는데, 이 차이가 답이다 — 전이(어디로 더 나아가나)와 종단(무엇을 건드렸나)을 다르게 본다.

`rel_cat()`은 **탐색이 아니라 채점용**이다. 정답 파일의 연결 튜플 `(관계 종류, 출발, 도착, eventID)`과 비교하기 위한 분류다 (→ §9 알아둘 점 1).

---

## 3. `proposed()` 단계별 (65–123행) — n4를 따라가며

### 3.1 앵커 찾기 (67–69행)

```python
anchors = [r for r in edges if r['eventID']==anchor_id and succ(r) and within(r['eventTime'],f,to)]
a = anchors[0];  actor = a['src'];  atime = a['eventTime']
```

n4: 앵커 = `0140e32e` UpdateAssumeRolePolicy → **actor = Cred2, atime = 06:13:19**

### 3.2 OBTAINS 인접 리스트 (71–78행)

```python
obt_in  = {dst: [OBTAINS 간선…]}   # 이 키는 누구에게서 발급됐나
obt_out = {src: [OBTAINS 간선…]}   # 이 키는 무엇을 발급했나
if include_inferred:               # 후보 모드면 CAN_OBTAIN 후보(§4)도 같은 리스트에 넣는다
    for r in handoffs: obt_in[r['dst']].append(r); obt_out[r['src']].append(r)
```

탐색은 **OBTAINS 간선만** 따라간다. ACCESS, ISSUES, RUNS_ON은 순회하지 않는다. 그래서 신원을 경유해 무관한 키로 번지지 않는다 (01 문서 §5.5).

n4의 시간창 안 OBTAINS: `Cred1→Cred2`, `Cred2→Cred3`, `Cred3→Cred4`, 그리고 `svc:resource-explorer-2 → ASIA…` 3개.

### 3.3 `addedge()` — 결과에 담기 (81–88행)

```python
def addedge(r):
    if r['rel'] == 'CAN_OBTAIN':             # 후보는 연결로 세지 않고
        for witness in r['witnesses']:       # 근거가 된 원본 간선(제어·사용)을 대신 담는다
            addedge(witness)
        return
    c = (rel_cat(r), r['src'], r['dst'], r['eventID'])
    ret_edges[c] = r;  conns.add(c)
```

결과는 **원본 간선의 집합**이다. 추론 간선(CAN_OBTAIN) 자체는 결과 연결에 들어가지 않고 그 근거 레코드만 들어간다. 논문 4.4의 "CAN_OBTAIN 후보 간선은 연결 수에 합산하지 않는다"가 이 분기다.

### 3.4 상류 탐색 (93–101행)

```python
frontier = [(actor, atime, (actor,))]
while frontier:
    node, tmax, path = frontier.pop()
    if len(path)-1 >= 6: continue                                   # 6홉 상한
    for r in obt_in[node]:
        if (도착시각(r) <= tmax                                      # 시간을 거슬러서만
            and r['src'] not in path                                 # 경로 안 키 반복 금지
            and is_cred(r['src']) and is_cred(r['dst'])):            # 키 → 키만
            addedge(r); issue_events.add(r['eventID'])
            frontier.append((r['src'], r['eventTime'], path+(r['src'],)))
```

n4:

```
obt_in[Cred2] = [f216ac9b: Cred1→Cred2 @06:13:18]   06:13:18 ≤ 06:13:19 ✔  → 추가, Cred1로 이동
obt_in[Cred1] = []                                   종료 (Cred1의 발급은 로그에 없음)
```

`is_cred(r['src'])` 조건 때문에 `svc:resource-explorer-2 → ASIA…` 같은 서비스 발급은 계보로 올라가지 않는다.

### 3.5 하류 탐색 (102–112행)

```python
frontier = [(actor, atime, (actor,))]
while frontier:
    node, tmin, path = frontier.pop()
    if len(path)-1 >= 6: continue
    for r in obt_out[node]:
        if r['eventTime'] >= tmin and r['dst'] not in path and is_cred(...) and is_cred(...):
            addedge(r); issue_events.add(r['eventID'])
            at = 도착시각(r)                                         # 관측 발급이면 eventTime, 후보면 사용 시각
            arrivals[r['dst']] = min(arrivals.get(r['dst'], at), at)
            frontier.append((r['dst'], at, path+(r['dst'],)))
```

`arrivals`는 **"이 키가 언제부터 공격자 손에 있었나"**다. 앵커 키는 앵커 시각으로 초기화된다 (91행).

n4:

```
arrivals = {Cred2: 06:13:19}
obt_out[Cred2] = [792f3408: Cred2→Cred3 @06:13:31]   ≥ 06:13:19 ✔  → arrivals[Cred3] = 06:13:31
obt_out[Cred3] = [4b056976: Cred3→Cred4 @06:13:35]   ≥ 06:13:31 ✔  → arrivals[Cred4] = 06:13:35
obt_out[Cred4] = []                                   종료
issue_events = {f216ac9b, 792f3408, 4b056976}
```

### 3.6 동반 간선과 후속 행위 (113–121행)

```python
for r in edges:
    companion = r['eventID'] in issue_events                     # 발급 레코드의 다른 간선
    effect = (r['src'] in arrivals and not is_obtains(r)          # 도달한 키의 행위 중
              and r['eventTime'] >= arrivals[r['src']])            # 도달 이후
    if (companion or effect) and succ(r) and within(...):
        addedge(r)
```

- **동반(companion):** 발급 레코드가 만든 다른 간선. AssumeRole의 `키 → 역할` 간선, CreateAccessKey의 `키 → 사용자` 간선. "어느 역할로 위임받았나"를 보여준다.
- **후속(effect):** 하류 키(와 앵커 키)가 도달 이후 한 행위.

### 3.7 n4 최종 결과 — 이벤트 8개, 연결 12개

```
시각      eventID   GT    관계     출발   → 도착                     API
06:13:18  f216ac9b  필수  OBTAINS  Cred1  → Cred2                    AssumeRole         (상류)
06:13:18  f216ac9b  필수  USE      Cred1  → role/tier1-app-role      AssumeRole         (동반)
06:13:19  0140e32e  필수  CHANGE   Cred2  → role/tier2-admin-role    UpdateAssumeRolePolicy (앵커)
06:13:31  792f3408  필수  OBTAINS  Cred2  → Cred3                    AssumeRole         (하류)
06:13:31  792f3408  필수  USE      Cred2  → role/tier2-admin-role    AssumeRole         (동반)
06:13:32  c0f74667  문맥  USE      Cred3  → user/apt-chain-e-admin   CreateUser         (후속)
06:13:34  07281081  문맥  USE      Cred3  → user/apt-chain-e-admin   AttachUserPolicy   (후속)
06:13:34  07281081  문맥  USE      Cred3  → policy/AdministratorAccess AttachUserPolicy (후속)
06:13:35  4b056976  필수  OBTAINS  Cred3  → Cred4                    CreateAccessKey    (하류)
06:13:35  4b056976  필수  USE      Cred3  → user/apt-chain-e-admin   CreateAccessKey    (동반)
06:13:47  e7319337  필수  USE      Cred4  → secret prod/db-master    GetSecretValue     (후속)
06:13:48  9fa6b1c5  필수  USE      Cred4  → secret prod/api-key      GetSecretValue     (후속)
```

고유 eventID 8개 = 필수 6 + 문맥 2 + 무관 0. 전체 로그 140개 중 8개다. 이게 표 3의 n4 행이다.

**들어가지 않은 것과 그 이유:**

- Cred1의 다른 행위 — 상류 키는 `arrivals`에 없으므로 후속 행위를 모으지 않는다. (n4에서는 Cred1이 창 안에서 한 다른 성공·대상 특정 행위가 원래 없다.)
- 진입점 GetParameter(`f466bb81`) — 호출한 키가 Cred1이 아니라 다른 키라 계보로 이어지지 않는다. GT에서 `entry_unlinkable`로 따로 분류해 감점하지 않는다.
- 배경 활동 131개 — OBTAINS로 이어지지 않는 키의 행위라 아예 닿지 않는다. 그중에는 공격자와 **같은 IP(203.0.113.10)**를 쓰는 무관한 키 `AKIA…47FWDD4TB`의 이벤트 8개도 있다 (GT의 `negative_controls_natural`). "같은 IP ≠ 같은 사건"을 전략이 지킨다는 자연 대조군이다.

---

## 4. `candidate_handoffs()` — 로그에 없는 탈취를 근거로 잇기 (39–62행)

02 문서 §8에서 본 대로, 뷰의 CAN_OBTAIN은 가능성 목록이다. 조사 전략은 그 목록을 **원본 레코드로 다시 검증**해서 통과한 것만 탐색에 쓴다. 논문 3.3 셋째 단락이다.

```python
bindings = {(키, 워크로드) for RUNS_ON}
for g in canobtain.csv의 후보:
    for w in g['viaWorkloads']:
        if (g['dst'], w) not in bindings: continue
        controls = [r: g['src']가 w에 한 성공 간선, eventName ∈ {SendCommand, SendSSHPublicKey}]
        uses     = [r: g['dst']가 한 성공·대상 특정 간선]
        for control in controls:
            for use in uses:
                if use 시각 < control 시각: continue                          # 제어 이후 사용만
                same = control.sourceIP == use.sourceIP (AWS 도메인 아님)
                if require_same_source and not same: continue                   # 기본: 같은 출처 필수
                결과에 추가: rel='CAN_OBTAIN', eventTime=제어 시각, arrivalTime=사용 시각,
                            witnesses=[control, use]
```

**두 시각을 두는 이유:** 제어가 10:00, 탈취한 키의 첫 사용이 10:02라면 그 키는 10:02부터 공격자 손에 있다고 본다. 그래서 하류 탐색에서 `arrivals`에 사용 시각이 들어가고(110–111행), 그 키의 후속 행위는 10:02 이후만 모은다. 제어 시각부터 모으면 인스턴스가 원래 하던 정상 행위까지 딸려온다.

### n1 예시

```
후보(뷰): AKIA…W5UHPSX2 → ASIA…ZXTI44UW  via i-0e4ede…

제어: 5f835336 SendCommand @07:42:37  (공격자 IP 203.0.113.10)   ← 이게 n1의 앵커이기도 하다
통과한 사용 (같은 IP, 제어 이후):
  88c2e2cc @07:42:51  ListObjects       → ransomware 버킷
  ddc7648c @07:42:58  CreateUser        → user/apt-backdoor-admin
  40237724 @07:43:00  AttachUserPolicy  → AdministratorAccess
  83bcb124 @07:43:05  CreateAccessKey   → user/apt-backdoor-admin
→ handoff 행 4개 (쌍은 1개), arrivals[ASIA…ZXTI44UW] = 07:42:51
```

인스턴스 키가 인스턴스 IP(203.0.113.30)에서 한 `UpdateInstanceInformation`들은 출처가 달라 통과하지 못한다. n2에서는 같은 방식으로 뷰의 후보 11쌍이 1쌍으로 줄었다.

### 관측 모드 vs 후보 모드

| 사례 | 관측 발급만 (`proposed`) | 후보 포함 (`proposed_inferred`) |
|---|---|---|
| n1 | 반환 4, 연결 **1/55** | 반환 66, 연결 **55/55** |
| n2 | 반환 4, 연결 **2/24** | 반환 31, 연결 **24/24** |
| n3 | 반환 5, 연결 5/9 | 동일 (후보 없음) |
| n4 | 반환 8, 연결 6/6 | 동일 (후보 없음) |

n1에서 관측 모드는 앵커(SendCommand)와 그 결과 조회(GetCommandInvocation) 3개에서 멈춘다. 공격자 키에서 나가는 OBTAINS가 없기 때문이다. 후보 한 개가 인스턴스 키로 넘어가는 다리를 놓자, 거기서 다시 **관측된** OBTAINS(CreateAccessKey → 백도어 키)를 타고 StopLogging, 객체 삭제 52건까지 도달한다. 추론 한 홉 + 관측 한 홉의 조합이다.

---

## 5. 매개변수 — 코드에는 있지만 실험에서 쓰지 않은 것 `[논문 미사용]`

| 인자 | 코드 | 역할 | 표 3 실행값 |
|---|---|---|---|
| `--target-resource` | 117행 | 후속 행위 중 특정 자원만. 중간 발급 근거는 유지 | 비움 |
| `--effect-api` | 118행 | 후속 행위 중 특정 API만 | 비움 |
| `--account` | 199–202행 | 앵커 키의 계정 확인 | 비움 |
| `--allow-different-source` | 188행 | 후보의 같은 출처 조건 해제 | 끔 (같은 출처 필수) |
| 6홉 상한 | 97·106행 | 경로 길이 제한 | 코드에 있음. 실측 최대 깊이는 n3 하류 1홉, n4 상류 1·하류 2홉이라 **한 번도 발동하지 않음** → 논문에서 뺌 |

논문 4.4의 "후속 API·자원에 추가 제한을 두지 않았다"가 첫 두 줄이 비어 있다는 뜻이다.

---

## 6. Cypher 판 — `07_common_investigation.cypher`

같은 전략을 Neo4j에서 **경로 단위로** 반환한다. 뷰가 적재된 그래프(`:Credential` 라벨, `:CAN_OBTAIN` 간선)가 필요하다.

### 6.1 구조

```
4–9행    앵커: (anchor:Credential)-[seed:BASE_EVENT {eventID:$event_id}]->()
10–18행  두 방향의 가변 길이 경로
           상류  (origin:Credential)-[:BASE_EVENT|CAN_OBTAIN*0..6]->(anchor)
           하류  (anchor)-[:BASE_EVENT|CAN_OBTAIN*0..6]->(actor:Credential)
20–23행  경로 필터: 모든 노드가 Credential, 반복 없음,
           모든 간선이 성공 OBTAINS이거나 ($include_inferred일 때) CAN_OBTAIN
24–59행  홉마다 "선택지" 만들기
           관측 OBTAINS → {begin=arrival=eventTime}
           CAN_OBTAIN   → Python의 candidate_handoffs와 같은 제어·사용 결합 → {begin=제어, arrival=사용}
61–69행  reduce로 시간순 상태 전개: 다음 홉의 begin ≥ 이전 홉의 arrival
           상류는 최종 arrival ≤ 앵커 시각이어야 함
71–76행  하류 경로 끝 키의 후속 행위 (arrival 이후, 성공, Service 아님, 앵커 제외)
78–84행  경로별 반환: credentialSequence, connectingEvidence, inferredHops, effect…, touchesHopLimit
```

### 6.2 Python과의 대응 (query.md §13.6 정리)

| 기능 | Python | Cypher 07 |
|---|---|---|
| 앵커 | `anchors` 67행 | 5–9행 |
| 상류 | `obt_in` + 93–101행 | upstream 경로 |
| 하류 | `obt_out` + 102–112행 | downstream 경로 |
| 후보 검증 | `candidate_handoffs()` | 37–51행 |
| 시간순 | `tmax`/`tmin`, `arrivalTime` | `reduce` 상태 전개 |
| 후속 행위 | 113–121행 `effect` | 71–76행 |
| 동반 간선 | **있음** (`issue_events`) | **없음** |
| 출력 | 원본 간선 합집합 (중복 제거) | 경로마다 한 행 |

동반 간선 유무와 출력 단위가 달라서, 같은 사례에서 반환 이벤트 수가 다를 수 있다. 동등성 대조는 미수행이다.

---

## 7. 개별 질의 01~06 — 시연용 도구

`query.md`에 각각 해설이 있다. 논문 수치에는 쓰지 않았지만 Neo4j 시연에서 한 장면씩 보여주기 좋다. 매개변수 예시: `params.common.n4.json`.

| 파일 | 질문 | 비고 |
|---|---|---|
| `01_anchor_events.cypher` | 이 시간창에 조사를 시작할 만한 이벤트는? | `$anchor_apis` 목록으로 후보를 보여줄 뿐, 공격 판정 아님. 실험에서는 앵커를 시나리오 기록에서 지정 |
| `02_upstream_evidence/graph` | 이 키는 어디서 왔나? | 공통 전략 상류의 원형 |
| `03_downstream_evidence/graph` | 이후 어떤 키와 자원으로 이어졌나? | 공통 전략 하류의 원형. `$effect_apis` 필수 |
| `04_trust_change_and_use` | 신뢰정책 변경 → 같은 역할 위임 → 발급 키 사용 | n4 전용 시나리오 질의. 공통 전략에 넣지 않음 |
| `05_handoff_evidence_audit` | 각 CAN_OBTAIN 후보에 실제 제어·사용 근거가 있나? | `candidate_handoffs()`의 원형 |
| `06_resource_contrast` | 같은 자원에 접근한 다른 주체는? | 무관한 주체를 연루시키지 않는 대조용 |

---

## 8. 전략이 못 하는 것

- **서비스 수준 행위.** `succ()`가 `dstAs=='Service'`를 거른다. n3에서 필수 9개 중 4개를 놓친 이유다: ConsoleLogin, GetCallerIdentity, ListUsers (대상이 서비스 노드) + GetSigninToken (자기 자신으로 가는 OBTAINS, 01 문서 §11-3). 서비스 노드를 순회하면 허브가 되어 무관한 키가 대량으로 딸려오기 때문에 **순회**에서 빼는 건 맞는데, 이 4개는 전부 경로의 **끝(종단)**이다. 종단에서만 서비스 대상을 허용하면 회수할 수 있다. 현재는 보수적 설계다.
- **발급이 로그에 없는 키의 계보.** 상류는 OBTAINS가 있어야 올라간다. n4의 Cred1처럼 SSM 파라미터에서 읽어낸 키는 계보가 끊긴다.
- **다른 IP에서 쓴 탈취 키.** 후보 모드는 기본적으로 같은 출처를 요구한다. 공격자가 프록시를 바꾸면 놓친다 (`--allow-different-source`로 풀 수 있지만 오탐이 늘어난다).

---

## 9. 알아둘 점

1. **`rel_cat()`의 `CHANGE`는 API 이름으로 하드코딩돼 있다** (31행). 탐색에는 영향이 없고, 정답 파일의 연결 튜플 종류(`CHANGE`/`USE`/`OBTAINS`)와 맞추는 채점용 분류다. 01 문서 §11-1의 파서 버그(UpdateAssumeRolePolicy가 `rel=ASSUME_ROLE`로 찍힘)를 채점 단계에서 우회하는 효과도 있다. 누가 "공통 전략이라면서 특정 API 이름이 코드에 있다"고 물으면: 그 줄은 결과 선택이 아니라 채점 분류다.
2. **앵커 키 자신의 후속 행위도 모은다.** `arrivals`가 앵커 키로 초기화되기 때문이다 (91행). 상류 키의 행위는 모으지 않는다.
3. **뷰의 `advances`·`exercised`는 쓰지 않는다.** 뷰 CSV를 입력으로 받지만 실제로 읽는 건 `edges.csv`의 원본 컬럼, `context.csv`의 RUNS_ON, `canobtain.csv`의 (src, dst, viaWorkloads)뿐이다.
4. **n1·n2의 앵커는 제어 이벤트 자체다** (최초 SendCommand). 그래서 후보 모드의 효과가 크게 보인다. 관측 모드에서는 앵커 키에서 나가는 OBTAINS가 없어 곧바로 막히기 때문이다.

---

## 10. 직접 해보기

```powershell
cd ".\scripts"
python measure_investigation.py --gt ..\groundtruth_json\aws.5_chain_n4.common.json --csv ..\csv\aws.5_chain_n4_view --mode both
#   time_window: events=140 required=6/6 links=6/6 irrelevant=131 complete=True
#   proposed: events=8 required=6/6 links=6/6 irrelevant=0 complete=True
#   proposed_inferred: events=8 … (n4는 후보가 없어 동일)
#   Reduction vs window: 0.9428…
```

n4 결과 12행을 직접 뽑아보는 짧은 스크립트:

```python
import sys, json; sys.path.insert(0, '.')
import measure_investigation as m
gt = json.load(open('../groundtruth_json/aws.5_chain_n4.common.json', encoding='utf-8'))
E  = m.load_edges('../csv/aws.5_chain_n4_view')
ev, conns, rows, a = m.proposed(E, gt['anchor_event'], gt['window']['from'], gt['window']['to'])
for r in sorted(rows, key=lambda r: r['eventTime']):
    print(r['eventTime'][11:], m.rel_cat(r), r['src'][-8:], '->', r['dst'][-30:], r['eventName'])
```
