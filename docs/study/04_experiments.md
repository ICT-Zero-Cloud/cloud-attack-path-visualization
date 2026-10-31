# 04. 실험 — 정답 집합, 측정, 그리고 표의 숫자

대상 파일:

- `groundtruth_json/aws.5_chain_n*.common.json` — 정답 집합 (두 실험 공통의 원천)
- `scripts/measure_target_extraction.py` (79줄) — **표 2**
- `scripts/measure_investigation_batch.py` (43줄) → `measure_investigation.py`의 `evaluate()`, `khop()`, `main()` — **표 3**
- `scripts/test_measure_investigation.py` (81줄) — 구현 점검

논문 위치: 4.1 데이터, 4.2 정답 근거의 정의, 4.3 대상 추출 범위의 효과(표 2), 4.4 근거 보존과 검토 대상 선택(표 3)

---

## 0. 한 줄 요약

실험은 두 개다.

| | 표 2 (4.3) | 표 3 (4.4) |
|---|---|---|
| 질문 | 대상 추출 범위를 넓히면 조사에 필요한 자원·접근 근거가 더 확보되는가? | 공통 조사 전략은 필수 근거를 다 보존하면서 볼 이벤트를 얼마나 줄이는가? |
| 비교 | L0(R-전용) vs L3(다중 필드) — **같은 로그, 파서 설정만 다름** | 시간창 검색 vs 공통 조사 전략 — **같은 그래프, 선택 방식만 다름** |
| 입력 | 원본 JSON을 매번 새로 파싱 | `csv/*_view/` |
| 조사 전략 실행 | 안 함 | 함 |
| 결과 | `results/target_extraction/summary.json` | `results/common_investigation_summary.json` |

두 실험 모두 **같은 정답 파일**(`*.common.json`)에서 출발한다.

---

## 1. 데이터 (4.1)

| 사례 | 시나리오 | 레코드 수 | 시간창 | 앵커 |
|---|---|---|---|---|
| n1 | EC2 자격증명 탈취 → 백도어 키 → 로깅 중지 → S3 객체 삭제 | 129 | 07:36:21 ~ 07:53:43 | 최초 SendCommand (`5f835336`) |
| n2 | EC2 자격증명 탈취 → 시크릿 접근 → 스냅샷 공유 → 플로우로그 삭제 | 165 | 05:22:03 ~ 05:44:12 | 최초 SendCommand (`0b5470f4`) |
| n3 | 페더레이션 로그인 → 사용자 자격증명 변경 → 키 사용 → 트레일 삭제 | 138 | 01:26:58 ~ 01:44:42 | GetFederationToken (`cdce6077`) |
| n4 | 역할 위임 → 신뢰정책 변경 → 키 발급 연쇄 → 시크릿 접근 | 140 | 06:07:14 ~ 06:22:04 | UpdateAssumeRolePolicy (`0140e32e`) |

시간창은 사례별 **최초~최후 레코드 전체**다. 그래서 표 3의 "시간창 반환"은 곧 그 사례의 전체 레코드 수다.

로그는 AWS 계정에서 공격 스크립트와 배경 활동(`…_execute_with_noise.sh`)을 함께 돌려 수집했다. **공개 침해 사례가 아니라 저자가 만든 로그**이고 정답도 그 실행 기록으로 정했다 — 논문 4.2 마지막 문장이 이 한계를 먼저 밝힌다.

---

## 2. 정답 파일 구조 — n4를 예로

`groundtruth_json/aws.5_chain_n4.common.json`의 키를 하나씩 보자.

