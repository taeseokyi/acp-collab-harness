const ACTION_LABELS = {
  check: "확인 중…",
  preview: "미리 보기를 만드는 중…",
  send: "보내는 중…",
};

let busy = null;
let lastState = null;

function $(id) {
  return document.getElementById(id);
}

function fmtAt(value) {
  if (!value) return "";
  return String(value).replace("T", " ").slice(0, 16);
}

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setMsg(text, kind) {
  const msg = $("msg");
  if (!text) {
    msg.hidden = true;
    msg.textContent = "";
    msg.className = "msg";
    return;
  }
  msg.hidden = false;
  msg.textContent = text;
  msg.className = "msg " + kind;
}

function showLog(tail) {
  const box = $("detail-box");
  box.textContent = "";
  if (!Array.isArray(tail) || tail.length === 0) return;
  const details = document.createElement("details");
  details.appendChild(make("summary", "", "전송 로그 끝"));
  details.appendChild(make("pre", "", tail.join("\n")));
  box.appendChild(details);
}

function updateButtons() {
  const buttons = {
    check: $("btn-check"),
    preview: $("btn-preview"),
    send: $("btn-send"),
  };
  for (const [action, button] of Object.entries(buttons)) {
    button.disabled = busy !== null;
    button.textContent = busy === action ? ACTION_LABELS[action] : {
      check: "지금 확인",
      preview: "미리 보기",
      send: "카톡 보내기",
    }[action];
  }
}

function renderLatest(state) {
  const body = $("latest-body");
  const at = $("latest-at");
  body.textContent = "";
  body.className = "body muted";
  at.hidden = true;
  at.textContent = "";

  const check = state.last_check;
  if (!check) {
    body.textContent = "아직 확인하지 않았습니다.";
    return;
  }
  if (!check.ok || !check.latest) {
    body.textContent = "확인 실패: " + (check.error || "까닭 없음");
    at.hidden = false;
    at.textContent = "확인 시각: " + fmtAt(check.at);
    return;
  }
  body.className = "body";
  body.appendChild(make("div", "date", check.latest.date));
  body.appendChild(make("div", "title", check.latest.title || "(제목 없음)"));
  at.hidden = false;
  at.textContent = "확인 시각: " + fmtAt(check.at);
}

function renderSent(state) {
  const body = $("sent-body");
  const at = $("sent-at");
  body.textContent = "";
  body.className = "body muted";
  at.hidden = true;
  at.textContent = "";

  const sent = state.sent;
  if (!sent) {
    body.textContent = "보낸 주보가 없습니다.";
    return;
  }
  body.className = "body";
  body.appendChild(make("div", "date", sent.date || "(날짜 없음)"));
  body.appendChild(make("div", "title", sent.title || "(제목 없음)"));
  at.hidden = false;
  const source = sent.source === "openclaw" ? "오픈클로 기록" : "앱에서 보냄";
  at.textContent = "보낸 시각: " + fmtAt(sent.at) + " · " + source;
}

function renderBadge(state) {
  const badge = $("new-badge");
  if (state.is_new === true) {
    badge.className = "badge new";
    badge.textContent = "새 주보 있음";
  } else if (state.is_new === false) {
    badge.className = "badge none";
    badge.textContent = "새 주보 없음";
  } else {
    badge.className = "badge unknown";
    badge.textContent = "아직 확인 못 함";
  }
}

function renderHistory(state) {
  const tbody = $("history-body");
  tbody.textContent = "";
  const rows = Array.isArray(state.history) ? state.history : [];
  $("history-empty").hidden = rows.length > 0;
  $("history-table").closest(".table-wrap").hidden = rows.length === 0;

  for (const entry of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(make("td", "", fmtAt(entry.at) || "—"));

    const bulletinCell = make("td");
    bulletinCell.appendChild(make("div", "", entry.date || "—"));
    if (entry.title) bulletinCell.appendChild(make("div", "", entry.title));
    tr.appendChild(bulletinCell);

    tr.appendChild(make("td", entry.ok ? "ok-text" : "fail-text", entry.ok ? "성공" : "실패"));
    tr.appendChild(make("td", "", entry.reason || "—"));
    tbody.appendChild(tr);
  }
}

function fmtClock(value) {
  if (!value) return "";
  const text = String(value);
  const match = text.match(/T(\d\d:\d\d)/);
  return match ? match[1] : text.slice(11, 16);
}

function renderPreview(state) {
  const headline = $("preview-headline");
  const status = $("preview-status");
  const row = $("preview-bubble-row");
  const thumbs = $("preview-thumbs");
  const side = $("preview-side");

  thumbs.textContent = "";
  side.textContent = "";
  row.hidden = true;
  status.textContent = "";
  status.className = "chat-status muted";

  const preview = state.preview;
  if (!preview) {
    headline.textContent = "보낼 그림 미리 보기";
    status.textContent = "미리 보기를 눌러 주세요.";
    return;
  }

  const images = Array.isArray(preview.images) ? preview.images.slice() : [];
  const count = images.length;
  headline.textContent = "보낼 그림 미리 보기 - 실제 전송과 같은 " + count + "장";

  if (!preview.ok) {
    status.className = "chat-status error";
    status.textContent = "미리 보기 실패: " + (preview.error || "까닭 없음");
  } else {
    status.textContent = "미리 보기 시각: " + fmtAt(preview.at);
  }

  if (count === 0) {
    if (preview.ok) status.textContent = "미리 보기 그림이 없습니다.";
    return;
  }

  images.sort((a, b) => (Number(a.seq) || 0) - (Number(b.seq) || 0));

  const meta = new Map();
  for (const bulletin of Array.isArray(preview.bulletins) ? preview.bulletins : []) {
    meta.set(bulletin.site, bulletin);
  }

  thumbs.className = "bubble-thumbs cols-" + (count >= 5 ? 3 : count >= 2 ? 2 : 1);
  for (const image of images) {
    const bulletin = meta.get(image.site) || {};
    const name = bulletin.site_name || image.site || "주보";
    const link = document.createElement("a");
    link.href = "api/preview/" + encodeURIComponent(image.name);
    link.target = "_blank";
    link.rel = "noopener";
    const img = document.createElement("img");
    img.src = "api/preview/" + encodeURIComponent(image.name);
    img.alt = name + " 주보 " + image.seq + "번째 그림 (" + image.name + ")";
    img.loading = "lazy";
    let retries = 0;
    img.addEventListener("error", () => {
      if (retries >= 3) return;
      retries += 1;
      const src = "api/preview/" + encodeURIComponent(image.name) + "?r=" + retries;
      setTimeout(() => { img.src = src; }, 800 * retries);
    });
    link.appendChild(img);
    thumbs.appendChild(link);
  }

  side.textContent = fmtClock(preview.at) + " · " + count + "장";
  row.hidden = false;
}

