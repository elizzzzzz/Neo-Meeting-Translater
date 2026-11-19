#!/usr/bin/env python3
"""Serial, resumable SGLang MLX collection; never claims translation quality."""
from __future__ import annotations
import argparse
import fcntl
import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
import httpx
import psutil
from benchmark_state import atomic, read, now, merge_states, recover_gguf

ROOT=Path(__file__).resolve().parents[1]
PYTHON=Path('/opt/sglang-metal/bin/python')
CACHE=Path('/tmp/sglang-benchmark-cache')
STATE=ROOT/'results/sglang-state.json'
PORT=30001
PATTERNS=['*.json','*.safetensors','*.model','*.txt','*.jinja','*.tiktoken']


def slug(repo): return repo.replace('/','--')
def safe(ex): return re.sub(r'https?://[^\s<>"\']+',lambda m:m[0].split('?')[0]+'[query redacted]',str(ex))[:1000]
def environment(offline=False):
    env=dict(os.environ,SGLANG_USE_MLX='1',SGLANG_MLX_CACHE_LIMIT_GB='0.125',
             TOKENIZERS_PARALLELISM='false',HF_HUB_DISABLE_XET='1',HF_HUB_DOWNLOAD_TIMEOUT='60',
             HF_HOME=str(CACHE/'hf'))
    env.pop('PYTHONPATH',None)
    if offline:env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    else:
        env.pop('HF_HUB_OFFLINE',None);env.pop('TRANSFORMERS_OFFLINE',None)
    return env

def download_progress(model_dir):
    files={}
    for p in (model_dir/'.cache/huggingface/trees').glob('*.json'):
        files.update(read(p).get('files',{}))
    files={k:v for k,v in files.items() if any(fnmatch.fnmatch(k,p) for p in PATTERNS)}
    total=sum(int(v.get('size',0)) for v in files.values()) or None
    complete=0;finished=set();partials={};details=[]
    if files:
        for name,meta in files.items():
            p=model_dir/name
            if p.is_file():
                size=p.stat().st_size;file_done=min(size,meta['size']);complete+=file_done
                if size==meta['size']:finished.add(meta.get('lfs_sha256') or meta.get('blob_id'))
            else:
                etag=meta.get('lfs_sha256') or meta.get('blob_id')
                candidates=list((model_dir/'.cache/huggingface/download').glob('*'+etag+'*.incomplete')) if etag else []
                terminal=model_dir/'.cache/curl'/Path(name+'.part')
                if terminal.exists():candidates.append(terminal)
                file_done=max((p.stat().st_size for p in candidates),default=0)
                if terminal.exists():
                    offset=terminal.stat().st_size
                    inflight=0
                    ranges={}
                    for path in terminal.parent.glob(terminal.name+'.*'):
                        match=re.search(r'\.(\d+)-(\d+)\.(chunk|incoming)$',path.name)
                        if match and int(match[1])>=offset:
                            ranges[(int(match[1]),int(match[2]))]=path.with_suffix('.chunk')
                    for (begin,end),chunk in ranges.items():
                        def size_now(path):
                            try:return path.stat().st_size
                            except FileNotFoundError:return 0
                        retained=min(size_now(chunk),end-begin+1)
                        headers=chunk.with_suffix('.incoming-headers')
                        try:raw=headers.read_text(errors='replace')
                        except FileNotFoundError:raw=''
                        declared=re.findall(r'content-range:\s*bytes\s+(\d+)-(\d+)/(\d+)',raw,re.I)
                        if declared and tuple(map(int,declared[-1]))==(begin+retained,end,meta['size']):
                            retained+=min(size_now(chunk.with_suffix('.incoming')),end-begin+1-retained)
                        inflight+=retained
                    file_done=max(file_done,offset+inflight)
                file_done=min(meta['size'],file_done);complete+=file_done
            details.append(dict(digest=name,total=meta['size'],completed=file_done))
        return dict(completed_bytes=complete,total_bytes=total,percent=round(100*complete/total,2) if total else None,layers=details)
    else:
        complete=sum(p.stat().st_size for p in model_dir.rglob('*') if p.is_file() and '.cache' not in p.parts)
    for p in (model_dir/'.cache/huggingface/download').glob('*.incomplete'):
        parts=p.name.split('.')
        etag=parts[-3] if len(parts)>=4 else p.name
        partials[etag]=max(partials.get(etag,0),p.stat().st_size)
    complete+=sum(size for etag,size in partials.items() if etag not in finished)
    for p in (model_dir/'.cache/curl').rglob('*.part'):
        complete+=p.stat().st_size
    if total:complete=min(complete,total)
    return dict(completed_bytes=complete,total_bytes=total,percent=round(100*complete/total,2) if total else None)

