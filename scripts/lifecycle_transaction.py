"""Transaction engine used only through version_lifecycle's common entry point.
No browser/shell hooks. Callers collect real post-quarantine validation evidence.
"""
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from urllib.parse import urlsplit

import version_lifecycle as core

MAX_ENTRY_BYTES = 1024 * 1024


def overlaps(a, b):
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _entry_bytes(p):
    if not p.exists():
        return None
    core.snapshot(p)  # Reject symlinks, hardlinks and special files.
    if not p.is_file() or p.stat().st_size > MAX_ENTRY_BYTES:
        raise ValueError('retirement entry must be a small regular file')
    return p.read_bytes()


def retirement_plan(root, data, units):
    """Explicit HTML replacement / JSON lifecycle annotation; never run code."""
    specs = data.get('retirements', [])
    if not isinstance(specs, list):
        raise ValueError('retirements must be a list')
    rows, seen = [], set()
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError('invalid retirement entry')
        rel = spec['path'];p = core.safe(root, rel)
        ids = spec.get('unit_ids')
        if (str(p) in seen or not isinstance(ids, list) or not ids or
                len(ids) != len(set(ids)) or any(uid not in units for uid in ids)):
            raise ValueError('duplicate entry or invalid retirement unit_ids')
        seen.add(str(p))
        if not p.parent.is_dir():
            raise ValueError('retirement parent must already exist')
        for u in units.values():
            if overlaps(p, core.safe(root, u['path'])):
                raise ValueError('retirement entry overlaps registered unit')
        for rel_guard in data.get('protected_paths', []):
            if overlaps(p, core.safe(root, rel_guard)):
                raise ValueError('retirement entry overlaps protected path')
        if any(units[uid]['status'] not in core.ELIGIBLE for uid in ids):
            raise ValueError('retirement may only target retired/cache units')
        raw = _entry_bytes(p)
        kind = spec.get('kind')
        if kind == 'html':
            url = spec.get('current_url', '')
            if not isinstance(url, str):raise ValueError('current_url must be text')
            try:
                parsed = urlsplit(url)
                valid = (url.startswith('/') and not url.startswith('//') and not parsed.netloc) or (parsed.scheme in ('http', 'https') and bool(parsed.netloc))
                if not valid or any(c in url for c in '\r\n\\'):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('current_url must be explicit HTTP(S) or root-local URL')
            if p.suffix.lower() not in ('.html', '.htm'):
                raise ValueError('HTML retirement requires HTML file')
            body = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>旧试验已退役</title><body data-retired="true">'
                    '<h1>旧试验已退役</h1><p>这个历史模型已退役，此页不再加载模型。'
                    '原始资料与审查记录按项目保留策略保存。</p><p>'
                    '<a href="' + html.escape(url, quote=True) + '">查看当前版本</a></p></body></html>')
            new = body.encode()
        elif kind == 'json':
            if p.suffix.lower() != '.json':
                raise ValueError('JSON retirement requires JSON file')
            old = json.loads(raw) if raw is not None else {}
            if not isinstance(old, dict):
                raise ValueError('JSON retirement requires object')
            old['_lifecycle'] = {'status': 'retired', 'unit_ids': ids,
                                 'model_available': False, 'historical_record_only': True,
                                 'reverification_requires_restoration_or_reconstruction': True}
            new = core.encoded(old)
        else:
            raise ValueError('unsupported retirement kind')
        if len(new) > MAX_ENTRY_BYTES:
            raise ValueError('retirement replacement too large')
        rows.append({'path': rel, 'unit_ids': ids, 'kind': kind,
                     'before': core.snapshot(p) if raw is not None else None,
                     'after_sha256': core.digest(new),
                     'after_base64': base64.b64encode(new).decode()})
    return rows


def _seal(obj, key):
    result = dict(obj);result[key] = core.digest(core.encoded(obj));return result


