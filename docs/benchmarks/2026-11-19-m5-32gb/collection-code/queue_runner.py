#!/usr/bin/env python3
"""Resumable local text-translation collection; no automatic quality claims.

Model downloads are synchronous and refill a two-model disk buffer. The download
response is closed before any inference starts. A process lock and an activity
gate prevent competing collectors. All servers use loopback and owned caches.
"""
from __future__ import annotations
import argparse
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_state import recover_gguf, merge_states, read as read_state

import httpx
try:
    import psutil
except ModuleNotFoundError:
    # The original run used psutil from a transient Python environment. Keep
    # the benchmark resumable on macOS when that environment is unavailable by
    # providing the small subset of psutil used here. System memory comes from
    # vm_stat; process RSS falls back to the current process resource usage.
    import resource
    from types import SimpleNamespace

    class _FallbackProcess:
        def __init__(self, pid): self.pid = pid
        def children(self, recursive=False): return []
        def memory_info(self):
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS reports ru_maxrss in bytes; normalize defensively.
            if rss < 1024 * 1024: rss *= 1024
            return SimpleNamespace(rss=int(rss))

    def _vm_stat():
        try:
            out = subprocess.check_output(['vm_stat'], text=True, stderr=subprocess.DEVNULL)
            page = 4096
            m = re.search(r'page size of (\d+) bytes', out)
            if m: page = int(m.group(1))
            vals = {}
            for line in out.splitlines():
                m = re.match(r'Pages ([^:]+):\s+(\d+)', line)
                if m: vals[m.group(1).strip().lower()] = int(m.group(2))
            free = sum(vals.get(k, 0) for k in ('free', 'inactive', 'speculative')) * page
            return free
        except Exception:
            return 0

    class _FallbackPsutil:
        Process = _FallbackProcess
        @staticmethod
        def virtual_memory(): return SimpleNamespace(available=_vm_stat())
        @staticmethod
        def swap_memory(): return SimpleNamespace(used=0)

    psutil = _FallbackPsutil()

TZ=timezone(timedelta(hours=8))
LANG={'zh':'Chinese','ja':'Japanese','en':'English'}
TERMINAL={'collected','backend_failed','partial_failed','source_unavailable','download_failed','quant_mismatch'}

def now(): return datetime.now(TZ).isoformat(timespec='seconds')
def in_scope(parameters_b): return 8<float(parameters_b)<=70

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)

def safe_error(error):
    return re.sub(r'https?://[^\s"<>]+',lambda m:m.group(0).split('?')[0]+'[query redacted]' if '?' in m.group(0) else m.group(0),str(error))[:800]

def requeue_network_failure(entry):
    error=entry.get('error','')
    transient=('eof','no such host','timed out','timeout','connection reset','connection refused','network is unreachable','tls handshake')
    if entry.get('phase')!='download_failed' or not any(x in error.lower() for x in transient):return False
    if entry.get('network_cycles',0)>=entry.get('max_network_cycles',3):return False
    entry.setdefault('download_failure_history',[]).append({'at':now(),'error':error})
    entry['phase']='download_retry'
    entry.setdefault('download',{}).update(status='network_retry',speed_bps=0,eta_seconds=None)
    return True

def request_profile(model):
    # DeepSeek-R1 spends a substantial prefix on reasoning. Give the retry
    # enough generation budget to reach the translation, while keeping the
    # standard budget for ordinary instruction models.
    reasoning=model.startswith('deepseek-r1:32b')
    return {'max_tokens': 1536 if reasoning else 384,'timeout_seconds':900 if reasoning else 120}

def collection_status(records):
    return 'collected' if len(records)==144 and all(r.get('success') for r in records) else 'partial_failed'

