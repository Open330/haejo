# Haejo 이름과 배포 식별자

Haejo(해줘)는 Claude와 Codex가 Mac 앱과 브라우저를 대신 쓰고, 결과를 확인하고,
그 과정을 Flow로 저장해 다시 실행하게 하는 도구입니다. 2026-11-09에 Tacto에서
이름을 바꿨습니다. 제품·명령·Python namespace·에이전트 스킬·저장 경로·서명 식별자를
Haejo로 통일합니다. 이전 이름의 명령·import·환경 변수를 런타임 별칭으로 제공하지 않습니다.

| 사용자 접점 | 이름·경로 |
| --- | --- |
| 제품·메뉴 막대 | Haejo |
| 명령·에이전트 스킬 | `haejo` |
| Python 배포·import | `haejo-runtime` / `haejo` |
| 서명된 실행기 | `launcher/haejo` |
| 권한용 helper | `helper/Haejo Helper.app/Contents/MacOS/HaejoHelper` |
| GUI 실행 파일 | `HaejoSetup` |
| 번들 ID·서명 식별자 | `ai.callabo.haejo.*` |
| 환경 변수 | `HAEJO_*` |
| 사용자 데이터 | `~/Library/Application Support/Haejo`, Flow는 `<data>/haejo/flows` |
| 랜딩페이지 | `sites/haejo/dist` |

## Tacto에서 옮길 때 — 2026-11-09

- **서명 ID가 바뀝니다.** `ai.callabo.tacto.*`에서 `ai.callabo.haejo.*`로 바뀌므로 macOS는
  Haejo Helper를 새 앱으로 봅니다. 새 배포를 설치한 뒤 접근성·화면 기록 권한을 다시
  허용해야 합니다. 소스의 ID가 바뀌었다는 이유로 권한이 승계됐다고 판정하지 않습니다.
- **사용자 데이터는 옮깁니다.** Haejo 앱을 처음 실행하거나 `haejo doctor`를 대화형으로
  실행하면 `~/Library/Application Support/Tacto`와 `<data>/tacto`를 Haejo 경로로 옮깁니다.
  Haejo 경로가 이미 있으면 아무것도 옮기거나 합치지 않습니다. 심볼릭 링크는 건드리지
  않습니다. 구현: `haejo/legacy_data.py`, `setup/main.swift`의 `migrateLegacyTactoData`.
- **이전 실행 기록도 읽습니다.** `tacto-*.jsonl` 활동 기록은 이름만 다를 뿐 같은 형식이라
  실행 기록 탭에 그대로 표시됩니다. 새 기록은 `haejo-*.jsonl`로 씁니다.
- **바꾸지 않은 저장 식별자.** 아래 값은 이미 디스크와 Keychain에 저장된 데이터를 찾는
  키라서 그대로 둡니다. 사용자에게 보이지 않습니다.
  - Keychain 서비스 `ai.callabo.tacto.credentials` (저장된 자격 증명)
  - 저장 형식 `tacto-links-v1`(설치 링크 기록), `tacto-dispatch-v1`(실행 저널),
    `tacto-resource-leases-v1`(자원 임대)
  - 헬퍼의 서명 신원이 바뀌므로 Keychain이 처음 한 번 접근 허용을 물을 수 있습니다.
- **은퇴한 연결 정리.** `./skill/install.sh`는 이 체크아웃이 만든 `tacto` 명령·스킬 링크를
  지웁니다(`nlc`와 같은 방식). 다른 프로그램이나 다른 체크아웃의 링크는 건드리지 않습니다.
- **저장소와 웹 주소는 아직 그대로입니다.** GitHub 저장소 `Open330/tacto`와
  `open330.github.io/tacto`는 저장소 이름을 바꾸기 전까지 유지합니다. v1.0.0-rc.13까지의
  출시 후보는 Tacto(`Tacto.app`, `tacto` 명령)로 배포됐습니다.
- **측정 기록의 라벨 이전.** 문서·측정표·비교 arm/case 키·fixture 이름을 Haejo 표기로
  옮겼습니다. 라벨과 식별자의 이전이며 재측정이 아닙니다. 토큰·시간·성공률·실패·SKIP
  수치와 결과의 한계는 그대로입니다. Git 이력과 무시된 비공개 원시 아티팩트는 새 측정
  결과처럼 재작성하지 않습니다. 녹화 영상과 스크린숏 속 앱 화면에는 당시 이름 Tacto가 보입니다.

