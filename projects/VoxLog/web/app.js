/* VoxLog - 화면. 빌드 없는 바닐라 JS. 서버에서 온 글은 textContent 로만 넣는다. */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  var STATUS = { pending: '대기', transcribing: '받아쓰는 중', done: '완료', failed: '실패', 'no-stt': '음성인식 없음' };
  var KIND = { summary: '요약', keywords: '핵심어', todo: '할 일', custom: '직접 묻기' };
  var UNSUPPORTED = '녹음은 VoxLog 자체 주소에서 - 여기서는 기록·묻기만';

  var state = {
    cfg: { token: '', autoRecord: false, saveLocation: true },
    selected: new Set(),
    detailId: null,
    detailStatus: null,
    audioObjectUrl: null,
    listTimer: 0,
    listSeq: 0,
    searchTimer: 0,
    lastItems: [],
    queueCount: 0,
    // 녹음
    rec: null, stream: null, chunks: [], startedAt: 0, startedIso: '', mime: '',
    timer: 0, wake: null, busy: false,
    rc: null, flushTimer: 0,
    // 묻기
    askToken: 0, askTimer: 0,
    // 열기 신호
    loadedAt: Date.now(), initialOpenHandled: false, consumerCalls: 0
  };

  /* ---------- 작은 도구 ---------- */

  var toastTimer = 0;
  function toast(msg) {
    var t = $('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, 4500);
  }

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fmtClock(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    return pad(Math.floor(s / 60)) + ':' + pad(s % 60);
  }
  function fmtTime(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso || '';
    return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  // 지역 시각 + 오프셋 ISO: 2026-11-16T08:00:00.000+09:00 (서버는 앞 10자를 날짜로 씀)
  function localIso(d) {
    var off = -d.getTimezoneOffset();
    var sign = off < 0 ? '-' : '+';
    off = Math.abs(off);
    var ms = d.getMilliseconds();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T' +
      pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()) + '.' +
      (ms < 10 ? '00' : ms < 100 ? '0' : '') + ms + sign + pad(Math.floor(off / 60)) + ':' + pad(off % 60);
  }
  function fmtSize(n) {
    if (n >= 1048576) return (n / 1048576).toFixed(1) + 'MB';
    return Math.max(1, Math.round(n / 1024)) + 'KB';
  }
  function isolated() {
    try {
      var q = window.VoxQueue;
      var sp = q && q.supported ? q.supported() : null;
      return location.origin === 'null' || !sp || !sp.indexedDB;
    } catch (e) { return true; }
  }
  function localDate(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }
  function uuid() {
    try { if (crypto.randomUUID) return crypto.randomUUID(); } catch (e) { /* 아래 대체 */ }
    return 'c-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function api() { return window.VoxApi; }

  function setConn(kind, text) {
    var c = $('conn');
    c.dataset.state = kind;
    c.textContent = text;
  }
  function onApiError(e) {
    if (e && e.status === 401) setConn('bad', '인증 필요');
    else if (e && e.status === 0) setConn('bad', '연결 안 됨');
    toast((e && e.message) || '오류가 났습니다');
  }

  /* ---------- 탭·설정 ---------- */

  function showTab(name) {
    ['rec', 'list', 'ask'].forEach(function (n) {
      var on = n === name;
      $('tab-' + n).hidden = !on;
      $('tabbtn-' + n).setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if (name === 'list') loadList();
    if (name === 'ask') { loadAnswers(); updateSelCount(); }
  }

  function fillSettings() {
    $('token').value = state.cfg.token || '';
    $('auto-record').checked = !!state.cfg.autoRecord;
    $('save-location').checked = state.cfg.saveLocation !== false;
  }
  function saveSetting(partial) {
    Object.assign(state.cfg, partial);
    return api().setConfig(partial);
  }

  function checkHealth(showOut) {
    var out = $('health-out');
    if (showOut) out.textContent = '확인 중…';
    return api().json('api/health').then(function (h) {
      setConn('ok', '연결됨');
      var stt = { command: '명령', openrouter: 'OpenRouter', none: '없음' }[h.stt] || String(h.stt);
      if (showOut) {
        out.textContent = '음성인식: ' + stt + ' · 묻기(claude): ' + (h.llm ? '준비됨' : '없음') +
          ' · 인증: ' + (h.auth ? '필요' : '안 씀');
      }
    }, function (e) {
      if (showOut) out.textContent = '실패: ' + e.message;
      onApiErrorQuiet(e);
    });
  }
  function onApiErrorQuiet(e) {
    if (e && e.status === 401) setConn('bad', '인증 필요');
    else setConn('bad', '연결 안 됨');
  }

  /* ---------- 대기열 ---------- */

  function queueApi() { try { return window.VoxQueue || null; } catch (e) { return null; } }

  function updateQueue() {
    var q = queueApi();
    if (!q) return Promise.resolve();
    var p;
    try { p = Promise.resolve(q.pending()); } catch (e) { return Promise.resolve(); }
    return p.then(function (arr) {
      arr = arr || [];
      var n = arr.filter(function (r) { return r.state !== 'failed'; }).length;
      renderFailed(arr.filter(function (r) { return r.state === 'failed' || r.lastError; }));
      var prev = state.queueCount;
      state.queueCount = n;
      var el = $('queue-count');
      el.textContent = '올릴 녹음 ' + n + '건';
      el.hidden = n === 0;
      if (n < prev) loadList();
    }, function () { /* 무시 */ });
  }

  function downloadRow(r) {
    var q = queueApi();
    Promise.resolve(q.blob(r.clientId)).then(function (b) {
      if (!b) { toast('녹음을 꺼내지 못했습니다.'); return; }
      var ext = /mp4/.test(r.mime || '') ? 'm4a' : /ogg/.test(r.mime || '') ? 'ogg' : 'webm';
      var a = document.createElement('a');
      var url = URL.createObjectURL(b);
      a.href = url;
      a.download = 'voxlog-' + String(r.recordedAt || r.clientId).replace(/[^0-9A-Za-z]+/g, '-') + '.' + ext;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    });
  }

  function renderFailed(rows) {
    var box = $('failed-box');
    var ul = $('failed-list');
    clear(ul);
    box.hidden = rows.length === 0;
    var iso = isolated();
    rows.forEach(function (r) {
      var li = document.createElement('li');
      li.className = 'failed-item';
      li.dataset.id = r.clientId;
      var info = document.createElement('div');
      info.textContent = fmtTime(r.recordedAt) + ' · ' + fmtSize(r.size);
      var why = document.createElement('div');
      why.className = 'why';
      why.textContent = r.state === 'failed'
        ? '서버가 받지 않았습니다: ' + (r.lastError || '알 수 없음')
        : '아직 올리지 못했습니다: ' + r.lastError;
      var row = document.createElement('div');
      row.className = 'row';
      function btn(label, cls, fn) {
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = label;
        if (cls) b.className = cls;
        b.addEventListener('click', fn);
        row.appendChild(b);
      }
      btn('내려받기', 'f-download', function () { downloadRow(r); });
      btn('다시 올리기', 'f-retry', function () {
        Promise.resolve(queueApi().retry(r.clientId)).then(updateQueue, function (e) { toast((e && e.message) || '다시 올리지 못했습니다'); });
      });
      if (!iso) {
        btn('지우기', 'danger f-remove', function () {
          if (!window.confirm('이 녹음을 기기에서 지울까요? 서버에 올라가지 않은 녹음이라 되돌릴 수 없습니다.')) return;
          Promise.resolve(queueApi().remove(r.clientId)).then(updateQueue, function (e) { toast((e && e.message) || '지우지 못했습니다'); });
        });
      }
      li.appendChild(info); li.appendChild(why); li.appendChild(row);
      ul.appendChild(li);
    });
  }

  /* ---------- 녹음 ---------- */

  function getLocation() {
    return new Promise(function (resolve) {
      if (state.cfg.saveLocation === false) return resolve(null);
      var done = false;
      function fin(v) { if (!done) { done = true; resolve(v); } }
      try {
        if (!navigator.geolocation) return fin(null);
        setTimeout(function () { fin(null); }, 12000);
        navigator.geolocation.getCurrentPosition(function (pos) {
          var c = pos && pos.coords;
          if (!c || typeof c.latitude !== 'number' || typeof c.longitude !== 'number') return fin(null);
          fin({ lat: c.latitude, lon: c.longitude, accuracy: Math.round(c.accuracy || 0) });
        }, function () { fin(null); }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
      } catch (e) { fin(null); }
    });
  }

  function recSupported() {
    try {
      var q = queueApi();
      var s = q && q.supported ? q.supported() : null;
      if (!s || !s.indexedDB) return false;
      if (!window.isSecureContext) return false;
      if (typeof window.MediaRecorder === 'undefined') return false;
      if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) return false;
      return true;
    } catch (e) {
      return false;
    }
  }

  function applyRecSupport() {
    var ok = recSupported();
    $('rec-unsupported').hidden = ok;
    $('rec').disabled = !ok;
  }

  function pickMime() {
    var list = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
    for (var i = 0; i < list.length; i++) {
      try { if (MediaRecorder.isTypeSupported(list[i])) return list[i]; } catch (e) { /* 다음 */ }
    }
    return '';
  }

  function micMessage(e) {
    var n = e && e.name;
    if (n === 'NotAllowedError' || n === 'SecurityError') return '마이크 권한이 거절되었습니다. 브라우저 설정에서 마이크를 허용해 주세요.';
    if (n === 'NotFoundError' || n === 'OverconstrainedError') return '마이크를 찾을 수 없습니다.';
    if (n === 'NotReadableError') return '마이크가 다른 앱에서 쓰이고 있습니다.';
    return '마이크를 열 수 없습니다' + (n ? ' (' + n + ')' : '') + '.';
  }

  function setRecUI(on) {
    var b = $('rec');
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.classList.toggle('recording', on);
    $('rec-label').textContent = on ? '멈춤' : '녹음';
  }

  function lockScreen() {
    try {
      Promise.resolve(navigator.wakeLock.request('screen')).then(function (l) { state.wake = l; }, function () {});
    } catch (e) { /* 실패는 무시 */ }
  }
  function unlockScreen() {
    try { if (state.wake) state.wake.release(); } catch (e) { /* 무시 */ }
    state.wake = null;
  }

  function startRec() {
    if (!recSupported()) { toast(UNSUPPORTED); return Promise.resolve(); }
    state.busy = true;
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var mime = pickMime();
      var mr;
      try {
        mr = mime ? new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 32000 })
          : new MediaRecorder(stream, { audioBitsPerSecond: 32000 });
      } catch (e) {
        stream.getTracks().forEach(function (t) { t.stop(); });
        toast('이 브라우저는 녹음 형식을 지원하지 않습니다.');
        return;
      }
      var rc = { // 녹음마다 자기 상태 - 멈춘 녹음의 저장이 다음 녹음과 섞이지 않게
        mr: mr, stream: stream, chunks: [], mime: mr.mimeType || mime || 'audio/webm',
        startedAt: Date.now(), draftId: uuid(), draftOk: false, chain: Promise.resolve(), locDone: null, loc: null, timer: 0
      };
      rc.startedIso = localIso(new Date(rc.startedAt));
      state.rc = rc;
      state.rec = mr;
      var dq = queueApi();
      try {
        rc.chain = Promise.resolve(dq.draftStart({ draftId: rc.draftId, mime: rc.mime, recordedAt: rc.startedIso, location: null }))
          .then(function () { rc.draftOk = true; }, function () { rc.draftOk = false; });
      } catch (e) { rc.chain = Promise.resolve(); }
      // 위치를 얻는 대로 초안에 적는다 - 페이지가 내려가 초안으로 살아난 녹음도 위치를 가지고 간다
      rc.locDone = getLocation().then(function (loc) {
        rc.loc = loc;
        if (loc) {
          rc.chain = rc.chain.then(function () {
            if (!rc.draftOk) return;
            return Promise.resolve(dq.draftSetLocation(rc.draftId, loc)).catch(function () {});
          });
        }
      });
      mr.ondataavailable = function (ev) {
        if (!(ev.data && ev.data.size)) return;
        rc.chunks.push(ev.data);
        var part = ev.data;
        rc.chain = rc.chain.then(function () {
          if (!rc.draftOk) return;
          return Promise.resolve(dq.draftAppend(rc.draftId, part)).catch(function () { rc.draftOk = false; });
        });
      };
      mr.onerror = function () { toast('녹음 중 오류가 났습니다.'); };
      mr.onstop = function () { finishRec(rc); };
      mr.start(5000);
      setRecUI(true);
      $('rec-time').textContent = '00:00';
      rc.timer = setInterval(function () {
        $('rec-time').textContent = fmtClock(Date.now() - rc.startedAt);
      }, 500);
      $('rec-result').textContent = '녹음 중…';
      lockScreen();
    }, function (e) {
      toast(micMessage(e));
    }).then(function () { state.busy = false; }, function () { state.busy = false; });
  }

  function stopRec() {
    if (!state.rec) return;
    var mr = state.rec;
    try { if (mr.state !== 'inactive') mr.stop(); } catch (e) { finishRec(state.rc); }
  }

  function finishRec(rc) {
    if (!rc || rc.finished) return;
    rc.finished = true;
    var durationMs = Date.now() - rc.startedAt;
    clearInterval(rc.timer);
    if (rc.stream) rc.stream.getTracks().forEach(function (t) { t.stop(); });
    if (state.rc === rc) { state.rc = null; state.rec = null; }
    unlockScreen();
    setRecUI(false);
    var type = rc.mime || 'audio/webm';
    var blob = new Blob(rc.chunks, { type: type });
    var draftId = rc.draftId;
    var q = queueApi();
    if (!blob.size) {
      $('rec-result').textContent = '녹음된 소리가 없어 저장하지 않았습니다.';
      rc.chain.then(function () { return q.draftDiscard(draftId); }).catch(function () {});
      return;
    }
    $('rec-result').textContent = '저장 중…';
    var p = rc.locDone.then(function () { return rc.chain; }).then(function () {
      var item = { blob: blob, mime: type, recordedAt: rc.startedIso, durationMs: durationMs, clientId: draftId, location: rc.loc };
      if (rc.draftOk) {
        return Promise.resolve(q.draftFinish(draftId, durationMs, rc.loc)).catch(function () { return q.enqueue(item); });
      }
      return q.enqueue(item);
    });
    p.then(function () {
      $('rec-result').textContent = '마지막 녹음 ' + fmtClock(durationMs) + ' · 저장됨, 서버로 올리는 중입니다.';
      updateQueue();
    }, function (e) {
      $('rec-result').textContent = '저장하지 못했습니다.';
      toast('녹음을 저장하지 못했습니다: ' + ((e && e.message) || ''));
    });
  }

  function toggleRec() {
    if (state.busy) return Promise.resolve();
    if (state.rec) { stopRec(); return Promise.resolve(); }
    return startRec();
  }

  /* ---------- 열기 신호 (측면 버튼·바로가기) ---------- */

  function handleOpen(url) {
    var action = '', source = '';
    if (url) {
      try {
        var u = new URL(url, location.href);
        action = u.searchParams.get('action') || '';
        source = u.searchParams.get('source') || '';
      } catch (e) { /* 무시 */ }
    } else {
      source = 'launch'; // 주소 없이 온 launchQueue 신호는 '열림'
    }
    if (action === 'toggle') return toggleRec();
    if (source === 'launch' && state.cfg.autoRecord) return toggleRec();
    return Promise.resolve();
  }

  function initOpen() {
    var href = location.href;
    var params = new URL(href).searchParams;
    var had = params.has('action') || params.has('source');
    state.initialOpenHandled = had;
    var p = handleOpen(href);
    if (had) {
      try {
        params.delete('action'); params.delete('source');
        var qs = params.toString();
        history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
      } catch (e) { /* 무시 */ }
    }
    try {
      if (window.launchQueue && window.launchQueue.setConsumer) {
        window.launchQueue.setConsumer(function (lp) {
          state.consumerCalls++;
          // 처음 열릴 때는 주소로 이미 처리했으므로, 열린 뒤 3초 안에 오는 같은 신호는 몇 번이든 무시한다
          if (state.initialOpenHandled && Date.now() - state.loadedAt < 3000) return;
          handleOpen(lp && lp.targetURL ? lp.targetURL : null);
        });
      }
    } catch (e) { /* 무시 */ }
    return p;
  }

  /* ---------- 기록 ---------- */

  function filterParams(limit) {
    var p = new URLSearchParams();
    var q = $('search').value.trim();
    if (q) p.set('q', q);
    if ($('date-from').value) p.set('from', $('date-from').value);
    if ($('date-to').value) p.set('to', $('date-to').value);
    if ($('status-filter').value) p.set('status', $('status-filter').value);
    if (limit) p.set('limit', String(limit));
    return p;
  }

  function renderStats(st) {
    st = st || {};
    $('stat-count').textContent = String(st.count || 0);
    $('stat-chars').textContent = String(st.chars || 0);
    var today = (st.by_date || {})[localDate(new Date())] || 0;
    $('stat-today').textContent = String(today);
  }

  function updateSelCount() {
    var n = state.selected.size;
    $('sel-count').textContent = '고른 것 ' + n + '건';
    $('ask-selected-count').textContent = '고른 녹취 ' + n + '건';
  }

  function renderList(items) {
    var ul = $('list');
    clear(ul);
    $('list-empty').hidden = items.length > 0;
    items.forEach(function (it) {
      var li = document.createElement('li');
      li.className = 'rec-item';
      li.dataset.id = it.id;
      if (it.id === state.detailId) li.classList.add('open');

      var pick = document.createElement('label');
      pick.className = 'rec-pick';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'rec-check';
      cb.checked = state.selected.has(it.id);
      cb.setAttribute('aria-label', '묻기에 쓸 녹취 고르기');
      cb.addEventListener('change', function () {
        if (cb.checked) state.selected.add(it.id); else state.selected.delete(it.id);
        updateSelCount();
      });
      pick.appendChild(cb);

      var main = document.createElement('div');
      main.className = 'rec-main';
      main.tabIndex = 0;
      main.setAttribute('role', 'button');

      var head = document.createElement('div');
      head.className = 'rec-head';
      var when = document.createElement('span');
      when.className = 'when';
      when.textContent = fmtTime(it.recorded_at || it.created);
      var dur = document.createElement('span');
      dur.className = 'dur';
      dur.textContent = it.duration_ms != null ? fmtClock(it.duration_ms) : '';
      var badge = document.createElement('span');
      badge.className = 'status s-' + it.status;
      badge.textContent = STATUS[it.status] || it.status;
      head.appendChild(when); head.appendChild(dur); head.appendChild(badge);
      if (it.location) {
        var pin = document.createElement('span');
        pin.className = 'loc-pin';
        pin.title = '위치 있음';
        pin.textContent = '📍';
        head.appendChild(pin);
      }

      var text = document.createElement('div');
      text.className = 'rec-text';
      var t = it.title || it.snippet || '';
      text.textContent = t || (it.status === 'done' ? '(빈 글)' : '(아직 글이 없습니다)');

      main.appendChild(head); main.appendChild(text);
      li.appendChild(pick); li.appendChild(main);
      li.addEventListener('click', function (ev) {
        if (pick.contains(ev.target)) return;
        openDetail(it.id);
      });
      main.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openDetail(it.id); }
      });
      ul.appendChild(li);
    });
  }

  function loadList() {
    var seq = ++state.listSeq;
    clearTimeout(state.listTimer);
    var qs = filterParams(200).toString();
    return api().json('api/recordings?' + qs).then(function (data) {
      if (seq !== state.listSeq) return;
      setConn('ok', '연결됨');
      var items = data.items || [];
      state.lastItems = items;
      renderStats(data.stats);
      renderList(items);
      var busy = items.some(function (i) { return i.status === 'pending' || i.status === 'transcribing'; });
      if (state.detailId && (state.detailStatus === 'pending' || state.detailStatus === 'transcribing')) {
        loadDetail(state.detailId, true);
        busy = true;
      }
      if (busy) state.listTimer = setTimeout(loadList, 5000);
    }, function (e) {
      if (seq !== state.listSeq) return;
      onApiError(e);
    });
  }

  /* ---------- 상세 ---------- */

  function setAudio(id) {
    var audio = $('detail-audio');
    if (state.audioObjectUrl) { URL.revokeObjectURL(state.audioObjectUrl); state.audioObjectUrl = null; }
    audio.removeAttribute('src');
    audio.load();
    $('audio-note').hidden = true;
    return api().audioUrl(id).then(function (url) {
      if (state.detailId !== id) { URL.revokeObjectURL(url); return; }
      state.audioObjectUrl = url;
      audio.src = url;
    }, function (e) {
      if (state.detailId !== id) return;
      $('audio-note').hidden = false;
      toast((e && e.message) || '음성을 불러오지 못했습니다');
    });
  }

  function renderLoc(loc) {
    var box = $('detail-loc');
    clear(box);
    var lat = loc ? Number(loc.lat) : NaN, lon = loc ? Number(loc.lon) : NaN;
    if (!isFinite(lat) || !isFinite(lon)) { box.hidden = true; return; }
    box.hidden = false;
    box.appendChild(document.createTextNode('📍 위치 ' + lat.toFixed(5) + ', ' + lon.toFixed(5) +
      (loc.accuracy != null ? ' (정확도 약 ' + Math.round(Number(loc.accuracy) || 0) + 'm) ' : ' ')));
    var a = document.createElement('a');
    a.id = 'detail-map';
    a.href = 'https://www.openstreetmap.org/?mlat=' + lat + '&mlon=' + lon + '#map=17/' + lat + '/' + lon;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = '지도에서 보기';
    box.appendChild(a);
  }

  function loadDetail(id, keepAudio) {
    return api().json('api/recordings/' + encodeURIComponent(id)).then(function (r) {
      if (state.detailId !== id) return;
      state.detailStatus = r.status;
      $('detail-title').textContent = r.title || '녹취';
      var meta = fmtTime(r.recorded_at || r.created) +
        (r.duration_ms != null ? ' · ' + fmtClock(r.duration_ms) : '') +
        ' · ' + (STATUS[r.status] || r.status) +
        (r.chars ? ' · ' + r.chars + '자' : '') +
        (r.error ? ' · ' + r.error : '');
      $('detail-meta').textContent = meta;
      renderLoc(r.location);
      $('detail-delete').hidden = isolated();
      var tr = $('transcript');
      if (r.transcript) tr.textContent = r.transcript;
      else if (r.status === 'pending' || r.status === 'transcribing') tr.textContent = '받아쓰는 중입니다…';
      else if (r.status === 'no-stt') tr.textContent = '음성인식 백엔드가 없어 글이 없습니다. 서버에 켠 뒤 \'다시 받아쓰기\'를 누르세요.';
      else tr.textContent = '(글이 없습니다)';
    }, function (e) {
      if (state.detailId === id) onApiError(e);
    });
  }

  function openDetail(id) {
    state.detailId = id;
    state.detailStatus = null;
    $('detail').hidden = false;
    $('detail-delete').hidden = isolated();
    $('detail-title').textContent = '녹취';
    $('detail-meta').textContent = '불러오는 중…';
    $('transcript').textContent = '';
    Array.prototype.forEach.call($('list').children, function (li) {
      li.classList.toggle('open', li.dataset.id === id);
    });
    setAudio(id);
    loadDetail(id).then(function () {
      if (state.detailStatus === 'pending' || state.detailStatus === 'transcribing') {
        clearTimeout(state.listTimer);
        state.listTimer = setTimeout(loadList, 5000);
      }
    });
    try { $('detail').scrollIntoView({ block: 'nearest' }); } catch (e) { /* 무시 */ }
  }

  function closeDetail() {
    state.detailId = null;
    state.detailStatus = null;
    $('detail').hidden = true;
    var audio = $('detail-audio');
    try { audio.pause(); } catch (e) { /* 무시 */ }
    if (state.audioObjectUrl) { URL.revokeObjectURL(state.audioObjectUrl); state.audioObjectUrl = null; }
    audio.removeAttribute('src');
    Array.prototype.forEach.call($('list').children, function (li) { li.classList.remove('open'); });
  }

  function retryDetail() {
    var id = state.detailId;
    if (!id) return;
    api().json('api/recordings/' + encodeURIComponent(id) + '/retry', { method: 'POST' }).then(function () {
      toast('다시 받아쓰기를 요청했습니다.');
      loadDetail(id);
      loadList();
    }, onApiError);
  }

  function deleteDetail() {
    var id = state.detailId;
    if (!id) return;
    if (!window.confirm('이 녹취(음성과 글)를 지울까요? 되돌릴 수 없습니다.')) return;
    api().json('api/recordings/' + encodeURIComponent(id), { method: 'DELETE' }).then(function () {
      state.selected.delete(id);
      updateSelCount();
      closeDetail();
      toast('지웠습니다.');
      loadList();
    }, onApiError);
  }

  /* ---------- 묻기 ---------- */

  function idsFor(scope) {
    if (scope === 'selected') return Promise.resolve(newest(Array.from(state.selected)));
    var p = new URLSearchParams();
    var now = new Date();
    if (scope === 'today') {
      p.set('from', localDate(now)); p.set('to', localDate(now));
    } else if (scope === 'week') {
      var from = new Date(now.getTime() - 6 * 86400000);
      p.set('from', localDate(from)); p.set('to', localDate(now));
    } else {
      p = filterParams(0);
    }
    p.set('limit', '500');
    return api().json('api/recordings?' + p.toString()).then(function (d) {
      return newest((d.items || []).map(function (i) { return i.id; }));
    });
  }

  // 한 번에 200건까지만 묻는다 (최신 것부터; id 는 시각순)
  var ASK_MAX = 200;
  function newest(ids) {
    if (ids.length <= ASK_MAX) return ids;
    ids = ids.slice().sort().reverse().slice(0, ASK_MAX);
    toast('최근 ' + ASK_MAX + '건만 묻습니다');
    return ids;
  }

  function showAnswer(a) {
    var st = $('answer-status');
    var box = $('answer');
    if (a.status === 'done') {
      st.textContent = (KIND[a.kind] || a.kind) + ' · ' + fmtTime(a.created) + ' · 녹취 ' + (a.ids || []).length + '건';
      box.textContent = a.answer || '(빈 답)';
    } else if (a.status === 'failed') {
      st.textContent = '실패';
      box.textContent = a.error || '답을 만들지 못했습니다.';
    } else {
      st.textContent = '묻는 중… (보통 수십 초 걸립니다)';
      box.textContent = '';
    }
  }

  function pollAnswer(aid, token) {
    clearTimeout(state.askTimer);
    state.askTimer = setTimeout(function () {
      api().json('api/answers/' + encodeURIComponent(aid)).then(function (a) {
        if (token !== state.askToken) return;
        showAnswer(a);
        if (a.status === 'done' || a.status === 'failed') {
          $('ask-go').disabled = false;
          loadAnswers();
        } else {
          pollAnswer(aid, token);
        }
      }, function (e) {
        if (token !== state.askToken) return;
        $('ask-go').disabled = false;
        onApiError(e);
      });
    }, 2000);
  }

  function ask() {
    var kind = $('ask-kind').value;
    var prompt = $('ask-prompt').value.trim();
    if (kind === 'custom' && !prompt) { toast('직접 묻기는 질문을 적어야 합니다.'); $('ask-prompt').focus(); return; }
    var scope = $('ask-scope').value;
    $('ask-go').disabled = true;
    var token = ++state.askToken;
    idsFor(scope).then(function (ids) {
      if (!ids.length) {
        $('ask-go').disabled = false;
        toast(scope === 'selected' ? '기록 탭에서 녹취를 먼저 골라 주세요.' : '그 범위에 녹취가 없습니다.');
        return;
      }
      $('answer-status').textContent = '요청 중…';
      $('answer').textContent = '';
      return api().json('api/ask', { method: 'POST', body: { kind: kind, prompt: prompt, ids: ids } }).then(function (a) {
        if (token !== state.askToken) return;
        showAnswer(a);
        if (a.status === 'done' || a.status === 'failed') { $('ask-go').disabled = false; loadAnswers(); }
        else pollAnswer(a.id, token);
      });
    }).catch(function (e) {
      $('ask-go').disabled = false;
      $('answer-status').textContent = '';
      onApiError(e);
    });
  }

  function loadAnswers() {
    return api().json('api/answers').then(function (d) {
      var ul = $('answers');
      clear(ul);
      var items = d.items || [];
      $('answers-empty').hidden = items.length > 0;
      items.forEach(function (a) {
        var li = document.createElement('li');
        li.className = 'answer-item';
        li.dataset.id = a.id;
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'answer-open';
        var head = document.createElement('span');
        head.className = 'when';
        head.textContent = (KIND[a.kind] || a.kind) + ' · ' + fmtTime(a.created);
        var badge = document.createElement('span');
        badge.className = 'status s-' + (a.status === 'done' ? 'done' : a.status === 'failed' ? 'failed' : 'transcribing');
        badge.textContent = a.status === 'done' ? '완료' : a.status === 'failed' ? '실패' : '묻는 중';
        var sub = document.createElement('span');
        sub.className = 'rec-text';
        sub.textContent = a.prompt || ('녹취 ' + (a.ids || []).length + '건');
        b.appendChild(head); b.appendChild(badge); b.appendChild(sub);
        b.addEventListener('click', function () {
          var token = ++state.askToken;
          $('ask-go').disabled = false;
          api().json('api/answers/' + encodeURIComponent(a.id)).then(function (full) {
            if (token !== state.askToken) return;
            showAnswer(full);
            if (full.status === 'running') { $('ask-go').disabled = true; pollAnswer(full.id, token); }
          }, onApiError);
        });
        li.appendChild(b);
        ul.appendChild(li);
      });
    }, function (e) { onApiErrorQuiet(e); });
  }

  /* ---------- 시작 ---------- */

  function bind() {
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) {
      b.addEventListener('click', function () { showTab(b.dataset.tab); });
    });
    $('settings-btn').addEventListener('click', function () {
      var s = $('settings');
      s.hidden = !s.hidden;
      $('settings-btn').setAttribute('aria-expanded', s.hidden ? 'false' : 'true');
    });
    function flushSoon() {
      clearTimeout(state.flushTimer);
      state.flushTimer = setTimeout(function () {
        try { var fq = queueApi(); if (fq && fq.flush) Promise.resolve(fq.flush()).then(updateQueue, function () {}); } catch (e) { /* 무시 */ }
      }, 600);
    }
    $('token').addEventListener('input', function () { saveSetting({ token: $('token').value }).then(flushSoon); });
    $('save-location').addEventListener('change', function () { saveSetting({ saveLocation: $('save-location').checked }); });
    $('auto-record').addEventListener('change', function () { saveSetting({ autoRecord: $('auto-record').checked }); });
    $('health-check').addEventListener('click', function () { checkHealth(true); });

    $('rec').addEventListener('click', function () { toggleRec(); });

    $('search').addEventListener('input', function () {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(loadList, 300);
    });
    ['date-from', 'date-to', 'status-filter'].forEach(function (id) {
      $(id).addEventListener('change', loadList);
    });
    $('sel-clear').addEventListener('click', function () {
      state.selected.clear();
      Array.prototype.forEach.call(document.querySelectorAll('.rec-check'), function (c) { c.checked = false; });
      updateSelCount();
    });
    $('detail-close').addEventListener('click', closeDetail);
    $('detail-retry').addEventListener('click', retryDetail);
    $('detail-delete').addEventListener('click', deleteDetail);

    $('ask-go').addEventListener('click', ask);
    $('ask-kind').addEventListener('change', function () {
      $('ask-prompt-hint').textContent = $('ask-kind').value === 'custom' ? '(필수)' : '(직접 묻기일 때 필수 · 다른 때는 덧붙일 말)';
    });

    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') {
        updateQueue();
        if (state.rec) lockScreen();
      }
    });
  }

  function init() {
    bind();
    updateSelCount();
    applyRecSupport(); // 설정을 읽기 전에도 안내는 바로 보이게
    var q = queueApi();
    try { if (q && q.onchange) q.onchange(function () { updateQueue(); }); } catch (e) { /* 무시 */ }
    api().getConfig().then(function (cfg) {
      state.cfg = cfg;
      fillSettings();
      applyRecSupport();
      updateQueue();
      checkHealth(false);
      var rq = queueApi();
      var rec;
      try { rec = Promise.resolve(rq.draftRecover()); } catch (e) { rec = Promise.resolve(0); }
      return rec.catch(function () { return 0; }).then(function (n) {
        if (n > 0) { toast('끝나지 않은 녹음 ' + n + '건을 살렸습니다'); updateQueue(); }
        return initOpen();
      });
    }).catch(function (e) { toast((e && e.message) || '시작 중 오류'); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
