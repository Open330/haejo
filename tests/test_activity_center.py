"""Read real JSONL fixtures and exercise native controls, never user windows."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from tacto.preferences import load_preferences
from tacto.access_log import AccessLog

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform=='darwin','AppKit required')
class ActivityCenterTests(unittest.TestCase):
    def test_history_groups_calls_by_task(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); product=folder/'Tacto'; logs=product/'Logs'; logs.mkdir(parents=True)
            tid='t-'+'a'*24; ended='t-'+'b'*24; missing='t-'+'c'*24
            for task_id, meta in ((tid, dict(state='open',result=None,goal='수강 진행',detail='사용자 요청: 법정교육 3과목 수강')), (ended, dict(state='closed',result='failed',goal='끝난 작업'))):
                d=product/'Tasks'/task_id; d.mkdir(parents=True)
                (d/'task.json').write_text(json.dumps(dict(schema=1,id=task_id,created_at='x',closed_at=None,**meta)))
            (product/'Tasks'/tid/'events.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in (
                dict(schema=1,event='invocation_start',invocation='e'*32,why='진도 화면 확인',at='2026-11-09T02:12:00.000000+00:00'),
                dict(schema=1,event='note',text='팝업을 닫기로 결정',at='2026-11-09T02:13:00.000000+00:00'),
                dict(schema=1,event='note',text='오래된 판단',at='2026-11-09T01:00:00.000000+00:00'))))
            def write(index, minute, task_id=None, exit_code=0, command='session'):
                start=dict(schema=1,event='command_start',command=command,at=f'2026-11-09T02:{minute:02d}:00.000000+00:00',elapsed_ms=0)
                if task_id: start['task_id']=task_id
                if index==2: start['invocation_id']='e'*32
                rows=[start,dict(schema=1,event='access_start',operation='observe',target='com.apple.Safari',elapsed_ms=5),
                      dict(schema=1,event='access_end',operation='observe',target='com.apple.Safari',type='observation',elapsed_ms=9),
                      dict(schema=1,event='command_end',exit_code=exit_code,elapsed_ms=10)]
                (logs/(f'tacto-20261109T02{minute:02d}00000000Z-'+format(index,'x')*32+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
            write(1,10,tid);write(2,12,tid,2);write(3,14,tid);write(4,11);write(5,5,ended);write(6,6,missing);write(7,7,'t-NOTVALID')
            source=(ROOT/'setup/ActivityCenter.swift').read_text().replace('private ', '')
            (folder/'ActivityCenter.swift').write_text(source)
            (folder/'main.swift').write_text(r'''
import AppKit
let app=NSApplication.shared; app.setActivationPolicy(.prohibited)
let store=ActivityStore(root:URL(fileURLWithPath:CommandLine.arguments[1]))
let groups=try! store.groups()
assert(groups.count==5, "\(groups.count)")
let open=groups[0]
assert(open.isTask && open.records.count==3 && open.title=="수강 진행" && open.status=="진행 중")
assert(!open.failed && !open.complete && open.records.first!.started > open.records.last!.started)
let closed=groups.first{$0.taskID?.hasPrefix("t-bbb") == true}!
assert(closed.failed && closed.complete && closed.status=="실패")
let orphan=groups.first{$0.taskID?.hasPrefix("t-ccc") == true}!
assert(orphan.task == nil && orphan.title.hasPrefix("작업 t-ccc"))
assert(groups.filter{!$0.isTask}.count==2)
let center=ActivityCenter(store:store,refreshAutomatically:false)
try! center.snapshot(to:URL(fileURLWithPath:CommandLine.arguments[1]).appendingPathComponent("snapshot"))
assert(center.filtered.count==5 && center.filtered[0].key==open.key)
assert(center.summary.stringValue.hasPrefix("최근 7개 실행 · 작업 3개"), center.summary.stringValue)
let texts=center.detail.arrangedSubviews.compactMap{($0 as? NSTextField)?.stringValue}
assert(texts.contains("수강 진행") && texts.contains{$0.hasPrefix("1. 연속 작업")} && texts.contains{$0.hasPrefix("3. 연속 작업")}, "\(texts)")
assert(texts.contains("요청 설명") && texts.contains("사용자 요청: 법정교육 3과목 수강") && texts.contains("이유 · 진도 화면 확인"), "\(texts)")
let notes=center.detail.arrangedSubviews.compactMap{($0 as? NSStackView)?.arrangedSubviews.last as? NSStackView}.compactMap{($0.arrangedSubviews.first as? NSTextField)?.stringValue}.filter{$0.hasPrefix("판단 · ")}
assert(notes==["판단 · 팝업을 닫기로 결정","판단 · 오래된 판단"], "\(notes)")
let flat=center.detail.arrangedSubviews.map{v -> String in (v as? NSTextField)?.stringValue ?? ((v as? NSStackView)?.arrangedSubviews.last as? NSStackView).flatMap{($0.arrangedSubviews.first as? NSTextField)?.stringValue} ?? ""}
let i3=flat.firstIndex{$0.hasPrefix("3.")}!, iNote=flat.firstIndex(of:"판단 · 팝업을 닫기로 결정")!, i2=flat.firstIndex{$0.hasPrefix("2.")}!
assert(i3 < iNote && iNote < i2, "note between call 3 and call 2: \(flat)")
let heads=texts.filter{$0.first?.isNumber == true}
assert(heads.first!.hasPrefix("3.") && heads.last!.hasPrefix("1."), "newest first: \(heads)")
var many=open; many.records=(0..<45).map{_ in open.records[0]}
center.showDetail(many)
let manyTexts=center.detail.arrangedSubviews.compactMap{($0 as? NSTextField)?.stringValue}
assert(manyTexts.filter{$0.first?.isNumber == true}.count==ActivityCenter.taskCallLimit && manyTexts.contains{$0.hasPrefix("최근 30회")}, "\(manyTexts.prefix(6))")
center.showDetail(open)
center.search.stringValue="수강";center.applyFilter();assert(center.filtered.count==1)
center.search.stringValue="";center.filter.selectedSegment=1;center.applyFilter();assert(center.filtered.count==1 && center.filtered[0].key==closed.key)
print("task-groups-pass")
''')
            binary=folder/'check'
            built=subprocess.run(['swiftc','ActivityCenter.swift','main.swift','-o',str(binary)],cwd=folder,capture_output=True,text=True,timeout=120)
            self.assertEqual(0,built.returncode,built.stderr)
            result=subprocess.run([str(binary),str(product)],capture_output=True,text=True,timeout=30)
            self.assertEqual(0,result.returncode,result.stderr)
            self.assertIn('task-groups-pass',result.stdout)

    def test_native_reader_filters_settings_and_private_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); product=folder/'Tacto'; logs=product/'Logs'; logs.mkdir(parents=True)
            def write(index, command, end=None, target='com.apple.TextEdit', partial=False):
                rows=[dict(schema=1,event='command_start',command=command,at='2026-10-20T00:00:00.000000+00:00',elapsed_ms=0),
                      dict(schema=1,event='access_start',operation='observe',target=target,elapsed_ms=10)]
                if end is not None:
                    rows += [dict(schema=1,event='access_end',operation='observe',target=target,type='observation',elapsed_ms=20),
                             dict(schema=1,event='command_end',exit_code=end,elapsed_ms=30)]
                text=''.join(json.dumps(r)+'\n' for r in rows)+('{"partial":' if partial else '')
                (logs/('tacto-20261020T000000000000Z-'+str(index)*32+'.jsonl')).write_text(text)
            write(1,'first-run',0);write(2,'run',1);write(3,'observe',partial=True)
            sentinel=logs/'notes.txt';sentinel.write_text('KEEP')
            (logs/('tacto-20261020T000000000000Z-'+'4'*32+'.jsonl')).symlink_to(sentinel)
            source=(ROOT/'setup/ActivityCenter.swift').read_text().replace('private ', '')
            (folder/'ActivityCenter.swift').write_text(source)
            (folder/'main.swift').write_text(r'''
import AppKit
let app=NSApplication.shared; app.setActivationPolicy(.prohibited)
let root=URL(fileURLWithPath:CommandLine.arguments[1])
let store=ActivityStore(root:root)
let records=try! store.records()
assert(records.count==3)
assert(records.filter{$0.failed}.count==1)
assert(records.filter{!$0.complete}.count==1)
assert(records.allSatisfy{$0.steps.count==1})
let partial=records.first{!$0.complete}!
assert(!partial.damaged && !partial.steps[0].ended)
let boolEnd=Data("{\"schema\":1,\"event\":\"command_start\",\"command\":\"observe\"}\n{\"schema\":1,\"event\":\"command_end\",\"exit_code\":false}\n".utf8)
assert(!store.parse(boolEnd,url:root,modified:Date()).complete)
func retried(_ exit:Int) -> ActivityRecord {
  let rows = "{\"schema\":1,\"event\":\"command_start\",\"command\":\"activate\"}\n"
    + "{\"schema\":1,\"event\":\"access_start\",\"operation\":\"observe\"}\n"
    + "{\"schema\":1,\"event\":\"access_end\",\"operation\":\"observe\",\"type\":\"error\",\"error\":\"no_window_content\"}\n"
    + "{\"schema\":1,\"event\":\"command_end\",\"exit_code\":\(exit)}\n"
  return store.parse(Data(rows.utf8),url:root,modified:Date())
}
assert(retried(0).steps[0].outcome=="다시 확인")
assert(retried(1).steps[0].outcome=="실패")
let future=Data("{\"schema\":2,\"event\":\"command_end\",\"exit_code\":0}\n".utf8)
assert(store.parse(future,url:root,modified:Date()).damaged)
assert(TactoPreferences(["retention_days":7.0]).retentionDays==30)
let center=ActivityCenter(store:store,refreshAutomatically:false)
try! center.snapshot(to:root.appendingPathComponent("snapshot"))
assert(center.split.subviews[0].frame.width>=240 && center.split.subviews[0].frame.width<=380)
assert(center.split.subviews[1].frame.width>=300)
let initialListWidth=center.split.subviews[0].frame.width
try! center.snapshot(to:root.appendingPathComponent("compact"),size:NSSize(width:900,height:600))
assert(abs(center.split.subviews[0].frame.width-initialListWidth)<2)
assert(center.split.subviews[1].frame.width>=300)
assert(center.historyButton.bounds.width==176)
assert(center.historyButton.title=="실행 기록" && center.historyButton.image != nil)
assert(center.settingsButton.title=="설정" && center.settingsButton.image != nil)
center.filter.selectedSegment=1;center.applyFilter();assert(center.filtered.count==1)
center.search.stringValue="no-match";center.applyFilter();assert(center.filtered.isEmpty)
center.window!.contentView!.layoutSubtreeIfNeeded()
assert(center.detail.arrangedSubviews.allSatisfy{abs($0.alignmentRect(forFrame:$0.frame).width-(center.detail.frame.width-48))<2})
center.search.stringValue="";center.filter.selectedSegment=2;center.applyFilter();assert(center.filtered.count==1)
center.navigate(center.settingsButton)
assert(center.warmToggle.state == .off && !center.helperIdle.isEnabled)
center.warmToggle.performClick(nil)
assert(center.helperIdle.isEnabled)
center.helperIdle.selectItem(at:9);center.saveSettings()
assert(try! store.preferences().keepHelperWarm)
assert(try! store.preferences().helperIdleMinutes==10)
assert(TactoPreferences(["helper_idle_minutes":1.5]).helperIdleMinutes==2)
assert(TactoPreferences(["keep_helper_warm":1]).keepHelperWarm==false)
try! center.snapshot(to:root.appendingPathComponent("settings"),settingsPage:true,size:NSSize(width:900,height:600))
center.logToggle.performClick(nil)
center.bannerToggle.performClick(nil)
center.retention.selectItem(at:0);center.saveSettings()
let settings=try! store.preferences()
assert(!settings.loggingEnabled && !settings.showControlBanner && settings.retentionDays==7)
assert(TactoPreferences(["show_control_banner":0]).showControlBanner)
assert(!TactoPreferences(["show_control_banner":false]).showControlBanner)
let permissions=try! FileManager.default.attributesOfItem(atPath:store.preferencesURL.path)
assert((permissions[.posixPermissions] as! NSNumber).intValue==0o600)
try! store.deleteRecords()
assert(try! store.records().isEmpty)
assert(FileManager.default.fileExists(atPath:store.logs.appendingPathComponent("notes.txt").path))
assert(FileManager.default.fileExists(atPath:store.logs.appendingPathComponent("tacto-20261020T000000000000Z-44444444444444444444444444444444.jsonl").path))
print("activity-and-settings-pass")
''')
            binary=folder/'check'
            built=subprocess.run(['swiftc','ActivityCenter.swift','main.swift','-o',str(binary)],cwd=folder,capture_output=True,text=True,timeout=90)
            self.assertEqual(0,built.returncode,built.stderr)
            result=subprocess.run([str(binary),str(product)],capture_output=True,text=True,timeout=30)
            self.assertEqual(0,result.returncode,result.stderr)
            self.assertIn('activity-and-settings-pass',result.stdout)
            prefs=load_preferences(product)
            self.assertFalse(prefs['show_control_banner'])
            self.assertTrue(prefs['keep_helper_warm'])
            self.assertEqual(10,prefs['helper_idle_minutes'])
            self.assertEqual((False,7),(prefs['logging_enabled'],prefs['retention_days']))
            self.assertNotIn('present_first_result',prefs)
            log=AccessLog('observe',root=logs);log.finish(0);log.close()
            self.assertIsNone(log.path)
            self.assertTrue((product/'snapshot/app.png').is_file())
