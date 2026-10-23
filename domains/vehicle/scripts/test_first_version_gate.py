import json
import tempfile
import unittest
from pathlib import Path
from first_version_gate import seal, check, sha

class ExecutionGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ('reference','model','live','evidence','validation'):
            (self.root/name).write_text('synthetic contract fixture; not visual fidelity proof')
        specs=[('front.'+k,k) for k in ('silhouette','landmark','visual')]+[('feature.lamps','visual'),('protection','protection'),('functional','functional')]
        self.plan={'references':[self.ref('reference')],'required_views':['front'],'required_features':['lamps'],'budget':{'max_rounds':6,'stagnation_rounds':2,'min_improvement':.01},'checks':[{'id':i,'kind':k,'op':'min','limit':1,'uncertainty':0,'max_regression':0,'calibrated':True,'reason':'synthetic test'} for i,k in specs]}
        self.save('plan',self.plan);seal(self.root/'plan',self.root/'lock')
        self.save('alignment',{'status':'validated','independent_validation':self.ref('validation')})
        self.manifest={'model':self.ref('model'),'plan_sha256':sha(self.root/'plan'),'inputs':[self.ref('model')],'live_inputs':[self.ref('live')],'outputs':{k:self.ref('evidence') for k in ('front.render','front.gray','front.difference','feature.lamps')}}
        self.manifest['outputs']['front.alignment']=self.ref('alignment')
        self.record={'round':1,'alignment':'validated','plan_sha256':sha(self.root/'plan'),'model':self.ref('model'),'history':[],'checks':{i:{'value':1,'evidence':[self.ref('evidence')]} for i,k in specs}}
    def save(self,n,obj): (self.root/n).write_text(json.dumps(obj))
    def ref(self,n):return {'path':n,'sha256':sha(self.root/n)}
    def run_gate(self):
        self.save('capture',self.manifest);self.record['capture']=self.ref('capture');self.save('record',self.record)
        return check(self.root/'lock',self.root/'record')
    def test_complete_contract_pass(self):self.assertTrue(self.run_gate()['may_deliver'])
    def test_missing_difference(self):
        del self.manifest['outputs']['front.difference']
        self.assertEqual(self.run_gate()['action'],'calibrate')
    def test_unregistered_camera(self):
        self.save('alignment',{'status':'unregistered'});self.manifest['outputs']['front.alignment']=self.ref('alignment')
        self.assertFalse(self.run_gate()['may_end_as_complete'])
    def test_missing_feature(self):
        del self.manifest['outputs']['feature.lamps']
        self.assertFalse(self.run_gate()['may_deliver'])
    def test_stale_live_asset(self):
        (self.root/'live').write_text('changed runtime')
        with self.assertRaises(ValueError):self.run_gate()
    def test_changed_render(self):
        (self.root/'evidence').write_text('changed pixels')
        with self.assertRaises(ValueError):self.run_gate()
    def test_changed_plan(self):
        self.plan['checks'][0]['limit']=0;self.save('plan',self.plan)
        with self.assertRaises(ValueError):self.run_gate()
    def test_visual_fail_function_pass(self):
        self.record['checks']['front.visual']['value']=0
        self.assertEqual(self.run_gate()['action'],'repair')
    def test_unbound_evidence(self):
        self.record['checks']['functional']['evidence']=[self.ref('validation')]
        with self.assertRaises(ValueError):self.run_gate()
    def test_missing_coverage(self):
        self.plan['checks']=self.plan['checks'][1:];self.save('plan2',self.plan)
        with self.assertRaises(ValueError):seal(self.root/'plan2',self.root/'lock2')
    def test_no_overwrite(self):
        with self.assertRaises(FileExistsError):seal(self.root/'plan',self.root/'lock')

if __name__=='__main__':unittest.main()
