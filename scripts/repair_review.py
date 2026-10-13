"""Versioned repair evidence validation; no automatic visual judgment or editing."""
import hashlib
import json
import math
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(path, current_spec=None):
    path = Path(path).resolve()
    record = json.loads(path.read_text())
    require(record.get('version') == 1, 'unsupported repair version')
    for k in ('issue_id', 'hypothesis', 'change_summary'):
        require(isinstance(record.get(k), str) and record[k].strip(), 'missing repair '+k)
    require(record.get('cause') in ('camera','proportion','representation','connection','normals','material','runtime'), 'classify repair cause')
    require(record.get('decision') in ('adopt','rework','reassess'), 'invalid repair decision')
    snapshots = {}
    for key in ('before','after'):
        item = record.get(key,{})
        p = path.parent / item.get('spec_path','')
        require(p.is_file() and digest(p)==item.get('sha256'), 'stale '+key+' spec')
        snapshots[key] = json.loads(p.read_text())
    require(record['before']['sha256'] != record['after']['sha256'], 'repair needs changed spec identity')
    if current_spec is not None:
        require(digest(current_spec)==record['after']['sha256'], 'repair is not for current spec')
    # Freeze the basis of comparison, including targets and thresholds.
    for key in ('references','quality_contract','observations','checks','production_contract','cameras','coordinate_system'):
        require(snapshots['before'].get(key)==snapshots['after'].get(key), 'comparison basis changed: '+key)
    ids={c['id'] for c in snapshots['after'].get('components',[])}
    protected=record.get('protected_components')
    require(isinstance(protected,list) and len(protected)==len(set(protected)) and all(x in ids for x in protected), 'invalid protected components')
    by=[{c['id']:c for c in snapshots[k].get('components',[])} for k in ('before','after')]
    require(all(by[0].get(x)==by[1][x] for x in protected), 'protected component changed')
    from scene_build import prepared
    prepared_snapshots=[prepared(snapshots[k]) for k in ('before','after')]
    for key in ('references','quality_contract','observations','checks','production_contract','cameras','coordinate_system'):
        require(prepared_snapshots[0][0].get(key)==prepared_snapshots[1][0].get(key), 'resolved comparison basis changed: '+key)
    resolved=[item[1] for item in prepared_snapshots]
    for cid in protected:
        chains=[]
        for nodes in resolved:
            chain=[];cursor=cid
            while cursor is not None:
                node=nodes[cursor];chain.append(node);cursor=node.get('parent')
            chains.append(chain)
        require(chains[0]==chains[1], 'protected resolved geometry/ancestor changed')
    artifacts=record.get('artifacts')
    require(isinstance(artifacts,list) and artifacts, 'repair artifacts required')
    paths=set()
    for a in artifacts:
        name=a.get('path');require(isinstance(name,str) and name and name not in paths,'unique artifact paths required');paths.add(name)
        p=path.parent/name
        require(p.is_file() and digest(p)==a.get('sha256'), 'stale repair artifact')
    results=record.get('results')
    require(isinstance(results,list) and results, 'repair results required')
    require(any(x.get('scope')=='target' for x in results) and any(x.get('scope')=='regression' for x in results),'target and regression results required')
    for result in results:
        require(result.get('scope') in ('target','regression'),'invalid result scope')
        require(result.get('verdict') in ('pass','fail','unevaluated'),'invalid result verdict')
        require(result.get('method') in ('visual','numeric','runtime'),'invalid result method')
        require(isinstance(result.get('reviewer'),str) and result['reviewer'].strip(),'reviewer required')
        require(result.get('artifact_paths') and all(p in paths for p in result['artifact_paths']),'result evidence required')
    attempts=record.get('consecutive_no_improvement',0);limit=record.get('reassessment_after',2)
    require(type(attempts)==int and attempts>=0 and type(limit)==int and limit>=1,'invalid retry counters')
    require(attempts<limit or record['decision']=='reassess','stagnation requires reassessment')
    if record['decision']=='adopt':
        require(all(x['verdict']=='pass' for x in results),'cannot adopt failed/unevaluated repair')
        require(any(x['scope']=='target' and x['method']=='visual' for x in results),'adoption needs target visual review')
    return {'valid':True,'decision':record['decision'],'scope':'repair metadata, snapshot integrity and declared regression; reviewer truth and completeness are not automatically verified'}
