# 02. 후처리(뷰) — 기반 그래프 위에 해석을 얹는다

대상 파일:

- `scripts/simulate_views.py` (231줄) — **규칙의 원본** (Python)
- `scripts/apply_view.py` (102줄) — 규칙을 CSV로 물질화 → `csv/*_view/`
- `enrich_views.cypher` (586줄) — 같은 규칙의 Neo4j 판

논문 위치: 3.3 워크로드 기반 이동 후보, 표 1의 구분 열(이벤트/문맥/추론)
관통 예시: n4 + CAN_OBTAIN은 n1·n2 (n4는 RUNS_ON이 0건이라 후보가 없음)

---

## 0. 한 줄 요약

파서가 만든 기반 그래프는 "로그에 적힌 사실"만 담는다. 뷰는 그 위에 **해석** 네 가지를 얹는다.

| 단계 | 무엇 | 새 간선? | 논문 사용 |
|---|---|---|---|
| STEP 1 | 노드 종류 4분류 (`nodeKind`) | 없음 | 표 1의 노드 4종 |
| STEP 2 | 간선마다 `advances` (전이 여부) | 없음 | CAN_OBTAIN 합성의 입력 |
| STEP 3 | **CAN_OBTAIN** 합성 + `exercised` 표시 | **유일한 새 간선** | 3.3, 표 1의 "추론" |
| STEP 4 | SplitWorkload / SplitIdentity 표시 | 없음 | `[논문 미사용]` |

---

## 1. 왜 기반과 뷰를 나누나

기반을 **목적 중립**으로 두고, 목적별 해석은 뷰에서 바꾼다. 예를 들어 "무엇을 전이로 볼 것인가"는 조사 목적에 따라 달라질 수 있는데, 그걸 파서에 넣으면 목적이 바뀔 때마다 로그를 다시 파싱해야 한다. 뷰로 떼면 기반 CSV는 그대로 두고 규칙만 바꿔 다시 돌리면 된다.

세 파일의 관계:

```
simulate_views.py  ← 규칙의 진리원본 (함수: node_kind, advances, can_obtain, split_identity)
      │ import
      ▼
apply_view.py      → csv/aws.5_chain_n*_view/   ← 표 3 실험의 입력
      
enrich_views.cypher  ← 같은 규칙을 Neo4j에서 실행 (시각화·시연용). "두 결과가 다르면 둘 중 하나가 틀린 것" (simulate_views.py 5행)
```

`apply_view.py`는 규칙을 새로 구현하지 않고 `simulate_views`의 함수를 그대로 부른다 (29행 `import simulate_views as sv`). 그래서 Python 쪽 진리원본은 하나다.

---

## 2. STEP 1 — 노드 종류 (`node_kind`, simulate_views.py 25–40행)

```python
if n['resourceType'] in ('role', 'instance-profile', 'iam-user', 'iam-policy'):  return 'Identity'
if n['kind'] in ('LongTermKey', 'TempKey', 'Service', 'Anonymous'):              return 'Credential'
if n['resourceType'] in ('instance', 'launch-template'):                         return 'Workload'
return 'Asset'
```

파서의 `Actor/Resource/Service`는 **역할** 라벨이라 겹칠 수 있다(한 노드에 둘 이상). 뷰의 `nodeKind`는 **종류**라서 노드당 정확히 하나다. 기준은 "AWS가 뭐라 부르나"가 아니라 "이 그래프에서 무슨 역할을 하나"다 (enrich_views.cypher 62–63행 주석).

| nodeKind | 논문 표현 | 그래프에서의 역할 |
|---|---|---|
| Credential | 자격증명 | 모든 이벤트 간선의 출발점 |
| Identity | 신원 | 권한을 정의하는 IAM 객체. Actor이자 Resource일 수 있는 유일한 부류 |
| Workload | 워크로드 | 자격증명이 실리는 곳. CAN_OBTAIN이 경유 |
| Asset | 자원 | 나머지 대상 전부 |

n4: `Credential 35 / Asset 33 / Identity 9 / Workload 0`.