| 키 | 내용 | 채점에서의 역할 |
|---|---|---|
| `investigation_question` | "tier2-admin-role 신뢰정책 변경 이벤트의 발급 계보와 후속 행위를 설명하라" | 문서화 |
| `anchor_event`, `window` | `0140e32e`, 06:07:14~06:22:04 | 전략의 입력 |
| `required_events` (6) | 상류 발급, 앵커, 하류 발급 2개, 시크릿 읽기 2개 | 분자·분모 |
| `required_connections` (6) | `(관계 종류, 출발, 도착, eventID)` 튜플 | 연결 보존의 분자·분모 |
| `context_events` (2) | CreateUser, AttachUserPolicy — "있으면 유용, 필수 아님" | 반환돼도 **감점 안 함** |
| `context_connections` (6) | 동반 간선들 (AssumeRole의 키→역할 등) | 반환돼도 감점 안 함 |
| `entry_unlinkable` (1) | GetParameter `/app/prod/deploy-key` — 로그에 키 값이 없어 어떤 그래프도 Cred1로 못 이음 | 반환 안 돼도 감점 안 함 |
| `temporal_constraints` (5) | `[선행 eventID, 후행 eventID]` 쌍 | 시간순 검사 |
| `same_role_checks` (1) | 정책 변경 대상 역할 = 위임받은 역할인가 | 설명 완성 조건 |
| `negative_controls_natural` | 공격자와 **같은 IP**를 쓰는 무관 키 `AKIA…47FWDD4TB`의 이벤트 8개 | 문서화 (같은 IP ≠ 같은 사건) |
| `notes` | "정책변경→위임 연결은 동일 역할에 대한 시간 선행까지만 정답(인과 아님)" 등 | 해석 경계 |
| `sources` | 시나리오 설명 md, 실행 셸 스크립트, 원본 로그 | 정답의 근거 |

**정답은 어떻게 정했나** (`_comment` 필드): "원본 로그·실행 기록 기준으로 버킷 고정(질의 결과에 맞추지 않음)". 공격 스크립트가 실행한 단계와 알려진 키·대상으로 먼저 정하고, eventID·API·시각을 원본 CloudTrail과 대조했다. 전략을 돌린 결과를 보고 정답을 조정하지 않았다. 논문 4.2의 "정답 집합은 질의 결과 선택에 사용하지 않는다"가 이것이다.

사례별 필수 근거 구성:

| 사례 | 필수 | 구성 |
|---|---|---|
| n1 | 55 | SendCommand 1, CreateAccessKey 1, StopLogging 1, DeleteObjects 1, **DeleteObject 51** |
| n2 | 24 | GetSecretValue 20, SendCommand 2, ModifySnapshotAttribute 1, DeleteFlowLogs 1 |
| n3 | 9 | GetFederationToken, GetSigninToken, ConsoleLogin, CreateLoginProfile, UpdateLoginProfile, CreateAccessKey, GetCallerIdentity, ListUsers, DeleteTrail (각 1) |
| n4 | 6 | 위 표 |

n1의 분모가 큰 건 삭제 레코드가 51개이기 때문이다. DeleteObjects 1건과 DeleteObject 51건은 원본 레코드 수 그대로다.

---

## 3. 표 2 — 대상 추출 범위의 효과 (`measure_target_extraction.py`)

### 3.1 정답을 먼저 얼린다 (29–44행)

```python
for i in 1..4:
    gt = *.common.json
    raw = 원본 로그 {eventID: 레코드}
    access = {(src, dst, eid) for (rel, src, dst, eid) in gt['required_connections']
              if rel != 'OBTAINS' and dst.startswith('arn:aws:')}            # 36–37
    for (src, dst, eid) in access:
        assert eid in raw                                                    # 원본에 있는 레코드인가
        assert raw[eid]['userIdentity']['accessKeyId'] == src                # 호출 키가 맞는가
    frozen.append(targets=dst 집합, accesses=access, GT·원본의 SHA-256)
→ results/target_extraction/fixed_groundtruth.json
```

