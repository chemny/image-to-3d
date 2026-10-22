"""Explicit version ledger, dry-run plans, transactional retirement, restoration and authorized purge.

The ledger is a projection of existing project/handoff records, not approval.
Inventory heuristics NEVER make an artifact eligible for cleanup.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import unquote

PROTECTED = {'active', 'working', 'accepted', 'rollback', 'source', 'evidence', 'unknown'}
ELIGIBLE = {'retired', 'cache'}
RESERVED = {'.model-quarantine', '.model-lifecycle.lock'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2).encode()


def write_new(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded(obj))
        stream.flush(); os.fsync(stream.fileno())


def safe(root, rel):
    rel = Path(rel)
    if rel.is_absolute() or not rel.parts or '..' in rel.parts or rel.parts[0] in RESERVED:
        raise ValueError('unsafe/reserved path: ' + str(rel))
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlink not allowed: ' + str(current))
    if current.resolve() == root or not current.resolve().is_relative_to(root):
        raise ValueError('path outside root')
    return current


def snapshot(path):
    """Bind names, bytes and metadata; reject links and special files."""
    path = Path(path)
    if path.is_symlink() or not path.exists():
        raise ValueError('missing or symlink: ' + str(path))
    files = sorted(path.rglob('*')) if path.is_dir() else [path]
    rows, total, allocated = [], 0, 0
    for p in files:
        s = p.lstat()
        if stat.S_ISLNK(s.st_mode) or not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
            raise ValueError('unsupported filesystem entry: ' + str(p))
        if stat.S_ISREG(s.st_mode) and s.st_nlink != 1:
            raise ValueError('hardlinked file requires manual review: ' + str(p))
        name = str(p.relative_to(path)) if p != path else '.'
        row = [name, s.st_mode, s.st_mtime_ns, s.st_size if p.is_file() else 0]
        if p.is_file():
            h = hashlib.sha256()
            with p.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            if p.stat().st_mtime_ns != s.st_mtime_ns or p.stat().st_size != s.st_size:
                raise ValueError('file changed during scan: ' + str(p))
            row.append(h.hexdigest())
            total += s.st_size
            allocated += getattr(s, 'st_blocks', 0) * 512
        rows.append(row)
    return {'sha256': digest(encoded(rows)), 'bytes': total, 'allocated_bytes': allocated}


def load_ledger(root, ledger):
    ledger = Path(ledger).resolve()
    data = json.loads(ledger.read_text())
    if data.get('version') != 1 or not isinstance(data.get('units'), list):
        raise ValueError('invalid ledger')
    units, paths = {}, []
    for unit in data['units']:
        uid = unit.get('id')
        if not isinstance(uid, str) or not uid or uid in units:
            raise ValueError('invalid/duplicate unit ID')
        if unit.get('status') not in PROTECTED | ELIGIBLE:
            raise ValueError('invalid status')
        p = safe(root, unit['path'])
        if p == ledger or ledger.is_relative_to(p):
            raise ValueError('ledger inside cleanup unit')
        if not p.exists():
            raise ValueError('missing unit: ' + uid)
        for other in paths:
            if p == other or p.is_relative_to(other) or other.is_relative_to(p):
                raise ValueError('overlapping units')
        if not isinstance(unit.get('dependencies', []), list):
            raise ValueError('dependencies must be a list')
        paths.append(p)
        units[uid] = unit
    for unit in units.values():
        if any(dep not in units for dep in unit.get('dependencies', [])):
            raise ValueError('unknown dependency')
    return data, units


def plan(root, ledger):
    root = Path(root).resolve()
    data, units = load_ledger(root, ledger)
    if data.get('coverage_complete') is True and not data.get('scan_files'):
        raise ValueError('verified coverage requires scan_files')
    from lifecycle_transaction import retirement_plan
    retirements = retirement_plan(root, data, units)
    required_checks = data.get('required_checks', ['current_case', 'protected_state'])
    if (not isinstance(required_checks, list) or not required_checks or
            any(not isinstance(c, str) or not c for c in required_checks) or
            len(set(required_checks)) != len(required_checks)):
        raise ValueError('invalid required_checks')
    scans, texts = [], []
    for rel in data.get('scan_files', []):
        p = safe(root, rel)
        if not p.is_file():
            raise ValueError('scan file missing/not a file')
        raw = p.read_bytes()
        texts.append((rel, unquote(raw.decode('utf-8'))))
        scans.append({'path': rel, 'sha256': digest(raw)})
    protected = {uid for uid, u in units.items() if u['status'] in PROTECTED}
    reasons = {uid: ['status:' + units[uid]['status']] for uid in protected}
    for uid, unit in units.items():
        rel = unit['path'].rstrip('/')
        if any(rel in text and not any(p['path'] == src and uid in p['unit_ids'] for p in retirements) for src, text in texts):
            protected.add(uid)
            reasons.setdefault(uid, []).append('reference in scan_files')
        for p in data.get('protected_paths', []):
            a, b = safe(root, p), safe(root, rel)
            if a == b or a.is_relative_to(b) or b.is_relative_to(a):
                protected.add(uid)
                reasons.setdefault(uid, []).append('protected path')
        for scan in data.get('scan_files', []):
            a, b = safe(root, scan), safe(root, rel)
            if a == b or a.is_relative_to(b):
                protected.add(uid)
                reasons.setdefault(uid, []).append('scan source')
    # Mark reachable dependencies, including cycles; retired dependencies may be live.
    queue = list(protected)
    while queue:
        uid = queue.pop()
        for dep in units[uid].get('dependencies', []):
            if dep not in protected:
                protected.add(dep)
                reasons.setdefault(dep, []).append('dependency of ' + uid)
                queue.append(dep)
    rows = []
    for uid, unit in units.items():
        why = reasons.get(uid, []).copy()
        if data.get('coverage_complete') is not True:
            why.append('reference coverage not verified')
        if unit['status'] in ELIGIBLE:
            evidence = unit.get('retirement_evidence')
            if not unit.get('reason') or not isinstance(evidence, dict):
                why.append('missing retirement/rebuild evidence')
            else:
                ep = safe(root, evidence['path'])
                raw = ep.read_bytes()
                if digest(raw) != evidence.get('sha256'):
                    raise ValueError('stale retirement evidence')
                scans.append({'path': evidence['path'], 'sha256': digest(raw)})
                # Never move a unit containing the record authorizing its move.
                target = safe(root, unit['path'])
                if ep == target or ep.is_relative_to(target):
                    why.append('retirement evidence inside unit')
        rows.append({'id': uid, 'path': unit['path'], 'status': unit['status'],
                     'eligible': not why and unit['status'] in ELIGIBLE,
                     'reasons': why or [unit.get('reason', '')],
                     'snapshot': snapshot(safe(root, unit['path']))})
    # Evidence for any unit also protects other units containing that evidence.
    for row in rows:
        p = safe(root, row['path'])
        if any(safe(root, s['path']) == p or safe(root, s['path']).is_relative_to(p) for s in scans):
            row['eligible'] = False
            if 'record dependency' not in row['reasons']:
                row['reasons'].append('record dependency')
    protected_rows = {r['id'] for r in rows if not r['eligible']}
    queue = list(protected_rows)
    while queue:
        uid = queue.pop()
        for dep in units[uid].get('dependencies', []):
            if dep not in protected_rows:
                protected_rows.add(dep); queue.append(dep)
                row = next(r for r in rows if r['id'] == dep)
                row['eligible'] = False
                row['reasons'].append('dependency of retained ' + uid)
    guards = []
    guard_paths = set(data.get('protected_paths', [])) | {r['path'] for r in rows if not r['eligible']}
    for rel_guard in sorted(guard_paths):
        guards.append({'path': rel_guard, 'snapshot': snapshot(safe(root, rel_guard))})
    result = {'version': 1, 'root': str(root), 'ledger': str(Path(ledger).resolve()),
              'ledger_sha256': digest(Path(ledger).read_bytes()),
              'scan_files': scans, 'units': rows, 'retirements': retirements,
              'required_checks': required_checks, 'guards': guards,
              'quarantine_bytes': sum(r['snapshot']['bytes'] for r in rows if r['eligible']),
              'reclaimed_bytes': 0,
              'limits': 'Explicit dependency graph and declared scans only; dynamic/unknown references require review. Freeze external builds before applying.'}
    result['plan_sha256'] = digest(encoded(result))
    return result


@contextlib.contextmanager
def lock(root):
    p = root / '.model-lifecycle.lock'
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        p.unlink()


def quarantine(root, plan_file, approval):
    from lifecycle_transaction import quarantine as execute
    return execute(root, plan_file, approval)


def restore(root, transaction):
    root = Path(root).resolve()
    rel = Path(transaction)
    if len(rel.parts) != 2 or rel.parts[0] != '.model-quarantine' or not re.fullmatch('[0-9a-f]{64}', rel.parts[1]):
        raise ValueError('invalid transaction')
    tx = root / rel
    if tx.is_symlink() or tx.parent.is_symlink() or (tx / 'journal.json').is_symlink():
        raise ValueError('quarantine symlink')
    journal = json.loads((tx / 'journal.json').read_text())
    if journal.get('version') == 2:
        from lifecycle_transaction import restore as execute
        return execute(root, transaction)
    return _legacy_restore(root, transaction)


def purge_plan(root, transaction, report_file):
    from lifecycle_transaction import purge_plan as execute
    return execute(root, transaction, report_file)


def purge(root, plan_file, approval):
    from lifecycle_transaction import purge as execute
    return execute(root, plan_file, approval)


def _legacy_restore(root, transaction):
    root = Path(root).resolve()
    rel = Path(transaction)
    if len(rel.parts) != 2 or rel.parts[0] != '.model-quarantine' or not re.fullmatch('[0-9a-f]{64}', rel.parts[1]):
        raise ValueError('invalid transaction')
    tx = root / rel
    if tx.is_symlink() or tx.parent.is_symlink():
        raise ValueError('quarantine symlink')
    with lock(root):
        jp = tx / 'journal.json'
        if jp.is_symlink():
            raise ValueError('journal symlink')
        journal = json.loads(jp.read_text())
        if journal.get('root') != str(root) or journal.get('plan_sha256') != rel.parts[1]:
            raise ValueError('journal identity mismatch')
        entries = journal['entries']
        # Preflight all before restoring any; no overwriting active/recreated files.
        for i, entry in enumerate(entries):
            if entry.get('slot') != str(i):
                raise ValueError('invalid journal slot')
            dest = safe(root, entry['path'])
            src = tx / str(i)
            if src.exists() or src.is_symlink():
                if dest.exists() or dest.is_symlink():
                    raise ValueError('restore destination occupied')
                if snapshot(src) != entry['snapshot']:
                    raise ValueError('quarantined content changed')
            elif not dest.exists() or snapshot(dest) != entry['snapshot']:
                raise ValueError('missing/changed transaction content')
        count = 0
        for i, entry in enumerate(entries):
            src = tx / str(i)
            if src.exists():
                dest = safe(root, entry['path'])
                dest.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dest)
                count += 1
        return {'restored': count, 'reclaimed_bytes': 0}


def inventory(root, scan_files=()):
    """Read-only legacy discovery; references are hints, never deletion proof."""
    root = Path(root).resolve()
    rows, references, skipped = {}, set(), 0
    pattern = re.compile(r'(?:/)?outputs/([A-Za-z0-9_.-]+)')
    for folder in sorted(root.iterdir()):
        if folder.name in RESERVED:
            continue
        total = allocated = files = links = 0
        for base, dirs, names in os.walk(folder, followlinks=False) if folder.is_dir() and not folder.is_symlink() else []:
            links += sum((Path(base) / d).is_symlink() for d in dirs)
            dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
            for name in names:
                p = Path(base) / name
                if p.is_symlink():
                    links += 1
                    continue
                s = p.stat()
                if not stat.S_ISREG(s.st_mode):
                    continue
                total += s.st_size
                allocated += getattr(s, 'st_blocks', 0) * 512
                files += 1
        if folder.is_file():
            s = folder.stat(); total = s.st_size; allocated = getattr(s, 'st_blocks', 0) * 512; files = 1
        rows[folder.name] = {'path': folder.name, 'bytes': total, 'allocated_bytes': allocated,
                             'files': files, 'symlinks': links, 'eligible': False}
    for rel in scan_files:
        p = safe(root, rel)
        if p.stat().st_size > 4 * 1024 * 1024:
            skipped += 1
        else:
            references.update(pattern.findall(unquote(p.read_text())))
    for name, row in rows.items():
        row['status'] = 'referenced-review-required' if name in references else 'unknown-review-required'
    return {'version': 1, 'root': str(root), 'mode': 'inventory-only',
            'total_bytes': sum(r['bytes'] for r in rows.values()),
            'total_allocated_bytes': sum(r['allocated_bytes'] for r in rows.values()),
            'reclaimed_bytes': 0, 'eligible_bytes': 0, 'large_text_files_skipped': skipped,
            'limits': 'Static path hints, not complete dependencies or retirement evidence. No item is authorized for cleanup.',
            'units': sorted(rows.values(), key=lambda r: -r['bytes'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inventory', 'plan', 'quarantine', 'restore', 'purge-plan', 'purge'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--ledger')
    parser.add_argument('--scan-file', action='append', default=[])
    parser.add_argument('--plan')
    parser.add_argument('--approve-sha256')
    parser.add_argument('--transaction')
    parser.add_argument('--report', help='Actual post-quarantine check report for purge-plan')
    parser.add_argument('--out', required=True, help='New report file, never overwritten')
    args = parser.parse_args()
    # Refuse an already occupied output before side effects. The transaction
    # journal remains the recovery source if writing the final report fails.
    output = Path(args.out)
    if output.exists() or output.is_symlink():
        parser.error('output already exists')
    if args.command in {'plan', 'quarantine'}:
        ledger_path = args.ledger if args.command == 'plan' else json.loads(Path(args.plan).read_text())['ledger']
        output_data, output_units = load_ledger(Path(args.root).resolve(), ledger_path)
        for unit in output_units.values():
            target = safe(Path(args.root).resolve(), unit['path'])
            if output.resolve() == target or output.resolve().is_relative_to(target):
                parser.error('output must be outside registered units')
        output_guards = output_data.get('protected_paths', []) + [p['path'] for p in output_data.get('retirements', [])]
        for rel in output_guards:
            target = safe(Path(args.root).resolve(), rel)
            if output.resolve() == target or output.resolve().is_relative_to(target):
                parser.error('output must be outside protected/retirement entries')
    if args.command in {'restore', 'purge-plan', 'purge'}:
        transaction = args.transaction if args.command != 'purge' else json.loads(Path(args.plan).read_text())['transaction']
        transaction_path = Path(args.root).resolve() / transaction
        if output.resolve() == transaction_path or output.resolve().is_relative_to(transaction_path):
            parser.error('output must be outside transaction')
        root = Path(args.root).resolve()
        rel_tx = Path(transaction)
        if len(rel_tx.parts) != 2 or rel_tx.parts[0] != '.model-quarantine' or not re.fullmatch('[0-9a-f]{64}', rel_tx.parts[1]):
            parser.error('invalid transaction')
        if transaction_path.is_symlink() or transaction_path.parent.is_symlink() or (transaction_path / 'journal.json').is_symlink():
            parser.error('invalid transaction link')
        from lifecycle_transaction import _load
        tx, journal = _load(root, transaction) if args.command != 'restore' else (transaction_path, json.loads((transaction_path / 'journal.json').read_text()))
        output_targets = [e['path'] for e in journal['entries']] + [p['path'] for p in journal.get('retirements', [])] + [g['path'] for g in journal.get('guards', [])]
        for rel in output_targets:
            target = safe(root, rel)
            if output.resolve() == target or output.resolve().is_relative_to(target):
                parser.error('output must be outside transaction resource paths')
    if args.command == 'inventory':
        result = inventory(args.root, args.scan_file)
    elif args.command == 'plan':
        result = plan(args.root, args.ledger)
    elif args.command == 'quarantine':
        result = quarantine(args.root, args.plan, args.approve_sha256)
    elif args.command == 'restore':
        result = restore(args.root, args.transaction)
    elif args.command == 'purge-plan':
        result = purge_plan(args.root, args.transaction, args.report)
    else:
        result = purge(args.root, args.plan, args.approve_sha256)
    write_new(output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'units'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