def _verify_seal(obj, key):
    copy = dict(obj);saved = copy.pop(key, None)
    if not saved or core.digest(core.encoded(copy)) != saved:
        raise ValueError('modified/corrupt ' + key)


def _read_json(p):
    return json.loads(p.read_text())


def _load(root, transaction):
    rel = Path(transaction)
    if (len(rel.parts) != 2 or rel.parts[0] != '.model-quarantine' or
            not re.fullmatch('[0-9a-f]{64}', rel.parts[1])):
        raise ValueError('invalid transaction')
    tx = root / rel
    if tx.is_symlink() or tx.parent.is_symlink() or not tx.is_dir():
        raise ValueError('invalid quarantine directory')
    p = tx / 'journal.json'
    if p.is_symlink() or not p.is_file():
        raise ValueError('invalid journal')
    j = _read_json(p)
    if j.get('version') != 2:
        raise ValueError('new commands require version 2 transaction; legacy restore remains available')
    _verify_seal(j, 'transaction_sha256')
    if j['root'] != str(root) or j['plan_sha256'] != rel.parts[1]:
        raise ValueError('journal identity mismatch')
    for i, e in enumerate(j['entries']):
        core.safe(root, e['path'])
        if e['slot'] != str(i):raise ValueError('invalid payload slot')
    return tx, j


def _append(tx, value):
    with (tx / 'operations.jsonl').open('ab') as stream:
        stream.write(core.encoded(value) + b'\n');stream.flush();os.fsync(stream.fileno())


