import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import workflow as w
from production_evidence import validate as viewcheck
import repair_review as rr

class ProductionIntegration(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.r=Path(self.t.name)
        for f in ('ref','source'): (self.r/f).write_text(f)
        from PIL import Image
        for f in ('front','side'):Image.new('RGB',(4,4),'gray').save(self.r/f,format='PNG')
        self.s={'schema_version':1,'id':'fixture','domain':'generic','coordinate_system':{'unit':'m','up':'y','forward':'z'},'references':[{'id':'ref','path':'ref','sha256':w.digest(self.r/'ref'),'origin':'original','approved':True}], 'source_files':[{'path':'source','sha256':w.digest(self.r/'source')}], 'parameters':{},'materials':{'m':{'color':'#888888'}},'components':[{'id':'body','role':'shell','material':'m','geometry':{'type':'mesh','positions':[0,0,0,1,0,0,0,1,0],'triangles':[0,1,2]}}], 'observations':[], 'cameras':{'front':{'position':[0,0,3],'target':[0,0,0]},'side':{'position':[3,0,0],'target':[0,0,0]}},'checks':[{'id':'production-feature-coverage','kind':'visual','required':True,'stage':'body'}],'quality_contract':{'scope':'display','limits':{},'production_standard':1},'production_contract':{'version':1,'profiles':['soft'],'features':[{'id':'shape','reference_id':'ref','roi':[0,0,1,1],'provenance':'observed','importance':'critical','form_type':'volume','component_ids':['body'],'method':{'type':'mesh','rationale':'volume'},'geometry_bindings':[{'component_id':'body','vertex_index':0}],'check_ids':['production-feature-coverage']}],'relations':[]}}
        self.sp=self.r/'spec.json';self.save()
    def save(self):w.save(self.sp,self.s)
    def evidence(self,stage='body'):
        art=[{'path':x,'sha256':w.digest(self.r/x)} for x in ('front','side')]
        e={'stage':stage,'verdict':'pass','acceptance':'quality_passed','reviewer':'fixture','rationale':'synthetic metadata check only','review_scope':'display','spec_sha256':w.digest(self.sp),'resource_hashes':{x['path']:x['sha256'] for x in self.s['references']+self.s['source_files']},'artifacts':art,'check_results':[{'id':x,'verdict':'pass','method':'visual','reviewer':'fixture','scope':'display','artifact_paths':['front','side']} for x in ('stage:'+stage,'production-feature-coverage')],'production_review':{'reviewer_role':'author','execution_reference':'test fixture','coverage_verdict':'pass','features':[{'id':'shape','verdict':'pass','rationale':'metadata only','views':[{'camera_id':x,'artifact_path':x} for x in ('front','side')]}]}}
        capture={'passed':True,'spec_sha256':w.digest(self.sp),'cameras':self.s['cameras'],'captures':[{'view':x,'mode':'gray','file':x,'sha256':w.digest(self.r/x)} for x in ('front','side')]}
        w.save(self.r/'capture.json',capture);e['artifacts'].append({'path':'capture.json','sha256':w.digest(self.r/'capture.json')});e['production_review']['capture_report']='capture.json'
        return e
    def check(self,e,stage='body'):
        p=self.r/'review.json';w.save(p,e);return w.validate_evidence(self.sp,p,stage)
    def test_full_metadata_pass_no_visual_claim(self):self.check(self.evidence())
    def test_requires_contract_at_spec_gate(self):
        del self.s['production_contract'];self.save()
        with self.assertRaisesRegex(ValueError,'contract required'):self.check(self.evidence('spec'),'spec')
    def test_single_view_rejected(self):
        e=self.evidence();e['production_review']['features'][0]['views'].pop()
        with self.assertRaisesRegex(ValueError,'two distinct'):self.check(e)
    def test_duplicate_position_rejected(self):
        self.s['cameras']['side']['position']=[0,0,3];self.save()
        with self.assertRaisesRegex(ValueError,'duplicated camera'):self.check(self.evidence())
    def test_missing_coverage_review_rejected(self):
        e=self.evidence();e['production_review']['coverage_verdict']='unevaluated'
        with self.assertRaisesRegex(ValueError,'coverage'):self.check(e)
    def test_policy_cannot_be_removed(self):
        state=self.r/'state.json';w.init(self.sp,state);del self.s['quality_contract']['production_standard'];self.save()
        self.assertTrue(w.status(state)['blocked'])
        p=self.r/'e.json';w.save(p,self.evidence('intake'))
        with self.assertRaisesRegex(ValueError,'downgraded'):w.mark(state,p)
    def test_unknown_policy_rejected(self):
        self.s['quality_contract']['production_standard']=2;self.save()
        with self.assertRaisesRegex(ValueError,'unsupported production'):w.validate_spec(self.sp)
    def test_missing_local_visual_cannot_use_numeric(self):
        e=self.evidence();e['check_results'][1]['method']='numeric'
        with self.assertRaisesRegex(ValueError,'visual'):self.check(e)
    def test_source_change_invalidates_evidence(self):
        e=self.evidence();(self.r/'source').write_text('changed')
        with self.assertRaisesRegex(ValueError,'hash'):self.check(e)
    def record(self):
        before=copy.deepcopy(self.s);after=copy.deepcopy(self.s);after['components'][0]['position']=[.1,0,0]
        w.save(self.r/'before.json',before);w.save(self.r/'after.json',after)
        return {'version':1,'issue_id':'shape','hypothesis':'position error','change_summary':'translate body','cause':'proportion','decision':'adopt','before':{'spec_path':'before.json','sha256':w.digest(self.r/'before.json')},'after':{'spec_path':'after.json','sha256':w.digest(self.r/'after.json')},'protected_components':[],'artifacts':[{'path':'front','sha256':w.digest(self.r/'front')}],'results':[{'scope':k,'verdict':'pass','method':'visual','reviewer':'fixture','artifact_paths':['front']} for k in ('target','regression')]}
    def repair(self,r):
        p=self.r/'repair.json';w.save(p,r);return rr.validate(p,self.r/'after.json')
    def test_valid_repair_record(self):self.assertTrue(self.repair(self.record())['valid'])
    def test_bad_repair_adoption(self):
        r=self.record();r['results'][1]['verdict']='fail'
        with self.assertRaisesRegex(ValueError,'cannot adopt'):self.repair(r)
    def test_stagnation_reassess(self):
        r=self.record();r['consecutive_no_improvement']=2
        with self.assertRaisesRegex(ValueError,'reassessment'):self.repair(r)
        r['decision']='reassess';self.assertTrue(self.repair(r)['valid'])
    def test_protected_changed(self):
        r=self.record();r['protected_components']=['body']
        with self.assertRaisesRegex(ValueError,'protected'):self.repair(r)
    def test_comparison_basis_changed(self):
        r=self.record();s=w.read(self.r/'after.json');s['quality_contract']['limits']={'relaxed':1};w.save(self.r/'after.json',s);r['after']['sha256']=w.digest(self.r/'after.json')
        with self.assertRaisesRegex(ValueError,'basis changed'):self.repair(r)

    def test_relaxed_geometry_threshold_rejected(self):
        r=self.record();s=w.read(self.r/'after.json');s['production_contract']['geometry_checks']=[{'max':99}];w.save(self.r/'after.json',s);r['after']['sha256']=w.digest(self.r/'after.json')
        with self.assertRaisesRegex(ValueError,'basis changed'):self.repair(r)
    def test_protected_parameter_change_rejected(self):
        r=self.record()
        for name,value in [('before',0),('after',.1)]:
            s=w.read(self.r/(name+'.json'));s['parameters']={'x':{'value':value,'min':-1,'max':1}};s['components'][0]['position']=[{'param':'x'},0,0];w.save(self.r/(name+'.json'),s);r[name]['sha256']=w.digest(self.r/(name+'.json'))
        r['protected_components']=['body']
        with self.assertRaisesRegex(ValueError,'resolved'):self.repair(r)
    def test_capture_wrong_camera_rejected(self):
        e=self.evidence();c=w.read(self.r/'capture.json');c['captures'][1]['view']='front';w.save(self.r/'capture.json',c);e['artifacts'][-1]['sha256']=w.digest(self.r/'capture.json')
        with self.assertRaisesRegex(ValueError,'matching captured'):self.check(e)
    def test_non_image_cannot_be_view(self):
        (self.r/'front').write_text('not a rendered image');e=self.evidence()
        with self.assertRaises(Exception):self.check(e)
    def test_same_direction_not_multiview(self):
        self.s['cameras']['side']['position']=[0,0,6];self.save()
        with self.assertRaisesRegex(ValueError,'directions'):self.check(self.evidence())
    def test_production_adoption_needs_repair(self):
        import project
        w.save(self.r/'project.json',{'schema_version':1});w.save(self.r/'fit.json',{'input_file_sha256':w.digest(self.sp),'spec':self.s})
        with self.assertRaisesRegex(ValueError,'repair-record'):project.adopt(self.r,self.r/'fit.json')

    def test_parameterized_camera_change_rejected(self):
        r=self.record()
        for name,value in [('before',3),('after',4)]:
            s=w.read(self.r/(name+'.json'));s['parameters']={'cx':{'value':value,'min':1,'max':5}};s['cameras']['front']['position']=[0,0,{'param':'cx'}];w.save(self.r/(name+'.json'),s);r[name]['sha256']=w.digest(self.r/(name+'.json'))
        with self.assertRaisesRegex(ValueError,'resolved comparison'):self.repair(r)

if __name__=='__main__':unittest.main()
