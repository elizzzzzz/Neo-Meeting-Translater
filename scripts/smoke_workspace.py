"""Model-free UI smoke check. Requires Playwright with Chromium installed.

Run: python scripts/smoke_workspace.py
Does not download weights, open the microphone or change user preferences.
"""
import json, os, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
out=root/'artifacts/ui-review';out.mkdir(parents=True,exist_ok=True)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
smoke_env = dict(os.environ, PYTHONPATH=str(root / 'src'), MEETING_INTERPRETER_MODE='mock', MEETING_INTERPRETER_TRANSLATION_BACKEND='nllb')
proc=subprocess.Popen([sys.executable,'-m','uvicorn','meeting_interpreter.app:app','--host','127.0.0.1','--port',str(port),'--log-level','error'],cwd=root,env=smoke_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for i in range(100):
  try:urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=.3);break
  except OSError:time.sleep(.1)
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page(viewport={'width':1440,'height':900})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/preferences',lambda route:route.fulfill(json={'show_tips':True}))
  page.route('**/system/check',lambda route:route.fulfill(json={'installed':False,'reachable':False,'recommended_model':'translategemma:4b','recommended_model_present':False,'brew_available':False}))
  page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
  page.locator('#tipsModal').wait_for(state='visible')
  page.screenshot(path=str(out/'tips.png'))
  page.locator('#closeTipsBtn').click()
  for w,h in [(1440,900),(1280,720),(1024,768)]:
   page.set_viewport_size({'width':w,'height':h})
   page.screenshot(path=str(out/f'workspace-{w}.png'))
   assert page.evaluate('document.body.scrollWidth <= innerWidth && document.body.scrollHeight <= innerHeight')
   for selector in ['#startBtn', '#stopBtn', '#demoBtn', '#diagnosticStatus', '#audioStatus', '#clearBtn', '#floatingBtn', 'footer']:
    box=page.locator(selector).bounding_box()
    assert box and 0 <= box['x'] and box['x']+box['width'] <= w+1 and 0 <= box['y'] and box['y']+box['height'] <= h+1, (w,h,selector,box)

   print('layout',w,h,page.evaluate('({width:innerWidth,height:innerHeight,scrollW:document.body.scrollWidth,scrollH:document.body.scrollHeight,footer:document.querySelector("footer").getBoundingClientRect().bottom,captions:document.querySelector("#captions").clientHeight})'))
  page.set_viewport_size({'width':1440,'height':900})
  page.locator('#settingsBtn').click();page.locator('#ollamaInstallStatus').get_by_text('未安装',exact=True).wait_for()
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
