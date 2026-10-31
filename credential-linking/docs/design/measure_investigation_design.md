# 공통 조사 질의 실험 설계 — n1~n4

작성·실행: 2026-09-14. 기존 n4 중심 설계와 단일 시간창 결과를 이 설계로 대체한다.

## 1. 목적과 비교 조건

**자격증명 관계를 이용해 필요한 조사 근거를 보존하면서 검토 대상 이벤트를 줄인다.**

같은 공통 탐색 코드에서 관측 발급만 사용하는 모드와 워크로드 이동 후보를 포함하는 모드를 실행한다. 주 결과 표는 네 사례 모두 **후보 포함 모드**로 고정한다. 결과가 좋은 모드를 사례별로 골라 쓰지 않는다. 이동 후보가 없는 n3·n4도 같은 모드를 실행한다.

측정은 `measure_investigation.py`의 Python 구현을 CSV에서 실행한 결과다. 공통 Cypher는 `queries/investigation/07_common_investigation.cypher`이며, 이 표를 Neo4j 실행 성능으로 해석하지 않는다.

## 2. 공통 입력 설정

- 그래프: `csv/aws.5_chain_n{1..4}_view`의 nodes/edges/context/canobtain CSV.
- 시간창: **시나리오별 수집 로그의 최초 eventTime~최후 eventTime 전체**. 결과에 맞춰 구간을 줄이지 않는다.
- 앵커: 기록된 조사 시작 사건 1개. n1·n2는 최초 SendCommand, n3는 GetFederationToken, n4는 기존 정책변경 사건이다.
- 계정·대상 자원 추가 제한 없음. 후속 API 목록 제한 없음. 최대 6홉, 동일 키 반복 금지.
- 후보 옵션: 동일 워크로드 RUNS_ON, 성공한 SendCommand/SendSSHPublicKey, 그 이후 대상 키 사용과 동일 출처를 요구한다. 후보 집계의 exercised 플래그만으로 채택하지 않는다.

| 사례 | 시간창(UTC, 양끝 포함) | 앵커 |
| :--- | :--- | :--- |
| n1 | 2026-09-01T07:36:21Z ~ 2026-09-01T07:53:43Z | `5f835336-8de6-4b53-acdf-2b9398d6e127` |
| n2 | 2026-09-07T05:22:03Z ~ 2026-09-07T05:44:12Z | `0b5470f4-d1fc-44bf-89f0-2495a1394168` |
| n3 | 2026-09-08T01:26:58Z ~ 2026-09-08T01:44:42Z | `cdce6077-82bf-409c-9226-92aa39dffc23` |
| n4 | 2026-09-10T06:07:14Z ~ 2026-09-10T06:22:04Z | `0140e32e-f328-4fc5-8984-63326b68a8df` |

시간창은 쿼리 소요 시간이 아니라 조회할 로그의 발생 시각 범위다. 이번 표에서 시간창 반환량은 각 CSV의 서로 다른 eventID 전체 개수다. n4도 전체 140개를 분모로 사용하므로, 이전의 1분 시간창 28개와 구분한다.

## 3. 정답 근거를 확정하는 과정

`stratus-red-team/detail_md/aws.5_chain_n*.md`의 공격 타임라인, `shell code/aws.5_chain_n*_execute_with_noise.sh`의 실행 단계, 기존 키·자원 GT를 확인한다. 그 단계의 실제 eventID·API·시각은 `log_json/aws.5_chain_n*.json`과 대조하고, CSV의 호출 키·대상·관계를 정답 연결로 적는다. 이번에 추가한 GT는 로그 재구성에 따른 조사 정답이며 결과 선택 함수에는 전달하지 않는다.

정답 파일은 `groundtruth_json/aws.5_chain_n{1..4}.common.json`이다. 각 파일에 필수/문맥 이벤트, 정확한 연결 튜플, 시간순 조건, 출처를 저장한다.

