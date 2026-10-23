import copy
import json
from pathlib import Path
import tempfile
import unittest
from fidelity_loop import decide, sha


class FidelityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'target').write_text('approved design')
        (self.root/'model').write_text('candidate')
        (self.root/'evidence').write_text('synthetic contract fixture; not image fidelity proof')
        self.plan = {'references':[self.ref('target')], 'budget':{'max_rounds':6,'stagnation_rounds':2,'min_improvement':.01}, 'checks':[{'id':k,'kind':k,'op':'min','limit':1,'uncertainty':0,'max_regression':0,'calibrated':True,'reason':'synthetic fixture'} for k in ('silhouette','landmark','visual','protection','functional')]}
        self.save('plan.json', self.plan)
        self.r = {'plan_sha256':sha(self.root/'plan.json'),'round':1,'alignment':'validated','model':self.ref('model'),'checks':{s['id']:{'value':1,'evidence':[self.ref('evidence')]} for s in self.plan['checks']},'history':[]}
    def save(self, name, value):
        (self.root/name).write_text(json.dumps(value))
    def ref(self, name):
        return {'path':name,'sha256':sha(self.root/name)}
    def run_gate(self, r=None):
        return decide(self.root/'plan.json', r or self.r)
    def advance(self, r):
        self.save(f"round-{r['round']}.json", r)
        ref = self.ref(f"round-{r['round']}.json")
        new = copy.deepcopy(r)
        new['history'].append(ref)
        new['round'] += 1
        new['previous_best'] = r.get('previous_best', ref)
        return new
    def test_complete_pass(self):
        self.assertEqual(self.run_gate()['action'],'passed')
    def test_functional_pass_does_not_hide_shape_failure(self):
        self.r['checks']['silhouette']['value']=.5
        self.assertEqual(self.run_gate()['action'],'repair')
    def test_missing_measurement_calibrates(self):
        del self.r['checks']['landmark']
        self.assertEqual(self.run_gate()['action'],'calibrate')
        self.assertIsNone(self.run_gate()['loss'])
    def test_missing_evidence_calibrates(self):
        self.r['checks']['visual']['evidence']=[]
        self.assertEqual(self.run_gate()['action'],'calibrate')
    def test_alignment_required(self):
        self.r['alignment']='unregistered'
        self.assertEqual(self.run_gate()['action'],'calibrate')
    def test_threshold_calibration_required(self):
        self.plan['checks'][0]['calibrated']=False
        self.save('plan.json',self.plan)
        self.r['plan_sha256']=sha(self.root/'plan.json')
        self.assertEqual(self.run_gate()['action'],'calibrate')
    def test_changed_reference_rejected(self):
        (self.root/'target').write_text('easier target')
        with self.assertRaises(ValueError): self.run_gate()
    def test_changed_model_rejected(self):
        (self.root/'model').write_text('new model old evidence')
        with self.assertRaises(ValueError): self.run_gate()
    def test_nonfinite_rejected(self):
        self.r['checks']['landmark']['value']=float('nan')
        with self.assertRaises(ValueError): self.run_gate()
    def test_regression_rolls_back(self):
        r=self.advance(self.r)
        r['checks']['silhouette']['value']=.7
        self.assertEqual(self.run_gate(r)['action'],'rollback')
    def test_stagnation_changes_method(self):
        self.r['checks']['silhouette']['value']=.5
        r=self.advance(self.advance(self.r))
        self.assertEqual(self.run_gate(r)['action'],'change_method')
    def test_budget_exhaustion_blocks(self):
        self.r['checks']['silhouette']['value']=.5
        r=self.r
        for _ in range(5): r=self.advance(r)
        self.assertEqual(self.run_gate(r)['action'],'blocked')
    def test_missing_history_rejected(self):
        self.r['round']=3
        with self.assertRaises(ValueError): self.run_gate()
    def test_changed_plan_rejected(self):
        self.plan['checks'][0]['limit']=.01
        self.save('plan.json',self.plan)
        with self.assertRaises(ValueError): self.run_gate()
    def test_visual_failure_blocks_even_if_metrics_pass(self):
        self.r['checks']['visual']['value']=0
        self.assertEqual(self.run_gate()['action'],'repair')


if __name__=='__main__': unittest.main()
