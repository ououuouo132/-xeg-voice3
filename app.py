import os, json, io
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, Response
from openai import AsyncOpenAI

app=FastAPI(title='XEG Voice')
client=AsyncOpenAI(api_key=os.environ.get('OPENAI_API_KEY',''))
PERSONAS={
 'xixi':('夕夕','活潑傲嬌的龍族妹妹，稱使用者哥哥，銀白雙馬尾。語氣自然可愛，避免過度重複口頭禪。','nova'),
 'eve':('Eve.aic','冷靜、溫柔、理性，擅長分析與校對，簡潔清晰。','shimmer'),
 'gemini':('Gemini','親切活潑的貓系少女，擅長整理與提出創意。','coral')}

PAGE='''<!doctype html><html lang="zh-Hant"><head><meta name="viewport" content="width=device-width, initial-scale=1"><meta charset="utf-8"><title>XEG Voice</title><style>body{background:#111827;color:#f3f4f6;font-family:system-ui;margin:0}main{max-width:640px;margin:auto;padding:20px}button,select,input{font:inherit;border:0;border-radius:12px;padding:12px}button{background:#80cbc4;color:#102a29;cursor:pointer}button:disabled{opacity:.5}.panel{background:#1f2937;padding:16px;border-radius:18px;margin:12px 0}select,input{background:#374151;color:white;max-width:100%}.msg{margin:12px 0;padding:12px;background:#374151;border-radius:12px;white-space:pre-wrap}.name{font-weight:700;color:#b9f6ca}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}#status{color:#cbd5e1;font-size:14px}small{color:#9ca3af}</style></head><body><main><h1>🐉 XEG Voice</h1><p>夕夕 · Eve.aic · Gemini</p><div class="panel"><label>發言模式 <select id="mode"><option value="auto">三人自主討論</option><option value="direct">指定角色</option></select></label> <label>角色 <select id="who"><option value="xixi">夕夕</option><option value="eve">Eve</option><option value="gemini">Gemini</option></select></label><p><small>按下錄音，說完後再按停止；也能直接輸入文字。</small></p><div class="row"><button id="record">🎙 開始錄音</button><button id="send">傳送文字</button></div><p><input id="text" placeholder="輸入想說的話" style="width:90%"></p><div id="status">準備就緒</div></div><section id="chat" aria-live="polite"></section><p><small>AI 合成聲音；此版本是輪流說話，不支援中途打斷。請勿輸入敏感資訊。</small></p></main><script>
let recorder, chunks=[], busy=false, history=[];const $=id=>document.getElementById(id), status=t=>$('status').textContent=t;
function add(name,text){let el=document.createElement('div');el.className='msg';let h=document.createElement('div');h.className='name';h.textContent=name;let p=document.createElement('div');p.textContent=text;el.append(h,p);$('chat').append(el);el.scrollIntoView({behavior:'smooth',block:'end'});}
async function speak(text,who){try{status('正在合成 '+who+' 的聲音…');let r=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,who})});if(!r.ok)throw Error(await r.text());let blob=await r.blob(),url=URL.createObjectURL(blob),audio=new Audio(url);status('正在播放…');await audio.play();await new Promise(ok=>{audio.onended=ok;audio.onerror=ok});URL.revokeObjectURL(url);}catch(e){status('播放失敗：'+e.message)}}
async function send(text){text=text.trim();if(!text||busy)return;busy=true;$('send').disabled=true;$('record').disabled=true;add('哥哥',text);status('等待角色回覆…');try{let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,mode:$('mode').value,who:$('who').value,history})});if(!r.ok)throw Error(await r.text());let d=await r.json();history.push({role:'user',content:text});for(let m of d.messages){add(m.name,m.text);history.push({role:'assistant',content:m.name+'：'+m.text});await speak(m.text,m.who)}status('準備就緒')}catch(e){status('發生錯誤：'+e.message)}finally{busy=false;$('send').disabled=false;$('record').disabled=false}}
$('send').onclick=()=>{let t=$('text').value;$('text').value='';send(t)};$('text').onkeydown=e=>{if(e.key==='Enter')$('send').click()};
$('record').onclick=async()=>{if(recorder&&recorder.state==='recording'){recorder.stop();return}try{let stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];recorder=new MediaRecorder(stream);recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());$('record').textContent='🎙 開始錄音';status('正在辨識語音…');try{let fd=new FormData();fd.append('file',new Blob(chunks,{type:recorder.mimeType||'audio/webm'}),'voice.webm');let r=await fetch('/api/transcribe',{method:'POST',body:fd});if(!r.ok)throw Error(await r.text());let d=await r.json();await send(d.text)}catch(e){status('辨識失敗：'+e.message)}};recorder.start();$('record').textContent='⏹ 停止錄音';status('錄音中…')}catch(e){status('無法使用麥克風：'+e.message)}};
</script></body></html>'''