def download_worker(repo,path):
    from hub_terminal_download import download
    download(repo,path)

def render(c,tok,repo):
    lang={'zh':'Chinese','ja':'Japanese','en':'English'}
    src,tgt=c['source_language'],c['target_language']
    style='a formal' if c['register']=='formal' else 'an informal but professional'
    text=(f'Translate the following {lang[src]} text into {lang[tgt]}. Context: {style} meeting between internet or technology companies. '
          'Preserve meaning, uncertainty, negation, numbers, units, named entities and technical terms. '
          'Output only the translation, without explanations or a thinking process.\n\n'+c['source'])
    if 'translategemma' in repo.lower():
        return tok.apply_chat_template([{'role':'user','content':[{'type':'text','source_lang_code':src,'target_lang_code':tgt,'text':c['source']}]}],tokenize=False,add_generation_prompt=True)
    try:return tok.apply_chat_template([{'role':'user','content':text}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
    except TypeError:return tok.apply_chat_template([{'role':'user','content':text}],tokenize=False,add_generation_prompt=True)

class Runner:
    def __init__(self,args):
        self.args=args;self.mutex=threading.RLock();self.stop=threading.Event();self.proc=None;self.worker=None
        self.current=None;self.client=None;self.memory_stop=threading.Event();self.sampler=None
        self.lock=(ROOT/'results/queue.lock').open('a+')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        CACHE.mkdir(parents=True,exist_ok=True)
        self.plan=read(ROOT/'results/sglang-plan-20261115.json')
        self.cases=[json.loads(x) for x in (ROOT/'data/cases.jsonl').read_text().splitlines()]
        for name,digest in read(ROOT/'data/corpus.sha256.json').items():
            assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest, name
        self.s=read(STATE,{'schema':2,'queue':[],'events':[]})
        for q in self.plan['queue']:
            key=q['repo']+'@'+q['quant']
            if not any(e['key']==key for e in self.s['queue']):
                self.s['queue'].append(dict(q,key=key,status='queued',completed_cases=0,successes=0))
        for e in self.s['queue']:
            if e['status']=='cleaning' and e.get('cleanup')=='verified':
                e['status']='collected' if e.get('summary') else 'backend_failed'
        self.s.update(pid=os.getpid(),phase='sglang_preflight',current_backend='sglang',
                      overall_status='running',finished_at=None,activity=None,paused=False,driver_error='')
        self.save()
        self.heartbeat=threading.Thread(target=self.watch,daemon=True);self.heartbeat.start()
    def save(self):
        with self.mutex:
            self.s['updated_at']=now();atomic(STATE,self.s)
    def event(self,message):
        with self.mutex:
            self.s.setdefault('events',[]).append(dict(at=now(),message=safe(message)))
            self.s['events']=self.s['events'][-100:];self.save()
        print(now(),safe(message),flush=True)
    def phase(self,name,activity=None):
        with self.mutex:
            self.s.update(phase=name,activity=activity,download_paused=activity!='download',
                          current_model=self.current['repo'] if self.current else None)
            self.save()
    def paused(self):return read(ROOT/'results/control.json').get('action')=='pause'
    def wait_pause(self):
        prior=self.s['phase'];activity=self.s.get('activity')
        while self.paused():
            self.s['paused']=True;self.phase('paused');self.stop.wait(1)
            if self.stop.is_set():raise InterruptedError('Stopped')
        self.s['paused']=False
        if self.s['phase']=='paused':self.phase(prior,activity)
    def watch(self):
        while not self.stop.wait(2):self.save()
    def preflight(self):
        command=[str(PYTHON),'-c','import sglang.srt.entrypoints.http_server']
        p=subprocess.run(command,env=environment(True),capture_output=True,text=True,timeout=120)
        atomic(ROOT/'results/sglang-preflight-20261116.json',dict(command=command,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,unsafe_triton_stub=False,at=now()))
        if p.returncode:raise RuntimeError('SGLang import preflight failed; see preflight record')
        self.event('SGLang 无模拟 Triton 的运行时导入预检通过')
    def stop_process(self,proc):
        if proc and proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
            except (ProcessLookupError,subprocess.TimeoutExpired):
                try:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
                except ProcessLookupError:pass
    def download(self,e):
        md=CACHE/'models'/(slug(e['repo'])+'-'+e['quant']);md.mkdir(parents=True,exist_ok=True)
        e.pop('error',None);e.update(status='downloading',download_started=now());self.phase('sglang_downloading','download')
        attempt=0
        while attempt<3:
            self.wait_pause();attempt+=1
            e['download_attempt']=attempt;self.event(f"下载 {e['repo']} · 尝试 {attempt}/3")
            log=ROOT/'results/sglang'/slug(e['repo'])/e['quant']/'download.log';log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('a') as f:
                self.worker=subprocess.Popen([str(PYTHON),str(Path(__file__).resolve()),'--download',e['repo'],str(md)],env=environment(),stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            last=download_progress(md);last_bytes=last['completed_bytes'];idle=time.monotonic();sample_t=idle;sample_bytes=last_bytes
            try:
                while self.worker.poll() is None:
                    if self.stop.wait(1):raise InterruptedError('Stopped')
                    if self.paused():
                        self.stop_process(self.worker);self.wait_pause();attempt-=1;break
                    progress=download_progress(md);t=time.monotonic()
                    if progress['completed_bytes']!=last_bytes:idle=t;last_bytes=progress['completed_bytes']
                    speed=max(0,(progress['completed_bytes']-sample_bytes)/(t-sample_t))
                    if t-sample_t>=10:sample_t=t;sample_bytes=progress['completed_bytes']
                    progress.update(status='downloading',speed_bps=speed,attempt=attempt,
                                    eta_seconds=(progress['total_bytes']-progress['completed_bytes'])/speed if progress['total_bytes'] and speed else None)
                    e['download']=progress;self.save()
                    if t-idle>240:raise TimeoutError('Download made no byte progress for 240 seconds')
                else:
                    if self.worker.returncode:raise RuntimeError(f'Hub worker exited {self.worker.returncode}; see download.log')
                    if not list(md.glob('*.safetensors')):raise RuntimeError('No MLX safetensors downloaded')
                    total=sum(p.stat().st_size for p in md.rglob('*') if p.is_file() and '.cache' not in p.parts)
                    e.pop('error',None);e.update(status='downloaded',model_dir=str(md),cleanup='not_needed')
                    e['download']=dict(status='verified',completed_bytes=total,total_bytes=total,percent=100,speed_bps=0,attempt=attempt)
                    self.save();self.event(f"下载完成 {e['repo']} · {total/1024**3:.2f} GiB")
                    return md
            except InterruptedError:raise
            except Exception as ex:
                self.stop_process(self.worker);e['error']=safe(ex);self.event(f"下载失败 {e['repo']}：{ex}")
                if attempt<3:self.stop.wait(5*attempt)
            finally:self.stop_process(self.worker);self.worker=None
        e['status']='download_failed';self.save();return None
    def sample(self,out):
        while not self.memory_stop.wait(1):
            try:
                parent=psutil.Process(self.proc.pid);rss=0
                for p in [parent]+parent.children(recursive=True):
                    try:rss+=p.memory_info().rss
                    except psutil.NoSuchProcess:pass
                rec=dict(at=now(),rss_tree_bytes=rss,available_bytes=psutil.virtual_memory().available,swap_bytes=psutil.swap_memory().used)
                with (out/'memory.jsonl').open('a') as f:f.write(json.dumps(rec)+'\n')
                e=self.current;e['peak_rss_gib']=max(e.get('peak_rss_gib',0),rss/1024**3)
                e['min_available_gib']=min(e.get('min_available_gib',1000),rec['available_bytes']/1024**3)
                e['max_swap_gib']=max(e.get('max_swap_gib',0),rec['swap_bytes']/1024**3)
            except psutil.NoSuchProcess:return
    def start(self,e,out):
        import socket
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',PORT))==0:raise RuntimeError('Dedicated SGLang port occupied')
        cmd=[str(PYTHON),'-m','sglang.launch_server','--model-path',e['model_dir'],'--host','127.0.0.1','--port',str(PORT),'--context-length','2048','--max-running-requests','1','--max-total-tokens','2048','--chunked-prefill-size','256','--mem-fraction-static','0.7','--skip-server-warmup','--disable-cuda-graph','--random-seed','42']
        if 'Qwen3.5' in e['repo']:cmd+=['--mamba-radix-cache-strategy','no_buffer','--disable-overlap-schedule']
        atomic(out/'launch.json',dict(command=cmd,environment={k:v for k,v in environment(True).items() if k.startswith(('SGLANG_','HF_','TRANSFORMERS_','TOKENIZERS_'))},unsafe_triton_stub=False))
        self.proc=subprocess.Popen(cmd,env=environment(True),stdout=(out/'server.log').open('a'),stderr=subprocess.STDOUT,start_new_session=True)
        self.memory_stop.clear();self.sampler=threading.Thread(target=self.sample,args=(out,),daemon=True);self.sampler.start()
        self.client=httpx.Client(base_url=f'http://127.0.0.1:{PORT}',trust_env=False,timeout=httpx.Timeout(10,connect=2))
        started=time.monotonic()
        while time.monotonic()-started<240:
            if self.proc.poll() is not None:raise RuntimeError(f'SGLang startup exit {self.proc.returncode}; see server.log')
            if self.stop.wait(1):raise InterruptedError('Stopped')
            try:
                if self.client.get('/health').status_code==200:return
            except httpx.HTTPError:pass
        raise TimeoutError('SGLang startup exceeded 240 seconds')
    def request(self,tok,prompt):
        t=time.perf_counter();first=None;final={};text=''
        payload=dict(input_ids=tok.encode(prompt,add_special_tokens=False),stream=True,
                     sampling_params=dict(temperature=0,max_new_tokens=384,skip_special_tokens=True,repetition_penalty=1.0))
        with self.client.stream('POST','/generate',json=payload,timeout=httpx.Timeout(150,connect=5)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if time.perf_counter()-t>180:raise TimeoutError('Request exceeded 180 seconds')
                if not line or line.startswith(':'):continue
                if line.startswith('data:'):line=line[5:].strip()
                if line=='[DONE]':continue
                final=json.loads(line)
                if final.get('error'):raise RuntimeError(safe(final['error']))
                text=final.get('text','')
                if text.strip() and first is None:first=time.perf_counter()-t
        elapsed=time.perf_counter()-t;meta=final.get('meta_info',{});n=meta.get('completion_tokens')
        rate=(n-1)/(elapsed-first) if n and n>1 and first and elapsed>first else None
        return dict(response=text,success=bool(text.strip()),latency_seconds=elapsed,ttft_seconds=first,decode_tps=rate,
                    decode_tps_method='stream completion_tokens minus first / elapsed after first nonempty output',output_tokens=n,possible_truncation=bool(n and n>=384),raw=final)
    def stop_server(self):
        self.memory_stop.set();self.stop_process(self.proc)
        if self.sampler:self.sampler.join(timeout=3)
        if self.client:self.client.close()
        self.proc=self.client=self.sampler=None
    def test(self,e,md):
        from transformers import AutoTokenizer
        out=ROOT/'results/sglang'/slug(e['repo'])/e['quant'];out.mkdir(parents=True,exist_ok=True)
        e.update(status='testing',test_started=now());self.phase('sglang_testing','inference')
        output=out/'outputs.jsonl';prior=[json.loads(x) for x in output.read_text().splitlines()] if output.exists() else []
        # Successful persisted cases survive a resume. Failed cases are retried.
        records={x['case_id']:x for x in prior if x.get('success')};e.update(completed_cases=len(records),successes=len(records))
        try:
            tok=AutoTokenizer.from_pretrained(md,local_files_only=True,trust_remote_code=False)
            self.start(e,out);self.event(f"服务已就绪 {e['repo']}；下载停止，开始预热")
            warm=dict(self.cases[0],source_language='en',target_language='ja',source='Please confirm the meeting time.')
            self.request(tok,render(warm,tok,e['repo']))
            atomic(out/'conditions.json',dict(cases=144,dataset_sha256=hashlib.sha256((ROOT/'data/cases.jsonl').read_bytes()).hexdigest(),download_active=False,thinking=False,native_multimodal_input_tested=False,repo=e['repo'],quant=e['quant'],unsafe_triton_stub=False))
            failures=0
            with output.open('a') as f:
                for c in self.cases:
                    self.wait_pause()
                    if c['case_id'] in records:continue
                    if self.stop.is_set():raise InterruptedError('Stopped')
                    prompt=render(c,tok,e['repo'])
                    try:r=self.request(tok,prompt);failures=0 if r['success'] else failures+1
                    except Exception as ex:r=dict(response='',success=False,error=safe(ex));failures+=1
                    rec=dict(c,prompt=prompt,**r,model=e['repo'],quant=e['quant'],backend='sglang',recorded_at=now())
                    f.write(json.dumps(rec,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno());records[c['case_id']]=rec
                    current_rates=[r['decode_tps'] for r in records.values() if r.get('success') and r.get('decode_tps')]
                    current_lats=[r['latency_seconds'] for r in records.values() if r.get('success')]
                    e.update(completed_cases=len(records),successes=sum(bool(r.get('success')) for r in records.values()),
                             mean_decode_tps=statistics.mean(current_rates) if current_rates else None,
                             median_latency_seconds=statistics.median(current_lats) if current_lats else None);self.save()
                    if failures>=3:raise RuntimeError('Three consecutive failed requests')
            rows=list(records.values());rates=[r['decode_tps'] for r in rows if r.get('success') and r.get('decode_tps')];lats=[r['latency_seconds'] for r in rows if r.get('success')]
            e['status']='collected' if len(rows)==144 and e['successes']==144 else 'partial_failed'
            e['summary']=dict(status=e['status'],cases=len(rows),successes=e['successes'],mean_decode_tps=statistics.mean(rates) if rates else None,median_latency_seconds=statistics.median(lats) if lats else None,peak_rss_gib=e.get('peak_rss_gib'),min_available_gib=e.get('min_available_gib'),max_swap_gib=e.get('max_swap_gib'),output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),review_status='scoring_pending')
            atomic(out/'summary.json',e['summary']);e.pop('error',None)
        except InterruptedError:raise
        except Exception as ex:
            e.update(status='partial_failed' if records else 'backend_failed',error=safe(ex));atomic(out/'error.json',dict(status=e['status'],error=e['error'],at=now()));self.event(f"测试失败 {e['repo']}：{ex}")
        finally:self.stop_server();self.save()
    def cleanup(self,e,md):
        self.phase('sglang_cleanup');status=e['status'];e['cleanup']='removing';self.save()
        expected=CACHE/'models'/(slug(e['repo'])+'-'+e['quant'])
        if md.resolve()!=expected.resolve():raise RuntimeError('Unexpected cleanup path')
        shutil.rmtree(md)
        if md.exists():raise RuntimeError('Weights still present after cleanup')
        e.update(status=status,cleanup='verified');e.pop('model_dir',None);self.save();self.event(f"清理完成 {e['repo']} · {status}")
    def run(self):
        try:
            self.preflight()
            for e in self.s['queue']:
                if self.args.only and e['repo'] not in self.args.only:continue
                if e['status']=='collected' and e.get('cleanup')=='verified':continue
                if e['status'] in ('backend_failed','download_failed','partial_failed') and not self.args.retry_failed:continue
                self.current=e;self.wait_pause();md=None
                md=Path(e['model_dir']) if e.get('model_dir') and Path(e['model_dir']).exists() else self.download(e)
                if md is None:
                    # A terminal download failure must not leave a partial
                    # model occupying disk; evidence remains in download.log
                    # and the durable state snapshot.
                    partial=CACHE/'models'/(slug(e['repo'])+'-'+e['quant'])
                    if partial.exists():
                        shutil.rmtree(partial)
                    e['cleanup']='verified';e['cleanup_status']='verified';self.save()
                    continue
                try:
                    # Retry every previously failed item up to three times.  A
                    # startup failure may come from a transient MLX/HF cache
                    # issue, and old logs can contain errors from before the
                    # current Triton compatibility stubs were installed.
                    for attempt in range(1,4):
                        self.wait_pause();e['test_attempt']=attempt;self.test(e,md)
                        if e['status']=='collected':break
                        if attempt<3:self.stop.wait(5*attempt)
                finally:
                    self.stop_server()
                    if not self.stop.is_set() and not (self.args.keep_failed and e['status']!='collected'):self.cleanup(e,md)
            failed=[e for e in self.s['queue'] if e['status']!='collected']
            self.s.update(overall_status='needs_attention' if failed else 'collected',finished_at=now())
            self.current=None;self.phase('sglang_needs_attention' if failed else 'sglang_finished')
            self.event(f"本次SGLang处理结束：{len(self.s['queue'])-len(failed)}/{len(self.s['queue'])} 完整采集；其余需处理")
        except BaseException as ex:
            self.s.update(overall_status='interrupted' if isinstance(ex,(KeyboardInterrupt,InterruptedError)) else 'driver_failed',driver_error=safe(ex))
            self.phase(self.s['overall_status']);raise
        finally:
            self.stop.set();self.stop_process(self.worker);self.stop_server();self.save()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--download',nargs=2);parser.add_argument('--only',action='append');parser.add_argument('--retry-failed',action='store_true');parser.add_argument('--keep-failed',action='store_true');args=parser.parse_args()
    if args.download:download_worker(*args.download)
    else:
        runner=Runner(args)
        def stop(*_):runner.stop.set();raise InterruptedError('Interrupted by signal')
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        runner.run()