def _replace(p, data, mode, mtime_ns=None, atime_ns=None):
    """Atomic file replacement, no executable callbacks or parent creation."""
    fd, name = tempfile.mkstemp(prefix='.lifecycle-', dir=p.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        if mtime_ns is not None:
            os.utime(tmp, ns=(atime_ns if atime_ns is not None else mtime_ns, mtime_ns))
        tmp.replace(p)
    finally:
        if tmp.exists():tmp.unlink()


def quarantine(root, plan_file, approval):
    root = Path(root).resolve();saved = _read_json(Path(plan_file))
    _verify_seal(saved, 'plan_sha256')
    if approval != saved['plan_sha256']:
        raise ValueError('explicit approval must match plan hash')
    with core.lock(root):
        fresh = core.plan(root, saved['ledger'])
        if fresh != saved:
            raise ValueError('stale or edited plan; regenerate and review')
        selected = [r for r in fresh['units'] if r['eligible']]
        if not selected:raise ValueError('no eligible units')
        selected_ids = {r['id'] for r in selected}
        patches = fresh.get('retirements', [])
        if any(not set(p['unit_ids']).issubset(selected_ids) for p in patches):
            raise ValueError('retirement refers to protected/ineligible unit')
        container = root / '.model-quarantine'
        if container.is_symlink():raise ValueError('quarantine symlink')
        container.mkdir(exist_ok=True);tx = container / approval;tx.mkdir()
        if tx.stat().st_dev != root.stat().st_dev:raise ValueError('quarantine must use same filesystem')
        journal_patches = []
        for patch in patches:
            p = core.safe(root, patch['path']);raw = _entry_bytes(p)
            s = p.stat() if raw is not None else None
            if (core.snapshot(p) if raw is not None else None) != patch['before']:
                raise ValueError('entry changed before backup')
            journal_patches.append({**patch, 'before_base64': base64.b64encode(raw).decode() if raw is not None else None,
                                    'before_mode': stat.S_IMODE(s.st_mode) if s else None,
                                    'before_mtime_ns': s.st_mtime_ns if s else None,
                                    'before_atime_ns': s.st_atime_ns if s else None})
        j = _seal({'version': 2, 'root': str(root), 'plan_sha256': approval,
                   'ledger': fresh['ledger'], 'ledger_sha256': fresh['ledger_sha256'],
                   'scan_files': fresh['scan_files'], 'guards': fresh.get('guards', []),
                   'required_checks': fresh.get('required_checks', []),
                   'entries': [{**r, 'slot': str(i)} for i, r in enumerate(selected)],
                   'retirements': journal_patches}, 'transaction_sha256')
        core.write_new(tx / 'journal.json', j)  # All move + entry restoration intents durable first.
        for e in j['entries']:
            src = core.safe(root, e['path'])
            if core.snapshot(src) != e['snapshot']:raise ValueError('concurrent change; restore partial transaction')
            if src.stat().st_dev != tx.stat().st_dev:raise ValueError('cross-filesystem move refused')
            src.rename(tx / e['slot']);_append(tx, {'moved': e['path']})
        for patch in j['retirements']:
            p = core.safe(root, patch['path']);raw = _entry_bytes(p)
            if (core.snapshot(p) if raw is not None else None) != patch['before']:
                raise ValueError('entry concurrently changed; restore partial transaction')
            _replace(p, base64.b64decode(patch['after_base64']), patch['before_mode'] if raw is not None else 0o644)
            _append(tx, {'retired': patch['path']})
        return {'transaction': str(tx.relative_to(root)), 'transaction_sha256': j['transaction_sha256'],
                'moved': len(selected), 'retired_entries': len(patches),
                'quarantine_bytes': fresh['quarantine_bytes'], 'reclaimed_bytes': 0,
                'next': 'Collect actual post-quarantine checks, then restore or request purge-plan.'}


def restore(root, transaction):
    root = Path(root).resolve()
    with core.lock(root):
        tx, j = _load(root, transaction)
        if (tx / 'purge-started.json').exists():
            raise ValueError('permanent deletion started; complete restoration is no longer available')
        if (tx / 'restored.json').exists():return {'restored': 0, 'restored_entries': 0, 'reclaimed_bytes': 0}
        # Preflight ALL content and entries before restoring anything.
        for e in j['entries']:
            src = tx / e['slot'];dest = core.safe(root, e['path'])
            if src.exists() or src.is_symlink():
                if dest.exists() or dest.is_symlink():raise ValueError('restore destination occupied')
                if core.snapshot(src) != e['snapshot']:raise ValueError('quarantined content changed')
                # Avoid creating untracked parents; ordinary quarantine leaves parents in place.
                if not dest.parent.is_dir():raise ValueError('restore parent missing')
            elif not dest.exists() or core.snapshot(dest) != e['snapshot']:
                raise ValueError('missing/changed transaction content')
        entry_states = []
        for patch in j['retirements']:
            p = core.safe(root, patch['path']);raw = _entry_bytes(p)
            before = base64.b64decode(patch['before_base64']) if patch['before_base64'] is not None else None
            after = base64.b64decode(patch['after_base64'])
            if core.digest(after) != patch['after_sha256']:raise ValueError('corrupt entry backup')
            if raw == before:
                entry_states.append(False)
            elif raw == after:
                entry_states.append(True)
            else:raise ValueError('retired entry changed; refuse to overwrite new work')
        restored = entries = 0
        for e in j['entries']:
            src = tx / e['slot']
            if src.exists():
                src.rename(core.safe(root, e['path']));restored += 1;_append(tx, {'restored': e['path']})
        for patch, changed in zip(j['retirements'], entry_states):
            if not changed:continue
            p = core.safe(root, patch['path'])
            if patch['before_base64'] is None:p.unlink()
            else:_replace(p, base64.b64decode(patch['before_base64']), patch['before_mode'], patch['before_mtime_ns'], patch['before_atime_ns'])
            entries += 1;_append(tx, {'restored_entry': patch['path']})
        core.write_new(tx / 'restored.json', {'transaction_sha256': j['transaction_sha256'], 'status': 'restored'})
        return {'restored': restored, 'restored_entries': entries, 'reclaimed_bytes': 0}


def _guards(root, j):
    ledger = Path(j['ledger'])
    if not ledger.is_file() or core.digest(ledger.read_bytes()) != j['ledger_sha256']:
        raise ValueError('ledger changed since quarantine; re-audit, do not purge')
    replaced = {p['path'] for p in j['retirements']}
    for item in j['scan_files']:
        if item['path'] in replaced:continue
        p = core.safe(root, item['path'])
        if not p.is_file() or core.digest(p.read_bytes()) != item['sha256']:
            raise ValueError('reference/evidence changed since quarantine')
    for guard in j['guards']:
        if core.snapshot(core.safe(root, guard['path'])) != guard['snapshot']:
            raise ValueError('protected resource changed since quarantine')
    for patch in j['retirements']:
        raw = _entry_bytes(core.safe(root, patch['path']))
        if raw is None or core.digest(raw) != patch['after_sha256']:
            raise ValueError('retirement not complete or entry changed')


def _report(root, tx, j, report_file):
    p = Path(report_file).resolve()
    if p.is_relative_to(tx):raise ValueError('validation report must be outside transaction')
    raw = p.read_bytes();report = json.loads(raw)
    if report.get('version') != 1 or report.get('transaction_sha256') != j['transaction_sha256'] or report.get('phase') != 'post-quarantine':
        raise ValueError('validation report must bind this post-quarantine transaction')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:raise ValueError('missing validation checks')
    ids = [c.get('id') for c in checks]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError('invalid/duplicate validation check IDs')
    if not set(j['required_checks']).issubset(ids):raise ValueError('missing required validation check')
    evidence = []
    for check in checks:
        if check.get('passed') is not True:raise ValueError('validation check failed')
        item = check.get('evidence', {});ep = core.safe(root, item['path'])
        if ep == p:raise ValueError('self-referencing evidence')
        if not ep.is_file() or core.digest(ep.read_bytes()) != item.get('sha256'):
            raise ValueError('stale validation evidence')
        evidence.append({'path': item['path'], 'sha256': item['sha256']})
    return {'path': str(p), 'sha256': core.digest(raw), 'evidence': evidence}


def _manifest(p):
    rows = []
    for f in sorted(p.rglob('*')) if p.is_dir() else [p]:
        if f.is_symlink():raise ValueError('payload symlink')
        s = f.lstat();rel = str(f.relative_to(p)) if f != p else '.'
        if stat.S_ISDIR(s.st_mode):rows.append({'path': rel, 'kind': 'directory'})
        elif stat.S_ISREG(s.st_mode):rows.append({'path': rel, 'kind': 'file', 'snapshot': core.snapshot(f)})
        else:raise ValueError('special payload file')
    return rows


def purge_plan(root, transaction, report_file):
    root = Path(root).resolve()
    with core.lock(root):
        tx, j = _load(root, transaction)
        if (tx / 'restored.json').exists() or (tx / 'purge-started.json').exists():
            raise ValueError('transaction restored or purge already started')
        _guards(root, j);report = _report(root, tx, j, report_file)
        payloads = []
        for e in j['entries']:
            p = tx / e['slot']
            if core.safe(root, e['path']).exists():raise ValueError('original path occupied; do not purge')
            if core.snapshot(p) != e['snapshot']:raise ValueError('missing/changed quarantined payload')
            payloads.append({'slot': e['slot'], 'original_path': e['path'], 'snapshot': e['snapshot'],
                             'is_directory': p.is_dir(), 'files': _manifest(p)})
        return _seal({'version': 1, 'root': str(root), 'transaction': str(tx.relative_to(root)),
                      'transaction_sha256': j['transaction_sha256'], 'validation_report': report,
                      'payloads': payloads, 'logical_bytes': sum(p['snapshot']['bytes'] for p in payloads),
                      'allocated_bytes': sum(p['snapshot']['allocated_bytes'] for p in payloads),
                      'reclaimed_bytes': 0, 'irreversible': True,
                      'limits': 'Only listed quarantine payloads; entry backups and audit journal remain. Full restore unavailable after purge starts.'}, 'purge_plan_sha256')


def _payload_path(tx, slot, rel):
    p = tx / slot
    if rel == '.':return p
    parts = Path(rel)
    if parts.is_absolute() or '..' in parts.parts or not parts.parts:raise ValueError('unsafe purge path')
    for part in parts.parts:
        p = p / part
        if p.is_symlink():raise ValueError('purge symlink')
    return p


def purge(root, plan_file, approval):
    root = Path(root).resolve();saved = _read_json(Path(plan_file));_verify_seal(saved, 'purge_plan_sha256')
    if approval != saved['purge_plan_sha256']:raise ValueError('permanent-delete approval must match purge plan')
    with core.lock(root):
        tx, j = _load(root, saved['transaction'])
        if saved['root'] != str(root) or saved['transaction_sha256'] != j['transaction_sha256']:
            raise ValueError('purge transaction mismatch')
        if (tx / 'restored.json').exists():raise ValueError('restored transaction cannot be purged')
        # Bind exactly the journal units even during interrupted purge resume.
        if [(p['slot'], p['original_path'], p['snapshot']) for p in saved['payloads']] != [(e['slot'], e['path'], e['snapshot']) for e in j['entries']]:
            raise ValueError('purge scope mismatch')
        _guards(root, j)
        report = _report(root, tx, j, saved['validation_report']['path'])
        if report != saved['validation_report']:raise ValueError('validation report changed')
        started = tx / 'purge-started.json'
        resume = started.exists()
        if resume:
            record = _read_json(started)
            if record.get('plan') != saved:raise ValueError('different plan after purge started')
        files, dirs, missing = [], [], 0
        for payload in saved['payloads']:
            p = tx / payload['slot']
            if p.is_symlink():raise ValueError('payload symlink')
            if core.safe(root, payload['original_path']).exists():raise ValueError('original path occupied')
            if not resume and core.snapshot(p) != payload['snapshot']:raise ValueError('payload changed')
            expected = {row['path'] for row in payload['files']}
            actual = {str(f.relative_to(p)) for f in p.rglob('*')} if p.is_dir() else ({'.'} if p.exists() else set())
            if not actual.issubset(expected):raise ValueError('unexpected payload content')
            for row in payload['files']:
                f = _payload_path(tx, payload['slot'], row['path'])
                if row['kind'] == 'file':
                    if not f.exists():
                        if not resume:raise ValueError('missing payload file')
                        missing += 1;continue
                    if core.snapshot(f) != row['snapshot']:raise ValueError('payload file changed')
                    files.append(f)
                elif row['kind'] == 'directory':
                    if f.exists() and not f.is_dir():raise ValueError('payload directory replaced')
                    if f.exists():dirs.append(f)
                else:raise ValueError('invalid purge manifest')
            if payload['is_directory'] and p.exists():dirs.append(p)
        # Irreversible intent persisted before the first unlink; restore refuses from here.
        before_free = shutil.disk_usage(root).free;allocated = sum(core.snapshot(p)['allocated_bytes'] for p in files)
        if not resume:core.write_new(started, {'plan': saved, 'available_bytes': before_free})
        count = 0
        for p in files:
            p.unlink();count += 1;_append(tx, {'permanently_deleted': str(p.relative_to(tx))})
        for p in sorted(set(dirs), key=lambda f: len(f.parts), reverse=True):p.rmdir()
        after_free = shutil.disk_usage(root).free
        result = {'transaction': str(tx.relative_to(root)), 'transaction_sha256': j['transaction_sha256'],
                  'status': 'purged', 'deleted_files_this_run': count, 'previously_missing_files': missing,
                  'logical_bytes': saved['logical_bytes'], 'allocated_bytes_unlinked_this_run': allocated,
                  'available_bytes_before': before_free,
                  'available_bytes_after': after_free,
                  'observed_available_delta_bytes': after_free-before_free,
                  'full_restoration_available': False,
                  'limits': 'Observed volume delta includes background activity and snapshot/clone accounting; not exact reclaim attribution.'}
        if not (tx / 'purged.json').exists():core.write_new(tx / 'purged.json', result)
        return result
