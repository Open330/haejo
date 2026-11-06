# 비교 실행 기록

## 2026-11-06 후속 성능: 입력 뒤 고정 대기와 읽기 대기

동료와 코드를 독립 검토해 Calculator 관측의 약 0.9초가 native AX tree 읽기보다
Python의 행동 뒤 1초 settle에서 나옴을 확인했다. `read`도 이 시각을 갱신하던
문제를 수정했다. 행동 전에 없었던 `expect`를 가진 클릭은 결과를 즉시 새로
관측해 폴링한다. 텍스트·키 입력·메뉴, 이미 보이던 문구, 검사 없는 단계는 기존
대기를 유지한다. 화면 변화 두 번이 같다는 이유만으로 조기 완료하는 안은 중간
loading 화면 반례 때문에 채택하지 않았다. Calculator guide는 각 숫자·연산자
단계의 짧은 `equals`와 실제 표시 기호/공백을 명시한다.

동일한 Flow·native 바이너리·Python 3.11로 각 시나리오를 전후 3쌍 교대 실행했다.
이는 모델 작성이 아닌 재생 측정이며 모델 호출은 0회다. 마지막 계산값 408은
postcondition으로 검증했다. 읽기는 전후 모두 시작 관측을 포함해 4회 새로 읽었다.

| 재생 시나리오 | 수정 전 중앙값 | 수정 후 중앙값 | 관측 감소 |
|---|---:|---:|---:|
| 클릭 결과 문구 기다리기 | 6.994초 | 1.938초 | 72.3% |
| 연속 읽기 3회 | 3.408초 | 0.281초 | 91.7% |
| 결과 검사 없는 비교군 | 7.004초 | 6.991초 | 차이 없음 |

별도로 새 문맥의 에이전트를 사용해 before Tacto 3회 후 after Tacto/Sky 3쌍을
실행했다. 요청 모델/노력은 gpt-6.1-sol/medium, 제한 180초, 같은 외부 controller,
같은 길이 runtime 경로와 같은 native 바이너리이며 양쪽 Tacto 모두 --timings다.
과제 결과 oracle은 9/9 통과했다. 단 after Tacto 첫 시행에서 System Settings
활성화 1건을 기록해 그 시행은 배경 조건 불합격으로 보존했다. 원인은 미확인이다.
회귀 검사와 배포 빌드는 모델 cohort가 끝난 뒤 시작했다.

배경 조건을 통과한 행만 비교한 주 수치는 아래와 같다. 수정 후 Tacto의 표본은
2회뿐이며, 서로 다른 시행 수의 중앙값/평균이지 3쌍 인과 추정이 아니다.

| 도구·시점 | 유효 시행 | 시간 중앙값 | 회당 평균 입력 | 회당 평균 출력 |
|---|---:|---:|---:|---:|
| Tacto 수정 전 | 3 | 43.8초 | 127,806 | 831.3 |
| Tacto 수정 후 | 2 | 36.5초 | 114,924.5 | 805 |
| Sky 후속 대조 | 3 | 30.0초 | 134,707 | 565.3 |

주 수치의 시간 감소는 약16.7%, 평균 입력 감소는 약10.1%다. 불합격 행까지 포함한
참고 집계는 after Tacto 중앙값35.0초(약20.1% 감소), 3회 입력 합계383,418→339,377
(11.5% 감소), 출력2,494→2,423이다. 출력 개선은 주장하지 않는다. Tacto 입력은
Sky보다 적지만 시간과 출력은 더 크다. 불합격 행을 지우거나 성공으로 재분류하지
않았다. serving model·실제 청구·서버 cache/부하·strict 제품 동등성은 미입증이며
harness exit2도 보존했다. before Sky 대조군 없이 순차 실행한 소표본 관측이다.

Calculator 재생은 before 4.84~5.84초에서 after 0.72~0.84초가 됐다. 세 after 모두
observe1/wait6으로 중간 검사 경로를 사용했다. 반면 Flow 바이트 중앙값655→737,
Flow 수신 시각 중앙값5.87→6.75초로 작성 부담은 조금 늘었다. 안내 변경의 비용과
이득을 함께 기록하며 모든 전체 시간 감소를 런타임 변경에 귀속하지 않는다.

에이전트 측정 source는 db90000이다. 이후 동료가 지적한 자동 완성 경합을 반영해
즉시 expect 확인을 click으로만 제한한 최종 source는85b5702, 동일 tree의 검사
source는1f8ff2e다. 측정된 click/read/guide 경로는 같지만 이 축소 뒤 에이전트 전체
측정을 다시 했다고 주장하지 않는다. 최종 candidate native6확인은 별도로 통과했다.
최종 전체3,275검사는 실패·오류0, 제외27, 소스 불변으로 통과했다. 중간의 병렬
빌드 중 300ms 하위 프로세스 시험1건 실패는 보존했고, 코드 변경 없이 해당 시험
5회 통과 후 빌드와 분리한 전체 재검사를 통과했다. 부하 원인은 확정하지 않았다.

rc.24 앱·DMG 공증과 Gatekeeper, 산출물12검사·보안 검사를 통과했다. 세 Mac에
동일 번들을 설치해 기존 권한·스킬 연결·백그라운드 실행·Dock 숨김을 확인했다.
설치본 native7검사, 세션 수리·본문 readback·취소·관측 paging도 통과했다.
공개 GitHub release와 Vault 세션은 변경하지 않았다.

[공개 집계](benchmarks/2026-11-06-replay-readiness-perf.json). 원본·실패·재검사 기록은
로컬 `reviews/perf-followup-20261106-evidence/`에 있다. 남은 성능 과제는 모델의
Flow 작성/도구 왕복과 큰 트리 관측이며, 이번 결과를 모든 앱의 보장값으로 쓰지 않는다.

## 2026-11-06 첫 작성 성능: 반복 schema 수리 제거

동료와 원시 trace를 독립 검토해 Calculator 첫 Flow의 `selector.ancestor`
형식 오류가3/3 반복됨을 찾았다. 실제 입력은 기록되지 않았으므로 객체/빈 문자열
중 어떤 값이었는지는 미확인이다. 안내에 문자열 또는 문자열 목록임을 명시하고,
단일 창에서는 생략하도록 했다. 오류 힌트도 해당 필드만 설명한다. 본문 편집과
Save의 receipt/exit 의미는 이번 수정에서 바꾸지 않았다.

같은 길이의 고립 runtime 경로, 같은 native 바이너리·CLI·설정·controller,
요청 모델 `gpt-6.1-sol`/medium과 과제를 사용했다. before Tacto3회 후 after
Tacto/Sky3쌍을 실행했다. 두 Tacto cohort 모두 session `--timings`를 요청했다.

| 도구·시점 | 작업 성공 | 시간 중앙값 | 입력 합계 | 비캐시 입력 합계 | 출력 합계 | schema 수리 |
|---|---:|---:|---:|---:|---:|---:|
| Tacto 수정 전 | 3/3 | 61.0초 | 483,541 | 54,997 | 3,187 | 3 |
| Tacto 수정 후 | 3/3 | 41.3초 | 382,267 | 37,307 | 2,494 | 0 |
| Sky 후속 대조 | 3/3 | 33.3초 | 430,704 | 44,784 | 2,017 | — |

표본에서 시간 중앙값32.3%, 입력20.9%, 비캐시 입력32.2%, 출력21.7%가
줄었다. 수정 후 입력은 Sky보다 적지만 시간과 출력 부담은 여전히 더 크다.
Calculator의 Flow 수신 시각은 세션 시작 후17.2~25.6초에서6.4~6.9초로 줄었고, 준비 자체는
0.34~0.67초였다. 주된 수정 대상은 기동 지연이 아닌 작성·수리 왕복이다.
재생 시간1.79초는 한 번뿐이며 다른 두 after는 약5.8초였으므로 런타임 자체가
일관되게 빨라졌다는 근거로 쓰지 않는다. 생성된 Flow의 postcondition 구성
차이로 추정하며 입력 원문은 보관하지 않았다.

전3회 중1회 System Settings 전경 전환을 관측해 해당 시행의 배경 보존은
불합격으로 보존했다. 그 시행을 제외한 전2회 중앙값은58.05초다. 후6회는
활성화0이었다. 순차 전후 측정이며 before Sky 대조군은 없고 서버 cache/부하도
통제하지 못했다. 위 감소율은 관측치이며 일반적인 인과 효과·실제 청구 절감률이
아니다. 토큰은 부모 CLI의 reported usage다. strict 제품 동등성도 미입증이다.

기본 세션 출력에서 진단4개를 숨기고 입력 시도/수리/UTF-8 byte 계측을 추가했다.
`--timings`에서는 진단을 유지하므로 위 비교는 기본 출력 축소의 효과를 측정하지
않는다. 원문 값은 계측에 넣지 않는다. 전체3,266검사는 실패·오류0, 제외27,
소스 불변으로 통과했다. source `d611ada`와 배포 source `cab27d8`의 Git tree가
동일함을 확인했다. 향후 우선순위는 Calculator의 반복 전체 관측 비용과 본문
완료/저장 증빙의 출력 구분이며 이번 결과에 미구현 효과를 섞지 않는다.

rc.23 앱·DMG 공증, Gatekeeper, 산출물12검사와 소스/DMG 보안 검사를 통과했다.
세 Mac에 같은 번들을 설치하고 권한 유지·백그라운드 실행·Dock 숨김을 확인했다.
로컬 설치본 native7검사와 세션 수리·본문 readback·취소·추가 관측도 통과했다.
공개 GitHub release와 Vault 세션은 변경하지 않았다.

[공개용 집계](benchmarks/2026-11-06-authoring-perf.json). 원본은 로컬
`reviews/perf-20261106-evidence/`에 보존했다.

## 2026-11-06 rc.22: 새 작업 독립3쌍 비교와 설치 검증

같은 Calculator→소유 TextEdit 과제를 각3회 실행했다. 요청 모델은
`gpt-6.1-sol`, reasoning `medium`, 제한180초로 같고 매번 새 임시 작업 공간과
새 대화를 사용했다. Tacto 후보 CLI·guide를 명시하고 두 arm의 선행 순서를
번갈았다. Calc 결과와 문서 본문 `437`, 창/파일 정리를 host가 별도 확인했다.

| 도구 | 성공 | 시간 중앙값 | 입력 토큰 합계 | 비캐시 입력 합계 | 출력 합계 |
|---|---:|---:|---:|---:|---:|
| Tacto | 3/3 | 57.0초 | 461,607 | 51,111 | 3,269 |
| Sky | 3/3 | 33.0초 | 432,887 | 48,631 | 1,899 |

이번 표본에서 Tacto의 첫 작성 시간은 더 길고 입력 합계는 약6.6%, 출력 합계는
약72.1% 많았다. Flow 재사용·0모델 재생 절감률과 섞지 않는다. 실제 명령에서
선택 후보 경로를 관측했고 다른 Tacto GUI alias나 내부 provider 명령은 관측되지
않았으나 실행 attestation은 아니다. CLI·선택 runtime·설정·지침 해시는 불변이었다.
후보의 긴 절대 실행 경로를 명시한 안내는 평소의 짧은 설치 명령과 다르다.

대화는 독립이지만 숨은 전역 context·실제 serving 모델·서버 cache·완전한 초기 UI
동일성·TCC 책임 경계·실제 청구는 입증하지 못했다. `comparison_eligible=false`,
harness exit2를 보존한다. 위 표는 조건을 맞춘 소표본 관측이며 엄격한 제품
우위나 인과적 개선률을 주장하지 않는다. 토큰은 부모 CLI가 보고한 turn usage다.

소스 `8a28650`의 전체3,257검사는 실패·오류0, 제외27로 통과했다. 실제 native
과제는 Save As3회·Finder 정확한 폴더 이름1회·Select All1회를 통과했다.
앱/DMG 공증·Gatekeeper·산출물12검사·보안 검사를 통과한 같은 번들을 세 Mac에
설치했다. 기존 권한·스킬 링크·백그라운드 실행·Dock 숨김을 확인했다. 로컬
설치본의 native7검사와 세션 수리·문서 readback·취소·관측 paging도 통과했다.
원격 native GUI 과제는 이번 batch에서 수행하지 않았다. 공개 release와 Vault
세션은 바꾸지 않았다. 초기 후보의 회귀2건, 전경 전환 시행과 늦은 저장 파일
관측은 실패/미확인 기록으로 보존했다.

공개용 익명 집계: [2026-11-06 rc.22 JSON](benchmarks/2026-11-06-rc22.json).
원본은 로컬 `reviews/goal-resume-20261106-finder/`와
`reviews/tacto-rc22-candidate4-20261106/`에 보존했다. 개인정보가 들어갈 수 있는
도구 원문·호스트 경로·설정 파일 내용은 공개 집계에 포함하지 않는다.

## 2026-11-06 실제 Finder 메뉴 준비의 반복 검사 비용

