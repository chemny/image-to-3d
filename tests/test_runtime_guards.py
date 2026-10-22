import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from runtime_guards import evaluate, rollback_preview


class RuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.temporal = {'version':1,'kind':'temporal','contract':{'sequences':['load','orbit','reset'],'invariants':['receiver','contact','layer_clearance'],'tolerance':1e-6,'minimums':{'layer_clearance':.001}},'sequences':[]}
        for name in self.temporal['contract']['sequences']:
            self.temporal['sequences'].append({'id':name,'frames':[{'time':i,'camera':[i,2,3],'invariants':{'receiver':[0,0,0],'contact':[0,.001,0],'layer_clearance':[.002]}} for i in range(3)]})
        identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
        snap={'vertices':[[0,0,0],[1,1,1],[.5,.5,.5]],'accessor_bounds':[0,0,0,1,1,1],'normalization_bounds':[0,0,0,1,1,1],'root_matrix':identity,'camera':[0,2,4],'anchors':{'foot':0}}
        self.scale={'version':1,'kind':'scale','contract':{'tolerance':1e-6,'max_bounds_delta':.1,'anchors':['foot']},'baseline':snap,'candidate':copy.deepcopy(snap)}
        self.rollback={'version':1,'kind':'rollback','current':{'a':'new','b':'latest-b'},'before':{'a':'old','b':'old-b'},'adopted':{'a':'new','b':'old-b'},'scope':['a']}
        self.bundle={'version':1,'kind':'bundle','expected':{},'required':['model.bin','shared.js','dynamic.js'],'packaged':['model.bin','shared.js','dynamic.js']}
        for name in self.bundle['required']:
            data=name.encode();(self.root/name).write_bytes(data);self.bundle['expected'][name]=hashlib.sha256(data).hexdigest()

    def ok(self, value):
        result=evaluate(value,self.root);self.assertTrue(result['passed'],result)
        return result

    def bad(self,value):
        result=evaluate(value,self.root);self.assertFalse(result['passed'],result)
        return result

    def test_temporal_camera_motion_does_not_move_ground(self):self.ok(self.temporal)
    def test_receiver_jump_rejected(self):
        self.temporal['sequences'][1]['frames'][1]['invariants']['receiver'][1]=.02;self.bad(self.temporal)
    def test_contact_drift_rejected(self):
        self.temporal['sequences'][0]['frames'][2]['invariants']['contact'][1]=.1;self.bad(self.temporal)
    def test_coplanar_layers_fail_even_without_transform_motion(self):
        for seq in self.temporal['sequences']:
            for frame in seq['frames']:frame['invariants']['layer_clearance']=[0]
        self.bad(self.temporal)
    def test_sequence_state_change_allowed_between_groups(self):
        for frame in self.temporal['sequences'][2]['frames']:frame['invariants']['receiver']=[0,-1,0]
        self.ok(self.temporal)
    def test_missing_lifecycle_sequence_rejected(self):
        self.temporal['sequences'].pop();self.bad(self.temporal)
    def test_one_frame_cannot_prove_stability(self):
        self.temporal['sequences'][0]['frames']=self.temporal['sequences'][0]['frames'][:1];self.bad(self.temporal)
    def test_duplicate_sequence_rejected(self):
        self.temporal['sequences'][0]['id']='orbit';self.bad(self.temporal)
    def test_repeated_timestamp_rejected(self):
        self.temporal['sequences'][0]['frames'][1]['time']=0;self.bad(self.temporal)
    def test_nan_measurement_rejected(self):
        self.temporal['sequences'][0]['frames'][0]['invariants']['receiver'][0]=float('nan');self.bad(self.temporal)
    def test_missing_invariant_rejected(self):
        del self.temporal['sequences'][1]['frames'][1]['invariants']['receiver'];self.bad(self.temporal)
    def test_local_surface_edit_preserves_world_anchors(self):
        self.scale['candidate']['vertices'][2]=[.55,.55,.55];self.ok(self.scale)
    def test_stale_accessor_bounds_rejected(self):
        self.scale['candidate']['vertices'][1]=[1.05,1,1];self.bad(self.scale)
    def test_authorized_new_extent_with_fixed_normalization(self):
        self.scale['candidate']['vertices'][1]=[1.05,1,1];self.scale['candidate']['accessor_bounds'][3]=1.05;self.ok(self.scale)
    def test_outlier_accessory_rejected(self):
        self.scale['candidate']['vertices'].append([50,0,0]);self.scale['candidate']['accessor_bounds'][3]=50;self.bad(self.scale)
    def test_double_normalization_rejected(self):
        self.scale['candidate']['root_matrix'][0]=.5;self.bad(self.scale)
    def test_recenter_rejected(self):
        self.scale['candidate']['root_matrix'][12]=1;self.bad(self.scale)
    def test_reframing_rejected(self):
        self.scale['candidate']['camera'][2]=5;self.bad(self.scale)
    def test_normalization_bounds_change_rejected(self):
        self.scale['candidate']['normalization_bounds'][3]=2;self.bad(self.scale)
    def test_world_anchor_uses_actual_matrix_and_vertex(self):
        self.scale['candidate']['vertices'][0]=[.01,0,0];self.scale['candidate']['accessor_bounds'][0]=.01;self.bad(self.scale)
    def test_invalid_anchor_index_rejected(self):
        self.scale['candidate']['anchors']['foot']=-1;self.bad(self.scale)
    def test_negative_tolerance_rejected(self):
        self.scale['contract']['tolerance']=-1;self.bad(self.scale)
    def test_bundle_complete(self):self.ok(self.bundle)
    def test_unchanged_model_changed_shared_runtime_invalidates_evidence(self):
        (self.root/'shared.js').write_text('new shader');self.bad(self.bundle)
    def test_untracked_import_excluded_from_package_rejected(self):
        self.bundle['packaged'].remove('shared.js');self.bad(self.bundle)
    def test_missing_dynamic_dependency_rejected(self):
        (self.root/'dynamic.js').unlink();self.bad(self.bundle)
    def test_missing_frozen_resource_identity_rejected(self):
        del self.bundle['expected']['dynamic.js'];self.bad(self.bundle)
    def test_path_escape_rejected(self):
        self.bundle['required'].append('../escape');self.bad(self.bundle)
    def test_symlink_resource_rejected(self):
        (self.root/'dynamic.js').unlink();(self.root/'dynamic.js').symlink_to(self.root/'model.bin');self.bad(self.bundle)
    def test_scoped_rollback_keeps_other_cases_newer_changes(self):
        before=copy.deepcopy(self.rollback);result=self.ok(self.rollback);self.assertEqual(result['registry'],{'a':'old','b':'latest-b'});self.assertEqual(before,self.rollback)
    def test_target_concurrent_change_rejects_without_mutation(self):
        self.rollback['current']['a']='user-edited';before=copy.deepcopy(self.rollback);self.bad(self.rollback);self.assertEqual(before,self.rollback)
    def test_newly_adopted_case_can_be_removed_without_touching_others(self):
        del self.rollback['before']['a'];self.assertEqual(self.ok(self.rollback)['registry'],{'b':'latest-b'})
    def test_missing_current_target_is_conflict(self):
        del self.rollback['current']['a'];self.bad(self.rollback)
    def test_unknown_target_rejected(self):
        self.rollback['scope']=['unknown'];self.bad(self.rollback)
    def test_malformed_records_fail_closed(self):
        for value in [None,[],{},dict(version=2),{'version':1,'kind':'unknown'}]:self.bad(value)
    def test_cli_read_only_and_exit_status(self):
        f=self.root/'record.json';f.write_text(json.dumps(self.rollback));before=f.read_bytes()
        script=Path(__file__).resolve().parents[1]/'scripts/runtime_guards.py'
        result=subprocess.run([sys.executable,str(script),str(f)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['registry']['b'],'latest-b');self.assertEqual(f.read_bytes(),before)
        self.rollback['current']['a']='conflict';f.write_text(json.dumps(self.rollback));result=subprocess.run([sys.executable,str(script),str(f)],capture_output=True,text=True);self.assertEqual(result.returncode,1)


if __name__=='__main__':unittest.main()
