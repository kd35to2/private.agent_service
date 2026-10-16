import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from core import settings

router = APIRouter()

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>账号 · Agent Service Toolkit</title>
<style>
body{font-family:system-ui,sans-serif;background:#f5f7fb;color:#192536;margin:0;padding:32px 16px}
main{max-width:760px;margin:auto}section{background:white;border:1px solid #dae1ed;border-radius:12px;padding:24px;margin:18px 0}
.forms{display:grid;grid-template-columns:1fr 1fr;gap:24px}label{display:block;margin:14px 0 6px}
input{box-sizing:border-box;width:100%;padding:11px;border:1px solid #bac6d8;border-radius:6px;font:inherit}
button,.chat{display:inline-block;background:#245bcc;color:white;border:0;border-radius:6px;padding:11px 18px;margin-top:18px;font:inherit;cursor:pointer;text-decoration:none}
.secondary{background:#526178}#message{white-space:pre-wrap;min-height:24px}small{color:#526178}a{color:#245bcc}
[hidden]{display:none!important}@media(max-width:600px){.forms{grid-template-columns:1fr}}
</style></head><body><main><h1>你的 Agent 账号</h1>
<p>登录同一账号，访问你的个人知识库和历史会话。</p>
<p id="message" role="status" aria-live="polite"></p>
<section id="guest"><div class="forms">
<form id="login"><h2>登录</h2><label for="login-name">用户名</label>
<input id="login-name" name="username" autocomplete="username" required>
<label for="login-password">密码</label><input id="login-password" name="password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required>
<button>登录</button></form>
<form id="register"><h2>注册</h2><label for="register-name">用户名</label>
<input id="register-name" name="username" autocomplete="username" pattern="[A-Za-z0-9_.-]{3,32}" required>
<small>3–32 个英文字母、数字、下划线、点或连字符</small>
<label for="register-password">密码</label><input id="register-password" name="password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required>
<label for="register-confirm">确认密码</label><input id="register-confirm" name="confirm" type="password" autocomplete="new-password" required>
<button>创建账号</button></form></div></section>
<section id="member" hidden><h2 id="identity"></h2><a class="chat" href="__APP_URL__">进入聊天</a>
<button id="logout" class="secondary">退出登录</button>
<form id="change"><h2>修改密码</h2><label for="current-password">当前密码</label>
<input id="current-password" name="current_password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required>
<label for="new-password">新密码</label><input id="new-password" name="new_password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required>
<label for="new-confirm">确认新密码</label><input id="new-confirm" name="confirm" type="password" autocomplete="new-password" required>
<button>修改密码</button><p><small>修改后所有设备的登录会话失效，需要重新登录。</small></p></form></section>
<p><a href="/docs">查看 API 文档</a></p></main>
<script>
const message=document.querySelector('#message');
const errors={'Username already exists':'用户名已存在','Invalid username or password':'用户名或密码错误','Current password is incorrect':'当前密码错误','Session expired or revoked':'登录已过期，请重新登录'};
async function api(path,data){const r=await fetch('/auth/'+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});let body=r.status===204?null:await r.json();if(!r.ok){const detail=body.detail;throw new Error(errors[detail]||(Array.isArray(detail)?'请检查用户名格式和密码长度':detail));}return body;}
async function refresh(){try{const user=await api('me');document.querySelector('#identity').textContent='已登录：'+user.username;document.querySelector('#guest').hidden=true;document.querySelector('#member').hidden=false;}catch{document.querySelector('#guest').hidden=false;document.querySelector('#member').hidden=true;}}
for(const id of ['login','register','change']){document.getElementById(id).addEventListener('submit',async e=>{e.preventDefault();const form=e.target;const data=Object.fromEntries(new FormData(form));if(data.confirm!==undefined&&data.confirm!==(data.new_password||data.password)){message.textContent='两次输入的密码不一致';return;}delete data.confirm;const button=form.querySelector('button');button.disabled=true;try{await api(id==='change'?'change-password':id,data);form.reset();message.textContent=id==='register'?'注册成功，请登录':id==='change'?'密码已修改，请重新登录':'登录成功，点击进入聊天';await refresh();}catch(error){message.textContent=error.message;}finally{button.disabled=false;}});}
document.querySelector('#logout').addEventListener('click',async()=>{try{await api('logout',{});message.textContent='已退出登录';await refresh();}catch(error){message.textContent=error.message;await refresh();}});
refresh();
</script></body></html>"""


@router.get("/account", response_class=HTMLResponse, include_in_schema=False)
async def account_page() -> HTMLResponse:
    page = PAGE.replace("__APP_URL__", html.escape(settings.APP_URL, quote=True))
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})
