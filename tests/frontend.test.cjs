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
  app.elements.get('#asrModel').value = 'SenseVoice-Small';
  app.elements.get('#translationEngine').value = 'llama';
  app.elements.get('#translationModel').value = 'local-translate';
  app.elements.get('#translationServiceUrl').value = 'http://127.0.0.1:9931';
  await app.run('saveModelDirectory()');
  const request = app.requests.find(r=>r.url==='/settings' && r.options?.method==='POST');
  assert.deepEqual(JSON.parse(request.options.body), {model_dir:'/models',asr_engine:'sensevoice',asr_model:'SenseVoice-Small',asr_url:'',translation_backend:'llama',translation_model:'local-translate',translation_url:'http://127.0.0.1:9931'});
});

test('health refresh failure does not relabel saved settings as a save failure', async () => {
  const app = loadApp();
  await new Promise(resolve => setImmediate(resolve));
  app.elements.get('#modelDirectory').value = '/models';
  app.context.fetch = async url => {
    if (url === '/health') throw new Error('connection reset');
    return {ok:true, json:async()=>({saved:true, settings:{model_dir_exists:true}})};
  };
  await app.run('saveModelDirectory()');
  assert.match(app.elements.get('#modelSaveNotice').textContent, /已保存/);
  assert.equal(app.elements.get('#modelSaveNotice').className, 'model-save-notice good');
});

test('persisted unavailable directory is reported separately from save success', async () => {
  const app = loadApp();
  await new Promise(resolve => setImmediate(resolve));
  app.elements.get('#modelDirectory').value = '/Volumes/offline/models';
  app.context.fetch = async url => ({ok:true, json:async()=>url === '/health' ? {mode:'mock',models:{ready:false}} : {saved:true,settings:{model_dir_exists:false}}});
  await app.run('saveModelDirectory()');
  const notice = app.elements.get('#modelSaveNotice');
  assert.match(notice.textContent, /已保存/);
  assert.match(notice.textContent, /目录.*不可用/);
});

test('speech and translation discover separate compatible models without loading them', async () => {
  const app=loadApp();
  app.context.fetch=async url=>({ok:true,json:async()=>({reachable:true,models:[
    {id:'qwen3-asr',asr:true,translation:false}, {id:'translategemma',asr:false,translation:true},
  ]})});
  app.run("asrEngine.value='ollama';translationEngine.value='llama';");
  await app.run('refreshModelSelections()');
  assert.equal(app.elements.get('#asrModel').value,'qwen3-asr');
  assert.equal(app.elements.get('#translationModel').value,'translategemma');
  assert.doesNotMatch(app.elements.get('#translationModel').innerHTML,/qwen3-asr/);
  assert.equal(app.elements.get('#asrServiceUrl').value,'http://127.0.0.1:11434');
  assert.equal(app.elements.get('#translationServiceUrl').value,'http://127.0.0.1:9931');
  assert.equal(app.elements.get('#downloadAsrBtn').hidden,true);
});

test('late model discovery cannot overwrite a newer provider selection', async () => {
  const app=loadApp();let resolve;
  app.context.fetch=async url=>{
    if(url.includes('provider=ollama')) return new Promise(r=>resolve=()=>r({ok:true,json:async()=>({reachable:true,models:[{id:'stale',asr:true}]})}));
    return {ok:true,json:async()=>({reachable:true,models:[{id:'new',asr:true}]})};
  };
  app.run("asrEngine.value='ollama'");
  const pending=app.run("refreshModelSelection('asr')");
  app.run("asrEngine.value='llama';asrServiceUrl.value='http://127.0.0.1:9931'");
  await app.run("refreshModelSelection('asr')");
  resolve();await pending;
  assert.equal(app.elements.get('#asrModel').value,'new');
});

