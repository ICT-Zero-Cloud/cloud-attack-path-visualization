# CloudTrail 자격증명 흐름 그래프

CISC-W'26 논문 **「자격증명 흐름과 자원 접근을 연결하는 CloudTrail 침해 조사 그래프」**의 코드, 정답 집합, 실험 결과를 담은 저장소입니다.

CloudTrail 로그를 그래프로 바꿔, 공격자가 자격증명을 바꿔 가며 이동한 경로와 그 경로가 닿은 자원을 끊기지 않고 따라갈 수 있게 합니다.

두 연구의 전체 소개는 [프로젝트 README](../README.md), 논문 원문과 등록 상태는 [논문 목록](../papers/README.md)에서 확인할 수 있습니다. 이 연구의 초기 모델과 메모는 [`archive/credentials`](https://github.com/ICT-Zero-Cloud/cloud-attack-path-visualization/tree/archive/credentials)에 보관합니다.

## 분석 흐름

```
CloudTrail 로그 ──▶ Python 파서 ──▶ 후처리(뷰) ──▶ Neo4j + 쿼리
 (JSON)            자격증명·자원 = 노드   이동 후보 추론     공통 조사 전략
                   발급·접근 = 간선       조사용 속성
```

## 핵심 아이디어

| 아이디어 | 내용 | 위치 |
| --- | --- | --- |
| ① 키 단위 통합 | 발급 응답의 `accessKeyId`와 후속 호출의 `accessKeyId`를 같은 노드로 통합해, 키가 바뀌어도 발급이 키→키 간선(`OBTAINS`)으로 이어지게 한다 | `parser_node3_v2.py` |
| ② 다중 필드 대상 추출 | `resources[]`뿐 아니라 요청·응답 필드에서도 대상 식별자를 찾아 구체적 자원과 연결하고, 찾은 위치(`refPath`)를 함께 남긴다 | `parser_node3_v2.py` (`--extract-level`) |
| ③ 워크로드 이동 후보 | 로그에 남지 않는 인스턴스 자격증명 획득을 "워크로드 제어 + 그 워크로드에 실린 키(`RUNS_ON`)"로 추론한 `CAN_OBTAIN` 후보로 표현한다. 관측된 발급과 구분하며, 확정이 아닌 조사 단서다 | `scripts/simulate_views.py`, `scripts/apply_view.py`, `enrich_views.cypher` |
| 공통 조사 전략 | 시작 이벤트 하나에서 상류(발급 계보)와 하류(후속 키와 자원 접근)를 같은 규칙으로 조회한다 | `scripts/measure_investigation.py`, `queries/investigation/` |

## 저장소 구조

| 경로 | 내용 |
| --- | --- |
| `parser_node3_v2.py` | CloudTrail JSON → `nodes.csv` / `edges.csv` / `context.csv` |
| `scripts/simulate_views.py` | 뷰 규칙의 원본 (노드 분류, `advances`, `CAN_OBTAIN` 합성) |
| `scripts/apply_view.py` | 뷰 규칙을 CSV로 물질화 → `csv/*_view/` |
| `scripts/measure_target_extraction.py` | 표 2 실험 (L0 vs L3 대상 추출) — 원본 로그 필요 |
| `scripts/measure_investigation.py` | 공통 조사 전략과 채점 |
| `scripts/measure_investigation_batch.py` | 표 3 실험 (n1~n4 일괄 실행) |
| `scripts/test_measure_investigation.py` | 조사 전략 구현 점검 (6개 테스트) |
| `load_3node_v2.cypher`, `enrich_views.cypher` | Neo4j 적재와 같은 뷰 규칙의 Cypher 판 |
| `queries/investigation/` | Neo4j 조사 쿼리 (시작 이벤트, 상류·하류, 후보 근거 점검 등) |
| `docker-compose.yml`, `browser-style.grass` | 로컬 Neo4j 실행 설정과 Browser 스타일 |
| `groundtruth_json/` | 시나리오별 정답 집합 (필수 근거, 문맥, 대조군) |
| `csv/` | n1~n4 파싱 결과(기반 그래프)와 뷰 결과 |
| `results/` | 논문 표 2·표 3의 원자료 |
| `docs/` | 단계별 해설 문서와 설계 노트 |
| `data/raw/` | 원본 CloudTrail 로그를 두는 자리 (저장소에는 포함하지 않음) |

## 실행

Python 3.10 이상, 표준 라이브러리만 사용합니다. 아래 명령은 `credential-linking/` 폴더에서 실행합니다.

```bash
cd credential-linking
```

### 표 3 재현 — 원본 로그 없이 가능

`csv/`에 파싱·뷰 결과가 들어 있어 바로 실행할 수 있습니다.

```bash
python scripts/measure_investigation_batch.py   # results/common_investigation_*.json 재생성
python scripts/test_measure_investigation.py
```

| 사례 | 수집 로그 | 반환 | 필수 연결 보존 | 관측 발급만 | 후보 쌍 |
| --- | --- | --- | --- | --- | --- |
| n1 | 129 | 66 | 55/55 | 1/55 | 1 |
| n2 | 165 | 31 | 24/24 | 2/24 | 1 |
| n3 | 138 | 5 | 5/9 | 5/9 | 0 |
| n4 | 140 | 8 | 6/6 | 6/6 | 0 |

### 표 2 재현 — 원본 로그 필요

원본 로그 `aws.5_chain_n1.json` ~ `aws.5_chain_n4.json`을 `data/raw/`에 두거나 `CT_RAW_DIR` 환경변수로 위치를 지정합니다.

```bash
python scripts/measure_target_extraction.py     # results/target_extraction/ 재생성
```

결과: 구체적 자원 접근 근거 L0 74/84 → L3 84/84, 정답 자원 식별 27/32 → 32/32.

### 임의의 로그를 그래프로

```bash
python parser_node3_v2.py <log.json> -o csv/<name>            # 기반 그래프 (기본 --extract-level 3)
python scripts/apply_view.py csv/<name>                        # 뷰 → csv/<name>_view/
python scripts/measure_investigation.py --gt <gt.json> --csv csv/<name>_view --mode both
```

Neo4j 적재와 시각화 절차는 `docs/design/RUN.md`를 참고하세요 (`docker compose up -d` → `load_3node_v2.cypher` → `enrich_views.cypher`).

## 논문 표와 파일

| 논문 | 파일 |
| --- | --- |
| 표 2 (4.3 대상 추출 범위) | `results/target_extraction/summary.json`, `fixed_groundtruth.json`, `raw_field_verification.json` |
| 표 3 (4.4 근거 보존과 검토 대상) | `results/common_investigation_summary.json`, `results/common_investigation_n*.json` |
| 4.4 관측 모드 / 후보 모드 | 위 파일의 `observed_*`, `candidate_pairs` 필드 |
| 정답 근거 정의 (4.2) | `groundtruth_json/aws.5_chain_n*.common.json` |

표 3의 수치는 `csv/` 위에서 Python으로 실행한 근거 선택 결과이며, Neo4j 처리 성능이 아닙니다.

## 데이터와 익명화

- 평가 로그는 저자가 AWS 환경에서 직접 구성·실행한 네 시나리오(n1~n4)에서 수집했습니다.
- **원본 CloudTrail 로그는 포함하지 않습니다.**
- 포함된 파생 파일(CSV, 정답 집합, 결과, 문서)은 같은 규칙으로 일관되게 바꿨습니다. 그래서 연결 관계와 표 3 수치는 바뀌지 않습니다 (익명화 후 재실행 결과가 동일함을 확인).
  - AWS 계정 ID → `123456789012`
  - 출처 IP → `203.0.113.10`, `203.0.113.20`, `203.0.113.30` (문서용 예약 대역)
  - 액세스 키 ID의 계정 유래 구간 → `AKIAEXAMPLE0…`, `ASIAEXAMPLE0…` (끝 8자리는 유지)
- `results/target_extraction/fixed_groundtruth.json`의 SHA-256 값은 익명화 이전 원본 기준입니다.
- `docker-compose.yml`의 Neo4j 비밀번호는 로컬 실행용 기본값입니다.

## 인용

```
강인석, 서장훈, 정준식, 박기웅(교수). 자격증명 흐름과 자원 접근을 연결하는 CloudTrail 침해 조사 그래프. CISC-W'26, 2026.
```
