import copy,json,struct,tempfile,unittest
from pathlib import Path
import numpy as np
from feature_guard import freeze,check
from asset_manifest import sha256
def fixture(path,change=None):
    doc={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0,1]}],'nodes':[{'name':'carrier','mesh':0},{'name':'component','mesh':1}],'meshes':[],'accessors':[],'bufferViews':[],'buffers':[{}],'materials':[{'name':'paint'}]};blob=bytearray()
    for i,pos in enumerate([[[0,0,0],[0,1,0],[0,0,1]],[[.01,.2,.2],[.01,.3,.2],[.01,.2,.3]]]):
        attributes={}
        values={'POSITION':np.array(pos,dtype='<f4'),'NORMAL':np.array([[1,0,0]]*3,dtype='<f4'),'TEXCOORD_0':np.zeros((3,2),dtype='<f4')}
        if change:change(i,values,doc)
        for key,v in values.items():
            attributes[key]=len(doc['accessors']);doc['bufferViews'].append({'buffer':0,'byteOffset':len(blob),'byteLength':v.nbytes});blob.extend(v.tobytes());doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'type':'VEC2' if key=='TEXCOORD_0' else 'VEC3','count':3})
        doc['meshes'].append({'primitives':[{'attributes':attributes,'material':0}]})
    doc['buffers'][0]['byteLength']=len(blob);s=json.dumps(doc).encode();s+=b' '*(-len(s)%4);path.write_bytes(struct.pack('<III',0x46546c67,2,28+len(s)+len(blob))+struct.pack('<II',len(s),0x4e4f534a)+s+struct.pack('<II',len(blob),0x004e4942)+blob)
class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.src=self.root/'a.glb';self.out=self.root/'b.glb';fixture(self.src)
        self.spec={'schema_version':1,'baseline_sha256':sha256(self.src),'evidence':'Explicit test carrier and component','allowed_changes':{'n0:p0':{'max_displacement':.25},'n1:p0':{'max_displacement':.25}},'fixed_regions':[{'id':'seam','binding':'n0:p0','indices':[0],'tolerance':0,'evidence':'Known carrier corner'}],'clearances':[{'id':'gap','moving_binding':'n1:p0','fixed_region':'seam','axes':[1,2],'minimum':.1,'evidence':'Known footprint relation'}]}
    def tearDown(self):self.tmp.cleanup()
    def run_case(self,change=None):
        spec=self.root/'s.json';spec.write_text(json.dumps(self.spec));self.lock=self.root/'l.json';freeze(self.src,spec,self.lock);fixture(self.out,change);return check(self.lock,self.out)
    def test_safe_component_edit_with_fixed_carrier(self):
        def change(i,v,d):
            if i==1:v['POSITION'][:,1]+=.1
        self.assertEqual(self.run_case(change)['verdict'],'passed')
    def test_fixed_seam_blocks_otherwise_bounded_edit(self):
        def change(i,v,d):
            if i==0:v['POSITION'][0,1]+=.01
        self.assertIn('Fixed feature moved: seam',self.run_case(change)['blockers'])
    def test_outside_allowed_vertices_blocks(self):
        self.spec['allowed_changes']['n1:p0']['indices']=[0]
        def change(i,v,d):
            if i==1:v['POSITION'][1,1]+=.01
        self.assertEqual(self.run_case(change)['verdict'],'needs_revision')
    def test_uv_tamper_blocks(self):
        def change(i,v,d):v['TEXCOORD_0'][0,0]=.5
        self.assertEqual(self.run_case(change)['verdict'],'needs_revision')
    def test_fixed_feature_normal_blocks_without_position_change(self):
        def change(i,v,d):
            if i==0:v['NORMAL'][0]=[0,1,0]
        self.assertIn('Fixed feature normals changed: seam',self.run_case(change)['blockers'])
    def test_normals_outside_allowed_vertices_block(self):
        self.spec['allowed_changes']['n1:p0']['indices']=[0]
        def change(i,v,d):
            if i==1:v['NORMAL'][1]=[0,1,0]
        self.assertIn('Outside allowed normal domain changed: n1:p0',self.run_case(change)['blockers'])
    def test_clearance_blocks_without_seam_motion(self):
        def change(i,v,d):
            if i==1:v['POSITION'][0,1:]=.02
        self.spec['allowed_changes']['n1:p0']['max_displacement']=1
        self.assertIn('Feature clearance violated: gap',self.run_case(change)['blockers'])
    def test_undeclared_binding_blocks(self):
        self.spec['allowed_changes'].pop('n1:p0')
        def change(i,v,d):
            if i==1:v['POSITION'][:,1]+=.01
        self.assertIn('Non-target positions changed: n1:p0',self.run_case(change)['blockers'])
    def test_loosened_frozen_spec_rejected(self):
        self.run_case();data=json.loads(self.lock.read_text());data['spec']['fixed_regions'][0]['tolerance']=99;self.lock.write_text(json.dumps(data))
        with self.assertRaises(ValueError):check(self.lock,self.out)
    def test_empty_protected_region_rejected(self):
        self.spec['fixed_regions'][0]['indices']=[]
        with self.assertRaises(ValueError):self.run_case()
    def test_node_transform_change_requires_remapping(self):
        def change(i,v,d):d['nodes'][0]['translation']=[.1,0,0]
        with self.assertRaises(ValueError):self.run_case(change)
    def test_material_change_blocks(self):
        def change(i,v,d):d['materials'][0]['name']='new'
        self.assertIn('Protected definitions changed: materials',self.run_case(change)['blockers'])
if __name__=='__main__':unittest.main()
