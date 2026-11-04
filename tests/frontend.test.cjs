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

test('local settings save the selected speech engine with its model directory', async () => {
  const app = loadApp();
  app.elements.get('#modelDirectory').value = '/models';
  app.elements.get('#asrEngine').value = 'sensevoice';
  await app.run('saveModelDirectory()');
  const request = app.requests.find(r=>r.url==='/settings' && r.options?.method==='POST');
  assert.deepEqual(JSON.parse(request.options.body), {model_dir:'/models',asr_engine:'sensevoice'});
});

test('preview never reports hot models and local warmup failure disables recording', () => {
  const app = loadApp();
  app.run("updateHealth({mode:'mock', models:{ready:true}})");
  assert.doesNotMatch(app.elements.get('#modelReadiness').textContent, /热启动/);
  app.elements.get('#startBtn').disabled=false;
  app.run("updateHealth({mode:'local', models:{ready:false,stage:'error',message:'模型未连接'}})");
  assert.equal(app.elements.get('#startBtn').disabled, true);
});

test('warmup completion clears the loading diagnostic while preserving later session messages', () => {
  const app = loadApp();
  app.run("updateHealth({mode:'local',models:{ready:false,message:'正在启动翻译模型'}})");
  app.run("updateHealth({mode:'local',models:{ready:true,message:'模型已就绪，可开始会议'}})");
  assert.equal(app.elements.get('#diagnosticStatus').textContent, '模型已就绪，可开始会议');
  app.run("setDiagnostic('已识别原文，翻译处理中');updateHealth({mode:'local',models:{ready:true}})");
  assert.equal(app.elements.get('#diagnosticStatus').textContent, '已识别原文，翻译处理中');
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

test('slow inference preserves every captured sample and reports backlog', () => {
  const app=loadApp();const sent=[];app.context.sent=sent;
  app.run("socket={readyState:WebSocket.OPEN,send:message=>sent.push(JSON.parse(message))};activeInputLabel='MacBook 麦克风'");
  app.run('for(let i=0;i<100;i++) queueAudioFrame(new Float32Array(1600).fill(.03));');
  assert.equal(sent.length,1);
  assert.equal(app.run('pendingAudio.length'),158400);
  assert.doesNotMatch(app.elements.get('#audioStatus').textContent,/已跳过/);
  for(let i=0;i<100;i++) app.run('audioInFlight=false;sendPendingAudio()');
  assert.equal(sent.reduce((n,e)=>n+Buffer.from(e.audio_base64,'base64').length/2,0),160000);
  assert.equal(app.run('pendingAudio.length'),0);
});

test('same speaker retains complete speech across chunks and pauses, next speaker starts a paragraph', () => {
  const app=loadApp();
  app.run(`
    for (const event of [
      {session_id:'mic', segment_id:'1', speaker_id:'SPEAKER_00', original_text:'今天讨论项目。', translated_text:'Today we discuss the project.', start_ms:0, end_ms:8000, is_final:true},
      {session_id:'mic', segment_id:'2', speaker_id:'SPEAKER_00', original_text:'预算是三万元。', translated_text:'The budget is thirty thousand yuan.', start_ms:8000, end_ms:16000, is_final:true},
      {session_id:'mic', segment_id:'3', speaker_id:'SPEAKER_01', original_text:'我同意。', translated_text:'I agree.', start_ms:17000, end_ms:18000, is_final:true},
      {session_id:'mic', segment_id:'4', speaker_id:'SPEAKER_00', original_text:'谢谢。', translated_text:'Thank you.', start_ms:19000, end_ms:20000, is_final:true},
    ]) upsertCaption(event);
  `);
  const paragraphs=JSON.parse(app.run('JSON.stringify(transcriptParagraphs())'));
  assert.equal(paragraphs.length,3);
  assert.match(paragraphs[0].original_text,/今天讨论项目。.*预算是三万元。/s);
  assert.match(paragraphs[0].translated_text,/Today.*thirty thousand/s);
  assert.equal(paragraphs[2].original_text,'谢谢。');
});

test('revising the current chunk preserves older speech and its last translation until corrected translation arrives', () => {
  const app=loadApp();
  app.run(`
    upsertCaption({session_id:'m',segment_id:'1',speaker_id:'SPEAKER_PENDING',original_text:'前一句保留。',translated_text:'Previous sentence.',is_final:true});
    upsertCaption({session_id:'m',segment_id:'2',speaker_id:'SPEAKER_PENDING',original_text:'项目预算三千元。',translated_text:'Three thousand yuan.',is_final:true});
    upsertCaption({session_id:'m',segment_id:'2',speaker_id:'SPEAKER_PENDING',original_text:'项目预算三万元。',translated_text:'',is_final:false});
  `);
  const paragraph=JSON.parse(app.run('JSON.stringify(transcriptParagraphs()[0])'));
  assert.match(paragraph.original_text,/前一句保留。.*三万元。/s);
  assert.match(paragraph.translated_text,/Previous.*Three thousand/s);
  assert.equal(app.run('captionRows.length'),2);
  app.run("upsertCaption({session_id:'m',segment_id:'2',speaker_id:'SPEAKER_PENDING',original_text:'项目预算三万元。',translated_text:'Thirty thousand yuan.',is_final:true});");
  assert.match(app.run('transcriptParagraphs()[0].translated_text'),/Thirty thousand/);
  assert.doesNotMatch(app.run('transcriptParagraphs()[0].translated_text'),/Three thousand/);
});

test('new captions do not pull a reader away from history, returning to latest resumes following', () => {
  const app=loadApp();
  const list=app.elements.get('#captions');
  list.scrollHeight=1600;list.clientHeight=500;list.scrollTop=240;
  app.run("followCaptions=false;upsertCaption({session_id:'m',segment_id:'1',speaker_id:'A',original_text:'历史',translated_text:'History',start_ms:0,is_final:true});renderCaptions();");
  assert.equal(list.scrollTop,240);
  assert.equal(app.elements.get('#latestBtn').hidden,false);
  app.run('returnToLatest()');
  assert.equal(list.scrollTop,1600);
  assert.equal(app.elements.get('#latestBtn').hidden,true);
});

test('manual boundary sends captured audio before changing speaker and later audio afterwards', () => {
  const app=loadApp();const sent=[];app.context.sent=sent;
  app.run("socket={readyState:WebSocket.OPEN,send:message=>sent.push(JSON.parse(message))};queueAudioFrame(new Float32Array(1600).fill(.01));queueAudioFrame(new Float32Array(1600).fill(.02));requestSpeakerChange();queueAudioFrame(new Float32Array(1600).fill(.03));");
  app.run('audioInFlight=false;sendPendingAudio()');
  assert.deepEqual(sent.map(e=>e.type),['audio','audio']);
  app.run('audioInFlight=false;sendPendingAudio()');
  assert.deepEqual(sent.map(e=>e.type),['audio','audio','speaker_change']);
  app.run('audioInFlight=false;sendPendingAudio()');
  assert.deepEqual(sent.map(e=>e.type),['audio','audio','speaker_change','audio']);
});

test('stopping drains queued audio before requesting final recognition', () => {
  const app=loadApp();const sent=[];app.context.sent=sent;
  app.run("socket={readyState:WebSocket.OPEN,send:message=>sent.push(JSON.parse(message)),close:()=>sent.push({type:'closed'})};queueAudioFrame(new Float32Array(1600));queueAudioFrame(new Float32Array(1600));stopSession();");
  assert.deepEqual(sent.map(e=>e.type),['audio']);
  app.run('audioInFlight=false;sendPendingAudio()');
  assert.deepEqual(sent.map(e=>e.type),['audio','audio']);
  app.run('audioInFlight=false;sendPendingAudio()');
  assert.deepEqual(sent.map(e=>e.type),['audio','audio','finish']);
});

test('starting recording again cannot overwrite the previous recording with reused segment ids', async () => {
  const app=loadApp();
  app.context.navigator.mediaDevices={getUserMedia:async()=>{}};
  app.context.WebSocket=class {static OPEN=1;static CONNECTING=0;constructor(){this.readyState=1;}};
  app.run("runtimeMode='LOCAL';modelsReady=true;");
  await app.run('startSession()');
  const first=app.run('captureSessionId');
  app.run('socket.readyState=3;socket.onclose();');
  await app.run('startSession()');
  assert.notEqual(app.run('captureSessionId'),first);
});

test('manual speaker changes remain available when no audio is waiting', () => {
  const app=loadApp();const sent=[];app.context.sent=sent;
  app.run("socket={readyState:WebSocket.OPEN,send:message=>sent.push(JSON.parse(message))};requestSpeakerChange();audioInFlight=false;requestSpeakerChange();");
  assert.deepEqual(sent.map(e=>e.type),['speaker_change','speaker_change']);
});

test('backlog remains visible across health refreshes instead of claiming realtime', async () => {
  const app=loadApp();
  app.context.navigator.mediaDevices={getUserMedia:async()=>{}};
  app.context.WebSocket=class {static OPEN=1;static CONNECTING=0;constructor(){this.readyState=1;}};
  app.run("runtimeMode='LOCAL';modelsReady=true");await app.run('startSession()');
  app.run("socket.onmessage({data:JSON.stringify({type:'audio_status',state:'sound',queued_audio_ms:3200})})");
  app.run("socket.onmessage({data:JSON.stringify({type:'translation_status',state:'processing',pending_translations:4})})");
  app.run("updateHealth({mode:'local',models:{ready:true,progress:100},asr:{status:'ready'},translation:{status:'processing'},audio:{frames:999}})");
  assert.match(app.elements.get('#audioStatus').textContent,/3\.2 秒/);
  assert.match(app.elements.get('#translationStatus').textContent,/4 段/);
});


test('microphone opens only after the selected language has finished warming', async () => {
  const app=loadApp(); let opened=0;
  app.context.navigator.mediaDevices={getUserMedia:async()=>{opened++;throw new Error('test permission');}};
  app.context.WebSocket=class {
    static OPEN=1;static CONNECTING=0;
    constructor(){this.readyState=1;} send(){} close(){this.readyState=3;}
  };
  app.run("runtimeMode='LOCAL';modelsReady=true;sourceLanguage.value='zh';targetLanguage.value='ja'");
  await app.run('startSession()');
  const opening=app.run('socket.onopen()');
  await Promise.resolve();
  assert.equal(opened,0,'language setup must not record speech into a cold recognizer');
  app.run("socket.onmessage({data:JSON.stringify({type:'configured',asr_language:'zh'})})");
  await opening;
  assert.equal(opened,1);
});


test('canceling language warmup never opens the microphone', async () => {
  const app=loadApp(); let opened=0;
  app.context.navigator.mediaDevices={getUserMedia:async()=>{opened++;}};
  app.context.WebSocket=class {
    static OPEN=1;static CONNECTING=0;
    constructor(){this.readyState=1;} send(){} close(){this.readyState=3;this.onclose();}
  };
  app.run("runtimeMode='LOCAL';modelsReady=true"); await app.run('startSession()');
  const opening=app.run('socket.onopen()');
  app.run('stopSession()'); await opening;
  assert.equal(opened,0); assert.equal(app.elements.get('#sourceLanguage').disabled,false);
});
