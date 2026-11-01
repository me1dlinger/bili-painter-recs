#!/usr/bin/env node
/**
 * B站评论区画师推荐分析 —— 静态数据 + 零依赖 HTTP 服务
 * 启动：node server.js [port]
 * 默认监听 0.0.0.0:8787，局域网可直接访问。
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const PORT = Number(process.argv[2] || process.env.PORT || 8787);
const ROOT = __dirname;
const DATA = path.join(ROOT, '..', 'data.json');
const PUBLIC = path.join(ROOT, 'public');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

function send(res, code, body, type) {
  res.writeHead(code, {
    'Content-Type': type || 'text/plain; charset=utf-8',
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(body);
}

const server = http.createServer((req, res) => {
  const url = decodeURIComponent((req.url || '/').split('?')[0]);
  if (url === '/api/data') {
    fs.readFile(DATA, (err, buf) => {
      if (err) return send(res, 500, JSON.stringify({ error: String(err) }), MIME['.json']);
      send(res, 200, buf, MIME['.json']);
    });
    return;
  }
  if (url === '/data.json') {          // 静态托管时 data.json 与 index.html 同目录
    return fs.readFile(DATA, (err, buf) =>
      err ? send(res, 500, '{}', MIME['.json']) : send(res, 200, buf, MIME['.json']));
  }
  if (url === '/health') return send(res, 200, 'ok');
  let rel = url === '/' ? '/index.html' : url;
  const file = path.join(PUBLIC, path.normalize(rel).replace(/^(\.\.[/\\])+/, ''));
  if (!file.startsWith(PUBLIC)) return send(res, 403, 'forbidden');
  fs.readFile(file, (err, buf) => {
    if (err) return send(res, 404, 'not found');
    send(res, 200, buf, MIME[path.extname(file)] || 'application/octet-stream');
  });
});

server.listen(PORT, '0.0.0.0', () => {
  const ips = Object.values(os.networkInterfaces()).flat()
    .filter((i) => i && i.family === 'IPv4' && !i.internal)
    .map((i) => i.address);
  const lan = ips.find((ip) => ip.startsWith('192.168.')) || ips[0] || '127.0.0.1';
  console.log(`画师推荐分析服务已启动`);
  console.log(`  本机   http://127.0.0.1:${PORT}`);
  console.log(`  局域网 http://${lan}:${PORT}`);
});