| 사례 | 조사 질문과 필수 이벤트 | 필수 개수 |
| :--- | :--- | ---: |
| n1 | SendCommand 1건 → CreateAccessKey 1건 → StopLogging 1건 및 DeleteObjects 1건·DeleteObject 51건 | 55 |
| n2 | SendCommand 2건과 GetSecretValue 20건, ModifySnapshotAttribute 1건, DeleteFlowLogs 1건 | 24 |
| n3 | GetFederationToken·GetSigninToken·ConsoleLogin·CreateLoginProfile·UpdateLoginProfile·CreateAccessKey·발급 키의 GetCallerIdentity·ListUsers·DeleteTrail | 9 |
| n4 | 상류 AssumeRole·신뢰정책 변경·후속 AssumeRole·CreateAccessKey·GetSecretValue 2건 | 6 |

필수 연결은 각 필수 이벤트의 핵심 원본 연결을 지정한다. SendCommand는 호출 키→인스턴스, 발급은 호출 키→발급 키, 영향 행위는 호출 키→대상 자원이다. n3의 콘솔·신원 조회는 해당 키→서비스 연결도 필수로 둔다. 현재 질의가 반환하지 않는다는 이유로 이 항목을 정답에서 빼지 않는다.

**표의 연결 보존은 원본 이벤트 근거 연결의 보존이다.** CAN_OBTAIN 후보 자체를 확정된 발급 연결로 합산하지 않는다. 후보 개체쌍과 제어·사용 증거는 별도 저장한다. 따라서 두 원본 근거의 존재와 후보 가설의 정확성을 같은 지표로 취급하지 않는다.

문맥은 기록된 정찰, 발급 준비(CreateUser·AttachUserPolicy), 명령 결과 조회와 각 필수 이벤트의 부가 대상 연결 등이다. n1~n3의 정찰/명령 조회 문맥은 알려진 실행 키와 공격 실행 출처에 속하는 API로 정했고, 그 조건으로 얻은 정확한 ID·튜플을 고정했다. n4는 앞서 확인한 문맥 정의를 유지한다.

## 4. 질의를 실행해 반환 집합을 만드는 과정

1. CSV를 읽고 공통 시간 범위 안의 행을 선택한다. 이 행을 모두 반환하는 것이 시간창 검색이다.
2. 앵커 호출 키에서 성공한 OBTAINS를 역방향으로 따라 상류 발급 근거를 모은다. 상류는 발급 시각이 앵커보다 늦지 않아야 한다.
3. 하류는 앵커 이후의 발급을 시간순으로 따라간다. 각 키의 도달 시각 이후 성공한 대상 특정 행위를 수집한다.
4. 후보 포함 모드는 제어 키→워크로드←RUNS_ON 대상 키를 확인하고, 제어 이후 동일 출처의 키 사용을 찾아 이동 후보로 연결한다. 제어 시각과 사용 시각을 함께 보존하고 다음 홉은 사용 시각 이후에만 허용한다.
5. 선택한 후보의 원본 제어·사용 행을 반환 근거에 포함한다. 가상 후보를 새 eventID로 만들지 않는다. 발급 이벤트의 역할·사용자 대상도 함께 보존한다.
6. 반환 원본 행을 eventID로 중복 제거해 이벤트 수를 센다. 연결은 `(관계종류, 출발 ID, 도착 ID, eventID)`로 중복 제거한다. 관계종류는 OBTAINS/CHANGE/USE이다.

공통 탐색 규칙에 시나리오별 API 순서를 추가하지 않는다. 후보 제어 API는 동작 유형에 대한 공통 설정이며, 필수 API 목록은 탐색이 끝난 뒤 평가할 때만 사용한다.

## 5. 정답 대조와 축소율 계산

- 필수 이벤트 보존 = 반환한 필수 eventID 수 / GT의 필수 이벤트 수.
- 필수 연결 보존 = 반환한 정확한 필수 연결 튜플 수 / GT의 필수 연결 수.
- 설명 완성 = 필수 이벤트·연결 전체 포함 + GT에 명시한 시간순 조건 충족 + n4의 동일 역할 조건 충족.
- 축소율 = `(시간창 반환량 − 제안 반환량) / 시간창 반환량 × 100`.
- 시간창과 제안 결과가 모두 설명 완성을 충족할 때만 축소율을 성과로 보고한다. 누락이 있으면 ‘— (필수 누락)’로 표시한다.

예: n1에서 시간창은 129개를 반환하고 제안은 66개를 반환한다. 필수 이벤트·연결이 각각 55/55이고 설명이 완성되므로 `(129−66)/129×100=48.8%`다. n3는 반환량이 5개로 작아도 필수 4개가 빠지므로 축소 성과로 보고하지 않는다.