**검사 순서가 의미를 가진다.** role 노드는 `kind=Role`이기도 하지만 첫 줄에서 먼저 `Identity`가 된다. `svc:` 주체는 `kind=Service`라 `Credential`이다 (서비스 노드 `ec2.amazonaws.com`은 `kind`가 비어 있어 `Asset`).

---

## 3. STEP 2 — `advances` (simulate_views.py 43–51행)

```python
def advances(r):
    return (r['outcome'] == 'SUCCESS'
            and r['dstAs'] != 'Service'
            and (r['rel'] == 'OBTAINS' or r['readOnly'] == 'false'))
```

"이 호출이 공격자를 **전진**시키는가"를 불리언 하나로 표시한다. 새 간선은 만들지 않는다.

| 조건 | 의미 | 빠지면 |
|---|---|---|
| `outcome == SUCCESS` | 실제로 일어났다 | 실패한 시도는 전이가 아님 |
| `dstAs != Service` | 대상이 특정됐다 | "EC2에 뭔가 했다"로는 어디로 전진했는지 모름 |
| `rel == OBTAINS` | 새 자격증명을 얻었다 | — |
| 또는 `readOnly == false` | 상태를 바꿨다 | 읽기는 노출(잎)이지 전이가 아님 |

**`rel == OBTAINS`를 따로 허용하는 이유:** CloudTrail은 AssumeRole을 `readOnly: true`로 분류한다 (01 문서 §7). readOnly만 보면 키 발급이 전부 전이에서 빠진다.

**readOnly 하나로 가르는 이유:** 서비스별 지식이 필요 없다. 400개 서비스의 수천 API를 목록 없이 처리한다 (enrich_views.cypher 136–137행 주석).

### n4에서의 결과 — 158개 중 11개만 true

```
AssumeRole              OBTAINS      Cred1 → Cred2                      ✔ (OBTAINS)
UpdateAssumeRolePolicy  ASSUME_ROLE  Cred2 → role/tier2-admin-role      ✔ (readOnly=false)
AssumeRole              OBTAINS      Cred2 → Cred3                      ✔
CreateUser              ACCESS       Cred3 → user/apt-chain-e-admin     ✔
AttachUserPolicy        ACCESS       Cred3 → user/apt-chain-e-admin     ✔
AttachUserPolicy        ACCESS       Cred3 → policy/AdministratorAccess ✔
CreateAccessKey         OBTAINS      Cred3 → Cred4                      ✔
CreateAccessKey         ACCESS       Cred3 → user/apt-chain-e-admin     ✔
AssumeRole              OBTAINS      svc:resource-explorer-2 → ASIA…    ✔ ×3  (AWS 서비스 자체의 세션)
```

false인 147개의 사유: 대상 미특정(Service) 92, 읽기 48, 실패 7.

눈여겨볼 두 가지:

- `AssumeRole`의 **ASSUME_ROLE 간선(키 → 역할)은 false**다. readOnly=true이고 OBTAINS가 아니기 때문이다. 같은 레코드의 OBTAINS 간선만 true다.
- `GetSecretValue`(Cred4 → 시크릿)도 **false**다. 읽기이기 때문이다. 시크릿 접근은 "공격의 목적지"이지 "다음 단계로 넘어가는 통로"가 아니라는 해석이다. 03의 조사 전략은 advances를 쓰지 않으므로 이 간선도 결과에 들어간다 (§8 참고).

사례별 true 비율: n1 154/215, n2 16/199, n4 11/158. n1이 높은 건 S3 객체 삭제 52건이 모두 상태 변경이기 때문이다.

---

## 4. STEP 2b — 주체별 출처 IP 집합

```python
ip = r['sourceIP']
if ip and not ip.endswith('.amazonaws.com'):   # 서비스 대리 호출이면 IP 대신 도메인이 들어온다
    ip_of[r['src']].add(ip)
```

(simulate_views.py 129–134행, apply_view.py에서 `sourceIPs` 컬럼으로 저장) STEP 3b와 STEP 4가 이 집합을 쓴다.

---

## 5. STEP 3 — CAN_OBTAIN 합성 (simulate_views.py 54–86행)

### 5.1 규칙