- 4.4의 정답에서 **OBTAINS**(키 → 키, 대상 추출과 무관)와 **ARN이 아닌 대상**(서비스 노드)을 빼서 "구체적 자원 접근"만 남긴다. 논문 4.3의 "OBTAINS를 제외한 구체적 ARN 대상 접근(IAM 사용자·역할 포함, 서비스 대표 노드 제외)"이 36–37행이다.
- 파싱하기 **전에** 정답을 고정하고 해시를 남긴다. L0·L3 결과를 보고 정답을 바꿀 수 없게 하기 위해서다.
- 그래서 같은 사례라도 표 2와 표 3의 분모가 다르다 (n3: 표 2 접근 3개, 표 3 연결 9개).

### 3.2 두 번 파싱해서 센다 (46–69행)

```python
for level in (0, 3):
    parser_node3_v2.py 원본 -o n{i}_L{level} --extract-level {level}
    nodes   = {노드 id}
    triples = {(src, dst, eventID) for 간선}
    자원 식별 = |정답 대상 ∩ nodes|                 # 노드가 존재하는가
    접근 근거 = |정답 접근 ∩ triples|               # (호출 키, 대상, eventID) 간선이 존재하는가
```

**두 지표를 따로 세는 이유:** 노드는 다른 레코드 하나만 그 ARN을 언급해도 생긴다. 하지만 "누가 언제 그 자원에 무엇을 했나"는 **그 레코드 자신의** 간선에만 있다. 01 문서 §8.4의 n4 사례 — 역할 노드는 있는데 신뢰정책 변경 간선이 없는 상태 — 가 자원 3/3, 접근 2/3이 되는 이유다.

### 3.3 결과

| 사례 | 자원 L0 → L3 | 접근 L0 → L3 | L0에서 빠졌다가 L3가 되찾은 것 (API · refPath) |
|---|---|---|---|
| n1 | 2/3 → 3/3 | 52/54 → 54/54 | SendCommand · `instanceIds[0]`, StopLogging · `name` |
| n2 | 21/23 → 23/23 | 20/24 → 24/24 | SendCommand · `instanceIds[0]` ×2, ModifySnapshotAttribute · `snapshotId`, DeleteFlowLogs · `DeleteFlowLogsRequest.FlowLogId.content` |
| n3 | 1/3 → 3/3 | 0/3 → 3/3 | CreateLoginProfile · `userName`, UpdateLoginProfile · `userName`, DeleteTrail · `name` |
| n4 | 3/3 → 3/3 | 2/3 → 3/3 | UpdateAssumeRolePolicy · `roleName` |
| **합계** | **27/32 → 32/32** | **74/84 → 84/84** | 10건, 전부 `requestParameters` |

`raw_field_verification.json`: 되찾은 10건 모두 "해당 레코드에 `resources[]`가 없고, refPath가 가리키는 원본 값이 정답 대상 id 안에 들어 있음"을 확인.

**응답 필드(`responseElements`)의 기여는 따로 측정하지 않았다.** 되찾은 10건이 전부 요청 필드에서 나왔기 때문에 응답 필드를 끈 구성은 돌리지 않았다. 논문 결론의 한계 문단에 적혀 있다.

---

## 4. 표 3 — 공통 조사 전략 (`measure_investigation_batch.py` → `measure_investigation.py`)

### 4.1 배치가 하는 일 (batch 11–37행)

```python
for i in 1..4:
    measure_investigation.py --gt *.common.json --csv csv/aws.5_chain_n{i}_view --mode both
                             --output results/common_investigation_n{i}.json
    selected = strategies['proposed_inferred']     # ← 표 3의 "제안" = 후보 포함 모드
    baseline = strategies['time_window']
    observed = strategies['proposed']              # ← 본문의 "관측 발급만" 비교
→ results/common_investigation_summary.json
```

논문 4.4 "본 실험에서는 CAN_OBTAIN 후보를 포함하는 모드로 고정하였으며"가 20행이다.

### 4.2 비교 전략 (`main()` 203–215행)

| 이름 | 무엇 | 논문 |
|---|---|---|
| `time_window` | 시간창 안 모든 간선 | 기준선 ("시간창 반환") |
| `proposed` | 관측 OBTAINS만 따라가는 전략 | 4.4 마지막 문단 |
| `proposed_inferred` | 후보 포함 전략 | **표 3의 "제안 반환"** |
| `k1`, `k2`, `k3` (+`_inferred`) | 앵커 키에서 방향 무시 k홉 이웃 (`khop()` 125–143행) | `[논문 미사용]` |

