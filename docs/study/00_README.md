# 발표용 공부자료 — 전체 지도

논문: 「자격증명 흐름과 자원 접근을 연결하는 CloudTrail 침해 조사 그래프」 (CISC-W'26, 제출번호 96)
코드 위치: `<repo>`
작성 기준일: 2026-09-30 (모든 줄번호·수치는 이 날짜의 파일로 다시 실행해 확인함)

---

## 1. 파이프라인 한 장

```
../stratus-red-team/log_json/aws.5_chain_n4.json        원본 CloudTrail (레코드 140개)
        │
        │  [01] parser_node3_v2.py
        ▼
csv/aws.5_chain_n4/  nodes.csv · edges.csv · context.csv     기반 그래프 (해석 없음)
        │
        │  [02] scripts/apply_view.py  (규칙은 simulate_views.py)
        ▼
csv/aws.5_chain_n4_view/  + nodeKind · advances · canobtain.csv   뷰 그래프 (해석 얹음)
        │
        │  [03] scripts/measure_investigation.py  의 proposed()
        ▼
조사 결과 = 이벤트 집합 + 연결 튜플 집합
        │
        │  [04] measure_investigation_batch.py / measure_target_extraction.py
        ▼
results/…json  →  논문 표 2 · 표 3
```

| 문서 | 다루는 코드 | 논문 위치 | 이 문서를 읽고 답할 수 있어야 하는 것 |
|---|---|---|---|
| `01_parser.md` | `parser_node3_v2.py` | 3.1, 3.2, 표 1 | 레코드 한 건이 어떤 노드·간선이 되는가. 왜 주체 id가 ARN이 아니라 accessKeyId인가. R-전용과 다중 필드의 차이가 코드에서 어디인가 |
| `02_postprocess.md` | `simulate_views.py`, `apply_view.py`, `enrich_views.cypher` | 3.3 | advances가 무엇이고 어디에 쓰이는가. CAN_OBTAIN은 어떤 두 사실을 곱해 만드는가. n2에서 후보 11개가 왜 1개로 줄어드는가 |
| `03_queries.md` | `measure_investigation.py`의 전략 함수, `queries/investigation/*.cypher` | 3.4, 4.4의 절차 | 시작 이벤트 하나에서 무엇을 어떤 순서로 모으는가. n4에서 8개 이벤트가 정확히 어떻게 나오는가. Python과 Cypher는 무엇이 같고 다른가 |
| `04_experiments.md` | `measure_target_extraction.py`, `measure_investigation_batch.py`, `evaluate()`, GT 파일 | 4.1~4.4, 표 2·표 3 | 정답 집합은 어떻게 만들고 무엇을 세는가. 표의 숫자 하나하나가 어느 파일의 어느 필드인가. 축소율을 어떻게 해석해야 하는가 |

각 문서 끝에 **알아둘 점**이 있다. 코드를 직접 돌려보다 발견한, 논문에는 없지만 발표 전에 알고 있어야 할 동작들이다.

`[논문 미사용]` 태그는 코드에는 있지만 논문 수치를 만드는 데 쓰이지 않은 기능이다.

---

## 2. 관통 예시 — n4 (역할 위임과 키 발급 연쇄)

모든 문서가 같은 n4 이벤트를 따라간다. 키가 길어서 별명을 붙인다.

| 별명 | accessKeyId | 소속 신원 | 어떻게 생겼나 |
|---|---|---|---|
| **Cred1** | `AKIAEXAMPLE0SEAZXEHZ` | `user/deploy-user` | 공격자가 SSM 파라미터 `/app/prod/deploy-key`에서 읽어낸 장기 키 (로그에 키 값이 없어 그래프로 못 이음) |
| **Cred2** | `ASIAEXAMPLE0377HGFVC` | `role/tier1-app-role` | Cred1이 AssumeRole로 받은 임시 키 |
| **Cred3** | `ASIAEXAMPLE07QBHVZLC` | `role/tier2-admin-role` | Cred2가 AssumeRole로 받은 임시 키 |
| **Cred4** | `AKIAEXAMPLE0ZCUWMCHR` | `user/apt-chain-e-admin` | Cred3이 CreateAccessKey로 만든 백도어 장기 키 |

```
06:13:17  (다른 키) GetParameter /app/prod/deploy-key          ← 진입점. 여기서 Cred1이 새어나감 (그래프에 연결 없음)
06:13:18  Cred1  AssumeRole tier1-app-role   → Cred2 발급       f216ac9b
06:13:19  Cred2  UpdateAssumeRolePolicy tier2-admin-role        0140e32e  ★ 조사 시작점(앵커)
06:13:31  Cred2  AssumeRole tier2-admin-role → Cred3 발급       792f3408
06:13:32  Cred3  CreateUser apt-chain-e-admin                   c0f74667
06:13:34  Cred3  AttachUserPolicy AdministratorAccess           07281081
06:13:35  Cred3  CreateAccessKey apt-chain-e-admin → Cred4 발급 4b056976
06:13:47  Cred4  GetSecretValue prod/db-master                  e7319337
06:13:48  Cred4  GetSecretValue prod/api-key                    9fa6b1c5
```

공격자가 tier1 역할로 tier2 역할의 신뢰정책을 고쳐 자기에게 위임을 허락하고, tier2로 넘어가 백도어 사용자와 키를 만든 뒤 그 키로 시크릿을 읽는 흐름이다. 전체 로그 140개 중 공격 경로는 9개뿐이고 나머지는 콘솔 조회 같은 배경 활동이다.

**n4로 못 보는 것 하나:** n4에는 `RUNS_ON`이 0건이라 CAN_OBTAIN 후보가 생기지 않는다. 그래서 02·03 문서의 CAN_OBTAIN 부분만은 **n1**(EC2 인스턴스 자격증명 탈취)을 보조 예시로 쓴다.

---

## 3. 논문 용어 ↔ 코드 용어

| 논문 | 코드·CSV |
|---|---|
| 자격증명 | `Actor` 라벨, `kind` = `LongTermKey`(AKIA) / `TempKey`(ASIA). 뷰에서 `nodeKind=Credential` |
| 신원 | IAM user/role/policy ARN 노드. 뷰에서 `nodeKind=Identity` |
| 워크로드 | `RUNS_ON`의 도착 노드 (EC2 instance 등). 뷰에서 `nodeKind=Workload` |
| 자원 | 나머지 대상 노드. 뷰에서 `nodeKind=Asset` |
| 이벤트 간선(BASE_EVENT) | `edges.csv`의 한 행. `rel` = `ACCESS` / `ASSUME_ROLE` / `OBTAINS` / (`PRODUCES`) |
| 문맥 관계 | `context.csv`의 한 행. `rel` = `ISSUES` / `RUNS_ON` |
| 추론 관계 CAN_OBTAIN | 뷰의 `canobtain.csv` (+ 조사 시 `candidate_handoffs()`가 원본 근거로 재구성) |
| R-전용 / 다중 필드 | `--extract-level 0` / `--extract-level 3` |
| 공통 조사 전략(제안 전략) | `measure_investigation.py`의 `proposed()` |
| 관측 발급만 / 후보 포함 모드 | `strategies['proposed']` / `strategies['proposed_inferred']` |
| 연결 보존 | `connections.hits / connections.required` |
| 시간창 반환 / 제안 반환 | `window_events` / `proposed_events` (`results/common_investigation_summary.json`) |

---

## 4. 전부 다시 돌려보기

PowerShell, `ct_graph_v2` 폴더에서. 각 단계의 기대 출력은 해당 문서에 있다.

```powershell
# [01] 파싱 (n1~n4 각각)
python parser_node3_v2.py ..\stratus-red-team\log_json\aws.5_chain_n4.json -o .\csv\aws.5_chain_n4

# [02] 뷰 만들기
python ".\scripts\apply_view.py" .\csv\aws.5_chain_n4

# [03] 한 사례 조사 (관측 + 후보 두 모드)
python ".\scripts\measure_investigation.py" --gt .\groundtruth_json\aws.5_chain_n4.common.json --csv .\csv\aws.5_chain_n4_view --mode both

# [04] 논문 표 3 (n1~n4 일괄) / 표 2
python ".\scripts\measure_investigation_batch.py"
python ".\scripts\measure_target_extraction.py"

# 구현 점검 (6개 테스트)
cd ".\scripts"; python test_measure_investigation.py
```

2026-09-30에 n4를 다시 파싱한 결과는 저장된 `csv/aws.5_chain_n4/`와 세 파일 모두 한 글자도 다르지 않았고, 파서의 SHA-256 앞자리(`23cb488ce5b181df`)도 표 2 결과 파일에 기록된 값과 같다. 즉 지금 폴더의 코드로 논문 수치가 그대로 재현된다.

---

## 5. 같이 보면 좋은 기존 문서

| 파일 | 내용 |
|---|---|
| `3-node-v2.md` | 기반 모델 정의서 (01과 짝) |
| `enrich.md` | 뷰 계층 정의서 (02와 짝) |
| `query.md` | 조사 질의 설계, 특히 §13 "Python과 Cypher의 관계" (03과 짝) |
| `measure_investigation_design.md`, `experiment_measurement.md` | 4.4 실험 설계와 결과 원본 기록 (04와 짝) |
| `timeline.md` | 모델이 어떤 피드백으로 바뀌어 왔는가 |
| `PAPER_FILE_MAP.md` | 폴더의 어떤 파일이 논문에 쓰였는가 |
