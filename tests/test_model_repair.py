import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import model_repair as repair


def fixture():
    return {'id':'toy', 'coordinate_system':{'unit':'m','up':'y','forward':'z'},
            'references':[{'id':'original','path':'ref.png','sha256':''}],
            'materials':{'solid':{'color':'#cccccc'}},
            'parameters':{'width':{'value':1,'min':.5,'max':2}},
            'components':[{'id':'body','material':'solid','geometry':{'type':'box','size':[{'param':'width'},1,1]}},
                          {'id':'joint','kind':'assembly'},
                          {'id':'eye','parent':'joint','material':'solid','geometry':{'type':'box','size':[.2,.3,.4]}}],
            'cameras':{'front':{'position':[0,1,5],'target':[0,0,0]},'side':{'position':[5,1,0],'target':[0,0,0]}}}


def contract():
    return {'version':1,'targets':[{'id':'body-shape','component_ids':['body'],'reference_ids':['original'],
                                   'problem':'body too narrow','expected':'body width aligns reference','check_ids':['shape','depth']}],
            'editable_components':['body','joint'],'allowed_parameters':['width'],
            'protected_components':[{'id':'eye','mode':'rigid','allow_translation':True,'allow_rotation':True}],
            'checks':[{'id':'shape','method':'visual','component_ids':['body'],'view_ids':['front'],'view_role':'original'},
                      {'id':'depth','method':'visual','component_ids':['body'],'view_ids':['side'],'view_role':'depth'}],
            'dependency_edges':[['body','eye']], 'dependency_complete':False}