| 같은 종류의 준비 검사 | 수정 전 관측 | 수정 후3회 관측 |
|---|---:|---:|
| 이벤트당 validation | 2,092ms | 23~31ms |
| 필요한 headroom | 21,153ms | 407~537ms |
| 새 폴더 생성 | 이벤트0회로 거절 | 3/3, 디스크에 각1개 |

초기 전체2124노드 검사는 유지하고, 내용 입력이 없는 임시 메뉴 준비의
각 이벤트에서는 같은 창과 변경 가능한 문맥을 직접 읽는다. 수정 후 메뉴
작업은2.86~2.92초였으며 전면 witness와 정리도3/3 통과했다. 서로 다른 시점의
프로파일이므로 전체 작업의 인과적 속도 개선률이나 Sky 대비 성능으로 쓰지 않는다.
이 첫 시험의 이름 지정 실패는 rename_verified=false로 보존했다. 후속으로
준비가 유지되는 동안 menu.text 입력과 Return을 한 번 수행해 최초3/3,
리뷰 수정 후1/1 정확한 디스크 이름·새 항목1개·전면 witness 보존·정리를
확인했다. 이름까지 포함한 메뉴 작업은3.76~4.90초였다. 새 단계나 모델 요청은
없다. 원본은 `reviews/goal-resume-20261106-finder/verified-named-folder/report.json`.
root가 raw/wrapper·디스크 개수·소스 불변·입력 보존 표본·정리를 재검증해
`reviews/goal-resume-20261106-finder/verified-new-folder/report.json`에 보존했다.
전체3,249검사는 실패·오류0, 조건부 제외27로 통과했다. 이는 회귀 검사 수이며
실제 사용자 앱 과제의 성공 횟수와 합산하지 않는다.

## 후보 런타임을 선택한 독립 비교

`examples/product_comparison.py --tacto-launcher /absolute/runtime/launcher/tacto`
는 선택한 CLI와 그 스킬을 Tacto arm에 명시하고 Sky arm의 도구 지침은 그대로
둔다. 선택한 실행 파일·helper·Python·모듈·스킬의 해시도 각 arm의 source
manifest에 포함한다. 외부 fixture worker 모드에도 이 선택을 전달한다.
기본값은 기존 설치 경로 선택을 유지한다. 이 옵션은 설치나 권한을 바꾸지 않는다.
각 반복 직전에도 후보를 재확인하며 없어졌거나 손상됐으면 fixture·모델을
실행하지 않는다. 실행 중 없어졌으면 결과를 invalid로 남긴다. 기본 설치본과
후보 모두 AppleScript·직접 native 입력을 사용하지 않는 같은 도구 제한을 갖는다.

실제 signed worker의 metadata-only preflight에서 선택된 후보와161개 runtime
파일을 확인했다. 모델·native 과제 입력은0이며 비교 결과가 아니다. 명시적 선택은
agent가 그 경로를 실제 사용했다는 증거가 아니므로 execution attribution은
false로 둔다. 실제 비교에서는 tool trace도 검토하며, 이전 설치본을 새 소스의
성능으로 부르지 않는다. 원본: `reviews/goal-resume-20261105-comparison-selection/`.


## 2026-11-05 실제 Preview의 AX 밖 이미지 읽기

소유한 난수 점수 PNG를 실제 Preview에서 열고, 서명된 rc.22 후보 CLI의
`capture --helper --window`로 그 창만 캡처했다. 같은 창의 scoped AX tree에
정답 숫자가 없는 것을 확인한 뒤 이미지 질문1회를 했다. 기대 숫자는 질문이나
파일명에 넣지 않았다. 정답과 창·임시 파일 정리는 host가 별도로 확인했다.

| 백본 | 이미지 정답 | 창·파일 정리 | 모델 요청 |
|---|---:|---:|---:|
| Codex CLI 기본값 | 3/3 | 3/3 | 각1회 |
| Claude CLI 기본값 | 3/3 | 3/3 | 각1회 |

일반 앱의 이미지 읽기 기능 검증이다. native 픽셀 입력·전체 에이전트 과제·
Tacto/Sky 성능 비교로 계산하지 않는다. 매번 새 이미지/창을 사용했고 모델·
서버 cache·시작 상태를 동등하게 통제하지 않아 시간/토큰 우위를 계산하지 않는다.
선택된 서명 후보의 source는78cd467이며 아직 공증·설치하지 않았다. 이미지
질문에 쓰인 세 provider 모듈의 해시는 여섯 실행에서 같았다. 첫 로컬 실행은
main 모듈을 사용했고 나머지는 고립 작업본을 사용한 점도 원본에 남겼다.
원격 june-mba 최초 시도는 잠긴 화면을 늦게 발견해 실패했다. preflight 보강
후에는 bootstrap·모델 호출 없이0.3초 이내 SKIP했고 실패를 성공으로 바꾸지 않았다.
게임 점수는 직접 생성한 일반 fixture 데이터이며 인증 challenge가 아니다.

코드: `examples/probes/preview_visual_read.py`. 측정 당시 runner와 원본은
`reviews/goal-resume-20261105-preview/`에 보존했다. 이 결과는 위 배경 Save As의
입력 보존이나 문서 저장 receipt 검증과 별도다.


## 2026-11-05 실제 지도 시각 입력과 이미지 요청의 고정 비용

OpenStreetMap을 개인 브라우저와 분리된 headless Chromium에서 열고 이미지로
확대 버튼을 계획했다. 클릭 후 URL 확대 수준15→16과 중심 좌표 불변을
독립 판정했다. 이 버튼은 AX에도 있으므로 AX 밖 콘텐츠나 native Preview
지원의 증거로 부르지 않는다. 아래는 Tacto 내부 백본 기능 검증이며 Sky 비교가 아니다.

| 자연 상태 반복 | Codex | Claude |
|---|---:|---:|
| 수정 전 성공 | 2/3 | 3/3 |
| 수정 후 성공 | 3/3 | 3/3 |
| 수정 후 각 작업의 모델 요청·클릭 | 1·1 | 1·1 |

수정 전 실패는 버튼 밖 지도 변화로 전체 캡처가 달라진 `stale_capture`였다.
선택적으로 host가 원래 DOM 버튼·좌표·영역 픽셀·수신 문맥을 다시 확인하면
무관한 화면 변화를 허용한다. 원래 전체 화면 비교는 기본값으로 유지한다.
실제 지도의 버튼과 떨어진 타일만 바꾼 보정 시험도 양쪽1/1 통과했고
`target_revalidated=true`였다. 반투명 버튼 뒤 지도까지 바꾼 최초 보정2건은
버튼 영역 픽셀도 바뀌어 거절됐으며 실패 원본을 보존했다. 스크립트의 실패
종료 코드가0이던 결함도1로 수정했다. 자연 반복에서 개선 경로가 매번
필요했던 것은 아니므로 이 성공률 차이만으로 개선의 인과성을 주장하지 않는다.

별도로 같은 PNG와 같은 실제 질문을 고정해 Codex 이미지 요청을 전후 각3회
실행했다. 이미지 요청이 텍스트 요청의 최소 안내 설정을 빠뜨려 전체 agent·도구
지침을 전달하던 분기를 고쳤다. 이미지 첨부와 응답 schema는 유지한다.

| 동일 이미지·질문 | 수정 전 | 수정 후 |
|---|---:|---:|
| 정확한 확대 버튼 좌표 | 3/3 | 3/3 |
| 입력 토큰 중앙값 | 16,612 | 7,575 |
| 출력 토큰(매 요청) | 28 | 28 |
| 모델 응답 시간 중앙값(초) | 7.89 | 5.53 |

표본 입력은 약54.4% 감소했다. 프롬프트와 이미지 SHA가 모두 같고 각 측정 중
관련 소스가 불변임을 확인했다. 전3회 후3회 순서이며 serving 모델·실제 청구·
서버/호스트 부하·cache를 통제하지 않았으므로 인과적 시간 개선률이나 전체
에이전트 비용 절감률은 아니다. Codex의 serving 모델은 미보고, Claude의
`claude-opus-5-5`는 provider 보고값이다. 서로 다른 tokenizer의 수치를 동등한
청구 단위로 취급하지 않는다. 최소 안내를 적용한 후의 실제 지도 보정 시험도
클릭1회·모델1회로 통과했다.

원본과 모든 실패: `reviews/goal-resume-20261105-public-map*/`,
이미지 고정 전후: `reviews/goal-resume-20261105-image-context/report.json`.
기존 Tacto/Sky 실제 앱 비교와 아래 미완료 범위는 이 시험으로 대체하지 않는다.



## 2026-11-05 큰 native 관측: 페이지 탐색과 이름 검색

소유 AppKit240버튼 창에서 첫 관측에 없는 Item239를 정확히1회 누르고 결과를
읽는 과제다. 일반 사용자 앱 성공률이나 Sky 비교가 아닌 실제 모델 기능 검증이다.
수정 전 고정 판단은 다음 관측 수단이 없어 입력0으로 실패했다. 명시적인
continuation 뒤 direct/signed 고정 판단, Codex/Claude 실모델 모두 독립 수신
JSON(count1, Item239)·본문 결과·정리·전경/포인터 표본 검사를 통과했다.

동일 fixture/목표를 유지하고 정확한 이름 검색을 추가한 후의 단회 결과다.
각 행은 별도 초기화했고 입력은1회뿐이며, 추가 페이지 읽기는 앱 입력이 아니다.

| 모델 요청 경로 | 페이지 탐색 요청 / 초 | 이름 검색 포함 요청 / 초 | 관측 입력 합계 전→후 | 출력 합계 전→후 |
|---|---|---|---|---|
| Codex | 9 / 62.9 | 7 / 51.8 | 83133→64773 | 377→385 |
| Claude | 9 / 35.6 | 7 / 31.0 | 52031→40805 | 870→919 |

두 경로 모두 continuation7→4회와 이름 검색1회로 실제 동작했다. 개별 작업
프롬프트의 host o200k_base 계수는 최대3,495로 설정4,000 이내다. 이 예산은
provider 전체 context나 serving tokenizer의 사용량을 뜻하지 않는다. 입력은
캐시를 포함한 CLI 관측 합계다. Codex에서는 로컬 경로 거절9/7건의 토큰이
미관측이며 이를0으로 채우지 않았다. Claude usage는 uncached/cache 생성
보고를 합산한 값이다. 청구 검증·모델 간 동등성·일반 절감률은 주장하지 않는다.
각1회이고 일부 peer 검사와 실행 시점이 달라 시간의 인과 효과도 확정하지 않는다.
요청 감소에도 출력 토큰은 증가했음을 유지한다.

별도 direct/signed 고정 판단에서 literal presence 확인은 모델을 부르지 않고
runtime이4페이지를 읽어 실제 결과를 찾았다. 이 결과는 전체 tree 변화 비교나
Save/송신 인과 증거가 아니다. 깊이·큐·노드 제한과 물리 타이핑 미검증도 유지한다.

원본 연결·전후 소스 해시·각 실행·usage:
`reviews/goal-resume-20261105-observation-paging/report.json`.


## 2026-11-05 rc.20 실제 앱 3쌍

rc.20(a13cc55) 설치 검증 뒤 빌드·회귀가 끝나고 peer가 idle인 상태에서
Calculator→소유 TextEdit 과제를 새 대화로 3쌍 교차 실행했다. 요청 모델
gpt-6.1-sol/medium, arm 제한180초, 독립 본문 판정과 정리를 유지했다.
양쪽3/3 성공, 정리6/6 완료, 소스·런타임·CLI 설정은 전후 같았다.

| 회차 | Tacto 초 | Sky 초 | Tacto 총 입력 / 출력 | Sky 총 입력 / 출력 |
|---|---|---|---|---|
| 1 | 59.2 | 32.1 | 171831 / 1029 | 144034 / 596 |
| 2 | 53.0 | 30.8 | 144727 / 1033 | 144299 / 611 |
| 3 | 59.2 | 49.1 | 171860 / 1038 | 144101 / 671 |

관측 평균은 Tacto57.1초/Sky37.3초다. 3회 합계 총입력488,418/432,434,
캐시입력441,088/391,296, 새입력47,330/41,138, 출력3,100/1,878이다.
Tacto는 여전히 평균 약1.53배 시간이 걸렸고 총입력 약13%, 새입력 약15%,
출력 약65%가 많았다. rc.19보다 수치가 낮아도 과거 부하 중첩·표본3회·서버
변동 때문에 변경의 인과 효과나 일반 절감률로 주장하지 않는다.

세 Tacto 실행은 skill 읽기와 경로 확인, Calculator session1회와 문서 session1회로
끝났다. 문서 실패의 본문 상태 marker를 확인해 별도 재관찰 세션을 만들지 않았다.
JSON Flow 작성과 대화형 입출력 왕복 비용은 남는다. 저장이 과제가 아니므로
본문 일치를 Save 성공으로 간주하지 않는다.