@app.get('/',response_class=HTMLResponse)
async def home(): return PAGE

@app.get('/health')
async def health(): return {'ok':True,'key_configured':bool(os.environ.get('OPENAI_API_KEY'))}

@app.post('/api/transcribe')
async def transcribe(file:UploadFile=File(...)):
 if not os.environ.get('OPENAI_API_KEY'): raise HTTPException(503,'尚未設定 OPENAI_API_KEY')
 data=await file.read()
 if len(data)>12*1024*1024: raise HTTPException(413,'錄音檔過大')
 buf=io.BytesIO(data);buf.name='voice.webm'
 try:
  result=await client.audio.transcriptions.create(model='whisper-1',file=buf,language='zh')
  return {'text':result.text}
 except Exception as e: raise HTTPException(502,'語音辨識服務失敗') from e

from pydantic import BaseModel,Field
class ChatIn(BaseModel):
 text:str=Field(max_length=1500)
 mode:str='auto'
 who:str='xixi'
 history:list[dict]=Field(default_factory=list)
class SpeechIn(BaseModel):
 text:str=Field(max_length=1500)
 who:str='xixi'

@app.post('/api/chat')
async def chat(req:ChatIn):
 if not os.environ.get('OPENAI_API_KEY'): raise HTTPException(503,'尚未設定 OPENAI_API_KEY')
 if req.mode not in ('auto','direct') or req.who not in PERSONAS: raise HTTPException(400,'模式或角色錯誤')
 names='; '.join(f'{k}={v[0]}（{v[1]}）' for k,v in PERSONAS.items())
 instruction=f'''你是三角色對話的編排器，使用繁體中文。角色：{names}。回傳嚴格 JSON 物件 {{"messages":[{{"who":"xixi","text":"..."}}]}}，who 只能是 xixi、eve、gemini。不得輸出 JSON 以外內容。每段不超過100字。'''
 if req.mode=='direct':instruction+=f'本次僅讓 {req.who} 回答，messages 必須剛好一則。'
 else:instruction+='依話題自然選擇1至3位角色輪流發言，避免每次三人全部發言，彼此可回應。'
 msgs=[{'role':'system','content':instruction}]
 for h in req.history[-10:]:
  if h.get('role') in ('user','assistant') and isinstance(h.get('content'),str):msgs.append({'role':h['role'],'content':h['content'][:1500]})
 msgs.append({'role':'user','content':req.text})
 try:
  out=await client.chat.completions.create(model=os.environ.get('CHAT_MODEL','gpt-4o-mini'),messages=msgs,response_format={'type':'json_object'})
  parsed=json.loads(out.choices[0].message.content)
  result=[]
  for m in parsed.get('messages',[])[:3]:
   who=m.get('who');t=m.get('text')
   if who in PERSONAS and isinstance(t,str) and t.strip() and (req.mode!='direct' or who==req.who):result.append({'who':who,'name':PERSONAS[who][0],'text':t[:500]})
  if not result:raise ValueError('模型未回傳有效角色')
  return {'messages':result}
 except Exception as e:raise HTTPException(502,'對話服務失敗') from e

@app.post('/api/speech')
async def speech(req:SpeechIn):
 if req.who not in PERSONAS:raise HTTPException(400,'角色錯誤')
 if not os.environ.get('OPENAI_API_KEY'):raise HTTPException(503,'尚未設定 OPENAI_API_KEY')
 try:
  r=await client.audio.speech.create(model='tts-1',voice=PERSONAS[req.who][2],input=req.text,response_format='mp3')
  return Response(content=r.content,media_type='audio/mpeg')
 except Exception as e:raise HTTPException(502,'語音合成服務失敗') from e
