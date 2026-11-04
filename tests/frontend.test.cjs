const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadApp() {
  const elements = new Map();
  const requests = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      id, textContent: '', value: '', hidden: true, disabled: false, checked: false,
      options: [{textContent: '中文'}], selectedIndex: 0, dataset: {},
      classList: {toggle(){}, add(){}, remove(){}},
      addEventListener(){}, focus(){}, contains(){return false;},
      querySelector(){return null;}, querySelectorAll(){return [];},
    });
    return elements.get(id);
  }
  const document = {
    querySelector: (s) => element(s), querySelectorAll: () => [],
    addEventListener(){}, body: element('body'), activeElement: null,
  };
  const context = vm.createContext({
    document, window: {}, navigator: {}, console,
    location: {host:'127.0.0.1:8000', protocol:'http:'},
    WebSocket: {OPEN:1, CONNECTING:0}, Date,
    btoa: value=>Buffer.from(value,'binary').toString('base64'),
    setInterval: () => 1, clearInterval(){}, setTimeout: () => 1, clearTimeout(){},
    localStorage: {getItem(){return null;},setItem(){}},
    fetch: async (url, options) => {
      requests.push({url, options});
      const payload = url === '/preferences' ? {show_tips:false} : url === '/health' ? {mode:'mock',models:{ready:true}} : {};
      return {ok:true, json:async()=>payload};
    },
  });
  vm.runInContext(fs.readFileSync('web/app.js','utf8'), context);
  return {elements, context, requests, run:(code)=>vm.runInContext(code,context)};
}

test('health refresh preserves a folder the user is editing', () => {
  const app = loadApp();
  app.elements.get('#modelDirectory').value = '/Volumes/外置硬盘/我的模型';
  app.run("updateHealth({mode:'mock', models:{ready:true}, settings:{model_dir:'/old-cache'}})");
  assert.equal(app.elements.get('#modelDirectory').value, '/Volumes/外置硬盘/我的模型');
});

test('preview never reports hot models and local warmup failure disables recording', () => {
  const app = loadApp();
  app.run("updateHealth({mode:'mock', models:{ready:true}})");
  assert.doesNotMatch(app.elements.get('#modelReadiness').textContent, /热启动/);
  app.elements.get('#startBtn').disabled=false;
  app.run("updateHealth({mode:'local', models:{ready:false,stage:'error',message:'模型未连接'}})");
  assert.equal(app.elements.get('#startBtn').disabled, true);
});

test('tip dismissal is saved to local preferences independently of the service port', async () => {
  const app = loadApp();
  app.elements.get('#rememberTips').checked = true;
  await app.run('closeTips()');
  const save = app.requests.find(r=>r.url==='/preferences' && r.options?.method==='POST');
  assert.ok(save);
  assert.deepEqual(JSON.parse(save.options.body), {show_tips:false});
});

test('subtitle preview produces a revision with the same id without a microphone', () => {
  const app = loadApp();
  app.run("sourceLanguage.value='zh';targetLanguage.value='ja';startDemo();");
  const first=app.run('JSON.stringify(captionRows)');
  assert.equal(JSON.parse(first).length, 1);
  app.run('advanceDemo()');
  const second=JSON.parse(app.run('JSON.stringify(captionRows)'));
  assert.equal(second.length, 1);
  assert.equal(second[0].segment_id, JSON.parse(first)[0].segment_id);
  assert.equal(second[0].is_final, true);
});

test('native export uses the macOS save dialog bridge', () => {
  const app = loadApp();
  const messages=[];
  app.context.window.webkit={messageHandlers:{native:{postMessage:message=>messages.push(message)}}};
  app.run("sourceLanguage.value='zh';targetLanguage.value='ja';startDemo();advanceDemo();exportTranscript();");
  assert.equal(messages.length,1);
  assert.equal(messages[0].type,'export_transcript');
  assert.match(messages[0].text,/今天我们/);
  assert.match(messages[0].text,/今日は/);
});

test('permission refresh preserves the actual microphone and reveals its name', async () => {
  const app = loadApp();
  app.context.navigator.mediaDevices = {enumerateDevices: async () => [
    {kind:'audioinput', deviceId:'builtin', label:'MacBook 麦克风'},
    {kind:'audioinput', deviceId:'loopback', label:'BlackHole 2ch'},
  ]};
  app.elements.get('#inputDevice').value='builtin';
  app.context.activeTrack={getSettings:()=>({deviceId:'loopback'}),label:'BlackHole 2ch'};
  await app.run('loadDevices(activeTrack)');
  assert.equal(app.elements.get('#inputDevice').value,'loopback');
  assert.equal(app.elements.get('#sourceStatus').textContent,'BlackHole 2ch');
  app.run('updateSummary()');
  assert.equal(app.elements.get('#sourceStatus').textContent,'BlackHole 2ch');
});

test('input level distinguishes silence and audible input without dropping quiet speech', () => {
  const app = loadApp();
  app.run('updateInputLevel(new Float32Array(1600))');
  assert.match(app.elements.get('#inputLevelStatus').textContent,/无输入|静音/);
  app.run('updateInputLevel(new Float32Array(1600).fill(.03))');
  assert.match(app.elements.get('#inputLevelStatus').textContent,/收到声音/);
});

test('recording locks language controls and displays the server-confirmed decoder language', async () => {
  const app = loadApp();
  app.context.navigator.mediaDevices={getUserMedia:async()=>{}};
  app.context.WebSocket=class {
    static OPEN=1;static CONNECTING=0;
    constructor(){this.readyState=1;}
  };
  app.run("runtimeMode='LOCAL'; modelsReady=true;sourceLanguage.value='zh';targetLanguage.value='ja';");
  await app.run('startSession()');
  assert.equal(app.elements.get('#sourceLanguage').disabled,true);
  assert.equal(app.elements.get('#swapLanguages').disabled,true);
  assert.match(app.elements.get('#recognitionLanguageStatus').textContent,/等待服务确认/);
  app.run("socket.onmessage({data:JSON.stringify({type:'configured',source_language:'zh',asr_language:'zh',target_language:'ja'})})");
  assert.equal(app.elements.get('#recognitionLanguageStatus').textContent,'已锁定中文');
  app.run('socket.onclose()');
  assert.equal(app.elements.get('#sourceLanguage').disabled,false);
});

test('slow inference keeps one audio packet in flight and a bounded recent window', () => {
  const app=loadApp();const sent=[];
  app.context.sent=sent;
  app.run("socket={readyState:WebSocket.OPEN, send:message=>sent.push(JSON.parse(message))}; activeInputLabel='MacBook 麦克风'");
  app.run('for(let i=0;i<100;i++) queueAudioFrame(new Float32Array(1600).fill(.03));');
  assert.equal(sent.length,1);
  assert.ok(app.run('pendingAudio.length') <= 64000);
  assert.match(app.elements.get('#audioStatus').textContent,/已跳过/);
  app.run('audioInFlight=false;sendPendingAudio()');
  assert.equal(sent.length,2);
  assert.equal(app.run('pendingAudio.length'),0);
});
