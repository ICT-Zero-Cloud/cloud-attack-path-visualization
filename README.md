# 연구 아카이브

CloudTrail 공격 경로 시각화 프로젝트의 초기 분석, 모델링, 실험 자료를 주제별로 보관합니다. 현재 자격증명 연구의 최종 코드와 재현 절차는 [main 브랜치](https://github.com/ICT-Zero-Cloud/cloud-attack-path-visualization/tree/main)에 있습니다.

이 프로젝트에서는 **자격증명**과 **로그 삭제**를 주제로 논문 두 편이 작성되었습니다. 아래 이름은 논문 제목이 아니라 자료를 찾기 위한 주제 구분입니다. 논문 원문은 이 저장소에 등록되어 있지 않습니다.

| 연구 주제 | 보관 자료 | 확인 상태 |
| --- | --- | --- |
| [자격증명](credentials/README.md) | 그래프 모델, 정규화, 자격증명 계보, 횡적 이동 실험, 초기 원고 | 최종 코드는 `main`; 이곳은 이전 연구 자료 |
| [로그 삭제](log-deletion/README.md) | CloudTrail 삭제·중지 및 VPC Flow Logs 삭제 로그, 분석 문서 | 관련 로그 존재 확인; 로그 삭제 논문과의 대응은 확인 필요 |

## 자료 찾기

| 경로 | 내용 |
| --- | --- |
| [`credentials/`](credentials/README.md) | 자격증명 관련 초기 모델과 실험 |
| [`log-deletion/`](log-deletion/README.md) | 로그 삭제·수집 중지 관련 자료 |
| [`datasets/`](datasets/README.md) | 공통 데이터셋, 공격 시나리오, 데이터 생성 스크립트 |
| [`references/`](references/README.md) | CloudTrail·IAM·provenance·그래프 압축 관련 조사 |
| [`provenance/`](provenance/README.md) | 원래 위치, 원본 커밋, 파일별 출처 |

## 보관 기준

사람 이름과 작업 번호 대신 연구 주제와 자료의 용도로 분류했습니다. 같은 내용의 파일은 한곳에 두고, 내용이 다른 버전은 구분해 남겼습니다. 기존 브랜치들의 커밋 이력은 이 브랜치의 조상으로 보존했습니다.

코드와 로그는 원본 그대로 보관했습니다. 문서의 본문은 보존하고 옮겨진 자료를 가리키는 상대 링크만 현재 위치에 맞췄습니다. 과거 문서의 실행 예시는 당시 저장소 경로를 사용합니다. 현재 배치는 위 색인과 [파일별 출처](provenance/manifest.json)에서 확인할 수 있습니다. 이 브랜치에는 당시 수집한 원본 로그도 포함되어 있으며, `main`에 포함된 익명화된 파생 자료와 구분됩니다.
