# 전체 목표의 완료 기준과 현재 작업

## 2026-11-06 후속 대기 최적화

읽기가 불필요하게 1초 settle을 갱신하던 문제를 수정하고, 새 expect가 있는
클릭은 즉시 새 관측으로 결과를 확인하게 했다. 텍스트/키/메뉴의 입력 후처리와
검사 없는 단계는 기존 대기를 유지한다. Calculator 안내도 중간 결과를 명시한다.
동일Flow 3쌍에서 클릭6.994→1.938초, 연속 읽기3.408→0.281초, 검사 없는 비교군은
약7초 그대로였다. 최종 native6확인과 전체3,275검사를 통과했다(제외27).
중간 timeout시험1건 실패와 이후 재검사 기록을 보존했다.

새 에이전트 비교의 유효 행은 before Tacto3회/after Tacto2회/Sky3회다. 시간 중앙값
43.8→36.5초, Sky30초로 여전히 격차가 있다. after 첫 시행의 System Settings
활성화1건은 배경 불합격·원인 미확인으로 보존한다. 전체3회 after의35초는 참고값이다.
출력 개선·일반적인 인과 효과·청구 절감·완전한 제품 동등성은 주장하지 않는다.
[상세와 작성 비용](benchmark-records.md), [집계](benchmarks/2026-11-06-replay-readiness-perf.json).

소스85b5702의 rc.24 앱·DMG 공증/Gatekeeper, 산출물12검사·보안 검사를 통과해
세 Mac에 같은 번들을 설치했다. 기존 권한·스킬 연결·백그라운드 실행·Dock 숨김과
설치본 native7검사·세션/본문/취소/paging을 확인했다. 공개 release와 Vault 세션은
변경하지 않았다. 아래 rc.23은 직전 배포 기록이다.

## 2026-11-06 후속 성능 수정

Calculator 첫 Flow가 잘못된 ancestor 형식으로 매번 거절되는 반복을 동료와
확인해 안내/필드 힌트를 수정했다. 새 측정은 수리3→0, 작업3/3을 유지하며
시간 중앙값61.0→41.3초, 입력483,541→382,267, 출력3,187→2,494였다.
같은 후속 대조의 Sky는33.3초, 입력430,704, 출력2,017이다. 입력 부담은
줄었지만 시간과 출력은 더 개선해야 한다. 시간 감소율은 순차 소표본의 관측이며
캐시/부하 인과 통제나 실제 청구를 입증하지 않는다. 전1회의 전경 변화도
불합격으로 보존했다. [상세 측정](benchmark-records.md)을 우선한다.

안내 형식 외 권한·receipt·exit 판정은 유지했다. 기본 관측에서 진단 출력만
줄이고 --timings에 입력 시도/수리/길이 카운터를 추가했다. 같은 코드 tree의
전체3,266검사는 실패·오류0, 조건부 제외27이었다. 소스 cab27d8의 rc.23 앱·DMG 공증, Gatekeeper, 산출물12검사와 보안 검사를
통과해 세 Mac에 설치했다. 같은 번들·서명·권한 유지·스킬 연결·백그라운드
실행·Dock 숨김을 확인했고 로컬 설치본 native7검사와 세션/본문/취소/paging도
통과했다. 공개 release와 Vault 세션은 바꾸지 않았다. 아래 rc.22는 직전 기록이다.

## 2026-11-06 현재 상태: rc.22 세 Mac 설치 완료

고정 소스 `8a28650`의 rc.22를 로컬과 두 원격 Mac에 설치했다. 전체3,257검사
실패·오류0, 조건부 제외27, 소스 불변을 확인했다. 앱·DMG Apple Accepted,
티켓·Gatekeeper·산출물12검사·소스/DMG 보안 검사를 통과했다. 세 기기의 같은
번들·서명·스킬 연결·백그라운드 실행·Dock 숨김·기존 권한 유지를 확인했고
추가 권한 작업은 필요하지 않았다. 공개 GitHub release와 Vault 세션은 변경하지 않았다.

서명 source runtime의 실제 Save As3/3·Finder 정확한 이름1/1·Select All1/1과
정리·전면 witness 보존을 확인했다. 설치본의 로컬 native7검사와 세션 schema
수리·본문 readback·요청자 종료 취소·추가 관측도 통과했다. 원격 GUI 입력
과제는 이 batch에서 수행하지 않았으며 설치/audit와 구분한다.

새 대화·작업 공간·같은 요청 모델의 Calculator→TextEdit 비교3쌍은 양쪽3/3이다.
시간 중앙값은 Tacto57.0초, Sky33.0초, 입력 합계461,607/432,887,
비캐시 입력51,111/48,631, 출력3,269/1,899다. 첫 작성은 여전히 더 느리고
출력 부담도 크므로 작성 경로의 안내 중복과 왕복을 줄이는 작업이 남아 있다.
실제 serving 모델·청구·서버 cache·TCC 책임 경계는 미입증이며 strict 비교로
승격하지 않는다. [측정 기록](benchmark-records.md)과
[공개용 익명 집계](benchmarks/2026-11-06-rc22.json)에 범위와 실패 시행을 남겼다.

이 릴리스가 G0~G10 전체 완료를 뜻하지 않는다. 실제 Preview 읽기 이후의 native
시각 입력, 장기 작업과 실제 서비스 저장·전송의 재개 증거, 첫 작성 비용 개선은
계속 남아 있다. 한 번의 System Settings 전경 전환과 늦게 나타난 저장 파일의
원인은 확정하지 않았으며 해당 시행을 성공으로 바꾸지 않았다. 아래는 시점별 기록이다.

## 2026-11-06 배포 전 통합 기록: Finder 메뉴와 정확한 이름 지정

메인 `d3606f2`까지 커밋·푸시했다. 통합 고립 소스 `731c016`과 메인의
커밋 tree가 같고 다른 작업의 미완성 변경은 그대로 보존했다. 이 고립 소스의
서명 helper/launcher 빌드, 전체3,249검사(실패·오류0, 조건부 제외27),
검사 중 core/tests 소스 불변을 확인했다. 메인에 남은 타 작업 변경을 합친
Swift 컴파일도 별도로 통과했으며 그 바이너리를 실행하거나 배포하지 않았다.

Finder 임시 메뉴 준비는 초기 전체 검사를 한 번 유지하고 이벤트마다 같은
창·main/focus·modal/sheet·chrome 위치를 직접 확인한다. 실제2124노드 창에서
반복 검사는2,092ms에서23~31ms, 필요한 headroom은21,153ms에서407~537ms로
바뀌었다. 서명 시험본의 새 폴더 생성3/3에서 디스크의 새 폴더가 정확히1개,
전면 witness의 본문/선택/키/first responder 보존, 창과 폴더 정리를 root가
원본으로 재검증했다. 메뉴 작업은2.86~2.92초였다. 이 수치는 전체 agent/Sky
비교가 아니다. 별도 act로 이름을 입력하면 임시 준비 해제 때 편집기가 닫히던
후속 실패는 메뉴와 선택 `text`를 같은 유한 실행으로 묶어 고쳤다. 정확한
이름·폴더1개·정리·전면 witness 보존을 최초3/3, 리뷰 수정 후1/1 확인했다.
쓰기 직전과 Return 직전 같은 main window·기한을 다시 확인하고 실패 시 key-up을
최선으로 회수한다. 별도 모델 단계 없이 필요한 메뉴 안내에만 예제를 추가했다.
이 후속은 위3,249검사 이후이므로 새 고정 후보에서 전체 회귀를 다시 한다.
증빙: `reviews/goal-resume-20261106-finder/verified-named-folder/report.json`.
원본: `reviews/goal-resume-20261106-finder/verified-new-folder/report.json`.

Save As/Select All이 아닌 일반 명령마다 시트가 열리기를3초 기다리던 지연을
없앴다. 실제 Select All3/3, 후속 Save As2/2와 준비 검사 수정 후 각1회도
peer가 확인했다. Save As 후속1건은 commit_unverified 뒤 정리 중 파일이 나타났고 재시험은
통과했다. 첫 실패를 보존하고 RTF receipt에 내용·경로 없는 읽기 단계 진단을
추가했다(관련43검사 통과). 원인은 아직 확정하지 않았다. 최종 후보에서
실제 앱 회귀와 새3쌍 Sky 비교를 이어간다.
선택 후보의 실행 경로와 guide를 명시하며 실행 중 후보가 사라지면 비교를
유효하게 계산하지 않는다. 기존 설치본을 새 소스의 성능으로 부르지 않는다.

설치본은 여전히 세 호스트 모두rc.21이다. 공증을 막았던 Vault 공개 경로는
11월6일 재확인에서 HTTP200 JSON으로 복구됐고 기존 인증 세션으로 필요한
공증 필드3개를 읽을 수 있음까지 확인했다. 공증 제출·새 설치는 아직0이다.
고정 후보3(93ffde9)은 빌드를 통과했으나 전체3,257검사에서 새 capability의
helper 전용 분류 누락과 이전 launcher schema 검사2건이 실패해 공증 전에
보류했다. 범위를 삭제하지 않고 지원 backend/optional text를 맞췄다. 직접 AX
드라이버가 text를 무시하던 결함도 --helper 안내로 바로잡았고 관련46검사가
통과했다(조건부 제외1). 서명 소스의 Save As3/3은 receipt·정확한 새 파일·
문서 URL·정리까지 통과했다. Finder는 정확한 이름/정리에는 성공했지만
System Settings 전경 전환이 관측돼 배경 시행은 불합격으로 보존했다.
원인은 미확정이며 전체 검사 종료 후 새 후보4에서 검증한다. 세션 파일·잠금 상태는 바꾸지 않았다. 후보2(78cd467)는
새 Finder/doctor 수정을 포함하지 않으므로 배포하지 않는다. 후보4는 별도로
최종 소스를 고정해 회귀·서명·보안·공증을 거친다. 공개 release는 변경하지 않았다.
아래 절은 각 시점의 기록이며 현재 상태는 이 체크포인트를 우선한다.

## 2026-11-05 후속 통합: 배경 Save As 수신과 실제 Preview

고립 통합 작업본 `da52f7d`의 helper는 peer 최종 소스 `cc93830`과 바이트가
동일하다. 비활성 배경 메뉴에만 기존 창 지정 준비를 한 번 적용하고, 같은
창에 비활성화 이벤트를 보내 앱 내부 활성 상태를 되돌린다. 새 agent JSON은
필요 없다. 준비·실행·해제 상태는 `temporary_preparation`에 남기며 실제
완료는 후속 화면과 receipt로 확인한다. 독립 `prepare_window` 의미는 유지한다.

실제 서명 helper의 TextEdit Save As는 소유 전면 witness 아래3/3 통과했다.
각각 저장 입력1회·새 RTF 본문·같은 문서 URL 전이·상태 복구·창/파일 정리를
확인했고 작업 구간 활성화는0회였다. 원본 probe 전체 판정은 bootstrap의
활성화 때문에 false이며 그대로 보존했다. 작업 구간 성공은 별도 wrapper로
판정했고 원시 로그와 helper 해시까지 재검증했다. 물리 타이핑 보존이나 다른
앱의 메뉴 전체 성공은 이 결과로 주장하지 않는다. 시트가 없는 명령에도3초
기다리는 불필요한 지연은 발견해 별도 최적화·실제 Finder 검증을 진행 중이다.
증빙: `reviews/goal-resume-20261105-saveas/background-fixed/report.json`.

실제 Preview에서 난수 점수 PNG를 열어 서명된 Tacto로 해당 창만 캡처했다.
점수가 scoped AX tree에 없는 것을 먼저 확인한 뒤 이미지 질문을 했다.
Codex·Claude 각각3/3 정답, 창/임시 파일 정리를 통과했다. 새 rc.22 후보의
capture 경로를 사용했으나 후보는 아직 공증·설치하지 않았다. 이 시험은
읽기 기능 검증이며 native 시각 입력·전체 agent 비용·Sky 비교는 아니다.
원본: `reviews/goal-resume-20261105-preview/report.json`, 재현 코드:
`examples/probes/preview_visual_read.py`. 원격 최초 실패와 잠금 preflight SKIP도
보존했다. 설치 rc.21의 doctor가 잠긴 화면을 준비 완료로 보고하던 결함은
`ddc1677`에서 고쳤고 관련38검사가 통과했다. 앱 목록과 잠금 상태를 구분하며
알 수 없는 잠금 상태에 새 차단을 추가하지 않는다.

배포: rc.22 첫 후보는 Python3.13 환경에서 기존 setuptools 누락을 검출해
중단했다. Python3.11로 고정한 후보2(소스78cd467)는 전체3,226검사 실패·오류0,
제외27·소스 불변,190개 Mach-O 타임스탬프·서명·앱 보안 검사를 통과했다.
공증 키 조회는 Vault 공개 경로의 Cloudflare1033와 내부 서버 접속 실패로
중단됐다. CLI status는 unlocked이며 세션 파일·잠금·갱신은 변경하지 않았다.
공증 제출0, 설치0이다. 새 메뉴/doctor 통합 뒤 후보3을 만들며, 위 후보2를
통합 수정까지 포함한 설치본으로 부르지 않는다. 외부 접속 경로를 확인하는
동안 다른 목표 구현·검증은 계속한다.


## 2026-11-05 후속 후보: 동적 페이지와 이미지 요청 비용

실제 OpenStreetMap의 무관한 타일 변화가 전체 캡처 비교를 깨뜨리는 실패를
재현했다. host가 원래 버튼 identity·좌표·영역 픽셀·수신 문맥을 재확인하는
선택 경로를 추가했다. 자연 상태 Codex/Claude 각3/3, 의도적으로 버튼에서
떨어진 타일만 바꾼 실제 앱 보정 시험 각1/1을 통과했다. 버튼 픽셀까지 바뀐
보정 실패2건도 보존했다. AX에도 있는 버튼이므로 G5의 native/AX 밖 콘텐츠
검증을 대신하지 않는다. 실패한 probe의 CLI exit0 결함도 수정했다.

Codex 이미지 질문에서 누락된 최소 안내 설정을 연결했다. 같은 PNG·질문 전후
각3회 좌표3/3을 유지하며 입력 중앙값16,612→7,575를 관측했다.
전후 순서·serving 모델 미보고·부하/서버 cache 미통제 한계는 유지한다.
Sky 비교·전체 제품 시간/비용 절감률은 아니다. 상세는 [측정 기록](benchmark-records.md).
이 후보는 아직 미배포이며, 아래 f593291 상태와 구분한다.

## 2026-11-05 현재 체크포인트: 소스 f593291, 설치본 rc.21

