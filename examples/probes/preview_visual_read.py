"""Read an owned score image in actual macOS Preview through signed Haejo capture.

Source-checkout evaluation: install web extras and Chromium for fixture rendering.
Each trial creates one PNG/window, asks one image question, then closes only that
window. No existing document is modified. This is visual-read functionality,
not a full autonomous agent, native image input, or Haejo/Sky performance test.
Use --host SSH_ALIAS for an already configured Mac; localhost is the default.
A known locked desktop is skipped before fixture creation or model invocation.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,secrets,shlex,subprocess,sys,time,shutil
from types import SimpleNamespace
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default='localhost');p.add_argument('--provider',choices=['codex','claude'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--launcher',default='/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo');a=p.parse_args()
base=a.output.resolve().parent;base.mkdir(parents=True,exist_ok=True);root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from haejo.browser import BrowserDriver
from haejo.visual import query_visual
from haejo.provider_observation import capture_provider_calls,summarize_provider_calls
CLI=a.launcher;TARGET='com.apple.Preview'
def remote(code,*args,timeout=45):
 command='python3 -c '+shlex.quote(code)+' '+shlex.join([str(x) for x in args])
 r=subprocess.run([sys.executable,'-c',code,*[str(x) for x in args]] if a.host=='localhost' else ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',a.host,command],capture_output=True,text=True,timeout=timeout)
 if r.returncode:raise RuntimeError('remote_command_failed')
 return json.loads(r.stdout)
def cli(*args):
 return remote("import subprocess,json,sys;r=subprocess.run(json.loads(sys.argv[1]),capture_output=True,text=True,timeout=35);print(json.dumps({'exit':r.returncode,'stdout':r.stdout}))",json.dumps([CLI,*args]))
def json_cli(*args):
 r=cli(*args)
 try:data=json.loads(r['stdout'])
 except ValueError:raise RuntimeError('cli_reply_not_json')
 return r['exit'],data
nonce=secrets.token_hex(8);score=str(1000+secrets.randbelow(9000))
while score in nonce:nonce=secrets.token_hex(8)
name='haejo-preview-vision-'+nonce+'.png';local=base/name;out=a.output.resolve()
fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
r={'passed':False,'scope':'owned PNG in actual Preview, signed native capture, read-only model interpretation','host':a.host,'provider':a.provider,'expected_score':score,'comparison_eligible':False,'model_tool_isolation_verified':False,'ui_inputs_for_task':0,'cleanup_attempts':0}
stage=None;window=None;calls=[];began=time.monotonic()
try:
 r['stage']='session_preflight'
 session=remote("import subprocess,json;r=subprocess.run(['/Applications/Haejo.app/Contents/Resources/runtime/.venv/bin/python','-I','-B','-c','from haejo.session import lock_state;import json;print(json.dumps(lock_state()))'],capture_output=True,text=True,timeout=10);print(r.stdout)")
 r['remote_session']=session
 if session.get('locked') is True:
  r['status']='skipped';r['skip_reason']='screen_locked';raise RuntimeError('screen_locked')
 browser=BrowserDriver(headless=True)
 try:
  browser._page.set_viewport_size({'width':800,'height':480})
  browser._page.set_content('<canvas width="800" height="480" style="display:block"></canvas><style>body{margin:0}</style>')
  browser._page.evaluate("""score=>{const c=document.querySelector('canvas').getContext('2d');c.fillStyle='#142536';c.fillRect(0,0,800,480);c.fillStyle='#fff';c.font='bold 40px sans-serif';c.fillText('Game score',70,130);c.font='bold 112px monospace';c.fillText(score,70,300)}""",score)
  local.write_bytes(browser._page.locator('canvas').screenshot(type='png'));local.chmod(0o600)
 finally:browser.close()
 r['source_image_sha256']=hashlib.sha256(local.read_bytes()).hexdigest();r['source_image_artifact']=local.name
 stage=remote("import tempfile,json;print(json.dumps(tempfile.mkdtemp(prefix='haejo-preview-vision-',dir='/private/tmp')))")
 assert re.fullmatch('/private/tmp/haejo-preview-vision-[A-Za-z0-9_]+',stage)
 shutil.copy2(local,Path(stage)/name) if a.host=='localhost' else subprocess.run(['scp','-q',str(local),a.host+':'+stage+'/'+name],check=True,timeout=20)
 r['remote_release']=remote("import plistlib,json,sys;from pathlib import Path;app=next(p for p in Path(sys.argv[1]).parents if p.suffix=='.app');r=plistlib.loads((app/'Contents/Info.plist').read_bytes());print(json.dumps({k:r.get(k) for k in ('HaejoReleaseTag','HaejoSourceCommit')}))",CLI)
 r['stage']='bootstrap'
 r['bootstrap']=remote("import subprocess,json,sys;r=subprocess.run(['open','-g','-a','Preview',sys.argv[1]],capture_output=True,timeout=15);print(json.dumps({'exit':r.returncode}))",stage+'/'+name)
 if r['bootstrap']['exit']!=0:raise RuntimeError('owned_file_open_failed')
 end=time.monotonic()+12
 while time.monotonic()<end:
  code,data=json_cli('windows',TARGET,'--helper')
  matches=[w for w in data.get('windows',[]) if nonce in w.get('title','')]
  if len(matches)==1:window=matches[0];break
  time.sleep(.25)
 if window is None:raise RuntimeError('owned_preview_window_unavailable')
 r['owned_window_id']=window['window_id']
 r['stage']='ax_observation'
 code,obs=json_cli('observe',TARGET,'--helper','--json','--window-id',str(window['window_id']))
 if code!=0 or obs.get('type')!='observation':raise RuntimeError('owned_observation_unavailable')
 r['score_absent_from_ax']=score not in obs.get('tree','');r['ax_tree_sha256']=hashlib.sha256(obs.get('tree','').encode()).hexdigest()
 if not r['score_absent_from_ax']:raise RuntimeError('score_already_accessible')
 r['stage']='native_capture'
 image_path=stage+'/captured.png';capture_result=cli('capture',TARGET,'--helper','--window',window['title'],'--output',image_path)
 if capture_result['exit']!=0:raise RuntimeError('owned_capture_failed')
 meta=json.loads(capture_result['stdout']);r['native_capture']=meta
 captured=out.with_suffix('.png')
 shutil.copy2(image_path,captured) if a.host=='localhost' else subprocess.run(['scp','-q',a.host+':'+image_path,str(captured)],check=True,timeout=20)
 captured.chmod(0o600)
 png=captured.read_bytes();r['captured_sha256']=hashlib.sha256(png).hexdigest()
 image=SimpleNamespace(capture_id='preview-read-'+nonce,sha256=r['captured_sha256'],png=png,viewport=meta['pixels'])
 r['stage']='visual_read'
 with capture_provider_calls() as calls:
  answer=query_visual(image,'What game score is visible in the image? Return only its decimal digits inside the answer string.',provider=a.provider,timeout=45)
 r['answer']=answer['answer'];r['score_read_correct']=answer['answer'].strip()==score
 r['passed']=r['score_read_correct']
except Exception as e:r.update(error_class=type(e).__name__,error_code=str(e) if re.fullmatch('[a-z_]+',str(e)) else 'probe_error')
finally:
 if window is not None:
  try:
   r['cleanup_attempts']=1
   flow={'name':'Close owned Preview image','target':TARGET,'steps':[{'action':'click','selector':{'role':'Button','subrole':'AXCloseButton','ancestor':window['title']},'safety':{'effects':['write_ephemeral'],'reversibility':'reversible','resource':{'scope':'entry'}},'unverified_ok':True}]}
   remote("from pathlib import Path;import json,sys;p=Path(sys.argv[1]);p.write_text(sys.argv[2]);p.chmod(0o600);print('{}')",stage+'/close.json',json.dumps(flow))
   close=cli('run',stage+'/close.json','--helper','--yes');r['close_cli_exit']=close['exit']
   code,data=json_cli('windows',TARGET,'--helper');r['owned_window_closed']=close['exit']==0 and code==0 and all(w.get('window_id')!=window['window_id'] for w in data.get('windows',[]))
  except Exception as e:r['cleanup_error_class']=type(e).__name__
 if stage:
  try:
   remote("from pathlib import Path;import sys,json;p=Path(sys.argv[1]);allowed={sys.argv[2],'captured.png','close.json'};assert all(x.name in allowed and x.is_file() and not x.is_symlink() for x in p.iterdir());[x.unlink() for x in p.iterdir()];p.rmdir();print('{}')",stage,name)
   r['owned_remote_files_removed']=True
  except Exception as e:r['file_cleanup_error_class']=type(e).__name__
 r['provider_source']={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [root/'haejo/visual.py',root/'haejo/codex_result.py',root/'haejo/claude_result.py']}
 r['provider_calls']=calls
 try:r['usage']=summarize_provider_calls(calls)
 except Exception as e:r['usage_error_class']=type(e).__name__
 r['seconds']=time.monotonic()-began
 r['passed']=r['passed'] and r.get('owned_window_closed') is True and r.get('owned_remote_files_removed') is True
 with os.fdopen(fd,'w') as stream:json.dump(r,stream,indent=2);stream.write('\n')
print(json.dumps({k:r.get(k) for k in ('passed','provider','stage','error_code','score_absent_from_ax','score_read_correct','close_cli_exit','owned_window_closed','owned_remote_files_removed','seconds')}))
raise SystemExit(2 if r.get('status')=='skipped' else not r['passed'])
