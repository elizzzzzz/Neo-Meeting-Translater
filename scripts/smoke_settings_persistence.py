"""Exercise real settings persistence through the UI and a server restart.

Uses a temporary configuration and simulated service catalogues only. No user
preferences, model files, microphone or inference requests are touched.
Run with a Python environment containing Playwright and Chromium.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'frozenlab/qwen3-asr:1.7b'
DIRECTORY = '/Volumes/lmi-regression-unmounted/models'
SERVER = '''
import sys
from pathlib import Path
from meeting_interpreter import system
system.user_config_path = lambda: Path(sys.argv[1])
system.load_user_config()
from meeting_interpreter.app import create_app
import uvicorn
uvicorn.run(create_app(), host='127.0.0.1', port=int(sys.argv[2]), log_level='error')
'''


def start_server(config):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('MEETING_INTERPRETER_')}
    environment.update(PYTHONPATH=str(ROOT / 'src'), MEETING_INTERPRETER_MODE='mock')
    process = subprocess.Popen([sys.executable, '-c', SERVER, str(config), str(port)],
                               cwd=ROOT, env=environment)
    url = f'http://127.0.0.1:{port}'
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url + '/settings', timeout=.3):
                    return process, url
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError('Settings test server exited')
                time.sleep(.1)
        raise RuntimeError('Settings test server startup timed out')
    except BaseException:
        process.terminate()
        process.wait(timeout=10)
        raise


with tempfile.TemporaryDirectory(prefix='lmi-settings-') as temporary, sync_playwright() as playwright:
    config = Path(temporary) / '.env'
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={DIRECTORY}\n'
                      'MEETING_INTERPRETER_ASR_BACKEND=sensevoice\n'
                      'MEETING_INTERPRETER_ASR_MODEL=/old/whisper\n'
                      'MEETING_INTERPRETER_TRANSLATION_BACKEND=nllb\n')
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':1440, 'height':900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/preferences', lambda route: route.fulfill(json={'show_tips':False}))
    page.route('**/system/check', lambda route: route.fulfill(json={'installed':False}))
    page.route('**/services/models?**', lambda route: route.fulfill(json={
        'reachable':True, 'models':[{'id':MODEL, 'asr':True, 'translation':False}]}))
    process, url = start_server(config)
    try:
        page.goto(url, wait_until='networkidle')
        page.evaluate("setInterfaceLanguage('zh')")
        page.locator('#settingsBtn').click()
        page.locator('#asrEngine').select_option('ollama')
        page.wait_for_function('(model) => document.querySelector("#asrModel").value === model', arg=MODEL)
        page.locator('#translationEngine').select_option('llama')
        page.wait_for_function('document.querySelector("#translationModel").value === ""')
        with page.expect_response(lambda response: response.url.endswith('/settings') and response.request.method == 'POST') as saved:
            page.locator('#saveSettingsBtn').click()
        receipt = saved.value.json()
        assert saved.value.ok and receipt['saved'], receipt
        assert receipt['settings']['asr_model'] == MODEL
        assert receipt['settings']['model_dir_exists'] is False
        page.wait_for_function('document.querySelector("#modelSaveNotice").textContent.includes("已保存")')
        assert '目录当前不可用' in page.locator('#modelSaveNotice').inner_text()
        page.keyboard.press('Escape')
        page.locator('#settingsBtn').click()
        page.wait_for_function('(model) => document.querySelector("#asrModel").value === model', arg=MODEL)
        assert page.locator('#asrEngine').input_value() == 'ollama'
        print('UI save and settings reopen: verified')
        process.terminate()
        process.wait(timeout=10)
        process, url = start_server(config)
        page.goto(url, wait_until='networkidle')
        page.locator('#settingsBtn').click()
        page.wait_for_function('(model) => document.querySelector("#asrModel").value === model', arg=MODEL)
        assert page.locator('#asrEngine').input_value() == 'ollama'
        assert page.locator('#translationEngine').input_value() == 'llama'
        assert page.locator('#translationModel').input_value() == ''
        assert page.locator('#modelDirectory').input_value() == DIRECTORY
        health = page.request.get(url + '/health').json()
        assert health['asr']['backend'] == 'ollama' and health['asr']['model'] == MODEL
        assert 'MEETING_INTERPRETER_ASR_MODEL=' not in config.read_text()
        assert not Path(DIRECTORY).exists()
        assert not errors, errors
        print('Fresh server, runtime selection and UI readback: verified')
    finally:
        browser.close()
        process.terminate()
        process.wait(timeout=10)
