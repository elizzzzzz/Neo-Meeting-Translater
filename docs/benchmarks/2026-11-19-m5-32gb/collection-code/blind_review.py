#!/usr/bin/env python3
"""Evidence-backed, deduplicated review; model identities are hidden in show."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import unicodedata
from benchmark_state import atomic,read,now
ROOT=Path(__file__).resolve().parents[1]
REVIEW=ROOT/'review'
OLD=ROOT.parent/'translation-benchmark-2026-11-09'

def fp(case,text):return hashlib.sha256((case+'\n'+unicodedata.normalize('NFKC',text).strip()).encode()).hexdigest()
def cases():return {r['case_id']:r for r in map(json.loads,(ROOT/'data/cases.jsonl').read_text().splitlines())}
def configs():
    for p in sorted((ROOT/'results').glob('*/*/outputs.jsonl')):
        if p.parent.name in ('ollama','llamacpp'):yield p
    yield from sorted((ROOT/'results/sglang').glob('*/*/outputs.jsonl'))
def load_rows(p):
    rows={}
    for line in p.read_text().splitlines():
        r=json.loads(line);rows[r['case_id']]=r
    return rows

def prepare():
    REVIEW.mkdir(exist_ok=True);cs=cases();unique={};lookup=defaultdict(list);complete=[]
    old_packets=REVIEW/'packets.jsonl'
    old_ids={}
    if old_packets.exists():
        raw=old_packets.read_bytes();archive=REVIEW/'packet-archives';archive.mkdir(exist_ok=True)
        digest=hashlib.sha256(raw).hexdigest();(archive/(digest+'.jsonl')).write_bytes(raw)
        if (REVIEW/'identity-map.json').exists():
            (archive/(digest+'-identity-map.json')).write_bytes((REVIEW/'identity-map.json').read_bytes())
        old_ids={r['fingerprint']:r['packet_id'] for r in map(json.loads,raw.splitlines())}
    for p in configs():
        s=read(p.parent/'summary.json');rows=load_rows(p)
        if s.get('status')!='collected' or len(rows)!=144:continue
        digest=s.get('output_sha256') or s.get('outputs_sha256')
        if not digest or digest!=hashlib.sha256(p.read_bytes()).hexdigest():raise ValueError('Output checksum mismatch '+str(p))
        key=str(p.parent.relative_to(ROOT/'results'));complete.append(key)
        for cid,r in rows.items():
            c=cs[cid];text=r.get('response','');fingerprint=fp(cid,text)
            unique[fingerprint]=dict(fingerprint=fingerprint,case_id=cid,source_language=c['source_language'],target_language=c['target_language'],register=c['register'],source=c['source'],reference=c['reference'],atomic_facts=c['atomic_facts'],output=text,success=r.get('success',False))
            lookup[fingerprint].append(dict(configuration=key,case_id=cid))
    packets=list(unique.values());random.Random(20261116).shuffle(packets)
    next_id=max((int(pid[1:]) for pid in old_ids.values()),default=0)+1
    for p in packets:
        if p['fingerprint'] in old_ids:p['packet_id']=old_ids[p['fingerprint']]
        else:p['packet_id']=f'H{next_id:06d}';next_id+=1
    (REVIEW/'packets.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in packets))
    atomic(REVIEW/'identity-map.json',dict(configurations=complete,lookup=dict(lookup)))
    # Reuse a previous explicit review only when the entire case specification matches.
    oldcases={r['case_id']:r for r in map(json.loads,(OLD/'data/cases.jsonl').read_text().splitlines())}
    keys=('source_language','target_language','register','source','reference','atomic_facts')
    same={cid for cid,c in cs.items() if all(c.get(k)==oldcases.get(cid,{}).get(k) for k in keys)}
    prior={r['fingerprint']:r for r in map(json.loads,(REVIEW/'annotations.jsonl').read_text().splitlines())} if (REVIEW/'annotations.jsonl').exists() else {}
    reused=0
    for line in (OLD/'review/annotations.jsonl').read_text().splitlines():
        a=json.loads(line)
        if a['fingerprint'] in unique and a['fingerprint'] not in prior and a['case_id'] in same:
            a=dict(a,reused_from=str(OLD/'review/annotations.jsonl'),reused_at=now());prior[a['fingerprint']]=a;reused+=1
    (REVIEW/'annotations.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in prior.values()))
    atomic(REVIEW/'progress.json',dict(at=now(),configurations=len(complete),outputs=sum(map(len,lookup.values())),unique_packets=len(packets),reviewed_packets=len(set(prior)&set(unique)),reused_this_run=reused,pending_packets=len(set(unique)-set(prior))))
    print(json.dumps(read(REVIEW/'progress.json'),ensure_ascii=False))

def show(args):
    packets=list(map(json.loads,(REVIEW/'packets.jsonl').read_text().splitlines()))
    annotations={a['fingerprint'] for a in map(json.loads,(REVIEW/'annotations.jsonl').read_text().splitlines())}
    pending=[p for p in packets if p['fingerprint'] not in annotations]
    if args.case:pending=[p for p in pending if p['case_id']==args.case]
    if args.direction:pending=[p for p in pending if p['source_language']+'_'+p['target_language']==args.direction]
    grouped=defaultdict(list)
    for p in pending[:args.limit]:grouped[p['case_id']].append(p)
    for cid,ps in grouped.items():
        p=ps[0];print(json.dumps({k:p[k] for k in ('case_id','source','reference','atomic_facts')},ensure_ascii=False))
        for p in ps:print(json.dumps(dict(id=p['packet_id'],output=p['output']),ensure_ascii=False))

def add(path):
    grades=json.loads(Path(path).read_text());packets={p['packet_id']:p for p in map(json.loads,(REVIEW/'packets.jsonl').read_text().splitlines())}
    annotations={a['fingerprint']:a for a in map(json.loads,(REVIEW/'annotations.jsonl').read_text().splitlines())};batch=[]
    for pid,g in grades.items():
        p=packets[pid];a,t,f,r,facts,critical,note=g
        for v in (a,t,f,r):assert isinstance(v,(int,float)) and 0<=v<=5 and v*2==int(v*2)
        fs=[{'1':1,'h':.5,'0':0}[c] for c in facts];assert len(fs)==len(p['atomic_facts']),(pid,len(fs),len(p['atomic_facts']))
        assert isinstance(critical,bool)
        row=dict(fingerprint=p['fingerprint'],packet_id=pid,case_id=p['case_id'],adequacy=a,terminology=t,factual=f,register=r,atomic_fact_scores=fs,critical_error=critical,error_notes=[note] if note else [],reviewer='assistant_label_hidden_review',reviewed_at=now())
        if row['fingerprint'] in annotations:raise ValueError('Already reviewed '+pid)
        batch.append(row)
    with (REVIEW/'annotations.jsonl').open('a') as f:
        for a in batch:f.write(json.dumps(a,ensure_ascii=False)+'\n')
    print('Recorded explicit reviews:',len(batch))

def rank():
    annotations={a['fingerprint']:a for a in map(json.loads,(REVIEW/'annotations.jsonl').read_text().splitlines())}
    cs=cases();eligible=[];pending=[]
    for p in configs():
        s=read(p.parent/'summary.json');rows=load_rows(p)
        if s.get('status')!='collected' or len(rows)!=144:continue
        assert (s.get('output_sha256') or s.get('outputs_sha256'))==hashlib.sha256(p.read_bytes()).hexdigest()
        grades=[];missing=[];dirs=defaultdict(list)
        for cid,r in rows.items():
            a=annotations.get(fp(cid,r.get('response','')));c=cs[cid]
            if not a:missing.append(cid);continue
            assert len(a['atomic_fact_scores'])==len(c['atomic_facts'])
            score=10*a['adequacy']+4*a['terminology']+4*a['factual']+2*a['register']
            grades.append(dict(case_id=cid,quality=score,facts=sum(a['atomic_fact_scores']),count=len(a['atomic_fact_scores']),critical=a['critical_error'],register=c['register']))
            dirs[c['source_language']+'_'+c['target_language']].append((grades[-1],r))
        key=str(p.parent.relative_to(ROOT/'results'))
        if missing:pending.append(dict(configuration=key,reviewed=len(grades),unreviewed=len(missing)));continue
        ds={d:dict(quality=statistics.mean(g['quality'] for g,r in rs),source_chars_per_second=statistics.mean(len(cs[g['case_id']]['source'])/r['latency_seconds'] for g,r in rs if r.get('latency_seconds'))) for d,rs in dirs.items()}
        eligible.append(dict(configuration=key,quality=statistics.mean(d['quality'] for d in ds.values()),fact_accuracy=100*sum(g['facts'] for g in grades)/sum(g['count'] for g in grades),critical_error_cases=sum(g['critical'] for g in grades),effective_rate=statistics.mean(d['source_chars_per_second'] for d in ds.values()),stability=100*sum(r.get('success',False) for r in rows.values())/144,directions=ds,mean_decode_tps=s.get('mean_decode_tps'),peak_rss_gib=s.get('peak_rss_gib')))
    fastest=max((r['effective_rate'] for r in eligible),default=1)
    for r in eligible:r.update(speed_score=100*r['effective_rate']/fastest,overall_score=.85*r['quality']+.10*100*r['effective_rate']/fastest+.05*r['stability'])
    eligible.sort(key=lambda r:r['overall_score'],reverse=True)
    atomic(ROOT/'results/ranking.json',dict(at=now(),status='provisional' if pending else 'reviewed_outputs_ranked',rankings=eligible,pending_review=pending,weights=dict(quality=.85,speed=.10,stability=.05),note='未采集/未完成盲评的配置不参加质量排名；未测试图像。'))
    print(json.dumps(dict(ranked=len(eligible),pending_review=len(pending),reviewed_unique=len(annotations))))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','show','add','rank']);p.add_argument('--case');p.add_argument('--direction');p.add_argument('--limit',type=int,default=20);p.add_argument('--file');a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='show':show(a)
    elif a.action=='add':add(a.file)
    else:rank()