```
   (주체 a) ─[advances=true 간선]→ (워크로드 w)      ① a가 w를 장악했다
   (키 b)   ─[CONTEXT: RUNS_ON]──→ (워크로드 w)      ② b가 w에 실려 있다
   ────────────────────────────────────────────
   ⇒ (a) ─[CAN_OBTAIN]→ (b)                          a는 b를 손에 넣을 수 있다
```

```python
runs = {workload: {cred…}}     on = {cred: {workload…}}        # RUNS_ON 역인덱스 (62–67)
for r in E:
    if not advances(r): continue                                 # ① 장악 간선만
    for cred in runs.get(r['dst'], ()):                          # ② 그 워크로드에 실린 키
        if cred == r['src']: continue                            # 자기 자신 제외
        if r['dst'] in on.get(r['src'], ()): continue            # a 자신도 w에 실린 키면 제외
        cur = out.setdefault((r['src'], cred), {'via': set(), 'at': r['eventTime'], 'n': 0})
        cur['via'].add(r['dst']); cur['at'] = min(cur['at'], r['eventTime']); cur['n'] += 1
```

**왜 필요한가:** 공격자가 인스턴스의 자격증명을 **훔친** 행위는 CloudTrail에 남지 않는다. IMDS 조회는 API 호출이 아니기 때문이다. 훔친 키를 **쓴** 기록만 남는다. 그래서 "a가 b를 얻었다"는 간선이 기반에 없고, 이 규칙이 그 빈칸을 **추론으로** 채운다 (enrich_views.cypher 176–181행 주석).

**두 번째 제외 규칙의 이유 (75–80행 주석):** 인스턴스에 실린 키는 그 인스턴스에 제어 간선을 남기게 마련이다(SSM 에이전트의 `UpdateInstanceInformation` 등). 그대로 두면 같은 인스턴스의 키들이 서로를 CAN_OBTAIN하는 쌍방향 간선이 생긴다. 같은 워크로드 안은 이미 같은 신뢰 경계라 "획득"이라 부를 게 없다. 이전 통합 로그 실측에서 19개 중 10개가 이 오류였고, 규칙을 넣은 뒤 9개로 줄었다 (timeline.md §2).

저장하는 근거: `viaWorkloads`(경유 워크로드), `at`(최초 장악 시각), `controlEvents`(근거 간선 수). 추론이므로 **사람이 반박할 수 있게** 근거를 싣는다.

### 5.2 n1 예시 — 후보 1개

```
RUNS_ON:  ASIA…ZXTI44UW → instance/i-0e4edeef541a5f212   (근거 13건, 07:41:27 ~ 07:51:27)

워크로드를 대상으로 한 advances=true 간선:
  ASIA…ZXTI44UW  UpdateInstanceInformation  07:41:27  203.0.113.30   ← 자기 인스턴스 → 제외 규칙 2
  AKIA…W5UHPSX2  SendCommand                07:42:37  203.0.113.10    ← ★ 공격자 키
  ASIA…ZXTI44UW  UpdateInstanceInformation  07:45:12, 07:46:27, 07:51:27  (제외)

canobtain.csv:
  AKIA…W5UHPSX2 → ASIA…ZXTI44UW   via=i-0e4ede…   at=07:42:37   controlEvents=1   exercised=true
```

공격자의 장기 키가 SendCommand로 인스턴스를 제어했고, 그 인스턴스에 실린 역할 세션 키를 얻을 수 있다는 후보 하나가 생긴다.

### 5.3 n2 예시 — 후보 11개

```
RUNS_ON: 같은 인스턴스 i-07eec8fec13e5ed60 에 세션 키 11개
         (ASIA…RSR5IOBD 근거 99건, 나머지 10개는 1~11건)

장악 간선: AKIA…W5UHPSX2 의 SendCommand 2건 (05:30:08, 05:31:12)

canobtain.csv: AKIA…W5UHPSX2 → 11개 키 전부, 그중 exercised=true 는 ASIA…RSR5IOBD 하나
```

