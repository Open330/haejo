"""Content-free interruption descriptions; never an automatic resume cursor."""
def interruption_summary(result, total_steps, *, step_offset=0, failed=False):
    if not failed and result is not None and result.ok is True:
        return {'failed_step':None,'remaining_steps':0,'next':None}
    failed_step = None
    if result is not None:
        for row in result.log:
            step = row.get('step')
            if row.get('status') in ('error','gated','unverified') and type(step) is int and 0 <= step+step_offset < total_steps:
                failed_step = step+step_offset
                break
    return {'failed_step':failed_step,'remaining_steps':None if failed_step is None else total_steps-failed_step,
            'next':{'action':'inspect_receiving_state','automatic_resume':False}}