class ActivityGate:
    def __init__(self):self.phase=None;self.lock=threading.Lock()
    def enter(self,phase):
        with self.lock:
            if self.phase is not None:raise RuntimeError(f'Cannot enter {phase} while {self.phase} active')
            self.phase=phase
    def leave(self,phase):
        with self.lock:
            if self.phase!=phase:raise RuntimeError('Activity ownership mismatch')
            self.phase=None
    @contextmanager
    def use(self,phase):
        self.enter(phase)
        try:yield
        finally:self.leave(phase)

class PauseRequested(Exception):
    pass

class PullProgress:
    def __init__(self,layers=None):
        self.layers={x['digest']:dict(x) for x in (layers or [])}
        self.seen_layers=set()
        self.samples=deque(maxlen=50);self.status='connecting';self.layer=None;self.last_progress=None
    def update(self,event,timestamp=None):
        t=time.monotonic() if timestamp is None else timestamp
        old=sum(x.get('completed',0) for x in self.layers.values())
        self.status=event.get('status',self.status)
        if event.get('digest'):
            key=event['digest'];x=self.layers.setdefault(key,{'digest':key,'total':0,'completed':0})
            self.layer=key
            x['total']=max(x['total'],int(event.get('total',0)))
            # The server may have lost partial files since the saved snapshot.
            # Reconcile once per stream, then retain monotonic progress.
            completed=int(event.get('completed',0))
            x['completed']=max(x['completed'],completed) if key in self.seen_layers else completed
            self.seen_layers.add(key)
        done=sum(x.get('completed',0) for x in self.layers.values())
        if not self.samples or t-self.samples[-1][0]>=1:self.samples.append((t,done))
        if done>old:self.last_progress=t
    def snapshot(self,timestamp=None):
        t=time.monotonic() if timestamp is None else timestamp
        total=sum(x['total'] for x in self.layers.values());done=sum(x['completed'] for x in self.layers.values())
        recent=[s for s in self.samples if t-s[0]<=15]
        speed=(recent[-1][1]-recent[0][1])/(recent[-1][0]-recent[0][0]) if len(recent)>1 and recent[-1][0]>recent[0][0] else 0
        if self.last_progress is None or t-self.last_progress>15:speed=0
        age=None if self.last_progress is None else round(t-self.last_progress)
        return dict(completed_bytes=done,total_bytes=total or None,percent=min(100,done/total*100) if total else None,
            speed_bps=max(0,speed),eta_seconds=(total-done)/speed if speed>0 and total else None,
            layers=list(self.layers.values()),current_layer=self.layer,status=self.status,last_progress_age_seconds=age)

