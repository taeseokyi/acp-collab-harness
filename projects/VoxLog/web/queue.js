/* VoxLog 오프라인 업로드 대기열 - window.VoxQueue (docs/INTERFACE.md)
 * IndexedDB `voxlog` 판 2: 저장소 queue(keyPath clientId) · config(키 "main") · drafts · chunks.
 * sw.js 가 같은 DB·같은 규칙으로 올립니다(코드는 sw.js 안에 따로 있음 - 고치면 둘 다 고칠 것).
 * 녹음 초안의 주인 판정은 웹 잠금(navigator.locks)이 한다. 녹음 탭은 초안마다 배타 잠금을 쥐고,
 * 저장·정리가 끝날 때 놓는다. 다른 탭은 ifAvailable 로 잠금을 바로 얻어 보아 주인이 죽었으면 거둔다.
 * 웹 잠금이 없는 브라우저에서는 초안을 만들지 않는다(녹음·올리기는 그대로, 끊긴 녹음 되살리기만 꺼짐). */
(function () {
  'use strict';

  var DB_NAME = 'voxlog';
  var DB_VERSION = 2;
  var DEFAULT_CONFIG = { token: '', autoRecord: false, saveLocation: true };
  var NO_SAVE = '이 화면에서는 녹음을 저장할 수 없습니다';

  var idbOk = false;
  try { idbOk = !!window.indexedDB; } catch (e) { idbOk = false; }
  var memConfig = Object.assign({}, DEFAULT_CONFIG);
  var listeners = [];
  var dbPromise = null;
  var flushing = null;
  var flushAgain = false;
  var retryTimer = null;
  var activeDraft = null; // 이 탭이 지금 녹음 중인 초안(다른 탭의 draftRecover 가 건드리지 않게)
  var held = {};  // draftId -> 쥔 잠금을 놓는 함수
  var waits = {}; // draftId -> 기다리는 요청의 AbortController
  var recoverListeners = [];
  var OLD_DRAFT_FRESH_MS = 20000; // 잠금 이전 초안 전용: 구버전 탭이 녹음 중일 수 있는 시간

  function locksOk() {
    try {
      return !!(navigator.locks && typeof navigator.locks.request === 'function');
    } catch (e) {
      return false;
    }
  }

  function openDb() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise(function (resolve, reject) {
      try {
        var req = window.indexedDB.open(DB_NAME, DB_VERSION);
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
        req.onerror = function () { reject(req.error || new Error('indexedDB 오류')); };
        req.onblocked = function () { reject(new Error('indexedDB 막힘')); };
      } catch (e) { reject(e); }
    }).catch(function (e) {
      idbOk = false;
      dbPromise = null;
      throw e;
    });
    return dbPromise;
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

  function store(db, name, mode) {
    var tx = db.transaction(name, mode);
    return { tx: tx, st: tx.objectStore(name) };
  }

  function notify() {
    listeners.slice().forEach(function (cb) {
      try { cb(); } catch (e) { /* 화면 쪽 오류는 무시 */ }
    });
  }

  function getConfig() {
    if (!idbOk) return Promise.resolve(Object.assign({}, memConfig));
    return openDb().then(function (db) {
      var s = store(db, 'config', 'readonly');
      return reqP(s.st.get('main'));
    }).then(function (v) {
      return Object.assign({}, DEFAULT_CONFIG, v || {});
    }).catch(function () {
      return Object.assign({}, memConfig);
    });
  }

  function setConfig(partial) {
    partial = partial || {};
    if (!idbOk) { Object.assign(memConfig, partial); return Promise.resolve(); }
    return getConfig().then(function (cur) {
      var next = Object.assign({}, cur, partial);
      memConfig = Object.assign({}, next);
      return openDb().then(function (db) {
        var s = store(db, 'config', 'readwrite');
        s.st.put(next, 'main');
        return txDone(s.tx);
      });
    }).catch(function () {
      Object.assign(memConfig, partial);
    });
  }

  function pending() {
    if (!idbOk) return Promise.resolve([]);
    return openDb().then(function (db) {
      var s = store(db, 'queue', 'readonly');
      return reqP(s.st.getAll());
    }).then(function (rows) {
      rows.sort(function (a, b) { return (a.addedAt || 0) - (b.addedAt || 0); });
      return rows.map(function (r) {
        return {
          clientId: r.clientId,
          recordedAt: r.recordedAt,
          size: r.blob ? r.blob.size : 0,
          tries: r.tries || 0,
          lastError: r.lastError || null,
          state: r.state || 'waiting',
          mime: r.mime || (r.blob && r.blob.type) || 'audio/webm',
          location: r.location || null
        };
      });
    }).catch(function () { return []; });
  }

  function registerSync() {
    try {
      if (!('serviceWorker' in navigator)) return Promise.resolve();
      return navigator.serviceWorker.getRegistration().then(function (reg) {
        if (reg && reg.sync) return reg.sync.register('voxlog-upload');
      }).catch(function () { /* 등록 실패는 무시 - online/visibility 로 올림 */ });
    } catch (e) { return Promise.resolve(); }
  }

  function normLoc(l) {
    if (!l || typeof l.lat !== 'number' || typeof l.lon !== 'number') return null;
    return { lat: l.lat, lon: l.lon, accuracy: typeof l.accuracy === 'number' ? l.accuracy : 0 };
  }

  function locHeader(l) {
    l = normLoc(l);
    if (!l) return null;
    return l.lat.toFixed(6) + ',' + l.lon.toFixed(6) + ',' + Math.round(Math.max(0, l.accuracy));
  }

  function enqueue(item) {
    item = item || {};
    if (!idbOk) return Promise.reject(new Error(NO_SAVE));
    var clientId = item.clientId ||
      ('c-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8));
    var row = {
      clientId: clientId,
      blob: item.blob,
      mime: item.mime || (item.blob && item.blob.type) || 'audio/webm',
      recordedAt: item.recordedAt || new Date().toISOString(),
      durationMs: item.durationMs == null ? null : item.durationMs,
      tries: 0,
      lastError: null,
      state: 'waiting',
      location: normLoc(item.location),
      addedAt: Date.now()
    };
    return openDb().then(function (db) {
      var s = store(db, 'queue', 'readwrite');
      s.st.put(row);
      return txDone(s.tx);
    }).catch(function (e) {
      if (!idbOk) throw new Error(NO_SAVE);
      throw e;
    }).then(function () {
      notify();
      return registerSync();
    }).then(function () {
      flush().catch(function () { /* 실패는 lastError 에 남음 */ });
    });
  }

  // 늘 같은 출처 - 예전에 저장된 apiBase 는 무시
  function uploadUrl() {
    return new URL('api/recordings', document.baseURI).href;
  }

  function updateRow(db, clientId, patch) {
    var s = store(db, 'queue', 'readwrite');
    var g = s.st.get(clientId);
    g.onsuccess = function () {
      if (g.result) s.st.put(Object.assign(g.result, patch(g.result)));
    };
    return txDone(s.tx);
  }

  function removeRow(db, clientId) {
    var s = store(db, 'queue', 'readwrite');
    s.st.delete(clientId);
    return txDone(s.tx);
  }

  function doFlush() {
    var result = { sent: 0, failed: 0 };
    if (!idbOk) return Promise.resolve(result);
    var cfg, db, rows;
    return getConfig().then(function (c) {
      cfg = c;
      return openDb();
    }).then(function (d) {
      db = d;
      var s = store(db, 'queue', 'readonly');
      return reqP(s.st.getAll());
    }).then(function (all) {
      rows = all.filter(function (r) { return (r.state || 'waiting') === 'waiting'; }).sort(function (a, b) { return (a.addedAt || 0) - (b.addedAt || 0); });
      var url = uploadUrl();
      var i = 0;
      function next() {
        if (i >= rows.length) return Promise.resolve();
        var row = rows[i++];
        var headers = { 'Content-Type': row.mime || 'audio/webm' };
        if (row.recordedAt) headers['X-Recorded-At'] = row.recordedAt;
        if (row.durationMs != null) headers['X-Duration-Ms'] = String(row.durationMs);
        headers['X-Client-Id'] = row.clientId;
        var lh = locHeader(row.location);
        if (lh) headers['X-Location'] = lh;
        if (cfg.token) headers['Authorization'] = 'Bearer ' + cfg.token;
        return fetch(url, { method: 'POST', headers: headers, body: row.blob }).then(function (res) {
          if (res.ok) {
            return res.json().catch(function () { return null; }).then(function (body) {
              if (body && typeof body.id === 'string') {
                result.sent++;
                return removeRow(db, row.clientId).then(notify).then(next);
              }
              // 캡티브 포털·프록시의 200 text/html 처럼 JSON 메타가 없는 응답은 성공이 아니다.
              result.failed++;
              return updateRow(db, row.clientId, function (r) {
                return { lastError: '서버 응답이 올바르지 않음', tries: (r.tries || 0) + 1 };
              }).then(notify).then(function () {
                scheduleRetry('5');
                return next();
              });
            });
          }
          if (res.status === 401) {
            result.failed++;
            return updateRow(db, row.clientId, function () { return { lastError: '인증 실패' }; })
              .then(notify);
          }
          return res.json().catch(function () { return {}; }).then(function (body) {
            // 503(동시 업로드 자리 없음)·507(디스크 부족)·408(업로드 너무 느림)은 영구 실패가 아님 - 대기열에 남겨 다시 올림
            var perm = res.status === 400 || res.status === 413 || res.status === 415;
            var msg = (body && body.error) || (res.status === 413 ? '너무 큼(413)' : '서버 오류 ' + res.status);
            result.failed++;
            return updateRow(db, row.clientId, function (r) {
              var p = { lastError: msg, tries: (r.tries || 0) + 1 };
              if (perm) p.state = 'failed';
              return p;
            }).then(notify).then(function () {
              if (res.status >= 500 || res.status === 408) { // 서버 문제·408(업로드 너무 느림) - 멈추고, Retry-After(없으면 5초, 최대 60초) 뒤 한 번 더
                scheduleRetry(res.headers.get('Retry-After'));
                return;
              }
              return next();
            });
          });
        }, function () {
          result.failed++;
          return updateRow(db, row.clientId, function () { return { lastError: '연결 안 됨' }; })
            .then(notify);
        });
      }
      return next();
    }).then(function () { return result; }, function () { return result; });
  }

  // Background Sync 가 없는 브라우저도 5xx 뒤 스스로 다시 올림. 이미 걸려 있으면 다시 걸지 않음
  function scheduleRetry(header) {
    if (retryTimer) return;
    var sec = parseInt(header, 10);
    if (!(sec >= 0)) sec = 5;
    sec = Math.min(sec, 60);
    retryTimer = setTimeout(function () {
      retryTimer = null;
      flush().catch(function () {});
    }, sec * 1000);
  }

  // 올리는 중에 새로 넣은 녹음도 올라가게 - 진행 중이면 그게 끝난 뒤 한 번 더 돈다
  function flush() {
    if (flushing) { flushAgain = true; return flushing; }
    flushing = doFlush().then(function (r) {
      flushing = null;
      if (flushAgain) { flushAgain = false; return flush(); }
      return r;
    }, function (e) {
      flushing = null;
      if (flushAgain) { flushAgain = false; return flush(); }
      throw e;
    });
    return flushing;
  }

  function guard() {
    if (!idbOk) return Promise.reject(new Error(NO_SAVE));
    return openDb();
  }

  function remove(clientId) {
    return guard().then(function (db) { return removeRow(db, clientId); }).then(notify);
  }

  function blob(clientId) {
    if (!idbOk) return Promise.resolve(null);
    return openDb().then(function (db) {
      return reqP(store(db, 'queue', 'readonly').st.get(clientId));
    }).then(function (r) { return (r && r.blob) || null; }).catch(function () { return null; });
  }

  function retry(clientId) {
    return guard().then(function (db) {
      return updateRow(db, clientId, function () { return { state: 'waiting', tries: 0, lastError: null }; });
    }).then(function () {
      notify();
      return registerSync();
    }).then(function () {
      flush().catch(function () {});
    });
  }

  // ---- 녹음 중 초안: 조각을 바로 IndexedDB 에, 초안마다 웹 잠금을 쥔다 ----
  function draftRelease(draftId) {
    var release = held[draftId];
    if (release) {
      delete held[draftId];
      try { release(); } catch (e) { /* 무시 */ }
    }
    if (activeDraft === draftId) activeDraft = null;
  }

  // 잠금을 얻은 뒤에만 초안 줄을 넣는다. 잠금은 draftFinish/draftDiscard 가 놓을 때까지 쥔 채로 둔다.
  function draftStart(d) {
    d = d || {};
    var draftId = d.draftId;
    if (!draftId || !locksOk()) return Promise.resolve(false);
    var name = 'voxlog-draft-' + draftId;
    return new Promise(function (resolve) {
      try {
        navigator.locks.request(name, { ifAvailable: true }, function (lock) {
          if (!lock) return null; // 주인이 쥐고 있음 - 초안을 만들지 않는다
          var release;
          var hold = new Promise(function (r) { release = r; });
          held[draftId] = function () {
            delete held[draftId];
            release();
          };
          return guard().then(function (db) {
            var now = Date.now();
            var s = store(db, 'drafts', 'readwrite');
            s.st.put({
              draftId: draftId, mime: d.mime || 'audio/webm',
              recordedAt: d.recordedAt || new Date().toISOString(),
              location: normLoc(d.location), started: now, aliveAt: Infinity, lock: true
            });
            return txDone(s.tx);
          }).then(function () {
            activeDraft = draftId;
            resolve(true);
            return hold;
          }, function () {
            draftRelease(draftId);
            resolve(false);
            return null;
          });
        }).then(function () {
          resolve(false);
        }, function () {
          resolve(false);
        });
      } catch (e) {
        resolve(false);
      }
    });
  }

  // 덧붙임: 녹음 중 얻은 위치를 초안에 바로 적는다(초안이 이미 지워졌으면 아무것도 안 함)
  function draftSetLocation(draftId, location) {
    return guard().then(function (db) {
      var s = store(db, 'drafts', 'readwrite');
      var g = s.st.get(draftId);
      g.onsuccess = function () {
        var d = g.result;
        if (!d) return;
        d.location = normLoc(location);
        s.st.put(d);
      };
      return txDone(s.tx);
    });
  }

  function draftAppend(draftId, blobPart) {
    return guard().then(function (db) {
      var tx = db.transaction(['drafts', 'chunks'], 'readwrite');
      var st = tx.objectStore('chunks');
      var g = tx.objectStore('drafts').get(draftId);
      g.onsuccess = function () {
        var d = g.result;
        if (!d) return; // 초안이 이미 없으면(다른 탭이 가져갔거나 지웠으면) 고아 조각을 남기지 않는다
        tx.objectStore('drafts').put(d);
        // seq = 지금까지 쌓인 조각 수(같은 트랜잭션 안에서 셈)
        var cnt = st.index('draftId').count(IDBKeyRange.only(draftId));
        cnt.onsuccess = function () { st.add({ draftId: draftId, seq: cnt.result, blob: blobPart }); };
      };
      return txDone(tx);
    });
  }

  function draftClear(db, draftId) {
    var tx = db.transaction(['drafts', 'chunks'], 'readwrite');
    tx.objectStore('drafts').delete(draftId);
    var st = tx.objectStore('chunks');
    st.index('draftId').openKeyCursor(IDBKeyRange.only(draftId)).onsuccess = function (e) {
      var c = e.target.result;
      if (!c) return;
      st.delete(c.primaryKey);
      c.continue();
    };
    return txDone(tx);
  }

  function draftDiscard(draftId) {
    return guard().then(function (db) { return draftClear(db, draftId); }).then(function () {
      draftRelease(draftId);
    }, function (e) {
      draftRelease(draftId);
      throw e;
    });
  }

  // 초안을 조각 순으로 이어 올린다. 돌려주는 값: 초안이 있어 처리했으면 true, 초안이 없었으면 false
  function draftFinish(draftId, durationMs, location) {
    var db, draft;
    return guard().then(function (d) {
      db = d;
      return reqP(store(db, 'drafts', 'readonly').st.get(draftId));
    }).then(function (dr) {
      draft = dr;
      if (!draft) return null;
      return reqP(store(db, 'chunks', 'readonly').st.index('draftId').getAll(IDBKeyRange.only(draftId)));
    }).then(function (chunks) {
      if (!draft) return false;
      if (!chunks || !chunks.length) return draftClear(db, draftId).then(function () { return false; });
      chunks.sort(function (a, b) { return a.seq - b.seq; });
      var mime = draft.mime || 'audio/webm';
      var b = new Blob(chunks.map(function (c) { return c.blob; }), { type: mime });
      return enqueue({
        blob: b, mime: mime, recordedAt: draft.recordedAt,
        durationMs: durationMs == null ? null : durationMs, clientId: draftId,
        location: location !== undefined && location !== null ? location : draft.location
      }).then(function () { return draftClear(db, draftId); }).then(function () { return true; });
    }).then(function (done) {
      draftRelease(draftId);
      return done;
    }, function (e) {
      draftRelease(draftId);
      throw e;
    });
  }

  function recovered(n) {
    recoverListeners.slice().forEach(function (cb) {
      try { cb(n); } catch (e) { /* 화면 쪽 오류는 무시 */ }
    });
    notify();
  }

  function onrecover(cb) {
    if (typeof cb === 'function') recoverListeners.push(cb);
  }

  // 주인이 쥔 새 세대 초안에 거는 요청. 주인이 죽으면 잠금을 받아 회수하고, freeze/pagehide 에서 abort 한다.
  function waitForDraft(draftId) {
    if (waits[draftId]) return;
    var name = 'voxlog-draft-' + draftId;
    var ac;
    try { ac = new AbortController(); } catch (e) { return; }
    waits[draftId] = ac;
    try {
      navigator.locks.request(name, { signal: ac.signal }, function () {
        delete waits[draftId];
        return draftFinish(draftId, null).then(function (done) {
          if (done === true) recovered(1);
        });
      }).then(function () {
        delete waits[draftId];
      }, function (e) {
        delete waits[draftId];
        if (e && e.name === 'AbortError') return;
        // 다른 실패는 조용히 삼킨다 - 다음 방문에서 다시 본다.
      });
    } catch (e) {
      delete waits[draftId];
    }
  }

  // 끝나지 않은 초안을 회수한다. 구세대 초안은 잠금 이전 탭 보호를 위해 20초 신선도 필터를 먼저 본다.
  // 즉시 ifAvailable 판정으로 살린 수를 돌려주고, 주인이 쥔 새 세대 초안에는 기다리는 요청을 건다.
  function draftRecover(exceptDraftId) {
    if (!locksOk()) return Promise.resolve(0);
    var n = 0;

    function recoverOne(draft) {
      var id = draft.draftId;
      var name = 'voxlog-draft-' + id;
      if (draft.lock !== true) {
        if (typeof draft.aliveAt === 'number' && Date.now() - draft.aliveAt < OLD_DRAFT_FRESH_MS) {
          return Promise.resolve();
        }
      }
      return navigator.locks.request(name, { ifAvailable: true }, function (lock) {
        if (!lock) return null;
        return draftFinish(id, null);
      }).then(function (done) {
        if (done === true) n++;
        if (done === null && draft.lock === true) waitForDraft(id);
      }, function () { /* 즉시 판정 실패는 다음 방문에서 다시 본다 */ });
    }

    return guard().then(function (db) {
      return reqP(store(db, 'drafts', 'readonly').st.getAll());
    }).then(function (rows) {
      var drafts = (rows || []).filter(function (draft) {
        if (!draft || !draft.draftId) return false;
        if (draft.draftId === exceptDraftId) return false;
        if (draft.draftId === activeDraft) return false;
        if (held[draft.draftId]) return false;
        return true;
      });
      return drafts.reduce(function (p, draft) {
        return p.then(function () { return recoverOne(draft); });
      }, Promise.resolve()).then(function () { return n; });
    });
  }

  // 기다리는 요청만 abort 한다. 쥔 잠금(held)은 freeze/pagehide 에서 놓지 않는다(녹음 탭이 스스로 정리할 때까지).
  function abortWaits() {
    Object.keys(waits).forEach(function (draftId) {
      var ac = waits[draftId];
      delete waits[draftId];
      try { ac.abort(); } catch (e) { /* 무시 */ }
    });
  }

  function resumeRecover() {
    draftRecover().then(function (n) {
      if (n > 0) recovered(n);
    }, function () { /* 무시 */ });
  }

  function onchange(cb) {
    if (typeof cb === 'function') listeners.push(cb);
  }

  function supported() {
    var sw = false, bg = false;
    try {
      sw = 'serviceWorker' in navigator && !!window.isSecureContext;
      bg = sw && 'SyncManager' in window;
    } catch (e) { /* 격리된 출처 */ }
    return { indexedDB: idbOk, serviceWorker: sw, backgroundSync: bg, draftLocks: locksOk() };
  }

  window.VoxQueue = {
    getConfig: getConfig,
    setConfig: setConfig,
    enqueue: enqueue,
    pending: pending,
    flush: flush,
    remove: remove,
    blob: blob,
    retry: retry,
    draftStart: draftStart,
    draftAppend: draftAppend,
    draftSetLocation: draftSetLocation,
    draftFinish: draftFinish,
    draftDiscard: draftDiscard,
    draftRecover: draftRecover,
    onrecover: onrecover,
    onchange: onchange,
    supported: supported
  };

  // 서비스 워커 등록(한 번) + 이벤트 연결
  try {
    if ('serviceWorker' in navigator && window.isSecureContext) {
      navigator.serviceWorker.register('sw.js').catch(function () { /* 무시 */ });
      navigator.serviceWorker.addEventListener('message', function (ev) {
        if (ev.data && ev.data.type === 'voxlog-queue') notify();
      });
    }
  } catch (e) { /* 무시 */ }

  try {
    window.addEventListener('online', function () { flush().catch(function () {}); });
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') flush().catch(function () {});
    });
  } catch (e) { /* 무시 */ }

  // 페이지 수명(한 번만 등록): 얼어붙은 대기 요청을 줄에서 빼고, 다시 보이면 회수를 다시 건다.
  try {
    document.addEventListener('freeze', abortWaits);
    window.addEventListener('pagehide', abortWaits);
    document.addEventListener('resume', resumeRecover);
    window.addEventListener('pageshow', resumeRecover);
  } catch (e) { /* 무시 */ }

  // 격리된 출처면 여기서 idbOk 가 false 로 바뀜
  if (idbOk) openDb().catch(function () {});
})();