function renderState(state) {
  lastState = state;
  busy = state.busy || null;
  updateButtons();
  renderLatest(state);
  renderSent(state);
  renderBadge(state);
  renderHistory(state);
  renderPreview(state);
}

async function request(path, method) {
  const response = await fetch(path, {
    method: method || "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  let data;
  try {
    data = await response.json();
  } catch (error) {
    throw new Error("서버 응답이 JSON 이 아닙니다");
  }
  if (!response.ok) {
    throw new Error(data.error || ("HTTP " + response.status));
  }
  return data;
}

async function loadState() {
  try {
    const state = await request("api/state");
    renderState(state);
    if (state.last_check && !state.last_check.ok) {
      setMsg("확인 실패: " + (state.last_check.error || "까닭 없음"), "error");
    }
  } catch (error) {
    setMsg("상태를 읽지 못했습니다: " + error.message, "error");
  }
}

async function runAction(action) {
  const prev = lastState || {};
  const before = {
    sendAt: ((prev.history || [])[0] || {}).at,
    checkAt: (prev.last_check || {}).at,
    previewAt: (prev.preview || {}).at,
  };
  busy = action;
  updateButtons();
  setMsg("", "");
  showLog([]);
  try {
    const data = await request("api/" + action, "POST");
    renderState(data.state);
    const result = data.result || {};

    if (action === "check") {
      if (result.ok && result.latest) {
        setMsg("확인했습니다: 최신 " + result.latest.date + " · " + (result.latest.title || "(제목 없음)"), "ok");
      } else {
        setMsg("확인 실패: " + (result.error || "까닭 없음"), "error");
      }
    } else if (action === "preview") {
      if (result.ok) {
        setMsg("미리 보기를 만들었습니다: " + (result.images || []).length + "장", "ok");
      } else {
        setMsg("미리 보기 실패: " + (result.error || "까닭 없음"), "error");
      }
    } else if (action === "send") {
      const entry = result.entry || {};
      if (result.ok) {
        setMsg("카톡으로 보냈습니다: " + (entry.date || "?") + " · " + (entry.title || "(제목 없음)"), "ok");
      } else {
        setMsg("전송 실패: " + (entry.reason || result.error || "까닭 없음"), "error");
        showLog(result.log_tail);
      }
    }
  } catch (error) {
    // 응답만 못 받았을 수 있다(화면을 잠깐 떠나면 브라우저가 기다리던 요청을 끊는다). 일은 서버에서 계속되므로
    // 서버 상태를 다시 읽어 실제 결과를 보인다.
    await settle(action, before, error);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function settle(action, before, error) {
  setMsg("응답을 받지 못해 결과를 다시 확인하는 중…", "");
  let state = null;
  for (let miss = 0; miss < 5;) {
    try {
      state = await request("api/state");
      renderState(state);
      if (!state.busy) break;
      miss = 0;
    } catch (again) {
      state = null;
      miss += 1;
    }
    await sleep(3000);
  }
  if (!state || state.busy) {
    busy = null;
    updateButtons();
    setMsg("요청을 끝내지 못했습니다: " + error.message + " - 결과는 새로 고쳐 확인하십시오", "error");
    return;
  }
  if (action === "send") {
    const entry = (state.history || [])[0];
    if (!entry || entry.at === before.sendAt) {
      setMsg("전송이 시작되지 않았습니다: " + error.message, "error");
    } else if (entry.ok) {
      setMsg("카톡으로 보냈습니다: " + (entry.date || "?") + " · " + (entry.title || "(제목 없음)"), "ok");
    } else {
      setMsg("전송 실패: " + (entry.reason || "까닭 없음"), "error");
    }
    return;
  }
  const done = action === "check" ? state.last_check : state.preview;
  if (!done || done.at === before[action + "At"]) {
    setMsg("요청을 끝내지 못했습니다: " + error.message, "error");
  } else if (done.ok) {
    setMsg(action === "check" ? "확인했습니다" : "미리 보기를 만들었습니다", "ok");
  } else {
    setMsg((action === "check" ? "확인 실패: " : "미리 보기 실패: ") + (done.error || "까닭 없음"), "error");
  }
}

$("btn-check").addEventListener("click", () => runAction("check"));
$("btn-preview").addEventListener("click", () => runAction("preview"));
$("btn-send").addEventListener("click", () => {
  if (!confirm("흑석동성당·서울대교구 주보를 카톡으로 보냅니다")) return;
  runAction("send");
});

loadState();