## 브랜드

이름 ‘해줘’가 사용법입니다. 사용자는 부탁하고, Haejo는 앱을 써서 해 주고, 확인한 것만
끝났다고 말합니다. 전체 시안과 근거는 [브랜드북](haejo-brandbook.html)에 있습니다.

### 메시지

| 층위 | English | 한국어 |
| --- | --- | --- |
| 태그라인 | Ask Haejo. | 말하면 해 줍니다. 확인까지. |
| 헤드라인 장치 | Ask Haejo to ____. | Haejo, ____ 해 줘. |
| 대표 문장 | Ask Haejo to use your apps. | 앱을 열고, 입력하고, 결과까지 확인해 줘. |

다섯 가지 약속은 모두 “~해 줘”로 씁니다. 반복은 그중 하나입니다.

| 약속 | 뜻 | 근거 |
| --- | --- | --- |
| 써 줘 | Mac 앱과 브라우저를 열고, 누르고, 입력하고, 끌어 옮김 | README의 실제 앱·사이트 녹화 |
| 확인해 줘 | 결과를 확인하고, 증거가 부족하면 끝났다고 하지 않음 | TextEdit 저장 내용 디스크 검증 |
| 다시 해 줘 | Flow로 저장해 새 입력으로 다시 실행 | 일반 재실행 중 모델 호출 0회 |
| 로그인해 줘 | Keychain·Bitwarden 값을 서명된 헬퍼가 직접 입력 | 에이전트에는 결과만 전달 |
| 보여 줘 | 어떤 앱에서 무엇을 했고 결과가 어땠는지 기록 | 기록은 이 Mac에만, 화면 내용·입력값 제외 |

말하지 않는 것: “무엇이든 해 드립니다”, “완전 자율”, “100% 정확”, 확인하지 않은 일의 “완료”.
이름 표기는 `Haejo` 한 단어입니다. `HAE-JO`처럼 하이픈을 넣지 않습니다. 발음은 hay-joh,
표준 로마자 표기는 `haejwo`이며 `jo`는 구어 발음을 따른 표기입니다.

### 마크

한글 초성 **ㅎ**입니다. 코럴 점은 부탁이자 해(태양), 가로획은 부탁을 적는 빈칸이자
에이전트가 기록한 Flow, 원은 확인까지 끝난 결과입니다.

- 가로획은 원 폭의 약 1.55배입니다. 마크가 정사각형을 가로로도 채웁니다.
- 해는 원의 안쪽 구멍과 같은 크기로 **보이도록** 0.72배로 그립니다. 꽉 찬 원은 같은 크기의
  빈 구멍보다 커 보입니다.
- 워드마크 `haejo`의 j 점은 마크의 해와 같은 원입니다. 한글 워드마크 `해줘`의 ㅎ도 같은 규칙입니다.
- 코럴은 해에만 씁니다. 해를 가로획에 붙이거나, 키우거나, 마크를 기울이지 않습니다.

### 자산

| 용도 | 파일 |
| --- | --- |
| 마크·로크업·워드마크·상태 아이콘·모션·배너·공유 카드 | `docs/assets/brand/haejo/` |
| macOS 앱 아이콘 | `docs/assets/haejo-app.icns` (16–1024 px, 10개 크기) |
| 아이콘 벡터 원본 | `docs/assets/haejo-app-icon.svg` (64 px 이상), `docs/assets/haejo-app-icon-small.svg` (16·32 px) |
| 앱·사이트용 마크와 로크업 | `docs/assets/haejo-logo.svg`, `docs/assets/haejo-wordmark.svg`, `sites/haejo/dist/assets/` |
| 설정 메뉴 막대 template | `docs/assets/haejo-menu-template.svg` |

- 모든 SVG와 `.icns`는 `python3 setup/build_brand_assets.py`가 만듭니다. SVG를 직접 고치지 말고
  스크립트 상수를 고친 뒤 다시 생성합니다. `--check`는 렌더링 없이 추적 중인 SVG가 생성기와
  같은지만 확인합니다.
- 16·32 px은 획 4.6의 소형 광학 크기를 씁니다.
- 메뉴 막대의 상시 아이콘은 설정과 작업 상태를 여는 접점이라 두 슬라이더 template을 유지합니다.
  `docs/assets/brand/haejo/haejo-state-*.svg`(대기·하는 중·완료·확인 필요)는 상태 표시 시안이며
  아직 앱에 연결하지 않았습니다.
