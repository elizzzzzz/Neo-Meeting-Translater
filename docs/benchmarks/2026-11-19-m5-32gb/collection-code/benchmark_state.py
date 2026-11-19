"""Recover durable benchmark evidence and merge independent driver snapshots."""
import copy
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))

def now():
    return datetime.now(TZ).isoformat(timespec='seconds')

def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default

def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def recover_entry(root, catalog, previous=None):
    e = dict(copy.deepcopy(previous or {}), **catalog)
    e.setdefault('id', e['model'].replace(':', '--'))
    e.setdefault('phase', 'queued')
    e.setdefault('download', {})
    e.setdefault('test', {})
    e.setdefault('backends', {})
    e.setdefault('review_status', 'not_reviewable')
    e.setdefault('cleanup_status', 'not_needed')
    out = Path(root) / 'results' / e['id']
    for backend in catalog.get('platforms', ['ollama', 'llamacpp']):
        summary = read(out / backend / 'summary.json')
        if summary:
            e['backends'][backend] = summary
    checkpoint = read(out / 'checkpoint.json')
    if checkpoint:
        e['native_capabilities'] = checkpoint.get('capabilities', [])
        blob = checkpoint.get('blob')
        if blob and Path(blob).is_file():
            e['weights_blob'] = blob
    if read(out / 'cleanup.json').get('removed_from_isolated_store'):
        e['cleanup_status'] = 'verified'
    if any(b.get('status') == 'collected' for b in e['backends'].values()):
        e['phase'] = e['review_status'] = 'scoring_pending'
    elif e['backends']:
        e['phase'] = 'backend_failed'
    return e

def recover_gguf(root):
    root = Path(root)
    results = root / 'results'
    previous = {}
    candidates = sorted(results.glob('dashboard-state*.json'), key=lambda p:p.stat().st_mtime)
    candidates += [results / 'gguf-state.json']
    base = {}
    for path in candidates:
        d = read(path)
        if any(e.get('id') for e in d.get('queue', [])):
            base.update({k:v for k,v in d.items() if k != 'queue'})
        for e in d.get('queue', []):
            if e.get('id') and e.get('format') != 'mlx':
                previous[e['model']] = e
    base['queue'] = [recover_entry(root, q, previous.get(q['model']))
                     for q in read(root / 'data/queue.json', [])]
    return base

def mlx_row(e):
    status = e.get('status', 'queued')
    if status == 'cleaning' and e.get('cleanup') == 'verified':
        status = 'collected' if e.get('summary') else 'backend_failed'
    summary = dict(e.get('summary', {}), status=status,
                   completed_cases=e.get('completed_cases', 0), successes=e.get('successes', 0))
    for key in ('mean_decode_tps','median_latency_seconds','peak_rss_gib'):
        if e.get(key) is not None:summary[key]=e[key]
    return dict(model=e['repo'], quant=e['quant'], format='mlx', platforms=['sglang'],
                phase=status, download=e.get('download', {}), test=summary,
                backends={'sglang':summary}, mlx_status=status,
                review_status='scoring_pending' if status=='collected' else 'not_reviewable',
                cleanup_status=e.get('cleanup', 'not_needed'), error=e.get('error', ''))

def merge_states(gguf, mlx):
    d = copy.deepcopy(gguf)
    d['queue'] = list(d.get('queue', [])) + [mlx_row(e) for e in mlx.get('queue', [])]
    if mlx.get('updated_at', '') > gguf.get('updated_at', ''):
        for key in ('phase', 'current_model', 'current_backend', 'activity', 'pid',
                    'updated_at', 'paused', 'download_paused', 'driver_error'):
            if key in mlx:
                d[key] = mlx[key]
    d['events'] = sorted(gguf.get('events', []) + mlx.get('events', []),
                         key=lambda e:e.get('at', ''))[-80:]
    d['configuration_count'] = sum(len(e.get('platforms', ['ollama', 'llamacpp'])) for e in d['queue'])
    d['collected_count'] = sum(b.get('status')=='collected' for e in d['queue']
                               for b in e.get('backends', {}).values())
    pid = d.get('pid')
    try:
        if not pid:
            raise ProcessLookupError()
        os.kill(pid, 0)
        age = (datetime.now(TZ)-datetime.fromisoformat(d['updated_at'])).total_seconds()
        d['runner_alive'] = age < 30
    except (OSError, ValueError, KeyError):
        d['runner_alive'] = False
    return d

def snapshot(root):
    root = Path(root)
    gguf = read(root / 'results/gguf-state.json') or recover_gguf(root)
    d = merge_states(gguf, read(root / 'results/sglang-state.json'))
    d.setdefault('device', 'Apple M5 MacBook Air')
    d.setdefault('memory', '32 GiB unified memory')
    d['dashboard_at'] = now()
    d['review_progress'] = read(root/'review/progress.json')
    try:
        import psutil
        import shutil
        d['system'] = dict(available_gib=psutil.virtual_memory().available/1024**3,
                           swap_gib=psutil.swap_memory().used/1024**3)
        d['free_disk_bytes'] = shutil.disk_usage(root).free
    except ImportError:
        pass
    return d