실제 TextEdit Save As 수정은 `2d396a0`에 통합·푸시했다. 후속 `f593291`은
백그라운드 Format 메뉴의 비활성 제목을 확정된 편집 모드 증거와 구분한다.
`menu_enabled`와 `title_current_verified`를 함께 보존하며, 저장 직전에는
같은 문서의 저장 패널 RTF 선택으로 독립 검증한다. 전체 3,217검사에서
실패·오류0, 조건부 제외27이며, 검사 대상 소스의 변경 없음도 확인했다.
이 소스는 아직 앱 배포·재설치에 포함되지 않았다. 설치본은 위 rc.21이다.

별도 전면 시험 앱을 유지한 실제 백그라운드 시험에서 본문·커서·키 입력 수·
first responder가 보존됐다. fixture를 여는 초기 활성화와 snapshot 이후 작업을
시간으로 구분했다. read-only snapshot은 통과했지만 `File > Save As…`는
비활성 메뉴 사전 검사로 거절됐다(run21). 실험적으로 해당 사전 검사를
제외한 run22에서도 AXPress는 `acted`를 반환할 뿐 패널이 열리지 않아
postcondition timeout이었다. 저장 버튼 입력은0회이며 소유 문서·파일은 정리했다.
이 실험 변경은 채택하지 않았다. 이를 백그라운드 저장 성공으로 계산하지 않는다.

다음 작업은 기존 창 지정 키보드 경로를 통한 메뉴 대체 실행과 실제 수신 상태
검증이다. peer는 별도 작업본에서 이를 담당한다. G0~G10 전체 목표는 유지하며,
실제 앱 시각 과제와 백본별 반복·동일 조건 Sky 비교·새 후보 배포도 남아 있다.
물리 사용자 타이핑·원격 모델 과금 취소·서식/첨부 보존·일반 앱 전체 성공은
위 검사로 입증되지 않았다.

증빙: `reviews/goal-resume-20261105-saveas/background-checkpoint.json`,
`foreground-witness/run19-report.json`~`run22-report.json`,
`full-regression-candidate3/shards/final-regression.json`.
아래 절은 각 시점의 기록이며 “현재 설치본” 등은 이 체크포인트를 우선한다.


## 2026-11-05 G7: 실제 TextEdit Save As 수정본3회 통과

고립 작업본에 관측 창 선택 핀·편집 모드 reader·같은 관측의 저장 버튼으로 패널을
읽는 API·문서 URL 전이와 신규 RTF readback을 연결한 `DocumentSaveEvidence`를
구현했다. trace 사용 중 이 연결이 빠지는 결함도 수정했다. 본문·연결 token을
재생용 trace에 저장하지 않는다. 관련153검사와 전체 helper/launcher 서명을 통과했다.

초기 실제 TextEdit 실패에서는 네이티브 응답의
공통 시간 필드 때문에 성공한 첨부 조회를 오류로 처리하던 결함을 고쳤고, 문서
전체 재검증을 속성마다 반복하던 비용을 읽기 시작·종료의 검증으로 옮겼다.
경로 reader가 사이드바 선택 뒤의 단일 열을 처리하지 못하는 실제 NSSavePanel
구조를 재현했다. 파일 항목의 native AXURL 부모에서 현재 폴더를 확인하는 수정 뒤,
같은 코드로 실제 TextEdit Save As3회가 연속 통과했다. 각각 guarded Save1회·
정확한 신규 RTF 본문·같은 문서의 URL 전이·창과 파일 정리·소스 불변을 확인했다.
처음10개 실패/중단 시행도 보존했으며 당시 저장 버튼 입력은0회다.
빈 단일 열 폴더는 여전히 unavailable이고, 비어 있지 않은 열에서도 AXURL의 부모
일치는 최대64개 표본만 확인한다. 이 범위를 전체 폴더·서식·첨부 보존으로 확대하지 않는다.

원본과 집계는 고립 작업본의 `reviews/2026-11-05/textedit-save-as-transition-*.json`,
저장소의 `reviews/goal-resume-20261105-saveas/report.json`이다. 모델 호출0이며
Sky 비교·전체 작업 시간 개선·대표 앱 성공률·배경 작업 성공을 주장하지 않는다.
현재 변경은 개발 작업본에만 있으며 설치본 교체와 전체 목표 완료는 아직 남아 있다.


## 2026-11-05 rc.21 배포 검증 완료

수정 후보 eddb2de는 전체3,171검사에서 실패·오류0, 조건부 제외26으로 통과했다.
앱·DMG Apple Accepted, 티켓·Gatekeeper·보안·최종 산출물 검사를 통과했다.
localhost·june-mba·jiun-mini에 동일 번들을 설치했고 서명·스킬 연결·백그라운드
실행·Dock 숨김·기존 권한 유지를 확인했다. 추가 사용자 조치는 없다.
Vault 세션과 GitHub 공개 릴리스는 변경하지 않았다.

설치본 native7검사(한글 NFC/NFD·암호 입력·클립보드·floating 드래그/크기 조절),
같은 세션의 schema 수리, 문서 본문 상태 확인, 요청자 종료 시 로컬 모델 그룹
정리도 통과했다. 새 CLI 관측 검증에서는 첫 관측에 없던 Item239를 같은
session의 추가3페이지에서 찾았다. 안내1회·Flow 제출1회·수신 입력1회·모델0·
exit0·소유 시험 앱 종료를 확인했다. 이 증거는 Save나 물리 사용자 타이핑
보존을 뜻하지 않는다. 실패한 첫 rc.21 후보도 그대로 보존했다.

배포 원본은 `reviews/tacto-rc21-candidate2-20261105/completion-report.json`,
`fleet-installation-report.json`, `fleet-final-audit.json`, `installed-native.log`,
`installed-observation-session.json`이다. 아래 rc.20/이전 후보 절은 시점별 기록이다.
G0~G10 전체 목표는 계속 진행 중이다. 다음은 실제 TextEdit Save As의 스냅샷·
저장 패널·새 파일/문서 URL 전이를 연결하는 G7 작업이다. 현재 저장 상태 증거를
인과 증거로 바꾸어 부르지 않는다.


## 2026-11-05 G2: 관측에서 생략된 후보의 탐색 연결

기존 token paging은 받은 후보만 나눴다. 실제240버튼 AppKit 창에서 첫 관측의
자식60개 제한 뒤 Item239가 사라지고 다음 후보를 요청할 수도 없음을 재현했다.
입력0·수신 count0의 실패 기록을 보존했다. 후속은 cap을 키우지 않고 생략된
부분을 명시적으로 이어 읽는다. 각 페이지의 obs_id/요소 번호는 새로 부여하며
창·조상 문맥을 유지한다. 오래된 cursor나 바뀐 목록은 이전 위치로 추측하지 않는다.

일반 플래너와 session 모두 연결했다. cursor는 runtime만 보유한다.
session은 입력 전 {"observe_next":true} 또는 지원되는 정확한 이름 검색을
같은 연결·원래 입력 deadline·합산8회 안에서 요청한다. 알려진 이름이면
{"find_in_observation":"exact label"}로 페이지 왕복을 줄인다. 고정 문서는
같은 token과 Document 경로 검증을 유지한다. 검색 일치 수/미완료를 모델에
알려 못 찾음과 관측 제한을 구분한다. 이 탐색은 앱 입력이나 완료 증거가 아니다.

실제 direct/signed 고정 판단 시험 모두 누락된 Item239 입력 정확히1회,
독립 앱 수신 JSON·결과 읽기·입력 표본 UNCHANGED_SAMPLED·소유 앱 종료를
통과했다. 실제 Codex와 Claude도 각각 성공했다. 같은 fixture/목표에서 이름
검색을 연결한 후 두 모델의 logical 요청은 각각9→7회였다. 작업 프롬프트는
모두4,000 host 토큰 이내다. 단회 시간 감소나 전체 제품 절감률로 일반화하지 않는다.
[측정 기록](benchmark-records.md)에 원시 usage의 미관측 범위까지 남겼다.

별도 실제 CLI session은 관측3페이지 추가·안내1회·Flow 제출1회로 누락된
버튼 입력1회를 완료했다. replay의 새 관측/이름 검색까지 실제 연결로 검증했다.

뒤쪽 결과의 literal presence를 기다릴 때는 runtime이 추가 페이지를 읽는다.
실제 direct/signed 각각4페이지에서 결과를 찾아 모델 추가 호출·재입력 없이
검증했다. 전체 before/after tree 비교는 부분 페이지를 변화로 오판할 수 있어
이 탐색을 켜지 않는다. trace 래퍼도 continuation과 presence 옵션을 전달·기록한다.

한계는 페이지당2,500노드/자식60, 깊이25, frontier4,096개다. 초과/미확인 상태를
보고하며 물리 사용자 타이핑 보존·일반 사용자 앱 전체 성공률·Save 인과 증거로
승격하지 않는다. 이 변경은 위 rc.21 배포 검증에 포함됐다.
rc.21 첫 후보의 전체3,171검사에서는 표시 진입점 목록 검사2개가 실패했다.
새 continuation 진입점을 추가하면서 기존 검사 갱신을 놓쳤다. 조건을 삭제하지
않고 읽기 전용 진입점을 명시했고 관련84검사가 통과했다. peer도 수정이 원래
검사 의미를 보존함을 확인했다. 이 후보의 공증·설치는 시작하지 않았으며
`reviews/tacto-rc21-20261105/failed-candidate-checkpoint.json`에 보존했다.
수정된 별도 후보는 위 전체 회귀·공증·설치 검증을 통과했다.

원본·각 실패/성공·모델별 집계:
`reviews/goal-resume-20261105-observation-paging/report.json`.

## 2026-11-05 rc.20 설치 검증 완료

고정 소스 a13cc55의 rc.20은 전체 3,120검사에서 실패·오류0, 조건부 제외26으로
통과했다. 첫 후보의 필드 오류 안내 회귀 5건을 고친 새 후보이며 실패 기록은
보존했다. 앱·DMG 모두 Apple Accepted, 티켓·Gatekeeper 검증과 보안·최종
산출물 검사를 통과했다. localhost·june-mba·jiun-mini에 동일 번들을 설치했고
서명·스킬 연결·기존 앱 조작/화면 읽기 권한을 확인했다. Vault 세션과 GitHub
공개 릴리스는 변경하지 않았다.

설치본 native7검사(한글 NFC/NFD·암호 입력·클립보드·floating 드래그/크기 조절),
같은 세션의 schema 수리(guide1·READY2·모델0·쓰기0), 실제 소유 TextEdit의
입력1회 뒤 본문 상태 확인과 정리를 통과했다. Flow는 exit1로 유지하며 본문
일치를 저장 성공으로 승격하지 않는다. 설치된 signed launcher에서 요청 CLI를
종료한 시험도 소유 합성 provider 그룹 회수·지연 쓰기 없음으로 통과했다
(종료까지0.236초). 실제 원격 생성/과금 취소와 물리 Esc는 이 시험 범위가 아니다.

증빙은 `reviews/tacto-rc20-candidate2-20261105/completion-report.json`,
`fleet-final-audit.json`, `fleet-installation-report.json`, `installed-native.log`,
`installed-session-repair.log`,
`test-installed-document-readback.py.log`, `test-installed-client-cancel.py.log`다.
후속 실제 앱3쌍도 Tacto/Sky 모두3/3 성공했다. 관측 평균57.1/37.3초로
차이가 남으며 엄격 비교 제외 사유도 유지한다. [비교 기록](benchmark-records.md)에
토큰·전체 실행·한계를 보존했다. 이 배포 검증은 G0~G10 전체 목표 완료를
뜻하지 않는다. 아래 과거 절의
“현재 rc.19”, “설치본 E2E 미검증”은 해당 시점의 기록이며 이 절로 갱신한다.

## 2026-11-05 후속: 입력 전 수리·본문 상태·실제 취소 경로

후보 d696a6c/525fb61/ea2a103은 잘못된 selector/check/resource/evidence/binding을
짧은 필드 안내로 돌려준다. 입력 전에 정적 계약이 이미 거절될 경우도 같은
대화형 연결에서 고칠 수 있다. 기존 정책에서 허용한 계약은 더 엄격하게
거절하지 않는다. 실제 signed 세션에서 잘못된 selector와 resource.scope를
고친 뒤 읽기 완료, 안내1회·READY2회·모델0·쓰기0을 확인했다.

고정 문서의 set_value가 commit_unverified이면 같은 native token으로 본문을
한 번 읽어 `TACTO_DOCUMENT_STATE`를 내보낸다. 텍스트/토큰/경로는 marker에
넣지 않으며 요청 본문 일치·남은 단계만 알려준다. Save·writer 귀속·실패 Flow
성공·템플릿 저장을 주장하지 않는다. 실제 소유 TextEdit 입력1회, 독립 본문
판정, 닫힘/임시 파일 제거를 확인했다. probe의 closed/completed 상태명 비교
오류는 원본을 보존하고 읽기 증거로 바로잡았으며 입력을 다시 보내지 않았다.

기본 skill은 rc.19의7,210→4,039바이트, 일반 문서 guide는 같은 경로에서
2,729→1,709바이트다. host o200k_base 표본은 각각1,655→950토큰,
576→369토큰이다. serving tokenizer나 전체 provider context의 절감률이 아니다.
불필요한 공통 안내를 문서 guide에서 빼고 설치/복구/저장 세부를 단계별로 뒀다.

실제 독립 Codex 문서 시험은 첫 시도에서 계약 정보 부족으로 입력 전에 실패했다.
이 기록을 보존했다. 후속 시도는 skill 읽기+session1회, guide1회, marker true,
독립 oracle와 정리 통과였다. 별도 Claude 시험도 실제 TextEdit 과제와 정리를
통과했지만 Bash/Read 도구에서 session2회·guide1회를 사용했다. 모델·CLI 도구·
시점·바이너리가 달라 성능 동등 비교가 아니다. Claude 직접 ~/.local/bin 경로의
조직 접근 비활성 오류와, 성공한 ASX shim 경로를 구분한다. 원본은
`reviews/goal-resume-20261105-document-forward*/` 및
`reviews/goal-resume-20261105-claude-document-forward/`에 있다.

G4 통합 dc93e3b/74f2a85/5011c4d/2bafb03은 요청별 취소, helper Stop 알림,
감시 스레드 수명/비차단 전송, 시작 전 취소 거부를 연결했다. root의 통합140검사와
서명 빌드가 통과했다. 그러나 실제 전체 signed 런처에서 cancel_id 없는 요청자의
종료를 놓쳐 provider가 남는 실패를 발견했다. 0253fde는 EOF/HUP를 취소 프레임과
독립 감시하고 client 종료를 sticky flag로 전달하며 shutdown 정리 시간을 보장한다.
수정 전 실패는 보존했고, peer signed source3회와 root signed source1회 모두
provider 그룹 부재·지연 쓰기 없음으로 통과했다(root0.202초). 새17검사도 통과했다.
원격 생성/청구 중단, 실제 Esc 키 이벤트, 설치본 E2E는 이 증거로 주장하지 않는다.

