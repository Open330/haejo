"""One fresh body-state read after a scoped edit's uncertain completion.

This is an observation, never a Save receipt, writer attribution, permission,
resume instruction, or reason to retry input. No document text/token is emitted.
"""
import unicodedata

MARKER = 'TACTO_DOCUMENT_STATE '
MAX_UTF16_UNITS = 1_000_000


def failure_readback(driver, flow, result):
    from .document_scope import DocumentScopedDriver
    if (not isinstance(driver,DocumentScopedDriver) or result.ok
            or flow.target != driver.target or not result.log):
        return None
    last=result.log[-1]
    index=last.get('step')
    if (last.get('status')!='unverified' or last.get('error')!='commit_unverified'
            or type(index) is not int or not 0<=index<len(flow.steps)):
        return None
    step=flow.steps[index]
    value=step.params.get('value')
    if (step.action!='set_value' or type(value) is not str or step.into_sensitive_field
            or step.selector is None or step.selector.identifier!='First Text View'
            or step.selector.role not in (None,'TextArea','AXTextArea')
            or step.safety is None or 'write_persistent' not in step.safety.effects
            or set(step.safety.effects)-{'read','write_ephemeral','write_persistent'}):
        return None
    event=next((e for e in result.events if e.get('event_id')==last.get('event_id')),None)
    action=event.get('action') if event is not None else None
    if (event is None or event.get('target')!=flow.target or type(action) is not dict
            or action.get('name')!='set_value' or action.get('value')!=value):
        return None
    report={'scope':'visible_document_text','step':index,
            'matches_requested_text':None,'remaining_steps':len(flow.steps)-index-1,
            'save_verified':False,'dispatch_confirmed':False,'write_retried':False}
    try:
        units=len(value.encode('utf-16-le'))//2
        if units>MAX_UTF16_UNITS:return None
        # Same pin and channel, once. A longer or incomplete native snapshot
        # is unavailable; it is never compared as a truncated prefix.
        reply=driver.document_text(flow.target,max_utf16_units=min(MAX_UTF16_UNITS,units+1))
        if (type(reply) is dict and reply.get('type')=='document_text'
                and reply.get('text_complete') is True and type(reply.get('text')) is str
                and type(reply.get('document_path')) is str
                and unicodedata.normalize('NFC',reply['document_path'])==driver.path):
            report['matches_requested_text']=reply['text']==value
        else:report['reason']='readback_unavailable'
    except Exception:
        report['reason']='readback_unavailable'
    return report


def present_body_state(report, emit):
    """Describe a fresh body observation without upgrading the Flow receipt."""
    if not isinstance(report, dict) or report.get('scope') != 'visible_document_text':
        return False
    match = report.get('matches_requested_text')
    remaining = report.get('remaining_steps')
    if match is True and type(remaining) is int and remaining == 0:
        emit('body_verified — 요청한 본문과 현재 문서 내용이 일치합니다. 추가 읽기나 재입력은 필요하지 않습니다. '
             '저장 여부와 쓰기 실행 영수증은 확인되지 않았습니다.')
    elif match is True:
        emit('body_verified_partial — 현재 본문은 일치하지만 뒤 단계가 남아 있습니다. '
             '전체 Flow 완료나 저장을 확인한 결과는 아닙니다. 재입력하지 말고 남은 단계를 확인하세요.')
    elif match is False:
        emit('body_mismatch — 현재 본문이 요청과 다릅니다. 저장·쓰기 실행은 미확인입니다. '
             '재입력 전에 현재 문서를 확인하세요.')
    else:
        emit('body_unavailable — 현재 본문을 확인하지 못했습니다. 저장·쓰기 실행은 미확인입니다. '
             '재입력 전에 현재 문서를 확인하세요.')
    return True
