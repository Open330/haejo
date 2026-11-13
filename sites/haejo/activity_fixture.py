#!/usr/bin/env python3
"""Write the made-up activity records behind the landing page's history screenshot.

    python3 sites/haejo/activity_fixture.py /tmp/haejo-activity-fixture
    /Applications/Haejo.app/Contents/MacOS/HaejoSetup \
        --activity-snapshot /tmp/haejo-activity-shot \
        --activity-fixture /tmp/haejo-activity-fixture \
        -AppleLanguages '(ko)' -AppleLocale ko_KR

The second command draws the app's history page offscreen into app.png
(2120x1400); no window appears. Every task, time and reason here is composed
for the page and follows the story of the film (sites/haejo/film). Nothing is
read from a person's own records.
"""
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DAY = datetime(2026, 11, 13, tzinfo=KST)
SAFARI, TEXTEDIT, FINDER = 'com.apple.Safari', 'com.apple.TextEdit', 'com.apple.finder'

NOVEMBER = [
    ('스타벅스 역삼점', 18900), ('카카오T 택시', 14200), ('교보문고 강남점', 32000), ('다이소 역삼점', 8500),
    ('본죽 선릉점', 27000), ('코레일 KTX', 59800), ('쿠팡', 23400), ('한솔도시락 역삼점', 31500),
]
FIELDS = ['사용일자 입력', '가맹점명 입력', '비용 분류 선택', '금액 입력', '프로젝트 코드 입력', '사용 내용 입력', '등록']
FORM = ['observe', 'set_value', 'set_value', 'click', 'set_value', 'set_value', 'set_value', 'click', 'read']


def expense_calls():
    calls = [('observe', TEXTEDIT, '카드 사용내역 8건 읽기', ['observe', 'document_text'], 1.42),
             ('open-url', SAFARI, '경비 시스템 페이지를 쓰던 앱 뒤에서 열기', ['observe'], 1.18)]
    steps = ['set_value', 'set_value', 'click', 'set_value', 'set_value', 'set_value', 'click']
    for label, step in zip(FIELDS, steps):
        calls.append(('run', SAFARI, f'1/8 {NOVEMBER[0][0]} · {label}', ['observe', step], 0.9))
    for n, (merchant, amount) in enumerate(NOVEMBER[1:], start=2):
        calls.append(('run', SAFARI, f'{n}/8 {merchant} {amount:,}원 등록', FORM, 3.3 + (n % 3) * 0.29))
    return calls


TASKS = [
    # (start HH:MM, goal, request, calls)
    ('09:12', '주간 이슈 점검', '이번 주에 열린 버그를 댓글 많은 순으로 모아서 메모로 정리해줘', [
        ('open-url', SAFARI, '이슈 목록 페이지 열기', ['observe'], 1.31),
        ('session', SAFARI, '열린 버그만 남기고 댓글순 정렬', ['observe', 'click', 'click', 'read'], 4.12),
        ('session', TEXTEDIT, '검토할 이슈 메모 작성', ['observe', 'set_value', 'read'], 2.05),
    ]),
    ('10:40', '킥오프 회의록 정리', '킥오프 회의 메모를 회의록 양식에 맞춰 정리하고 저장해줘', [
        ('observe', TEXTEDIT, '회의 메모 읽기', ['observe', 'document_text'], 1.12),
        ('run', TEXTEDIT, '회의록 양식으로 입력', ['observe', 'set_value', 'read'], 2.64),
        ('run', TEXTEDIT, '저장하고 파일 내용 확인', ['observe', 'menu', 'read'], 1.87),
    ]),
    ('13:05', '워크숍 자료 폴더 정리', '워크숍 자료 폴더를 종류별로 보고 이름순으로 정렬해줘', [
        ('run', FINDER, '종류순, 이름순으로 정렬', ['observe', 'click', 'click', 'read'], 3.4),
    ]),
    ('15:20', '세금계산서 PDF 첨부', '10월 세금계산서 PDF 두 개를 정산 페이지에 첨부해줘', [
        ('open-url', SAFARI, '정산 페이지를 쓰던 앱 뒤에서 열기', ['observe'], 1.22),
        ('run', SAFARI, 'PDF 2개 첨부하고 파일 이름 확인', ['observe', 'upload', 'read'], 2.96),
    ]),
    ('16:42', '11월 법인카드 경비 등록', '11월 법인카드 사용내역 8건을 사내 경비 시스템에 등록해줘', expense_calls()),
]


def stamp(moment):
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f+00:00')


def main(root):
    root = Path(root)
    logs, tasks = root / 'Logs', root / 'Tasks'
    logs.mkdir(parents=True, exist_ok=True)
    tasks.mkdir(exist_ok=True)
    for start, goal, detail, calls in TASKS:
        task_id = 't-' + hashlib.sha256(goal.encode()).hexdigest()[:24]
        hour, minute = map(int, start.split(':'))
        moment = DAY.replace(hour=hour, minute=minute, second=7)
        folder = tasks / task_id
        folder.mkdir(exist_ok=True)
        events = []
        for index, (command, target, why, steps, seconds) in enumerate(calls):
            invocation = hashlib.sha256(f'{goal}/{index}'.encode()).hexdigest()[:32]
            events.append(dict(schema=1, event='invocation_start', invocation=invocation, why=why, at=stamp(moment)))
            total = int(seconds * 1000)
            rows = [dict(schema=1, event='command_start', command=command, task_id=task_id,
                         invocation_id=invocation, at=stamp(moment), elapsed_ms=0)]
            for position, step in enumerate(steps):
                operation = step if step in ('observe', 'document_text') else 'act'
                access = dict(schema=1, operation=operation, target=target)
                if operation == 'act':
                    access['action'] = step
                begin = int(total * (position + 0.35) / (len(steps) + 0.5))
                rows.append(dict(access, event='access_start', elapsed_ms=begin))
                rows.append(dict(access, event='access_end', type='result', elapsed_ms=begin + 90))
            rows.append(dict(schema=1, event='command_end', exit_code=0, elapsed_ms=total))
            name = f"haejo-{moment.astimezone(timezone.utc):%Y%m%dT%H%M%S%f}Z-{invocation}.jsonl"
            (logs / name).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
            moment += timedelta(seconds=seconds + 1.6)
        (folder / 'task.json').write_text(json.dumps(dict(
            schema=1, id=task_id, created_at=stamp(DAY.replace(hour=hour, minute=minute)), closed_at=stamp(moment),
            state='closed', result='done', goal=goal, detail=detail), ensure_ascii=False))
        (folder / 'events.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in events))
    print(root)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'haejo-activity-fixture')
