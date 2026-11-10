// AIMEM 함대 모니터 - 서비스 워커 (2026-11-10, 폰 설치용 PWA).
// 원칙: **API 응답은 절대 캐시하지 않는다**(함대 상태·요청 본문은 인증 뒤 데이터). 캐시는 앱 껍데기(정적 파일)뿐이고,
// 그마저 네트워크가 되면 새 것을 받아 갈아 끼운다(stale-while-revalidate). 오프라인이면 껍데기만 뜨고 화면이 "연결 끊김" 을 보인다.
const VERSION = 'aimem-shell-v6';
const SHELL = ['/', '/index.html', '/app.js', '/style.css', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL).catch(() => null)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                       // 쓰기는 항상 네트워크
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/') || url.pathname === '/login') return;   // 데이터·인증은 캐시 금지
  if (req.mode === 'navigate') {                           // 화면 진입: 네트워크 우선, 끊기면 껍데기
    e.respondWith(fetch(req).catch(() => caches.match('/index.html').then((r) => r || caches.match('/'))));
    return;
  }
  e.respondWith(caches.match(req).then((cached) => {
    const net = fetch(req).then((res) => {
      if (res && res.ok && res.type === 'basic') caches.open(VERSION).then((c) => c.put(req, res.clone()));
      return res;
    }).catch(() => cached);
    return cached || net;
  }));
});
