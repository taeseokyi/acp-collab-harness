/* VoxLog - 서버 API 호출. 전역 VoxApi. 빌드 없는 바닐라 JS. */
(function () {
  'use strict';

  // VoxQueue 가 없거나(격리된 출처) throw 해도 설정은 메모리에 둔다.
  var mem = { token: '', autoRecord: false, saveLocation: true };

  function getConfig() {
    var p;
    try {
      p = Promise.resolve(window.VoxQueue.getConfig());
    } catch (e) {
      return Promise.resolve(Object.assign({}, mem));
    }
    return p.then(function (c) {
      c = c || {};
      mem = {
        token: typeof c.token === 'string' ? c.token : mem.token,
        autoRecord: typeof c.autoRecord === 'boolean' ? c.autoRecord : mem.autoRecord,
        saveLocation: typeof c.saveLocation === 'boolean' ? c.saveLocation : mem.saveLocation
      };
      return Object.assign({}, mem);
    }, function () {
      return Object.assign({}, mem);
    });
  }

  function setConfig(partial) {
    mem = Object.assign({}, mem, partial || {});
    var p;
    try {
      p = Promise.resolve(window.VoxQueue.setConfig(partial));
    } catch (e) {
      return Promise.resolve();
    }
    return p.then(function () {}, function () {});
  }

  // 늘 이 화면을 연 서버(같은 출처)로 - 예전에 저장된 apiBase 는 무시
  function buildUrl(path) {
    return new URL(path, location.href).href;
  }

  function authHeaders(cfg, headers) {
    headers = headers || {};
    if (cfg.token) headers['Authorization'] = 'Bearer ' + cfg.token;
    return headers;
  }

  function fail(message, status) {
    var e = new Error(message);
    e.status = status;
    return e;
  }

  function timeoutError() {
    var e = fail('응답이 없습니다', 0);
    e.timeout = true;
    return e;
  }

  // 어느 호출이든 성공했다고 화면에 알린다(R57-N5). 화면이 없으면(단위 검사) 그냥 넘어간다.
  function notifyOk() {
    try {
      if (typeof window.__voxApiOk === 'function') window.__voxApiOk();
    } catch (e) { /* 알림 실패는 요청 결과에 영향 없음 */ }
  }

  function json(path, opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs > 0 ? opts.timeoutMs : 0;
    // 시간 제한이 있으면 내부 컨트롤러로 fetch 를 끊는다. 없으면 지금과 똑같이 동작한다.
    var ac = null;
    if (timeoutMs) {
      try { ac = new AbortController(); } catch (e) { ac = null; }
    }
    var timedOut = false;
    // 바깥 신호에 단 리스너를 요청이 끝나면(성공·실패·시간 제한) 거둔다(R57-N6).
    var detachExternal = null;
    function detach() {
      if (!detachExternal) return;
      var d = detachExternal;
      detachExternal = null;
      try { d(); } catch (e) { /* 무시 */ }
    }
    var work = getConfig().then(function (cfg) {
      var init = { method: opts.method || 'GET', headers: authHeaders(cfg), cache: 'no-store' };
      if (ac) {
        init.signal = ac.signal;
        // 바깥 신호와 시간 제한을 함께 듣는다: 바깥이 끊기면 내부 컨트롤러도 끊는다.
        if (opts.signal) {
          if (opts.signal.aborted) {
            ac.abort();
          } else {
            var external = opts.signal;
            var onAbort = function () { ac.abort(); };
            external.addEventListener('abort', onAbort, { once: true });
            detachExternal = function () { external.removeEventListener('abort', onAbort); };
          }
        }
      } else if (opts.signal) {
        init.signal = opts.signal;
      }
      if (opts.body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(opts.body);
      }
      return fetch(buildUrl(path), init).then(function (res) {
        return res.text().then(function (text) {
          var data = null;
          var isJson = false;
          if (text) {
            try { data = JSON.parse(text); isJson = true; } catch (e) { data = null; }
          }
          if (!res.ok) {
            throw fail((isJson && data && data.error) || String(res.status), res.status);
          }
          if (res.status === 204) { notifyOk(); return {}; } // 204 는 본문이 원래 없다
          // 200 인데 JSON 이 아니거나 본문이 빈 응답(캐티브 포털·프록시)은 성공으로 받지 않는다
          if (!isJson) throw fail('서버 응답이 JSON 이 아닙니다 (' + res.status + ')', res.status);
          notifyOk();
          return data == null ? {} : data;
        });
      }, function () {
        if (timedOut) throw timeoutError();
        throw fail('서버에 연결할 수 없습니다', 0);
      });
    });
    var settled = work.then(function (v) { detach(); return v; },
                             function (e) { detach(); throw e; });
    if (!timeoutMs) return settled;
    // getConfig 대기부터 fetch 끝까지를 덮는다. 시간이 지나면 (내부 컨트롤러가 있으면) fetch 를 끊고 거절한다.
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        timedOut = true;
        if (ac) { try { ac.abort(); } catch (e) { /* 아래에서 거절한다 */ } }
        detach();
        reject(timeoutError());
      }, timeoutMs);
      settled.then(function (v) { clearTimeout(timer); resolve(v); },
                   function (e) { clearTimeout(timer); reject(e); });
    });
  }

  function audioUrl(id) {
    return getConfig().then(function (cfg) {
      var url = buildUrl('api/recordings/' + encodeURIComponent(id) + '/audio');
      return fetch(url, { headers: authHeaders(cfg) }).then(function (res) {
        if (!res.ok) throw fail('음성을 불러오지 못했습니다 (' + res.status + ')', res.status);
        return res.blob();
      }, function () {
        throw fail('서버에 연결할 수 없습니다', 0);
      }).then(function (blob) {
        return URL.createObjectURL(blob);
      });
    });
  }

  window.VoxApi = { json: json, audioUrl: audioUrl, getConfig: getConfig, setConfig: setConfig, url: buildUrl };
})();