한 인스턴스에 세션 키가 여럿 실리면 **장악 한 번이 키 개수만큼 후보를 만든다.** 이게 CAN_OBTAIN이 "가능성"인 이유다. 이 부채꼴을 줄이는 방법은 두 가지다 — 뷰의 `exercised`(§6)와, 조사 전략의 원본 근거 재구성(§8).

### 5.4 n4 — 후보 0개

n4에는 RUNS_ON이 없으므로(01 문서 §6) 규칙 ②를 만족하는 키가 없다. `canobtain.csv`는 헤더만 있다. 그래서 표 3에서 n4의 관측 모드와 후보 모드 결과가 같다.

---

## 6. STEP 3b — `exercised` (apply_view.py 84–86행)

```python
exercised = bool(ip_of.get(a, set()) & ip_of.get(b, set()))
```

주체 a의 출처 IP 집합과 키 b가 쓰인 IP 집합이 **겹치는가.** 겹치면 b가 a의 단말에서 쓰였다는 정황이다.

n1에서 true인 이유: 인스턴스 키 `ASIA…ZXTI44UW`가 인스턴스 IP(203.0.113.30)뿐 아니라 공격자 IP(203.0.113.10)에서도 쓰였다.

**한계 (enrich_views.cypher 228–230행 주석):** 공격자가 훔친 키를 다른 단말이나 프록시에서 쓰면 안 겹친다. 즉 `false`가 "탈취 없음"을 뜻하지 않는다. **증거가 있는 것을 고르는 필터**이지, 없는 것을 배제하는 필터가 아니다. 그래서 논문은 이 값을 "정황"으로만 다루고 표 3에는 쓰지 않았다.

---

## 7. STEP 4 — 신원 분열 표시 `[논문 미사용]` (simulate_views.py 127–144행)

같은 워크로드에 실린 키들의 출처 IP가 **2개 이상**으로 갈리면, 그 워크로드에 `finding=split-workload`, 해당 키에 `finding=split-identity`를 붙인다.

n1: 인스턴스 `i-0e4ede…`와 키 `ASIA…ZXTI44UW`에 표시됨 — EC2 자격증명 탈취의 전형적 흔적(같은 인스턴스 키가 인스턴스 밖 IP에서 쓰임)이다. 판정을 라벨이 아니라 속성으로 둔 건, 종류 색(STEP 1)과 판정이 화면 색을 두고 다투지 않게 하기 위해서다 (timeline.md §3).

같은 파일의 `build_adj()`, `reach()`, `reverse()` (89–124행)와 main의 "뷰 1·2·3" 출력도 이전 분석용이며 논문 수치에 쓰이지 않았다.

---

## 8. 뷰의 CAN_OBTAIN과 조사 전략의 후보는 **다르다** (중요)

논문 3.3의 두 단락이 각각 하나씩에 대응한다.

| | 뷰 `can_obtain()` (02) | 조사 `candidate_handoffs()` (03) |
|---|---|---|
| 논문 | 3.3 둘째 단락: "주체 a가 워크로드 w를 대상으로 성공시킨 쓰기 또는 발급 이벤트와 RUNS_ON(b,w)를 결합" | 3.3 셋째 단락: "SendCommand 또는 SendSSHPublicKey와 b의 이후 성공·대상 특정 사용이 같은 출처에서 관측될 때만 채택" |
| 장악 간선 | `advances=true`인 **모든** 간선 | `SendCommand`, `SendSSHPublicKey`만 |
| 탈취 근거 | 없음 (`exercised`는 표시만) | b의 **이후** 사용이 제어와 **같은 IP**에서 있어야 함 |
| 시각 | `at` 하나 (최초 장악) | 시작 시각(제어) + 도달 시각(사용) 두 개 |
| 출력 단위 | (a, b) 쌍 하나 | (a, b, w, 제어 eventID, 사용 eventID) 조합마다 |
| n2 결과 | **11쌍** | **1쌍** (`ASIA…RSR5IOBD`) |

즉 뷰의 CAN_OBTAIN은 **후보 목록**이고, 조사 전략은 그 목록에서 원본 레코드로 뒷받침되는 것만 골라 탐색에 쓴다. 표 3의 "후보 포함 모드"는 뒤쪽이다. 뷰의 `advances`와 `exercised`는 표 3 계산에 직접 들어가지 않는다 — 조사 전략은 `advances` 대신 자체 `succ()` 조건을 쓴다 (03 문서 §2).