### 4.3 채점 — `evaluate()` (152–178행)

```python
events = {반환 행의 eventID}
conns  = {(rel_cat, src, dst, eventID) for 반환 행}

def score(returned, required, allowed):
    hit   = |returned ∩ required|
    false = |returned − required − allowed|        # 필수도 문맥도 아닌 것 = 무관
    precision = hit / (hit + false)                # 문맥은 정밀도 분모에서 뺀다
    recall    = hit / |required|

ep = score(events, 필수 이벤트, 문맥 이벤트 ∪ entry_unlinkable)
cp = score(conns,  필수 연결,  문맥 연결)

checks = {각 temporal_constraint: 선행 시각 ≤ 후행 시각,
          각 same_role_check:     두 연결의 (출발, 도착)이 같고 둘 다 반환됨}

complete = (ep.recall == 1) and (cp.recall == 1) and all(checks)       # "설명 완성"
```

그리고 `main()` 226행:

```python
reduction_vs_window = 1 − (반환 이벤트 수 / 시간창 이벤트 수)   if complete else None
```

**완성되지 않으면 축소율을 보고하지 않는다.** 근거를 놓친 축소는 성과가 아니다. n3의 `—`가 이것이다.

**연결 보존만 표에 싣는 이유:** 네 사례 모두 필수 이벤트 하나당 필수 연결이 정확히 하나씩 대응한다 (n1~n4 GT로 확인: 이벤트와 연결이 55·24·9·6개로 1:1). 연결 보존은 eventID에 더해 출발·도착까지 맞아야 하므로 **연결 보존 = 1이면 이벤트 보존 = 1이 자동으로 따라온다.** 두 열이 네 사례 모두 같은 값이라 한 열로 줄였다.

### 4.4 결과 전체

| 사례 | 연결 보존 | 시간창 반환 | 제안 반환 | = 필수 + 문맥 + 무관 | 축소율 | 설명 완성 |
|---|---|---|---|---|---|---|
| n1 | 55/55 | 129 | 66 | 55 + 7 + 4 | 48.8% | ✔ |
| n2 | 24/24 | 165 | 31 | 24 + 2 + 5 | 81.2% | ✔ |
| n3 | 5/9 | 138 | 5 | 5 + 0 + 0 | — | ✘ |
| n4 | 6/6 | 140 | 8 | 6 + 2 + 0 | 94.3% | ✔ |

(구성 출처: `results/common_investigation_n*.json` → `strategies.proposed_inferred`의 `events.hits`, `context_events`, `events.false`)

### 4.5 관측 모드 vs 후보 모드 (`observed_*` 필드)

| 사례 | 관측 발급만 | 후보 포함 | 채택된 후보 쌍 |
|---|---|---|---|
| n1 | 1/55 (반환 4) | 55/55 (반환 66) | 1 |
| n2 | 2/24 (반환 4) | 24/24 (반환 31) | 1 |
| n3 | 5/9 | 5/9 | 0 |
| n4 | 6/6 | 6/6 | 0 |

n1·n2는 EC2 탈취 시나리오라 "공격자 키 → 인스턴스 키" 사이에 로그상 발급이 없다. 후보 한 쌍이 그 다리를 놓자 뒤쪽의 관측 발급과 후속 행위가 전부 따라온다 (03 문서 §4).

### 4.6 n3가 실패한 이유

필수 9개 중 빠진 4개:

| API | 간선 | 왜 빠졌나 |
|---|---|---|
| GetSigninToken | `ASIA…43A27DRQF → 자기 자신` (OBTAINS), `→ signin.amazonaws.com` | 자기 자신으로 가는 간선 + 서비스 대상 |
| ConsoleLogin | `→ signin.amazonaws.com` | 서비스 대상 |
| GetCallerIdentity | `→ sts.amazonaws.com` | 서비스 대상 |
| ListUsers | `→ iam.amazonaws.com` | 서비스 대상 |