test('empty service lists do not claim a model is ready', async () => {
  const app=loadApp();
  app.context.fetch=async()=>({ok:true,json:async()=>({reachable:true,models:[]})});
  app.run("translationEngine.value='llama'");
  await app.run("refreshModelSelection('translation')");
  assert.equal(app.elements.get('#translationModel').value,'');
  assert.match(app.elements.get('#translationModelStatus').textContent,/未发现适用模型/);
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

test('short transport stalls preserve audio and include its capture time', () => {
  const app=loadApp();const sent=[];app.context.sent=sent;
  app.run("socket={readyState:WebSocket.OPEN,send:message=>sent.push(JSON.parse(message))};activeInputLabel='MacBook 麦克风'");
  app.run('for(let i=0;i<30;i++) queueAudioFrame(new Float32Array(1600).fill(.03));');
  assert.equal(sent.length,1);
  assert.equal(app.run('pendingAudio.length'),46400);
  assert.ok(sent[0].captured_at_ms <= Date.now());
  assert.doesNotMatch(app.elements.get('#audioStatus').textContent,/已跳过/);
  for(let i=0;i<100;i++) app.run('audioInFlight=false;sendPendingAudio()');
  assert.equal(sent.reduce((n,e)=>n+Buffer.from(e.audio_base64,'base64').length/2,0),48000);
  assert.equal(app.run('pendingAudio.length'),0);
});

test('long transport stalls discard old audio without pausing the microphone', () => {
  const app=loadApp(); const sent=[]; app.context.sent=sent;
  app.run("socket={readyState:WebSocket.OPEN,send:message=>sent.push(JSON.parse(message))};for(let i=0;i<100;i++) queueAudioFrame(new Float32Array(1600).fill(.03));");
  assert.ok(app.run('pendingAudio.length') <= 64000);
  assert.equal(app.run('sessionEnding'), false);
  assert.match(app.elements.get('#diagnosticStatus').textContent, /跳过旧音频/);
  const messages=[];
  app.context.window.webkit={messageHandlers:{native:{postMessage:message=>messages.push(message)}}};
  app.run('cleanupAudio();exportTranscript();');
  assert.match(messages[0].text, /可能不完整/);
});

test('preparation intro disappears only for real ready models and returns on failure', () => {
  const app=loadApp();
  app.run("updateHealth({mode:'local',models:{ready:false,progress:42,message:'加载中'}})");
  assert.equal(app.elements.get('#startupIntro').hidden, false);
  assert.equal(app.elements.get('#startupProgress').value, 42);
  app.run("updateHealth({mode:'local',models:{ready:true,progress:100}})");
  assert.equal(app.elements.get('#startupIntro').hidden, true);
  app.run("updateHealth({mode:'local',models:{ready:false,stage:'error'}})");
  assert.equal(app.elements.get('#startupIntro').hidden, false);
});

test('timed out translations stop waiting, retain original text and reject late output', () => {
  const app=loadApp();
  app.run(`
    setDirection('zh','ja');
    upsertCaption({session_id:'m',segment_id:'1',speaker_id:'A',source_language:'zh',target_language:'ja',original_text:'请确认时间',translated_text:'',end_ms:800,is_final:false});
    upsertCaption({session_id:'m',segment_id:'1',speaker_id:'A',source_language:'zh',target_language:'ja',original_text:'请确认时间',translated_text:'',end_ms:800,is_final:true,skipped_stage:'translation'});
    upsertCaption({session_id:'m',segment_id:'1',speaker_id:'A',source_language:'zh',target_language:'ja',original_text:'请确认时间',translated_text:'迟到的译文',end_ms:800,is_final:true});
    renderCaptions();
  `);
  assert.match(app.elements.get('#captions').innerHTML,/请确认时间/);
  assert.match(app.elements.get('#captions').innerHTML,/超时已跳过/);
  assert.doesNotMatch(app.elements.get('#captions').innerHTML,/迟到的译文|译文更新中/);
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

for (const [left, right] of [['zh', 'ja'], ['zh', 'en'], ['en', 'ja']]) {
  test(`${left}/${right} keeps language columns fixed in both directions and filters by role`, () => {
    const app = loadApp();
    app.run(`setDirection('${left}', '${right}');`);
    assert.equal(app.run('sourceLanguage.value'), 'auto');
    assert.equal(app.run('selectedLanguagePair'), `${left}-${right}`);
    app.run(`
      upsertCaption({session_id:'pair',segment_id:'1',speaker_id:'A',language_pair:'${left}-${right}',source_language:'${left}',target_language:'${right}',original_text:'left source',translated_text:'right translated',is_final:true});
      upsertCaption({session_id:'pair',segment_id:'2',speaker_id:'A',language_pair:'${left}-${right}',source_language:'${right}',target_language:'${left}',original_text:'right source',translated_text:'left translated',is_final:true});
      renderCaptions();
    `);
    const columns = JSON.parse(app.run('JSON.stringify(bilingualColumns(transcriptParagraphs()[0].chunks))'));
    assert.deepEqual(columns.left.map(part=>part.text), ['left source', 'left translated']);
    assert.deepEqual(columns.right.map(part=>part.text), ['right translated', 'right source']);
    assert.deepEqual(columns.left.map(part=>part.role), ['源', '译']);
    assert.deepEqual(columns.right.map(part=>part.role), ['译', '源']);
    assert.equal(app.run('transcriptParagraphs().length'), 1);
    app.run("captionDisplayMode.value='source';renderCaptions()");
    const source = app.elements.get('#captions').innerHTML;
    assert.match(source, /left source/); assert.match(source, /right source/);
    assert.doesNotMatch(source, /left translated|right translated/);
    app.run("captionDisplayMode.value='translation';renderCaptions()");
    const translated = app.elements.get('#captions').innerHTML;
    assert.match(translated, /left translated/); assert.match(translated, /right translated/);
    assert.doesNotMatch(translated, /left source|right source/);
  });

  test(`${left}/${right} sends bidirectional configuration and confirms automatic recognition`, async () => {
    const app = loadApp(); const sent=[];
    app.context.navigator.mediaDevices={getUserMedia:async()=>{throw new Error('test permission');}};
    app.context.WebSocket=class {
      static OPEN=1;static CONNECTING=0;
      constructor(){this.readyState=1;} send(message){sent.push(JSON.parse(message));} close(){this.readyState=3;}
    };
    app.run(`runtimeMode='LOCAL';modelsReady=true;setDirection('${left}','${right}');`);
    await app.run('startSession()');
    const opening=app.run('socket.onopen()');
    assert.equal(sent[0].language_pair, `${left}-${right}`);
    assert.equal(sent[0].source_language, 'auto');
    app.run(`socket.onmessage({data:JSON.stringify({type:'configured',asr_language:'auto',language_pair:'${left}-${right}'})});`);
    await opening;
    assert.match(app.elements.get('#recognitionLanguageStatus').textContent, /自动识别/);
  });
}

test('switching meeting languages leaves historical columns and source/translation labels intact', () => {
  const app=loadApp();
  app.run(`
    upsertCaption({session_id:'old',segment_id:'1',speaker_id:'A',language_pair:'en-ja',source_language:'ja',target_language:'en',original_text:'日本語です',translated_text:'English text',is_final:true});
    setDirection('zh','en');
  `);
  const columns=JSON.parse(app.run('JSON.stringify(bilingualColumns(transcriptParagraphs()[0].chunks))'));
  assert.equal(columns.leftLanguage,'en');assert.equal(columns.rightLanguage,'ja');
  assert.equal(columns.left[0].role,'译');assert.equal(columns.right[0].role,'源');
});

test('a superseded translation revision never replaces the latest caption', () => {
  const app=loadApp();
  app.run(`
    upsertCaption({session_id:'m',segment_id:'1',source_language:'en',target_language:'ja',original_text:'latest words',translated_text:'最新',is_final:false});
    upsertCaption({session_id:'m',segment_id:'1',source_language:'en',target_language:'ja',original_text:'latest words',translated_text:'obsolete',translation_source_text:'old words',is_final:true});
  `);
  assert.equal(app.run('captionRows[0].translated_text'),'最新');
});

test('interface language auto-detects Japanese and English while keeping caption pairs stable', () => {
  const app = loadApp();
  app.context.navigator.language = 'ja-JP';
  app.run("interfaceLanguage.value='auto'; applyInterfaceLanguage();");
  assert.equal(app.run('activeInterfaceLanguage()'), 'ja');
  assert.equal(app.run("uiText('actions.startAudio')"), '音声入力を開始');
  assert.equal(app.run("languageDisplayLabel('zh')"), '中国語');
  app.run("setInterfaceLanguage('en');");
  assert.equal(app.run('activeInterfaceLanguage()'), 'en');
  assert.equal(app.run("uiText('actions.startAudio')"), 'Start audio input');
  assert.equal(app.run("selectedLanguagePair"), 'zh-ja');
});

test('interface language switching does not rewrite transcript content', () => {
  const app = loadApp();
  app.run("upsertCaption({session_id:'i18n',segment_id:'1',speaker_id:'A',language_pair:'zh-ja',source_language:'zh',target_language:'ja',original_text:'中文原文',translated_text:'日本語訳',is_final:true}); renderCaptions(); setInterfaceLanguage('en'); renderCaptions();");
  assert.match(app.elements.get('#captions').innerHTML, /中文原文/);
  assert.match(app.elements.get('#captions').innerHTML, /日本語訳/);
});

test('model preview scans the edited folder and selects the resolved local model', async () => {
  const app=loadApp(); const urls=[];
  app.context.fetch=async url=>{urls.push(url);return {ok:true,json:async()=>({installed:true,model:'/new/whisper',models:['/new/whisper'],resolved_model:'/new/whisper'})};};
  app.run("asrEngine.value='whisper';asrModel.value='/old/whisper';modelDirectory.value='/new models'");
  await app.run("refreshModelSelection('asr')");
  assert.match(urls[0],/model_dir=%2Fnew%20models/);
  assert.equal(app.elements.get('#asrModel').value,'/new/whisper');
});

test('opening settings again reads the latest saved model directory', async () => {
  const app=loadApp();
  app.context.fetch=async url=>({ok:true,json:async()=>url==='/settings'?{model_dir:'/new',asr_engine:'whisper',translation_backend:'ollama'}:{models:[]}});
  app.run("modelDirectory.value='/old'");
  await app.run('openSettings()');
  assert.equal(app.elements.get('#modelDirectory').value,'/new');
});

test('a unique namespaced service model replaces a stale short name', async () => {
  const app=loadApp();
  app.context.fetch=async()=>({ok:true,json:async()=>({reachable:true,models:[{id:'vendor/translategemma:4b',translation:true}]})});
  app.run("translationEngine.value='ollama';translationModel.value='translategemma:4b'");
  await app.run("refreshModelSelection('translation')");
  assert.equal(app.elements.get('#translationModel').value,'vendor/translategemma:4b');
});

test('missing model folder displays the diagnostic instead of a script failure', async () => {
  const app=loadApp();
  app.context.fetch=async()=>({ok:true,json:async()=>({installed:false,model:'old/whisper',models:['old/whisper'],path:'/missing',message:'目录不存在或外置盘未挂载，请重新选择目录'})});
  app.run("asrEngine.value='whisper'");
  await app.run("refreshModelSelection('asr')");
  assert.match(app.elements.get('#asrModelStatus').textContent,/未挂载/);
  assert.doesNotMatch(app.elements.get('#asrModelStatus').textContent,/检查失败/);
});

test('empty changed folder clears the historical speech model option', async () => {
  const app=loadApp();
  app.context.fetch=async()=>({ok:true,json:async()=>({installed:false,model:'',models:[],path:'/new',message:'未找到语音模型'})});
  app.run("asrEngine.value='whisper';asrModel.value='/old/model';modelDirectory.value='/new'");
  await app.run("refreshModelSelection('asr')");
  assert.equal(app.elements.get('#asrModel').value,'');
  assert.doesNotMatch(app.elements.get('#asrModel').innerHTML,/old\/model/);
});

test('pending restart displays saved selection instead of the old active ASR path', () => {
  const app=loadApp();
  app.run("updateHealth({mode:'local',models:{ready:false,stage:'restart',message:'设置已保存，请重启'},asr:{status:'ready',model:'/old/whisper'},settings:{restart_required:true,asr_model:'SenseVoice-Small'}})");
  assert.match(app.elements.get('#asrStatus').textContent,/SenseVoice/);
  assert.doesNotMatch(app.elements.get('#asrStatus').textContent,/old/);
  assert.equal(app.elements.get('#startBtn').disabled,true);
});
