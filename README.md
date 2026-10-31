# CloudTrail 공격 경로 연구

클라우드 감사 로그를 바탕으로 **자격증명 연결**과 **로그 삭제**를 다루는 연구 프로젝트입니다. 두 연구의 논문과 대응하는 코드·실험 결과를 함께 안내합니다.

## 논문과 연구 결과

| 연구 | 논문 | 원문 | 코드·실험 결과 |
| --- | --- | --- | --- |
| 자격증명 연결 | [자격증명 흐름과 자원 접근을 연결하는 CloudTrail 침해 조사 그래프](papers/README.md) · CISC-W'26 | PDF·공개 링크 등록 예정 | [재현 코드와 결과](credential-linking/README.md) |
| 로그 삭제 | 제목 등록 예정 | PDF·공개 링크 등록 예정 | 최종 자료 정리 예정 — [`log-deletion/`](log-deletion/) |

논문 원문은 [`papers/`](papers/README.md)에 모읍니다. 현재 두 논문의 PDF와 공개 링크는 등록되어 있지 않습니다. 자격증명 논문의 제목과 학회 정보는 기존 연구 README에 기재된 내용을 사용했습니다.

## 저장소 구성

```text
.
├─ README.md
├─ papers/                    논문 목록과 원문
├─ credential-linking/        자격증명 연결 연구
│  ├─ README.md               논문 설명과 재현 절차
│  ├─ parser_node3_v2.py
│  ├─ scripts/
│  ├─ queries/
│  ├─ csv/
│  ├─ groundtruth_json/
│  ├─ results/
│  └─ docs/
└─ log-deletion/              로그 삭제 최종 자료를 추가할 위치
```

`credential-linking/`에는 기존 최종 코드와 실험 자료를 내부 구조 그대로 옮겼습니다. `log-deletion/`에는 폴더를 유지하는 빈 `.gitkeep` 파일만 두었으며, 논문에 대응하는 최종 자료가 준비되면 추가합니다.

## 자격증명 연결 연구 재현

Python 3.10 이상에서 실행합니다. 포함된 CSV로 수행하는 표 3 실험은 원본 CloudTrail 로그 없이 재현할 수 있습니다.

```sh
cd credential-linking
python scripts/measure_investigation_batch.py
python scripts/test_measure_investigation.py
```

전체 실행 방법, 논문 표와 결과 파일의 대응, 데이터 설명은 [자격증명 연결 연구 README](credential-linking/README.md)에 있습니다.

## 이전 연구 자료

초기 모델과 실험, 공통 데이터 조사, 과거 원고는 단일 [`archive` 브랜치](https://github.com/ICT-Zero-Cloud/cloud-attack-path-visualization/tree/archive)에 보관합니다. 당시 로그 삭제 관련 수집 로그와 문서도 포함되어 있으며, 로그 삭제 논문의 최종 자료와의 대응은 확인이 필요합니다.
