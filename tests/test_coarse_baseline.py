import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import coarse_initialization as ci
import coarse_baseline as cb
from test_coarse_initialization import fixture
import scene_build


class CoarseBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.initial, self.contract = fixture(self.root)
        self.fit = ci.fit(self.initial, self.contract, self.root, iterations=40)
        self.candidate = self.fit['spec']; self.report = self.fit['report']

    def verify(self, candidate=None, contract=None, report=None, resource_root=None):
        return cb.verify(candidate or self.candidate, contract or self.contract, report or self.report,
                         resource_root if resource_root is not None else self.root)

    def test_bounded_numeric_pass_without_optimizer_or_visual_adoption(self):
        with patch.object(ci, 'fit', side_effect=AssertionError('optimizer called')):
            result = self.verify()
        self.assertTrue(result['passed'], result['errors'])
        self.assertFalse(result['visual_fidelity_accepted']); self.assertFalse(result['production_accepted'])
        self.assertFalse(result['optimization_performed']); self.assertFalse(result['heldout_used_for_optimization'])
        self.assertEqual(result['data_jacobian']['rank'], 2)
        self.assertEqual(result['full_calibrated_geometry_sha256'], ci.full_geometry_identity(scene_build.build(self.candidate)))

    def test_forged_pass_does_not_hide_wrong_heldout(self):
        contract = copy.deepcopy(self.contract)
        for sample in contract['curves'][0]['samples']:
            if sample['role'] == 'validation': sample['pixel'] = [25, 25]
        result = ci.fit(self.initial, contract, self.root, iterations=40)
        self.assertEqual(result['spec'], self.candidate)
        fake = result['report']; fake['eligible_for_freeze'] = True; fake['errors'] = []
        for row in fake['validation']: row.update(error_px=0, passed=True)
        checked = self.verify(result['spec'], contract, fake)
        self.assertFalse(checked['passed']); self.assertTrue(any('validation' in e for e in checked['errors']))

    def test_stale_candidate_identity(self):
        candidate = copy.deepcopy(self.candidate); candidate['id'] = 'stale'
        self.assertFalse(self.verify(candidate=candidate)['passed'])

    def test_stale_full_untraced_geometry_even_updated_candidate_sha(self):
        candidate = copy.deepcopy(self.candidate)
        candidate['components'].append({'id':'untraced','material':'body','geometry':{'type':'box','size':[.2,.2,.2]}})
        report = copy.deepcopy(self.report); report['candidate_spec_sha256'] = ci.digest(candidate)
        r = self.verify(candidate=candidate, report=report)
        self.assertFalse(r['passed']); self.assertIn('full calibrated geometry',r['errors'][0])

    def test_report_curve_identity_changed(self):
        report = copy.deepcopy(self.report); report['actual_geometric_curves_sha256'] = '0'*64
        self.assertFalse(self.verify(report=report)['passed'])

    def test_camera_builder_actual_mismatch(self):
        candidate = copy.deepcopy(self.candidate); candidate['cameras']['view']['position'][0] += .05
        report = copy.deepcopy(self.report); report['candidate_spec_sha256'] = ci.digest(candidate)
        self.assertFalse(self.verify(candidate=candidate,report=report)['passed'])

    def test_camera_report_identity_changed(self):
        report = copy.deepcopy(self.report); report['camera_sha256'] = '0'*64
        self.assertFalse(self.verify(report=report)['passed'])

    def test_targets_cannot_change_under_same_report(self):
        contract = copy.deepcopy(self.contract); contract['curves'][0]['samples'][0]['pixel'][0] += 1
        self.assertFalse(self.verify(contract=contract)['passed'])

    def test_target_changed_and_contract_rehashed_still_remeasured(self):
        contract = copy.deepcopy(self.contract); contract['curves'][0]['samples'][0]['pixel'][0] += 1
        report = copy.deepcopy(self.report); report['contract_sha256'] = ci.digest(contract)
        self.assertFalse(self.verify(contract=contract,report=report)['passed'])

    def test_initial_contract_spec_crosslink_changed(self):
        report = copy.deepcopy(self.report); report['initial_spec_sha256'] = '0'*64
        self.assertFalse(self.verify(report=report)['passed'])

    def test_stale_image_bytes(self):
        (self.root/'reference.png').write_bytes(b'wrong')
        self.assertFalse(self.verify()['passed'])

    def test_source_files_actual_bytes_and_hashes_verified(self):
        author = self.root/'author.txt'; author.write_text('initial source')
        self.initial['source_files'] = [{'path':'author.txt','sha256':hashlib.sha256(author.read_bytes()).hexdigest()}]
        self.contract['spec_identity'] = ci.digest(self.initial)
        fit = ci.fit(self.initial,self.contract,self.root,iterations=40)
        self.assertTrue(self.verify(fit['spec'],self.contract,fit['report'])['passed'])
        author.write_text('new unrelated source')
        self.assertFalse(self.verify(fit['spec'],self.contract,fit['report'])['passed'])

    def test_source_report_identity_changed(self):
        report = copy.deepcopy(self.report); report['source_images']['source']['sha256']='0'*64
        self.assertFalse(self.verify(report=report)['passed'])

    def test_protected_before_or_after_hash_changed(self):
        for name in ('protected_geometry_hashes_before','protected_geometry_hashes_after'):
            report=copy.deepcopy(self.report);report[name]['protected']='0'*64
            with self.subTest(name=name):self.assertFalse(self.verify(report=report)['passed'])

    def test_changed_protected_geometry_even_report_full_sha_updated(self):
        candidate=copy.deepcopy(self.candidate);candidate['components'][1]['position'][0]-=.1
        report=copy.deepcopy(self.report);report['candidate_spec_sha256']=ci.digest(candidate)
        report['full_calibrated_geometry_sha256']=ci.full_geometry_identity(scene_build.build(candidate))
        r=self.verify(candidate=candidate,report=report);self.assertFalse(r['passed']);self.assertIn('protected',r['errors'][0])

    def test_forged_data_jacobian_and_metrics_rejected(self):
        for mutate in (lambda r:r['data_jacobian'].update(rank=1),
                       lambda r:r['data_jacobian'].update(condition=99),
                       lambda r:r.update(calibration_sse=10),
                       lambda r:r['calibration'][0].update(error_px=10)):
            report=copy.deepcopy(self.report);mutate(report)
            self.assertFalse(self.verify(report=report)['passed'])

    def test_rank_deficient_forged_pass_rejected(self):
        spec=copy.deepcopy(self.initial);contract=copy.deepcopy(self.contract)
        spec['parameters']['unused']={'min':-.5,'value':0,'max':.5}
        contract['camera_builders']['view']['target'][1]={'param':'unused','scale':0}
        contract['variable_ids'].append('unused')
        for seed in contract['seeds']:seed['unused']=0
        contract['spec_identity']=ci.digest(spec);fit=ci.fit(spec,contract,self.root,iterations=40)
        report=fit['report'];report['eligible_for_freeze']=True;report['errors']=[]
        r=self.verify(fit['spec'],contract,report);self.assertFalse(r['passed']);self.assertIn('unobservable',r['errors'][0])

    def test_boundary_rule_cannot_be_bypassed(self):
        spec=copy.deepcopy(self.initial);contract=copy.deepcopy(self.contract);spec['parameters']['width']['max']=.7
        contract['seeds']=[{'width':.45,'shift':-.1}];contract['spec_identity']=ci.digest(spec)
        fit=ci.fit(spec,contract,self.root,iterations=40);fit['report']['eligible_for_freeze']=True;fit['report']['errors']=[]
        self.assertFalse(self.verify(fit['spec'],contract,fit['report'])['passed'])

    def test_report_diagnostic_or_production_claim_rejected(self):
        for patcher in (lambda r:r.update(eligible_for_freeze=False),lambda r:r.update(production_accepted=True),lambda r:r.update(resources_verified=False)):
            report=copy.deepcopy(self.report);patcher(report);self.assertFalse(self.verify(report=report)['passed'])

    def test_missing_resource_root_rejected(self):
        self.assertFalse(cb.verify(self.candidate,self.contract,self.report,None)['passed'])

    def test_malformed_report_structures_fail_closed(self):
        for change in (lambda r:r.update(data_jacobian=[]),lambda r:r['calibration'].__setitem__(0,None),lambda r:r.update(version=True)):
            report=copy.deepcopy(self.report);change(report)
            self.assertFalse(self.verify(report=report)['passed'])

    def test_heldout_never_enters_jacobian(self):
        contract=copy.deepcopy(self.contract)
        for sample in contract['curves'][0]['samples']:
            if sample['role']=='validation':sample['pixel'][1]+=.01
        other=ci.fit(self.initial,contract,self.root,iterations=40)
        a=self.verify();b=self.verify(other['spec'],contract,other['report'])
        self.assertTrue(b['passed'],b['errors']);self.assertEqual(a['data_jacobian'],b['data_jacobian'])
        self.assertNotEqual(a['validation'],b['validation'])

    def files(self):
        inputs=[]
        for name,value in [('spec.json',self.candidate),('contract.json',self.contract),('report.json',self.report)]:
            p=self.root/name;p.write_text(json.dumps(value,indent=3)+'\n');inputs.append(p)
        return inputs

    def test_freeze_archives_exact_bytes_and_refuses_existing_directory(self):
        inputs=self.files();before=[p.read_bytes()for p in inputs];out=self.root/'frozen'
        result=cb.freeze(*inputs,self.root,out);self.assertTrue(result['passed']);self.assertFalse(result['production_accepted'])
        for name,blob in zip(('spec.json','contract.json','fit-report.json'),before):self.assertEqual((out/name).read_bytes(),blob)
        with self.assertRaisesRegex(ValueError,'new directory'):cb.freeze(*inputs,self.root,out)
        self.assertEqual([p.read_bytes()for p in inputs],before)

    def test_failed_freeze_creates_no_output(self):
        inputs=self.files();report=json.loads(inputs[2].read_text());report['candidate_spec_sha256']='0'*64;inputs[2].write_text(json.dumps(report));out=self.root/'bad-freeze'
        with self.assertRaises(ValueError):cb.freeze(*inputs,self.root,out)
        self.assertFalse(out.exists())

    def test_cli_no_overwrite_and_explicit_nonproduction_receipt(self):
        inputs=self.files();out=self.root/'cli-frozen';script=Path(cb.__file__)
        cmd=[sys.executable,str(script),'--spec',str(inputs[0]),'--contract',str(inputs[1]),'--fit-report',str(inputs[2]),'--resource-root',str(self.root),'--out',str(out)]
        first=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stdout+first.stderr)
        files={p.name:p.read_bytes()for p in out.iterdir()}
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        self.assertEqual(files,{p.name:p.read_bytes()for p in out.iterdir()})
        receipt=json.loads((out/'verification-receipt.json').read_text());self.assertFalse(receipt['production_accepted']);self.assertFalse(receipt['visual_fidelity_accepted'])


if __name__=='__main__':unittest.main()
