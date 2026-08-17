# OpenSpace 정적 아카이브

`site/`는 행사 종료 시점의 공개 화면만 담는 GitHub Pages 배포 산출물입니다.
운영 DB, 업로드 원본 전체, 관리자·로그인·신청·라이트닝 신청자 화면은 포함하지 않습니다.
공개 HTML에서 실제로 참조된 업로드 이미지만 복사합니다.

## 생성

운영 DB와 업로드 디렉터리를 안전한 로컬 환경에 복사한 뒤 다음을 실행합니다.

```bash
uv run python scripts/export_static_archive.py \
  --database /secure-backup/openspace.db \
  --uploads /secure-backup/uploads \
  --base-path /mvp-openspace
```

커스텀 도메인(예: `openspace-archive.pycon.kr`)을 쓸 때는 `--base-path ""`로 생성합니다.
생성 후 `archive/site/`의 내용을 검토한 뒤에만 커밋합니다.

## GitHub Pages 설정

저장소 **Settings → Pages → Build and deployment**에서 **GitHub Actions**를 선택합니다.
`main`에 `archive/site/` 변경이 푸시되면 `.github/workflows/deploy-static-archive.yml`이 배포합니다.

GitHub 프로젝트 페이지 주소는 기본적으로 `https://<owner>.github.io/mvp-openspace/`입니다.
저장소 이름을 바꾸면 생성 시 `--base-path`도 새 이름으로 바꿔야 합니다.
