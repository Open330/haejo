"""Actual TextEdit Save As: owned source, new destination, bound transition.

Run only through the signed evaluator. Fixture bootstrap writes a known RTF and
opens it in the background; the Save As operation itself uses the normal Flow.
This is not model, Sky, kernel writer, formatting or attachment evidence.
"""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from examples.probes.signed_owned_textedit import SignedOwnedTextEdit, TARGET


def run_probe(driver):
    from examples.probes.focus_witness import FocusWitness
    from tacto.agent import Agent
    from tacto.commit_evidence import DocumentSaveEvidence
    from tacto.document_snapshot import SnapshotDriver, SnapshotUnavailable, REQUIRED, _window_index
    from tacto.flow import replay
    from tacto.library import textedit_save_as
    from tacto.textedit_receipt import make_textedit_receipt

    report = {'passed':False, 'scope':'owned_actual_TextEdit_guarded_Save_As_transition',
              'model_requests':0, 'comparison_eligible':False,
              'kernel_writer_attribution_verified':False,
              'formatting_fidelity_verified':False, 'attachment_fidelity_verified':False,
              'guarded_save_attempts':0, 'cleanup_status':'not_started'}
    timeline = []
    def phase(name):
        timeline.append({'phase':name, 't':time.monotonic()})
    root = Path(__file__).resolve().parents[2]
    sources = [*root.glob('tacto/*.py'), *root.glob('helper/*.swift'),
               root/'examples/eval.py', root/'launcher/tacto.swift', root/'launcher/tacto', root/'helper/tacto-helper',
               root/'helper/Tacto Helper.app/Contents/MacOS/TactoHelper', Path(__file__)]
    hashes = lambda: {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sources if p.is_file()}
    report['source_before'] = hashes()
    if not REQUIRED <= set(getattr(driver, 'capabilities', ())):
        return {**report, 'failure_code':'native_capability_unavailable'}
    nonce = secrets.token_hex(12)
    body = 'Tacto native Save As '+nonce+'\nExact receiving text.\n'
    directory = Path(tempfile.mkdtemp(prefix='tacto-save-as-')).resolve()
    source = directory/('source-'+nonce+'.rtf')
    destination = (Path.home()/'Downloads').resolve()/('tacto-save-as-'+nonce+'.rtf')
    fixture = SignedOwnedTextEdit(driver, source.name)
    source.write_bytes(b'{\\rtf1\\ansi '+body.replace('\n','\\par\n').encode('ascii')+b'}')
    source.chmod(0o600)
    report.update(source_path=str(source), destination_path=str(destination))
    original_act = driver.act
    original_mode = driver.document_mode
    original_attachments = driver.document_attachment_metadata
    original_send = driver._send
    def send(message):
        response = original_send(message)
        if message.get('type')=='document_attachment_metadata' and isinstance(response, dict):
            report['attachment_transport'] = {key:response[key] for key in
                ('type','error','reason_code','sampled_stable','utf16_length','evidence_kind',
                 'proves_no_intermediate_change','source_format_verified',
                 'attachment_completeness_verified','attachment_payload_verified','authorizes_save')
                 if key in response}
            report['attachment_transport'].update(keys=sorted(response),
                token_matches=response.get('document_token')==message.get('document_token'),
                text_hash_matches=response.get('text_sha256')==hashlib.sha256(body.encode()).hexdigest())
        if message.get('type')=='save_panel' and isinstance(response, dict):
            report['native_save_panel'] = {key:response[key] for key in
                ('type','error','effect','detail','format','authorizes_save') if key in response}
        return response
    def attachments(*args, **kwargs):
        response = original_attachments(*args, **kwargs)
        report['native_attachments'] = {key:response[key] for key in
            ('type','error','reason_code','sampled_stable','utf16_length') if key in response}
        return response
    def mode(*args, **kwargs):
        response = original_mode(*args, **kwargs)
        report['native_mode'] = {key:response[key] for key in
            ('type','error','reason_code','editing_mode','edited') if key in response}
        return response
    def act(*args, **kwargs):
        action = args[2] if len(args)>2 else kwargs.get('action', {})
        entry = {'action':action.get('name'), 't':time.monotonic()}
        timeline.append(entry)
        if kwargs.get('save_panel_token') is not None:
            report['guarded_save_attempts'] += 1
        response = original_act(*args, **kwargs)
        entry.update(end_t=time.monotonic(), result_type=response.get('type'))
        return response
    driver.act = act
    driver.document_mode = mode
    driver.document_attachment_metadata = attachments
    driver._send = send
    began = time.monotonic()
    witness = None
    open_attempted = False
    try:
        with FocusWitness() as witness:
            try:
                report['stage'] = 'source_setup'
                phase('source_setup')
                report['background_initial'] = witness.initial != TARGET
                open_attempted = True
                opened = subprocess.run(['open','-g','-a','TextEdit',str(source)],
                                        capture_output=True, timeout=20)
                if opened.returncode:
                    raise RuntimeError('owned_source_open_failed')
                info = directory.stat()
                fixture.resume(directory, (info.st_dev,info.st_ino), expected_text=body)
                observed = driver.observe(TARGET, document_token=fixture.token)
                if observed.get('type') != 'observation':
                    raise RuntimeError('owned_window_unavailable')
                window = _window_index(observed['tree'])
                snapshots = SnapshotDriver(driver, source_window=(observed['obs_id'],window))
                report['stage'] = 'snapshot'
                phase('snapshot')
                snapshot_began = time.monotonic()
                adapter = make_textedit_receipt(snapshots, target=TARGET,
                    directory=str(destination.parent), filename=destination.name, timeout_seconds=5)
                report['snapshot_seconds'] = time.monotonic()-snapshot_began
                # The initial path lookup was deliberately path-bound. Replace
                # it with the adapter's explicit window pin, which allows URL
                # transition while preserving the native window/body identity.
                fixture.token = adapter._initial['document_token']
                flow = textedit_save_as().bind(filename=destination.name, folder='Downloads')
                approvals, blocked = Agent(driver=driver).authorize(flow, ask=lambda _:True)
                if blocked:
                    raise RuntimeError('owned_flow_not_authorized')
                report['stage'] = 'flow'
                phase('flow')
                replay_began = time.monotonic()
                hooks = Agent.commit_adapter_hooks(adapter)
                original_prepare = hooks['prepare_commit']
                def prepare(event):
                    try:
                        return original_prepare(event)
                    except (ValueError, TypeError) as error:
                        report['prepare_error_class']=type(error).__name__
                        report['prepare_error']=str(error)[:300]
                        raise
                hooks['prepare_commit']=prepare
                result = replay(driver, flow, approvals=approvals,
                    **hooks)
                report['replay_seconds'] = time.monotonic()-replay_began
                report.update(flow_ok=result.ok, event_states=[e['state'] for e in result.events],
                              flow_errors=[r.get('error') for r in result.log if r.get('error')])
                report['flow_log'] = []
                for row in result.log:
                    entry = {key:row[key] for key in ('status','step','action','stage','error') if key in row}
                    detail = row.get('detail')
                    if isinstance(detail, dict):
                        entry['detail'] = {key:detail[key] for key in ('type','error','effect') if key in detail}
                    elif isinstance(detail, str):
                        entry['detail'] = detail[:400]
                    report['flow_log'].append(entry)
                proofs = list(result.commit_evidence.values())
                report['document_save_evidence'] = (len(proofs)==1
                    and type(proofs[0].evidence) is DocumentSaveEvidence
                    and proofs[0].evidence.source_path == str(source)
                    and proofs[0].evidence.path == str(destination))
                # A separate file read and fresh destination lookup do not
                # reuse the adapter's returned body as their expectation.
                report['stage'] = 'receiving_readback'
                phase('receiving_readback')
                if destination.is_file():
                    decoded = subprocess.run(['/usr/bin/textutil','-convert','txt','-stdout',str(destination)],
                        capture_output=True, timeout=10, check=True).stdout.decode('utf-8')
                    report['exact_file_text'] = decoded == body
                    report['destination_sha256'] = hashlib.sha256(destination.read_bytes()).hexdigest()
                lookup = driver.document_text(TARGET, document_path=str(destination))
                report['exact_destination_document'] = (lookup.get('type')=='document_text'
                    and lookup.get('text_complete') is True and lookup.get('text')==body
                    and lookup.get('document_path')==str(destination))
                report['passed'] = (result.ok and report['document_save_evidence']
                    and report.get('exact_file_text') is True and report['exact_destination_document']
                    and report['guarded_save_attempts']==1)
            finally:
                phase('cleanup')
                # Cancel only this owned document's observed Save panel, once.
                # A missing/unknown response remains in the report; no retry.
                if fixture.token and not report['passed']:
                    from tacto.flow import Selector
                    observation = driver.observe(TARGET, document_token=fixture.token)
                    if observation.get('type')=='observation':
                        try:
                            cancel, _ = Selector(role='Button', title=['Cancel','취소'],
                                                  ancestor='save-panel').resolve(observation['tree'])
                        except LookupError:
                            pass
                        else:
                            report['cancel_attempted']=True
                            reply = driver.act(observation['obs_id'], TARGET,
                                {'name':'click','element_index':cancel}, risk_class='preapproved',
                                approved=True, intent_text='Cancel only the evaluator-owned Save As panel')
                            report['cancel_response_type']=reply.get('type')
                report['cleanup_status'] = fixture.cleanup() if fixture.token else 'not_bound_left_as_is'
                report['save_sheet_left_open'] = None
                if report['cleanup_status']=='closed':
                    report['save_sheet_left_open'] = False
                elif fixture.token:
                    remaining = driver.observe(TARGET, document_token=fixture.token)
                    if remaining.get('type')=='observation':
                        report['save_sheet_left_open'] = any(' Sheet ' in line or ' AXSheet ' in line
                            for line in remaining.get('tree','').splitlines())
                if report['cleanup_status']=='closed' and report.get('exact_file_text') is True:
                    raw = destination.read_bytes()
                    if hashlib.sha256(raw).hexdigest()==report.get('destination_sha256'):
                        destination.unlink()
                        report['destination_removed']=True
        report['focus'] = witness.summary()
        report['passed'] = (report['passed'] and report['cleanup_status']=='closed'
            and report.get('destination_removed') is True and report['focus']['activations']==[])
    except Exception as error:
        report['passed'] = False
        report['failure_class'] = type(error).__name__
        codes = {'target_initially_frontmost','owned_source_open_failed','owned_window_unavailable',
                 'owned_flow_not_authorized'}
        if isinstance(error, SnapshotUnavailable) or str(error) in codes:
            report['failure_code']=str(error)
    finally:
        driver.act = original_act
        driver.document_mode = original_mode
        driver.document_attachment_metadata = original_attachments
        driver._send = original_send
        if not open_attempted:
            source.unlink()
            directory.rmdir()
            report['cleanup_status']='never_opened_removed'
        if witness is not None:
            report['focus'] = witness.summary()
            report['activation_events'] = [{'bundle':row.get('bundle'), 't':row['t']}
                                           for row in witness.activations]
        report['operation_timeline'] = timeline
        report['seconds'] = time.monotonic()-began
        report['source_removed'] = not directory.exists()
        report['destination_left'] = destination.exists()
        report['background_verified'] = (report.get('background_initial') is True
            and report.get('focus',{}).get('activations')==[] and report['passed'])
        report['source_after'] = hashes()
        report['source_unchanged'] = report['source_before']==report['source_after']
        report['passed'] = report['passed'] and report['source_unchanged']
    return report