전부 `succ()`(03 문서 §2)에서 걸린다. 넷 다 **경로의 끝**이라, 서비스 노드를 "순회"하지 않으면서 "종단"으로만 허용하면 회수할 수 있다. 현재 규칙은 순회와 종단을 같은 조건으로 걸러 필요 이상으로 엄격하다.

---

## 5. 축소율을 어떻게 읽어야 하나

| 사례 | 필수 / 전체 | 1 − 필수/전체 | 축소율 | 차이 |
|---|---|---|---|---|
| n1 | 55 / 129 = 42.6% | 57.4% | 48.8% | 8.5%p |
| n2 | 24 / 165 = 14.5% | 85.5% | 81.2% | 4.2%p |
| n4 | 6 / 140 = 4.3% | 95.7% | 94.3% | 1.4%p |

**축소율은 `1 − 필수/전체`에서 몇 %p밖에 안 떨어져 있다.** 즉 축소율의 대부분은 "공격 경로가 로그에서 차지하는 비중"이 정하고, 전략이 기여하는 건 오른쪽 몇 %p다. n4가 94.3%로 가장 높은 건 전략이 더 잘해서가 아니라 필수 근거가 6개뿐이어서다. 배경 활동이 많은 로그일수록 축소율은 저절로 커진다. 논문도 "축소율은 시간창의 폭과 배경 활동량에 영향을 받으므로 절대 반환량과 함께 해석한다"고 적었다.

**로그의 노이즈 양과 무관하게 전략 자체를 보여주는 숫자는 "무관" 열이다** — n1 4건, n2 5건, n4 0건. 필요한 것 말고 딸려온 게 한 자릿수라는 뜻이다. 이 숫자는 결과 파일에 있지만 논문 본문에는 n4 구성만 적혀 있다.

---

## 6. k홉 비교 `[논문 미사용]`

`khop()`은 앵커 키에서 **방향과 종류를 무시하고** k번 이웃을 넓힌다. 결과 파일에는 있지만 논문에서는 뺐다.

| 사례 | 제안(후보 포함) | 설명이 완성되는 가장 작은 k홉 |
|---|---|---|
| n1 | 66 (무관 4) | k3_inferred: 78 (무관 11) |
| n2 | 31 (무관 5) | k1_inferred: 35 (무관 3) |
| n3 | 5 — 미완성 | k2: 63 (무관 53) |
| n4 | 8 (무관 0) | k3: 13 (무관 5) |

완성된 사례에서는 제안 전략의 반환이 가장 작은 완성 k홉보다 항상 작다. 다만 n2에서는 무관 건수가 k1_inferred(3)가 제안(5)보다 적다. n3은 k2가 서비스 노드를 거쳐 빠진 4개를 되찾는다 — 대신 무관 53개가 딸려온다. §4.6에서 말한 "서비스 노드를 순회하면 허브가 된다"의 실측이다.

---

## 7. 구현 점검 — `test_measure_investigation.py` (6개)

실험이 아니라 **채점 코드가 틀린 걸 틀렸다고 판정하는지** 확인하는 테스트다. n4 데이터와 `aws.5_chain_n4.investigation.json`(common.json 이전 판 GT)을 쓴다.

| 테스트 | 무엇을 조작 | 기대 |
|---|---|---|
| `test_wrong_endpoint_is_false_positive` | 필수 연결 하나의 도착을 가짜 키로 바꿈 | 무관 1, 적중 5, 미완성 |
| `test_reversed_time_is_incomplete` | 시크릿 읽기 시각을 발급 이전으로 바꿈 | 미완성 (시간순 위반) |
| `test_use_before_issuance_is_excluded` | 발급 이전 시각의 가짜 사용 레코드를 추가 | 전략이 반환하지 않음 |
| `test_wrong_role_is_incomplete` | 위임 대상 역할 이름을 바꿈 | same_role 검사 실패 |
| `test_duplicate_rows_do_not_inflate_counts` | 반환 행을 두 번 넣음 | 채점 결과 동일 |
| `test_handoff_modes_and_witnesses` | 합성 데이터로 후보 조건 검사 | 같은 출처·제어 이후 조건이 동작 |

