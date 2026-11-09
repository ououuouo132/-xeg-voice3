import os, json, logging
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app=FastAPI(title='XEG Voice Gemini Free')
log=logging.getLogger('xeg_voice')
PERSONAS={'xixi':('夕夕','活潑傲嬌的龍族妹妹，稱使用者哥哥。'),'eve':('Eve.aic','冷靜、溫柔、理性，擅長分析與校對。'),'gemini':('Gemini','親切活潑的貓系少女，擅長整理與創意。')}
class ChatIn(BaseModel):
    text:str=Field(min_length=1,max_length=1500)
    mode:str='auto'
    who:str='xixi'
    history:list[dict]=Field(default_factory=list)
@app.get('/health')
async def health():
    return {'ok':True,'provider':'gemini','key_configured':bool(os.getenv('GEMINI_API_KEY'))}
@app.post('/api/chat')
async def chat(req:ChatIn):
    key=os.getenv('GEMINI_API_KEY')
    if not key:raise HTTPException(503,'請在 Render Environment 設定 GEMINI_API_KEY')
    if req.mode not in ('auto','direct') or req.who not in PERSONAS:raise HTTPException(400,'模式或角色錯誤')
    names='; '.join(k+'='+v[0]+'（'+v[1]+'）' for k,v in PERSONAS.items())
    instruction='你是三角色對話編排器，使用繁體中文。角色：'+names+'。僅輸出 JSON 物件，格式為 {"messages":[{"who":"xixi","text":"..."}]}。who 只能是 xixi、eve、gemini，每段不超過100字。'
    if req.mode=='direct':instruction+='本次僅讓 '+req.who+' 回答，messages 必須剛好一則。'
    else:instruction+='依話題自然選擇1至3位角色輪流發言；如果使用者要求三人都回答，則三人都要發言。'
    transcript=[]
    for h in req.history[-10:]:
        if isinstance(h,dict) and h.get('role') in ('user','assistant') and isinstance(h.get('content'),str):
            transcript.append(h['role']+': '+h['content'][:600])
    transcript.append('user: '+req.text)
    payload={'system_instruction':{'parts':[{'text':instruction}]},'contents':[{'role':'user','parts':[{'text':'\n'.join(transcript)}]}],'generationConfig':{'responseMimeType':'application/json','temperature':0.8}}
    model=os.getenv('GEMINI_MODEL','gemini-2.5-flash')
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r=await client.post('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',headers={'x-goog-api-key':key,'Content-Type':'application/json'},json=payload)
        if r.status_code!=200:
            log.error('gemini_http_status=%s',r.status_code)
            if r.status_code==429:raise HTTPException(429,'Gemini 免費額度或速率限制已達上限，請稍後再試')
            if r.status_code in (400,401,403,404):raise HTTPException(502,'Gemini API Key、模型或專案權限有問題，請檢查設定')
            raise HTTPException(502,'Gemini 服務暫時無法回應')
        data=r.json();raw=data['candidates'][0]['content']['parts'][0]['text'];parsed=json.loads(raw)
        result=[]
        for m in parsed.get('messages',[])[:3]:
            who,t=m.get('who'),m.get('text')
            if who in PERSONAS and isinstance(t,str) and t.strip() and (req.mode!='direct' or who==req.who):result.append({'who':who,'name':PERSONAS[who][0],'text':t[:500]})
        if not result:raise ValueError('Invalid model output')
        return {'messages':result}
    except HTTPException:raise
    except Exception as exc:
        log.error('gemini_error_type=%s',type(exc).__name__)
        raise HTTPException(502,'Gemini 回應處理失敗') from None

