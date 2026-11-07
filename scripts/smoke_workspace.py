"""Model-free UI smoke check. Requires Playwright with Chromium installed.

Run: python scripts/smoke_workspace.py
Does not download weights, open the microphone or change user preferences.
"""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
out=root/'artifacts/ui-review';out.mkdir(parents=True,exist_ok=True)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
smoke_env = dict(os.environ, PYTHONPATH=str(root / 'src'), MEETING_INTERPRETER_MODE='mock', MEETING_INTERPRETER_TRANSLATION_BACKEND='nllb')
server_log=tempfile.TemporaryFile(mode='w+')
proc=subprocess.Popen([sys.executable,'-m','uvicorn','meeting_interpreter.app:app','--host','127.0.0.1','--port',str(port),'--log-level','error'],cwd=root,env=smoke_env,stdout=server_log,stderr=server_log)
try:
 startup_deadline=time.monotonic()+60
 while time.monotonic()<startup_deadline:
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=.3):pass
   break
  except OSError:
   if proc.poll() is not None:break
   time.sleep(.1)
 else:
  server_log.seek(0)
  raise RuntimeError('UI test server did not start within 60 seconds: '+server_log.read())
 if proc.poll() is not None:
  server_log.seek(0)
  raise RuntimeError('UI test server exited: '+server_log.read())
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page(viewport={'width':1440,'height':900})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  health_fixture={'mode':'local','models':{'ready':False,'progress':42,'message':'测试：准备中'}}
  page.route('**/health',lambda route:route.fulfill(json=health_fixture))
  page.route('**/preferences',lambda route:route.fulfill(json={'show_tips':True}))
  page.route('**/system/check',lambda route:route.fulfill(json={'installed':False,'reachable':False,'recommended_model':'translategemma:4b','recommended_model_present':False,'brew_available':False}))
  saved_settings=[]
  def settings_route(route):
   if route.request.method=='POST':
    saved_settings.append(route.request.post_data_json)
    health_fixture.update(models={'ready':False,'stage':'restart','progress':0,'message':'设置已保存，请重启'},settings={'restart_required':True,**saved_settings[-1]})
    route.fulfill(json={'restart_required':True,'model_dir':saved_settings[-1]['model_dir']})
   else:route.fulfill(json={'model_dir':'/test/models','ollama_model_dir':'/test/ollama-models','asr_engine':'whisper','asr_model':'mlx-community/whisper-medium-mlx-8bit','translation_backend':'ollama','translation_model':'translategemma:4b'})
  page.route('**/settings',settings_route)
  apple_fixture={'available':True,'installed':False,'model':'Apple SpeechAnalyzer','models':['Apple SpeechAnalyzer'],'storage':'macOS','languages':[{'language':language,'installed':False,'status':'missing'} for language in ['zh','ja','en']]}
  apple_installs=[]
  def asset_route(route):
   if 'engine=apple' in route.request.url: route.fulfill(json=apple_fixture)
   else: route.fallback()
  def prepare_apple(route):
   payload=route.request.post_data_json
   assert payload['engine']=='apple'
   apple_installs.append(payload['languages'])
   for row in apple_fixture['languages']:
    if row['language'] in payload['languages']: row.update(installed=True,status='installed')
   apple_fixture['installed']=True
   route.fulfill(json={'ok':True,'message':'测试：语言资源准备完成'})
  page.route('**/system/models?**',asset_route)
  page.route('**/system/download-asr',prepare_apple)
  page.route('**/services/models?**',lambda route:route.fulfill(json={'reachable':True,'models':[
   {'id':'qwen3-asr:1.7b','asr':True,'translation':False},
   {'id':'translategemma:4b','asr':False,'translation':True}]}))
  page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
  page.locator('#tipsModal').wait_for(state='visible')
  page.screenshot(path=str(out/'tips.png'))
  page.locator('#closeTipsBtn').click()
  assert page.locator('#startupIntro').is_visible()
  assert page.locator('#startupProgress').get_attribute('max')=='100'
  page.screenshot(path=str(out/'startup.png'))
  health_fixture.update(models={'ready':True,'progress':100,'message':'测试：已就绪'})
  page.evaluate('health=>updateHealth(health)',health_fixture)
  assert not page.locator('#startupIntro').is_visible()
  for w,h in [(1440,900),(1280,720),(1024,768)]:
   page.set_viewport_size({'width':w,'height':h})
   page.screenshot(path=str(out/f'workspace-{w}.png'))
   assert page.evaluate('document.body.scrollWidth <= innerWidth && document.body.scrollHeight <= innerHeight')
   for selector in ['#startBtn', '#stopBtn', '#demoBtn', '#diagnosticStatus', '#audioStatus', '#clearBtn', '#floatingBtn', '#settingsBtn']:
    box=page.locator(selector).bounding_box()
    assert box and 0 <= box['x'] and box['x']+box['width'] <= w+1 and 0 <= box['y'] and box['y']+box['height'] <= h+1, (w,h,selector,box)

   for language in ['zh','ja','en']:
    page.evaluate('language=>setInterfaceLanguage(language)',language)
    assert not page.locator('#startupIntro').is_visible()
    assert page.evaluate('document.body.scrollWidth <= innerWidth && document.body.scrollHeight <= innerHeight')
    assert page.locator('#captions').evaluate('e=>e.clientHeight') > h*.6
    assert not page.locator('#sourceLanguage').is_visible()
    assert not page.locator('#targetLanguage').is_visible()
    page.screenshot(path=str(out/f'workspace-{w}-{language}.png'))
   print('layout',w,h,page.evaluate('({width:innerWidth,height:innerHeight,scrollW:document.body.scrollWidth,scrollH:document.body.scrollHeight,captions:document.querySelector("#captions").clientHeight})'))
  page.evaluate("setInterfaceLanguage('zh')")
  page.set_viewport_size({'width':1440,'height':900})
  # Exercise real select semantics and real click handlers without opening audio
  # hardware. The local WebSocket fixture confirms startup and live overrides.
  page.evaluate("""() => {
    window.__languageMessages = [];
    window.__realWebSocket = window.WebSocket;
    class TestSocket {
      static OPEN=1; static CONNECTING=0;
      constructor() { this.readyState=0; queueMicrotask(() => {this.readyState=1; this.onopen?.();}); }
      send(raw) {
        const message=JSON.parse(raw); window.__languageMessages.push(message);
        if (message.type==='config' || message.type==='source_language') queueMicrotask(() => {
          const pair=message.language_pair || selectedLanguagePair;
          const language=message.source_language;
          const target=language==='auto' ? pair.split('-')[1] : pair.split('-').find(item=>item!==language);
          this.onmessage?.({data:JSON.stringify({type:message.type==='config'?'configured':'source_language_changed',source_language:language,asr_language:language,target_language:target,language_pair:pair})});
        });
        if (message.type==='finish') this.close();
      }
      close() {this.readyState=3; this.onclose?.();}
    }
    window.WebSocket=TestSocket;
    window.__realAudioContext=window.AudioContext;
    window.AudioContext=class {
      constructor(){this.sampleRate=48000;this.destination={};}
      createMediaStreamSource(){return {connect(){}};}
      createScriptProcessor(){return {connect(){},disconnect(){}};}
      createGain(){return {gain:{value:0},connect(){}};}
      async resume(){} async close(){}
    };
    window.__realGetUserMedia=navigator.mediaDevices.getUserMedia;
    navigator.mediaDevices.getUserMedia=async()=>({getAudioTracks:()=>[{label:'UI test input'}],getTracks:()=>[{stop(){}}]});
  }""")
  for left,right in [('zh','ja'),('zh','en'),('en','ja')]:
   page.locator(f'.direction-button[data-source="{left}"][data-target="{right}"]').click()
   assert page.locator('.source-language-button:visible').count()==3
   page.locator(f'.source-language-button[data-language="{right}"]').click()
   assert page.locator('#sourceLanguage').input_value()==right
   assert page.locator('#targetLanguage').input_value()==left
   page.locator('#startBtn').click()
   page.wait_for_function('document.querySelector("#runtimeText").textContent.includes("运行中")')
   message=page.evaluate('window.__languageMessages.filter(m=>m.type==="config").at(-1)')
   assert message['source_language']==right and message['target_language']==left
   assert message['language_pair']==f'{left}-{right}'
   page.locator(f'.source-language-button[data-language="{left}"]').click()
   page.wait_for_function('language=>document.querySelector("#sourceLanguage").value===language',arg=left)
   assert page.locator(f'.source-language-button[data-language="{left}"]').get_attribute('aria-pressed')=='true'
   assert page.locator('#targetLanguage').input_value()==right
   assert '自动' not in page.locator('#recognitionLanguageStatus').inner_text()
   page.locator('.source-language-button[data-language="auto"]').click()
   page.wait_for_function('document.querySelector("#recognitionLanguageStatus").textContent.includes("自动")')
   page.locator('#stopBtn').click()
   page.wait_for_function('document.querySelector("#startBtn").disabled===false')
  page.evaluate("""() => {
    WebSocket=window.__realWebSocket; AudioContext=window.__realAudioContext;
    navigator.mediaDevices.getUserMedia=window.__realGetUserMedia;
    setDirection('zh','ja');
    for(let i=0;i<30;i++)upsertCaption({session_id:'ui-test',paragraph_id:'one',segment_id:String(i),speaker_id:i<2?'SPEAKER_PENDING':'SPEAKER_00',source_language:'zh',target_language:'ja',start_ms:i*8000,end_ms:(i+1)*8000,original_text:'测试记录：同一人的长段发言持续保留。'.repeat(4),translated_text:'テスト記録：同じ話者の長い発言を保持します。'.repeat(4),is_final:true});
    renderCaptions();
  }""")
  assert page.locator('.caption-row').count()==1
  assert page.locator('.caption-role').count()==2
  assert page.locator('#captions').evaluate('e=>e.scrollHeight>e.clientHeight')
  page.locator('#captions').hover()
  page.mouse.wheel(0,-700)
  page.wait_for_function('document.querySelector("#latestBtn").hidden===false')
  page.screenshot(path=str(out/'continuous-paragraph.png'))
  page.locator('#latestBtn').click()
  assert page.locator('#captions').evaluate('e=>e.scrollHeight-e.scrollTop-e.clientHeight<3')
  page.locator('#clearBtn').click()
  page.locator('#settingsBtn').click()
  page.locator('.service-management summary').click()
  page.locator('#ollamaInstallStatus').get_by_text('未安装',exact=True).wait_for()
  page.locator('.service-management summary').click()
  assert page.locator('#interfaceLanguage').is_visible()
  page.locator('#interfaceLanguage').select_option('ja')
  assert page.locator('#settingsTitle').inner_text()=='モデルとサービスの設定'
  page.locator('#interfaceLanguage').select_option('zh')
  for language in ['zh', 'ja', 'en']:
   page.locator('#interfaceLanguage').select_option(language)
   for w,h in [(1440,900),(1024,768)]:
    page.set_viewport_size({'width':w,'height':h})
    page.locator('#useOllamaDirectoryBtn').scroll_into_view_if_needed()
    box=page.locator('#useOllamaDirectoryBtn').bounding_box()
    assert box and box['x'] >= 0 and box['x']+box['width'] <= w, (language,w,box)
    assert page.locator('.modal-card').last.evaluate('e=>e.scrollWidth <= e.clientWidth')
  page.locator('#interfaceLanguage').select_option('zh')
  page.set_viewport_size({'width':1440,'height':900})
  # Check Apple settings without downloading or touching system speech assets.
  page.locator('#asrEngine').select_option('apple')
  page.wait_for_function('document.querySelector("#asrModel").value === "Apple SpeechAnalyzer"')
  assert not page.locator('#asrServiceField').is_visible()
  assert 'macOS' in page.locator('#asrEngineHint').inner_text()
  assert not apple_installs
  page.locator('#downloadAsrBtn').click()
  page.wait_for_function('document.querySelector("#asrModelStatus").textContent.includes("资源已就绪")')
  assert apple_installs==[['zh','ja']]
  assert page.locator('#downloadAsrBtn').is_disabled()
  for language in ['zh','ja','en']:
   page.locator('#interfaceLanguage').select_option(language)
   assert 'macOS 26' in page.locator('#asrEngineHint').inner_text()
   assert 'Apple' in page.locator('#asrEngine option:checked').inner_text()
   assert 'Apple' in page.locator('#downloadAsrBtn').inner_text()
   assert page.locator('.modal-card').last.evaluate('e=>e.scrollWidth <= e.clientWidth')
  page.locator('#interfaceLanguage').select_option('zh')
  page.locator('#asrSelectionTitle').scroll_into_view_if_needed()
  page.screenshot(path=str(out/'apple-speech-settings.png'))
  apple_fixture.update(available=False,installed=False,message='需要 macOS 26 或更高版本')
  page.locator('#refreshModelsBtn').click()
  page.wait_for_function('document.querySelector("#asrModelStatus").textContent.includes("需要 macOS 26")')
  assert page.locator('#downloadAsrBtn').is_disabled()
  page.locator('#asrEngine').select_option('whisper')
  page.locator('#useOllamaDirectoryBtn').click()
  page.wait_for_function('document.querySelector("#modelDirectory").value === "/test/ollama-models"')
  page.locator('#asrEngine').select_option('ollama')
  page.wait_for_function('document.querySelector("#asrModel").value === "qwen3-asr:1.7b"')
  page.locator('#translationEngine').select_option('llama')
  page.wait_for_function('document.querySelector("#translationModel").value === "translategemma:4b"')
  assert page.locator('#translationServiceUrl').input_value()=='http://127.0.0.1:9931'
  assert page.locator('#asrModel option').all_text_contents()==['qwen3-asr:1.7b']
  assert page.locator('#translationModel option').all_text_contents()==['translategemma:4b']
  page.locator('#modelDirectory').fill('/Volumes/我的硬盘/会议模型')
  page.wait_for_timeout(3300)
  assert page.locator('#modelDirectory').input_value()=='/Volumes/我的硬盘/会议模型'
  page.screenshot(path=str(out/'settings.png'))
  page.locator('#asrSelectionTitle').scroll_into_view_if_needed()
  page.screenshot(path=str(out/'model-selection.png'))
  page.locator('#saveSettingsBtn').click()
  page.wait_for_function('document.querySelector("#systemNotice").textContent.includes("已保存")')
  assert saved_settings[-1]['asr_engine']=='ollama' and saved_settings[-1]['translation_backend']=='llama'
  assert page.locator('#startBtn').is_disabled()
  assert '待重启加载' in page.locator('#asrStatus').inner_text()
  page.keyboard.press('Escape');page.locator('#demoBtn').click()
  assert page.locator('body').evaluate("e=>e.classList.contains('floating-mode')")
  assert page.locator('.caption-row').count()==0
  page.set_viewport_size({'width':900,'height':260})
  page.screenshot(path=str(out/'floating.png'))
  assert page.locator('body').evaluate("e=>e.classList.contains('floating-mode')")
  page.keyboard.press('Escape')
  page.set_viewport_size({'width':390,'height':844})
  page.screenshot(path=str(out/'narrow.png'))
  print('page_errors',errors)
  assert not errors
  browser.close()
finally:
 proc.terminate();proc.wait(timeout=10)
 server_log.close()