현재 설치본은 rc.19다. 이 후보를 rc.20으로 고정해 전체 회귀·공증·설치 검증한 뒤,
부하가 겹치지 않는 Tacto/Sky 반복 비교를 진행한다. G2 관측 truncation과 일반
플래너 연결, 실제 Finder/Save 및 시각/장기 복구, G0 동시 사용자 입력 등 전체
미완료 항목은 유지한다. 상세 증거:
`reviews/goal-resume-20261105-session-repair/efficiency-evidence.json` 및
`reviews/goal-resume-20261105-signed-cancel-main-fixed/report.json`.


## 2026-11-05 rc.19 배포와 다음 구현 격차

고정 소스1dd095c의 rc.19 앱·DMG는 Apple Accepted, 티켓과 Gatekeeper 검증,
3,085검사(실패/오류0, 조건부 제외26), 최종 이미지12검사와 보안 검사를
통과했다. localhost·june-mba·jiun-mini의 동일 번들·서명·스킬 연결·기존 권한을
확인했다. 설치본 native7검사와 대화형 연결 수리도 통과했다. Vault 세션은
변경하지 않았다. GitHub 공개 릴리스는 변경하지 않았다.
`reviews/tacto-rc19-20261105/completion-report.json`은 배포 범위의 증빙이며
G0~G10 전체 목표 완료를 뜻하지 않는다. 아래 선택 패널 수정은 이제 이
설치본에 포함된다.

실앱 독립3쌍은 양쪽3/3 성공했지만 peer 회귀/컴파일 부하가 겹쳐 시간은
참고값이다. 원본 실패와 모든 한계는 [비교 기록](benchmark-records.md)에
보존했다. Tacto의 안내3회·session3회·schema 수리1회·입력 뒤 추가 관찰은
반복 비용으로 남는다. 읽기 전용 세션의 실제 준비0.54~0.69초를 확인했으며,
전체 지연을 런타임 시작 비용으로 단정하지 않는다.

G4 후속 소스04c41ed는 `model_cancellation` 범위를 추가한다. 진행 중인 로컬
provider 프로세스 그룹을 취소하고 부분 usage·cancelled attempt를 보존하며,
새 fallback과 validation retry를 막는다. peer 회귀510검사(3제외), root의
독립32검사가 통과했다. 원격 생성·청구 중단은 보장하지 않는다. **서명 런처
내부 진행 요청의 취소와 CLI 취소 연결은 아직 남으며, 이 변경은 rc.19에
포함되지 않는다.** 구독 접근 오류였던 이전 Claude CLI 경로는 현재 비조작
요청에 성공했지만, 명시적 ~/.local/bin/claude 경로와의 동등성이나 실제 GUI
과제 성공은 이 preflight로 증명하지 않았다.

다음 유한 작업 순서는 다음과 같다.

1. G4의 signed launcher/CLI 취소 연결과 실제 자식 회수 검증.
2. 관측 truncation 때문에 61번째 이후 후보가 플래너에 사라지는 G2 경로:
   전체 후보 접근을 위한 좁은 재관측/탐색을 연결하고 실제 큰 목록 검증.
3. 필드별 짧은 schema 수리, 이미 읽은 안내 반복 제거, 같은 문서 연결에서
   입력 후 본문 상태 확인. 본문 일치를 Save/영속성/신규 전송 인과 증거로
   승격하지 않는다.
4. 부하를 분리한 재측정과 Finder 새 폴더·TextEdit 명시 저장·Claude 실제
   에이전트 과제. G0 동시 사용자 입력·G5 실제 앱 시각·G6 장기 중단/재개·
   G7 신규 저장/전송 인과 증거의 미검증 범위도 유지한다.

Lyrics의 가운데 정렬·이전 재시작 좌표 원인은 별도 미확인 사항이다. 다른 앱의
레이아웃 변경을 원래 G0~G10 전체 목표의 필수 P0 기준으로 추가하지 않는다.


## 2026-11-05 선택 패널 표시 실패의 AX 차단 제거

rc.18 실제 앱 비교에서 `document_text`가 `indicator_unavailable`로 입력 전에
차단됐다. 경로 오류가 아니라 선택적인 중단 패널을 표시하지 못한 것이 원인이었다.
`ensureVisibleControl`은 이제 패널 배치를 한 번만 시도하고, 좌표를 읽지 못하거나
다른 Space에 있거나 패널 표시가 지연되어도 AX 작업을 계속한다. 패널 준비를
위한 0.5초 재시도와 추가 0.5초 가시성 대기를 제거했다. 사용자 중단과 잠긴
세션 확인, 실제 픽셀 읽기의 OS 권한은 별도로 유지한다.

문서 선택 실패의 진단도 개선했다. 알려진 운영 오류 4종은 원래의 짧은
코드를 전달하며, 앱의 원문 오류·경로·비밀값은 진단에 추가하지 않는다.
Swift 실행 테스트를 포함한 관련 62개, 실제 signed helper floating 창 테스트
3개가 통과했다. peer의 읽기 전용 검토에서 중대한 문제는 없었다.
이 변경은 개발 소스 검증 결과이며, 기존 rc.18 설치본에 포함됐다는 뜻은 아니다.


## 2026-11-05 floating 창·중복 검증 개선

사용자 보고: floating 오버레이(layer 3)에서 Tacto가 입력 전에 거절했고,
별도 HID 입력으로 크기 조절을 마무리하려 했다. 이전 `layer == 0` 제한을
normal/floating으로 확장했다(cd702ef). 실제 소유 layer 3 창의 CG 조회와
잘못된 소유자 거절 검사는 통과했지만, 이는 크기 조절 성공 증거가 아니다.

후속 독립 검토에서 Python CG layer의 PyObjC 정수 래퍼를 순수 `int` 검사로
거절하는 결함을 발견했다. OS 경계에서 정규화하고 bool·문자열·소수·비정상
숫자를 제외한다. 실제 CG 행 조회와 signed helper로 floating canvas의
down/drag/up 수신, 전경·전역 커서 보존을 검증한다. 관련 비밀값은 사용하지 않는다.

검증은 중복을 줄인다. 창 트랜잭션의 전체 단계 경계에서 프로세스 시작 시각을
확인하고, 읽기·드래그의 incremental checkpoint는 메모리의 observation과
취소 상태를 비교한다. 반복되는 `proc_pidinfo`를 그 경로에서 제거한다.
창 소유자와 고유 window ID 확인은 잘못된 앱으로 입력하지 않기 위한 최소
식별이며, 사용자에게 별도 승인 단계를 추가하지 않는다.
포인터 창 바인딩에서 AXStandardWindow 서브롤 제한을 제거하고, 창으로 직접
보내는 drag에 키보드 포커스를 요구하지 않는다. 동일 readiness tree의 중복
순회도 제거한다. 키보드 입력의 포커스 계약은 별도로 유지한다.

보고 앱은 사용자가 Lyrics / `Now Playing Overlay`로 식별했다. 실제 소유
nonactivating utility panel에서 signed helper drag의 수신·전경/커서 보존을
확인했다. 별도 `tacto resize` / `resize_window`는 AXSize를 한 번 설정하고
AX·CG 크기 반영을 확인한다. AXSize가 쓰기 전에 지원 불가로 확인되면,
같은 창의 우하단 grip에 한 번의 window-bound resize stroke를 보낸다. 이때
예상되는 geometry 변화는 허용하고 이벤트의 창 상대좌표만 현재 frame으로
환산한다. 키보드 focus나 전역 HID 입력은 사용하지 않는다. 우하단이 실제
버튼·입력란 같은 조작 요소이면 그 콘텐츠에 resize를 보내지 않는다.
일반 panel의 AX resize와 borderless non-key custom resize 모두 600×360
크기가 수신 측 AppKit 기록에서도 일치했다. 첫 실행에서
AX 크기만 먼저 바뀌고 CG 반영이 늦어 검증 실패한 기록을 보존하며, 새 전송
없이 반영을 기다리는 경로로 수정했다.

실제 Lyrics는 june-mba에서 실행 중이며 `Now Playing Overlay`가 layer 3으로
관측됐다. 개발용 signed CLI/helper를 별도 임시 runtime에서 검증했다.
321×294 요청은 앱의 화면 하단 clamp로 321×288만 적용되어 성공으로 세지
않았다. 후속 명시적 원래 크기 복원은 301×274로 확인됐다. 테스트 전후
전역 커서 좌표는 달랐으므로 이 실앱 실행에 커서 보존 성공을 주장하지 않는다.
임시 runtime은 제거했으며 설치 앱은 변경하지 않았다.

후속 rc.17 설치본(c28b1d9)에서 실제 Lyrics의 너비 301→311→301px 변경·복원을
확인했다. 높이 274px와 위치, 전경 앱·커서는 유지됐다. 앞의 화면 경계 실패를
지우지 않고 `reviews/tacto-rc17-20261105/actual-lyrics-installed-receipt.json`에
별도 수신 증거를 남겼다. 앱/DMG 공증, 세 Mac exact-bundle 설치·기존 권한·
스킬 연결을 확인했다. 전체 3,066검사 실패/오류0·조건부 제외26이며,
실제 floating 3경우는 설치본에서 3회씩 총9/9 통과했다. 최초 native 묶음의
시험 앱 등록 전 식별 실패1건은 보존한다. fixture 등록 완료를 기다리는
준비 단계 보완 뒤의 반복 결과이며, 같은 창 입력의 자동 재전송은 아니다.

별도 미확인 사항: Lyrics 가운데 정렬 수신, 재시작 좌표 변화 원인.
기존 창 내부 drag는 매 이벤트의 bounds 불변을 요구하므로
창 테두리 드래그 resize 성공으로 계산하지 않는다. 아래 전체 목표와 비교
평가의 미완료 범위도 그대로 유지한다.

> 제품·측정 라벨·식별자는 현재 Tacto 이름으로 정규화했습니다. 당시 측정 수치와 성공·실패는 유지하며, 새 서명 배포를 검증했다는 뜻은 아닙니다.

## 2026-10-24 현재 상태 감사

2026-11-05 후속 후보는 대화형 session의 JSON/대상/기본 매개변수 오류를 같은
연결에서 고친다. 입력 전 수리만 허용하고 원래 기한·파이프 오류 종료·실행된
Flow 재전송 금지를 유지한다. Windows 입력 reader를 수정 시도 사이에 공유해
스레드가 입력을 빼앗지 않게 했다. 관련29검사와 실제 signed read-only 세션에서
관찰/안내1회, 잘못된 Flow→수정→완료, 모델0회·입력 비노출을 확인했다.
피어가 찾은 Windows 문제를 수정한 후 높은 우선 지적은 없었다.

Sky 후속 정리 실패 문서는 AXChildren에 버튼이 없었지만 창의 직접
AXCloseButton/Minimize/Zoom 속성에는 실제 control이 있었다. direct/signed
관찰에 해당 control을 중복 없이 포함했고, 같은 문서 본문437 재확인 뒤 닫기1회,
읽기만으로 닫힘 확인, 임시 파일 삭제가 통과했다. CG 검사 기준은 완화하지
않았다. 관련99검사 실패0·조건부 제외1이며 source 후보에 대한 증거다.
설치 rc.17 및 이전 비교의 실패·미완료를 소급 변경하지 않는다. 후보 배포와
새 동일 요청 조건 비교가 다음 단계다.

2026-11-05 새 실앱 비교는 `reviews/2026-11-05/product-comparison-20261105-141607.jsonl`에
실패를 보존한다. 고정 요청 gpt-6.1-sol/medium·cold-start에서 Tacto는
24.7초 뒤 Calculator target_busy/not_started로 실패했고, Sky는 준비 실패로
미실행이었다. 평가 worker가 앱 lease를 유지한 채 독립 에이전트를 기다리는
충돌을 확인했다. 후보 `release_targets`는 연결과 문서 pin을 유지하면서 앱·창
점유를 넘기고 이전 관찰을 무효화한다. 정적 peer 검토의 높은 문제는 없었고,
실제 다른 연결의 작업·최종 배포 검증은 별도로 진행한다.

문서 상태 응답에 helper의 coordination_elapsed_ms가 추가되면 Python의 정확한
필드 집합 검사가 정상 응답을 버리는 결함도 수정했다. 해당 회귀와 실제 이전
빈 fixture 닫기·삭제가 통과했다. 새 yielded-worker lifecycle에서는 빈 문서 읽기는
통과했지만, 닫기 뒤 global_window_still_present가 지속되어 정리 미완료로 남았다.
이를 전체 성공으로 세지 않으며 G7 P0에서 AX 창 부재와 CG backing 잔존을
구분하는 실제 증거를 더 확보한다. 두 후보 변경은 설치 rc.17에 소급 포함하지 않는다.

아래 2026-10-10 감사와 후속 기록은 당시 사실로 보존한다. 현재 제품명은
Tacto다. rc.6 배포 완료는 전체 computer-use 목표의 완료와 구분한다.

| 범위 | 현재 증거 | 아직 필요한 완료 증거 / 우선순위 |
|---|---|---|
| select·후보 paging | native/HTML/custom 옵션과 token-budget paging 구현·소유 fixture 평가가 아래 이력에 있음 | 실제 앱·큰 선택 목록·변경/실패·지원 백본 반복, serving tokenizer/context 한도 구분. P1 |
| 메뉴·키보드·입력 보존 | rc.6 실제 앱 재검 60/60, 최초 59/60의 TextEdit Save 비활성 거부도 유지 | 배경 앱 제한·실제 동시 사용자 입력의 결과를 별도 검증. helper 창 입력 후속 수정은 peer 진행 중이며 미배포/미검증 부분을 완료로 계산하지 않음. P0 |
| provider 응답·취소·비용 | 공통 envelope/로컬 자식 정리 구현, 새 Codex 실제6세션 usage 기록 | 다른 지원 백본 반복, 원격 취소·청구 중단/실제 비용·serving model 증거. CLI token 보고와 청구를 구분. P1 |
| 접근성 밖 시각 정보 | 소유 opaque/canvas receiving·실제 이미지 모델 이력 | 다양한 실제 앱의 시각 과제와 독립 결과 검증·백본 반복. 캡처/입력 전송만으로 완료하지 않음. P1 |
| 장기 작업·복구 | rc.6 exact-DMG fault12/12와 native/browser 장기 fixture 이력 | 실제 앱 장기 연결 중단 후 재개, 완료 prefix·불확실 저장/전송 중복 없는 실제 연속 실행. P1 |
| 저장·전송 인과 증거 | exact saved-state·producer·독립 inbox receipt 구현 및 아래 범위별 검증 | 일반 앱의 Save 인과 증거와 실제 수신자·본문·새 message identity의 전송 확인. 상태 일치를 생산자 인과 증거로 승격하지 않음. P0 |
| 대표 실제 작업·동일 조건 비교 | rc.6 native60 및 새 Tacto/Sky 3개 fixture 과제 실제 시행, 조건/환경 원본 보존 | 다중 실제 앱·다중 백본·반복 수 확대. serving model/숨은 context/동시 foreground-caret 동등성 미검증은 비교 제외로 유지. P1 |
| 설치·최종 보고 | rc.6 공증·산출물12·세 Mac exact-bundle 설치·실제 rollback·게시첨부5개 대조 완료 | 새 사용자 DMG 설치·권한3회·제한베타는 사람 확인. 전체 목표 최종보고는 위 범위를 모두 감사한 뒤 작성. P1 |

