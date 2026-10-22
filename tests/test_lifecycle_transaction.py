import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import version_lifecycle as v
import lifecycle_transaction as t


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ['active', 'trial', 'rollback', 'accepted']:
            p = self.root / name;p.mkdir();(p/'model.bin').write_bytes((name+'-geometry').encode())
        (self.root/'trial/index.html').write_bytes(b'<html><script src="old.js"></script>old preview</html>')
        os.chmod(self.root/'trial/index.html', 0o640)
        (self.root/'trial/bundle.json').write_text('{"files":{"model.bin":"historic-hash"},"passed":true}')
        (self.root/'cases.js').write_text("load('active/model.bin')")
        (self.root/'decision.json').write_text('{"decision":"retain-baseline"}')
        self.evidence = {'path':'decision.json','sha256':v.digest((self.root/'decision.json').read_bytes())}
        self.data = {'version':1,'coverage_complete':True,'scan_files':['cases.js'],
                     'protected_paths':['active','rollback','accepted'],
                     'required_checks':['case_load','rollback','protected','retired_pages'],
                     'units':[{'id':'old','path':'trial/model.bin','status':'retired','dependencies':[],
                               'reason':'recorded rejected trial','retirement_evidence':self.evidence}],
                     'retirements':[{'path':'trial/index.html','kind':'html','unit_ids':['old'],'current_url':'/cases/'},
                                    {'path':'trial/bundle.json','kind':'json','unit_ids':['old']},
                                    {'path':'trial/retirement.json','kind':'json','unit_ids':['old']}]}
        self.ledger = self.root/'ledger.json';self.save()

    def save(self): self.ledger.write_text(json.dumps(self.data))

    def plan(self):
        self.save();return v.plan(self.root,self.ledger)

    def stage(self):
        p=self.plan();f=self.root/'plan.json';f.write_text(json.dumps(p))
        self.q=v.quarantine(self.root,f,p['plan_sha256']);return self.q

    def validation(self):
        (self.root/'browser.json').write_text('{"actual_fixture_check":true}')
        evidence={'path':'browser.json','sha256':v.digest((self.root/'browser.json').read_bytes())}
        self.report=self.root/'checks.json'
        self.report.write_text(json.dumps({'version':1,'phase':'post-quarantine','transaction_sha256':self.q['transaction_sha256'],
                                          'checks':[{'id':i,'passed':True,'evidence':evidence} for i in self.data['required_checks']]}))
        return self.report

    def deletion_plan(self):
        report=self.validation();p=v.purge_plan(self.root,self.q['transaction'],report)
        self.purge_file=self.root/'purge-plan.json';self.purge_file.write_text(json.dumps(p));return p

    def tx(self):return self.root/self.q['transaction']

    def test_preview_does_not_mutate_page_or_payload(self):
        old=(self.root/'trial/index.html').read_bytes();p=self.plan()
        self.assertEqual(len(p['retirements']),3)
        self.assertEqual((self.root/'trial/index.html').read_bytes(),old)
        self.assertTrue((self.root/'trial/model.bin').exists())
        self.assertFalse((self.root/'trial/retirement.json').exists())

    def test_stage_retires_html_without_executing_old_scripts_and_preserves_json(self):
        self.stage();text=(self.root/'trial/index.html').read_text()
        self.assertIn('data-retired="true"',text);self.assertNotIn('<script',text)
        self.assertIn('href="/cases/"',text)
        data=json.loads((self.root/'trial/bundle.json').read_text())
        self.assertEqual(data['files'],{'model.bin':'historic-hash'})
        self.assertTrue(data['passed']);self.assertEqual(data['_lifecycle']['status'],'retired')
        self.assertFalse((self.root/'trial/model.bin').exists())
        self.assertEqual(self.q['reclaimed_bytes'],0)

    def test_complete_restore_bytes_mode_mtime_and_remove_created_sidecar(self):
        original={p:v.snapshot(self.root/p) for p in ['trial/model.bin','trial/index.html','trial/bundle.json']}
        self.stage();result=v.restore(self.root,self.q['transaction'])
        self.assertEqual(result['restored'],1);self.assertEqual(result['restored_entries'],3)
        self.assertFalse((self.root/'trial/retirement.json').exists())
        for p,before in original.items():self.assertEqual(v.snapshot(self.root/p),before)
        self.assertEqual(v.restore(self.root,self.q['transaction'])['restored'],0)

    def test_partial_retirement_failure_restores_all_and_preserves_sources(self):
        (self.root/'trial/build.py').write_text('source recipe preserved')
        original=(self.root/'trial/index.html').read_bytes();replacement=t._replace
        def fail_second(path,*args,**kwargs):
            if path.name=='bundle.json':raise OSError('simulated interruption')
            return replacement(path,*args,**kwargs)
        with patch.object(t,'_replace',fail_second):
            with self.assertRaises(OSError):self.stage()
        tx=next((self.root/'.model-quarantine').iterdir())
        v.restore(self.root,str(tx.relative_to(self.root)))
        self.assertEqual((self.root/'trial/index.html').read_bytes(),original)
        self.assertEqual((self.root/'trial/build.py').read_text(),'source recipe preserved')
        self.assertTrue((self.root/'trial/model.bin').exists())

    def test_partial_restore_is_restartable(self):
        self.stage();replacement=t._replace
        def fail_html(path,*args,**kwargs):
            if path.name=='index.html':raise OSError('restore interruption')
            return replacement(path,*args,**kwargs)
        with patch.object(t,'_replace',fail_html):
            with self.assertRaises(OSError):v.restore(self.root,self.q['transaction'])
        self.assertTrue((self.root/'trial/model.bin').exists())
        v.restore(self.root,self.q['transaction'])
        self.assertFalse((self.root/'trial/retirement.json').exists())

    def test_restore_conflict_preflights_all_before_any_move(self):
        self.stage();(self.root/'trial/bundle.json').write_text('{"new_work":true}')
        with self.assertRaisesRegex(ValueError,'changed'):v.restore(self.root,self.q['transaction'])
        self.assertFalse((self.root/'trial/model.bin').exists())
        self.assertEqual(json.loads((self.root/'trial/bundle.json').read_text()),{'new_work':True})

    def test_restored_new_payload_destination_not_overwritten(self):
        self.stage();(self.root/'trial/model.bin').write_bytes(b'new model')
        with self.assertRaisesRegex(ValueError,'occupied'):v.restore(self.root,self.q['transaction'])
        self.assertEqual((self.root/'trial/model.bin').read_bytes(),b'new model')

    def test_stale_retirement_page_rejects_before_move(self):
        p=self.plan();f=self.root/'p.json';f.write_text(json.dumps(p))
        (self.root/'trial/index.html').write_text('new page')
        with self.assertRaisesRegex(ValueError,'stale'):v.quarantine(self.root,f,p['plan_sha256'])
        self.assertTrue((self.root/'trial/model.bin').exists())

    def test_retirement_of_protected_entry_rejected(self):
        for rel in ['active/index.html','rollback/index.html','accepted/manifest.json']:
            self.data['retirements'][0]['path']=rel
            with self.assertRaisesRegex(ValueError,'protected'):self.plan()

    def test_retirement_overlap_payload_and_unknown_id(self):
        self.data['retirements'][0]['path']='trial/model.bin'
        with self.assertRaises(ValueError):self.plan()
        self.data['retirements'][0]['path']='trial/index.html'
        self.data['retirements'][0]['unit_ids']=['missing']
        with self.assertRaises(ValueError):self.plan()

    def test_unsafe_html_urls_and_escaping(self):
        for url in ['javascript:alert(1)','//evil.test','/path\\evil','/x\ny']:
            self.data['retirements'][0]['current_url']=url
            with self.assertRaises(ValueError):self.plan()
        self.data['retirements'][0]['current_url']='/current?name="quoted"'
        self.stage();self.assertIn('&quot;quoted&quot;',(self.root/'trial/index.html').read_text())

    def test_historical_scanned_consumer_can_be_explicitly_retired(self):
        (self.root/'trial/index.html').write_text('<a href="trial/model.bin">old</a>')
        self.data['scan_files'].append('trial/index.html')
        self.assertTrue(self.plan()['units'][0]['eligible'])
        (self.root/'cases.js').write_text("load('trial/model.bin')")
        self.assertFalse(self.plan()['units'][0]['eligible'])

    def test_purge_preview_does_not_delete_payload(self):
        self.stage();p=self.deletion_plan()
        self.assertTrue(p['irreversible']);self.assertEqual(p['reclaimed_bytes'],0)
        self.assertTrue((self.tx()/'0').exists())

    def test_purge_keeps_backups_and_live_rollback_accepted(self):
        protected={p:v.snapshot(self.root/p) for p in ['active','rollback','accepted']}
        self.stage();p=self.deletion_plan();r=v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertFalse((self.tx()/'0').exists());self.assertTrue((self.tx()/'journal.json').exists())
        self.assertEqual(r['deleted_files_this_run'],1);self.assertFalse(r['full_restoration_available'])
        self.assertEqual(r['observed_available_delta_bytes'],r['available_bytes_after']-r['available_bytes_before'])
        for k,s in protected.items():self.assertEqual(v.snapshot(self.root/k),s)
        with self.assertRaisesRegex(ValueError,'permanent deletion'):v.restore(self.root,self.q['transaction'])

    def test_missing_failed_duplicate_and_wrong_transaction_checks_rejected(self):
        self.stage();self.validation();good=json.loads(self.report.read_text())
        variants=[]
        a=json.loads(json.dumps(good));a['checks'].pop();variants.append(a)
        a=json.loads(json.dumps(good));a['checks'][0]['passed']=False;variants.append(a)
        a=json.loads(json.dumps(good));a['checks'].append(a['checks'][0]);variants.append(a)
        a=json.loads(json.dumps(good));a['transaction_sha256']='0'*64;variants.append(a)
        a=json.loads(json.dumps(good));a['phase']='before';variants.append(a)
        for data in variants:
            self.report.write_text(json.dumps(data))
            with self.assertRaises(ValueError):v.purge_plan(self.root,self.q['transaction'],self.report)
        self.assertTrue((self.tx()/'0').exists())

    def test_stale_report_evidence_refused_at_execution(self):
        self.stage();p=self.deletion_plan();(self.root/'browser.json').write_text('changed evidence')
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertTrue((self.tx()/'0').exists())

    def test_new_runtime_reference_after_quarantine_blocks_purge(self):
        self.stage();p=self.deletion_plan();(self.root/'cases.js').write_text("load('trial/model.bin')")
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertTrue((self.tx()/'0').exists())

    def test_changed_protected_geometry_blocks_purge_but_allows_restore(self):
        self.stage();p=self.deletion_plan();(self.root/'active/model.bin').write_text('active new work')
        with self.assertRaisesRegex(ValueError,'protected'):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        v.restore(self.root,self.q['transaction'])
        self.assertEqual((self.root/'active/model.bin').read_text(),'active new work')

    def test_wrong_purge_approval_and_tampered_plan(self):
        self.stage();p=self.deletion_plan()
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,'wrong')
        p['logical_bytes']=0;self.purge_file.write_text(json.dumps(p))
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertTrue((self.tx()/'0').exists())

    def test_changed_retired_page_or_quarantined_file_prevents_purge(self):
        self.stage();p=self.deletion_plan();original=(self.root/'trial/index.html').read_bytes()
        (self.root/'trial/index.html').write_text('new owner page')
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        (self.root/'trial/index.html').write_bytes(original)
        (self.tx()/'0').write_text('changed mesh')
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])

    def test_directory_payload_purge_and_interruption_resume_exact_scope(self):
        self.data['retirements']=[];self.data['units'][0]['path']='trial'
        self.stage();p=self.deletion_plan();unlink=Path.unlink;calls=[]
        def fail_second(path,*args,**kwargs):
            if path.resolve().is_relative_to((self.tx()/'0').resolve()):
                calls.append(str(path))
                if len(calls)==2:raise OSError('interrupted purge')
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_second):
            with self.assertRaises(OSError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        with self.assertRaisesRegex(ValueError,'permanent deletion'):v.restore(self.root,self.q['transaction'])
        r=v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertGreater(r['previously_missing_files'],0)
        self.assertFalse((self.tx()/'0').exists());self.assertTrue((self.root/'active/model.bin').exists())
        self.assertEqual(v.purge(self.root,self.purge_file,p['purge_plan_sha256'])['deleted_files_this_run'],0)

    def test_purge_refuses_unexpected_new_files(self):
        self.data['retirements']=[];self.data['units'][0]['path']='trial';self.stage();p=self.deletion_plan()
        (self.tx()/'0/extra').write_text('new work')
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertTrue((self.tx()/'0/extra').exists())

    def test_links_journal_tampering_and_lock_fail_closed(self):
        self.stage();p=self.deletion_plan()
        with v.lock(self.root):
            with self.assertRaises(FileExistsError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        journal=self.tx()/'journal.json';j=json.loads(journal.read_text());j['entries'][0]['path']='active/model.bin';journal.write_text(json.dumps(j))
        with self.assertRaisesRegex(ValueError,'corrupt'):v.restore(self.root,self.q['transaction'])
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])

    def test_cli_quarantine_restore_and_purge_output_safety(self):
        p=self.plan();f=self.root/'plan.json';f.write_text(json.dumps(p))
        out=self.root/'q.json'
        command=[sys.executable,v.__file__,'quarantine','--root',str(self.root),'--plan',str(f),'--approve-sha256',p['plan_sha256'],'--out',str(out)]
        r=subprocess.run(command,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
        self.q=json.loads(out.read_text());self.validation()
        pp=self.root/'pp.json'
        r=subprocess.run([sys.executable,v.__file__,'purge-plan','--root',str(self.root),'--transaction',self.q['transaction'],'--report',str(self.report),'--out',str(pp)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        plan=json.loads(pp.read_text())
        forbidden=self.tx()/'result.json'
        r=subprocess.run([sys.executable,v.__file__,'purge','--root',str(self.root),'--plan',str(pp),'--approve-sha256',plan['purge_plan_sha256'],'--out',str(forbidden)],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertTrue((self.tx()/'0').exists())
        restored=self.root/'restore.json'
        r=subprocess.run([sys.executable,v.__file__,'restore','--root',str(self.root),'--transaction',self.q['transaction'],'--out',str(restored)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((self.root/'trial/model.bin').exists())

    def test_cli_refuses_result_over_restored_model_and_new_retirement_sidecar(self):
        p=self.plan();f=self.root/'plan.json';f.write_text(json.dumps(p))
        cmd=[sys.executable,v.__file__,'quarantine','--root',str(self.root),'--plan',str(f),
             '--approve-sha256',p['plan_sha256'],'--out',str(self.root/'trial/retirement.json')]
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        self.assertTrue((self.root/'trial/model.bin').exists())
        self.stage();r=subprocess.run([sys.executable,v.__file__,'restore','--root',str(self.root),
                                      '--transaction',self.q['transaction'],'--out',str(self.root/'trial/model.bin')],capture_output=True)
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.root/'trial/model.bin').exists())

    def test_legacy_transaction_restore_still_supported(self):
        token='a'*64;tx=self.root/'.model-quarantine'/token;tx.mkdir(parents=True)
        p=self.root/'trial/model.bin';snap=v.snapshot(p)
        (tx/'journal.json').write_text(json.dumps({'version':1,'root':str(self.root.resolve()),'plan_sha256':token,
                                                  'entries':[{'path':'trial/model.bin','slot':'0','snapshot':snap}]}))
        p.rename(tx/'0')
        self.assertEqual(v.restore(self.root,str(tx.relative_to(self.root)))['restored'],1)
        self.assertEqual(v.snapshot(p),snap)

    def test_nontext_url_large_entry_duplicate_paths_and_unverified_retirement(self):
        self.data['retirements'][0]['current_url']=None
        with self.assertRaises(ValueError):self.plan()
        self.data['retirements'][0]['current_url']='/cases/'
        (self.root/'trial/index.html').write_bytes(b'x'*(t.MAX_ENTRY_BYTES+1))
        with self.assertRaises(ValueError):self.plan()
        (self.root/'trial/index.html').write_text('old')
        self.data['retirements'].append(self.data['retirements'][0])
        with self.assertRaises(ValueError):self.plan()
        self.data['retirements'].pop()
        self.data['coverage_complete']=False
        p=self.plan();f=self.root/'unverified.json';f.write_text(json.dumps(p))
        with self.assertRaises(ValueError):v.quarantine(self.root,f,p['plan_sha256'])
        self.assertTrue((self.root/'trial/model.bin').exists())

    def test_purge_blocks_existing_original_path(self):
        self.stage();p=self.deletion_plan();(self.root/'trial/model.bin').write_text('new model')
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertTrue((self.tx()/'0').exists())

    def test_symlinked_retirement_and_quarantine_payload_refused(self):
        (self.root/'trial/index.html').unlink();(self.root/'trial/index.html').symlink_to(self.root/'cases.js')
        with self.assertRaises(ValueError):self.plan()
        (self.root/'trial/index.html').unlink();(self.root/'trial/index.html').write_text('old')
        self.stage();p=self.deletion_plan();(self.tx()/'0').unlink();(self.tx()/'0').symlink_to(self.root/'active/model.bin')
        with self.assertRaises(ValueError):v.purge(self.root,self.purge_file,p['purge_plan_sha256'])
        self.assertTrue((self.root/'active/model.bin').exists())

    def test_restored_transaction_has_no_purge_plan(self):
        self.stage();report=self.validation();v.restore(self.root,self.q['transaction'])
        with self.assertRaises(ValueError):v.purge_plan(self.root,self.q['transaction'],report)


if __name__=='__main__':unittest.main()