2026-09-30 실행: `Ran 6 tests … OK`.

---

## 8. 논문 3.3의 "29개 중 24개" 재현

저장된 스크립트가 없는 수치라 여기 적어둔다.

```python
import csv
E = list(csv.DictReader(open('csv/aws.5_chain_n4/edges.csv', encoding='utf-8')))
subjects = {r['src'] for r in E if r['src'].startswith('ASIA')}                         # 주체로 등장한 임시 키
issued   = {r['dst'] for r in E if r['rel'] == 'OBTAINS' and r['outcome'] == 'SUCCESS'}  # 발급이 관측된 키
print(len(subjects), len(subjects - issued))                                             # 29 24
```

24개를 소속(ISSUES)별로 보면 계정 root 19개(콘솔 세션), `AWSServiceRoleForResourceExplorer` 2개(서비스 연결 역할 세션), `apt-chain-e-admin` 2개와 `ci-readonly` 1개(시크릿·파라미터를 읽을 때 KMS가 대신 호출한 `Decrypt` 세션)다. 모두 `context.csv`에 ISSUES(소속)는 있고 OBTAINS(발급)만 없다 — 01 문서 §5.1의 "발급이 아니라 사용 흔적이 근거"라서 가능한 일이다.

---

## 9. 숫자의 출처 한눈에

| 논문의 숫자 | 파일 | 필드 |
|---|---|---|
| 표 2 자원 L0/L3 | `results/target_extraction/summary.json` | `results[].levels["0"|"3"].target_hits` / `required_targets` |
| 표 2 접근 L0/L3 | 〃 | `access_hits` / `required_accesses` |
| 표 3 연결 보존 | `results/common_investigation_summary.json` | `connection_hits` / `required_connections` |
| 표 3 시간창 반환 | 〃 | `window_events` |
| 표 3 제안 반환 | 〃 | `proposed_events` |
| 표 3 축소율 | 〃 | `reduction` |
| 4.4 관측 모드 1/55, 2/24 | 〃 | `observed_connection_hits` |
| 4.4 n4 "필수 6개와 문맥 2개" | `results/common_investigation_n4.json` | `strategies.proposed_inferred.events.hits`, `.context_events` |
| 3.3 "29개 중 24개" | `csv/aws.5_chain_n4/edges.csv` | §8 스크립트 |
| 4.1 레코드 수 129/165/138/140 | 원본 JSON | `len(Records)` |

---

## 10. 알아둘 점

1. **표 2와 표 3은 서로 다른 그래프를 본다.** 표 2는 `results/target_extraction/n*_L3/`(매번 새로 파싱), 표 3은 `csv/*_view/`. 다만 n4에서 확인한 결과 `n4_L3`과 `csv/aws.5_chain_n4`는 세 파일이 완전히 같다 (같은 파서, 같은 원본).
2. **정답 파일이 두 종류 있다.** `*.common.json`(n1~n4, 표 2·3의 원천)과 `aws.5_chain_n4.investigation.json`(n4 단독 실험 시절의 판, 지금은 테스트에서만 사용).
3. **k홉 결과는 결과 파일에 남아 있다.** 발표에서 "다른 탐색 방식과 비교했나"라는 질문이 오면 §6이 근거다. 논문에 싣지 않았으니 수치를 말할 때는 "결과 파일 기준"이라고 한정할 것.
4. **"무관" 판정은 문맥 목록에 의존한다.** GT의 `context_events`에 없으면 전부 무관으로 센다. n1의 무관 4건, n2의 5건이 실제로 무관한지는 개별 확인하지 않았다.