이 실행에서는 peer 회귀/컴파일 중첩을 관측하지 않았다. 그러나 하네스의
`agent_responsibility_not_isolated_or_observed` 제외 사유가 남아 엄격 비교 적격은
false, 종료코드는2다. 실제 serving 모델·숨은 context·서버 캐시·청구 동등성도
확인하지 않았다. 따라서 관측 결과를 완전한 제품 성능 동등 비교로 포장하지 않는다.

원본: `reviews/tacto-rc20-candidate2-20261105/source/reviews/2026-11-05/product-comparison-20261105-173046.jsonl`.
요약·실행 전후 증거: `reviews/goal-resume-20261105-rc20-comparison/`.

## 2026-11-05 후보 문서 경로: 독립 동작 검증(성능 동등 비교 아님)

실제 소유 TextEdit의 빈 문서에 `TACTO 비교 테스트 7781`을 입력하도록, 앞선
대화가 없는 에이전트에게 후보 skill과 signed source CLI 경로만 제공했다.
Codex 첫 시도는 계약 불완전으로 실패(본문 빈 값), 정리는 완료했다. 후속
Codex 시도는 skill 읽기와 session1회로 완료했고 새 본문 상태 marker를 읽어
추가 observe 없이 끝냈다. guide1회·schema 오류0회, 독립 oracle·정리 통과다.
관측25.2초, 총입력71,787/cache64,640/새입력7,147/출력529다.

별도 Claude(현재 PATH의 ASX shim, CLI 보고 모델claude-opus-5-5)도 같은 문서
과제를 완료했다. Bash 명령2개로 session2회·guide1회를 사용했고 새 marker를
확인했다. 관측43.1초, CLI 총입력80,935/cache읽기69,666/cache생성11,261/
새입력11,269/출력1,737이다. 별도의 ~/.local/bin/claude 직접 비조작 요청은
조직 접근 비활성으로 실패했다. 실행 경로가 다르므로 전체 Claude 불가라고
일반화하지 않는다.

두 성공은 같은 시각/설정/도구/바이너리의 교차 반복이 아니다. 요청 모델도
Codex gpt-6.1-sol/medium과 Claude CLI default로 다르고 serving 모델은 미확인이다.
시간·토큰의 동등성이나 후보 변경의 인과 효과를 주장하지 않는다. 이 시험의
목적은 새 skill과 본문 확인 결과를 실제 서로 다른 에이전트가 사용하는지
확인하는 것이다. 본문 일치는 Save나 해당 입력의 인과 영수증이 아니다.

원본과 한계: `reviews/goal-resume-20261105-document-forward/report.json`(실패),
`reviews/goal-resume-20261105-document-forward-contract/report.json`(Codex 성공),
`reviews/goal-resume-20261105-claude-document-forward/report.json`(Claude 성공).


## 2026-11-05 rc.19 실제 앱 3쌍: 작업 성공과 시간 측정 한계

Calculator→TextEdit 과제, 독립 cold-start 에이전트, 요청 gpt-6.1-sol/medium,
arm별 180초 제한을 유지했다. Tacto와 Sky 모두 3/3 성공, 소유 자료 정리도
6/6 완료했다. 소스·설치 런타임·CLI 설정은 실행 전후 같았다.

| 회차 | Tacto 초 | Sky 초 | Tacto 총 입력 / 출력 | Sky 총 입력 / 출력 |
|---|---|---|---|---|
| 1 | 80.4 | 37.4 | 280500 / 1616 | 144213 / 601 |
| 2 | 69.7 | 32.3 | 221723 / 1454 | 141943 / 584 |
| 3 | 61.8 | 27.2 | 206250 / 1328 | 121167 / 464 |

관측 평균은 Tacto70.6초/Sky32.3초, 새 입력 합계는76,665/59,675다.
**이 시간은 통제된 성능 비교가 아니다.** 실행 중 peer의 subprocess 회귀와
Swift 컴파일(대략15:46~15:49 KST)이 겹쳤음을 후속 확인했다. 검사 연기
안내가 실행 중인 peer에게 전달되지 않았다. 속도 개선·정확한 배율·수정의
인과 효과를 이 수치로 확정하지 않는다. 원격 serving 모델·숨은 context·과금
동등성도 미확인이다. 작업 판정은 모두 통과했지만 비교 적격은 false이므로
하네스 종료 코드는2였다. rc.18 실패를 소급 성공으로 바꾸지 않는다.

세 Tacto 실행 각각에서 schema 오류 안내1회, guide 출력3회, session 명령3회,
`commit_unverified`1회가 관측됐다. 이는 후속 최적화의 구체적 대상이다.
별도 모델0·쓰기0의 설치본 Calculator 읽기 세션3회는 준비0.54~0.69초,
전체1.87~2.02초였다. helper 모드를 변경하지 않았고 전체 과제의 시간 귀속을
직접 측정한 것은 아니다. 따라서 런타임 시작만으로 차이를 설명하지 않는다.

원본: `reviews/2026-11-05/product-comparison-20261105-154545.jsonl`.
요약·한계: `reviews/goal-resume-20261105-rc19-comparison/report.json`.
읽기 측정: `reviews/tacto-rc19-20261105/read-session-profile.json`.


## 2026-11-05 rc.18 실제 앱 교차 비교: 3쌍

Calculator에서 23×19를 계산하고 소유 TextEdit 문서에 437을 입력하는 작업을
독립 에이전트로 3쌍 실행했다. 요청 모델은 gpt-6.1-sol, reasoning medium,
arm 제한은 180초이며 순서는 Tacto→Sky / Sky→Tacto / Tacto→Sky였다.

| 회차 | Tacto 결과 / 초 | Sky 결과 / 초 | Tacto 입력 / 출력 | Sky 입력 / 출력 |
|---|---|---|---|---|
| 1 | 실패 / 71.8 | 성공 / 38.2 | 176459 / 1087 | 140899 / 596 |
| 2 | 성공 / 83.9 | 성공 / 40.4 | 254012 / 1592 | 142700 / 593 |
| 3 | 성공 / 67.5 | 성공 / 32.6 | 203930 / 1399 | 142743 / 596 |

입력은 캐시를 포함한 총 입력이다. Tacto는 2/3, Sky는 3/3 성공했다.
첫 실패는 선택 패널 표시 오류가 `document_text`를 차단한 것으로 접근 로그에서
확인했다. 경로 quoting 오류로 분류하지 않는다. 6개 실행의 소유 테스트 자료
정리는 완료됐고 실행 전후 런타임·설정은 같았다. 비교 조정기는 소스의 signed
worker, 실행 arm은 설치 rc.18을 사용한 혼합 구성이다. 실제 serving 모델,
숨은 컨텍스트·서버 캐시·과금의 동일성은 확인하지 못했으므로 엄격 비교 적격
표시는 false로 유지한다. 선택 패널 수정의 성능 효과는 이 결과로 주장하지 않는다.

원시 기록: `reviews/2026-11-05/product-comparison-20261105-151055.jsonl`.
환경과 원인 증빙: `reviews/goal-resume-20261105-rc18-comparison/`.


