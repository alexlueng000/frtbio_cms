from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
from datetime import datetime
import json, os, shutil, secrets

# === 基本配置（按需修改或用环境变量覆盖） ===
SITE_ROOT = Path(os.getenv("SITE_ROOT", "/var/www/your-site")).resolve()
CONTENT_DIR = (SITE_ROOT / "content").resolve()
UPLOAD_DIR = (SITE_ROOT / "assets" / "uploads").resolve()
HISTORY_DIR = (CONTENT_DIR / ".history").resolve()

ADMIN_USER = os.getenv("CMS_USER", "editor")
ADMIN_PASS = os.getenv("CMS_PASS", "change-me-please")

app = FastAPI()
security = HTTPBasic()

def auth(creds: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(creds.username, ADMIN_USER)
    correct_pass = secrets.compare_digest(creds.password, ADMIN_PASS)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Unauthorized",
                            headers={"WWW-Authenticate":"Basic"})
    return True

def safe_content_path(name: str) -> Path:
    p = (CONTENT_DIR / name).resolve()
    if not p.suffix == ".json": raise HTTPException(400, "Only .json allowed")
    if not str(p).startswith(str(CONTENT_DIR)): raise HTTPException(400, "Invalid path")
    return p

@ app.get("/cms", response_class=HTMLResponse)
def admin_page(_: bool = Depends(auth)):
    # 极简单文件后台（左侧选择文件，右侧编辑器 + 保存）
    return """
<!doctype html><meta charset="utf-8"><title>CMS Admin</title>
<style>body{font:14px/1.5 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial}
.wrap{display:flex;height:100vh;margin:0}aside{width:280px;border-right:1px solid #eee;padding:12px;overflow:auto}
main{flex:1;display:flex;flex-direction:column}header{padding:10px;border-bottom:1px solid #eee}
textarea{flex:1;width:100%;border:0;outline:0;font:12px/1.5 ui-monospace,Consolas,Monaco,monospace;background:#fafafa;padding:12px}
.toolbar{padding:8px;border-top:1px solid #eee;display:flex;gap:8px}
input[type=file]{display:none}label.btn{border:1px solid #ddd;padding:6px 10px;border-radius:6px;cursor:pointer}
button{border:1px solid #2d6cdf;background:#2d6cdf;color:#fff;padding:6px 12px;border-radius:6px;cursor:pointer}
select, input[type=text]{padding:6px;border:1px solid #ddd;border-radius:6px}
small{color:#888}
</style>
<div class="wrap">
  <aside>
    <h3>文件</h3>
    <select id="fileList" size="20" style="width:100%"></select>
    <div style="margin-top:8px;display:flex;gap:6px">
      <input id="newName" type="text" placeholder="新文件名 如 about.zh.json" style="flex:1">
      <button onclick="createFile()">新建</button>
    </div>
    <p><small>目录：/content（仅 .json）</small></p>
    <h3>上传图片</h3>
    <input id="uploader" type="file" accept="image/*">
    <label for="uploader" class="btn">选择图片</label>
    <button onclick="doUpload()">上传</button>
    <p id="uploadResult"><small>上传后会返回可直接粘贴的 URL</small></p>
  </aside>
  <main>
    <header>
      <b id="curName">（未选择）</b>
      <button style="float:right" onclick="formatJson()">格式化 JSON</button>
    </header>
    <textarea id="editor" placeholder="选择左侧文件以编辑"></textarea>
    <div class="toolbar">
      <button onclick="save()">保存</button>
      <button onclick="reload()">重载</button>
      <span id="status"></span>
    </div>
  </main>
</div>
<script>
const st = (t)=>document.getElementById(t);
let current = null;

async function list() {
  const r = await fetch('/cms/list'); const d = await r.json();
  const sel = st('fileList'); sel.innerHTML='';
  d.files.forEach(f=>{const o=document.createElement('option');o.value=f;o.textContent=f;sel.appendChild(o)});
}
async function load(name){
  const r = await fetch('/cms/get?name='+encodeURIComponent(name));
  const t = await r.text(); st('editor').value = t; current=name; st('curName').textContent=name; st('status').textContent='已加载';
}
async function save(){
  if(!current){alert('请先选择文件');return}
  const content = st('editor').value;
  const r = await fetch('/cms/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name: current, content})});
  const d = await r.json(); st('status').textContent=d.msg||'已保存';
}
async function reload(){ if(current) load(current); }
st('fileList').addEventListener('change', e=> load(e.target.value));
async function createFile(){
  const name = st('newName').value.trim();
  if(!/^[a-zA-Z0-9_.-]+\\.json$/.test(name)){alert('请输入合法的 .json 文件名');return}
  const r = await fetch('/cms/create',{method:'POST',headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name})});
  const d = await r.json(); await list(); st('status').textContent=d.msg||'已创建';
}
async function doUpload(){
  const f = st('uploader').files[0]; if(!f){alert('请选择图片');return}
  const fd = new FormData(); fd.append('file', f);
  const r = await fetch('/cms/upload',{method:'POST',body:fd});
  const d = await r.json(); st('uploadResult').innerHTML = '<small>URL: <code>'+d.url+'</code> （已复制）</small>';
  navigator.clipboard?.writeText(d.url);
}
function formatJson(){
  try{ const v=JSON.parse(st('editor').value); st('editor').value=JSON.stringify(v,null,2); st('status').textContent='已格式化'; }
  catch(e){ alert('JSON 解析失败：'+e.message); }
}
list();
</script>
"""
@ app.get("/cms/list")
def list_files(_: bool = Depends(auth)):
    files = sorted([p.name for p in CONTENT_DIR.glob("*.json")])
    return {"files": files}

@ app.get("/cms/get", response_class=PlainTextResponse)
def get_file(name: str, _: bool = Depends(auth)):
    p = safe_content_path(name)
    if not p.exists(): raise HTTPException(404, "Not found")
    return p.read_text(encoding="utf-8")

@ app.post("/cms/save")
def save_file(payload: dict, _: bool = Depends(auth)):
    name = payload.get("name"); content = payload.get("content","")
    p = safe_content_path(name)
    try:
        data = json.loads(content)  # 校验 JSON
    except Exception as e:
        raise HTTPException(400, f"JSON invalid: {e}")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if p.exists():
        shutil.copy2(p, HISTORY_DIR / f"{p.name}.{ts}.bak.json")
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "msg": "保存成功，已自动备份一份到 .history/"}

@ app.post("/cms/create")
def create_file(payload: dict, _: bool = Depends(auth)):
    name = payload.get("name"); p = safe_content_path(name)
    if p.exists(): raise HTTPException(400, "文件已存在")
    p.write_text("{}\n", encoding="utf-8")
    return {"ok": True, "msg": "已创建空文件"}

@ app.post("/cms/upload")
def upload(file: UploadFile = File(...), _: bool = Depends(auth)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".jpg",".jpeg",".png",".webp",".gif",".svg"]:
        raise HTTPException(400, "只允许图片")
    safe_name = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + "".join(c for c in Path(file.filename).name if c.isalnum() or c in "._-")
    dest = (UPLOAD_DIR / safe_name)
    with dest.open("wb") as f: shutil.copyfileobj(file.file, f)
    url = f"/assets/uploads/{dest.name}"
    return {"ok": True, "url": url}
