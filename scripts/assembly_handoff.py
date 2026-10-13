#!/usr/bin/env python3
"""Validate declared parallel work ownership; never schedules agents or merges files.

Manifest: {schema_version:1, root:ABS, inputs:{relative:sha256},
contracts:{relative:sha256}, tasks:[{id, writes:[relative file paths]}]}.
Plans must explicitly declare review_paths (bounded directories/files) and
metadata_paths (exact receipt/manifest files excluded from snapshots).
Receipts: {task_id, manifest_sha256, changed_paths:[relative],
artifacts:{relative:sha256}}. Writes are exact files, not globs/directories.
`init` snapshots a plan's inputs/contracts (lists) into a manifest.
`claim` checks task ownership and prints its contract; it does not run an agent.
`check-all --manifest M --receipts R1 R2` requires valid receipts for all changed tasks.
`check` verifies receipt metadata and files; changes inside review_paths are checked against the captured baseline.
Other tasks with changes are reported as unreviewed, never silently accepted. No git commands or file copying occur.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def resolve(root, name):
    require(isinstance(name, str) and bool(name) and '\\' not in name, 'invalid relative path')
    p = PurePosixPath(name)
    require(not p.is_absolute() and all(x not in ('..', '.') for x in name.split('/')) and '' not in name.split('/'), 'path traversal/noncanonical path rejected')
    target = (root / name).resolve()
    require(target.is_relative_to(root), 'symlink escapes workspace')
    return target


def snapshot(root, review_paths, metadata_paths):
    require(isinstance(review_paths, list) and review_paths, 'bounded review_paths required')
    require(isinstance(metadata_paths, list), 'explicit metadata_paths required')
    excluded = {resolve(root, name) for name in metadata_paths}
    result = {}
    for name in review_paths:
        start = root if name == '.' else resolve(root, name)
        paths = start.rglob('*') if start.is_dir() else [start]
        for p in paths:
            require(not p.is_symlink(), 'symlinks forbidden in review scope')
            if p.is_file() and p.resolve() not in excluded:
                result[p.relative_to(root).as_posix()] = sha(p)
    return result


def reviewed(root, name, review_paths):
    p = resolve(root, name)
    for scope in review_paths:
        base = root if scope == '.' else resolve(root, scope)
        if p == base or p.is_relative_to(base):
            return True
    return False


def validate(manifest_path):
    m = read(manifest_path)
    require(m.get('schema_version') == 1, 'unsupported manifest schema')
    require(isinstance(m.get('root'), str) and Path(m['root']).is_absolute(), 'root must be absolute')
    root = Path(m['root']).resolve()
    require(root.is_dir(), 'workspace root missing')
    require(isinstance(m.get('baseline'), dict), 'baseline snapshot required')
    snapshot(root, m.get('review_paths'), m.get('metadata_paths'))
    locked = set()
    for field in ('inputs', 'contracts'):
        require(isinstance(m.get(field), dict), field + ' must map paths to hashes')
        for name, expected in m[field].items():
            p = resolve(root, name)
            require(p.is_file() and sha(p) == expected, 'stale/missing ' + field + ': ' + name)
            locked.add(p)
    require(isinstance(m.get('tasks'), list) and m['tasks'], 'tasks required')
    owners, ids = {}, set()
    for task in m['tasks']:
        require(isinstance(task.get('id'), str) and task['id'] and task['id'] not in ids, 'missing/duplicate task id')
        ids.add(task['id'])
        require(isinstance(task.get('writes'), list) and task['writes'], 'explicit write paths required')
        for name in task['writes']:
            p = resolve(root, name)
            require(reviewed(root, name, m['review_paths']), 'write outside review scope')
            require(not p.is_dir(), 'write paths must name files')
            require(p not in locked, 'input/contract cannot be writable: ' + name)
            require(p not in owners, 'overlapping writes: ' + name)
            require(not any(p.is_relative_to(old) or old.is_relative_to(p) for old in owners), 'nested overlapping write paths')
            owners[p] = task['id']
    for name in m['metadata_paths']:
        p = resolve(root, name)
        require(p not in locked and p not in owners, 'metadata exclusion overlaps source/input')
    return m, root


def init(plan_path, manifest_path):
    require(not Path(manifest_path).exists(), 'manifest exists; refusing overwrite')
    plan = read(plan_path)
    root = Path(plan['root']).resolve()
    manifest = {'schema_version': 1, 'root': str(root), 'tasks': plan['tasks'], 'review_paths': plan.get('review_paths'), 'metadata_paths': plan.get('metadata_paths')}
    for field in ('inputs', 'contracts'):
        require(isinstance(plan.get(field), list), 'plan ' + field + ' must be list')
        require(len(plan[field]) == len(set(plan[field])), 'duplicate input/contract paths')
        manifest[field] = {name: sha(resolve(root, name)) for name in plan[field]}
    manifest['baseline'] = snapshot(root, manifest['review_paths'], manifest['metadata_paths'])
    # Validate before committing destination; temporary file is removed even on rejection.
    target = Path(manifest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.pending')
    require(not temp.exists(), 'pending manifest exists')
    require(str(target.resolve().relative_to(root)) in manifest['metadata_paths'], 'manifest must be explicitly excluded metadata')
    try:
        temp.write_text(json.dumps(manifest, indent=2) + '\n')
        validate(temp)
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()
    return {'valid': True, 'manifest_sha256': sha(target)}


def claim(manifest_path, task_id):
    m, _ = validate(manifest_path)
    task = next((t for t in m['tasks'] if t['id'] == task_id), None)
    require(task is not None, 'unknown task')
    return {'task': task, 'manifest_sha256': sha(manifest_path), 'inputs': m['inputs'], 'contracts': m['contracts'], 'mode': 'ownership check only; no agent scheduled'}


def check(manifest_path, receipt_path):
    m, root = validate(manifest_path)
    receipt = read(receipt_path)
    require(receipt.get('manifest_sha256') == sha(manifest_path), 'stale manifest receipt')
    task = next((t for t in m['tasks'] if t['id'] == receipt.get('task_id')), None)
    require(task is not None, 'unknown receipt task')
    changed = receipt.get('changed_paths')
    artifacts = receipt.get('artifacts')
    require(isinstance(changed, list) and changed and len(changed) == len(set(changed)), 'nonempty unique changed paths required')
    require(isinstance(artifacts, dict) and set(artifacts) == set(changed), 'each changed path needs exactly one artifact hash')
    current = snapshot(root, m['review_paths'], m['metadata_paths'])
    actual = {name for name in set(current) | set(m['baseline']) if current.get(name) != m['baseline'].get(name)}
    owners = {name: t['id'] for t in m['tasks'] for name in t['writes']}
    unknown = actual - set(owners)
    require(not unknown, 'undeclared file changes: ' + ', '.join(sorted(unknown)))
    own_changes = {name for name in actual if owners[name] == task['id']}
    require(set(changed) == own_changes, 'receipt does not match actual task changes')
    unreviewed = sorted({owners[name] for name in actual if owners[name] != task['id']})
    for name in changed:
        p = resolve(root, name)
        require(name in task['writes'], 'unauthorized write: ' + name)
        if artifacts[name] is None:
            require(not p.exists() and name in m['baseline'], 'invalid deletion receipt')
        else:
            require(p.is_file() and sha(p) == artifacts[name], 'missing/stale artifact: ' + name)
    return {'valid': True, 'task_id': task['id'], 'verified_artifacts': changed, 'unreviewed_tasks': unreviewed, 'integration_ready': not unreviewed, 'scope': 'declared receipt and input integrity; no visual acceptance or automatic merge'}


def check_all(manifest_path, receipt_paths):
    require(bool(receipt_paths), 'receipts required')
    results = [check(manifest_path, path) for path in receipt_paths]
    ids = [r['task_id'] for r in results]
    require(len(ids) == len(set(ids)), 'duplicate task receipts')
    pending = set().union(*(set(r['unreviewed_tasks']) for r in results)) - set(ids)
    require(not pending, 'missing task receipts: ' + ', '.join(sorted(pending)))
    return {'valid': True, 'integration_ready': True, 'tasks': ids,
            'verified_artifacts': [p for r in results for p in r['verified_artifacts']],
            'scope': 'declared source integrity only; no automatic merge or visual acceptance'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    x = sub.add_parser('init'); x.add_argument('--plan', required=True); x.add_argument('--manifest', required=True)
    x = sub.add_parser('claim'); x.add_argument('--manifest', required=True); x.add_argument('--task', required=True)
    x = sub.add_parser('check'); x.add_argument('--manifest', required=True); x.add_argument('--receipt', required=True)
    x = sub.add_parser('check-all'); x.add_argument('--manifest', required=True); x.add_argument('--receipts', nargs='+', required=True)
    args = p.parse_args()
    try:
        result = init(args.plan, args.manifest) if args.cmd == 'init' else claim(args.manifest, args.task) if args.cmd == 'claim' else check_all(args.manifest, args.receipts) if args.cmd == 'check-all' else check(args.manifest, args.receipt)
        print(json.dumps(result, indent=2)); return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr); return 2


if __name__ == '__main__':
    sys.exit(main())