부가 지표는 이벤트·연결 각각의 문맥 제외 P/R/F1이다. P=필수 적중/(필수 적중+오답), R=필수 적중/전체 필수이며 허용 문맥은 분모에서 제외하고 포함량을 따로 저장한다. 주 표에서는 이해하기 쉬운 근거 보존과 반환량을 사용한다.

k홉 비교도 실행 결과 JSON에 남긴다. 관측 모드의 k1~k3는 BASE_EVENT 양방향 탐색이며, 후보 모드의 k1_inferred~k3_inferred는 제안 모드와 같은 후보 연결을 탐색한다. 후보가 선택되면 원본 제어·사용 증거를 반환량에 포함한다.

## 6. 실행·재현

ct_graph_v2 디렉터리에서 실행한다.

```powershell
python -X utf8 "scripts/measure_investigation_batch.py"
python -X utf8 "scripts/test_measure_investigation.py"
```

배치 스크립트는 고정한 네 GT에 같은 `--mode both` 설정을 적용한다. 개별 실행:

```powershell
python -X utf8 "scripts/measure_investigation.py" --gt groundtruth_json/aws.5_chain_n1.common.json --csv csv/aws.5_chain_n1_view --mode both --output results/common_investigation_n1.json
```

- 개별 결과: `results/common_investigation_n1.json`~`common_investigation_n4.json`.
- 집계: `results/common_investigation_summary.json`.
- `strategies.proposed`: 관측 발급 모드, `strategies.proposed_inferred`: 후보 포함 모드.
- `event_ids`·`connection_tuples`: 실제 반환 근거, `checks`: 시간순 검사, `complete`: 설명 완성.
- `inferred_handoffs`: 후보의 출발·도착 키, 워크로드, 제어·사용 eventID. 후보 정답률은 원본 연결 지표와 별개다.

## 7. 결과 보고 원칙

네 사례를 모두 표에 남긴다. n1의 삭제 52건과 n2의 시크릿 접근 20건은 서로 다른 eventID이므로 전부 집계하며 대표 1건으로 임의 축약하지 않는다. 반복 이벤트가 많은 사례가 평균을 지배하지 않도록 주 표는 시나리오별로 제시한다. 기존 n4의 71.4%와 새 전체 시간창의 94.3% 차이는 비교 범위 변경에 따른 것이며 질의 개선량으로 해석하지 않는다.


## 질의의 출처와 측정 구현

이번 측정은 query.md의 Q2(상류 발급), Q3(하류 발급·후속 행위), Q5(워크로드 후보 근거 점검)의 규칙을 참고해 별도 작성한 Python 조사 전략을 실행한 것이다. 기존 Cypher를 호출하거나 그 실행 결과를 합산하지 않았다. 새 `07_common_investigation.cypher`의 직접 실행 결과도 아니다. 계승한 규칙·추가한 규칙·출력 차이는 [query.md §13](query.md)에 명시했다.


## 추가 실험 A. 기본 대상 추출(L0)과 확장 대상 추출(L3) 비교

### A.1 목적과 고정 조건

자격증명 통합·공통 조사 실험은 그대로 유지하고, **여러 필드에서 대상을 추출하는 기능이 필요한 자원과 접근 근거를 얼마나 확보하는가**를 별도로 평가한다. 같은 n1~n4 원본 CloudTrail을 같은 파서로 변환하며 `--extract-level`만 0과 3으로 변경한다. 질의 실행·후보 생성은 하지 않는다.

| 구성 | 일반 대상 추출 범위 | 유지하는 기능 |
| :--- | :--- | :--- |
| L0 기본 추출 | resources[] | 호출 주체 식별·자격증명 발급(OBTAINS)·신원/워크로드 문맥 |
| L3 확장 추출 | resources[] 및 요청·응답·serviceEventDetails의 지원 식별 필드 | L0와 동일 |

L0에서도 주체·소속·발급 처리로 노드가 생성될 수 있다. 따라서 L0를 ‘resources[] 외에는 아무 정보도 쓰지 않는 그래프’라고 표현하지 않는다. 두 구성 모두 새 출력 디렉터리에 생성하여 기존 실험 CSV를 보존한다.

