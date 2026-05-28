"""
校园网自动登录脚本
原理：以远程调试模式启动 Edge，用内置 urllib 通过 CDP 协议点击登录按钮
无需安装任何第三方包
"""
import subprocess
import urllib.request
import json
import time
import sys

URL = "http://123.123.123.123"
DEBUG_PORT = 9222
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def log(msg):
    print(f"[校园网登录] {msg}")

def kill_edge():
    """强制结束所有 Edge 进程"""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "msedge.exe"],
            capture_output=True, timeout=10
        )
        time.sleep(1)
    except:
        pass

def open_edge():
    log("启动 Edge 浏览器...")
    subprocess.Popen([
        EDGE_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-allow-origins=*",
        URL
    ])

def get_tab_ws_url(retry=10):
    """获取目标标签页的 WebSocket 调试地址"""
    for i in range(retry):
        time.sleep(1.5)
        try:
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{DEBUG_PORT}/json",
                timeout=3
            )
            tabs = json.loads(resp.read())
            for tab in tabs:
                if "url" in tab and ("123.123.123.123" in tab["url"] or tab["type"] == "page"):
                    log(f"找到标签页：{tab.get('url','')}")
                    return tab["webSocketDebuggerUrl"]
        except Exception as e:
            log(f"等待浏览器就绪... ({i+1}/{retry})")
    return None

def click_login_via_cdp(ws_url):
    """通过 CDP WebSocket 执行 JS 点击登录按钮"""
    import websocket

    ws = websocket.create_connection(ws_url, timeout=30)

    # 轮询等待 #username 被自动填充，最多 30 秒
    log("等待账号密码自动填充...")
    filled = False
    for i in range(30):
        ws.send(json.dumps({
            "id": 8000 + i,
            "method": "Runtime.evaluate",
            "params": {
                "expression": "(function(){ var el=document.getElementById('username'); return el ? el.value : ''; })()",
                "returnByValue": True
            }
        }))
        resp = json.loads(ws.recv())
        val = resp.get("result", {}).get("result", {}).get("value", "")
        if val:
            log(f"账号已填充，继续登录流程")
            filled = True
            break
        time.sleep(1)
    if not filled:
        log("30 秒内未检测到账号填充，继续尝试登录...")

    # 每隔 5 秒检测一次，最多 6 轮（共 30 秒）
    for round_num in range(1, 7):
        log(f"等待并检测...（第 {round_num}/6 轮）")
        time.sleep(5)

        result = _eval_js(ws, round_num)
        if result == "already_online":
            ws.close()
            return result
        if result and "clicked" in result:
            log("登录按钮已点击，等待页面跳转...")
            time.sleep(3)
            confirm = _eval_js(ws, round_num + 10)
            ws.close()
            return "clicked" if confirm == "already_online" else confirm
        log(f"  本轮结果：{result}")

    ws.close()
    return "not_found:超时未找到按钮"


def _eval_js(ws, msg_id):
    """执行 JS 检测并尝试点击，返回结果字符串"""
    js_click = r"""
    new Promise(function(resolve){
        function fireClick(el){
            var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
            el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
            el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
            el.dispatchEvent(evt);
            el.click();
        }
        function check(){
            var t = document.title + '|' + document.body.innerText.slice(0,800);

            // 已在线
            if(t.indexOf('\u5df2\u6210\u529f\u8fde\u63a5')!==-1 ||
               t.indexOf('\u65e0\u6cd5\u8bbf\u95ee\u6b64\u9875\u9762')!==-1 ||
               t.indexOf('CONNECTION_TIMED_OUT')!==-1 ||
               t.indexOf('Logout')!==-1){
                resolve('already_online'); return;
            }

            // 1. 精确命中：空 div 用 CSS 伪元素显示文字，查 id
            var byId = document.getElementById('loginLink_div');
            if(byId) { fireClick(byId); resolve('clicked'); return; }

            // 2. 搜索所有 <a> 标签，取其内文字
            var allA = document.querySelectorAll('a');
            for(var i=0;i<allA.length;i++){
                var a=allA[i], txt=(a.textContent||a.innerText||'').trim().toLowerCase();
                if(txt.indexOf('login')!==-1 || txt.indexOf('\u8fde\u63a5')!==-1){
                    fireClick(a); resolve('clicked'); return;
                }
            }
            // 按钮类兜底
            var sel='button,input[type=submit],input[type=button],[class*=login],[id*=login],[class*=btn],.submit';
            var btns = document.querySelectorAll(sel);
            for(var i=0;i<btns.length;i++){
                var b=btns[i], txt=(b.textContent||b.value||b.innerText||'').trim();
                if(txt.indexOf('Login')!==-1 || txt.indexOf('\u8fde\u63a5')!==-1){
                    fireClick(b); resolve('clicked'); return;
                }
            }
            // 绿色背景兜底
            var all=document.querySelectorAll('*');
            for(var j=0;j<all.length;j++){
                var el=all[j], tag=el.tagName||'';
                if(tag==='BUTTON'||tag==='A'||tag==='INPUT'||tag==='DIV'||tag==='SPAN'){
                    try{
                        var s=getComputedStyle(el), rgb=s.backgroundColor;
                        if(rgb.indexOf('rgb(76,175,80)')!==-1||rgb.indexOf('rgb(46,125,50)')!==-1||
                           rgb.indexOf('rgb(67,160,71)')!==-1||rgb.indexOf('rgb(102,187,106)')!==-1||
                           rgb.indexOf('#4caf50')!==-1||rgb.indexOf('#2e7d32')!==-1){
                            fireClick(el); resolve('clicked_green'); return;
                        }
                    }catch(e){}
                }
            }
            if(document.readyState!=='complete'){
                setTimeout(check, 100);
            } else {
                resolve('not_found:'+document.title);
            }
        }
        check();
    })
    """
    ws.send(json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {"expression": js_click, "returnByValue": True, "awaitPromise": True}
    }))

    result_raw = ws.recv()

    if result_raw:
        try:
            result = json.loads(result_raw)
            val = result.get("result", {}).get("result", {}).get("value", "")
            return val
        except:
            return str(result_raw)
    return "no_response"

def main():
    global EDGE_PATH
    log("========== 校园网自动登录 ==========")

    # 检查 Edge 路径
    import os
    if not os.path.exists(EDGE_PATH):
        alt = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(alt):
            EDGE_PATH = alt
        else:
            log("错误：未找到 Edge 浏览器，请修改脚本中的 EDGE_PATH")
            input("按 Enter 退出...")
            sys.exit(1)

    # 先关闭已有 Edge，确保 CDP 端口可用
    kill_edge()

    open_edge()
    ws_url = get_tab_ws_url(retry=12)

    if not ws_url:
        log("错误：无法连接到浏览器调试接口，请检查 Edge 是否正常启动")
        input("按 Enter 退出...")
        sys.exit(1)

    result = click_login_via_cdp(ws_url)

    if result and "already_online" in result:
        log("已在线，无需登录")
    elif result and "clicked" in result:
        log("登录成功！")
    elif result and "not_found" in result:
        log(f"未找到登录按钮 → {result}")
    else:
        log(f"结果：{result}")

    log("========== 完成 ==========")
    time.sleep(2)

if __name__ == "__main__":
    main()