---

## 9. `apply_view.py`의 출력

| 파일 | 기반 대비 추가 |
|---|---|
| `nodes.csv` | `nodeKind`, `finding`, `sourceIPs` |
| `edges.csv` | `advances` (`true`/`false`) |
| `context.csv` | 그대로 복사 |
| `canobtain.csv` | 새 파일: `src, dst, rel, exercised, viaWorkloads, at, controlEvents` |

실행 시 요약 출력 (n1):

```
[apply_view] csv\aws.5_chain_n1  ->  csv\aws.5_chain_n1_view
  nodes 108 | edges 215 (advances true 154 / false 61) | context 12
  CAN_OBTAIN 1 (exercised 1) | nodeKind {'Credential': 13, 'Asset': 88, 'Identity': 6, 'Workload': 1}
  finding: split-workload 1 / split-identity 1
```

---

## 10. Python ↔ Cypher 대응

| 규칙 | simulate_views.py | enrich_views.cypher |
|---|---|---|
| 노드 종류 | `node_kind()` 25–40 | STEP 1, 86–104행 — 라벨 `:Identity`/`:Credential`/`:Workload`/`:Asset`을 실제로 붙임 |
| advances | `advances()` 43–51 | STEP 2, 147–151행 `SET r.advances = …` |
| IP 집합 | `split_identity()` 안 129–134 | STEP 2b, 161–164행 `SET a.sourceIPs` |
| CAN_OBTAIN | `can_obtain()` 54–86 | STEP 3, 192–210행 `MERGE (a)-[g:CAN_OBTAIN]->(cred)` |
| exercised | apply_view.py 84–86 | STEP 3b, 233–241행 |
| 신원 분열 | `split_identity()` | STEP 4, 257행~ |

미세한 차이: Cypher STEP 3은 `(cred:Credential)`로 라벨을 요구하고 `bindFirstSeen`을 추가로 저장하며, `controlEvents`를 (a, cred, w) 묶음마다 `count(r)`로 센다. Python은 간선마다 1씩 더한다. 표 3에는 이 값이 쓰이지 않는다.

---

## 11. 알아둘 점

1. **`advances`는 표 3 계산에 쓰이지 않는다.** 조사 전략은 `succ()`(성공 ∧ 대상 특정 ∧ 자기 자신 아님)와 OBTAINS로 판단한다. advances의 실제 소비자는 CAN_OBTAIN 합성(과 삭제된 `measure_paths.py`)이다. 발표에서 "전이 규칙"을 설명할 때 조사 전략의 규칙과 섞지 않도록 주의.
2. **뷰의 CAN_OBTAIN 개수를 논문 수치로 인용하면 안 된다.** n2의 11개는 가능성 목록이고, 논문 4.4가 쓴 후보는 원본 근거로 재구성한 1쌍이다 (`results/common_investigation_summary.json`의 `candidate_pairs`: n1 1, n2 1, n3 0, n4 0).
3. **CAN_OBTAIN 방향.** `(공격자 키) → (인스턴스 키)`다. 초기에는 방향이 뒤집혀 보이는 문제가 있었고(timeline.md §2) 제외 규칙 2로 해결됐다.
4. **n3·n4에는 CAN_OBTAIN이 없다.** 두 시나리오 모두 EC2를 거치지 않기 때문이다. 논문 결론의 "워크로드 이동 후보는 관측 발급만으로 확보하지 못한 후속 근거의 조사에 기여하였다"는 n1·n2에 대한 이야기다.

---

## 12. 직접 해보기

```powershell
python ".\scripts\apply_view.py" .\csv\aws.5_chain_n2 $env:TEMP\n2_view
Import-Csv $env:TEMP\n2_view\canobtain.csv | ft dst,exercised,at,controlEvents

# 규칙만 요약 출력 (파일 안 씀)
python ".\scripts\simulate_views.py" .\csv\aws.5_chain_n1
```
