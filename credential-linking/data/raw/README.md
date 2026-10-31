# data/raw

원본 CloudTrail 로그를 두는 자리입니다. 저장소에는 포함하지 않습니다 (`.gitignore`).

`scripts/measure_target_extraction.py`(표 2)는 아래 파일을 읽습니다.

```
data/raw/aws.5_chain_n1.json
data/raw/aws.5_chain_n2.json
data/raw/aws.5_chain_n3.json
data/raw/aws.5_chain_n4.json
```

다른 위치에 있으면 `CT_RAW_DIR` 환경변수로 지정합니다.

```bash
CT_RAW_DIR=/path/to/log_json python scripts/measure_target_extraction.py
```

원본 로그로 다시 파싱하면 실제 계정 ID·IP가 들어간 CSV가 생기므로, 공개 저장소에 커밋하지 마세요.