> 2026-10-20 이름 이전: 제품·arm·도구·fixture 라벨을 Tacto로 정규화했습니다. 재측정이 아니며 모든 토큰·시간·성공·실패 수치와 원래 결과의 한계를 유지합니다. 서명 ID 표기도 현재 이름으로 정규화한 것이며 당시 바이너리를 다시 서명했다는 뜻은 아닙니다. [이전 범위](tacto-branding.md#측정-기록의-이름-이전--2026-10-20).

`examples/task_benchmark.py`의 fixture 실행은 Tacto의 알려진 page target을 사용하는 로컬 작업 평가다. 실제 앱 routing, arbitrary 저장 witness discovery, 범용 computer-use 성공률은 측정하지 않는다.

실행 결과의 `requested_provider`는 설정값이다. `provider`, `model`, `provider_calls`, `model_usage`는 관측한 값만 사용한다. 계측이 없으면 provider/model은 null이며 토큰·비용을 0으로 채우지 않는다. 공통 집계는 route attempt를 한 번만 더하며 비용의 currency/basis 및 관측 누락 개수를 유지한다.

Codex 제품 UI는 trusted node tool로 별도 실행하고 원시 결과를 보관한다. 외부 결과를 검증해 정규화하려면 다음 명령을 사용한다.

```sh
.venv/bin/python examples/task_benchmark.py --manifest task-manifest.json import-baseline raw-result.json --artifact-root raw-artifacts
```

기록은 기존 결과 필드(`task_id`, `condition_id`, `system`, `run_id`, `status`, `elapsed_seconds`, `provider`, `model`, `evidence`)와 `environment`를 포함한다. `system`은 `codex-computer-use`다. `external_observation`에는 다음 필드를 넣는다.

```json
{
  "transport": "trusted node_repl sky RPC",
  "execution_mode": "fixed-actions",
  "artifacts": [{"path": "run.json", "sha256": "실제 파일 바이트의 SHA256"}]
}
```

`execution_mode`는 `fixed-actions` 또는 `autonomous-model`이다. 성공 결과의 각 evidence 항목은 기존 `oracle`, `passed`, `observed` 외에 `artifact`로 등록된 raw 파일 경로를 참조해야 한다. 조건 hash는 요청·fixture·시간 예산·oracle을 포함하며 manifest와 일치해야 한다. artifact는 root 안의 상대 경로만 허용하고 실제 bytes hash를 다시 확인한다.

이 검사는 파일 무결성과 기록 형식을 확인한다. outcome의 `observed`가 작업 성공을 입증하는지는 operator가 원시 자료와 독립 oracle을 검토해야 한다. 형식상 통과만으로 작업 결과를 재판정하거나 양쪽 시스템의 동등성을 선언하지 않는다. `summarize`는 fixed action·자율 모델·unknown cohort를 분리하고 누락/실패/unavailable 실행을 보존한다. 외부 기록을 제공하지 않으면 baseline은 unavailable이며 실행한 척하지 않는다.

Runner의 기존 `diagnostics.model_calls`는 planner 함수 호출 수다. 계획 검증 후 재질문이 있으면 실제 모델 요청은 더 많을 수 있다. 논리 모델 요청과 route 시도 수는 `provider_calls`와 `model_usage`를 사용한다. 실패 결과의 provider protocol 오류도 작업 실패와 함께 보존하며 성공 실행으로 제외·대체하지 않는다.

## Native 메뉴 자율 비교의 범위

2026-10-01의 `reviews/2026-10-01/run-owned-autonomous-menu.py`는 시험용 실험 adapter를 비교한다. 동일한 로컬 CLI planner·goal·65초 한도·12 screen 한도와 새 NativeMenuFixture를 사용한다. 순수 AX와 공개 Sky API를 각각 click/read로 제한하고, 메뉴 루트 role을 정규화한다. AX는 app menu tree도 읽고, SDK는 반환된 indexed text를 정규화한다. 두 관측의 내용이 같다는 보장은 없으며 production Driver 전체 capability 비교가 아니다. SDK에는 narrow probe가 없어 추가 get_app_state를 사용하며 root RPC 서비스 대기시간도 작업 기한에 포함된다. 성능 동등성이나 private 제품 구현의 증거로 쓰지 않는다.

목표는 Direct Command→Responder Command를 각각 한 번 실행하는 것이다. General의 done/ok와 별도로 독립 native host 카운터가 direct=1, responder=1, make-key=0이고 기록된 command 순서가 정확히 두 항목이어야 과제 성공이다. 전경·pointer·focus 표본 감사와 기능 성공은 따로 판정한다. 과거 adapter 준비 실패/서비스 timeout/provider 거절 기록을 보존하고 같은 source cohort의 반복 결과로 덮어쓰지 않는다. 실제 Codex serving model은 CLI가 제공하지 않아 unknown이다.

이 비교에서 동일 click 재계획이 내용 변경 뒤에도 반복으로 오판되는 결함을 발견했다. General은 click/menu 계획의 반복 검사에서 관측 content fingerprint도 확인한다. 변화 없는 재시도는 계속 중단하며, dispatch 오류 뒤 자동 입력 재시도나 최종 완료 증거는 제공하지 않는다.

2026-10-01 click/read 한정 동일 source-set의 8회는 AX/Sky × Claude/Codex × 2회다. AX는 두 provider 모두 0/2, SDK는 모두 2/2였고, 8회 모두 전경·pointer·focus 표본 감사가 통과했다. 이 결과는 owned fixture의 background responder-chain 차이를 드러내며 native runtime의 해결을 뜻하지 않는다. 기록은 `reviews/2026-10-01/verification/autonomous-menu-comparison.json`에 있고, 준비·provider·서비스 실패를 포함한 전체 23회도 보존했다.


2026-10-04에는 Tacto의 production Python `prepare_window`를 후보에 포함하고 AX-only
준비 힌트를 제거한 새 자율 cohort를 실행했다. 두 경로는 같은 목표·65초·12 screen·
새 fixture·독립 counter와 정확한 command 순서 oracle을 사용한다. SDK는 공개
`get_app_state`/`click`만 사용한다. SDK 서비스를 사전 준비한 8회는 Tacto Claude2/2,
Codex2/2, SDK Claude1/2, Codex2/2다. SDK Claude 실패는 Direct1 이후 명시 모델
거절로 Responder0이며 FAIL로 유지한다. 이전 서비스 대기 실패 3회와 bootstrap
거절도 별도 cohort로 보존한다. 이를 Tacto의 기능 우위나 전체 제품 동등성으로
해석하지 않는다.

원시 경로·SHA256·조건·40 selected sources·provider telemetry·표본 감사는
`reviews/2026-10-04/verification/autonomous-menu-preparation-comparison.json`에 있다.
선택 소스는 전체 dependency closure가 아니며 실제 사용자 caret/동시 typing,
대표 앱·장기 복구를 입증하지 않는다. SDK 서비스 대기가 기한에 포함되고 관측
형식과 adapter overhead가 달라 latency 동등성도 주장하지 않는다. 거절 진단/UX
수정은 GUI trial 이후이며 frozen trial과 후속 회귀 결과를 구분한다.

## TextEdit 저장 비교의 정확한 바이트 판정

`examples/product_comparison.py`의 `textedit_save_owned`는 새 결과부터
`oracle_contract: textedit-save-exact-utf8-v2`를 기록한다. 파일 바이트와
소유 문서 본문을 요청한 문자열에 정확히 대조하며, 공백·줄바꿈·BOM·본문의
Unicode 정규화를 허용하지 않는다. 경로 표시의 NFC 정규화와 본문 비교는
서로 다른 계약이다. 일반 읽기 과제의 기존 공백 정규화는 별도로 유지한다.

파일 판정은 Tacto receipt를 재사용하지 않는 독립 oracle다. 현재 사용자 소유의
일반 파일·단일 링크·4MiB 상한·no-follow/non-blocking open과 읽기 전후
descriptor/path metadata, canonical path, harness directory identity를 확인한다.
본문 미관측은 빈 문자열로 바꾸지 않는다. 이 readback은 관측된 저장 상태이며,
Save가 직접 파일을 썼다는 생산자 인과 증거나 향후 파일 불변성을 제공하지 않는다.

이전 cohort의 oracle는 공백을 정규화했다. 기존 원시 결과를 새 oracle의 성공으로
재분류하거나 덮어쓰지 않는다. 같은 소스·초기 상태에서 양쪽을 새 contract로
다시 실행해야 정확한 저장 성공률을 비교할 수 있다. 새 저장 oracle의 회귀 검사는
임시 파일과 주입된 문서 응답만 사용하며 실제 TextEdit GUI 실행이 아니다.

## 비교 실행의 환경과 종료 상태

Runner는 fixture 준비 전에 화면 잠금/세션 미관측을 확인하며, 이 경우
setup·모델·cleanup을 실행하지 않는다. setup 뒤 환경이 달라져도 모델을 시작하지
않고 소유 fixture를 보존한다. 실행 후 잠금 또는 세션 미관측이 보이면 cleanup
입력을 보내지 않으며 `comparison_eligible: false`로 기록한다.
이미 시도한 작업의 `failed`/`timeout`/`passed` 상태는 유지한다. 환경의 전후
관측은 실패 원인이나 실행 중 잠금이 없었다는 증거가 아니다.

현재 비교 실행기는 `tacto.session.lock_state`의 잠금·on-console·login-done
지표를 사용한다. 이 플랫폼에서는 로그인한 콘솔의 잠금 key가 생략될 수 있어,
key 부재에 console=true와 login_done=true가 함께 있을 때만 unlocked로
해석한다. 이 해석은 best-effort platform inference이며 앱별 입력 승인이나
원자적 잠금 확인이 아니다. 실제 key가 malformed이거나 세션/지표가 없고,
off-console·로그인 미완료인 경우는 GUI 준비·모델·cleanup 전에 중단한다.
명시적으로 잠긴 경우도 중단한다. Apple의
[console-user 상태 구현](https://github.com/apple-oss-distributions/xnu/blob/main/iokit/Kernel/IOService.cpp)의
positive console/login 지표와 private lock 비교, 현재 플랫폼의 읽기 전용
CGSession/IOConsole 지표 및 peer의 자체 signed fixture 실측을 참고했다.
동일한 Codex CLI를 호출했다는 사실만으로 실제 serving model·reasoning·
계정 상태·앱 초기 상태가 같다고 주장하지 않는다.

### 기존 기록의 비교 전제 감사

`examples/audit_product_pairs.py`는 GUI나 모델 호출 없이 기존 JSONL을 읽는다.
task/rep마다 각 arm이 정확히 한 번 있어야 하며, 잠금 관측·안정된 source
manifest의 실제 digest·oracle·layer 준수·초기 전경을 확인한다. 성공·실패
과제 결과는 그대로 보존하고, 중복 중 성공 행만 골라 짝짓지 않는다.

`recorded_prerequisites_match`는 기록된 전제 부분집합의 일치만 뜻한다.
이 감사는 독립적인 초기 task state와 실제 serving model/configuration을
추가로 요구하며 `same_conditions_verified=false`를 유지한다. 성공률이나
성능 비교 수치를 계산하지 않고 입력 원본과 SHA256을 새0600 보고서에 기록한다.
기존 JSONL에는 새 필드를 소급 추가하지 않는다.

```sh
PYTHONPATH=. .venv/bin/python examples/audit_product_pairs.py \
  reviews/2026-10-10/product-comparison-20261010-160542.jsonl \
  --output /tmp/tacto-pair-audit.json
```

2026-10-10의 네 cohort를 감사한 결과는
`reviews/2026-10-10/product-pair-prerequisites-audit.json`에 있다.
appearance/save cohort는 초기 전경이 행에 없었고, Finder 두-arm cohort는
초기 전경이 달랐으며, Finder 후속은 Tacto 한쪽만 실행했다. 원래 task oracle
결과는 보존하지만 이들 기록만으로 동일 조건 비교가 증명됐다고 선언하지 않는다.

알 수 없는 과제·빈 `--only`·0 이하 reps는 실행 전에 오류다. 새 report는
0600으로 배타적으로 생성한다. CLI는 모든 결과가 eligible PASS이면0,
FAIL/TIMEOUT/INVALID가 있으면1, 그 밖의 미실행·비교 제외가 있으면2로 끝난다.
`--list`는 실행하지 않고0으로 끝난다. 기존 기록에는 새 필드를 소급 추가하지 않는다.

## 외형 설정 읽기 실제 재실행

`reviews/2026-10-10/product-comparison-20261010-155619.jsonl`: Tacto1/1·Sky1/1
oracle PASS, 양쪽 Light. Tacto42.3초/입력149159/캐시126848/출력458,
Sky53.9초/입력118828/캐시104960/출력366. 이는 원시 usage이며 비용으로
환산하지 않는다. Codex CLI0.161.0을 사용했으며 실제 serving model은 미관측이다.

양쪽 before/after manifest SHA256은
`41ebde9ff344b8f999d1ef193d5d906992e2bc5779db52cf9e7bd33ed20a2c2b`로
동일하다. source_changed=false, process exit0, comparison_eligible=true,
잠금 전후 관측false, activation0건, cleanup은 요청하지 않았다. layer/shortcut
검사는 기록된 호출의 휴리스틱이며 전체 실행 경로의 인증이 아니다.
전경 앱/캐럿/사용자 동시 typing의 동일 초기 상태·보존은 입증하지 않는다.

이 과제는 `legacy-ui-state-v1` 읽기 oracle로 실행했다. 새 정확한 저장 oracle,
Dark/Auto 설정, 반복 성공률, 지연·비용 우위나 전체 제품 동등성의 증거로
확대하지 않는다. 이전 실패 cohort는 보존한다.

## 정확한 TextEdit 저장 상태의 실제 비교

`reviews/2026-10-10/product-comparison-20261010-160030.jsonl`: 신규 private
directory의 소유 `.txt` 문서로 `textedit-save-exact-utf8-v2`를 양쪽1회 실행했다.
Tacto1/1·Sky1/1 PASS, 각 행에서 disk_exact=true/window_exact=true이며 자체
문서 cleanup은 completed다. Tacto41.2초/입력168253/캐시152704/출력450,
Sky49.5초/입력204135/캐시195968/출력804. 입력/cache를 비용으로 환산하지 않는다.

양쪽 manifest SHA256은
`41ebde9ff344b8f999d1ef193d5d906992e2bc5779db52cf9e7bd33ed20a2c2b`로
동일하다. source_changed=false, process exit0, comparison_eligible=true,
전후 lock=false, TextEdit hidden=false, layer/shortcut 휴리스틱 false다.
파일은0600이다. Tacto activation0건, Sky2건(cmuxterm·Blender)이 관측됐으나
이 이벤트를 agent가 유발했는지 사용자의 앱 전환인지 판별하지 못했다.
포커스 침해의 인과 증거나 성능 우위로 사용하지 않는다.

이번 기록은 정확한 최종 저장 상태를 증명하며 명시 Save와 autosave의
생산자 기여를 분리하지 못한다. source-format/첨부 보존, 사용자 caret,
동시 typing, 여러 앱·백본·반복의 완료 증거도 아니다. 이전 저장 실패 기록을
삭제하거나 이번1회 성공으로 안정성 완료를 선언하지 않는다.

이 시행에는 초기 전경 앱 bundle 기록이 없으므로 양쪽 전경 상태가 같았다고
주장하지 않는다. 시행 후 runner는 witness의 `initial_frontmost_bundle`을
보존하도록 보강했다. 이 후속 변경은 위 frozen manifest에 포함되지 않으며
기존 행에 값을 추정해 추가하지 않는다. 이 메타데이터만으로 caret/selection
또는 실행 중 사용자의 입력 수신이 증명되는 것도 아니다.

## Finder 새 폴더 재실행: 실패 유지

`reviews/2026-10-10/product-comparison-20261010-160542.jsonl`은 Tacto0/1,
Sky1/1이다. Sky44.9초에 `untitled folder` 한 개가 실제 directory로 확인됐고,
Tacto165.7초 뒤 `children=[]`로 실패했다. 양쪽 process exit0이며 CLI도
전체 실패를 exit1로 반환했다. 자기 시험 폴더 cleanup은 양쪽 folder_removed다.

Tacto 최종 응답은 New Folder disabled와 창 준비 timeout을 보고했다. 이는 모델의
보고이며 원시 native 실패 코드/phase별 trace를 보존한 진단은 아니다. 따라서
readiness 전체-tree 예산, key/responder 상태 또는 다른 원인 중 하나로 확정하지
않는다. 다음 수정 전에 bounded 준비 진단과 실제 tool 실패 근거를 확보해야 한다.

Full SHA256은 양쪽 before/after 모두
`a2241b5073e3c2a2f7727dfe5fe062f5da95122e2d376b1b1e0a2d2acfa764cf`다.
source_changed=false, comparison_eligible=true, 전후 lock=false다.
이 flag는 환경/소스 검사를 뜻하며 완전한 초기 상태 동등성을 인증하지 않는다.
초기 전경은 Sky `godot#75802`, Tacto Finder로 달랐으므로 동일 초기 상태의
성능 비교라고 주장하지 않는다. activation은 Sky3건, Tacto1건으로 원인 미확정이다.

Tacto 원시 input603060/cache555776/output2139, Sky input205396/cache186624/
output668이다. 반복 준비에 든 실제 요청량을 보존하며 비용으로 환산하지 않는다.
이번 실패를 이전 저장/외형 읽기 성공으로 덮어쓰지 않는다.

### signed 비교 host와 모델 프로세스의 경계

새 native 비교 host는 `tacto eval --product-comparison`으로 signed launcher 아래
실행한다. `_driver`는 inherited helper만 사용하며 Python Driver로 대체하지
않는다. `--check-backend`는 helper의 앱 metadata와 capability만 읽고, task
setup·모델·입력을 실행하지 않는다. `--list`는 경로와 무관하게 목록만 표시한다.

```sh
tacto eval --product-comparison --check-backend
tacto eval --product-comparison --list
```

Calculator setup의 menu/clear가 error·unknown·미지원이면 후속 입력이나 모델을
진행하지 않는다. 아직 직접 AXPress를 사용하는 owned TextEdit cleanup 과제는
signed window/document binding을 구현할 때까지 setup 전에 not_run으로 남긴다.
사용자 문서나 출처가 불명인 창을 닫는 대체 경로를 쓰지 않는다.

모델 자식에서는 TACTO_HELPER_FD·TACTO_LAUNCHER·TACTO_HELPER_TOKEN을 제거한다.
이 환경 정리가 macOS TCC responsible identity를 분리하는 것은 아니다.
현재 signed host에서 spawn된 Codex/Sky의 responsible process는 관측하지
않았으므로 결과의 `agent_responsible_process_observed`는 null이다. task
oracle 결과는 보존하지만 `comparison_eligible=false`와
`agent_responsibility_not_isolated_or_observed`로 제품 비교에서 제외한다.
외부 agent controller 또는 실제 책임 신원 관측과 동일 조건 감사를 구현해야
새 native 제품 비교를 증명할 수 있다. 예전 launcher 밖 cohort와 섞지 않는다.

### 책임 프로세스의 읽기 전용 관측

`tacto.process_responsibility.observe_responsibility(pid)`는 현재 플랫폼의 private
libSystem responsibility SPI와 libproc의 실행 경로를 두 번 읽는다. PID·경로가
달라지거나 API/경로가 없으면 닫힌 unavailable/null 결과를 반환한다.
PPID를 대신 쓰거나 관리자 권한을 요청하지 않으며 argv·환경·문서 내용은
읽지 않는다. ABI는 Chromium의
[macOS process 구현](https://github.com/chromium/chromium/blob/main/base/process/process_info_mac.mm)의
pid_t 반환/인자를 참고했다. private API이므로 플랫폼에 따라 제공되지 않을 수 있다.

```sh
tacto eval --product-comparison --check-responsibility
```

이 명령은 controller와 자체 대기 중인 Python 자식 하나만 관측하고 자식을
종료·회수한다. GUI·모델·원격 요청은 없다. 실제 signed 경로의 두 프로세스는
각각 self-responsible PID와 Python 실행 경로를 반환했다. 기록은
`reviews/2026-10-10/signed-controller-responsibility-probe.json`에 있다.
이는 실제 Codex/Sky의 책임 그래프나 TCC 서비스의 권한 결정이 아니며
comparison_eligible=false를 유지한다. 프로세스 경로의 반복 일치로 실행 중
코드 신원·PID 재사용·후손 책임·동일 모델을 증명하지 않는다.

이 Python probe를 근거로 '실제 model이 Tacto launcher 책임을 상속한다'거나
'실제 model이 Python 귀속이다'라고 단정하지 않는다. 이전 launcher 상속
설명은 가능한 혼입에 대한 가설이었으며 실제 model/Sky 관측은 아직 없다.
probe의 start_new_session=True는 소유 자식의 세션/프로세스 그룹 설정으로
기록하며 TCC 책임 분리로 해석하지 않는다. 자식 정리 timeout은 kill/wait 후
owned_child_cleanup_timeout과 exit2이며 일반 실패의 예외 본문은 숨긴다.


## 실제 Codex 호출의 선택적 프로세스 관측

공통 `_provider_env()`는 Claude 세션 여부와 관계없이 TACTO_HELPER_FD,
TACTO_LAUNCHER, TACTO_HELPER_TOKEN을 모델 자식 환경에서 제거한다. 부모 환경과
사용자 profile·credential은 유지한다. 이는 채널 표지 제거이며 TCC 책임 분리를
증명하지 않는다.

`codex_result(..., process_observations=records)`에 호스트 소유 list를 넘기면
소유 Popen의 주 PID를 요청 중 관측한다. 진단은 ProviderResult와 분리되며
기본 호출에는 관측 스레드가 없다. 최대64회, 읽기 사이0.2초 간격이므로 긴 요청의
전체 구간을 관측하지 않는다. 요청 종료 시 stop 후 최대0.2초 join하고
`observer_stopped`와 `sample_limit_reached`를 기록한다. native read가 늦게
끝나도 반환 snapshot은 바뀌지 않는다. 오류 본문 대신 닫힌 코드만 남긴다.
주 프로세스 종료가 읽기 중 감지되면 그 sample을 버린다. 후손·PID 재사용·
실행 코드 신원·TCC 판정은 이 진단으로 확정하지 않는다. 경로에는 로컬 홈이
포함될 수 있으므로 외부 공유 시 홈 접두어를 치환해야 한다.

실제 기록(비공개 로컬 기록: `reviews/2026-10-10/live-codex-process-observation.json`; 공개 원본 미포함)은
Codex CLI의 도구 없는 산술 요청이 성공하고 독립 정답 검사가 통과한 결과다.
주 프로세스의 실행 경로와 책임 경로는 Codex CLI였으며31회 관측했고
observer 종료·오류 없음·sample 한도 미도달을 확인했다. 경과6.241초,
입력16139/cache12160/출력9 token은 CLI telemetry다. 실제 모델명·비용은
null로 유지했다. owner-only 보고서의 source hash는 호출 전후 일치했다.
이는 signed comparison에서 실행한 native task나 Sky 관측이 아니며
기존 `comparison_eligible=false`를 변경하지 않는다.


## G9 후속: signed 비교의 실제 모델 주 프로세스 관측

두 arm은 공통 `_run_agent`에서 owned process group을 시작하고 timeout·호출자
중단 시 kill/wait한다. prompt는 stdin이며 실제 tool event를 planning-only
ProviderResult로 수용하지 않는다. 주 PID의 선택적 diagnostics를
`agent_primary_process_diagnostics`로 기록하고 기존 null 책임 그래프 및
comparison 제외를 유지한다. 주 PID sample로 후손/Sky/TCC 권한을 추론하지 않는다.
실행 파일 부재는 닫힌 agent_launch_unavailable/not_run으로 보존하며 oracle을
읽지 않는다. 이미 발생한 setup을 취소했다고 주장하지 않는다.

signed launcher는 PATH를 고정하므로 default codex 경로가 실제 미발견이었다.
실패 기록은 `../reviews/2026-10-10/signed-agent-probe-path-unavailable.json`이다.
`--agent-executable ABSOLUTE_PATH`는 평가 호스트가 선택한 실행 파일을 두 arm에
공통 적용하며 PATH/권한/profile을 바꾸지 않는다. 경로 존재·실행 가능 여부가
코드 서명이나 실제 모델 신원 증거는 아니다.

```sh
tacto eval --product-comparison --agent-executable /absolute/path/to/codex --check-agent-responsibility
```

이 명령은 실제 모델 tokens를 쓰는 tool-free 산술 probe다. native 앱 입력이나
Sky 과제는 없다. owner-only 새 report
`../reviews/2026-10-10/signed-live-codex-process-observation.json`에서 oracle PASS,
exit0, source 전후 일치,32 samples/observer stopped/error 없음, Codex 주 PID와
책임 PID 일치를 관측했다. elapsed6.523초이며 실제 model/cost는 null이다.
이는 signed host의 실제 Codex 주 프로세스 관측이고 Sky/후손 책임 그래프나
TCC 판정이 아니다. 전체 G0~G10, 동일 초기 상태/serving model 감사, 대표 앱
반복과 설치 검증을 완료했다고 계산하지 않는다.

후속 Muxa read-only 리뷰 req_18dd258a65ab9a68_5c는 P1/P2 없음이었다.
실측 probe 당시 CLI의 cwd는 controller 저장소 경로를 상속했다. 이후 기존
비교 조건을 유지하도록 transport의 cwd를 /tmp로 명시했다. 두 arm과 probe는
요청 실행 경로·해석 경로·cwd·new-session을 기록한다. 앞선 실측 report는
그 후속 변경 이전 source manifest이며 새 상태 실측이라고 소급하지 않는다.
new session은 POSIX 그룹 정리 범위이며 TCC/asid 분리 증거가 아니다.


## G8/G9 실제 외관 모드 읽기 pair와 정책 구분

2026-10-10 signed doctor는 AX/화면 권한과8개 앱을 확인했다. Calculator는
미실행이었으며 System Settings 창은 관측됐다. 기존 installed signed launcher,
명시적인 Codex 실행 경로, 두 arm 공통120초 timeout으로 appearance_mode를
실행했다. 원시 owner-only 기록은
`../reviews/2026-10-10/product-comparison-20261010-195603.jsonl`이다.
두 arm 모두 독립 defaults 기반 oracle의 Light와 일치하고 process exit0,
source manifest 전후·두 arm 사이 일치, activations[]였다. Tacto46.3초,
Sky40.8초다. CLI telemetry 입력/캐시/출력은 Tacto214245/194048/611,
Sky159423/150016/620이다. 실제 serving model/비용은 관측하지 않았다.
`calls`는 인식한 tool item event 수이며 고유 invocation 수가 아니다.
Tacto shell:tacto12 및 Sky node_repl:js14를 실행 횟수로 해석하지 않는다.

두 arm의 소유 Codex 주 프로세스는64회 observed/self-responsible였으며
observer stopped/error 없음이다. sample_limit_reached=true라 전체 실행
시간 관측은 아니다. Sky 도구 실행 event가 있어도 @oai/sky 후손 책임이나
TCC 판정이 아니다. 첫 foreground는 모두 System Settings였으므로 이 과제를
배경 앱 성공으로 계산하지 않는다. activation0은 pointer/typing 보존을
증명하지 않으며 전체 초기 panel·serving model 동일성은 미검증이다.
전체 command exit2는 oracle 실패가 아니라 비교 제외를 유지한 결과다.

공통 prompt에 활성화·권한/설정/사용자 문서 변경 금지, target-only 읽기,
foreground/pointer/typing 보존과 불가능하면 중단을 명시했다. prompt는
강제 경계나 실제 준수 증거가 아니다. target-only와 pointer/typing 준수를
현재 계측으로 주장하지 않는다. Sky의 과제 의미도 제약이 추가됐으므로
이전 자유 활성화 cohort와 같은 정책으로 묶지 않는다.

Muxa read-only 리뷰 req_18dd25dd65817ed8_60의 P2 두 건을 반영했다.
Tacto 전용 signed --helper 안내를 Tacto ARM_CLAUSE로 옮겨 공통 제약은 계층
중립으로 유지하고 새 runtime_policy=background-v2를 추가했다. auditor는
policy version·제약 원문·positive integer timeout의 기록과 두 arm 일치를
확인한다. 동일 버전의 다른 문구나 같은 문구의 다른 timeout도 제외한다.
기존 원시 결과에 새 버전을 소급하지 않는다. 신규 감사
`../reviews/2026-10-10/appearance-pair-prerequisites-audit.json`은
run_not_eligible/runtime_policy_not_recorded를 보존하며 비교율을 계산하지
않는다. 실기 source는 후속 정책/auditor 수정 이전 cohort다.
관련 회귀81개가1.017초에 통과했고 추가 실제 model 요청은 없었다.

전체 G0~G10 완료 기준은 유지한다. 다음 실제 검증은 초기 상태와 입력
보존 관측, Sky 후손 책임/외부 실행 경계, signed owned TextEdit cleanup 및
다양한 앱·백본 반복이다. 이 읽기 pair로 select·저장·전송·장기 복구·설치
완료를 대신하지 않는다.


## G7/G8 후속: signed 문서 창의 부재 관측

TextEdit owned cleanup의 direct AXPress와 부재 검증을 signed 경로로 옮기기
위해 `document_window_status` 읽기 전용 API를 추가했다. 요청은 정확히
`type`, `target=com.apple.TextEdit`, `document_token`이다. launcher·helper가
다른 필드/대상·미지/만료 token을 거절하며 Python은 capability 및 응답의
정확한 field set/token/state/same_process_verified=true를 검증한다.
응답은 open/closed 또는 닫힌 unavailable 오류이며 경로/본문을 포함하지 않는다.

pin은 PID+launch stamp+CFEqual window+selectedPath와 초기 CGWindowID를
기록한다. 동일 프로세스의 성공한 AXWindows 열거 두 번과 선택 경로/창 일치를
검사한다. 경로 변경·중복·재열림·프로세스 재시작·읽기 오류는 closed가 아니다.
최소화돼 AX에 있는 창은 open이다. AX에서 빠진 창은 optionAll의 CG 목록에서
같은 PID/ID가 남아 있지 않은지 두 번 확인한다. 다른 Space나 ordered-out
창이 CG에 남으면 unavailable이다. window ID 없음·CG 목록 읽기 실패/과대/
malformed·화면 기록 권한 없음도 unavailable이며 권한을 바꾸거나 요청하지 않는다.
이 구현은 CGPreflightScreenCaptureAccess를 closed의 보수적 전제로 사용하므로
그 권한이 없는 환경에서는 closed를 제공하지 않는다. 무관한 malformed CG
항목도 결과를 거절한다. 상태는 관측 시점의 증거이며 이후 변경을 막지 않는다.
6초 logical deadline/abort를 읽기 사이 확인하고 이전 deadline을 복원한다.
이미 실행 중인 AX/CG native read를 강제 취소하는 보장은 없다.

닫힘 관측은 token을 유지한다. 다른 호출이 stale로 token을 폐기했으면 미지
token을 closed로 추론하지 않는다. TracingDriver는 live 결과를 전달하되
상태/token을 trace에 저장하지 않는다. TraceDriver는 capability를 제거하고
unavailable을 반환한다. 과거 closed를 현재 파일 정리 권한으로 재생할 수 없다.
본문·UI 입력·활성화·파일 삭제·저장 receipt를 이 API가 수행하거나 승인하지 않는다.

Muxa read-only 리뷰 req_18dd263a18033720_64의 P1 '다른 Space의 창을 closed로
오판'을 위 CG pin/전체 Space 확인으로 수정했다. 후속
req_18dd26516919dad0_65는 P1 해소/P2 없음이었다. 실제 Swift handler 주입
테스트는 off-Space/권한 없음/CG 실패·malformed/ID 없음과 기존 경로/프로세스/
읽기·deadline/abort/재열림을 검증한다. 기존 document text/RTF 경로도 유지했다.

전체 build.sh와 launcher/bundle strict 서명 검증은 성공했다. installed signed
backend는 새 evidence.document_window_status와8개 앱을 보고했고 doctor는
기존 AX/화면 권한·세션 준비 완료였다. 해당 owner-only report는
`../reviews/2026-10-10/document-window-status-backend.json`이며 source 전후 일치다.
이 report는 build/capability 확인이며 실제 문서 open→close나 file cleanup
실행 결과가 아니다. native 닫힘 실측과 signed owned cleanup 통합이 다음 작업이며
현재 comparison의 TextEdit 미실행 gate를 해제하지 않았다.
전체 G0~G10의 대표 앱/백본·인과적 저장/전송·동일 조건 비교/설치 완료 기준은 유지한다.


## G3/G6/G7/G8 후속: signed owned TextEdit 편집과 닫기 실측

`examples/probes/signed_owned_textedit.py`는 private0700 새 디렉터리·exclusive
파일을 만드는 평가 fixture다. `open -g`는 fixture bootstrap에만 사용하고
pin·전체 본문 readback·scoped observe·close는 inherited signed helper를 사용한다.
필요 capability가 없으면 파일 생성 전 거절한다. 성공한 pin은 빈 본문·완전
읽기·선택 경로와 연결한다. helper의 NFD 한글 경로는 NFC로 비교하고 두 경로의
실제 regular-file inode 일치도 확인한다. 이름 비교만으로 소속을 추정하지 않는다.

첫 pin 실패 뒤 현재 소유 문서를 조회해 빈 본문/NFD 경로를 확인했다.
`owned-document-initial-pin-failure.json`의 cause_verified는 이 문자열 비교
결함의 확인 범위다. 첫 reply stream 전체를 기록하지 않았으므로 모든 초기
실패 원인을 그 결함 하나로 확정하지 않는다. 보강 범위는
`owned-edit-file-state-and-diagnostic-scope.json`에도 명시했다. 해당 소유
디렉터리의 dev/ino를 host가 명시해 같은 문서를 다시 pin했고 새 파일을 만들지 않았다.
그 다음 닫기 control의 Description이 없어 close_control_unavailable로 중단한
원시 `signed-owned-document-lifecycle.json`도 그대로 보존했다. 두 실패에서
닫기 입력은 없었다.

이름 없는 AXButton에 Subrole을 표시하고 `expect.attribute=Subrole`로 실제
AXSubrole을 클릭 직전에 확인한다. 관측 및 expectation capability를 추가했다.
기존 label이 있는 요소·창·필드의 렌더링은 유지하며 parser의 attribute 경계에
Subrole을 포함했다. Python driver도 renderer와 독립적으로 AXSubrole을 읽는다.
Muxa 리뷰 req_18dd273aaa2acea0_68의 렌더링 범위·direct 검증 P2를 반영했고
후속 req_18dd27662a8b82f8_69는 P1/P2 없음이었다. 두 transport의 label 처리,
changed/missing/disabled/nil close-control 거절을 회귀로 검증했다.

`tacto eval --product-comparison --check-owned-document-lifecycle` 실기는
소유 빈 문서 open/완전한 empty text→window-bound close→같은 process의 AX/CG
closed 관측→artifact 제거에 성공했다. 기록은
`../reviews/2026-10-10/signed-owned-document-lifecycle-closed.json`이다.
이 probe의 FocusWitness는 setup부터 cleanup까지 포함했고 초기 전경 System
Settings/activations[]/source 전후 일치였다. 이 source는 이후 renderer 호환성,
평가 통합 및 read-only retry 후속 이전이다. 과거 보고서를 새 코드 실측으로
바꾸지 않는다. 모델 요청은0이다. pointer/typing 보존은 관측하지 않았다.

`textedit_edit_owned`만 signed setup/readback/cleanup으로 연결했다. ask는
fixture의 정확한 경로를 사용하며 offline --list는 준비 없이 preview를 출력한다.
잘못된 scope/token/truncated/중복 control/unknown effect는 동작 또는 삭제를
진행하지 않는다. close 요청을 반복하지 않으며 post-close의 일시적 unknown은
최대3초 logical poll 동안 읽기만 재검증한다. helper native read 하나가 deadline을
넘길 수 있다. dirty dialog나 deadline까지 미확정 상태는 남겨둔다.
파일 정리는 원래 directory fd에 unlink를 고정하고 UID/mode/dev/ino·단일
regular-file/nlink·예상 entry를 검사하며 recursive delete를 사용하지 않는다.
최종 rmdir 신원 확인은 같은 사용자의 rename과 atomic하지 않다. 소유 artifact
변경/미확정은 보존하며 실패한 fixture를 다음 setup으로 덮어쓰지 않는다.

실제 Tacto model arm은66.1초에 본문 oracle PASS/exit0/source stable였다.
원시는 `../reviews/2026-10-10/product-comparison-20261010-202730.jsonl`이며
initial-empty=true, agent 실행 중 activation0, top CLI 입력306674/캐시267648/
출력1350 tokens다. 이 usage는 nested provider 전체 비용이 아니다.
닫기 요청 후 상태 미확정으로 cleanup=document_status_unavailable_left_as_is,
closed=false/artifact_removed=false를 보존했다. pointer/typing·setup/cleanup
활성화는 그 모델 witness의 관측 범위가 아니다. state oracle 및 tool-event
검사는 actual input producer/layer attestation이 아니며 comparison 제외는 유지한다.

후속 안정된 disk readback에서25 bytes가 정확한 기대 UTF-8과 일치했다.
`owned-edit-file-state-and-diagnostic-scope.json`은 parent identity와 안정된
읽기를 확인한다. 이는 app autosave 또는 close와 구분된 explicit Save 인과
증거가 아니다. UI oracle의 원시 관측은60자 미만의 전체 본문이고 기대 문자열과
정확히 일치했다. 향후 oracle은 whitespace 정규화를 제거한
signed-owned-document-exact-text-v2로 변경했다. 원시 model 실행은 앞선 v1이며
v2의 새 실기라고 소급하지 않는다.

Save/연쇄 TextEdit 과제의 legacy cleanup gate는 유지한다. 실제 편집 뒤
cleanup 미확정의 원인과 개선한 readonly poll 실측, causal Save receipt 연결,
다른 앱·backbone 반복/동일 초기 상태·serving model·Sky 후손/입력 보존/설치 등
전체 G0~G10 완료 기준은 계속 남는다. 관련120개 테스트가5.556초에 통과했다.


## G6/G7 후속: 편집 후 닫힘의 과도 상태 실증

새로운 소유 fixture에만 signed document-token scoped set_value로 host-authored
본문을 입력하고 complete text와 정확히 비교하는 lifecycle probe를 추가했다.
`--owned-fixture-text`는 --check-owned-document-lifecycle에만 허용하고 추가
모델 호출은 없다. write 결과가 unknown이면 입력을 반복하지 않는다.

실제 `../reviews/2026-10-10/signed-edited-document-lifecycle-diagnostic.json`은
open/초기 empty/입력 receiving 검증 뒤 single close에 성공했다. 닫기 직후
native_read_failed, global_window_still_present 두 번을 거쳐 closed가 관측됐고
그때만 artifact를 제거했다. setup~cleanup FocusWitness의 초기 전경은 System
Settings, activations[]였고 source 전후 일치/model requests0이다. 이는 과도
상태에서 읽기만 재검증하는 경로의 실측이며 창 잔존을 closed로 앞당기거나
재클릭하지 않는다. 이전 모델 run의 첫 실패 reply 전체가 없으므로 이 새로운
케이스를 모든 과거 실패의 유일한 원인으로 소급하지 않는다. 과거 미확정
fixture/report를 새 성공으로 덮어쓰거나 그 문서에 입력·닫기를 재전송하지 않았다.

상태 오류의 reason_code는 helper의 고정 매핑과 Python의 정확한 field set/
화이트리스트를 통과한 코드만 보존한다. 알 수 없는 detail은 native_read_failed다.
원시 error/detail·본문·경로가 진단에 들어가지 않는다. effect=not_started는
읽기 전용 상태 query에 관한 값이며 앞선 close가 미실행이라는 뜻이 아니다.
reason_code 자체로 open/closed 또는 permission 원인을 추정하지 않는다.
fixture diagnostics는 token/same_process가 유효한 state만 기록하며 최대64개다.
후속 code는 잘림 표지를 남기고 failure 문자열/매핑 누락 회귀를 추가했다.
원시 실기는 그 telemetry 후속 전 source다. 기존 renderer/close 판정은 그대로다.
Muxa read-only req_18dd2919fa7a3a68_6d는 P1/P2 없음이었다.

전체 build.sh 및 bundle/launcher 서명 확인은 성공했고 서명 식별자·권한 설정은
바꾸지 않았다. 실제 model-agent 편집 후 새 코드 cleanup 반복, causal Save
receipt와 legacy Save/chain task 통합, Sky/다른 backbone 및 대표 앱 반복,
같은 초기 상태/serving model/입력 보존·Sky 후손·설치 검증 등 G0~G10의
완료 기준은 유지한다. 이 host fixture 실기를 모델·전체 비교 완료로 계산하지 않는다.


## G8/G9 모델 편집 pair의 cleanup 재검증

installed signed doctor의 기존 권한·8개 앱·세션 준비를 확인하고
textedit_edit_owned를 Tacto/Sky 한 번씩, 양쪽120초 timeout,
background-v2/signed-owned-document-exact-text-v2로 실행했다. 각각 독립적인
private empty fixture를 열고 정확한 경로만 ask에 전달했다. 원시는
`../reviews/2026-10-10/product-comparison-20261010-210206.jsonl`이다.

두 arm 모두 초기 empty/complete body, 정확한 기대 본문, process exit0,
cleanup completed/closed_observed/artifact_removed=true를 확인했다.
Tacto64.8초·Sky35.2초의 seconds는 agent invocation 구간이며 setup/oracle/cleanup
시간을 포함하지 않는다. Tacto는 global_window_still_present 한 번, Sky는
세 번 뒤 closed로 읽혔다. 이 횟수는 창 해제 타이밍의 진단이며 계층 성능
지표로 사용하지 않는다. close를 반복하지 않고 readonly poll만 했다.
각 model witness의 초기 전경 Settings/activations[]이고 두 arm source manifest는
서로 같고 전후 stable이다. 이 witness는 agent 실행만 관측하므로 setup/cleanup
전체 activation 또는 pointer/typing 보존을 주장하지 않는다.

CLI telemetry 입력/cache/출력은 Tacto311178/282368/1370,
Sky140453/129280/559다. calls(shell:tacto14/node_repl:js12)는 tool item event
수이며 고유 invocation 수나 실행 layer의 완전한 attestation이 아니다.
이 usage는 nested provider 전체 비용이 아니며 actual serving model/cost는
확인하지 못했다. 전체 초기 UI·좌표/선택 상태, Sky 후손 책임과 실제 TCC 판정,
입력 보존은 미검증이다. comparison_eligible=false 및 전체 command exit2를
유지한다. root의 주 프로세스 진단으로 Sky 그래프를 추정하지 않는다.

신규 owner-only 감사
`../reviews/2026-10-10/signed-edit-pair-prerequisites-audit.json`은 run_not_eligible을
보존하며 비교율을 계산하지 않는다. 실제 정확한 본문 및 cleanup의 성공을
전체 동일 조건 비교 완료로 승격하지 않는다. 과거 미확정 fixture/실패 보고서는
그대로이고 이 성공은 새 fixture/new cohort다.

host report에 상태/닫힌 reason_code의 복사본과 truncation 표지를 추가했다.
문서 token·본문·원시 오류는 새 diagnostics 필드에 넣지 않으며 mutable fixture와
alias하지 않는다. 관련91개 회귀가1.992초에 PASS였다. Muxa read-only 리뷰
req_18dd29a2cfa63718_71은 P1/P2 없음이었다. Save/chain legacy gate 및 explicit
Save 인과 증거·추가 앱/backbone·같은 초기 상태/serving model/입력 보존·Sky 후손·
설치 등 전체 G0~G10 완료 기준은 유지한다. 다음 단계는 Save receipt의 실제
signed 실행과 정확한 receiving 증거를 연결하는 것이다.


### 2026-10-17: signed-runtime latency, matched bytecode

A paired local benchmark compares the 91a48a0 runtime with predicate-first
verification and helper-cleanup improvements. Both arms use the same current
standalone builder with checked-hash precompiled bytecode. Common `.pyc` paths
and hashes must match; only the five declared changed Tacto modules are exempt.
The helper and Python CDHashes match; the changed launcher is explicit.

| Measurement | Baseline | Candidate |
|---|---:|---:|
| 앱 목록 조회 (5회 중앙값) | 2.42 s | 0.45 s |
| 화면 관찰 (5회 중앙값) | 2.70 s | 0.65 s |
| 6단계 flow 10회 합계 | 88.36 s | 12.57 s |

Ten positive task pairs use the same six-step Flow, alternating order and
matching initial amount/factor/bonus/phase/control-version/active predicates.
All 20 tasks passed the independent result/commit oracle. Four negative runs
preserve zero commits after a failed Review check and one logical commit after
a failed Finish check. No owned helper remains after each command. Logical
commit counts do not prove exactly one physical input. Both app signatures are
valid before and after, and the source/bytecode manifests remain unchanged.

Total positive-task time falls by 85.8%. This is model-free replay in one owned
fixture on one Mac with warmed filesystem caches. It does not measure agent
authoring, token usage, whole-product superiority or general application behavior.
Startup probes include the entire CLI/helper command and teardown; per-step
verification timing is covered by virtual-clock regressions, not direct trace
timestamps. Verification keeps ordinary settling for outcomes already true
before non-idempotent input, in both Flow and general-walk paths.

Reproduce with `examples/benchmark_runtime_latency.py --baseline /path/to/baseline/tacto
--candidate /path/to/candidate/tacto --output /absolute/new/private-directory
--pairs 10 --launcher-optimized`. Build the baseline from 91a48a0 with the same
current standalone builder; unmatched common bytecode is refused. Source for the
disposable native fixture is `tests/fixtures/NativeRepeatBenchmark.swift`.

The packaging check also found generated `__pycache__` files invalidating the old
app's resource seal. The new builder precompiles before signing and verifies
two actual signed-launcher runs. Owned Python entrypoints use `-B`; both benchmark
arms are precompiled so this fix is not credited as an isolated polling gain.
Related publication regressions: 92 tests passed; independent review approved.


### 2026-10-21: 독립 context·반복·실패율 재집계 (기존 원자료)

새 측정이 아니라 기존 원자료를 바뀐 집계기로 다시 읽은 결과다. 이 표들로
계산기 단발 최고속도나 일반 앱 성능을 말하지 않는다.

도구 변경:
- `examples/repeat_benchmark.py`
  - `freshN` arm(N=0/30/70/100)을 추가했다. agent job마다 독립 ephemeral
    session을 쓰고 resume하지 않으며 workspace도 공유하지 않는다.
  - 기존 `ratioN`은 이전처럼 CLI-resumed 대화 하나를 이어 쓴다.
  - `--reps N`(1..10)으로 모든 arm을 반복한다. 결과는 `rep-NN/<arm>/`에 둔다.
  - 알 수 없는 arm과 실행할 수 없는 agent CLI(`~/.local/bin/<provider>`)는
    fixture 앱을 빌드하기 전에 사용법 오류로 거절한다.
- `examples/summarize_reuse_ratios.py`
  - 출력은 (provider, context, reuse%) 그룹별 runs, passed_runs, failure_rate,
    실패 사유, run별 값, 통과 run의 중앙값, 같은 provider·context의 0% 대비
    변화율이다. provider끼리는 합치거나 비교하지 않는다.
  - 결과가 비었거나 실패한 run만 있으면 `complete`는 false다. 예전 방식의
    `savings_against_zero`는 provider·context가 하나이고 비율마다 통과 run이
    정확히 1개일 때만 계산하고, 그 밖에는 `null`이다.
  - 통과했지만 토큰 수를 모르는 run이 하나라도 있으면 그 중앙값은 `null`로
    둔다. 0으로 채우지 않는다.
  - fresh arm 안에 resumed job이 섞이면 실패로 센다.
- `examples/benchmark_matched_conditions.py`
  - `--reps N`을 추가했다. pair 번호가 반복 사이에도 이어지므로 arm 순서는
    계속 번갈아 바뀐다.
  - arm별 failure_rate와 통과 run의 시간·토큰 중앙값을 보고한다.

**Flow 재사용 비율 (resumed context, 1 batch/비율, codex, 2026-10-13)**

원자료는 `reviews/repeat-ratios-20261013/report.json`, 재집계 결과는
`reviews/2026-10-21/bench-reaggregate/repeat-ratios-20261013-groups.json`이다.
seed 작성과 repair는 각 비율에 포함했다.

| reuse | 실패율 | 시간 | 전체 입력 | 새 입력 | 출력 | 시간 변화 (0% 대비) | 전체 입력 변화 (0% 대비) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0% | 0/1 | 235.4 s | 921,897 | 45,609 | 4,235 | — | — |
| 30% | 0/1 | 291.6 s | 876,855 | 62,775 | 5,678 | +23.9% | −4.9% |
| 70% | 0/1 | 211.1 s | 736,739 | 63,843 | 5,407 | −10.3% | −20.1% |
| 100% | 0/1 | 120.8 s | 286,935 | 30,679 | 3,062 | −48.7% | −68.9% |

30%와 70%에서는 seed 작성 비용(61 s, 107 s) 때문에 새 입력이 0%보다 많다.
비율마다 1회뿐이라 분산과 실패율은 추정할 수 없다.

**동일조건 독립 session 비교 (codex gpt-6.1-sol medium, 원자료별)**

원자료별 집계는
`reviews/2026-10-21/bench-reaggregate/matched-prior-per-report.json`에 있다.
보고서마다 runtime·guide 버전이 다르므로 하나의 표본으로 합치지 않았다.
공개 표에는 arm 이름을 Tacto로 통일했다.

| 원자료 (`reviews/…/report.json`) | arm | 성공/실행 | 통과 run 시간 중앙값 | 전체 입력 중앙값 | 새 입력 중앙값 |
|---|---|---:|---:|---:|---:|
| matched-conditions-20261014 | tacto | 3/3 | 47.6 s | 66,230 | 6,730 |
| | sky | 3/3 | 39.7 s | 137,383 | 18,087 |
| tacto-matched-runtime-20261018 | tacto | 1/3 | 46.4 s | 208,857 | 23,897 |
| | sky | 3/3 | 28.4 s | 156,792 | 17,678 |
| tacto-native-resumption-20261019/matched-native-three-pairs | tacto | 2/3 | 20.0 s | 66,536 | 8,872 |
| | sky | 3/3 | 26.3 s | 137,695 | 19,329 |
| tacto-native-resumption-20261019/matched-fresh-fixture | tacto | 1/1 | 30.6 s | 69,728 | 11,616 |
| | sky | 1/1 | 25.5 s | 137,693 | 17,501 |
| tacto-native-resumption-20261019/matched-capacity-followup | tacto | 1/1 | 21.5 s | 72,765 | 14,909 |
| | sky | 1/1 | 61.5 s | 135,934 | 30,334 |

이 기록들의 총 실행은 arm별 11회, 합계 22회다. Tacto는 11회 중 3회 실패했고
Sky는 11회 모두 통과했다. 대신 tacto arm의 전체 입력은 대부분 sky arm의 절반 수준이다.
2026-10-18 runtime만 예외로 tacto 입력이 더 많다. 시간은 보고서마다 우세가
바뀐다.

**미측정**
- fresh context에서의 Flow 0/30/70/100% 비교: 도구만 준비했고 실행하지 않았다.
- 같은 조건의 반복(reps ≥ 3) 분포와 실패율 신뢰구간.
- claude provider의 matched 비교.
- Windows에서의 agent 비교. Windows는 replay 정확성만 CI와 live로 확인했다.
- 실제 과금, serving model 동일성, 서버 cache 상태.

새 live 측정에는 다른 사용자가 조작하지 않는 macOS 화면이 필요하다. 이번에는
사용 중인 foreground를 보존하기 위해 실행하지 않았다.

**측정 시간 줄이기: paired 모드** (`codex-tacto-paired`)
- fresh context에서는 agent job끼리 대화를 공유하지 않고, job마다 fixture를 새로
  준비한다. 그래서 0/30/70/100% 배치를 네 번 돌리지 않고, 한 반복 안에서
  job마다 fresh agent 실행 1회와 Flow replay 1회를 측정한 뒤 비율별로 합성한다
  (`summarize_reuse_ratios.compose_paired`).
- seed 작성 1회와 repair 1회를 모든 비율이 나눠 쓴다. 비율 >0에는 seed를,
  바뀐 컨트롤(job 7 이후)을 쓰는 비율에는 repair를 한 번씩 청구한다.
- 한 job 안에서 두 실행의 순서는 job마다 번갈아 바뀐다. fixture는 실행 내내 commit을
  지우지 않으므로, 두 모드는 같은 입력에 서로 다른 물리 job id(T01-A, T01-F)를 쓴다.
- 비율별 결과는 같은 행과 seed·repair를 나눠 쓰므로 서로 상관돼 있다. 한 반복은
  표본 1개이지 4개가 아니며, `savings_against_zero`는 paired에서 계산하지 않는다
  (`null`). 생성되는 요약 JSON의 limits에도 이 점과 서버 cache 미측정을 적는다.
- 30% 근사는 시간만 빌린다. job 9 자신의 replay가 실패하면 그 비율은 실패다.
- 한계: 30%의 첫 변경 후 replay(job 9)는 job 7에서 측정한 실패 시도와 남은 구간
  시간으로 대신한다(`approximated_first_changed_replay`). 네 비율을 따로 실행한
  것이 아니라는 점을 limits에 기록한다. resumed 모드는 job이 대화를 이어 써서
  합성할 수 없다.
- 예상 시간(2026-10-13 원자료 기준: agent job 20–27 s, seed 61–107 s, repair
  23–30 s, replay 1–4 s):

| 방식 | 반복당 | 3회 |
|---|---:|---:|
| freshN 네 arm 따로 (agent 20, seed 3, repair 3) | 약 15분 | 약 45분 |
| paired (agent 10, seed 1, repair 1) | 약 6–7분 | 약 20분 |

fresh 세션은 매번 지침을 새로 읽으므로 agent job이 위 값보다 길 수 있다. 이 표는
벤치마크를 돌리는 데 드는 예상 시간이지, 제품이 빨라졌다는 측정이 아니다.
30%를 실제 시나리오 그대로 엄격히 공개하려면 그 비율의 첫 변경 후 복구를 따로
측정하거나, 근사값을 분리해 표기한다.

```
uv run python -m examples.repeat_benchmark --output <새 디렉터리> --reps 3 --arms codex-tacto-paired
uv run python -m examples.summarize_reuse_ratios <디렉터리>/report.json --output <요약.json>
uv run python -m examples.benchmark_matched_conditions --output <새 디렉터리> --reps 3
```


### 2026-10-21: paired fresh-context 실측 (3 반복)

새 실측이다. 설치된 Preview 18(v0.1.0-preview.18)과 owned native fixture에서
`codex-tacto-paired`를 3회 반복했다. 약 22분 걸렸다(23:05–23:27).

원자료는 `reviews/2026-10-21/paired-live-2305/report.json`, 요약은 같은 폴더의
`summary.json`이다.

- 30개 job 모두 agent와 replay 양쪽이 통과했다(60행, 실패 0).
- source manifest는 3회 모두 실행 전후가 같았다.
- 비율별 값은 같은 행에서 합성한 것이다. 서로 상관돼 있고, 반복 1회는 표본 1개다.
- 30%의 첫 변경 후 replay 시간은 job 7 값을 빌렸다(†).

| reuse | 실패율 | 시간 중앙값 | 전체 입력 중앙값 | 새 입력 중앙값 | 출력 중앙값 | 0% 대비 시간 | 0% 대비 새 입력 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0% | 0/3 | 279.0 s | 725,278 | 109,470 | 5,266 | — | — |
| 30%† | 0/3 | 323.4 s | 845,630 | 117,432 | 7,596 | +15.9% | +7.3% |
| 70% | 0/3 | 217.7 s | 562,300 | 62,459 | 5,467 | −22.0% | −42.9% |
| 100% | 0/3 | 145.4 s | 350,143 | 40,937 | 3,943 | −47.9% | −62.6% |

반복별 시간은 다음과 같다(초).

| reuse | 반복 1 | 반복 2 | 반복 3 |
|---:|---:|---:|---:|
| 0% | 297.2 | 273.9 | 279.0 |
| 30%† | 274.5 | 323.4 | 354.5 |
| 70% | 156.7 | 217.7 | 244.4 |
| 100% | 78.3 | 145.4 | 173.1 |

구성 요소별 측정값:

| 구성 요소 | 측정값 |
|---|---|
| fresh agent job (30회) | 시간 중앙값 26.6 s, 범위 20.7–46.3 s; 전체 입력 중앙값 70,763, 새 입력 8,658 |
| replay (30회) | 시간 중앙값 1.23 s, 최대 3.3 s (복구 구간 포함) |
| seed 작성 (반복당 1회) | 44.7 s / 106.5 s / 140.1 s; 전체 입력 92,161 / 299,637 / 358,623 |
| repair (반복당 1회) | 15.8–20.7 s; 전체 입력 50,280–70,699 |

해석:
- 10개 job 규모에서는 seed 작성 비용이 크고 반복마다 크게 흔들린다. 그래서 30%는
  0%보다 시간과 토큰이 더 든다. 손익분기는 30%와 70% 사이에 있다.
- job 하나를 replay로 바꾸면 약 25 s와 새 입력 약 8.6k가 줄어든다. seed와 repair
  비용을 감안하면, 같은 Flow를 쓰는 job이 많을수록 절감이 커진다.

미측정:
- 4개 비율의 독립 실행
- claude provider
- 실제 과금, serving model 동일성(모델 보고 없음), 서버 cache 상태
- matched 비교 반복

## 2026-10-24: 새 독립 세션의 Tacto / Sky 3과제

`reviews/goal-resume-20261024-matched-actual/report.json` 및
`independent-audit.json`, 각 arm의 private `stdout.jsonl`이 원본이다.
고정한 설치 런타임은 rc.6이며, 요청 모델 `gpt-6.1-sol`, reasoning `medium`,
180초 제한, 각 실행 새 ephemeral 에이전트·빈 작업 폴더·새 fixture process와
데이터 폴더를 사용했다. bonus on/off/renamed-button 각 1쌍, 순서는 Tacto/Sky,
Sky/Tacto,Tacto/Sky다. fixture 설정 시간은 제외하고 에이전트의 안내 읽기와
작성·실행 시간은 포함한다. Flow 재사용 벤치마크가 아니다.

| 과제 | Tacto 결과·초·새 입력 | Sky 결과·초·새 입력 |
|---|---|---|
| bonus_on | 성공 · 29.11 · 6,676 | 성공 · 34.48 · 18,273 |
| bonus_off | 성공 · 22.47 · 10,523 | 성공 · 72.89 · 17,117 |
| renamed_button | 성공 · 25.42 · 6,048 | 성공 · 28.03 · 8,996 |
| 합계 | 3/3 · 77.00 · 23,247 | 3/3 · 135.40 · 44,386 |

입력 전체/cache/new/output 합계는 Tacto 207,567/184,320/23,247/1,564,
Sky 412,514/368,128/44,386/1,764다. 새 입력은 CLI 입력 전체에서 cache-read를
뺀 값이며 청구액이 아니다. 중단·실패한 task arm은 없고 각 fixture는 oracle의
정확한 결과·단일 commit·비활성 상태 확인 후 종료했다. source subset·선택한
런타임·guide·실제 CODEX_HOME config·초기 fixture 값은 전후 동일했다.

각 Tacto arm은 완료된 고유 tool item ID 기준 shell2회, 각 Sky arm은 shell1회와
node_repl/js5회였다. 이는 API 내부 dispatch 수나 동일한 복잡도의 호출 수라는
뜻은 아니다. 관측 차이는 여러 관찰·입력을 한 Flow/세션에 묶는 방식과 함께
나타났으나, 이 표본만으로 토큰·시간 차이의 원인이나 범용 우위를 확정하지 않는다.
공통으로 프로필의 지원하지 않는 설정 2개 경고가 CLI stream에 있었고 작업 실패로
집계하지 않았다. 사용자 프로필 설정은 변경하지 않았다.

**엄격한 제품 비교 판정은 제외(`comparison_eligible=false`)다.** 실제 serving
model은 stream에 보고되지 않았고, 숨은 context·서버 cache·모든 foreground/caret
동등성·동시 사용자 입력 보존·실제 과금은 검증하지 않았다. 요청 조건 일치는 true,
실제 task oracle 양쪽3/3이라는 범위를 구분한다. 각 과제1회인 소유 fixture 결과를
실제 사용자 앱·다중 백본의 일반 성공률이나 안정적인 속도/비용 절감률로 쓰지 않는다.

### 실제 Calculator → TextEdit 과제 (별도 cohort)

`reviews/2026-10-24/product-comparison-20261024-225521.jsonl`은 서명된
소스 checkout fixture worker로 준비·검증하고, 독립 cold-start Codex 세션이
실제 앱을 조작한 기록이다. 설치 rc.6의 exact-DMG 실기 기록은 아니다.
두 arm 모두 Calculator 표시437과 소유 TextEdit 문서 본문437을 독립 확인했고
소유 문서 정리를 완료했다. 명시 Save는 요구하지 않았다.

| arm | 결과 | 시간 | 전체 입력 / cache / 새 입력 / 출력 |
|---|---|---:|---|
| Tacto | 성공 | 106.3초 | 471,439 / 435,968 / 35,471 / 1,761 |
| Sky | 성공 | 26.1초 | 99,350 / 89,856 / 9,494 / 530 |

양쪽 source subset은 안정적이었고 cold-start 요청과 새 빈 작업 폴더 증거가
있다. 그러나 실제 serving model/책임 경계는 검증하지 못했고 Tacto 실행 동안
시험 앱·설정·로그인 창 사이 전경 변경7건이 관측돼, 누가 변경했는지나 동시
입력 보존을 증명하지 않는다. 양쪽 comparison_eligible=false, 전체 명령 exit2를
유지한다. 단일 과제이며 모델은 공통 상속 프로필의 CLI default 요청이었다.
앞의 고정 모델 fixture 비교와 합산하거나 일반 성능 우위로 해석하지 않는다.

Tacto의 완료된 고유 도구 item은 tacto7/기타shell7이었다(legacy calls 합계28은
started/completed 중복이며 고유14개 집계와 구분한다).
문서 범위 작업이 run 경로로 라우팅되면서 안내 여러 개와 긴 native-window-input
문서를 읽었고, description 대신 desc를 써야 하는 JSON 오류도 수정했다.
이 흐름의 입력 부담을 줄이기 위해 document-scoped session 및 필요한 안내를
같이 반환하는 경로를 구현·검증한다. 이 기록은 변경 전 실패·비효율 증거로
보존하며, 개선 구현만으로 속도 향상이 입증됐다고 하지 않는다.

### document session 소스 기능 검증과 새 모델 시행

`reviews/goal-resume-20261024-document-session-native/report.json`은 새
`session --document`를 서명된 소스 실행기로 시험한 기록이다. 소유 TextEdit
문서 입력·독립 본문 확인과 정리를 완료했다. 모델0회, 실제 Save 요청 없음,
0.90초이며 persistent commit receipt가 없으므로 session exit1/commit_unverified를
유지했다. 본문 일치와 저장·생산자 인과 증거를 분리한다.

새 스킬/런타임을 명시한 별도 실제 Codex 시행
`reviews/goal-resume-20261024-chain-source-guide/report.json`에서도 Calculator437와
소유 TextEdit437을 확인하고 정리했다. 84.98초, input236607/cache210816/
new25791/output1624, serving model 미보고·청구 미검증이다. 소스·선택 런타임·
안내 subtree는 전후 동일했다. 고정 모델 요청은 gpt-6.1-sol/medium이고 앞의
CLI-default 시행과 조건·런타임이 달라,106.3초와의 차이를 개선 효과로 확정하지
않는다. 동일한 Sky arm을 새 소스로 다시 실행한 비교도 아니다.

첫 문서 시도는 selector 없는 set_value가 범위 검사에서 not_started로 거부됐다.
이후 입력의 commit_unverified와 본문437 재관찰을 로그에 보존한다. stdin Flow
자체와 독립 receiving counter를 기록하지 않은 시행이므로 정확한 전체 입력
횟수·사용자 동시 입력 보존을 증명하지 않는다. 이 발견에 따라 생성 가이드의
read 예제에도 이름 있는 selector를 넣어, edit로 바꾸더라도 selector를 유지하도록
수정하고 생성 예제의 실제 replay/대상 index/저장 미검증 유지 테스트를 추가했다.
이 최종 안내 수정 뒤의 실제 모델 속도는 아직 재측정하지 않았다.

새 스킬의 command_flags 선언과 isolated help 검사는 소스 런타임의
session --document를 확인하고, 이를 제공하지 않는 설치 rc.6와는 호환되지 않음을
정확히 반환한다. 이 구현·안내는 아직 새 설치본으로 배포하지 않았다.

### Claude Code Tacto arm (prepared, no GUI result claimed)

`examples/benchmark_matched_conditions.py --tacto-provider claude` keeps the
same owned-fixture process/data isolation and alternating arm order, but runs
the Tacto arm through Claude Code and the Sky arm through Codex. This is a
cross-backbone descriptive trial, not a matched-model comparison. The default
remains Codex for both arms. Per-arm requested model/provider is persisted,
including aborted runs. Claude settings/global context are not attested, and
provider tokenizers/CLI counters are not interchangeable billing units.
`--profile` records Claude tool timing as unsupported/unknown, never zero.

The actual new-mode preflight passed without starting a fixture/model. A separate
non-UI tool-using Claude CLI probe exited1 with a synthetic
organization_access_disabled error; zero reported usage on that failed request
is not a completed-task cost saving. The signed tool-free Claude request earlier
in this record succeeded through a different route. No Claude/Sky GUI success
rate or paired timing is invented for this prepared mode.


## 2026-11-05: rc.17 모델 arm과 조정자 점유 해제 후 실제 두 앱 과제

Calculator에서 23×19를 계산하고 평가용 TextEdit 문서에 437을 입력했다.
요청 모델 gpt-6.1-sol, reasoning medium, arm당 180초, 새 ephemeral 세션과
빈 작업 폴더를 사용했다. 각 arm은 별도 signed source fixture worker와 새
소유 문서로 준비했다. Tacto 모델 arm은 설치 rc.17(c28b1d9)을 사용했고,
setup/oracle/cleanup 조정자는 후보 source 41854a2였다. exact-DMG 전체
qualification 또는 순수 설치본 evaluator 실행으로 해석하지 않는다.

최초 `reviews/2026-11-05/product-comparison-20261105-141607.jsonl`은 Tacto가
24.7초 뒤 target_busy/not_started로 실패했고 Sky는 준비 실패로 미실행이었다.
조정자의 연결이 앱 lease를 유지한 채 독립 에이전트를 기다리는 충돌을 확인해,
RPC 응답 전에 release_targets로 점유를 넘기도록 수정했다. 연결·문서 pin은
유지하되 이전 관찰과 대기 중 선택·저장패널 정보는 무효화한다. 별도 결함으로
coordination_elapsed_ms 진단 필드 때문에 정상 문서 상태 응답을 버리던 Python
검사도 수정했다. 관련53검사는 실패 없이 종료했고1개는 조건부 제외다.
Claude 피어의 점유 해제 정적 검토에는 높은 우선 지적이 없었다. 이는 native
실행 증거와 별개이며 후보 기능을 설치 rc.17에 소급 포함하지 않는다.

수정 뒤 새 각1회, Tacto 먼저/Sky 나중의 실제 결과:

| arm | 과제 판정 | 초 | 전체 입력 | cache read | 새 입력 | 출력 | fixture 정리 |
|---|---|---:|---:|---:|---:|---:|---|
| Tacto | 계산·본문 모두437 | 71.3 | 238,425 | 213,504 | 24,921 | 1,625 | 완료 |
| Sky | 계산·본문 모두437 | 27.3 | 101,598 | 91,520 | 10,078 | 536 | close control 미발견, 미완료 |

두 agent exit0, source/설치 runtime/실제 CODEX_HOME config/CLI 전후 해시는
동일했고 실행 구간 앱 활성화 전환은 관측되지 않았다. Tacto는 Calculator
Flow schema 오류 뒤 세션을 재시작했고, TextEdit set_value의 commit_unverified
뒤에는 재입력 없이 새 세션으로437을 읽었다. 두 번의 세션 재시작과 안내·관찰
반복을 원본에서 확인했다. 이 표본에서 Tacto가 더 느리고 입력·출력도 많았다.
각 단계 시간이 계측되지 않아 두 재시작이 전체 시간 차이의 얼마를 차지했는지는
확정하지 않는다. 명시 Save는 요구하지 않았으며 저장의 생산자 인과 증거도 아니다.

원본은 `reviews/2026-11-05/product-comparison-20261105-142645.jsonl`과
`product-comparison-20261105-142804.jsonl`, sidecar와 요약은
`reviews/goal-resume-20261105-real-app-comparison/report.json`이다.
`comparison_eligible=false`를 유지한다. 실제 serving 모델·숨은 context·서버
cache·전체 책임 그래프·사용자 typing/caret 보존·실제 청구는 미검증이다.
한 쌍과 고정 순서로 범용 속도/토큰 우위나 인과적 개선률을 주장하지 않는다.
Sky 정리 실패와 별도 빈 문서 lifecycle의 CG 잔존 실패도 보존한다.
