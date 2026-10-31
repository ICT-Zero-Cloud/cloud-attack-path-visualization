# 초기 그래프 모델링

| 경로 | 내용 |
| --- | --- |
| [`docs/graph-modeling.md`](docs/graph-modeling.md) | Identity·Credential·Execution·APIEvent·Resource 모델 |
| [`docs/3-node.md`](docs/3-node.md) | 3종 노드 모델 검토 |
| [`docs/3-node-v2.md`](docs/3-node-v2.md) | 기반 그래프 설계 |
| [`docs/REPORT.md`](docs/REPORT.md) | 공격 모티프와 필드 절제 실험의 연구 요약 |
| [`docs/RUN.md`](docs/RUN.md) | 당시 실행 절차 |
| [`docs/enrich.md`](docs/enrich.md), [`docs/query.md`](docs/query.md) | 뷰 규칙과 질의 |
| [`scripts/`](scripts/parser_node3_v2.py) | 초기 파서와 개선 파서 |
| [`neo4j/`](neo4j/README.md) | 초기 적재 스크립트와 Cypher 질의 |
| [`runtime/`](runtime/docker-compose.yml) | 기반 그래프의 실행 설정과 적재·뷰 스크립트 |
| [`data/session-graph/`](data/session-graph/edges.csv) | flaws.cloud에서 생성한 초기 세션 그래프 CSV |
| [`data/neo4j-export/`](data/neo4j-export/edges.csv) | 별도로 보관되었던 Neo4j용 CSV; 위 세션 그래프와 내용이 다른 자료 |

파일은 당시 내용을 보존했습니다. 여러 단계의 모델이 포함되어 있으며, 현재 최종 모델은 `main`을 참고합니다.
