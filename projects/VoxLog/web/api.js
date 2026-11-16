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

  function json(path, opts) {
    opts = opts || {};
    return getConfig().then(function (cfg) {
      var init = { method: opts.method || 'GET', headers: authHeaders(cfg), cache: 'no-store' };
      if (opts.body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(opts.body);
      }
      return fetch(buildUrl(path), init).then(function (res) {
        return res.text().then(function (text) {
          var data = {};
          try { data = text ? JSON.parse(text) : {}; } catch (e) { data = {}; }
          if (!res.ok) {
            throw fail((data && data.error) || String(res.status), res.status);
          }
          return data;
        });
      }, function () {
        throw fail('서버에 연결할 수 없습니다', 0);
      });
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
