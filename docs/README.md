# docs

| 폴더 | 내용 |
| --- | --- |
| `study/` | 파서 → 후처리 → 쿼리 → 실험 순서로 코드를 따라 읽는 해설 (00~04). 논문 수치가 어느 파일·필드에서 나오는지 정리 |
| `design/` | 연구 과정의 설계 노트: 그래프 데이터 모델(`3-node-v2.md`), 뷰(`enrich.md`), 조사 쿼리(`query.md`), Neo4j 실행 절차(`RUN.md`), 조사 실험 설계 |

참고:

- 문서의 줄번호와 경로는 작성 당시 작업 폴더 기준입니다. 이 저장소에서는 `verifying script/`가 `scripts/`로 바뀌었고, 원본 로그 경로(`stratus-red-team/log_json`)는 `data/raw/`에 해당합니다.
- `RUN.md`에 나오는 `merge_logs.py`, `verify_fields_v2.py`는 논문 실험에 쓰지 않아 저장소에 포함하지 않았습니다.
- 문서 속 계정 ID·IP·키 ID도 저장소의 다른 파일과 같은 규칙으로 익명화했습니다.
