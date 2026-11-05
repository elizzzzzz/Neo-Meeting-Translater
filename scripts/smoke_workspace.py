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
  page.locator('#settingsBtn').click();page.locator('#ollamaInstallStatus').get_by_text('未安装',exact=True).wait_for()
  assert page.locator('#interfaceLanguage').is_visible()
  page.locator('#interfaceLanguage').select_option('ja')
  assert page.locator('#settingsTitle').inner_text()=='モデルと Ollama の設定'
  page.locator('#interfaceLanguage').select_option('zh')
  page.locator('#modelDirectory').fill('/Volumes/我的硬盘/会议模型')
  page.wait_for_timeout(3300)
  assert page.locator('#modelDirectory').input_value()=='/Volumes/我的硬盘/会议模型'
  page.screenshot(path=str(out/'settings.png'))
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
