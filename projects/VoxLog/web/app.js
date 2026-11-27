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
    tagFilter: '',
    llm: false,
    detailTimer: 0,
    detailAutotag: null,
    detailLastLabel: '',
    detailLastTags: '',
    detailSttOptions: null,
    detailPrevText: null,
    sttDefaults: null,
    sttDefaultsReq: null,
    sttFields: null,
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

  /* ---------- 받아쓰기 옵션 (설정 기본값·상세 다시 받아쓰기) ---------- */

  var STT_PREPROCESS = ['none', 'basic', 'level', 'dereverb', 'denoise'];
  var STT_PREPROCESS_LABEL = {
    none: 'none · 손대지 않음',
    basic: 'basic · 고역 통과 등 기본 처리',
    level: 'level · 기본 + 작은 목소리 음량 맞춤',
    dereverb: 'dereverb · 기본 + 울림 제거',
    denoise: 'denoise · 기본 + 잡음 제거'
  };
  var STT_CONTEXT_MAX = 4000;
  var STT_SPEAKERS_MIN = 1, STT_SPEAKERS_MAX = 20;

  // 두 묶음(설정·상세)이 같은 입력 모양을 쓰게 만드는 하나의 함수. 만든 입력을 돌려준다.
  function buildSttFields(box, prefix) {
    clear(box);
    var els = {};
    // 설정 묶음의 빈 칸은 서버 기본값, 상세 묶음의 빈 칸은 앱 설정(전체 기본값)을 따른다는 뜻이다.
    var detailGroup = prefix === 'detail-stt';
    var defaultLabel = detailGroup ? '기본(앱 설정 따름)' : '서버 기본';
    function field(labelText, child, key) {
      var label = document.createElement('label');
      label.className = 'field';
      label.textContent = labelText;
      if (key) child.id = prefix + '-' + key;
      label.appendChild(child);
      box.appendChild(label);
      return child;
    }
    function note(text) {
      var p = document.createElement('p');
      p.className = 'muted stt-why';
      p.textContent = text;
      box.appendChild(p);
    }
    function select(labelText, key, options) {
      var sel = document.createElement('select');
      options.forEach(function (pair) {
        var o = document.createElement('option');
        o.value = pair[0];
        o.textContent = pair[1];
        sel.appendChild(o);
      });
      return field(labelText, sel, key);
    }

    var preprocessLabel = detailGroup ? defaultLabel : '서버 기본(level)';
    els.preprocess = select('전처리', 'preprocess', [['', preprocessLabel]].concat(
      STT_PREPROCESS.map(function (v) { return [v, STT_PREPROCESS_LABEL[v]]; })));
    note('잡음이 많은 녹음은 denoise 가 나을 수 있습니다(보장은 아님). 깨끗한 녹음에서는 오히려 나빠질 수 있습니다.');

    var spk = document.createElement('input');
    spk.type = 'number';
    spk.min = String(STT_SPEAKERS_MIN);
    spk.max = String(STT_SPEAKERS_MAX);
    spk.step = '1';
    spk.inputMode = 'numeric';
    spk.placeholder = '빈칸 = 자동';
    els.speakers = field('화자 수 (1~' + STT_SPEAKERS_MAX + ', 빈칸 = 자동)', spk, 'speakers');

    var ctx = document.createElement('textarea');
    ctx.rows = 3;
    ctx.maxLength = STT_CONTEXT_MAX;
    ctx.placeholder = '예: 참석자 이름, 회의 이름 (기본은 비움)';
    els.context = field('문맥 글 (최대 ' + STT_CONTEXT_MAX + '자)', ctx, 'context');
    note('문맥 글은 조용한 구간에 새어 나오거나 낱말이 끌려갈 수 있어 기본은 비워 둡니다.');

    var tri = [['', defaultLabel], ['1', '켬'], ['0', '끔']];
    els.auto = select('자동 추정', 'auto', tri);
    els.review = select('LLM 검토', 'review', tri);
    return els;
  }

  // 녹음에 저장된 옵션이 '비어 있지 않은 dict' 일 때만 그것을 쓴다(없음·{} 는 전체 기본값).
  function hasSttOptions(o) {
    return !!o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).length > 0;
  }

  function fillSttFields(els, opts) {
    if (!els) return;
    opts = opts && typeof opts === 'object' ? opts : {};
    els.preprocess.value = STT_PREPROCESS.indexOf(opts.preprocess) >= 0 ? opts.preprocess : '';
    els.speakers.value = (typeof opts.num_speakers === 'number' && isFinite(opts.num_speakers))
      ? String(opts.num_speakers) : '';
    els.context.value = typeof opts.context === 'string' ? opts.context : '';
    els.auto.value = typeof opts.auto === 'boolean' ? (opts.auto ? '1' : '0') : '';
    els.review.value = typeof opts.review === 'boolean' ? (opts.review ? '1' : '0') : '';
  }

  // 고른 것만 담는다. 틀린 값은 한국어 한 줄로 던진다(서버도 같은 규칙으로 거절한다).
  function readSttFields(els) {
    var opts = {};
    var p = els.preprocess.value;
    if (p) {
      if (STT_PREPROCESS.indexOf(p) < 0) throw new Error('전처리 값이 올바르지 않습니다.');
      opts.preprocess = p;
    }
    var sp = String(els.speakers.value || '').trim();
    if (sp) {
      if (!/^\d+$/.test(sp) || Number(sp) < STT_SPEAKERS_MIN || Number(sp) > STT_SPEAKERS_MAX) {
        throw new Error('화자 수는 ' + STT_SPEAKERS_MIN + '~' + STT_SPEAKERS_MAX + ' 사이 정수여야 합니다.');
      }
      opts.num_speakers = Number(sp);
    }
    var ctx = String(els.context.value || '').trim();
    if (ctx) {
      if (ctx.length > STT_CONTEXT_MAX) throw new Error('문맥 글은 ' + STT_CONTEXT_MAX + '자까지입니다.');
      opts.context = ctx;
    }
    if (els.auto.value === '1') opts.auto = true;
    else if (els.auto.value === '0') opts.auto = false;
    if (els.review.value === '1') opts.review = true;
    else if (els.review.value === '0') opts.review = false;
    return opts;
  }

  function sttDefaults() {
    if (state.sttDefaults) return Promise.resolve(state.sttDefaults);
    if (state.sttDefaultsReq) return state.sttDefaultsReq;
    state.sttDefaultsReq = api().json('api/stt-options').then(function (d) {
      var o = d && d.options;
      state.sttDefaults = o && typeof o === 'object' && !Array.isArray(o) ? o : {};
      state.sttDefaultsReq = null;
      return state.sttDefaults;
    }, function (e) {
      state.sttDefaultsReq = null;
      throw e;
    });
    return state.sttDefaultsReq;
  }

  function loadSttSettings() {
    var box = $('stt-defaults');
    if (isolated()) { box.hidden = true; return; }
    box.hidden = false;
    var note = $('stt-defaults-note');
    note.textContent = '';
    $('stt-defaults-fields').hidden = false;
    $('stt-defaults-save').hidden = false;
    sttDefaults().then(function (opts) {
      fillSttFields(state.sttFields.defaults, opts);
    }, function (e) {
      $('stt-defaults-fields').hidden = true;
      $('stt-defaults-save').hidden = true;
      note.textContent = '받아쓰기 옵션을 불러오지 못했습니다: ' + ((e && e.message) || '알 수 없음');
    });
  }

  function saveSttDefaults() {
    var opts;
    try { opts = readSttFields(state.sttFields.defaults); }
    catch (e) { toast(e.message); return; }
    var st = $('stt-defaults-state');
    st.textContent = '저장 중…';
    api().json('api/stt-options', { method: 'PUT', body: { options: opts } }).then(function (d) {
      var o = d && d.options;
      state.sttDefaults = o && typeof o === 'object' && !Array.isArray(o) ? o : opts;
      fillSttFields(state.sttFields.defaults, state.sttDefaults);
      st.textContent = '';
      toast('받아쓰기 기본값을 저장했습니다.');
    }, function (e) {
      st.textContent = '';
      toast((e && e.message) || '받아쓰기 기본값을 저장하지 못했습니다');
    });
  }

  function openSttPanel() {
    var id = state.detailId;
    if (!id) return;
    var box = $('detail-stt');
    var opening = box.hidden;
    box.hidden = !opening;
    $('detail-retry-opts').setAttribute('aria-expanded', opening ? 'true' : 'false');
    if (!opening) return;
    if (hasSttOptions(state.detailSttOptions)) {
      fillSttFields(state.sttFields.detail, state.detailSttOptions);
      return;
    }
    fillSttFields(state.sttFields.detail, {});
    sttDefaults().then(function (opts) {
      // 여는 사이 다른 녹취로 바뀌었거나 다시 닫았으면 건드리지 않는다 (폴링도 이 입력은 지우지 않는다)
      if (state.detailId === id && !$('detail-stt').hidden) fillSttFields(state.sttFields.detail, opts);
    }, function (e) {
      if (state.detailId === id && !$('detail-stt').hidden) {
        $('detail-stt-state').textContent = '기본값을 불러오지 못했습니다: ' + ((e && e.message) || '알 수 없음');
      }
    });
  }

  function retryWithOptions() {
    var id = state.detailId;
    if (!id) return;
    var opts;
    try { opts = readSttFields(state.sttFields.detail); }
    catch (e) { toast(e.message); return; }
    var st = $('detail-stt-state');
    st.textContent = '요청 중…';
    api().json('api/recordings/' + encodeURIComponent(id) + '/retry', { method: 'POST', body: { options: opts } }).then(function () {
      st.textContent = '';
      $('detail-stt').hidden = true;
      $('detail-retry-opts').setAttribute('aria-expanded', 'false');
      toast('옵션을 바꿔 다시 받아쓰기를 요청했습니다. 바뀌기 전 글 중 가장 긴 것 한 벌이 남습니다.');
      loadDetail(id);
      loadList();
    }, function (e) {
      st.textContent = '';
      onApiError(e); // 400 이면 서버가 준 까닭이 토스트로 간다
    });
  }

  function sttUsedText(used) {
    if (!used || typeof used !== 'object') return '';
    var parts = [];
    if (typeof used.preprocess === 'string' && used.preprocess) parts.push('전처리 ' + used.preprocess);
    if (typeof used.speakers === 'number' && isFinite(used.speakers)) parts.push('화자 ' + used.speakers);
    if (typeof used.auto === 'boolean') parts.push('자동 추정 ' + (used.auto ? '켬' : '끔'));
    if (typeof used.review === 'boolean') parts.push('검토 ' + (used.review ? '켬' : '끔'));
    return parts.length ? '받아쓴 옵션: ' + parts.join(' · ') : '';
  }

  function renderSttUsed(used) {
    var el = $('detail-stt-used');
    var text = sttUsedText(used);
    el.textContent = text;
    el.hidden = !text;
  }

  function renderPrev(text, used) {
    var box = $('detail-prev');
    var pre = $('detail-prev-text');
    var sum = $('detail-prev-summary');
    var prev = typeof text === 'string' ? text : '';
    var p = used && typeof used === 'object' && typeof used.preprocess === 'string' ? used.preprocess : '';
    sum.textContent = '이전 글 중 가장 긴 것' + (p ? ' (전처리 ' + p + ')' : '');
    box.hidden = !prev;
    if (!prev) {
      if (state.detailPrevText !== null) { box.open = false; pre.textContent = ''; state.detailPrevText = null; }
      return;
    }
    if (state.detailPrevText !== prev) { // 폴링이 펼쳐 둔 것을 접지 않게, 글이 바뀔 때만 다시 채운다
      state.detailPrevText = prev;
      box.open = false;
      pre.textContent = prev;
    }
  }

  // 서버가 살아 있는지(api/health, 토큰 없이 답함)와 넣은 토큰이 통하는지(토큰이 필요한 호출)를 따로 본다.
  function checkHealth(showOut) {
    var out = $('health-out');
    if (showOut) out.textContent = '확인 중…';
    return api().json('api/health').then(function (h) {
      state.llm = !!h.llm;
      updateDetailRetag();
      var stt = { command: '명령', api: '서버', none: '없음' }[h.stt] || String(h.stt);
      var head = '음성인식: ' + stt + ' · 묻기(claude): ' + (h.llm ? '준비됨' : '없음') + ' · 인증: ';
      if (!h.auth) {
        setConn('ok', '연결됨');
        if (showOut) out.textContent = head + '안 씀';
        return;
      }
      return api().json('api/answers').then(function () {
        setConn('ok', '연결됨');
        if (showOut) out.textContent = head + '통과';
      }, function (e) {
        onApiErrorQuiet(e);
        if (!showOut) return;
        if (e && e.status === 401) {
          out.textContent = head + (state.cfg.token ? '토큰이 틀립니다' : '토큰을 넣어야 합니다');
        } else {
          out.textContent = '실패: ' + e.message;
        }
      });
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

  var REC_BITRATE = 64000; // 화자 구분에 목소리 특징이 남게 (30분 ≈ 14MB, 올리기 상한 50MB ≈ 1시간 40분)

  function applyRecSupport() {
    var ok = recSupported();
    $('rec-unsupported').hidden = ok;
    $('rec').disabled = !ok;
    $('file-btn').hidden = isolated(); // 격리된 출처에는 대기열(IndexedDB)이 없다
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
    // 통화용 처리(울림 제거·잡음 억제·자동 음량 조절)는 끈다 - 떨어져 앉은 사람 목소리를 깎고 말 없는 구간의
    // 소음을 키워 받아쓰기·화자 구분이 나빠진다. 음량은 받아쓰기 서버가 맞춘다. 모르는 브라우저는 이 값을 무시한다.
    var audio = { echoCancellation: false, noiseSuppression: false, autoGainControl: false };
    return navigator.mediaDevices.getUserMedia({ audio: audio }).then(function (stream) {
      var mime = pickMime();
      var mr;
      try {
        mr = mime ? new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: REC_BITRATE })
          : new MediaRecorder(stream, { audioBitsPerSecond: REC_BITRATE });
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
        // 초안 주인 판정은 웹 잠금이 한다. draftStart 가 잠금을 쥐고, 저장·정리가 끝날 때 queue 가 놓는다.
        rc.chain = Promise.resolve(dq.draftStart({ draftId: rc.draftId, mime: rc.mime, recordedAt: rc.startedIso, location: null }))
          .then(function (ok) { rc.draftOk = ok === true; }, function () { rc.draftOk = false; });
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
      try {
        mr.start(5000);
      } catch (e) {
        rc.finished = true;
        if (state.rc === rc) { state.rc = null; state.rec = null; }
        rc.stream.getTracks().forEach(function (t) { t.stop(); });
        rc.chain = rc.chain.then(function () {
          if (!rc.draftOk) return;
          rc.draftOk = false;
          return Promise.resolve(dq.draftDiscard(rc.draftId)).catch(function () {});
        });
        toast('녹음을 시작하지 못했습니다.');
        return;
      }
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

  // ---- 다른 앱으로 녹음한 파일 올리기 (폰 녹음 앱의 m4a 등) - 녹음과 같은 대기열로 간다 ----
  var FILE_MAX = 50 * 1024 * 1024; // 서버 상한(MAX_AUDIO_BYTES)과 같게
  var FILE_MIME = { webm: 'audio/webm', ogg: 'audio/ogg', m4a: 'audio/mp4', mp3: 'audio/mpeg', wav: 'audio/wav' };

  function audioDuration(a) { // 초 - 못 읽으면 null
    return new Promise(function (resolve) {
      var done = false, timer;
      function finish(v) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        a.onloadedmetadata = null;
        a.ondurationchange = null;
        a.onerror = null;
        resolve(v);
      }
      function settle() {
        if (isFinite(a.duration) && a.duration > 0) { finish(a.duration); return; }
        try { a.currentTime = 1e7; } catch (e) { finish(null); }
      }
      a.onloadedmetadata = settle;
      a.ondurationchange = function () {
        if (isFinite(a.duration) && a.duration > 0) {
          try { a.currentTime = 0; } catch (e) { /* 무시 */ }
          finish(a.duration);
        }
      };
      a.onerror = function () { finish(null); };
      timer = setTimeout(function () { finish(null); }, 5000);
      if (a.readyState >= 1) settle();
    });
  }

  function fileDuration(file) { // 길이(ms) - 못 읽으면 null
    return new Promise(function (resolve) {
      var url, a, done = false;
      function end(v) {
        if (done) return;
        done = true;
        try { URL.revokeObjectURL(url); } catch (e) { /* 무시 */ }
        resolve(v);
      }
      try {
        url = URL.createObjectURL(file);
        a = new Audio();
        a.preload = 'metadata';
        audioDuration(a).then(function (sec) {
          end(sec == null ? null : Math.round(sec * 1000));
        });
        a.src = url;
      } catch (e) { end(null); }
    });
  }

  function uploadFile(file) {
    var q = queueApi();
    if (!file || !q) return Promise.resolve();
    var ext = (/\.([A-Za-z0-9]+)$/.exec(file.name || '') || [])[1];
    var mime = FILE_MIME[(ext || '').toLowerCase()];
    if (!mime) { toast('올릴 수 있는 파일은 m4a · mp3 · wav · ogg · webm 입니다.'); return Promise.resolve(); }
    if (!file.size) { toast('빈 파일입니다.'); return Promise.resolve(); }
    if (file.size > FILE_MAX) { toast('파일이 너무 큽니다 (최대 50MB).'); return Promise.resolve(); }
    $('rec-result').textContent = '파일 저장 중…';
    return fileDuration(file).then(function (durationMs) {
      // 기록 시각 = 올린 때(파일에 적힌 날짜가 아니라 작업한 날) - 기록 목록에 방금 한 일로 맨 위에 보인다
      return q.enqueue({ blob: file, mime: mime, recordedAt: localIso(new Date()), durationMs: durationMs });
    }).then(function () {
      $('rec-result').textContent = '파일 ' + (file.name || '') + ' · 저장됨, 서버로 올리는 중입니다.';
      updateQueue();
    }, function (e) {
      $('rec-result').textContent = '파일을 저장하지 못했습니다.';
      toast((e && e.message) || '파일을 저장하지 못했습니다.');
    });
  }

  function discardDraftQuiet(q, draftId) {
    try { return Promise.resolve(q.draftDiscard(draftId)).catch(function () {}); } catch (e) { return Promise.resolve(); }
  }

  function enqueueAndDiscard(q, item, draftId) {
    return Promise.resolve(q.enqueue(item)).then(function () { return discardDraftQuiet(q, draftId); });
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
        // 초안이 없으면(다른 탭이 가져갔거나 지워졌으면) 메모리의 조각으로 올린다 - 녹음을 버리지 않는다
        return Promise.resolve(q.draftFinish(draftId, durationMs, rc.loc)).then(function (done) {
          if (done === false) return enqueueAndDiscard(q, item, draftId);
        }, function () { return enqueueAndDiscard(q, item, draftId); });
      }
      return enqueueAndDiscard(q, item, draftId);
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
    if (state.tagFilter) p.set('tag', state.tagFilter);
    if (limit) p.set('limit', String(limit));
    return p;
  }

  function tagKey(t) { return String(t || '').toLowerCase(); }
  function autoKeysOf(tags) {
    var keys = new Set();
    (Array.isArray(tags) ? tags : []).forEach(function (t) { keys.add(tagKey(t)); });
    return keys;
  }
  function makeTagChip(tag, auto, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'tag-chip' + (auto ? ' tag-auto' : '');
    b.textContent = tag;
    if (auto) {
      b.title = 'AI 가 단 태그';
      b.setAttribute('aria-label', tag + ' (AI 가 단 태그)');
    }
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      onClick();
    });
    return b;
  }

  function applyTagFilter(tag) {
    state.tagFilter = tag || '';
    $('tag-filter-row').hidden = !state.tagFilter;
    $('tag-filter-label').textContent = state.tagFilter ? '태그: ' + state.tagFilter : '';
    if (state.tagFilter) loadList();
  }

  function clearTagFilter() {
    state.tagFilter = '';
    $('tag-filter-row').hidden = true;
    $('tag-filter-label').textContent = '';
    loadList();
  }

  function renderDetailChips(tags, tagsAuto) {
    var box = $('detail-chips');
    clear(box);
    var auto = autoKeysOf(tagsAuto);
    (Array.isArray(tags) ? tags : []).forEach(function (tag) {
      box.appendChild(makeTagChip(tag, auto.has(tagKey(tag)), function () { applyTagFilter(tag); }));
    });
  }

  function renderDetailTagState(autotag) {
    var st = $('detail-tag-state');
    if (autotag === 'pending') st.textContent = 'AI 가 태그를 다는 중…';
    else if (autotag === 'failed') st.textContent = '자동 태그를 달지 못했습니다';
    else st.textContent = '';
  }

  function updateDetailRetag() {
    $('detail-retag').hidden = isolated() || !state.llm || !String(state.detailText || '').trim();
  }

  function fillDetailInputs(label, tagsText, force) {
    var labelInput = $('detail-label');
    var tagsInput = $('detail-tags');
    if (force || (document.activeElement !== labelInput && labelInput.value === state.detailLastLabel)) {
      labelInput.value = label;
      state.detailLastLabel = label;
    }
    if (force || (document.activeElement !== tagsInput && tagsInput.value === state.detailLastTags)) {
      tagsInput.value = tagsText;
      state.detailLastTags = tagsText;
    }
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
      var t = it.label || it.title || it.snippet || '';
      text.textContent = t || (it.status === 'done' ? '(빈 글)' : '(아직 글이 없습니다)');
      main.appendChild(head); main.appendChild(text);

      var tags = Array.isArray(it.tags) ? it.tags : [];
      if (tags.length) {
        var tagRow = document.createElement('div');
        tagRow.className = 'rec-tags';
        var auto = autoKeysOf(it.tags_auto);
        tags.slice(0, 2).forEach(function (tag) {
          tagRow.appendChild(makeTagChip(tag, auto.has(tagKey(tag)), function () { applyTagFilter(tag); }));
        });
        if (tags.length > 2) {
          var more = document.createElement('button');
          more.type = 'button';
          more.className = 'tag-chip tag-more';
          more.textContent = '+' + (tags.length - 2);
          more.title = '나머지 태그 보기';
          more.addEventListener('click', function (ev) {
            ev.stopPropagation();
            openDetail(it.id);
          });
          tagRow.appendChild(more);
        }
        main.appendChild(tagRow);
      }
      if (it.match === 'label' || it.match === 'tag') {
        var match = document.createElement('div');
        match.className = 'rec-match';
        match.textContent = it.match === 'label' ? '이름에서 맞음' : '태그에서 맞음';
        main.appendChild(match);
      }

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
    var wasBusy = state.lastItems.some(function (i) { return i.status === 'pending' || i.status === 'transcribing'; }) ||
      (state.detailId && (state.detailStatus === 'pending' || state.detailStatus === 'transcribing'));
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
        loadDetail(state.detailId);
        busy = true;
      }
      if (busy) state.listTimer = setTimeout(loadList, 5000);
    }, function (e) {
      if (seq !== state.listSeq) return;
      onApiError(e);
      if (wasBusy && !(e && e.status === 401)) state.listTimer = setTimeout(loadList, 5000);
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
      audio.preload = 'metadata';
      audio.src = url;
      audioDuration(audio);
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

  function loadDetail(id, forceFill) {
    return api().json('api/recordings/' + encodeURIComponent(id)).then(function (r) {
      if (state.detailId !== id) return;
      var prevStatus = state.detailStatus;
      var wasPending = state.detailAutotag === 'pending';
      state.detailStatus = r.status;
      var label = typeof r.label === 'string' ? r.label : '';
      var tags = Array.isArray(r.tags) ? r.tags : [];
      $('detail-title').textContent = label || r.title || '녹취';
      var meta = fmtTime(r.recorded_at || r.created) +
        (r.duration_ms != null ? ' · ' + fmtClock(r.duration_ms) : '') +
        ' · ' + (STATUS[r.status] || r.status) +
        (r.chars ? ' · ' + r.chars + '자' : '') +
        (r.error ? ' · ' + r.error : '');
      $('detail-meta').textContent = meta;
      renderLoc(r.location);
      state.detailSttOptions = hasSttOptions(r.stt_options) ? r.stt_options : null;
      $('detail-retry-opts').hidden = isolated();
      if (isolated()) $('detail-stt').hidden = true;
      renderSttUsed(r.stt_used);
      renderPrev(r.transcript_prev, r.prev_stt_used);
      $('detail-delete').hidden = isolated();
      state.detailText = r.transcript || '';
      state.detailHead = (label || r.title || '녹취') + ' · ' + fmtTime(r.recorded_at || r.created);
      $('detail-export').hidden = !state.detailText;
      $('detail-share').hidden = !canShare();
      renderDetailChips(tags, r.tags_auto);
      $('detail-edit').hidden = isolated();
      fillDetailInputs(label, tags.join(', '), forceFill);
      renderDetailTagState(r.autotag);
      updateDetailRetag();
      var tr = $('transcript');
      if (r.transcript) tr.textContent = r.transcript;
      else if (r.status === 'pending' || r.status === 'transcribing') tr.textContent = '받아쓰는 중입니다…';
      else if (r.status === 'no-stt') tr.textContent = '음성인식 백엔드가 없어 글이 없습니다. 서버에 켠 뒤 \'다시 받아쓰기\'를 누르세요.';
      else tr.textContent = '(글이 없습니다)';

      state.detailAutotag = r.autotag || null;
      clearTimeout(state.detailTimer);
      if (r.autotag === 'pending') {
        state.detailTimer = setTimeout(function () {
          if (state.detailId === id) loadDetail(id);
        }, 2000);
      } else if (wasPending) {
        loadList();
      }
      if (r.autotag == null && r.status === 'done' &&
          (prevStatus === 'pending' || prevStatus === 'transcribing') && state.llm) {
        state.detailTimer = setTimeout(function () {
          if (state.detailId === id) loadDetail(id);
        }, 2000);
      }
    }, function (e) {
      if (state.detailId === id) onApiError(e);
      if (state.detailId === id && state.detailAutotag === 'pending') {
        clearTimeout(state.detailTimer);
        state.detailTimer = setTimeout(function () {
          if (state.detailId === id) loadDetail(id);
        }, 5000);
      }
    });
  }

  function openDetail(id) {
    state.detailId = id;
    state.detailStatus = null;
    state.detailAutotag = null;
    state.detailLastLabel = '';
    state.detailLastTags = '';
    clearTimeout(state.detailTimer);
    $('detail').hidden = false;
    $('detail-delete').hidden = isolated();
    $('detail-title').textContent = '녹취';
    $('detail-meta').textContent = '불러오는 중…';
    $('transcript').textContent = '';
    state.detailText = '';
    clear($('detail-chips'));
    $('detail-label').value = '';
    $('detail-tags').value = '';
    $('detail-edit').hidden = isolated();
    renderDetailTagState(null);
    updateDetailRetag();
    $('detail-export').hidden = true;
    state.detailSttOptions = null;
    state.detailPrevText = null;
    $('detail-stt').hidden = true;
    $('detail-retry-opts').setAttribute('aria-expanded', 'false');
    $('detail-retry-opts').hidden = isolated();
    $('detail-stt-state').textContent = '';
    $('detail-stt-used').hidden = true;
    $('detail-stt-used').textContent = '';
    $('detail-prev').hidden = true;
    $('detail-prev-text').textContent = '';
    fillSttFields(state.sttFields.detail, {});
    Array.prototype.forEach.call($('list').children, function (li) {
      li.classList.toggle('open', li.dataset.id === id);
    });
    setAudio(id);
    loadDetail(id, true).then(function () {
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
    state.detailAutotag = null;
    clearTimeout(state.detailTimer);
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

  function saveLabels(id) {
    if (!id) return;
    var label = $('detail-label').value;
    var tagsText = $('detail-tags').value;
    var labelChanged = label !== state.detailLastLabel;
    var tagsChanged = tagsText !== state.detailLastTags;
    if (!labelChanged && !tagsChanged) {
      toast('바뀐 것이 없습니다');
      return;
    }
    var body = { label: label };
    if (tagsChanged) body.tags = tagsText.split(',');
    api().json('api/recordings/' + encodeURIComponent(id), { method: 'PATCH', body: body }).then(function () {
      toast('저장했습니다.');
      loadDetail(id, true);
      loadList();
    }, function (e) {
      if (e && e.status === 401) setConn('bad', '인증 필요');
      toast((e && e.message) || '저장하지 못했습니다');
    });
  }

  function retagDetail() {
    var id = state.detailId;
    if (!id) return;
    api().json('api/recordings/' + encodeURIComponent(id) + '/autotag', { method: 'POST' }).then(function () {
      loadDetail(id);
    }, function (e) {
      toast((e && e.message) || '태그 다시 달기를 요청하지 못했습니다');
    });
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

  // 지난 답 목록의 제목: 답의 첫 글줄에서 마크다운 표시(#·-·*·>·번호·굵게)를 뗀 것
  function answerTitle(text) {
    var lines = String(text || '').split('\n');
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].replace(/^[\s#>*\-+]+|^\s*\d+[.)]\s+/, '').replace(/[*_`]/g, '').replace(/\|/g, ' ').trim();
      if (t && !/^[-:\s]+$/.test(t)) return t.slice(0, 80);
    }
    return '';
  }

  // 지난 답 목록의 제목: 질문 + 어떤 녹취에 대한 답인지(첫 녹취의 때·첫마디, 여러 건이면 '외 N건')
  function answerLabel(a) {
    var n = (a.ids || []).length;
    var parts = [];
    if (a.prompt) parts.push(a.prompt);
    if (a.about) {
      var said = String(a.about.title || '').replace(/화자 \d+:\s*/g, '').trim();
      parts.push(fmtTime(a.about.recorded_at) + ' 녹취' + (n > 1 ? ' 외 ' + (n - 1) + '건' : '') + (said ? ' “' + said + '”' : ''));
    } else {
      var first = answerTitle(a.answer); // 녹취가 지워졌으면 답의 첫 글줄
      if (first) parts.push(first);
      parts.push('녹취 ' + n + '건');
    }
    return parts.join(' · ');
  }

  function copyText(text) {
    if (!text) return;
    function fallback() { // 클립보드 API 가 없거나 막힌 곳 - 보이지 않는 글상자를 골라 복사
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      toast(ok ? '복사했습니다.' : '복사하지 못했습니다.');
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { toast('복사했습니다.'); }, fallback);
        return;
      }
    } catch (e) { /* 아래로 */ }
    fallback();
  }

  function shareText(title, text) {
    if (!text) return;
    try {
      Promise.resolve(navigator.share({ title: title, text: text })).catch(function (e) {
        if (e && e.name === 'AbortError') return; // 사용자가 닫음
        toast('공유하지 못했습니다.');
      });
    } catch (e) { toast('공유하지 못했습니다.'); }
  }

  function canShare() { // 기기의 공유 창이 있는가 (없으면 '공유' 단추를 숨긴다)
    try { return typeof navigator.share === 'function'; } catch (e) { return false; }
  }

  function copyAnswer() { copyText(state.shownText); }
  function shareAnswer() { shareText('VoxLog ' + state.shownHead, state.shownText); }
  // 녹취 상세: 받아쓴 글 그대로 내보낸다 (받아쓰는 중·글 없음 안내는 내보내지 않는다)
  function copyDetail() { copyText(state.detailText); }
  function shareDetail() { shareText('VoxLog ' + state.detailHead, state.detailText); }

  function deleteAnswer(aid) {
    if (!window.confirm('이 답을 지울까요? 되돌릴 수 없습니다. (녹취는 그대로 남습니다)')) return;
    api().json('api/answers/' + encodeURIComponent(aid), { method: 'DELETE' }).then(function () {
      if (state.shownAnswer === aid) { // 화면에 펼쳐 둔 답이면 같이 치운다
        state.askToken++;
        state.shownAnswer = null;
        state.shownText = '';
        $('answer-actions').hidden = true;
        $('answer-status').textContent = '';
        $('answer').classList.remove('md');
        $('answer').textContent = '';
      }
      toast('지웠습니다.');
      loadAnswers();
    }, function (e) { onApiError(e); loadAnswers(); });
  }

  function showAnswer(a) {
    var st = $('answer-status');
    var box = $('answer');
    state.shownAnswer = a.id || null;
    // 복사·공유는 다 된 답에만 - 내보내는 글은 답의 마크다운 원문
    state.shownText = a.status === 'done' && a.answer ? a.answer : '';
    state.shownHead = (KIND[a.kind] || a.kind || '답') + ' · ' + fmtTime(a.created);
    $('answer-actions').hidden = !state.shownText;
    $('answer-share').hidden = !canShare();
    if (a.status === 'done') {
      st.textContent = (KIND[a.kind] || a.kind) + ' · ' + fmtTime(a.created) + ' · 녹취 ' + (a.ids || []).length + '건';
      // 답은 마크다운으로 그린다 (md.js - DOM 으로만 만들어 답에 든 HTML 은 글자로 보인다)
      box.classList.add('md');
      box.textContent = '';
      if (a.answer && window.VoxMd) box.appendChild(window.VoxMd.render(a.answer));
      else box.textContent = a.answer || '(빈 답)';
    } else if (a.status === 'failed') {
      st.textContent = '실패';
      box.classList.remove('md');
      box.textContent = a.error || '답을 만들지 못했습니다.';
    } else {
      st.textContent = '묻는 중… (보통 수십 초 걸립니다)';
      box.classList.remove('md');
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
        sub.textContent = answerLabel(a);
        var top = document.createElement('span'); // 기록 목록과 같은 머리줄 - 때와 상태 칩을 세로 가운데로 맞춘다
        top.className = 'rec-head';
        top.appendChild(head); top.appendChild(badge);
        b.appendChild(top); b.appendChild(sub);
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
        if (!isolated() && a.status !== 'running') { // 격리된 출처(모니터)는 DELETE 를 이어 주지 않는다
          var del = document.createElement('button');
          del.type = 'button';
          del.className = 'danger small answer-del';
          del.textContent = '지우기';
          del.setAttribute('aria-label', '이 답 지우기');
          del.addEventListener('click', function () { deleteAnswer(a.id); });
          li.appendChild(del);
        }
        ul.appendChild(li);
      });
    }, function (e) { onApiErrorQuiet(e); });
  }

  /* ---------- 시작 ---------- */

  function bind() {
    state.sttFields = {
      defaults: buildSttFields($('stt-defaults-fields'), 'stt-defaults'),
      detail: buildSttFields($('detail-stt-fields'), 'detail-stt')
    };
    $('answer-copy').addEventListener('click', copyAnswer);
    $('answer-share').addEventListener('click', shareAnswer);
    $('detail-copy').addEventListener('click', copyDetail);
    $('detail-share').addEventListener('click', shareDetail);
    $('file-btn').addEventListener('click', function () { $('file-input').click(); });
    $('file-input').addEventListener('change', function () {
      var f = this.files && this.files[0];
      this.value = ''; // 같은 파일을 다시 골라도 change 가 나게
      uploadFile(f);
    });
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) {
      b.addEventListener('click', function () { showTab(b.dataset.tab); });
    });
    $('settings-btn').addEventListener('click', function () {
      var s = $('settings');
      s.hidden = !s.hidden;
      $('settings-btn').setAttribute('aria-expanded', s.hidden ? 'false' : 'true');
      if (!s.hidden) loadSttSettings();
    });
    $('stt-defaults-save').addEventListener('click', saveSttDefaults);
    $('detail-retry-opts').addEventListener('click', openSttPanel);
    $('detail-stt-run').addEventListener('click', retryWithOptions);
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
    $('tag-filter-clear').addEventListener('click', clearTagFilter);
    $('sel-clear').addEventListener('click', function () {
      state.selected.clear();
      Array.prototype.forEach.call(document.querySelectorAll('.rec-check'), function (c) { c.checked = false; });
      updateSelCount();
    });
    $('detail-close').addEventListener('click', closeDetail);
    $('detail-retry').addEventListener('click', retryDetail);
    $('detail-delete').addEventListener('click', deleteDetail);
    $('detail-save').addEventListener('click', function () { saveLabels(state.detailId); });
    $('detail-retag').addEventListener('click', retagDetail);

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
    var oq = queueApi();
    try {
      if (oq && typeof oq.onrecover === 'function') {
        oq.onrecover(function (n) {
          toast('끝나지 않은 녹음 ' + n + '건을 살렸습니다');
          updateQueue();
        });
      }
    } catch (e) { /* 무시 */ }
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
