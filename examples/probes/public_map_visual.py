"""One screenshot-planned zoom on the public OSM app in a private headless browser."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
URL='https://www.openstreetmap.org/#map=15/37.5665/126.9780'
CAPTURE_CODES={'stale_observation','stale_document','page_changed_during_capture'}
VISUAL_CODES=CAPTURE_CODES|{'invalid_visual_response','invalid_visual_proposal'}
READ_SECONDS=10


def map_state(url):
    """(zoom, lat, lon) from the owned page URL; anything else is refused."""
    parsed=urlsplit(url)
    if (parsed.scheme!='https' or parsed.netloc!='www.openstreetmap.org' or parsed.path!='/'
            or parsed.query):
        raise ValueError('unexpected_map_origin')
    if not parsed.fragment.startswith('map='):raise ValueError('map_state_unavailable')
    parts=parsed.fragment[len('map='):].split('/')
    if len(parts)!=3 or not parts[0].isascii() or not parts[0].isdecimal():
        raise ValueError('map_state_unavailable')
    try:lat,lon=float(parts[1]),float(parts[2])
    except ValueError:raise ValueError('map_state_unavailable') from None
    zoom=int(parts[0])
    if not (0<=zoom<=20 and math.isfinite(lat) and math.isfinite(lon)
            and -90<=lat<=90 and -180<=lon<=180):
        raise ValueError('map_state_unavailable')
    return zoom,lat,lon


def authorize_click(page,control,initial,report,proposal):
    """True only for one click inside the one visible Zoom In control."""
    if report['host_click_attempts'] or map_state(page.url)!=initial:return False
    if control.count()!=1 or not control.is_visible():return False
    box=control.bounding_box()
    return (box is not None
            and box['x']<=proposal['x']<box['x']+box['width']
            and box['y']<=proposal['y']<box['y']+box['height']
            and control.evaluate('(el,p)=>el.contains(document.elementFromPoint(p.x,p.y))',
                                 {'x':proposal['x'],'y':proposal['y']}) is True)


def capture_with_retry(driver,page,report,capture_browser,VisualError):
    """Retry only a read that saw the page change; never after model or input."""
    for attempt in range(3):
        observation=driver.observe('page')
        if observation.get('type')!='observation':raise RuntimeError('observation_unavailable')
        try:
            capture=capture_browser(driver,observation['obs_id'],'page')
        except VisualError as error:
            code=str(error)
            report['capture_attempts'].append({'attempt':attempt+1,'accepted':False,
                'error_code':code if code in CAPTURE_CODES else 'other'})
            if code!='page_changed_during_capture' or attempt==2:raise
            page.wait_for_timeout(200)
            continue
        report['capture_attempts'].append({'attempt':attempt+1,'accepted':True})
        return capture
    raise AssertionError('unreachable capture loop')


def read_zoom(page,initial,report,*,clock=time.monotonic,seconds=READ_SECONDS):
    """Poll the URL until zoom +1; the last state read is kept either way."""
    deadline=clock()+seconds
    while True:
        final=map_state(page.url);report['final_state']=final
        if final[0]==initial[0]+1:return final
        if clock()>=deadline:raise TimeoutError('map_zoom_unverified')
        page.wait_for_timeout(100)


def zoomed_in_place(initial,final):
    return (final[0]==initial[0]+1
            and abs(final[1]-initial[1])<=.00001 and abs(final[2]-initial[2])<=.00001)


def browser_environment(page):
    """Conditions a later cohort must match; no page content."""
    viewport=page.viewport_size
    return {'locale':page.evaluate('navigator.language'),
            'user_agent':page.evaluate('navigator.userAgent'),
            'viewport':dict(viewport) if viewport else None}


def run(provider, output, *, clock=time.monotonic, perturb_background=False):
    if provider not in ('codex','claude'):raise ValueError('unsupported_provider')
    if type(perturb_background) is not bool:raise ValueError('invalid perturbation flag')
    from tacto.browser import BrowserDriver
    from tacto.visual import VisualError,capture_browser,plan_visual
    from tacto.visual_actions import VisualClickExecutor
    from tacto.model_budget import model_deadline
    from tacto.provider_observation import capture_provider_calls,summarize_provider_calls
    output=Path(output)
    descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report={'passed':False,'scope':'public app, headless browser, one host-authorized pixel zoom',
            'provider':provider,'comparison_eligible':False,'native_ui_test':False,
            'provider_side_effects_verified':False,'host_click_attempts':0,
            'oracle':'owned browser URL zoom +1 with unchanged center; not persistent output',
            'started_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'stage':'initialization','capture_attempts':[],
            'controlled_background_perturbation':perturb_background}
    paths=sorted((ROOT/'tacto').glob('*.py'))+[Path(__file__).resolve()]
    def manifest():return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before=None;driver=None;calls=[];began=clock()
    try:
        before=manifest();driver=BrowserDriver(headless=True);page=driver._page
        report['stage']='navigation'
        page.set_default_timeout(10000)
        response=page.goto(URL,wait_until='networkidle',timeout=25000)
        report['http_status']=response.status if response else None
        report['environment']=browser_environment(page)
        control=page.locator('a[aria-label="Zoom In"]')
        if control.count()!=1 or not control.is_visible():raise RuntimeError('zoom_control_unavailable')
        initial=map_state(page.url)
        if initial[0]!=15:raise RuntimeError('initial_zoom_mismatch')
        report.update(initial_state=initial,browser_version=driver._browser.version)
        # Pin the actual control before the model sees the full-page image.
        # Clipped screenshots do not scroll or act on the element.
        pinned=control.element_handle()
        def target_state():
            if (pinned is None or not control.evaluate('(el, original)=>el===original', pinned)
                    or not pinned.evaluate('(el)=>el.isConnected')):
                return None
            box=pinned.bounding_box()
            if box is None:return None
            return {'box':box, 'pixels_sha256':hashlib.sha256(page.screenshot(clip=box)).hexdigest()}
        target_before=target_state()
        if target_before is None:raise RuntimeError('target_witness_unavailable')
        report['target_before']=target_before
        report['stage']='capture'
        capture=capture_with_retry(driver,page,report,capture_browser,VisualError)
        if target_state()!=target_before:raise RuntimeError('target_changed_during_capture')
        capture.save(output.with_suffix('.before.png'))
        report['capture']=capture.to_dict()
        report['stage']='planning'
        with capture_provider_calls() as calls, model_deadline(time.monotonic()+60):
            proposal=plan_visual(capture,'Click the visible plus (+) Zoom In map control exactly once. '
                'Do not click search, location, login, sharing, editing or any other control.',
                provider=provider,timeout=45)
        report['proposal']=proposal
        if perturb_background:
            # Calibration case: only the map tiles change, never the control.
            tile=page.locator('.leaflet-tile-pane img').evaluate_all("""(nodes)=>{
                const el=nodes.find(n=>{const r=n.getBoundingClientRect();
                    return r.left>=350 && r.right<1100 && r.top>=100 && r.bottom<650});
                if(!el)return null;
                const r=el.getBoundingClientRect();el.style.opacity='0.5';
                return {x:r.x,y:r.y,width:r.width,height:r.height};
            }""")
            if tile is None:raise RuntimeError('calibration_tile_unavailable')
            report['background_perturbation']={'tile_opacity':0.5,'box':tile}
        report['stage']='dispatch'
        def revalidate_target(proposal,original,fresh):
            current=target_state();report['target_at_revalidation']=current
            return (current is not None and current==target_before
                    and authorize_click(page,control,initial,report,proposal))
        event=VisualClickExecutor(driver,'page').click(capture,proposal,
            lambda proposal,current:authorize_click(page,control,initial,report,proposal),
            revalidate_target=revalidate_target)
        report['click_result']=event
        report['host_click_attempts']=int(event.get('effect') in ('unknown','dispatched'))
        if event.get('effect')!='dispatched':raise RuntimeError('pixel_click_not_dispatched')
        report['stage']='verification'
        # Observe the owned browser URL without evaluating a page expression.
        final=read_zoom(page,initial,report,clock=clock)
        report['passed']=zoomed_in_place(initial,final)
    except Exception as error:
        report['error_class']=type(error).__name__
        if isinstance(error,VisualError):
            code=str(error)
            report['error_code']=code if code in VISUAL_CODES else 'other_visual_error'
    finally:
        report['provider_calls']=calls
        try:report['usage']=summarize_provider_calls(calls)
        except Exception as error:report['usage_error_class']=type(error).__name__
        report['elapsed_seconds']=clock()-began
        try:after=manifest()
        except Exception:after=None
        report.update(source_before=before,source_after=after,
                      source_subset_stable=before is not None and before==after)
        if not report['source_subset_stable']:report['passed']=False
        if driver is not None:
            try:driver.close()
            except Exception as error:
                report['cleanup_error_class']=type(error).__name__;report['passed']=False
        with os.fdopen(descriptor,'w') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=('codex','claude'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--perturb-background',action='store_true',help='Calibration: change one map tile away from the control after planning')
    args=parser.parse_args(argv);result=run(args.provider,args.output,perturb_background=args.perturb_background)
    print(json.dumps({k:result.get(k) for k in ('passed','provider','host_click_attempts',
        'http_status','initial_state','final_state','elapsed_seconds','error_class','source_subset_stable')}))

    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
