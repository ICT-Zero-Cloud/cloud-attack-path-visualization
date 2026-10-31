# 출처와 이력

[manifest.json](manifest.json)에 원본 브랜치, 브랜치의 마지막 커밋, 원래 파일 경로, 원본 Git blob, 현재 보관 위치를 기록했습니다. 여러 브랜치가 같은 파일을 공유한 경우 같은 보관 위치를 가리킵니다.

코드와 로그는 바이트 단위로 보존했고, 내용이 다른 파일을 같은 이름으로 덮어쓰지 않았습니다. 문서의 상대 링크를 수정한 경우 manifest에 원본 blob과 보관본 blob, 수정한 링크를 함께 기록했습니다. 기존 브랜치들의 마지막 커밋은 `archive`의 조상으로 연결되어 있으므로 브랜치 이름을 나중에 정리해도 원본 이력이 유지됩니다.

과거 시점의 원래 저장소는 manifest에 기록된 커밋으로 조회할 수 있습니다.

```sh
git show <commit>:<original-path>
git log <commit>
```

[`repository/`](repository/README.md)에는 예전 루트 README, Git 제외 규칙, 이슈·PR 템플릿을 보관했습니다. 연구 자료의 탐색은 [아카이브 색인](../README.md)에서 시작합니다.
