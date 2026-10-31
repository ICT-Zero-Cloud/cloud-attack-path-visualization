# 로그 삭제와 수집 중지 관련 자료

프로젝트의 두 논문 중 하나는 로그 삭제를 다룹니다. 이 폴더에는 저장소에서 실제로 확인한 관련 수집 로그와 분석 문서를 모았습니다. **아래 자료가 해당 논문의 실험·결과에 사용되었는지는 별도 확인이 필요합니다.** 논문 제목과 원문, 대응 실험 코드 및 결과표는 아직 등록하지 않았습니다.

| 사례 | 수집 로그 | 전체 이벤트 | 핵심 이벤트 | 분석 문서 |
| --- | --- | ---: | --- | --- |
| CloudTrail 트레일 삭제 | [JSON](data/aws.defense-evasion.cloudtrail-delete.json) | 56 | `DeleteTrail` 1건 | [분석](docs/aws.defense-evasion.cloudtrail-delete.md) |
| CloudTrail 로깅 중지 | [JSON](data/aws.defense-evasion.cloudtrail-stop.json) | 39 | `StopLogging` 1건 | [분석](docs/aws.defense-evasion.cloudtrail-stop.md) |
| VPC Flow Logs 삭제 | [JSON](data/aws.defense-evasion.vpc-remove-flow-logs.json) | 63 | `DeleteFlowLogs` 1건 | 전용 분석 문서 미확인 |

위 값은 보관된 JSON의 `Records`를 직접 집계한 것이며 논문의 평가 수치가 아닙니다. 파일명에 삭제·중지가 있어도 의미가 서로 다르므로 각 사례를 구분해 두었습니다.

관련 공통 자료:

- [Stratus Red Team 기법 조사](../datasets/stratus-red-team/docs/stratus-red-team.md)
- [공격 모티프 연구 요약](../credentials/graph-modeling/docs/REPORT.md): 방어 회피 모티프도 포함된 공통 그래프 연구 자료
- [초기 인과 의미 왜곡 분석](../credentials/drafts/semantic-distortion-analysis.md): `StopLogging` 등의 모델링 검토
- [원본 브랜치·파일 출처](../provenance/manifest.json)
