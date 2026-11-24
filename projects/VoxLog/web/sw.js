/* VoxLog 서비스 워커: 앱 껍데기 캐시 + Background Sync 업로드.
 * 업로드 규칙은 queue.js 와 같음(importScripts 없이 여기에 따로 둠 - 고치면 둘 다 고칠 것). */
'use strict';

var VERSION = 10;
var CACHE = 'voxlog-shell-v' + VERSION;
var SHELL = [
  './', 'index.html', 'style.css', 'app.js', 'api.js', 'md.js', 'queue.js', 'manifest.webmanifest',
  'icons/icon.svg', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      // 하나가 없어도 설치가 깨지지 않게 따로따로 담음
      return Promise.all(SHELL.map(function (u) {
        return cache.add(new Request(u, { cache: 'reload' })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return k.indexOf('voxlog-shell-') === 0 && k !== CACHE;
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf('/api/') !== -1) return;
  event.respondWith(
    fetch(req).then(function (res) {
      if (res && res.ok && res.type === 'basic') {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { return c.put(req, copy); }).catch(function () {});
      }
      return res;
    }).catch(function () {
      return caches.match(req).then(function (hit) {
        if (hit) return hit;
        return caches.match(req, { ignoreSearch: true }).then(function (h2) {
          if (h2) return h2;
          if (req.mode === 'navigate') {
            return caches.match('./', { ignoreSearch: true }).then(function (h3) {
              return h3 || caches.match('index.html', { ignoreSearch: true });
            });
          }
          return Response.error();
        });
      });
    })
  );
});

// ---- 업로드 (queue.js 와 같은 DB·같은 규칙) ----

function openDb() {
  return new Promise(function (resolve, reject) {
    var req = indexedDB.open('voxlog', 2);
      req.onupgradeneeded = function (ev) {
        var db = req.result;
        var q;
        if (!db.objectStoreNames.contains('queue')) q = db.createObjectStore('queue', { keyPath: 'clientId' });
        else q = req.transaction.objectStore('queue');
        if (!db.objectStoreNames.contains('config')) db.createObjectStore('config');
        if (!db.objectStoreNames.contains('drafts')) db.createObjectStore('drafts', { keyPath: 'draftId' });
        if (!db.objectStoreNames.contains('chunks')) {
          db.createObjectStore('chunks', { autoIncrement: true }).createIndex('draftId', 'draftId');
        }
        if (ev.oldVersion < 2) { // 판 1 의 줄에 state 를 채움
          q.openCursor().onsuccess = function (e) {
            var c = e.target.result;
            if (!c) return;
            if (!c.value.state) { var v = c.value; v.state = 'waiting'; c.update(v); }
            c.continue();
          };
        }
      };
    req.onsuccess = function () { resolve(req.result); };
    req.onerror = function () { reject(req.error); };
  });
}

function reqP(req) {
  return new Promise(function (resolve, reject) {
    req.onsuccess = function () { resolve(req.result); };
    req.onerror = function () { reject(req.error); };
  });
}

function txDone(tx) {
  return new Promise(function (resolve, reject) {
    tx.oncomplete = function () { resolve(); };
    tx.onerror = function () { reject(tx.error); };
    tx.onabort = function () { reject(tx.error || new Error('저장 취소')); };
  });
}

function updateRow(db, clientId, patch) {
  var tx = db.transaction('queue', 'readwrite');
  var st = tx.objectStore('queue');
  var g = st.get(clientId);
  g.onsuccess = function () {
    if (g.result) st.put(Object.assign(g.result, patch(g.result)));
  };
  return txDone(tx);
}

function removeRow(db, clientId) {
  var tx = db.transaction('queue', 'readwrite');
  tx.objectStore('queue').delete(clientId);
  return txDone(tx);
}

function notifyClients() {
  return self.clients.matchAll({ includeUncontrolled: true, type: 'window' }).then(function (list) {
    list.forEach(function (c) { c.postMessage({ type: 'voxlog-queue' }); });
  });
}

var running = null;

// 네트워크 오류·서버 5xx 면 throw(브라우저가 sync 를 다시 시도). 401 은 멈추기만.
function uploadQueue() {
  if (running) return running;
  running = doUpload().then(function () { running = null; }, function (e) { running = null; throw e; });
  return running;
}

function doUpload() {
  var db, cfg, retryError = null;
  return openDb().then(function (d) {
    db = d;
    var tx = db.transaction('config', 'readonly');
    return reqP(tx.objectStore('config').get('main'));
  }).then(function (c) {
    cfg = Object.assign({ token: '' }, c || {});
    var tx = db.transaction('queue', 'readonly');
    return reqP(tx.objectStore('queue').getAll());
  }).then(function (rows) {
    rows = rows.filter(function (r) { return (r.state || 'waiting') === 'waiting'; });
    rows.sort(function (a, b) { return (a.addedAt || 0) - (b.addedAt || 0); });
    // 늘 같은 출처 - 예전에 저장된 apiBase 는 무시
    var url = new URL('api/recordings', self.registration.scope).href;
    var i = 0;
    function next() {
      if (i >= rows.length) return Promise.resolve();
      var row = rows[i++];
      var headers = { 'Content-Type': row.mime || 'audio/webm' };
      if (row.recordedAt) headers['X-Recorded-At'] = row.recordedAt;
      if (row.durationMs != null) headers['X-Duration-Ms'] = String(row.durationMs);
      headers['X-Client-Id'] = row.clientId;
      var l = row.location;
      if (l && typeof l.lat === 'number' && typeof l.lon === 'number') {
        headers['X-Location'] = l.lat.toFixed(6) + ',' + l.lon.toFixed(6) + ',' +
          Math.round(Math.max(0, typeof l.accuracy === 'number' ? l.accuracy : 0));
      }
      if (cfg.token) headers['Authorization'] = 'Bearer ' + cfg.token;
      return fetch(url, { method: 'POST', headers: headers, body: row.blob }).then(function (res) {
        if (res.ok) {
          return res.json().catch(function () { return null; }).then(function (body) {
            if (body && typeof body.id === 'string') {
              return removeRow(db, row.clientId).then(notifyClients).then(next);
            }
            // 캡티브 포털·프록시의 200 text/html 처럼 JSON 메타가 없는 응답은 성공이 아니다.
            return updateRow(db, row.clientId, function (r) {
              return { lastError: '서버 응답이 올바르지 않음', tries: (r.tries || 0) + 1 };
            }).then(function () {
              retryError = new Error('서버 응답이 올바르지 않음');
              return next();
            });
          });
        }
        if (res.status === 401) {
          return updateRow(db, row.clientId, function () { return { lastError: '인증 실패' }; });
        }
        return res.json().catch(function () { return {}; }).then(function (body) {
          // 503(동시 업로드 자리 없음)·507(디스크 부족)·408(업로드 너무 느림)은 영구 실패가 아님 - 대기열에 남겨 다시 올림
          var perm = res.status === 400 || res.status === 413 || res.status === 415;
          var msg = (body && body.error) || (res.status === 413 ? '너무 큼(413)' : '서버 오류 ' + res.status);
          return updateRow(db, row.clientId, function (r) {
            var p = { lastError: msg, tries: (r.tries || 0) + 1 };
            if (perm) p.state = 'failed';
            return p;
          }).then(function () {
            if (res.status >= 500 || res.status === 408) { retryError = new Error(msg); return; }
            return next();
          });
        });
      }, function () {
        return updateRow(db, row.clientId, function () { return { lastError: '연결 안 됨' }; })
          .then(function () { retryError = new Error('network'); });
      });
    }
    return next();
  }).then(function () {
    return notifyClients();
  }, function (e) {
    return notifyClients().then(function () { throw e; });
  }).then(function () {
    if (retryError) throw retryError;
  });
}

self.addEventListener('sync', function (event) {
  if (event.tag === 'voxlog-upload') event.waitUntil(uploadQueue());
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'flush') {
    event.waitUntil(uploadQueue().catch(function () {}));
  }
});