### A.2 정답 선정

이미 고정한 `groundtruth_json/aws.5_chain_n*.common.json`의 필수 연결에서 **OBTAINS가 아니고 대상이 구체적인 AWS ARN인 연결**을 가져온다. 자격증명 발급, 서비스 대표 노드(signin.amazonaws.com 등), 문맥 전용 연결은 이번 대상 추출 평가에서 제외한다. IAM 사용자·역할도 호출의 구체적인 대상이면 포함한다.

네 사례의 정답을 두 변환 실행 전에 `results/target_extraction/fixed_groundtruth.json`으로 저장한다. 각 접근의 eventID와 호출 키는 원본 CloudTrail과 대조한다. 이 평가는 기존 조사 질문에 필요한 구체적 대상에 대한 평가이며 모든 로그의 모든 자원에 대한 전체 정답은 아니다.

| 사례 | 정답 자원 | 정답 접근 근거 |
| :--- | :--- | ---: |
| n1 | 인스턴스·트레일·버킷 3개 | SendCommand 1 + StopLogging 1 + 삭제 52 = 54 |
| n2 | 인스턴스·시크릿 20개·스냅샷·플로우로그, 총 23개 | SendCommand 2 + GetSecretValue 20 + 공유 1 + 로그 삭제 1 = 24 |
| n3 | IAM 사용자 2개·트레일 1개 | 프로필 생성·변경·트레일 삭제, 총 3 |
| n4 | 역할 1개·시크릿 2개 | 신뢰정책 변경·시크릿 접근 2건, 총 3 |

### A.3 측정 순서와 계산

1. 정답 자원 집합 T와 접근 집합 A를 고정한다. A의 단위는 `(호출 키, 대상 ID, eventID)`이다.
2. 각 원본 로그에 L0, L3를 적용하여 nodes.csv·edges.csv를 각각 생성한다. 다른 파서 옵션은 기본값으로 동일하게 둔다.
3. nodes.csv에 T의 정확한 ID가 존재하는지 확인한다. 이름·접미사 유사 매칭은 사용하지 않는다.
4. edges.csv에 A의 세 값이 모두 일치하는 행이 있는지 확인한다. 같은 자원을 다른 이벤트가 접근한 것은 정답 접근을 대신하지 못한다.
5. 같은 ID·같은 튜플은 중복 제거한다. 삭제 52건이 같은 버킷에 향하면 자원은 1개, eventID가 다른 접근은 52개다.
6. L0에서 없고 L3에서 확보한 연결의 refPath를 원본 JSON에서 직접 읽어 대상 값과 대조한다.

- 자원 식별률 = 존재하는 정답 자원 ID 수 / 전체 정답 자원 ID 수.
- 접근 근거 보존율 = 존재하는 정답 접근 튜플 수 / 전체 정답 접근 튜플 수.

예를 들어 n4에서 역할 노드가 다른 이벤트로 이미 생성됐어도, 정책변경 eventID와 호출 키가 그 역할로 연결되지 않으면 해당 접근은 누락이다. 따라서 노드 식별과 접근 보존을 따로 측정한다.

### A.4 재현과 산출물

ct_graph_v2에서 실행:

```powershell
python -X utf8 "scripts/measure_target_extraction.py"
```

스크립트는 네 사례의 정답을 먼저 고정한 뒤 파서를 총 8회 실행한다. 한 구성의 변환 예:

```powershell
python -X utf8 parser_node3_v2.py ../stratus-red-team/log_json/aws.5_chain_n1.json -o results/target_extraction/n1_L0 --extract-level 0
```

- 정답: `results/target_extraction/fixed_groundtruth.json`.
- 결과·누락 ID·확보한 근거의 API/refPath: `results/target_extraction/summary.json`.
- 생성 그래프: `results/target_extraction/n1_L0`~`n4_L3`.
- 원본 필드 확인: `results/target_extraction/raw_field_verification.json`.
- 원본 로그·기존 GT·파서의 SHA-256을 결과에 저장한다.

기존 조사 실험은 확보한 관계의 활용 효과를 보여주고, 이번 실험은 그에 앞서 대상 정보와 원본 접근 관계를 확보하는 파서의 기여를 보여준다.