rc.6 원본은 `reviews/tacto-rc6-20261023/RC6-REPORT.md`(별도 rc.6 worktree)에,
공개 범위는 [rc.6 VALIDATION](https://github.com/Open330/tacto/releases/tag/v1.0.0-rc.6)에
있다. 실제 앱 첫 묶음59/60, 부하 저하 후 별도 새60/60을 합쳐 최초 실패를
지우지 않는다. 아래 오래된 '설치 미완료'·'다음 CLI scope 구현' 등은 당시 기록이며
현재 기능 상태는 코드와 이 감사 및 최신 실행 기록을 함께 본다.

## 2026-10-10 감사와 후속 이력

2026-10-10 감사. 기존 장기 목표 G0~G10의 최신 작업 계획이다. G0~G10의 원래 범위와 완료 기준을
유지한다. 이전의 특정 fixture 성공 또는 14/14 결과로 전체 완료를 선언하지
않는다. 비교·URL 감사 기준 소스는 401f960이며, 창 timeout 분기 검사는
883f621에서 보강됐다. 아래 상태는 기능 제공과 범용 실기 완료를 구분한다.
원래 목표 이력은 `reviews/2026-09-19/next-goal.md`에 보존한다.

| 항목 | 현재 확인 가능한 구현·증거 | 남은 완료 증거 / 다음 작업 | 우선순위 |
|---|---|---|---|
| G0 입력 보존 | 강제 활성화 제거·window-bound 입력·중단 경계 구현; 비교 cohort의 activation 표본 | 사용자 동시 typing, numeric caret/selection, pointer를 입력 중 관측하고 작업 결과도 검증. 앱 활성화 0만으로 입력 보존을 판정하지 않음 | P0 |
| G1 select | HTML/custom ARIA/native 선택 및 identity·disabled 거절 경로; 소유 fixture 결과는 기존 이력 참조 | 다양한 실제 native 앱의 선택·재열기·변경/실패 케이스와 백본별 반복. Finder 새 폴더 실패를 select 전체 성공으로 대신하지 않음 | P1 |
| G2 paging | 원본 후보 번호·참조 조회·예산 계약 및 회귀 구현 | provider tokenizer를 사용한 token 예산/큰 화면 실모델 반복. byte 예산과 provider 전체 context 한도를 구분 | P1 |
| G3 메뉴·키 | capability·menu-state·dispatch guard 구현. 0d86230에서 timeout set/reset 실패 거부, 401f960에서 Document URL raw 정책 통일 | 배경 Finder New Folder와 TextEdit Save의 실제 효과. 앱/창별 timeout 분기 회귀 유지; 거절 자체는 지원 기능 완료가 아님 | P0 |
| G4 provider | 공통 envelope·attempt usage·로컬 process-group 정리 구현 | 지원 백본별 실제 framing/usage 반복, 실패 시 비용 누락 구분. 원격 취소/비용 중단은 현재 미보장으로 기록 | P1 |
| G5 시각 | browser/native capture 및 host-authorized window 입력 계약. 자체 headless canvas 실제 Codex 이미지 읽기 3/3, 아래 범위 참조 | 다양한 실제 앱의 AX 밖 화면과 receiving 증거. 캡처·event 전송 성공을 결과 성공으로 계산하지 않음 | P1 |
| G6 장기 복구 | 시간/화면 예산·모달·detached·commit 불확실성 회귀 구현 | native 앱의 긴 작업과 끊긴 연결/중단 뒤 상태 재검증. 비멱등 저장·전송의 자동 중복 금지 유지 | P1 |
| G7 저장·전송 | event-bound receipt·정확한 파일 readback·document token·save-panel guard 구현; ExistingTextFileReceipt는 관측된 상태 증거 | 정확한 신규 본문 저장 및 안정된 disk readback, source-format/첨부/목적지 검증, 실제 수신자/본문/신규 message identity의 전송 증거. 이미 있던 정답 파일·앱 autosave를 Save 인과 증거로 계산하지 않음 | P0 |
| G8 대표 평가 | native/Web 과제와 원시 결과/manifest/oracle 기록 존재 | 위 미완료 과제와 다른 앱·백본·반복을 같은 source cohort에서 확장. 실패·SKIP·환경 미지원 보존 | P1 |
| G9 동일 조건 비교 | 2026-10-08 및 10-09 Tacto/Sky 비교 원시 cohort 존재 | 성공·실패 모두 동일 초기 상태·manifest·task oracle·시간 제한을 재감사. 요청 백본과 실제 serving model을 구분 | P1 |
| G10 설치·보고 | signed launcher/helper·checkout-backed setup preview·계약 문서 | 새 Mac의 실제 drag/install/permission/skill 연결·업데이트·재시작; standalone 배포 및 notarization. 최종 보고서는 실제 검증 범위별로 작성 | P1 |

### 현재 비교 증거

- `../reviews/2026-10-08/product-comparison-20261008-211647.jsonl`: 28행,
  Tacto 14/14·Sky 14/14 oracle 통과, process exit 모두0, source_changed 모두false.
  이는 해당14과제 cohort의 결과다. 명시 manifest 멤버십은 모든 의존성의 폐쇄를
  증명하지 않으며, 전체 기능 완료나 동시 사용자 입력 보존을 증명하지 않는다.
- `../reviews/2026-10-09/product-comparison-20261009-184154.jsonl`: 16행,
  Tacto3/8·Sky8/8. Tacto 실패는 textedit_save_owned1건, finder_new_folder2건,
  appearance_mode2건. 모든 프로세스 exit0이지만 독립 oracle 실패는 실패다.
  후속 appearance 재실행은 별도 source cohort로 다루며 이 실패를 지우지 않는다.
- 실제 전체 로그 `../reviews/2026-10-10-unit-tests-62.log`, `../reviews/2026-10-10-unit-tests-63.log`: 각각1219 tests, skipped2, 실행1217개.
  단위 테스트 통과는 위 실제 앱 성공과 별개다.

### 다음 실행

1. G7: 배경 TextEdit의 AXValue/AXSelectedText 편집·document edited 상태·
   autosave 순서를 분리해 정확한 본문과 안정된 파일을 검증한다. menu-state는
   진단이며 실제 저장 증거가 아니다. 새 문서·이미 저장된 문서·다른 경로의 같은
   basename·한글 NFD·큰 본문·중단·문서 교체를 각각 포함한다.
2. G3/G0: Finder background New Folder에 필요한 responder/window readiness를
   지원 범위 안에서 구현하고 새 실제 directory identity와 사용자 입력 보존을
   함께 검증한다. 단순 활성화 우회 또는 안전 거절만으로 완료하지 않는다.
3. G4/G2/G6 회귀와 실제 지원 백본 평가, G5 실제 앱 receiving 검증을 이어간다.
4. G8/G9: 수정 전 실패 cohort를 보존하고 새 소스 manifest로 같은 실패 과제들을
   반복 비교한다. 기능 성공과 focus/caret 보존, token 관측과 실제 비용을 분리한다.
5. G10: setup preview를 실제 설치로 검증하고 전체 G0~G10을 재감사한 뒤
   최종 보고서를 작성한다. 아직 미검증인 항목은 완료로 승격하지 않는다.

권한·잠금·captcha·사용자 입력 협조가 필요한 경우는 구체적 환경 조건을 남긴다.
그 환경에서 실행하지 못한 과제를0%/100%로 환산하거나 결과를 만들어내지 않는다.

## 이번 독립 회귀 검증

401f960 기준 provider_result, provider_attempts, candidate_paging,
text_paging, recovery_integration의40개 테스트가21.546초에 통과했다.
provider는 mocked 결과/로컬 subprocess를 사용했으며 실제 유료 모델 요청은
아니다. recovery_integration은 격리된 Chromium 페이지의12단계 wizard,
모달·detached·불확실 commit 경계를 검증한다. macOS 실앱 저장·전송이나
사용자 동시 typing을 검증한 수치가 아니다.

재현 명령:

```sh
.venv/bin/python -m unittest tests.test_provider_result tests.test_provider_attempts tests.test_candidate_paging tests.test_text_paging tests.test_recovery_integration
```

관련 계약과 추가 검증 범위: [capability](capabilities.md),
[paging](context-paging.md), [provider](provider-envelope.md),
[저장](textedit-save.md), [평가](evaluation.md), [비교 기록](benchmark-records.md),
[설치](installation.md). 이 계획은 최종 완료 보고서가 아니며 모든 행의
실기·반복·실패 증거가 확보될 때 전체 목표를 재감사한다.

## G7 후속: 읽는 도중 바뀐 파일의 완료 증거 거부

기존 `_file_state`는 열린 descriptor의 바이트만 읽어 반환했다. EOF 직후
이름의 파일을 다른 내용으로 교체하면 이전 바이트가 정상 반환됐고, 실제
경로의 내용은 달랐다. 이는 실제 임시 파일로 재현했다.

후속 구현은 읽기 전후 descriptor와 경로의 dev/ino/mode/uid/nlink/size/
mtime/ctime, 읽은 길이, canonical path를 대조한다. 변경 시 닫힌 코드
`file_changed_during_read`로 거부한다. 사라진 파일은 `file_unreadable`로
거부한다. 실패한 after_commit을 다시 호출해 완료로 바꾸지 않는다.

`tests/test_existing_file_read_stability.py`는 정상 파일, path 교체,
같은 크기 덮어쓰기 후 mtime 복원, final symlink 교체, 삭제, parent symlink,
receipt 발급 및 재사용 금지의7개 검사를 수행한다. 수정 전 코드에서는
6개가 실패하고, 수정 후 기존 receipt 검사와 합친30개가 통과했다.
추가로 replay commit evidence·typed evidence·fresh-file receipt34개도 통과했다.
검사는 실제 임시 파일과 주입된 문서 응답을 사용하며 실제 TextEdit 저장을
수행하지 않는다. 바이트 일치가 어떤 앱의 Save가 썼다는 생산자 인과 증거를
제공하거나, 마지막 검사 이후 변경·동일 사용자 ABA 경쟁을 배제하지 않는다.

## G8/G9 후속: 저장 oracle 계약 강화

기존 비교는 공백·줄바꿈을 정규화해 정확한 저장 요청을 느슨하게 채점했다.
새 `textedit-save-exact-utf8-v2`는 정확한 UTF-8 바이트와 소유 문서의 정확한
본문을 비교하고 파일 교체·symlink·FIFO·초과 크기를 거부한다. 이전 원시
cohort는 그대로 보존하며 새 oracle 성공으로 승격하지 않는다.
자세한 계약은 [비교 기록](benchmark-records.md)에 있다.

실제 signed `doctor --check`에서 AX·screen 권한 및 GUI 세션 연결을 확인했다.
읽기 전용 menu-state는 배경 TextEdit Save disabled와 전경 Finder New Folder
enabled를 반환했다. 이 조회는 작업 효과·사용자 caret 보존 검증이 아니다.

## 최신 비교 실행과 환경 gate

준비 전/후 화면 잠금·세션 미관측 gate, 시도한 실패의 보존,
comparison_eligible 분리, 잠금 뒤 cleanup 금지, filter/reps 검증 및 종료
코드를 구현했다. 관련 readiness7개+저장 oracle9개+provenance36개,
총52개 회귀 통과. 새 report는0600으로 생성한다.

`reviews/2026-10-10/product-comparison-20261010-155619.jsonl`에서 외형 읽기를
Tacto와 Sky 각각 실제1회 실행해 양쪽 PASS(Light)를 확인했다. Tacto42.3초,
Sky53.9초, 동일 manifest이며 activation0건이다. 이 기록은 실제 모델·GUI
실행이다. 정확한 저장·Finder 생성·Dark/Auto·동시 사용자 입력은 검증하지 않았다.
시행1회로 속도/비용 우위나 범용 성공률을 주장하지 않는다.
원시 usage·full SHA256·관측 한계는 [비교 기록](benchmark-records.md)에 기록한다.

### G7 정확한 저장 상태 실제 시행

`reviews/2026-10-10/product-comparison-20261010-160030.jsonl`에서 새 소유
문서를 사용해 Tacto1/1·Sky1/1의 exact UTF-8 파일/본문 일치와 자체 문서
정리를 확인했다. Tacto41.2초, Sky49.5초, 동일 frozen manifest다. 처음의
배경 Save disabled 관측이나 이전 저장 실패를 삭제하지 않는다. 이번 성공은
정확한 최종 상태이며 명시 Save 인과 증명/반복 안정성 완료가 아니다.

Tacto activation0, Sky2건의 원인은 미확정이다. 초기 전경 상태를 보존하는
후속 runner 변경은52개 회귀로 검증했으나 위 시행에는 포함되지 않는다.
다음은 초기 상태/receiving witness를 고정한 반복 저장과 Finder 생성,
기존 파일과 새 파일·문서 교체·실패 후 복구, 저장·전송 인과 증거다.

### G3 현재 실패와 다음 구현

`reviews/2026-10-10/product-comparison-20261010-160542.jsonl`에서 Finder 새
폴더는 Sky1/1, Tacto0/1이었다. Tacto는165.7초/실제 input603060 후 빈 directory로
끝났다. 모델은 메뉴 disabled·창 준비 timeout을 보고했지만 native phase별
실패 trace는 보존되지 않아 원인을 확정하지 않는다. 자기 시험 폴더는 정리했다.

다음 P0 작업은 창 준비의 native readiness 검사/target binding/dispatch phase를
분리한 bounded 진단과 tool의 실제 실패 코드 보존이다. 원시 tree·문서 본문을
로그에 복사하지 않고 노드 예산·deadline·refusal code 등만 계측한다. 새로운
원인 증거에 따라 준비 구현을 수정한 뒤 같은 owned-directory 과제를 반복한다.
필요한 안전 조건을 제거하거나 실패를 지원 완료로 선언하지 않는다.

초기 전경 앱이 양쪽에서 달랐으므로 이 시행은 작업 결과·실패 재현 증거이며
완전한 동일 조건 비교 결과가 아니다. source/lock eligibility와 초기 상태
동등성은 별도 판정으로 유지한다.

### G3 진단 구현과 실제 전송 확인

창 준비의 phase/closed reason/elapsed/scoped AX operation counter를 구현했다.
실제 Swift 함수의 주입 실패와 기존 readiness/dispatch 회귀7개 PASS, helper
빌드/번들 서명 검증 PASS. signed owned AppKit eval1/1 PASS에서 새 진단을
수신했고 background 준비552 scoped operations/1015ms와 responder 효과를
확인했다. 사용자 앱 내용은 새 진단 필드에 넣지 않았다.
계약과 원시 artifact 위치는 [창 입력](native-window-input.md)에 기록한다.

Finder 원인 확인과 구현 개선·실제 반복은 여전히 남아 있다. 새 진단을
작업 성공/재시도 허가/사용자 동시 입력 보존으로 대신하지 않는다.

### 진단 transport와 Finder 단독 시행

`reviews/2026-10-10/product-comparison-20261010-162643.jsonl`: Tacto1/1,
256초 뒤 `untitled folder` 한 개를 독립 oracle로 확인했다. source_changed=false,
cleanup folder_removed다. input1421307/cache1333120/output3800이며 raw usage다.
초기 Finder, activation9건의 원인은 미확정이다. 같은 백본의 시행1회이며
반복 안정성/비침해/비용 우위 또는 동일 조건 Sky 비교의 증거가 아니다.

실제 준비 진단 배열은0건이었다. 이후 closed marker 검증/수집과 replay의
bounded 별도 목록/CLI 출력을 연결하고 postcondition 실패 및 no-trace json
예외 경로를 보강했다. 실제 replay와 CLI를 주입 driver로 실행한 검사 등을
합쳐75개 PASS. 다음은 이 후속 transport를 사용해 실제 Finder 준비 실패를
다시 수집하고, 원인 증거에 따라 readiness/targeting 구현을 개선하는 것이다.

### G3 모델 없는 직접 재현: readiness 예산

`examples/probes/finder-preparation-diagnostic.py`는 신규 소유 빈 폴더와 명시한
Window selector로 open_folder→prepare_window를 한 번 실행한다. GUI는 설치된
signed launcher만 사용하고 모델/자동 복구를 호출하지 않는다. 전체 CLI60초
제한에서 로컬 process group을 회수한다. timeout/예외 후 자기 directory도
보존하며, 정상 반환 뒤 동일 inode의 빈 자기 directory만 제거한다. Finder
창과 사용자 파일은 닫거나 삭제하지 않는다.

실제 `reviews/2026-10-10/finder-preparation-directed.json`은 binding 단계에서
readiness_deadline,4956ms, scoped AX2452회로 거부됐다. 이어 현재 source
manifest를 기록한 `finder-preparation-directed-manifest.json`은 같은 단계의
readiness_nodes,1058ms, scoped AX542회로 거부됐다. 후자는 source_changed=false,
report0600이다. 각 시행의 자기 빈 directory는 제거됐다. 둘 다 model_calls0이다.

따라서 원인은 한 가지 timeout만이 아니다. 전체 앱 readiness 순회에서 시간과
노드 예산 모두 실제 차단 조건이다. 이는 시점별 앱 트리 상태가 다른 두 시행이며
동일 트리의 성능 비교는 아니다. 다음 구현은 우선 안전 조건을 보존한 다중 속성
조회로 AX 왕복을 줄이고, 별도로 대규모 다른 창의 modal 검증을 완전하게 수행할
방법을 검토한다. 단순 role prune/예산 확대를 지원 완료의 대체물로 사용하지 않는다.

### G3 attribute batching 구현

Readiness의 node-local Role/Modal/Children packet을 구현했다. 전체 tree 검사와
budget을 유지하고 사후 top role/modal/sheets를 다시 읽는다. 기존 adversarial
corpus의 단건·batch 거부 결과 일치, packet 실패/late modal/role change 및
기존 dispatch/diagnostic 회귀9개 PASS. helper/bundle 빌드·서명 검증 PASS다.

배치 이후 Finder 직접 시행은 readiness_nodes로455ms/193 scoped AX 작업에서
거부됐다. 같은 tree의 전후 실험이 아니므로 성능 비율을 계산하지 않는다.
AppKit receiving 두 시행은 기존 사용자 focus guard에서 입력 전에 거부됐고
실패를 보존했다. 포커스/노드 예산 해결 완료가 아니다. [구현과 실기 한계](native-window-input.md)에
원시 artifact와 실행이 겹친 trial, 최종 role guard 보강의 소스 범위를 기록한다.

### 고정 소스 통합 검사와 Python 회귀 수정

공유 트리 실행 중 소스가 바뀐 검사는 최종 통과 증거로 쓰지 않는다.
소스·테스트를 독립 임시 디렉터리에 복사하고 복사 전후 및 검사 종료 후
파일 SHA256 일치를 확인했다. 이 사본에는 진행 중이던 double_click의
Python 분기도 포함됐다. 분기 안의 중복 `AXUIElementPerformAction` import가
기존 click/menu/secondary_action을 UnboundLocalError로 막는 실제 회귀를
확인했다(최초1259개 검사에서 failure7/error1). 전역 import는 유지하고
분기 import 한 줄을 제거했다. 공유 트리의 같은 수정도39개 회귀로 확인했다.

수정된 고정 사본의 전체 검사는1259 tests, skipped2, 실행1257개,
실패0,223.504초로 통과했다. 사본 manifest SHA256은
`3f5c4ee7e957dd4260d97c84833d41b13f72b9ee150263a054d79d1ef31f4d52`다.
이는 비교 runner의 manifest와 다른 전체 소스/테스트 사본 계약이다.
원시 통과/실패 로그와 manifest는
`reviews/2026-10-10/isolated-integration-*`에0600으로 보존했다.
후속 peer 변경이나 통합 helper 빌드는 별도 검증이 필요하다.
실앱 receiving, Finder 노드 예산 해결, 전체 목표 완료의 증거는 아니다.

### G7 리뷰 반영: safe-save 교체 중 읽기 재관측

Muxa read-only 리뷰에서 정상 safe-save의 rename/swap 도중 읽기 실패가
즉시 종결되는 liveness 문제를 확인했다. after_commit은 실제 ENOENT 또는
metadata/inode 변경을 내부 typed transient로 분리해 마감까지 파일만 다시
관측한다. public error 문자열만으로 재시도를 허용하지 않는다. 매번 동일
문서 token·경로·정확한 본문을 재검증한다. 초기 prepare는 안정된 파일을
요구하며 재관측하지 않는다. Save 입력은 반복하지 않고 after_commit은
여전히 한 번만 호출할 수 있다.

권한·EIO·nonregular·다중 hardlink와 문서 변경은 즉시 거부한다. 계속
교체되거나 이름이 사라지면 마감에 마지막 closed code로 거부한다. 정상
파일의 exact bytes도 마감 후 반환되면 file_readback_deadline으로 거부한다.
OS/AX 호출 강제 취소, writer attribution 또는 autosave와 명시 Save의 인과
구분을 구현했다고 주장하지 않는다.

새15개 검사는 실제 임시 파일의 EOF 교체·open 직전 교체·이름 공백·
반복 교체·다른 내용·문서 변경·권한/EIO·FIFO·hardlink·마감 초과를 다룬다.
최초12개를 수정 전 cfa9aa2에 실행하면 failure5/error4, 수정 후 최종15개와
기존 receipt/replay/evidence 검사를 합친93개는2.130초에 통과했다.
이는 실제 TextEdit UI safe-save나 전송 수신 증거의 검증은 아니다.

후속 Muxa 리뷰는 P1 없음·범위 적합으로 판단했다. 늦은 exact read 거부는
FreshFileReceipt와 같은 receipt 수용 마감 계약으로 유지한다. 이는 Save
실패나 파일 불일치를 뜻하지 않으며 OS/AX 호출을 취소하는 것도 아니다.
큰 문서/느린 backend는 호스트가 timeout을 늘려야 하고, 자동으로 수용
기간을 늘리지 않는다. 첫 poll이 느리면 정상 저장 상태도 마감으로 거부될
수 있다는 liveness 제약을 API docstring에 명시했다.

### G7 새 요청과 독립 수신함의 전송 증거

`DeliveredMessageReceipt`는 호스트의 실제 control/payload 관측으로 결합된
request_id와 authoritative 수신함의 새 message_id·account·recipient·정확한
본문 digest를 대조한다. 기존 수신 record, queued/accepted, 모델 JSON,
송신 Sent 표시는 완료 증거가 아니다. prepare/after 각각 한 번만 허용하고
수신함 조회만 반복한다. 이 API는 native 메신저의 자동 bridge가 아니며
서비스 request binding·인증된 수신 조회·독점 요청 identity가 전제다.
첨부·동일 UID의 다른 writer·서비스별 atomic precondition은 아직 별도 과제다.
[서비스 계약과 실기 범위](delivery-evidence.md)에 상세 조건을 기록했다.

실제 headless Chromium의 Tacto click→owned loopback HTTP POST→인증된
독립 HTTP inbox read를 검증했다. 서비스는 수신 본문을 보관하고 조회 시
그 본문을 hash한다. 정확한 새 수신, no-op Sent, 수신 본문 손상, 응답 유실,
기존 요청 재사용 거부, 승인 거절, 실제 form 수신인 변경, dispatch 전 거절의
8개 통합 케이스다. 실제 외부 사람이나 native GUI에 메시지를 보내지 않았다.

응답 유실 케이스에서 기존 replay는 host receipt로 event를 confirmed한 뒤에도
원래 driver error를 반환해 실패했다. receipt가 검증된 consequential unknown
응답만 원래 transport uncertainty를 event에 남기고 진행하도록 수정했다.
이 hunk는 peer 통합 커밋 ce4074a에 포함됐다. 영수증이 없거나 not_started면
완료로 바꾸지 않으며 재전송하지 않는다. 후속 UI postcondition은 별도다.

새 adapter unit14 + receiving integration8 + 기존 저장/receipt/replay/evidence
검사를 합친115개가13.096초에 통과했다. 초기 approval fixture 오류4건과
그 수정 후 발견한 실제 response-loss 오류1건의 로그도 보존한다. 전체
실제 native 전송·첨부·다양한 백본·Tacto/Sky 동일 조건 비교는 아직 남아 있다.

고정된 exact ce4074a archive + root receipt8개 overlay의 전체 검사는
1301 tests/skipped2/230.193초, 문서 링크 검사1건만 실패했다. 새 문서의
README 링크를 추가하고 관련 문서 검사6개를0.025초에 통과했다. 원시 실패
및 manifest는 `reviews/2026-10-10/receipt-stable-full-*`, 수정 검사 로그는
`receipt-docs-recheck.log`에 보존했다. 이 결과는 후속 f339633의 bound Return과
진행 중인 TranscriptEvidence를 검증하지 않는다. 앞선 일부 WIP가 섞인
사본의1301개 검사/실패3개도 `receipt-partial-wip-*`에 별도로 보존했다.

G4 실제 framing 교정은 Codex CLI0.161.0 direct adapter에서 JSON oracle
PASS(5.337초,input16149/cache12160/output9)를 확인했다. 실제 serving model과
달러 비용은 미관측이다. Claude CLI2.1.296 common/tools-disabled route는
nonzero error로 실패하고 usage는 미관측이다. 각 시행1회·서로 다른 route의
순수 산술 요청으로, UI 성공률/동일 조건 비교/비용 우위가 아니다. 원시
envelope와 source checkpoint는 `provider-framing-codex.json`,
`provider-framing-claude.json`에0600으로 보존했다. Claude 실패 원인과
closed provider reason 분류는 추가 진단 중이다.

### G4 실제 조직 접근 제약과 오류 분류

Claude CLI2.1.296의 실패는 옵션 호환·quota·모델 refusal이 아닌 조직의
Claude Code 구독 사용 제한이라는 명시적 API 오류였다. 초기 일반nonzero
실패 기록을 보존하고, 완전한 isolated failed stream만
organization_access_disabled로 분류하도록 보강했다. 성공 parser는 완화하지
않고 본문·모델·usage·cost를 검증된 성공 값으로 승격하지 않는다. 설정이나
인증 경로를 바꾸지 않았다. 실제 common 호출에서도 새 닫힌 attempt code와
사용자 설명이 반환됐고 usage는null이었다(1.797초). 원시 envelope는
`provider-organization-access-classified.json`에0600으로 보존했다.

조직 제한을 설명하는 정상 답변, 도구 포함/불완전/다른 세션/다른 API 실패,
잘못된 JSON/예산, fallback 뒤 다른 실패와 timeout 및 primary error code의
일관성을 검증했다. 관련 provider/CLI/envelope 검사66개가6.384초에 통과했다.
이것은 Claude 모델의 실제 UI 작업 성공이나 비용0을 증명하지 않는다.
현재 Claude 구독 경로의 대표 실제 백본 평가는 접근 제약으로 남아 있으며
Codex 등 독립적으로 사용할 수 있는 경로의 작업은 계속한다.

### G7 수신 영수증 후속 리뷰 반영

Muxa 리뷰의 P1 없음·계약 적합 판단을 확인했다. 호스트의 기대 body digest를
commit_expected에 내보내고 공통 DeliveryEvidence matcher가 독립 대조하도록
보강했다. 승인 대기 실행에서도 prepare가 소모되는 수명을 문서화하고,
실제 gated→동일 adapter 재사용 거부→새 request/adapter 승인 실행을 추가했다.
message_id의 colon/dot/@/Unicode는 보존하고 control·공백·초과 길이는 거부한다.
해당 변경을 포함한 delivery/replay/typed evidence/transcript 검사54개는
12.267초에 통과했다. 송신 transcript와 수신함 증거의 품질 구분은 유지하며
실제 native bridge·첨부·독점 요청 조건이 없는 서비스에는 성공을 주장하지 않는다.

## G4/G5 후속: 계획 응답의 도구 기록 거부와 실제 이미지 읽기

Codex 계획 adapter는 reasoning/agent_message 이외의 turn item을 거부한다.
성공한 명령 실행이나 MCP 호출 뒤 정답 final이 나와도 계획 응답 성공으로
인정하지 않는다. 이는 실행 후 수용 조건이며 도구 실행 차단의 증거가 아니다.
관련 provider/visual/process 회귀 34개가 통과했다.

`examples/probes/browser-visual-score.py`로 자체 headless Chromium의 canvas에
무작위 네 자리 게임 점수를 그려 실제 Codex 이미지 요청을 세 번 실행했다.
점수는 AX tree와 DOM 문자열에 없음을 각 사례에서 검사했고, 위치·배경 대비·
글꼴을 바꾼 세 이미지 모두 정확한 점수를 반환했다(3/3).
원시 이미지·답변·provider metadata는
`../reviews/2026-10-10/visual-score-codex-acceptance/`에 보존한다.
관측 input 합계 48,784 tokens, output 합계 48 tokens이며 이는 CLI telemetry다.
실제 serving model과 비용은 null이고 요청은 기본 Codex image 경로를 사용했다.

이 실행은 HEAD 3351584에 미커밋 adapter/probe 변경을 포함했다. 최초 실행은
HEAD checkpoint만 기록해 전체 dependency freeze 또는 source 불변성을
증명하지 않는다. 후속 probe는 제한된 여섯 소스의 전후 hash도 기록하지만
전체 의존성 폐쇄를 증명하지 않는다. 사용자의 실제 브라우저·macOS 창,
시각 좌표 행동, 저장·전송 receiving 증거, Tacto/Sky 동일 조건 비교를 수행한
결과가 아니다. 전체 G5 완료 기준은 유지한다.

## G2/G1 후속: 실제 token 예산·재요청 한도·웹 옵션 선택

`ask_here_paged`의 최초 prompt 검사 뒤 `ask`가 검증 재요청 안내문을 붙여
예산보다 큰 요청을 보낼 수 있었고, 재요청은 max_pages 호출 상한에도
포함되지 않았다. 실제 reach_model 직전 guard가 최종 prompt와 논리 요청 수를
함께 검사한다. validation retry가 한도를 소진하면 추가 페이지를 요청하지
않으며, 기존의 예산 안 재요청과 원래 후보 선택은 유지한다.
새 테스트4개를 HEAD 2207886의 ask 소스로 실행하면3개가 실패했다.
수정 후 paging/validation/provider-envelope/docs 검사33개가 통과했다.
기준 실패 로그는 `../reviews/2026-10-10/paging-request-limit-baseline.log`다.

실제 tiktoken 0.14.0의 o200k_base·cl100k_base로 한글·emoji·결합 문자·
JSON escape·특수 토큰처럼 보이는 문자열이 있는211개 후보를 각각29페이지로
손실 없이 재조립했다. 전체 renderer prompt는350 token 예산 안에 있었다.
같은 원문의 text paging은180 token 예산 안에서 각각23·25페이지로 재조립했다.
기록: `../reviews/2026-10-10/tokenizer-lossless-paging.json`.
선택한 tokenizer의 문자열 예산을 검증한 것이며 실제 serving model tokenizer,
숨겨진 provider system/tool/framing 토큰 또는 전체 context 한도를 증명하지 않는다.

자체 headless Chromium에36개·48개 select control을 만들고 실제 AX tree에서
후보와 disabled option을 추출했다. 기본 direct Codex CLI 모델에 전체 task
prompt의 o200k_base 예산2500을 적용해 뒤쪽 후보를 찾고 Priority를 선택했다.
호스트는 목표 control·단일 select_option·정확한 value를 독립 대조한 뒤
동작을 적용했고, DOM에서 목표 하나만 변경되고 나머지 선택값은 모두 그대로임을
검사했다. 모델 요청은 각각3·5회, 최대 측정 task prompt는2420 tokens,
최종 DOM oracle은2/2 통과했다. actual model·비용은 미관측이며 native 앱이나
Sky 동일 조건 비교 결과가 아니다. 직접 adapter를 주입했으므로 Muxa 우선
라우팅 검증으로 취급하지 않는다.

첫 시험은 probe의 driver.act 인자 순서 오류로 target_mismatch/not_started,
DOM oracle0/2였다. 모델이 올바른 후보를 고른 것만으로 성공 처리하지 않았으며
그 실패 기록 `../reviews/2026-10-10/token-budget-select-codex/`를 보존했다.
인자 순서를 수정한 후의 실제 재시험은
`../reviews/2026-10-10/token-budget-select-codex-corrected/`에 별도 보존했다.
두 실행 모두 측정한 Python source subset의 전후 hash는 같았으나 전체 의존성
freeze를 증명하지 않는다. 전체 G1/G2의 실제 native 앱·백본별 완료 기준은 유지한다.

Muxa read-only 리뷰는 P1 없음으로 판단했다. 요청 상한의 의미 변화는 의도이며
README의 CLI 옵션과 API docstring에 실패·검증 재요청을 포함하는 시도 기준으로
명시했다. 재요청 거부 metadata에 phase를 남기고, 재요청 직전 계측 실패는
모델 실패(None)로 숨기지 않고 token_counter_failed·미측정 count null로 반환한다.
이 추가 경로와 CLI를 포함한 후속38개 테스트가 통과했다. 새 실제 모델 요청을
보내지 않는 진단 변경이므로 기존 실제 모델/DOM 시험 기록은 별도 소스 범위로
유지한다. 리뷰 request는 req_18dd223a04ea7418_3d다.

## G10 후속: 새 사용자 설치·스킬 연결의 실패 경계

skill/install.sh는 signed launcher 경로가 없으면 Python console script를
연결하던 fallback을 제거했다. 새 사용자·relocated Claude/Codex 환경의
없는 skills 폴더를 생성하고 최신 checkout의 skill 링크를 만든다.
확인 모드는 변경 없이 누락/충돌을 exit1로 보고하며, 잘못된 옵션은
설치를 시작하기 전에 exit2로 거부한다. 이름만 같은 다른 명령/스킬의
파일·정상/깨진 symlink는 보존한다. 기존 Tacto 스킬 복사본과 그 안의 로컬
추가 파일은 삭제 대신 private backup에 보관한 후 연결한다.
기존 Tacto checkout의 launcher/console 링크는 Tacto marker를 확인해 갱신한다.

실제 bash installer를 임시 checkout·새 사용자 경로(공백 포함)에 실행한
9개 케이스와 기존 설치5개 케이스는14/14 통과했다. 이 fixture의 launcher는
실행하지 않는 placeholder이며 서명·TCC·실제 앱 검증을 대신하지 않는다.
원래8개 새 케이스를 수정 전 HEAD 8c37eca의 installer로 실행한 결과는
unittest failures8/errors2(하위 subtest 포함)였고, 전체 로그를
`../reviews/2026-10-10/skill-installer-baseline.log`에 보존했다.
회귀 runner의 wrapper exit는0이므로 그 exit를 테스트 성공으로 해석하지 않는다.

현재 실제 설치에는 `skill/install.sh --check`만 실행했다. launcher와
Claude/Codex skill 링크는 모두 맞고 exit0이었다. 실제 사용자 디렉터리의
설치·권한 변경이나 앱 실행은 하지 않았다. 시작 앱의 연결 버튼은 installer의
nonzero 상태를 실패로 표시하는 기존 계약을 그대로 사용한다. 새 Mac의
드래그·Gatekeeper·권한 부여, standalone runtime·배포 서명·공증은 여전히
남아 있으며, 이 연결 검증만으로 G10 전체 완료를 선언하지 않는다.

후속 Muxa read-only 리뷰(req_18dd22a8bf3e80c0_41)는 P1 clobber 없음으로
판단했다. 중복 스킬 탐색 가능성을 줄이기 위해 백업은 skills discovery root
밖의 상위 폴더로 옮겼고 회귀에서 이를 검사한다. 기본 두 agent 폴더 생성은
installer가 두 도구를 함께 준비하는 명시 목적이므로 유지하며 문서에 적었다.
존재하는 이전 checkout 링크 갱신은 회귀로 검증됐지만, 이전 checkout 자체가
없어진 dangling link는 출처를 확인할 수 없어 자동 교체하지 않는다.
구체적인 확인 안내를 추가했고 이 이동 복구 제약도 유지한다.

현재 설치의 launcher·Codex skill·.venv의 Python CLI import 경로가 이 checkout과
일치함을 읽기 전용으로 확인했다(`../reviews/2026-10-10/installed-runtime-paths.json`).
현재 launcher와 helper bundle의 codesign strict 검증은 모두 exit0이었다
(`../reviews/2026-10-10/installed-signature-checks.json`). 이는 현재 로컬 signature
유효성 확인이며 새 Mac의 권한·배포 identity·notarization 검증이 아니다.

실제 설치된 skill 링크를 통해 install.sh --check를 실행하는 추가 회귀에서
Bash의 논리적 '..' 처리 때문에 repo가 ~/.codex/skills로 잘못 계산되고,
launcher가 없다는 exit1이 재현됐다. 먼저 installer 디렉터리를 pwd -P로
확정한 뒤 그 부모를 repo로 계산하도록 수정했다. Codex/Claude의 설치된
skill 경로 모두 같은 checkout을 찾는 검사를 추가했다.
최종 installer10개+기존설치5개+docs6개는21/21 통과했다.

## G6/G7 후속: 일시적인 수신 조회 장애 뒤 단일 전송 확인

DeliveredMessageReceipt는 호스트가 명시적으로 InboxTemporarilyUnavailable을
발생시킨 경우에만 after_commit의 read-only 수신함 조회를 마감 안에서
재관측한다. prepare에서 조회불가는 이전 수신 부재를 확인하지 못한 것이므로
입력 전에 거부한다. 일반 예외·인증 오류·수신 field 불일치는 즉시 거부한다.
마감이 이미 지났으면 새로운 읽기를 시작하지 않으며, 진행 중인 조회를
강제 취소하거나 늦은 수신 record를 수용하지 않는다. 같은 request_id로만
조회하고 bind/click/POST를 다시 실행하지 않는다.

새 unit6개는 준비 조회불가/재사용 거부, 일시 장애 복구, 지속 장애의 정확한
deadline 종료, generic 권한 오류의 즉시 거부, 복구 후 본문 불일치와 느린
조회 실패를 검사한다. 새 headless Chromium/loopback HTTP4개는 실제503
두 번 뒤 정확한 새 수신, dispatch 응답 유실+503 뒤 단일 전송 확인,
지속503 미검증, 수신403 즉시 거부를 검사한다. 원래 검사와 합계37개가
18.365초에 통과했다. 성공한 복구에서도 전송 POST는1회이며 새로운 message
identity와 수신 본문을 확인한다. 장애 사례에는 실제 수신 메시지가 있어도
조회 증거가 없으면 commit_unverified를 유지한다.

수정 전 HEAD c0cc88d 구현에 새 호스트 신호 타입만 제공해 동일한10개 새
검사를 실행하면 failures5/errors1, exit1이었다. baseline polling 로직은
변경하지 않았다. 로그는 `../reviews/2026-10-10/delivery-read-outage-baseline.log`다.
이 검증은 자체 계정·본문·로컬 서버만 사용했으며 실제 원격 메신저, 첨부,
native 앱과 여러 모델 백본 또는 Tacto/Sky 동일 조건 비교의 완료 증거가 아니다.
이 범위 밖 항목은 G0~G10 원래 완료 기준으로 계속 진행한다.

Muxa read-only 리뷰(req_18dd231e9140bb18_46)는 P1/P2 없음으로 판단했다.
명시 신호의 하위 클래스도 읽기 재관측에 해당함을 문서화했다. 표시 계층이
private exception 클래스명만 보여 주는 문제는 별도 replay 소유 경로에서
peer가 다루며, delivery 모듈에는 닫힌 PUBLIC_CODES와 내부 code 검증을
제공한다. 현재 범위의 완료·오류 수용 조건은 변경하지 않는다.
추가 typed commit/replay/observation-binding/transcript 회귀21개도 통과했다.

## G0/G9 후속: 세션 지표 결합과 기존 비교 전제 감사

초기 WIP에서는 CGSession lock key 부재를 항상 unknown으로 막았고,
Finder 두-arm CLI가 setup/모델 없이 exit2를 반환했다. 그 실행 기록
`../reviews/2026-10-10/comparison-session-unobservable.json`은 보존하지만,
이를 현재 환경이 접근 불가라는 근거로 쓰지 않는다. Muxa 리뷰는 정상 로그인한
콘솔에서도 그 private key가 생략되는 플랫폼 동작 때문에 거짓 차단이라고
지적했다. root는 공식 Apple XNU의 console/login positive 지표와 lock 비교,
현재 CGSession·IOConsole의 boolean 지표를 읽기 전용으로 확인해 교정했다.

최종 lock_state는 key가 생략됐을 때 console=true+login_done=true가 함께
있으면 unlocked로 해석한다. malformed lock flag, 없는 세션·지표는unknown이다.
비교 실행기는 off-console·로그인 미완료·unknown과 명시적인 잠금을 차단한다.
이는 best-effort platform inference이며 atomic 입력 승인이나 사용자 입력
보존의 증거가 아니다. peer의 잠긴 때 raw dictionary 원본은 없다는 한계도
유지하며 원래 평가의 task별 guard는 계속 필요하다.

실제 installed signed launcher의 doctor --check는 exit0으로 손쉬운 사용·
화면 기록 권한과 보이는 앱8개를 보고했다. 권한 요청·설정 열기·비교 task 실행은
없었다. 현재 readiness는 잠금 key 부재만으로 차단할 상태가 아니다.
확인 결과는 `../reviews/2026-10-10/comparison-session-calibrated.json`에 별도 보존한다.

새 audit_product_pairs는 기존 JSONL의 task/rep를 정확한 arm 한 쌍으로
그룹화하고, 중복·누락·초기 전경·oracle·layer 준수·source manifest checksum 및
전후 안정성·잠금 관측을 검사한다. task outcomes를 보존하고 입력을 수정하지
않는다. 기록된 부분 전제가 같아도 전체 초기 task 상태나 실제 serving
model/configuration은 증명하지 못하므로 same_conditions_verified=false를
유지하고 비교 성공률·성능 수치를 계산하지 않는다.

실제 기존 네 cohort를 감사해 appearance/save의 초기 전경 누락, Finder의
초기 전경 차이, Tacto-only 후속을 확인했다. 결과와 각 입력 SHA256은
`../reviews/2026-10-10/product-pair-prerequisites-audit.json`에 보존한다.
새 pair 감사7개와 비교 provenance/소유 oracle/세션 검사를 합친 초기47개는
0.236초에 통과했다. 교정한 로그인·malformed 지표와 기존 eval 환경 검사를
포함한 후속70개는0.428초에 통과했다. 비교 harness의 setup/oracle은 기존
Python Driver 경로도 사용하므로 signed helper 실행 경계로 맞추는 다음 작업이
필요하다. 새로운 native task 실행과 완전한 동일 조건/backbone/초기상태
cohort 구축은 여전히 남아 있다. 리뷰는 req_18dd2386b10fe078_4b 및
req_18dd239ebba8bc40_4c다.

## G9 후속: signed 비교 host 진입과 책임 신원 제약

comparison의 `_driver`를 InheritedHelperDriver로 바꾸고 signed launcher의
`tacto eval --product-comparison` runpy 진입을 추가했다. helper 채널이 없으면
setup 전에 not_run이며 Python direct fallback이 없다. backend 확인은 앱
metadata/capability만 읽는다. 실제 installed signed command는 exit0으로
대상8개와 observe/act/background prepare/document text 등 capability를
보고했다. 기록은 `../reviews/2026-10-10/signed-comparison-backend.json`이며
source hash는 smoke 뒤 followup 진단 변경 후의 것이라고 구분했다.
이 확인은 task input·모델·사용자 앱 정리·권한 변경을 수행하지 않았다.

Calculator menu/clear 준비가 거부되거나 불확실하면 준비를 중단하고 후속
입력을 반복하지 않는다. 직접 AXPress cleanup이 남은 owned TextEdit 과제는
signed window binding을 구현할 때까지 fixture 생성 전 미실행이다.

Muxa read-only 리뷰(req_18dd2431bbd4bbe0_51)의 P1을 반영했다. 공통
_provider_env는 Tacto helper 채널을 제거하지 않으므로 비교 전용 _agent_env에서
FD/launcher/token 표지를 명시적으로 제거한다. 부모 환경은 바꾸지 않는다.
환경 제거만으로 TCC responsible identity가 분리되지는 않으며, signed host가
spawn한 model/Sky의 실제 책임 신원은 미관측이다. 현재 경로의 task outcome은
보존하되 모든 실행을 제품 비교에서는 제외한다. 외부 agent controller와
signed host를 분리하거나 실제 responsible identity를 관측·감사하는 다음
구현이 필요하다. 이 제한을 동일 조건 비교 완료로 승격하지 않는다.

product flag는 argv 위치와 무관하게 선택하고 중복은 실행 전에 거부한다.
backend/provenance/CLI/install 후속66개는65 PASS/선택적 wheel 설치1 SKIP,
0.477초였다. 환경과 API 연결 검증이며 실제 새 native 과제 성공률은 없다.
전체 G0~G10과 대표 앱/백본/동일 초기 상태·모델 증거 완료 기준을 유지한다.

## G9 후속: 관리자 권한 없는 책임 PID 진단

launchctl procinfo는 현재 환경에서 root가 필요해 거부됐다. 승격하거나
권한을 변경하지 않았다. 실제 libSystem responsibility SPI가 존재하고
현재 process PID를 조회할 수 있음을 읽기 전용으로 확인해 진단 모듈을
추가했다. libproc 경로와 책임 PID를 두 번 읽고 변화·API 없음·읽기 실패는
unavailable/null이다. 기본 Python 코어에 GUI 의존성을 추가하지 않으며
비Darwin에서는 native library를 로드하지 않는다.

`tacto eval --product-comparison --check-responsibility`는 signed controller와
그 controller가 만든 idle Python 자식을 관측했다. 실행 exit0, controller
88162와 child88173은 각각 자기 PID를 책임 PID로 반환했고 경로는 동일한
Python 실행 파일이었다. 자식은 stdin byte로 종료하고 wait로 회수했다.
예외/3초 timeout에는 그 소유 자식만 종료·회수한다. 모델·Sky·native task
입력·권한 변경은 없었다. 실제 기록과 primary ABI source hash는
`../reviews/2026-10-10/signed-controller-responsibility-probe.json`에 보존했다.
source hash는 live probe 뒤 확인한 것으로 구분했다.

반복 경로 일치는 code identity, PID 재사용, descendants 책임 또는 실제
TCC permission 판정을 증명하지 않는다. 실제 Codex/Sky 책임 관측 및 외부
agent↔signed host 분리도 구현하지 않았으므로 기존 비교 제외 조건은 유지한다.
이 진단과 backend/provenance58개가0.334초에 통과했다. 전체 목표와 실제
대표 앱·백본·같은 초기 상태 비교 완료 기준은 계속 유지한다.

Muxa read-only 리뷰(req_18dd24b163cf97f0_55)는 P1 없음으로 판단했다.
앞선 'model이 Tacto launcher 책임 신원을 상속한다' 설명은 가설이었고,
현재 owned Python probe는 self-responsible 관측이므로 그 가설의 직접 증거가
아니라고 정정한다. 그렇다고 실제 Codex/Sky가 Python 귀속이라고 추론하지도
않는다. 아직 그 프로세스를 관측하지 않았다.
cleanup timeout은 소유 자식을 kill/wait한 뒤 닫힌 status와 exit2로 반환하고,
일반 probe 실패의 예외 본문은 출력하지 않는다. caller interrupt는 소유 자식
정리 후 재발생시킨다. start_new_session=True도 결과에 기록하며 이를 TCC
분리로 주장하지 않는다. 추가 회귀 후60개가0.345초에 통과했다.


## G4/G9 후속: 실제 Codex 주 프로세스 관측과 provider 환경 정리

공통 provider 환경에서 private Tacto 채널 표지를 항상 제거하도록 수정했다.
부모 환경·profile·credential은 보존한다. Codex structured adapter에는
호스트 소유 list로만 전달되는 선택적 OwnedProcessSampler를 추가했다.
주 PID를 최대64회 관측하고 요청 종료 시 bounded join하며 실패·timeout에도
진단을 보존한다. tool/model 결과 envelope와 분리하고 후손 및 TCC permission은
미관측으로 유지한다. 긴 요청의 전체 시간 관측은 보장하지 않는다.

실제 도구 없는 Codex 산술 요청은 성공하고 정답 oracle도 통과했다.
31회 관측에서 주 프로세스/책임 실행 경로는 Codex CLI였고 observer는 종료했다.
요청 전후 source hash가 같고 report는 owner-only 새 파일
`../reviews/2026-10-10/live-codex-process-observation.json`에 보존했다.
이 live 요청은 signed controller 비교 과제가 아니므로 앞선 비교 제외를
해제하지 않는다. actual Sky 및 후손 책임 그래프, 외부 agent↔signed host 경계,
owned TextEdit signed cleanup, 같은 초기 상태/모델 cohort와 설치 검증 등
G0~G10 완료 기준은 계속 남는다.

Muxa read-only 리뷰 req_18dd252e1646a7d0_59에서 P1/P2 없음으로 판단했다.
관측 한도·경로 공유 주의·미관측 범위를 문서에 명시했다.


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

관련 회귀105개가4.334초에 통과했다. 후속 lifecycle14개도0.668초에
통과했고 실제 소유 CLI의 cwd가 /tmp임을 추가 확인했다. 실제 소유 Python 부모가 띄운
같은 그룹 후손의 지연 파일 쓰기가 timeout 후 발생하지 않는지 확인했다.
이는 로컬 그룹 종료 증거이며 별도 세션 이탈·원격 모델 취소·Sky 실작업
완료 증거가 아니다. 실행 파일 부재·두 arm의 diagnostic 보존·기존 source
drift/cleanup/provenance 및 provider/documentation 회귀를 포함한다.

소유 프로세스의 진단이 기록된 뒤 OSError가 발생하면 not_run 대신
agent_transport_failed/failed로 남긴다. transport 실패를 미실행으로 바꾸거나
앱 oracle로 성공 판정하지 않는다.


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

최종 관련 테스트51개 중50 PASS/선택적 TACTO_CONTRACT_LIVE 실기1 SKIP,
4.969초였다. 문서 변경 뒤 docs6도0.039초에 통과했다. 없는 test_trace 모듈을
잘못 지정한 첫 검증 명령은 import 오류였고, 실제 test_document_text_trace로
수정한 위 실행이 최종 결과다. 실기 SKIP을 성공으로 계산하지 않는다.


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

최종 관련123개가4.631초에 PASS, 문서 변경 뒤 docs6도0.037초에 PASS였다.


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

## G7 후속: owned native Save producer와 fresh-file 영수증

`tacto eval --product-comparison --check-owned-save-receipt`는 모델 호출 없이
전용 NSSavePanel fixture에서 signed backend로 실행한다. PID를 owned child와
대조하고 새 nonce 파일의 directory/filename/RTF/original_changes_setting을
확인한 뒤 guarded Save를 한 번 실행한다. FreshFileReceipt와 앱의 OK callback,
nonce·경로·SHA256·실제 UTF-8 RTF 바이트를 모두 확인해야 통과한다.
콜백 중복이나 written/refused 혼재는 거부한다. 이는 전용 디렉터리를 intended
producer만 사용한다는 host 가정 아래의 증거이며 실제 TextEdit Save나 일반
앱의 producer 귀속을 증명하지 않는다. Save/chain legacy gate는 유지한다.

owner-only `../reviews/2026-10-10/owned-native-save-writer-cleanup-success.json`은
source stable, 모델 요청0, guarded dispatch acted, typed evidence 오류 없음,
정확한 callback/bytes, owned child 회수 및 fixture 설정 파일 부재를 기록한다.
전체 fixture 구간에서 초기 frontmost는 System Settings, activation은 없었다.
pointer/typing 보존이나 동일 조건 Tacto/Sky 비교 완료로 승격하지 않는다.

실패 보고서는 별도로 보존했다. 처음에는 format 없는 패널이 RTF-only guard에
거부됐고, 새 leaf를 포함한 realpath는 /tmp 별칭을 해석하지 못했다. 부모
디렉터리 realpath 후 새 leaf를 조합한다. collapsed 패널은 exact Identifier의
DisclosureTriangle Value0를 signed AX로 한 번 확장한 뒤 재관측한다.
/tmp의 많은 항목은 AX 관측 예산을 초과해, fixture 임시 디렉터리를 사용자
Library/Caches 아래에 둔다. 중간 root 시행은 성공했지만 공유 작업트리의
임시 untracked 노출을 피하도록 이동했다. window 수1 가정 대신 최대4개 창에서 정확한 panel 후보가
하나인지 확인하며 준비 상태만15초까지 읽는다. UI 입력 재시도는 없다.

NSSavePanel 자체가 fixture 도메인의 설정을 영속 저장할 수 있었다. 실행 인자
기본값만으로 이 부작용이 사라진다고 주장하지 않는다. 기존 populated fixture
설정이 있으면 시작을 거부하고, owned child 종료 뒤 생성된 도메인을 비운다.
남은 empty plist는 owner·regular·single link·크기·읽기 전후 메타데이터와
내용{}을 확인한 후 해당 fixture 파일만 제거한다. 같은 UID의 경쟁 및 최종
확인 이후 변경까지 원자적으로 막는다는 주장은 없다.

최종 owner-only `../reviews/2026-10-10/owned-native-save-writer-cache-success.json`도
PASS였다. 실행 전 설정 파일 부재, 단일 확장 및 guarded Save, 정확한 callback/
바이트/typed evidence, child 회수, 즉시/지연 설정 파일 부재, activation 없음,
source stable을 확인했다. 이는 앞 root 시행과 별개의 fresh fixture다.

관련52개 회귀가 PASS다. Muxa read-only 리뷰의 fixture prefs 및 공유 작업트리
임시 디렉터리 지적을 반영했다. 정리 뒤0.2초 후 설정 파일 부재도 다시 읽는다.
지연 재생성까지 영구히 막는다는 주장은 하지 않는다.

실제 TextEdit Save 인과 증거, 추가 앱/backbone, 입력 보존, 동일 초기 상태와
serving model, Sky 후손 책임, 설치 등 전체 G0~G10 완료 기준은 유지한다.

## G7 후속: 비실행 Save 영수증 거부와 실제 TextEdit 시행

ExistingTextFileReceipt.after_commit은 driver_result를 검사하지 않았다.
파일 내용이 이미 맞으면 None/{}/observation/error not_started/acted not_started도
typed receipt가 발급됐다. 신규 실제 임시 파일 회귀의6 subcase가 baseline에서
모두 실패했고, 이제 driver_dispatch_unverified로 거부한다. 거부도 single-use
컨텍스트를 소모한다. acted 또는 effect가 not_started가 아닌 error만 상태
확인으로 진행한다. effect 없는 error는 replay/FreshFileReceipt와 같이 불확실한
실행으로 다루며 writer를 귀속하지 않는다. 기존 문서 교체/단일사용 테스트의
{} 응답2곳은 acted로 수정해 원래의 문서/재사용 검사를 계속 수행한다.
Muxa read-only req_18dd2b3252304238_7c는 P1/P2 없음이었다.

`tacto eval --product-comparison --check-owned-textedit-save`는 fresh owned .txt의
정확한 본문을 signed helper로 편집하고, 메뉴를 읽어 Save가 이미 enabled면
불필요한 창 준비를 생략한다. disabled면 pinned document window 준비1회 뒤
메뉴 enabled를 재확인한다. File Save에는 exact focused_document 경로를
붙이며, prepare→Save1회→typed receipt→정확한 disk readback을 확인한다.
잠금/전경 변경 뒤 owned 문서를 닫지 않는다. 정리는 기존 signed token close와
관측된 부재 검증을 사용한다. 이 probe가 legacy Save/chain 비교 gate를 제거한
것은 아니며 실제 모델의 Save 비교 시행도 아니다.

owner-only `../reviews/2026-10-10/signed-textedit-save-bound.json`은 PASS였다.
문서 본문 정확, Save 직전 disk_matched_before_save=false, bound dispatch acted,
evidence_error=null, exact_saved_text=true, cleanup closed, artifact_removed=true다.
source SHA prefix34d50532af72 전후 stable, 모델 요청0, 전체 fixture 구간 초기
frontmost=System Settings 및 activation=[]였다. 이는 실제 TextEdit의 새 본문
편집·bound Save 실행·저장된 상태 증거다. autosave가 dispatch 사이에 개입할
가능성과 같은 UID의 다른 writer를 배제한 producer attribution은 아니다.

앞 scoped Window의 role-alone Selector 거부와 불필요한 prepare_window의
not_started 실패는 별도 signed-textedit-save-initial/prepared.json으로 보존했다.
두 실패에서도 owned 문서 정리와 activation 없음이 확인됐다. 필요한 창 준비가
실제 TextEdit에서 작동한다고 승격하지 않는다. 신규 probe의 enabled/disabled/
준비 실패/준비 후 여전히 disabled/환경 변경 뒤 cleanup 금지 및 receipt 관련
92개 테스트가 PASS였다. req_18dd2b5ea3f12318_7d 리뷰는 P1/P2 없음이었다.

다음에는 Save/chain 비교 fixture의 legacy cleanup을 signed lifecycle로
이행하고 실제 모델 비교를 수행한다. 원래 G0~G10과 인과·입력 보존·동일 조건
완료 기준은 그대로이며 이번 실제 Save 성공으로 전체 완료를 선언하지 않는다.

## G8/G9 후속: signed 저장 비교와 앱 간 작업 실패 실측

textedit_save_owned와 calc_to_textedit의 setup/cleanup을 signed lifecycle로
이행했다. 과제는 basename만 아니라 새 owned path를 지정하며 setup 전 list는
preview만 사용한다. Save oracle은 영수증 코드와 독립인 bounded fd/lstat 읽기와
original0700 directory identity/정확한 구성원, pinned signed 본문을 결합한다.
계약은 signed-owned-document-exact-utf8-saved-state-v3다. 비교 코드에 남은
legacy custom cleanup gate를 전역으로 제거하지 않았다. chain wrapper도
fixture evidence를 기록하도록 setup identity 대신 cleanup identity를 사용한다.

owner-only `../reviews/2026-10-10/product-comparison-20261010-214334.jsonl`에서
실제 Sky/Tacto Save가 각각49.6/45.1초에 PASS였다. 두 arm 모두 exact disk와
본문, 초기 빈 문서, signed close/부재/삭제 및 cleanup completed를 기록했다.
agent 구간 초기 frontmost=System Settings, activation=[]였다. source prefix
b930dd980e0e가 두 arm 전후 stable이다. CLI input/cache/output은
Sky188422/178944/723, Tacto132725/105472/933다. tool item event 수는
Sky node_repl:js16, Tacto shell:tacto12/shell:other2이며 고유 호출 수가 아니다.
실제 serving model/cost, nested provider 총 비용, typing/caret/pointer 보존,
Sky descendant/TCC graph, 완전한 초기 UI는 미검증이다. 비교 제외와 command
exit2를 유지한다. 저장된 상태를 autosave 없는 명시 Save 인과 증거로 승격하지
않는다. 동일 cohort의 chain 두 arm은 setup KeyError obs_id로 not_run이었다.

signed observe의 target_not_found 및 NSRunningApplication count0로 Calculator
미실행을 확인했다. calc_reset은 해당 오류에만 unlocked 확인 후 open -g -b로
배경 실행하고,8초 read-only 재관측/activation witness를 확인한다. 다른 오류는
명시 unavailable로 종료하며 무조건 obs_id를 읽지 않는다. signed 독립 읽기로
표시값0/모드basic을 확인하고 setup evidence를 남긴다. 새로 실행한 Calculator는
자동 종료하거나 포커스를 복원하지 않으며 left_running boolean을 남긴다.

`../reviews/2026-10-10/product-comparison-20261010-214831.jsonl`의 실제 chain은
Tacto44.2초/Sky40.8초 모두 FAIL이었다. Tacto는 CLI에서 정확한 TextEdit 문서
경로로 관측을 제한할 수 없다고 중단했고, Sky는 background 입력과 입력 보존
지원 여부를 확인하지 못해 중단했다. 두 문서 본문은 빈 상태였고 signed cleanup
completed/artifact removed, activation 없음, source stable이었다. Tacto setup은
Calculator background launch 및 초기0/basic을 독립 검증했다. 이 실패를 새
준비 성공이나 다른 과제의 Save 성공으로 지우지 않는다. command exit1이었다.

chain의 이전 oracle은 owned 본문437만 검증했다. 이제 Calculator 표시437도
독립 검증해야 하는 signed-calculator-and-owned-document-exact-text-v3를
사용한다. 명시 Save를 요구하지 않는 앱 간 결과 전달 과제이며 새 계약의 실제
model 실행은 아직 없다. 위 실패 cohort는 이전 v2 oracle로 그대로 보존한다.
두 새 prerequisites audit는 source/runtime 계약을 확인하되 not_run/제외를
보존하고 비교율을 계산하지 않는다.

오래된 readiness 단위 테스트가 subprocess.run을 mock한 반면 실제 agent
경로는 _run_agent/Popen으로 바뀌어 있었다. signed channel mock 보강 후
실제 CLI가 기동된 테스트 실행을 SIGINT로 중단했다. _run_codex의 BaseException
killpg/reap 및 프로세스 부재를 확인했다. 이 중단 실행의 모델 usage/cost와 GUI
효과는 계측되지 않았으며 모델 호출 없는 단위 테스트 증거로 사용하지 않는다.
현재 테스트는 _run_agent를 mock하고 Popen fail-fast 경계를 추가했다. 채널은
명시 mock이며 eligible=false 검사는 실제 책임 경계 미검증 계약에 맞춘다.
최종 관련101개 테스트가 PASS이며 모델/GUI subprocess를 실행하지 않는다.

Muxa req_18dd2b9f73eeaeb0_80 및 req_18dd2bd0e99e15e8_81 리뷰의 P1/P2는
없었다. 다음 실제 기능 격차는 installed CLI의 path-scoped 문서 관측/실행이다.
Python API의 document_path/token 지원을 CLI 사용자가 안전하게 활용할 수
있도록 연결하고 재평가한다. 전체 G0~G10 완료 기준을 유지한다.

## G8/G9 비교 중단 증거 보존 (2026-10-24)

현재 설치본을 지정한 `benchmark_matched_conditions.py --preflight-only`가
통과했다. 비공개 원본은 `reviews/goal-resume-20261024-preflight/preflight.json`이다.
이는 런타임·안내·실행 파일의 사전 조건 검사이며 실제 모델 호출·GUI 실행,
Sky 도구 접근, 실제 serving model 또는 동일 조건 비교 완료를 증명하지 않는다.

비교의 agent/setup/oracle/cleanup 예외나 사용자 인터럽트가 최종 보고서를
남기지 않는 격차를 수정했다. 이제 완료된 arm·관측 usage와 중단된 arm·미시도
개수를 별도로 남기고, 중단 arm의 usage/cost와 source 안정성은 unknown으로
표시한다. 부분 결과를 전체 비교 성공 또는 비용0으로 승격하지 않는다.
예외 본문은 개인정보를 포함할 수 있어 저장하지 않고 예외 종류만 기록한다.
관련 검사는 실제 모델·GUI 없이 orchestration 대역으로 실행한다.

다음 검증은 peer의 현재 창 입력 수정과 충돌하지 않는 GUI 구간을 확보한 뒤
설치본을 고정한 실제 비교를 실행하는 것이다. G0~G10의 실앱·다중 백본·입력
보존·인과적 완료 증거 기준은 위 원래 범위를 유지하며 아직 전체 완료가 아니다.

### 실제 프로필 및 Sky 도구 환경 확인

비교가 `CODEX_HOME`을 상속하면서 기본 `~/.codex/config.toml`만 기록하던
오류를 수정했다. 이제 실제 프로필의 config 경로·존재 여부·SHA256과 실행
전후 동일성을 기록한다. 값과 인증파일은 읽거나 보고서에 저장하지 않는다.
설정 변경 시 작업 oracle이 통과해도 동일 조건 판정은 false다. config 파일의
해시는 전역 지침·원격 설정·실제 serving model의 동일성을 증명하지 않는다.

`reviews/goal-resume-20261024-profile-preflight/preflight.json`은 이 프로필
기록을 포함한 사전 점검이다. 별도 실제 Codex 세션의
`reviews/goal-resume-20261024-sky-environment/agent/stdout.jsonl`에서는
node_repl/js로 @oai/sky를 import하고 target=mac을 확인했다. 앱 관찰·입력은
하지 않았다. 16.19초, CLI가 보고한 input55533/cache47616/new7917/output233이며
과제 벤치마크나 실제 청구 비용의 증거가 아니다. 보고된 serving model은 없다.

### 새 독립 실제 모델 비교 완료 범위

2026-10-24 rc.6 설치본을 사용한 bonus on/off/버튼 이름 변경의 3쌍에서
Tacto3/3·Sky3/3의 정확한 결과·단일 commit을 확인했다. 총시간77.00/135.40초,
CLI 새 입력 합계23,247/44,386이며 세부 조건과 한계는
[비교 기록](benchmark-records.md)의 새 절에 있다. 실제 serving model·숨은
context·완전한 입력 상태 동등성 미검증으로 comparison_eligible=false를 유지한다.

실제 앱 비교의 외부 worker 진입에서 cold-start 옵션이 누락되는 회귀도
실패 테스트로 재현해 수정했다(관련31건 통과). rc.6 설치 wheel은 개발용 fixture를
포함하지 않아 worker 연결이 'fixture는 wheel에 포함되지 않음'으로 종료됐다.
이를 제품 task 실패나 모델 호출로 세지 않는다. 별도 서명된 소스 checkout
worker의 메타데이터 연결은 통과했고 실제 두 앱 과제를 별도 cohort로 실행한다.
이 경로의 결과를 rc.6 exact-DMG qualification과 혼동하지 않는다.

### 실제 앱 병목에 근거한 document-scoped session

실제 두 앱 과제는 양쪽 성공했으나 Tacto106.3초/Sky26.1초였고, Tacto는 여러
안내·긴 내부 문서·JSON 수정 경로를 거쳤다. 전경 변경·책임 경계 미검증으로
엄격 비교 제외는 유지한다. 이 발견에서 session --document 경로를 구현했다.
기존 DocumentScopedDriver를 첫 관찰 전 한 번만 연결하고, 모든 관찰/재생이
같은 토큰을 쓰며 실패 시 전체 앱으로 넓히거나 다시 pin하지 않는다. 저장한
Flow 자체에 scope가 보존되는 것은 아니므로 scoped replay argv를 별도 반환한다.

모의 replay/가이드 예제·실제 서명 소스/TextEdit 본문 검증과 독립 리뷰를 수행했다.
새 안내/소스의 실제 모델 과제도 성공했으나 최종 selector 안내 수정 후 시간은
재측정하지 않았다. 속도·토큰 개선을 확정하거나 rc.6 배포 완료로 표기하지 않는다.
세부 원본·시간·한계는 [비교 기록](benchmark-records.md)의 해당 절을 본다.
다음 우선순위는 최종 안내의 독립 반복 측정, 다른 실제 앱/백본의 select·시각·
장기 복구 및 저장/전송의 인과 증거 검증이다. 전체 목표는 계속 활성 상태다.

## 2026-10-24 후속: 다중 백본·시각·장기 복구의 실제 확인

공증용 Vault 세션 갱신은 대기 상태다. rc.7 고정 소스3790c18과 빌드/회귀
증빙을 바꾸거나 Vault 상태를 반복 확인하지 않고 별도 source-runtime 검증을
수행했다. 아래 원본의 private digest 목록은
`reviews/goal-resume-20261024-capability-audit/evidence.json`에 있다.

| 항목 | 실제 확인 | 전체 판정과 미검증 |
|---|---|---|
| G4 Claude envelope | signed launcher 경로, 보고 모델claude-opus-5-5, 정확한 JSON응답, 총입력609/출력17,2.43초. cache생성607·uncached2를 분리 | 이 단일 응답 검사는 PASS. CLI 표시비용USD0.005204는 list estimate이고 실제 청구가 아님. cancellation_supported=false, 원격 취소 미보장 |
| G1/G2 Claude 큰 선택 목록 | 실제131항목 ComboBox에서 Choice127/index130/count1/closed. 모델8요청, host o200k_base 예산2500 내 최대1977토큰 | 전체FAIL: input audit CHANGED. source subset불변. serving tokenizer/전체CLI context예산을 증명하지 않음 |
| G6/G7 장기 다중앱 | native24단계 accepted24·Cancel3·Other0,8/14/20단계의 실제TextEdit 저장상태3회와 문서정리 완료, 모델0 | task_oracle=true이나 전체FAIL: input audit CHANGED. 저장상태 일치는 어느writer가 썼는지의 인과 증거가 아님 |
| G5 Codex 시각 입력 | AX밖 소유AppKit canvas의 목표 클릭·Right·정확A😀한글 수신, 다른창입력0. 실제이미지모델2요청, 소유child회수 | 전체FAIL: input audit CHANGED. source subset불변. 일반사용자앱/동시사용자입력 보존 검증으로 승격하지 않음 |

이 세 native 과제에서 작업 결과와 별개로 전경·포커스 변화가 관측됐으므로
실패를 지우거나 입력 보존을 통과로 바꾸지 않았다. 장기 복구의 변화는 원래
전경 프로세스 종료/설정앱 전경 전환과 함께 나타났으나, 원인을 Tacto 또는
사용자에게 귀속할 증거는 없다. sample gap·미관측 구간도 원본에 유지한다.
조용한 환경에서의 입력 보존 검증은 남아 있다.

장기 복구 실패의 기존 짧은 메시지는 passed=false/error_class=null만 보여
작업 실패와 입력 감사 실패를 구분하지 못했다. 요약에 task_oracle·저장상태·
input_audit_status를 추가하고, 전체 실패와 개인정보 비노출을 유지했다.
관련15개 단위/대역 검사가 통과했다. 이 요약 개선은 원본의 FAIL을 PASS로
바꾸지 않으며 rc.7 고정 배포본에 소급 포함하지 않는다.

june-mba는 rc.6 설치와 콘솔 연결을 읽기 전용으로 확인했지만 확인한4개
통상 소스 위치에는 평가checkout이 없었다. 원격에 평가환경을 몰래 설치하거나
권한을 변경하지 않았다. 이미 실행한 source시험을 원격/새사용자 시험으로
표기하지 않는다. 전체 G0~G10 완료 기준은 유지한다.

## 2026-10-24 후속: 인과적 재개와 Claude 에이전트 비교 경로

`reviews/goal-resume-20261024-causal-recovery/evidence.json`과 해당
requirements-source-index는 현재 관련 구현·검사 파일 및 원본 해시를 기록한다.
파일 존재를 완료 증거로 쓰지 않는다. 실제 signed producer worker 재시작에서
첫 worker exit17 뒤 둘째 worker exit0, 원래 journal 보존, 인과영수증 확인,
새 native 입력1회(count0→1)를 확인했다. native_causal_continuation_verified=true
이지만 input audit CHANGED로 전체FAIL을 유지한다. 일반앱/명시TextEdit Save의
생산자 증명이 아니며 rc.7 exact-DMG 결과도 아니다.

비교 도구에 `--tacto-provider claude`를 추가했다. 기존 기본값은 Codex이며
Sky는 항상 Codex다. Claude에는 Codex 전용 모델·effort 플래그를 보내지 않는다.
백본·모델 요청은 arm별 기록하고 Claude모드는 requested_backbones_matched=false,
requested_conditions_matched=false,comparison_eligible=false다. 중단 보고서에도
같은 불일치를 남긴다. provider별 토큰 단위/추정비용을 동일 청구 단위로 비교하지
않는다. 현재 타이밍 파서는 Codex용이므로 Claude에는 미지원/unknown을 기록하고
도구 시간이0이었다고 만들지 않는다. 관련25개 비조작 검사가 통과했다.

Claude 비교 preflight는 실행 파일/안내 점검만 통과했으며 GUI·모델0회였다.
별도 실제 Claude Code CLI 비조작 요청은 조직 구독 접근 비활성의 합성 API 오류로
exit1이었다. 앞서 통과한 signed 단일요청 경로와 다르다. 원본은
`reviews/goal-resume-20261024-claude-agent-route/agent/stdout.jsonl`, 닫힌 진단은
failure-classification.json이다. hook이 init 앞에 오는 실제 frame을 처리하고
organization_access_disabled만 보고하며 계정 오류 본문은 공개하지 않는다.
이를 task 성공·모델 비용 절감·전체 Claude 사용 불가로 해석하지 않는다.

다음 실제 GUI 검증은 사용 가능한 조용한 환경에 대한 사용자 답을 기다린다.
현재 Mac에서는 서로 다른 작업의 전경 변화가 관측됐고 원격의 확인한4개 경로에는
평가 소스가 없었다. 임의의 권한 변경/설치나 같은 실패의 무의미한 재실행을 하지
않는다. rc.7은 공식 Vault 세션 갱신을 기다리며 고정 빌드/회귀 증빙을 재사용할
준비가 됐다. 이 때문에 전체 목표 완료를 선언하지 않는다.