class Runner:
    def __init__(self,root,retry_models=()):
        self.root=Path(root).resolve();self.results=self.root/'results';self.public=self.root/'public'
        self.results.mkdir(exist_ok=True);self.public.mkdir(exist_ok=True)
        self.control_path=self.results/'control.json'
        if not self.control_path.exists(): atomic_json(self.control_path,{'action':'resume','updated_at':now()})
        self.lock=(self.results/'queue.lock').open('a+')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.lock.seek(0);self.lock.truncate();self.lock.write(str(os.getpid()));self.lock.flush()
        self.config=json.loads((self.root/'run-config.json').read_text())
        self.cache=Path(self.config['cache']).resolve();self.cache.mkdir(parents=True,exist_ok=True)
        marker=self.cache/'owner.json'
        if marker.exists():
            if json.loads(marker.read_text())['project']!=str(self.root):raise RuntimeError('Cache owner mismatch')
        elif any(self.cache.iterdir()):raise RuntimeError('Refusing an unmarked populated cache')
        else:atomic_json(marker,{'project':str(self.root),'purpose':'owned benchmark weights'})
        self.models=self.cache/'models';self.models.mkdir(exist_ok=True)
        self.host='127.0.0.1:'+str(self.config.get('ollama_port',11455))
        self.api=httpx.Client(base_url='http://'+self.host,trust_env=False,timeout=httpx.Timeout(60,connect=5))
        self.case_path=self.root/'data/cases.jsonl'
        hashes=json.loads((self.root/'data/corpus.sha256.json').read_text())
        for name,h in hashes.items():
            if hashlib.sha256((self.root/'data'/name).read_bytes()).hexdigest()!=h:raise RuntimeError('Frozen corpus hash mismatch: '+name)
        self.cases=[json.loads(l) for l in self.case_path.read_text().splitlines()];assert len(self.cases)==144
        self.catalog=json.loads((self.root/'data/queue.json').read_text())
        if not all(in_scope(x['parameters_b']) for x in self.catalog):raise RuntimeError('Queue outside (8B,70B]')
        self.gate=ActivityGate();self.mutex=threading.RLock();self.stop=threading.Event();self.server=None;self.llama=None;self.pull=None
        old=recover_gguf(self.root)
        previous={x['model']:x for x in old.get('queue',[]) if x.get('id')}
        entries=[]
        for q in self.catalog:
            entry=previous.get(q['model']) or dict(q,id=q['model'].replace(':','--'),phase='queued',download={},test={},backends={},review_status='not_reviewable',cleanup_status='not_needed')
            if q['model'] in retry_models:
                entry['network_cycles']=0
                for backend,b in entry.get('backends',{}).items():
                    if b.get('status') in ('backend_failed','partial_failed'):
                        entry.setdefault('previous_backend_failures',[]).append(dict(backend=backend,summary=b,at=now()))
                        entry['backends'][backend]={'status':'queued'}
                entry['phase']='queued'
            requeue_network_failure(entry)
            # A previous driver can be interrupted while the dashboard still
            # contains ``paused``.  When the control file is already resume,
            # convert that stale marker into a normal retryable download so a
            # fresh driver does not leave the queue visibly paused forever.
            try:
                control_action=json.loads(self.control_path.read_text()).get('action')
            except Exception:
                control_action='resume'
            if entry.get('phase')=='paused' and control_action!='pause':
                entry['phase']='download_retry'
                entry.setdefault('download',{}).update(status='network_retry',auto_retry=True)
            entries.append(entry)
        self.state=dict(schema=2,updated_at=now(),device='Apple M5 MacBook Air',memory='32 GiB unified memory',
            phase='starting',current_model=None,current_backend=None,pid=os.getpid(),download_paused=False,
            paused=False,
            buffer_models=self.config.get('buffer_models',2),queue=entries,events=old.get('events',[])[-60:],
            notes=['仅文字翻译；质量分须另行逐题盲评','RSS为进程树采样，非独占显存','本轮平台模板与旧轮次不同，跨硬件只作参考'])
        self.write_state()
        self.heartbeat=threading.Thread(target=self.watch,daemon=True);self.heartbeat.start()
    def event(self,text):
        with self.mutex:
            self.state['events'].append({'at':now(),'message':safe_error(text)});self.state['events']=self.state['events'][-60:]
            self.write_state()
    def write_state(self):
        with self.mutex:
            self.state['updated_at']=now();self.state['activity']=self.gate.phase
            atomic_json(self.results/'gguf-state.json',self.state)
            combined=merge_states(self.state,read_state(self.results/'sglang-state.json'))
            atomic_json(self.results/'dashboard-state.json',combined)
            atomic_json(self.public/'dashboard-state.json',combined)
    def paused(self):
        try:
            return json.loads(self.control_path.read_text()).get('action')=='pause'
        except Exception:
            return False
    def wait_if_paused(self):
        while self.paused() and not self.stop.is_set():
            with self.mutex:
                self.state['paused']=True
                self.state['phase']='paused'
                self.state['download_paused']=True
                self.write_state()
            self.stop.wait(1)
        with self.mutex:
            self.state['paused']=False
            if self.state.get('phase')=='paused': self.state['phase']='resuming'
            self.write_state()
    def watch(self):
        while not self.stop.wait(2):
            with self.mutex:
                if self.paused():
                    self.state['paused']=True
                    self.state['download_paused']=True
                self.state['free_disk_bytes']=shutil.disk_usage(self.cache).free
                mem=psutil.virtual_memory();swap=psutil.swap_memory()
                self.state['system']=dict(available_gib=mem.available/1024**3,swap_gib=swap.used/1024**3)
                if self.pull and self.state['current_model']:
                    e=next(x for x in self.state['queue'] if x['model']==self.state['current_model'])
                    attempt=e['download'].get('attempt');e['download'].update(self.pull.snapshot());e['download']['attempt']=attempt
                self.write_state()
    def start_server(self):
        import socket
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',int(self.config.get('ollama_port',11455))))==0:raise RuntimeError('Dedicated Ollama port occupied; refusing unrelated server')
        env=dict(os.environ,OLLAMA_HOST=self.host,OLLAMA_MODELS=str(self.models),OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_CONTEXT_LENGTH='2048',OLLAMA_KEEP_ALIVE='0',OLLAMA_NO_CLOUD='1',OLLAMA_NOPRUNE='1')
        self.server=subprocess.Popen([self.config['ollama_binary'],'serve'],env=env,stdout=(self.results/'ollama-v2.log').open('a'),stderr=subprocess.STDOUT,start_new_session=True)
        atomic_json(self.results/'owned-processes.json',{'runner':os.getpid(),'ollama':self.server.pid,'host':self.host})
        for _ in range(120):
            if self.server.poll() is not None:raise RuntimeError('Owned Ollama server exited')
            try:
                r=self.api.get('/api/version',timeout=3);r.raise_for_status();self.state['ollama_version']=r.json()['version'];return
            except httpx.HTTPError:time.sleep(1)
        raise RuntimeError('Ollama startup timed out')
    def download(self,e):
        # No background pull is ever left active during the test phase.
        out=self.results/e['id'];out.mkdir(exist_ok=True)
        total=e.get('bytes') or 0
        if shutil.disk_usage(self.cache).free<total+8*1024**3:raise RuntimeError('Insufficient free disk with 8GiB headroom')
        e['phase']='downloading';self.state.update(phase='downloading',current_model=e['model'],current_backend=None,download_paused=False)
        progress=PullProgress(e['download'].get('layers'));self.pull=progress
        with self.gate.use('download'):
            for attempt in range(1,4):
                e['download']['attempt']=attempt;self.event(f"下载 {e['model']} · 尝试 {attempt}/3")
                began=time.monotonic();last_received=began;last_bytes=0
                try:
                    with self.api.stream('POST','/api/pull',json={'model':e['model'],'stream':True},timeout=httpx.Timeout(45,connect=5)) as response:
                        response.raise_for_status();success=False
                        with (out/'download-events.jsonl').open('a') as log:
                            for line in response.iter_lines():
                                if not line:continue
                                packet=json.loads(line)
                                if self.paused(): raise PauseRequested('Paused by dashboard')
                                if packet.get('error'):raise RuntimeError(safe_error(packet['error']))
                                progress.update(packet)
                                snap=progress.snapshot()
                                if snap['completed_bytes']>last_bytes:last_received=time.monotonic();last_bytes=snap['completed_bytes']
                                if time.monotonic()-last_received>180:raise TimeoutError('Download made no byte progress for 180 seconds')
                                if time.monotonic()-began>3*3600:raise TimeoutError('Download exceeded 3 hours')
                                e['download'].update(snap);e['download']['attempt']=attempt
                                # 1Hz state writes via heartbeat; record each actual structured event.
                                log.write(json.dumps({'at':now(),**packet},ensure_ascii=False)+'\n');log.flush()
                                if packet.get('status')=='success':success=True;break
                        if not success:raise RuntimeError('Pull stream ended without success')
                    info=self.api.post('/api/show',json={'model':e['model']}).json()
                    details=info.get('details',{});actual=details.get('quantization_level','').upper()
                    if actual and actual!=e['quant'].upper():
                        e['phase']='quant_mismatch';raise RuntimeError(f"Expected {e['quant']}, got {actual}")
                    tags=self.api.get('/api/tags').json()['models'];tag=next(x for x in tags if x['name']==e['model'])
                    manifest=self.models/'manifests/registry.ollama.ai/library'/e['model'].split(':')[0]/e['model'].split(':')[1]
                    m=json.loads(manifest.read_text());weights=[x for x in m['layers'] if x['mediaType']=='application/vnd.ollama.image.model']
                    if len(weights)!=1:raise RuntimeError('Expected a single model GGUF layer')
                    blob=self.models/'blobs'/weights[0]['digest'].replace(':','-')
                    # Verification is part of pull, before inference. Retain the registry SHA256 ledger.
                    atomic_json(out/'checkpoint.json',dict(tag=tag,details=details,capabilities=info.get('capabilities'),model_info=info.get('model_info'),
                        weights_digest=weights[0]['digest'],weights_bytes=weights[0]['size'],blob=str(blob),verified_by='Ollama pull SHA256 verification'))
                    atomic_json(out/'model-show.json',info)
                    e['weights_blob']=str(blob);e['manifest_digest']=tag['digest'];e['native_capabilities']=info.get('capabilities',[])
                    e['download'].update(percent=100,status='verified',speed_bps=0,eta_seconds=0)
                    e['phase']='downloaded';self.event(f"校验完成 {e['model']}");self.pull=None;return True
                except PauseRequested:
                    e['phase']='paused';e['download']['status']='paused';self.event(f"已暂停下载 {e['model']}");self.write_state();return False
                except Exception as exc:
                    e['error']=safe_error(exc);self.event(f"下载重试 {e['model']}：{e['error']}")
                    if '404' in str(exc) or 'not found' in str(exc).lower() or e['phase']=='quant_mismatch':break
                    if attempt<3:
                        e['phase']='download_retry';self.write_state();self.stop.wait(10*attempt);e['phase']='downloading'
        self.pull=None
        if e['phase']!='quant_mismatch':e['phase']='download_failed'
        e['network_cycles']=e.get('network_cycles',0)+1
        if requeue_network_failure(e):
            self.state['phase']='download_retry'
            self.event(f"临时网络错误，保留分片并等待60秒后继续队列：{e['model']}")
            self.stop.wait(60)
        e['review_status']='not_reviewable';self.write_state();return False
    def text_prompt(self,c):
        style='a formal' if c['register']=='formal' else 'an informal but professional'
        return (f"Translate the following {LANG[c['source_language']]} text into {LANG[c['target_language']]}. "
            f'Context: {style} meeting between internet or technology companies. '
            'Preserve meaning, uncertainty, negation, numbers, units, named entities and technical terms. '
            'Output only the translation, without explanations or a thinking process.\n\n'+c['source'])
    def start_llama(self,e):
        out=self.results/e['id']/'llamacpp';out.mkdir(exist_ok=True)
        binary=self.config.get('llama_binary_overrides',{}).get(e['model'],self.config['llama_binary'])
        cmd=[binary,'-m',e['weights_blob'],'--host','127.0.0.1','--port','18085','-c','2048','-np','1','-ngl','99','-t','4','-b','128','-ub','128','--no-warmup']
        atomic_json(out/'launch.json',{'command':cmd})
        self.llama=subprocess.Popen(cmd,stdout=(out/'server.log').open('a'),stderr=subprocess.STDOUT,start_new_session=True)
        api=httpx.Client(base_url='http://127.0.0.1:18085',trust_env=False,timeout=httpx.Timeout(60,connect=5))
        for _ in range(180):
            if self.llama.poll() is not None:raise RuntimeError('llama.cpp exited during load; see server.log')
            try:
                if api.get('/health',timeout=3).status_code==200:return api
            except httpx.HTTPError:pass
            time.sleep(1)
        raise TimeoutError('llama.cpp loading exceeded 180 seconds')
    def request(self,api,backend,e,c,warmup=False):
        prompt=self.text_prompt(c);t=time.perf_counter();first=None;chunks=[];thinking=[];usage={};timings={};done=False
        max_tokens=request_profile(e['model'])['max_tokens']
        opts=dict(temperature=0,num_ctx=2048,num_predict=max_tokens,seed=42,num_thread=4,num_batch=128)
        if backend=='ollama':
            route='/api/chat';body={'model':e['model'],'messages':[{'role':'user','content':prompt}],'stream':True,'think':False,'keep_alive':'5m','options':opts}
        else:
            route='/v1/chat/completions';body={'messages':[{'role':'user','content':prompt}],'stream':True,'temperature':0,'seed':42,'max_tokens':max_tokens,'cache_prompt':True,'chat_template_kwargs':{'enable_thinking':False},'stream_options':{'include_usage':True}}
        with api.stream('POST',route,json=body,timeout=httpx.Timeout(60,connect=5)) as r:
            if r.status_code!=200:raise RuntimeError(f'{r.status_code}: {safe_error(r.read().decode())}')
            for line in r.iter_lines():
                limit=request_profile(e['model'])['timeout_seconds']
                if time.perf_counter()-t>limit:raise TimeoutError(f'Request exceeded {limit} seconds')
                if not line or line.startswith(':'):continue
                if line=='data: [DONE]':done=True;break
                packet=json.loads(line[6:] if line.startswith('data: ') else line)
                if 'error' in packet:raise RuntimeError(safe_error(packet['error']))
                if backend=='ollama':
                    message=packet.get('message',{});text=message.get('content','');thought=message.get('thinking','')
                    if packet.get('done'):usage=packet;done=True
                else:
                    choices=packet.get('choices',[]);delta=choices[0].get('delta',{}) if choices else {}
                    text=delta.get('content') or '';thought=delta.get('reasoning_content') or ''
                    if packet.get('usage'):usage=packet['usage']
                    if packet.get('timings'):timings=packet['timings']
                    if choices and choices[0].get('finish_reason'):done=True
                if text or thought:
                    if first is None:first=time.perf_counter()-t
                    chunks.append(text);thinking.append(thought)
        elapsed=time.perf_counter()-t
        if not done:raise RuntimeError('Incomplete inference stream')
        text=''.join(chunks);think=''.join(thinking)
        if backend=='ollama':
            tokens=usage.get('eval_count');seconds=(usage.get('eval_duration') or 0)/1e9
        else:tokens=usage.get('completion_tokens');seconds=(timings.get('predicted_ms') or 0)/1000
        # No invented decode speed: OpenAI usage alone cannot identify decode duration.
        rate=tokens/seconds if tokens and seconds else None
        return dict(case_id=c['case_id'],source_language=c['source_language'],target_language=c['target_language'],
            register=c['register'],source=c['source'],reference=c['reference'],atomic_facts=c['atomic_facts'],prompt=prompt,
            response=text,thinking=think,success=bool(text.strip()),latency_seconds=elapsed,ttft_seconds=first,
            decode_tps=rate,output_tokens=tokens,raw_usage=usage,raw_timings=timings,model=e['model'],backend=backend,
            possible_truncation=bool(tokens and tokens>=max_tokens),warmup=warmup,recorded_at=now())
    def sample(self,process,e,out,stop):
        while not stop.wait(1):
            try:
                proc=psutil.Process(process.pid);rss=0
                for p in [proc]+proc.children(recursive=True):
                    try:rss+=p.memory_info().rss
                    except psutil.NoSuchProcess:pass
                m=psutil.virtual_memory();swap=psutil.swap_memory();sample=dict(at=now(),rss_tree_bytes=rss,available_bytes=m.available,system_swap_bytes=swap.used)
                with (out/'memory.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
                with self.mutex:
                    e['test']['peak_rss_gib']=max(e['test'].get('peak_rss_gib') or 0,rss/1024**3)
                    e['test']['min_available_gib']=min(e['test'].get('min_available_gib') or 1000,m.available/1024**3)
                    e['test']['max_swap_gib']=max(e['test'].get('max_swap_gib') or 0,swap.used/1024**3)
            except psutil.NoSuchProcess:return
    def test(self,e,backend):
        if e['backends'].get(backend,{}).get('status') in TERMINAL:return
        out=self.results/e['id']/backend;out.mkdir(exist_ok=True)
        output=out/'outputs.jsonl';prior=[json.loads(x) for x in output.read_text().splitlines()] if output.exists() else []
        latest={x['case_id']:x for x in prior};prior=list(latest.values())
        seen={x['case_id'] for x in prior if x.get('success')}
        self.state.update(phase='testing',current_model=e['model'],current_backend=backend,download_paused=True)
        e.update(phase='testing',test=dict(completed_cases=len(prior),total_cases=144,successes=sum(x.get('success',False) for x in prior),mean_decode_tps=None,peak_rss_gib=None))
        with self.gate.use('inference'):
            api=self.api;llama_api=None;sample_stop=threading.Event();sampler=None
            try:
                if backend=='llamacpp':llama_api=api=self.start_llama(e)
                anchor=self.llama if backend=='llamacpp' else self.server
                sampler=threading.Thread(target=self.sample,args=(anchor,e,out,sample_stop),daemon=True);sampler.start()
                atomic_json(out/'conditions.json',dict(dataset_sha256=hashlib.sha256(self.case_path.read_bytes()).hexdigest(),
                    context=2048,max_output_tokens=request_profile(e['model'])['max_tokens'],request_timeout_seconds=request_profile(e['model'])['timeout_seconds'],temperature=0,seed=42,threads=4,batch=128,
                    template='backend-native chat template; same user instruction as M3 study',thinking=False,
                    download_active=False,native_multimodal_tested=False))
                self.event(f"预热 {e['model']} / {backend}；下载已停止")
                warmup=self.request(api,backend,e,self.cases[0],warmup=True);atomic_json(out/'warmup.json',warmup)
                self.event(f"开始144题 {e['model']} / {backend}")
                failures=0
                with output.open('a') as f:
                    for c in self.cases:
                        self.wait_if_paused()
                        if c['case_id'] in seen:continue
                        if self.stop.is_set():raise InterruptedError('Stopped')
                        if psutil.virtual_memory().available<512*1024**2:raise MemoryError('Available RAM below 512MiB; stopping this configuration')
                        try:
                            rec=self.request(api,backend,e,c)
                            failures=0 if rec.get('success') else failures+1
                        except Exception as exc:
                            rec=dict(case_id=c['case_id'],model=e['model'],backend=backend,success=False,error=safe_error(exc),recorded_at=now());failures+=1
                        f.write(json.dumps(rec,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno());latest[rec['case_id']]=rec;prior=list(latest.values())
                        with self.mutex:
                            rates=[r['decode_tps'] for r in prior if r.get('success') and r.get('decode_tps')]
                            latencies=[r['latency_seconds'] for r in prior if r.get('success')]
                            e['test'].update(completed_cases=len(prior),successes=sum(r.get('success',False) for r in prior),mean_decode_tps=statistics.mean(rates) if rates else None,
                                median_latency_seconds=statistics.median(latencies) if latencies else None)
                            self.write_state()
                        if failures>=3:raise RuntimeError('Three consecutive failed cases; stopped partial configuration')
                status=collection_status(prior);review='scoring_pending' if status=='collected' else 'not_reviewable'
                result=dict(e['test'],status=status,output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),review_status=review)
                e['review_status']=review;e['backends'][backend]=result
                atomic_json(out/'summary.json',result);self.event(f"采集状态 {status}：{e['model']} / {backend}；成功 {e['test']['successes']}/144")
            except Exception as exc:
                result=dict(e['test'],status='partial_failed' if prior else 'backend_failed',error=safe_error(exc),review_status='not_reviewable')
                e['backends'][backend]=result;atomic_json(out/'summary.json',result);self.event(f"配置未完成 {e['model']} / {backend}：{safe_error(exc)}")
            finally:
                sample_stop.set()
                if sampler:sampler.join(timeout=3)
                if self.llama:
                    self.llama.terminate()
                    try:self.llama.wait(timeout=15)
                    except subprocess.TimeoutExpired:self.llama.kill();self.llama.wait(timeout=5)
                    self.llama=None
                if backend=='ollama':
                    try:self.api.post('/api/generate',json={'model':e['model'],'keep_alive':0},timeout=15).raise_for_status()
                    except httpx.HTTPError as exc:self.event('卸载请求失败：'+safe_error(exc))
                # ``start_llama`` returns a separate client. Keep the main
                # Ollama client open for the cleanup request after a llama.cpp
                # backend, otherwise cleanup fails with "client is closed".
                if llama_api is not None and llama_api is not self.api:llama_api.close()
                e['phase']='scoring_pending' if any(x.get('status')=='collected' for x in e['backends'].values()) else 'backend_failed'
                self.write_state()
    def clean(self,e):
        # Delete this exact model from our own cache only, after both platforms.
        e['cleanup_status']='removing';self.write_state()
        try:
            r=self.api.request('DELETE','/api/delete',json={'model':e['model']},timeout=60)
            if r.status_code not in (200,404):r.raise_for_status()
            tags=self.api.get('/api/tags').json()['models']
            if any(x['name']==e['model'] for x in tags):raise RuntimeError('Model still registered after delete')
            e['cleanup_status']='verified';e.pop('weights_blob',None)
            atomic_json(self.results/e['id']/'cleanup.json',dict(model=e['model'],cache=str(self.models),removed_from_isolated_store=True,at=now()))
            self.event('清理完成 '+e['model'])
        except Exception as exc:
            e['cleanup_status']='failed';e['cleanup_error']=safe_error(exc);self.write_state();raise
    def run(self):
        try:
            self.start_server();self.event('独立驱动启动；顺序预取两项，推理期间零下载')
            while not self.stop.is_set():
                self.wait_if_paused()
                todo=[e for e in self.state['queue'] if e['phase'] not in {'download_failed','quant_mismatch','source_unavailable'} and (not all(e['backends'].get(b,{}).get('status') in TERMINAL for b in self.config['backends']) or e.get('cleanup_status')!='verified')]
                if not todo:break
                ready=[]
                for e in todo:
                    # Finish interrupted cleanup without downloading the weights again.
                    if all(e['backends'].get(b,{}).get('status') in TERMINAL for b in self.config['backends']):
                        self.clean(e);continue
                    # Preserve verified prefetched files and partially collected configurations on resume.
                    if not e.get('weights_blob') or not Path(e['weights_blob']).exists():
                        if not self.download(e):
                            if self.paused(): break
                            continue
                    ready.append(e)
                    if len(ready)>=self.state['buffer_models']:break
                if not ready:continue
                for e in ready:
                    for backend in self.config['backends']:
                        self.test(e,backend)
                    self.clean(e)
            self.state.update(phase='collection_finished',current_model=None,current_backend=None,download_paused=True)
            self.event('当前GGUF队列采集已处理；质量评分与MLX适配另列待办')
        finally:
            self.stop.set()
            if self.server:
                self.server.terminate()
                try:self.server.wait(timeout=15)
                except subprocess.TimeoutExpired:self.server.kill()
            self.write_state()

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--retry-model',action='append',default=[]);args=p.parse_args()
    r=Runner(args.root,args.retry_model)
    def interrupted(*_):r.stop.set();raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:r.run()
    except BaseException as exc:
        r.state['phase']='interrupted' if isinstance(exc,KeyboardInterrupt) else 'driver_failed';r.state['driver_error']=safe_error(exc);r.write_state();raise

if __name__=='__main__':main()
