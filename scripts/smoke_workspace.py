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
  page=browser.new_page(viewport={'width':1440,'height':900},color_scheme='dark')
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  health_fixture={'mode':'local','models':{'ready':False,'progress':42,'message':'测试：准备中'}}
  page.route('**/health',lambda route:route.fulfill(json=health_fixture))
  preferences={'show_tips':True}
  def preferences_route(route):
   if route.request.method=='POST':preferences.update(route.request.post_data_json)
   route.fulfill(json=preferences)
  page.route('**/preferences',preferences_route)
  page.route('**/system/check',lambda route:route.fulfill(json={'installed':False,'reachable':False,'recommended_model':'translategemma:4b','recommended_model_present':False,'brew_available':False}))
  saved_settings=[]
  def settings_route(route):
   if route.request.method=='POST':
    saved_settings.append(route.request.post_data_json)
    preferences['setup_completed']=True
    health_fixture.update(asr={'backend':saved_settings[-1]['asr_engine'],'model':saved_settings[-1]['asr_model'],'status':'loading'},models={'ready':False,'stage':'applying','progress':25,'message':'设置已保存，正在应用'},settings={'restart_required':False,'applying':True,'revision':len(saved_settings)-1,'requested_revision':len(saved_settings),**saved_settings[-1]})
    route.fulfill(json={'saved':True,'restart_required':False,'applying':True,'revision':len(saved_settings),'model_dir':saved_settings[-1]['model_dir']})
   else:route.fulfill(json={'model_dir':'/test/models','ollama_model_dir':'/test/ollama-models','asr_engine':'whisper','asr_model':'mlx-community/whisper-medium-mlx-8bit','translation_backend':'ollama','translation_model':'translategemma:4b'})
  page.route('**/settings',settings_route)
  apple_fixture={'available':True,'installed':False,'model':'Apple SpeechAnalyzer','models':['Apple SpeechAnalyzer'],'storage':'macOS','languages':[{'language':language,'installed':False,'status':'missing'} for language in ['zh','ja','en']]}
  apple_installs=[]
  def asset_route(route):
   if 'engine=apple' in route.request.url: route.fulfill(json=apple_fixture)
   else: route.fulfill(json={'installed':True,'model':'mlx-community/whisper-medium-mlx-8bit','models':['mlx-community/whisper-medium-mlx-8bit'],'path':'/test/models/speech'})
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
  assert page.locator('html').get_attribute('data-theme')=='dark'
  page.emulate_media(color_scheme='light')
  page.wait_for_function('document.documentElement.dataset.theme==="light"')
  page.locator('#appearanceToggleBtn').click()
  page.wait_for_function('document.documentElement.dataset.theme==="dark"')
  page.evaluate('appearanceSaveQueue')
  assert preferences['appearance']=='dark'
  page.emulate_media(color_scheme='light')
  assert page.locator('html').get_attribute('data-theme')=='dark'
  for w,h in [(1440,900),(1280,720),(1024,768)]:
   page.set_viewport_size({'width':w,'height':h})
   page.screenshot(path=str(out/f'workspace-{w}.png'))
   assert page.evaluate('document.body.scrollWidth <= innerWidth && document.body.scrollHeight <= innerHeight')
   for selector in ['#startBtn', '#stopBtn', '#demoBtn', '#diagnosticStatus', '#audioStatus', '#clearBtn', '#floatingBtn', '#settingsBtn', '#appearanceToggleBtn']:
    box=page.locator(selector).bounding_box()
    assert box and 0 <= box['x'] and box['x']+box['width'] <= w+1 and 0 <= box['y'] and box['y']+box['height'] <= h+1, (w,h,selector,box)

   for language in ['zh','ja','en']:
    page.evaluate('language=>setInterfaceLanguage(language)',language)
    assert page.title() == 'NMT · Neo Meeting Translater'
    assert page.locator('#settingsBtn').get_attribute('aria-label') == page.locator('#settingsBtn').get_attribute('title')
    assert page.locator('#settingsBtn').get_attribute('title') == {'zh':'本地设置','ja':'ローカル設定','en':'Local settings'}[language]
    assert not page.locator('#startupIntro').is_visible()
    assert page.evaluate('document.body.scrollWidth <= innerWidth && document.body.scrollHeight <= innerHeight')
    assert page.locator('#captions').evaluate('e=>e.clientHeight') > h*.6
    assert not page.locator('#sourceLanguage').is_visible()
    assert not page.locator('#targetLanguage').is_visible()
    page.screenshot(path=str(out/f'workspace-{w}-{language}.png'))
   page.locator('#appearanceToggleBtn').click()
   assert page.locator('html').get_attribute('data-theme')=='light'
   assert page.evaluate('document.body.scrollWidth <= innerWidth && document.body.scrollHeight <= innerHeight')
   page.screenshot(path=str(out/f'workspace-{w}-light.png'),animations='disabled')
   page.locator('#appearanceToggleBtn').click()
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
      constructor() { this.closeListeners=[]; this.readyState=0; queueMicrotask(() => {this.readyState=1; this.onopen?.();}); }
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
      addEventListener(name,callback) {if(name==='close')this.closeListeners.push(callback);}
      close() {if(this.readyState===3)return;this.readyState=3; this.onclose?.();this.closeListeners.forEach(callback=>callback());}
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
  # Change real UI controls during the simulated recording, retaining history.
  page.locator('.direction-button[data-source="zh"][data-target="ja"]').click()
  page.locator('#startBtn').click()
  page.wait_for_function('document.querySelector("#runtimeText").textContent.includes("运行中")')
  page.evaluate("upsertCaption({session_id:'before-switch',paragraph_id:'kept',segment_id:'one',speaker_id:'SPEAKER_00',source_language:'zh',target_language:'ja',start_ms:0,end_ms:600,original_text:'切换前的记录',translated_text:'切り替え前の記録',is_final:true});renderCaptions()")
  page.locator('#settingsBtn').click()
  page.wait_for_function('document.querySelector("#modelDirectory").value === "/test/models" && document.querySelector("#asrModel").value === "mlx-community/whisper-medium-mlx-8bit" && document.querySelector("#asrModel").dataset.selected === ""')
  assert page.locator('#asrEngine').is_enabled()
  assert page.locator('#saveSettingsBtn').is_enabled()
  page.locator('#asrEngine').select_option('ollama')
  page.wait_for_function('document.querySelector("#asrModel").value === "qwen3-asr:1.7b"')
  page.locator('#saveSettingsBtn').click()
  page.wait_for_function('document.querySelector("#modelSaveNotice").textContent.includes("正在自动应用")')
  assert not page.locator('#settingsModal').is_visible()
  assert not page.locator('#tipsModal').is_visible()
  assert page.locator('.caption-row').count()==1
  assert page.locator('#stopBtn').is_enabled()
  health_fixture.update(models={'ready':True,'stage':'ready','progress':100,'message':'测试：新模型就绪'},settings={**health_fixture['settings'],'applying':False,'revision':len(saved_settings)})
  page.evaluate('health=>updateHealth(health)',health_fixture)
  page.wait_for_function('document.querySelector("#runtimeText").textContent.includes("运行中")')
  assert page.locator('.caption-row').count()==1
  assert '切换前的记录' in page.locator('#captions').inner_text()
  page.keyboard.press('Escape')
  page.locator('#stopBtn').click()
  page.wait_for_function('document.querySelector("#startBtn").disabled===false')
  page.locator('#clearBtn').click()
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
  # Appearance must leave the scrolled history and live capture untouched.
  old_scroll=page.locator('#captions').evaluate('e=>e.scrollTop')
  old_rows=page.locator('#captions').inner_text()
  page.locator('#appearanceToggleBtn').click()
  assert page.locator('html').get_attribute('data-theme')=='light'
  assert page.locator('#captions').inner_text()==old_rows
  assert abs(page.locator('#captions').evaluate('e=>e.scrollTop')-old_scroll)<2
  page.locator('#appearanceToggleBtn').click()
  page.locator('#latestBtn').click()
  assert page.locator('#captions').evaluate('e=>e.scrollHeight-e.scrollTop-e.clientHeight<3')
  page.locator('#clearBtn').click()
  page.evaluate('''() => {
    const samples = [
      ['zh', 'ja', 'UI 测试样例：今天先讨论本地会议翻译的使用体验。中文和日语发言会保留在固定的两列里，方便大家连续阅读。', 'UI テスト例：まずはローカル会議翻訳の使い心地について話しましょう。中国語と日本語の発言を固定の二列に残し、続けて読めるようにします。'],
      ['ja', 'zh', '次に、オンライン会議でも字幕を小さなウィンドウで表示したいです。共有画面を隠さずに、必要な情報をすぐ確認できると助かります。', '接下来，希望在线会议也能用一个小窗口显示字幕。这样就能随时查看所需信息，同时不遮挡共享画面。'],
      ['zh', 'ja', '可以。我们会保留整段发言，正在修正时也不清空已有译文。需要查看前面的内容时，只要向上滚动即可。', 'はい。発言全体を残し、修正中も訳文を消しません。前の内容を確認するときは、上にスクロールするだけです。']
    ];
    samples.forEach(([source,target,original,translation],i) => upsertCaption({
      session_id:'design-test',paragraph_id:'turn-'+i,segment_id:'turn-'+i,
      speaker_id:'SPEAKER_0'+(i%2),source_language:source,target_language:target,
      start_ms:i*18000,end_ms:(i+1)*18000,original_text:original,translated_text:translation,is_final:true
    }));
    updateSummary(); renderCaptions();
    runtimeText.textContent='UI 测试';
    modelReadiness.textContent='界面预览 · 未连接真实模型';
    modelReadiness.classList.remove('ready');
    sourceStatus.textContent='未使用麦克风';
    modeStatus.textContent='界面测试';
    asrStatus.textContent='未连接真实模型';
    ollamaStatus.textContent='未连接真实服务';
    ollamaModelStatus.textContent='未连接';
    translationStatus.textContent='样例字幕';
    audioStatus.textContent='未采集音频';
    diagnosticStatus.textContent='仅用于布局验证';
  }''')
  page.evaluate("setAppearance('dark')")
  page.screenshot(path=str(out/'nmt-conversation.png'))
  page.screenshot(path=str(out/'nmt-dark.png'))
  page.locator('#appearanceToggleBtn').click()
  assert page.locator('html').get_attribute('data-theme')=='light'
  assert page.locator('body').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(244, 244, 247)'
  page.wait_for_function('getComputedStyle(document.querySelector("#startBtn")).backgroundColor==="rgb(112, 83, 193)"')
  page.screenshot(path=str(out/'nmt-light.png'),animations='disabled')
  page.locator('#demoBtn').click()
  page.set_viewport_size({'width':900,'height':360})
  assert page.locator('#floatingBtn').get_attribute('aria-pressed') == 'true'
  assert page.locator('#floatingBtn').get_attribute('title') == '退出浮窗'
  page.screenshot(path=str(out/'nmt-floating-light.png'))
  page.evaluate("setAppearance('dark')")
  page.screenshot(path=str(out/'nmt-floating.png'))
  page.screenshot(path=str(out/'nmt-floating-dark.png'))
  page.locator('#floatingBtn').click()
  assert page.locator('#floatingBtn').get_attribute('title') == '字幕浮窗'
  page.set_viewport_size({'width':1440,'height':900})
  page.locator('#clearBtn').click()
  page.locator('#settingsBtn').click()
  page.locator('.service-management summary').click()
  page.locator('#ollamaInstallStatus').get_by_text('未安装',exact=True).wait_for()
  page.locator('.service-management summary').click()
  assert page.locator('#interfaceLanguage').is_visible()
  assert page.locator('#appearanceMode').is_visible()
  for mode in ['light','dark','system']:
   page.locator('#appearanceMode').select_option(mode)
   expected=mode if mode!='system' else 'light'
   assert page.locator('html').get_attribute('data-theme')==expected
   page.locator('#appearanceMode').scroll_into_view_if_needed()
   page.screenshot(path=str(out/f'appearance-settings-{mode}.png'),animations='disabled')
  page.emulate_media(color_scheme='dark')
  page.wait_for_function('document.documentElement.dataset.theme==="dark"')
  assert page.locator('#appearanceMode').input_value()=='system'
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
  assert not page.locator('#settingsModal').is_visible()
  assert page.locator('#settingsBtn').is_visible()
  assert saved_settings[-1]['asr_engine']=='ollama' and saved_settings[-1]['translation_backend']=='llama'
  assert page.locator('#startBtn').is_disabled()
  assert '正在应用' in page.locator('#asrStatus').inner_text()
  assert '重启' not in page.locator('#modelSaveNotice').inner_text()
  health_fixture.update(models={'ready':True,'stage':'ready','progress':100,'message':'测试：新模型就绪'},settings={**health_fixture['settings'],'applying':False,'revision':len(saved_settings)})
  page.evaluate('health=>updateHealth(health)',health_fixture)
  assert '已生效' in page.locator('#modelSaveNotice').inner_text()
  assert page.locator('#startBtn').is_enabled()
  page.keyboard.press('Escape');page.locator('#demoBtn').click()
  assert page.locator('body').evaluate("e=>e.classList.contains('floating-mode')")
  assert page.locator('.caption-row').count()==0
  page.set_viewport_size({'width':900,'height':260})
  page.screenshot(path=str(out/'floating.png'))
  assert page.locator('body').evaluate("e=>e.classList.contains('floating-mode')")
  page.keyboard.press('Escape')
  page.set_viewport_size({'width':390,'height':844})
  page.screenshot(path=str(out/'narrow.png'))
  # A fresh document reads the backend preference, independent of localStorage.
  page.evaluate("setAppearance('light')")
  page.evaluate('appearanceSaveQueue')
  page.evaluate('localStorage.removeItem("appearance")')
  page.reload(wait_until='networkidle')
  page.wait_for_function('document.documentElement.dataset.theme==="light"')
  assert page.evaluate('appearanceMode')=='light'
  assert not page.locator('#tipsModal').is_visible()
  assert not page.locator('#settingsModal').is_visible()
  # Help remains available explicitly, while settings save/restart never opens it.
  page.locator('#tipsBtn').click()
  assert page.locator('#tipsModal').is_visible()
  page.locator('#closeTipsBtn').click()
  page.locator('#tipsModal').wait_for(state='hidden')
  page.set_viewport_size({'width':1440,'height':900})
  page.evaluate("runtimeText.textContent='UI 测试';modelReadiness.textContent='界面预览 · 未连接真实模型';modelReadiness.classList.remove('ready');setDiagnostic('流程测试：保存后自动返回，重新打开不重复提示设置')")
  page.screenshot(path=str(out/'settings-saved-return.png'))
  print('onboarding: successful save returns, restart skips guidance, manual help remains available')
  print('appearance: light/dark/system, toggle, floating, history and reload passed')
  print('page_errors',errors)
  assert not errors
  browser.close()
finally:
 proc.terminate();proc.wait(timeout=10)
 server_log.close()
