import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const HREF = "https://monitor.example/app/x/";
const listeners = [];
let seq = 0;
let stubbed = false;

function stubGlobals() {
  if (stubbed) return;
  stubbed = true;
  globalThis.location = { href: HREF };
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() { throw new Error("SecurityError"); },
  });
  globalThis.addEventListener = (type, fn) => {
    if (type === "message") listeners.push(fn);
  };
  globalThis.removeEventListener = (type, fn) => {
    const i = listeners.indexOf(fn);
    if (i >= 0) listeners.splice(i, 1);
  };
}

function fakeParent() {
  const sent = [];
  const origins = [];
  const fp = {
    postMessage(m, origin) { sent.push(m); origins.push(origin); },
  };
  globalThis.parent = fp;
  return { sent, origins, fp };
}

function sendToParentForTests() {
  const source = readFileSync(new URL("../web/js/storage.js", import.meta.url), "utf8")
    .replace(/^export\s+/gm, "")
    .replace("let parentMode = false;", "let parentMode = true;");
  return new Function(`${source}\nreturn sendToParent;`)();
}

const reply = (data, source = globalThis.parent) => {
  for (const fn of [...listeners]) fn({ source, data, origin: "null" });
};

const tick = () => new Promise((r) => setTimeout(r, 0));

async function fresh() {
  seq += 1;
  return import(`../web/js/storage.js?v=${seq}`);
}

async function opened() {
  stubGlobals();
  const { sent, origins, fp } = fakeParent();
  const S = await fresh();
  const p = S.init();
  await tick();
  reply({ aimem: "store.v1", op: "snapshot", items: {} });
  await p;
  return { S, sent, origins, fp };
}

test("ready 를 보낸다: {aimem:'store.v1',op:'ready'} 와 부모 오리진", async () => {
  stubGlobals();
  const { sent, origins } = fakeParent();
  const S = await fresh();
  const p = S.init();
  await tick();
  assert.equal(sent[0].aimem, "store.v1");
  assert.equal(sent[0].op, "ready");
  assert.equal(origins[0], "https://monitor.example");
  reply({ aimem: "store.v1", op: "snapshot", items: {} });
  await p;
});

test("스냅숏이 읽기에 반영된다", async () => {
  stubGlobals();
  const { sent } = fakeParent();
  const S = await fresh();
  const p = S.init();
  await tick();
  reply({ aimem: "store.v1", op: "snapshot", items: { settings: '{"hardMode":true}' } });
  await p;
  assert.equal(sent[0].op, "ready");
  assert.equal(S.loadSettings().hardMode, true);
});

test("쓰기가 put 으로 나간다", async () => {
  const { S, sent } = await opened();
  S.saveSettings({ hardMode: false, dark: true, colorblind: false });
  const last = sent.at(-1);
  assert.equal(last.aimem, "store.v1");
  assert.equal(last.op, "put");
  assert.equal(last.key, "settings");
  assert.equal(typeof last.value, "string");
  assert.equal(JSON.parse(last.value).dark, true);
});

test("지우기는 value 가 null 이다", async () => {
  const { S, sent } = await opened();
  S.clearDaily("2026-11-11");
  assert.deepEqual(sent.at(-1), { aimem: "store.v1", op: "put", key: "daily.2026-11-11", value: null });
});

test("딴 데서 온 메시지는 무시한다", async () => {
  stubGlobals();
  const { sent } = fakeParent();
  const S = await fresh();
  S.saveSettings({ hardMode: false, dark: false, colorblind: false }); // 메모리에 미리 심어 둔다
  const p = S.init();
  await tick();
  assert.equal(sent[0].op, "ready");
  reply({ aimem: "store.v1", op: "snapshot", items: { settings: '{"hardMode":true}' } }, {});
  await tick();
  assert.equal(S.loadSettings().hardMode, false, "딴 출처 스냅숏은 반영되지 않는다");
  reply({ aimem: "store.v1", op: "snapshot", items: { settings: '{"hardMode":true}' } });
  await p;
  assert.equal(S.loadSettings().hardMode, true);
});

test("스냅숏이 안 오면 500ms 안에 포기한다", async () => {
  stubGlobals();
  fakeParent();
  const S = await fresh();
  const t0 = Date.now();
  await S.init();
  const elapsed = Date.now() - t0;
  assert.ok(elapsed < 1500, `포기가 너무 늦다: ${elapsed}ms`);
  assert.equal(typeof S.loadSettings().hardMode, "boolean");
  S.saveDaily("2026-11-11", { guesses: ["crane"] });
  assert.deepEqual(S.loadDaily("2026-11-11"), { guesses: ["crane"] });
});

function todayLocal() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

test("init 은 지난 daily 기록을 daily. 접두까지 붙여 지운다", async () => {
  stubGlobals();
  const { sent } = fakeParent();
  const S = await fresh();
  const today = todayLocal();
  const p = S.init();
  await tick();
  reply({ aimem: "store.v1", op: "snapshot", items: {
    "daily.2020-01-02": '{"g":[]}',
    ["daily." + today]: '{"g":["crane"]}',
    settings: '{"hardMode":false}',
  } });
  await p;
  assert.ok(sent.some((m) => m.op === "put" && m.key === "daily.2020-01-02" && m.value === null));
  assert.ok(!sent.some((m) => m.op === "put" && m.key === "2020-01-02"), "접두 없는 키로 지움을 보냈다");
  assert.deepEqual(S.loadDaily(today), { g: ["crane"] });
});

test("스냅숏이 안 오면 put 을 하나도 안 보낸다", async () => {
  stubGlobals();
  const { sent } = fakeParent();
  const S = await fresh();
  await S.init();
  S.recordResult(true, 3, todayLocal());
  S.saveSettings({ hardMode: true, dark: false, colorblind: false });
  assert.deepEqual(sent, [{ aimem: "store.v1", op: "ready" }]);
  assert.equal(S.loadStats().played, 1);
});

test("거절되는 키는 부모에게 아무것도 보내지 않는다", () => {
  stubGlobals();
  const { sent } = fakeParent();
  const send = sendToParentForTests();
  for (const key of ["../other", ".hidden", "x".repeat(65), ""]) {
    send("put", key, "v");
  }
  assert.deepEqual(sent, []);
});

test("경계 키는 부모에게 그대로 보낸다", () => {
  stubGlobals();
  const { sent } = fakeParent();
  const send = sendToParentForTests();
  const keys = ["a", "A0._-", "k".repeat(64)];
  for (const key of keys) send("put", key, "v");
  assert.deepEqual(sent.map((m) => m.key), keys);
});

test("8,192자 값은 가고 8,193자는 가지 않는다", () => {
  stubGlobals();
  const { sent } = fakeParent();
  const send = sendToParentForTests();
  send("put", "a", "x".repeat(8192));
  assert.equal(sent.length, 1);
  send("put", "a", "x".repeat(8193));
  assert.equal(sent.length, 1);
});

test("null 값 지우기는 길이 검사에 걸리지 않고 그대로 간다", () => {
  stubGlobals();
  const { sent } = fakeParent();
  const send = sendToParentForTests();
  send("put", "a", null);
  assert.deepEqual(sent, [{ aimem: "store.v1", op: "put", key: "a", value: null }]);
});
