#!/usr/bin/env python3
"""Offline checks for this frozen text benchmark; standard library only."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import math
import statistics
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parent

def digest(data):
    return hashlib.sha256(data).hexdigest()

def load(name):
    return json.loads((ROOT / name).read_text())

def rows(data):
    return [json.loads(line) for line in data.splitlines() if line]

def fp(case_id, output):
    return digest((case_id + '\n' + unicodedata.normalize('NFKC', output).strip()).encode())

def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-7), (a, b)

manifest = load('SHA256SUMS.json')
assert set(manifest) == {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.json'}
for name, expected in manifest.items():
    assert digest((ROOT / name).read_bytes()) == expected, name
for name, expected in load('corpus.sha256.json').items():
    assert digest((ROOT / name).read_bytes()) == expected, name
cases = {r['case_id']: r for r in rows((ROOT / 'cases.jsonl').read_bytes())}
assert len(cases) == 144
assert set(Counter(r['source_language'] + '_' + r['target_language'] for r in cases.values()).values()) == {24}
assert Counter(r['register'] for r in cases.values()) == {'formal': 72, 'informal': 72}
metrics = load('configuration-metrics.json')
assert len(metrics) == 40
assert Counter(m['status'] for m in metrics) == {'collected': 39, 'backend_failed': 1}
assert Counter(m['backend'] for m in metrics) == {'ollama': 15, 'llamacpp': 15, 'sglang': 10}
assert all(m['image_input_tested'] is False for m in metrics)
assert sum(m['quality_rank_status'] == 'complete_144_reviewed' for m in metrics) == 7
assert sum(m['quality_rank_status'] == 'excluded_incomplete_review' for m in metrics) == 32
assert sum(m['quality_rank_status'] == 'excluded_backend_failed' for m in metrics) == 1
audit = load('source-audit.json')
normalized = defaultdict(dict)
for r in rows((ROOT / 'outputs.jsonl').read_bytes()):
    assert r['case_id'] not in normalized[r['configuration']]
    normalized[r['configuration']][r['case_id']] = r
annotations = {a['fingerprint']: a for a in rows((ROOT / 'annotations.jsonl').read_bytes())}
unique = set()
with zipfile.ZipFile(ROOT / 'raw-evidence.zip') as z:
    assert not z.testzip()
    assert set(z.namelist()) == {v['archive_member'] for a in audit.values() for v in a['sources'].values()}
    for m in metrics:
        key = m['configuration']
        for entry in audit[key]['sources'].values():
            b = z.read(entry['archive_member'])
            assert len(b) == entry['bytes'] and digest(b) == entry['sha256']
        s = json.loads(z.read(key + '/summary.json'))
        assert s['status'] == m['status']
        if m['status'] != 'collected':
            assert m['cases'] == 0 and key not in normalized
            continue
        raw = z.read(key + '/outputs.jsonl')
        assert digest(raw) == m['output_sha256'] == (s.get('output_sha256') or s.get('outputs_sha256'))
        latest = {r['case_id']: r for r in rows(raw)}
        assert len(latest) == 144 and set(latest) == set(cases)
        assert set(normalized[key]) == set(cases)
        cond = json.loads(z.read(key + '/conditions.json'))
        assert cond == m['conditions'] and cond['download_active'] is False
        assert cond['dataset_sha256'] == digest((ROOT / 'cases.jsonl').read_bytes())
        for cid, r in latest.items():
            assert r['success'] and r['response'].strip()
            for field in ['source', 'reference', 'atomic_facts', 'register', 'source_language', 'target_language']:
                assert r[field] == cases[cid][field], (key, cid, field)
            for field, value in normalized[key][cid].items():
                if field != 'configuration':
                    assert r[field] == value, (key, cid, field)
            unique.add(fp(cid, r['response']))
        rates = [r['decode_tps'] for r in latest.values() if r.get('decode_tps')]
        latencies = [r['latency_seconds'] for r in latest.values()]
        close(statistics.mean(rates), m['mean_decode_tps'])
        close(statistics.median(latencies), m['median_latency_seconds'])
        close(sorted(latencies)[math.ceil(.95 * len(latencies)) - 1], m['p95_latency_seconds'])
        assert m['possible_truncation_cases'] == sum(bool(r.get('possible_truncation')) for r in latest.values())
        assert m['reviewed_cases'] == sum(fp(cid, r['response']) in annotations for cid, r in latest.items())
        mem = rows(z.read(key + '/memory.jsonl'))
        if m['memory_validity'] == 'invalid_collector_fallback':
            assert key.startswith('qwen2.5--14b-instruct-q4_K_M/')
            assert all(m[f] is None for f in ['peak_rss_gib', 'max_system_swap_gib', 'min_system_available_gib'])
            assert {r['rss_tree_bytes'] for r in mem} == {55853056}
            assert {r['system_swap_bytes'] for r in mem} == {0}
        else:
            close(max(r['rss_tree_bytes'] for r in mem) / 1024**3, m['peak_rss_gib'])
            close(max(r.get('swap_bytes', r.get('system_swap_bytes')) for r in mem) / 1024**3, m['max_system_swap_gib'])
            close(min(r['available_bytes'] for r in mem) / 1024**3, m['min_system_available_gib'])
for a in annotations.values():
    assert a['fingerprint'] in unique
    assert len(a['atomic_fact_scores']) == len(cases[a['case_id']]['atomic_facts'])
progress = load('progress.json')
assert sum(len(v) for v in normalized.values()) == progress['outputs'] == 5616
assert len(unique) == progress['unique_packets'] == 3948
assert len(annotations) == progress['reviewed_packets'] == 1584
assert len(unique - annotations.keys()) == progress['pending_packets'] == 2364
assert len(load('ranking.json')['rankings']) == 7
assert len(load('ranking.json')['pending_review']) == 32
assert all(m['reviewed_cases'] == 144 for m in metrics if m['quality_rank_status'] == 'complete_144_reviewed')
assert sum(m['memory_validity'] == 'invalid_collector_fallback' for m in metrics) == 2
assert all(m['possible_truncation_cases'] == 144 for m in metrics if 'TranslateGemma' in m['model'])
print('Verified: file hashes, 40 statuses, 39 complete configurations, 5,616 outputs, timings, memory scope, 2 invalidations, corpus, 1,584 reviews, 1,008 complete quality rows and 32 excluded partial configurations.')