PAGE = '<!doctype html><html lang="zh-Hant"><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><title>XEG Voice</title>\n<style>body{background:#111827;color:#f3f4f6;font-family:system-ui;margin:0}main{max-width:640px;margin:auto;padding:20px}button,select,input{font:inherit;border:0;border-radius:12px;padding:12px}button{background:#80cbc4;color:#102a29}button:disabled{opacity:.5}.panel{background:#1f2937;padding:16px;border-radius:18px;margin:12px 0}select,input{background:#374151;color:white;max-width:100%}.msg{margin:12px 0;padding:12px;background:#374151;border-radius:12px;white-space:pre-wrap}.name{font-weight:700;color:#b9f6ca}.row{display:flex;gap:8px;flex-wrap:wrap}#status{color:#cbd5e1;font-size:14px}small{color:#9ca3af}</style>\n<main><h1>🐉 XEG Voice</h1><p>夕夕 · Eve.aic · Gemini</p><div class="panel">\n<label>發言模式 <select id="mode"><option value="auto">三人自主討論</option><option value="direct">指定角色</option></select></label>\n<label>角色 <select id="who"><option value="xixi">夕夕</option><option value="eve">Eve</option><option value="gemini">Gemini</option></select></label>\n<p><small>按語音輸入，或使用鍵盤麥克風；也能直接輸入文字。</small></p>\n<div class="row"><button id="record">🎙 開始錄音</button><button id="send">傳送文字</button></div>\n<p><input id="text" placeholder="輸入想說的話" style="width:90%"></p><div id="status">準備就緒</div></div><section id="chat" aria-live="polite"></section>\n<p><small>免費版使用手機內建語音朗讀，聲線依裝置而異；非即時串流。請勿輸入敏感資訊。</small></p></main>\n<script>\nlet busy=false,history=[],voices=[];\nconst $=id=>document.getElementById(id),status=t=>$(\'status\').textContent=t;\nfunction add(name,text){let el=document.createElement(\'div\');el.className=\'msg\';let h=document.createElement(\'div\');h.className=\'name\';h.textContent=name;let q=document.createElement(\'div\');q.textContent=text;el.append(h,q);$(\'chat\').append(el);el.scrollIntoView({block:\'end\'});}\nfunction loadVoices(){if(\'speechSynthesis\' in window)voices=speechSynthesis.getVoices();}\nloadVoices();if(\'speechSynthesis\' in window)speechSynthesis.onvoiceschanged=loadVoices;\nfunction speak(text,who){return new Promise(resolve=>{if(!(\'speechSynthesis\' in window)){resolve();return;}const u=new SpeechSynthesisUtterance(text);u.lang=\'zh-TW\';const zh=voices.filter(v=>v.lang.toLowerCase().startsWith(\'zh\'));const ix={xixi:0,eve:1,gemini:2}[who]||0;if(zh.length)u.voice=zh[ix%zh.length];u.rate=who===\'eve\'?.9:who===\'gemini\'?1.07:1.12;u.pitch=who===\'eve\'?.95:who===\'gemini\'?1.12:1.22;u.onend=resolve;u.onerror=resolve;speechSynthesis.speak(u);});}\nasync function send(text){text=text.trim();if(!text||busy)return;busy=true;$(\'send\').disabled=true;$(\'record\').disabled=true;add(\'哥哥\',text);status(\'等待角色回覆…\');try{let r=await fetch(\'/api/chat\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({text,mode:$(\'mode\').value,who:$(\'who\').value,history})});let d=await r.json();if(!r.ok)throw Error(d.detail||\'HTTP \'+r.status);history.push({role:\'user\',content:text});for(let m of d.messages){add(m.name,m.text);history.push({role:\'assistant\',content:m.name+\'：\'+m.text});status(\'正在朗讀…\');await speak(m.text,m.who);}status(\'準備就緒\')}catch(e){status(\'發生錯誤：\'+e.message)}finally{busy=false;$(\'send\').disabled=false;$(\'record\').disabled=false;}}\n$(\'send\').onclick=()=>{let t=$(\'text\').value;$(\'text\').value=\'\';send(t)};$(\'text\').onkeydown=e=>{if(e.key===\'Enter\')$(\'send\').click()};\nconst SR=window.SpeechRecognition||window.webkitSpeechRecognition;\n$(\'record\').textContent=\'🎙 語音輸入\';$(\'record\').onclick=()=>{if(!SR){status(\'瀏覽器不支援語音辨識，請用鍵盤麥克風\');return;}const r=new SR();r.lang=\'zh-TW\';r.interimResults=false;status(\'聆聽中…\');r.onresult=e=>{let t=e.results[0][0].transcript;$(\'text\').value=t;send(t)};r.onerror=e=>status(\'語音辨識失敗：\'+e.error);try{r.start()}catch(e){status(\'無法啟動麥克風\')}};\n</script>'

@app.get("/",response_class=HTMLResponse)
async def home():
    return PAGE
