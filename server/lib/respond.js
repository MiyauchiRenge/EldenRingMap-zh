/**
 * HTTP responses: one JSON writer and one file sender, both compression- and cache-aware.
 *
 * Two things matter here for a map that ships ~8 MB of marker JSON and ~8,000 icon files:
 *
 *   * the marker document and the layer documents are static once booted, so they are compressed once
 *     (brotli for browsers that ask for it, gzip otherwise) and the compressed copy is kept.
 *     Compressing an 8 MB document per request would cost more than sending it;
 *   * a conditional request (If-None-Match) is answered with 304, so a reload after a restart re-uses
 *     what the browser already has.
 *
 * File serving keeps the containment check it always had: the resolved path has to stay inside the
 * web root it is handed.
 */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const TEXT_EXT = new Set(['.html', '.js', '.css', '.json', '.svg', '.txt', '.map', '.webmanifest']);
const CACHE_EXT = new Set(['.webp', '.png', '.jpg', '.jpeg', '.gif', '.woff', '.woff2', '.ico']);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

/** Weak ETag from the content: cheap, and a rebuild that changes nothing keeps the same tag. */
function etagOf(body) {
  // djb2 over the buffer; a full hash would cost more than the comparison saves here.
  let h = 5381;
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(body);
  for (let i = 0; i < buf.length; i++) h = ((h * 33) ^ buf[i]) >>> 0;
  return `W/"${buf.length.toString(16)}-${h.toString(16)}"`;
}

const cache = new Map();          // etag -> { br, gzip }
const CACHE_MAX = 6;              // documents, not assets: six is the light doc plus a few layers

function encoded(etag, body) {
  let entry = cache.get(etag);
  if (!entry) {
    const buf = Buffer.isBuffer(body) ? body : Buffer.from(body);
    entry = { br: zlib.brotliCompressSync(buf, {
      params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 },
    }), gzip: zlib.gzipSync(buf, { level: 6 }), raw: buf };
    if (cache.size >= CACHE_MAX) cache.delete(cache.keys().next().value);
    cache.set(etag, entry);
  }
  return entry;
}

/** Does the client accept this encoding? */
function accepts(req, kind) {
  const header = String(req.headers['accept-encoding'] || '');
  return header.includes(kind);
}

/**
 * Send a JSON document with compression, an ETag and no-cache (the data can change under the page).
 */
function sendJson(req, res, obj, code = 200, extraHeaders = {}) {
  const body = Buffer.from(JSON.stringify(obj));
  const etag = etagOf(body);
  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    ETag: etag,
    'Cache-Control': 'no-cache',
    Vary: 'Accept-Encoding',
    ...extraHeaders,
  };
  if (req && req.headers['if-none-match'] === etag) {
    res.writeHead(304, headers).end();
    return;
  }
  const entry = encoded(etag, body);
  let payload = entry.raw;
  if (req && accepts(req, 'br')) {
    headers['Content-Encoding'] = 'br';
    payload = entry.br;
  } else if (req && accepts(req, 'gzip')) {
    headers['Content-Encoding'] = 'gzip';
    payload = entry.gzip;
  }
  headers['Content-Length'] = payload.length;
  res.writeHead(code, headers);
  res.end(payload);
}

/**
 * Send a file from the web root, compressed when it is text and cached when it is an asset.
 */
function sendFile(req, res, webRoot, urlPath) {
  const file = path.join(webRoot, decodeURIComponent(urlPath));
  // Containment is checked with path.relative, not a string prefix. A prefix test
  // ("file.startsWith(WEB)") also accepts a *sibling* whose name merely begins with "web" - a
  // directory next to web/ called "web-backup" would pass it - so a crafted path could step outside
  // web/ and read those files. Resolving the relative path and rejecting anything that climbs out
  // ("..") or lands on an absolute path (a different Windows drive) closes that.
  const within = path.relative(webRoot, path.resolve(file));
  if (within.startsWith('..') || path.isAbsolute(within)) {
    res.writeHead(403).end('forbidden');
    return;
  }
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain' }).end('not found');
      return;
    }
    const ext = path.extname(file).toLowerCase();
    const headers = {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': CACHE_EXT.has(ext) ? 'public, max-age=86400' : 'no-cache',
    };
    if (!TEXT_EXT.has(ext) || !req) {
      headers['Content-Length'] = st.size;
      headers['Last-Modified'] = st.mtime.toUTCString();
      res.writeHead(200, headers);
      fs.createReadStream(file).pipe(res);
      return;
    }
    fs.readFile(file, (readErr, body) => {
      if (readErr) {
        res.writeHead(500, { 'Content-Type': 'text/plain' }).end('read error');
        return;
      }
      sendBuffer(req, res, body, headers);
    });
  });
}

/** Shared tail of sendJson/sendFile for text: ETag, conditional request, encoding. */
function sendBuffer(req, res, body, headers) {
  const etag = etagOf(body);
  headers.ETag = etag;
  headers.Vary = 'Accept-Encoding';
  if (req.headers['if-none-match'] === etag) {
    res.writeHead(304, headers).end();
    return;
  }
  const entry = encoded(etag, body);
  let payload = entry.raw;
  if (accepts(req, 'br')) {
    headers['Content-Encoding'] = 'br';
    payload = entry.br;
  } else if (accepts(req, 'gzip')) {
    headers['Content-Encoding'] = 'gzip';
    payload = entry.gzip;
  }
  headers['Content-Length'] = payload.length;
  res.writeHead(200, headers);
  res.end(payload);
}

module.exports = { sendJson, sendFile, MIME, TEXT_EXT, CACHE_EXT };
