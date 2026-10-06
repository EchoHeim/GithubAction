#!/usr/bin/env python
"""
cdp.py —— 直接讲 CDP 协议的极简客户端。

agent-browser 的 CLI 在这台机器上老挂（SIGTERM / 输出管道不关闭），
所以直接用 WebSocket 跟 Chrome 说话：快、可靠、无超时悬案。

用法:
    python cdp.py eval "document.title"
    python cdp.py goto https://github.com/...
    python cdp.py shot out.png
    python cdp.py cookies
"""
import base64
import json
import sys
import time
import urllib.request

import websocket  # websocket-client

PORT = 9222


def _targets():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=8) as r:
        return json.load(r)


def pick_page(url_match=None, title_not=None):
    """挑一个页面 target。url_match 是子串过滤。"""
    pages = [t for t in _targets() if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if url_match:
        pages = [t for t in pages if url_match in t.get("url", "")]
    return pages[0] if pages else None


class CDP:
    def __init__(self, ws_url, timeout=25):
        self.ws = websocket.create_connection(ws_url, timeout=timeout,
                                             suppress_origin=True)
        self._id = 0

    def send(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        deadline = time.time() + 25
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(method)

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True, userGesture=True)
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            return {"__error__": str(r["exceptionDetails"])[:400]}
        return res.get("value")

    def nav(self, url):
        self.send("Page.navigate", url=url)
        time.sleep(3)

    def shot(self, path, full=False):
        params = {"format": "png"}
        if full:
            params["captureBeyondViewport"] = True
        r = self.send("Page.captureScreenshot", **params)
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return path

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def connect(url_match=None):
    t = pick_page(url_match)
    if not t:
        raise SystemExit("找不到页面 target")
    return CDP(t["webSocketDebuggerUrl"]), t


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "eval"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""

    if cmd == "list":
        for t in _targets():
            if t.get("type") == "page":
                print(f"{t.get('title','')[:45]:<47} {t.get('url','')[:95]}")

    elif cmd == "eval":
        c, t = connect(arg if arg != "eval" else None)
        try:
            out = c.js(sys.argv[2] if len(sys.argv) > 2 else "1")
        except SystemExit:
            c, t = connect()
            out = c.js(sys.argv[2])
        print(json.dumps(out, ensure_ascii=False, indent=2)
              if isinstance(out, (dict, list)) else out)
        c.close()

    elif cmd == "goto":
        c, t = connect()
        c.nav(arg)
        print(t.get("url"), "->", arg)
        c.close()

    elif cmd == "shot":
        c, t = connect()
        print(c.shot(arg if arg else "shot.png"))
        c.close()

    elif cmd == "cookies":
        c, t = connect()
        out = c.js("document.cookie")
        print(out)
        c.close()