def diagnostic_init(*args):
    # Historical low-level geometry mechanics only; no production adoption.
    return repair.init(*args, diagnostic=True)

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.spec = fixture(); (self.root/'ref.png').write_bytes(b'reference-image')
        self.spec['references'][0]['sha256'] = repair.sha(self.root/'ref.png')
        self.contract = contract()
        self.specpath = self.write('spec.json',self.spec)
        self.cpath = self.write('contract.json',self.contract)
        self.session = diagnostic_init(self.specpath,self.cpath,self.root/'session')['session_path']

    def write(self,name,value):
        p=self.root/name;p.write_text(json.dumps(value));return p

    def candidate(self,spec=None):
        return self.write('candidate.json',spec or self.spec)

    def test_unchanged_candidate_requires_full_review(self):
        r=repair.check(self.session,self.candidate())
        self.assertTrue(r['passed'],r);self.assertEqual(r['required_checks'],['depth','shape'])
        self.assertEqual(r['dependency_mode'],'full-recheck')

    def test_parameter_drives_real_geometry_change(self):
        values=self.write('values.json',{'width':1.5})
        p=self.root/'param.json';repair.parameters(self.session,values,p)
        r=repair.check(self.session,p)
        self.assertTrue(r['passed'],r);self.assertIn('body',r['changed_components'])

    def test_parameter_bounds_and_unknown_rejected(self):
        for values in ({'width':4},{'other':1},{'width':True}):
            with self.assertRaises(ValueError):
                repair.parameters(self.session,self.write('values.json',values),self.root/'out.json')

    def test_ancestor_translation_detected_and_rigid_allowed(self):
        s=copy.deepcopy(self.spec);s['components'][1]['position']=[1,2,3]
        r=repair.check(self.session,self.candidate(s))
        self.assertTrue(r['passed'],r);self.assertIn('eye',r['changed_components'])

    def test_ancestor_rotation_allowed(self):
        s=copy.deepcopy(self.spec);s['components'][1]['rotation']=[0,.6,0]
        self.assertTrue(repair.check(self.session,self.candidate(s))['passed'])

    def test_rigid_deformation_rejected(self):
        s=copy.deepcopy(self.spec);s['components'][2]['geometry']['size'][0]=.8
        r=repair.check(self.session,self.candidate(s))
        self.assertFalse(r['passed']);self.assertTrue(any('rigid protection' in e for e in r['errors']))

    def test_exact_protection_sees_parent_motion(self):
        c=contract();c['protected_components']=[{'id':'eye','mode':'exact'}]
        cp=self.write('exact-contract.json',c);session=diagnostic_init(self.specpath,cp,self.root/'exact')['session_path']
        s=copy.deepcopy(self.spec);s['components'][1]['position']=[1,0,0]
        self.assertFalse(repair.check(session,self.candidate(s))['passed'])

    def test_disallowed_rigid_translation_rejected(self):
        c=contract();c['protected_components'][0]['allow_translation']=False
        cp=self.write('rigid-contract.json',c);session=diagnostic_init(self.specpath,cp,self.root/'rigid')['session_path']
        s=copy.deepcopy(self.spec);s['components'][1]['position']=[1,0,0]
        self.assertFalse(repair.check(session,self.candidate(s))['passed'])

    def test_frozen_targets_camera_material_and_bounds(self):
        for section in ('cameras','materials','references'):
            s=copy.deepcopy(self.spec)
            if section=='cameras':s['cameras']['front']['position'][2]=6
            elif section=='materials':s['materials']['solid']['color']='#aaaaaa'
            else:s['references'][0]['id']='new'
            self.assertFalse(repair.check(self.session,self.candidate(s))['passed'],section)
        s=copy.deepcopy(self.spec);s['parameters']['width']['max']=100
        self.assertFalse(repair.check(self.session,self.candidate(s))['passed'])

    def test_missing_resource_or_drift_fails(self):
        (self.root/'ref.png').write_bytes(b'changed')
        self.assertFalse(repair.check(self.session,self.candidate())['passed'])

    def test_frozen_snapshot_tampering_fails(self):
        (self.root/'session'/'baseline.json').write_text('{}')
        self.assertFalse(repair.check(self.session,self.candidate())['passed'])

    def test_contract_relaxation_fails(self):
        self.contract['dependency_complete']=True;self.write('contract.json',self.contract)
        self.assertFalse(repair.check(self.session,self.candidate())['passed'])

    def test_no_duplicate_view_position(self):
        s=copy.deepcopy(self.spec);s['cameras']['side']['position']=s['cameras']['front']['position']
        with self.assertRaises(ValueError):
            diagnostic_init(self.write('bad.json',s),self.cpath,self.root/'bad')

    def test_declared_dependency_transitive_and_unknown_fallback(self):
        c=contract();c['dependency_complete']=True
        session=diagnostic_init(self.specpath,self.write('dependencies.json',c),self.root/'deps')['session_path']
        s=copy.deepcopy(self.spec);s['components'][0]['position']=[1,0,0]
        r=repair.check(session,self.candidate(s));self.assertEqual(r['affected_components'],['body','eye'])

    def constraint_session(self,constraints):
        c=contract();c['constraints']=constraints
        for v in constraints:c['checks'].append({'id':v['id'],'method':'numeric','component_ids':['body']})
        return diagnostic_init(self.specpath,self.write('constraints.json',c),self.root/'constraints')['session_path']

    def test_real_vertex_distance(self):
        bind=lambda cid:{'component_id':cid,'vertex_index':0}
        session=self.constraint_session([{'id':'gap','kind':'distance','a':bind('body'),'b':bind('eye'),'min':0,'max':.01}])
        r=repair.check(session,self.candidate());self.assertFalse(r['passed']);self.assertTrue(any('constraint failed: gap' in e for e in r['errors']))

    def test_closed_topology_hole_and_reversed_normal(self):
        s=copy.deepcopy(self.spec);s['components'][0]['geometry']={'type':'mesh','positions':[0,0,0,1,0,0,0,1,0],'triangles':[0,1,2]}
        self.spec=s;self.specpath=self.write('spec.json',s)
        session=self.constraint_session([{'id':'closed','kind':'topology','component_id':'body','contract':'closed_shell'},
                                         {'id':'normal','kind':'normal','component_id':'body','triangle_index':0,'direction':[0,0,-1],'min_dot':.9}])
        r=repair.check(session,self.candidate());self.assertFalse(r['passed'])
        self.assertEqual({x['id'] for x in r['constraints'] if not x['passed']},{'closed','normal'})

    def review_fixture(self):
        p=self.candidate();r=repair.check(self.session,p)
        review={'version':1,'decision':'adopt','reviewer':'test human',**{k:r[k] for k in ('candidate_sha256','session_sha256','contract_sha256')},'results':[]}
        views=[]
        for cid,view in (('shape','front'),('depth','side')):
            (self.root/(view+'.png')).write_bytes(b'actual capture '+view.encode())
            artifact={'path':view+'.png','sha256':repair.sha(self.root/(view+'.png'))}
            views.append({'id':view,'artifacts':[artifact]})
            review['results'].append({'id':cid,'verdict':'pass','method':'visual','notes':'Reviewed contour and depth in fixed view.','artifacts':[artifact],'capture_report':'receipt.json'})
        self.write('receipt.json',{'views':views})
        return p,review

    def test_review_missing_failed_and_stale_candidate(self):
        p,review=self.review_fixture();review['results']=[]
        self.assertFalse(repair.validate_review(self.session,p,self.write('review.json',review))['passed'])
        p,review=self.review_fixture();s=copy.deepcopy(self.spec);s['components'][0]['position']=[.1,0,0];self.candidate(s)
        self.assertFalse(repair.validate_review(self.session,p,self.write('review.json',review))['passed'])

    def test_receipt_verifier_required_and_image_membership(self):
        p,review=self.review_fixture();mock=types.SimpleNamespace(validate_receipt=lambda *a,**k:{'passed':True})
        with patch.dict(sys.modules,{'repair_capture':mock}):
            self.assertTrue(repair.validate_review(self.session,p,self.write('review.json',review))['passed'])
            (self.root/'front.png').write_bytes(b'changed')
            self.assertFalse(repair.validate_review(self.session,p,self.write('review.json',review))['passed'])
        mock=types.SimpleNamespace(validate_receipt=lambda *a,**k:{'passed':False,'errors':['stale camera']})
        p,review=self.review_fixture()
        with patch.dict(sys.modules,{'repair_capture':mock}):
            self.assertFalse(repair.validate_review(self.session,p,self.write('review.json',review))['passed'])


    def test_authorized_rebind_preserves_reference_target_tolerance(self):
        s=copy.deepcopy(self.spec)
        s['observations']=[{'id':'edge','component_id':'body','local_point':[0,0,0],
                            'reference_id':'original','camera_id':'front','target':[10,20],'sigma_px':2,'role':'validation'}]
        c=contract();c['allow_rebind_observations']=['edge']
        sp=self.write('observed-spec.json',s)
        session=diagnostic_init(sp,self.write('rebind-contract.json',c),self.root/'rebind')['session_path']
        candidate=copy.deepcopy(s);candidate['observations'][0]['local_point']=[.2,0,0]
        self.assertTrue(repair.check(session,self.candidate(candidate))['passed'])
        for key,value in (('target',[100,200]),('sigma_px',999),('id','unknown'),('reference_id','other')):
            bad=copy.deepcopy(candidate);bad['observations'][0][key]=value
            self.assertFalse(repair.check(session,self.candidate(bad))['passed'],key)
        c['allow_rebind_observations']=['missing']
        with self.assertRaises(ValueError):diagnostic_init(sp,self.write('bad-rebind-contract.json',c),self.root/'bad-rebind')

    def test_stale_topology_requires_rebinding(self):
        s=copy.deepcopy(self.spec)
        s['components'][0]['geometry']={'type':'mesh','positions':[0,0,0,1,0,0,0,1,0,1,1,0],'triangles':[0,1,2,1,3,2]}
        s['observations']=[{'id':'corner','component_id':'body','vertex_index':0,'reference_id':'original','target':[0,0],'camera_id':'front'}]
        sp=self.write('topo-spec.json',s)
        session=diagnostic_init(sp,self.cpath,self.root/'topo')['session_path']
        s['components'][0]['geometry']['triangles']=[0,1,3,0,3,2]
        r=repair.check(session,self.candidate(s))
        self.assertFalse(r['passed']);self.assertTrue(any('rebinding' in e for e in r['errors']))


    def normal_fixture_session(self):
        s=copy.deepcopy(self.spec)
        s['components'][2]['geometry']={'type':'mesh','positions':[0,0,0,.2,0,0,0,.3,0],
                                       'triangles':[0,1,2],'normals':[0,0,1]*3}
        session=diagnostic_init(self.write('normal-spec.json',s),self.cpath,self.root/'normal')['session_path']
        return s,session

    def test_rigid_authored_normal_reversal_is_rejected(self):
        s,session=self.normal_fixture_session()
        s['components'][2]['geometry']['normals']=[0,0,-1]*3
        r=repair.check(session,self.candidate(s))
        self.assertFalse(r['passed']);self.assertIn('eye',r['changed_components'])
        self.assertTrue(any('rigid protection violated: eye' in e for e in r['errors']))

    def test_rigid_parent_rotation_coherently_rotates_normals(self):
        s,session=self.normal_fixture_session()
        s['components'][1]['rotation']=[.37,.42,.13]
        r=repair.check(session,self.candidate(s))
        self.assertTrue(r['passed'],r)

    def test_rigid_local_rotation_normals_must_follow_positions(self):
        import scene_build
        s,session=self.normal_fixture_session();g=s['components'][2]['geometry'];angle=[.6,.2,0]
        g['positions']=[x for i in range(0,len(g['positions']),3) for x in scene_build.rotate(g['positions'][i:i+3],angle)]
        self.assertFalse(repair.check(session,self.candidate(s))['passed'])
        g['normals']=[x for i in range(0,len(g['normals']),3) for x in scene_build.rotate(g['normals'][i:i+3],angle)]
        r=repair.check(session,self.candidate(s));self.assertTrue(r['passed'],r)

    def test_target_cannot_bind_only_unrelated_visual_components(self):
        c=contract()
        for row in c['checks']:row['component_ids']=['eye']
        with self.assertRaisesRegex(ValueError,'target component lacks bound visual coverage: body'):
            diagnostic_init(self.specpath,self.write('misbound-contract.json',c),self.root/'misbound')

    def test_each_target_component_needs_visual_check_not_protected_by_default(self):
        c=contract();c['targets'][0]['component_ids']=['body','eye']
        with self.assertRaisesRegex(ValueError,'target component lacks bound visual coverage: eye'):
            diagnostic_init(self.specpath,self.write('multitarget-contract.json',c),self.root/'multitarget')
        # Protected components not targeted need no separate visual check.
        self.assertTrue(repair.check(self.session,self.candidate())['passed'])

    def test_restore_immutable_and_non_overwriting(self):
        p=self.root/'restored.json';r=repair.restore(self.session,p)
        self.assertEqual(r['sha256'],repair.sha(self.specpath))
        with self.assertRaises(ValueError):repair.restore(self.session,p)
        with self.assertRaises(ValueError):diagnostic_init(self.specpath,self.cpath,self.root/'session')


if __name__=='__main__':unittest.main()
