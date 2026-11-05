#!/usr/bin/env python3
"""本地预览服务（绑 0.0.0.0，局域网可访问）
用法: python3 serve.py <项目根> <端口>
  - 静态文件取自 <项目根>/web/public（没有则取根目录）
  - /data.json 单独路由到 <项目根>/data.json（预览时不污染仓库）
"""
import http.server, os, sys
ROOT = os.path.abspath(sys.argv[1]); PORT = int(sys.argv[2])
PUB = os.path.join(ROOT, 'web/public')
BASE = PUB if os.path.isdir(PUB) else ROOT
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=BASE, **k)
    def translate_path(self, path):
        p = path.split('?')[0].split('#')[0]
        if p == '/data.json': return os.path.join(ROOT, 'data.json')
        return super().translate_path(path)
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
