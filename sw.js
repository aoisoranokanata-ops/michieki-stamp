// 道の駅スタンプ帳 Service Worker
// github.io は他のアプリと同じオリジンなので、キャッシュ名に接頭辞を付け、消すのも自分のものだけにする。
// VERSION は index.html の APP_VERSION と必ずそろえて上げる。
const VERSION = '0.6.3';
const PREFIX = 'michieki-stamp-';
const CACHE = PREFIX + VERSION;

// オフラインでも記録できるように最初に保存しておくもの（地図タイルは保存しない：一括取得はしない方針）
const PRECACHE = [
  './',
  './index.html',
  './manifest.json',
  './data/michinoeki.json',
  './data/stations.json',
  './vendor/leaflet/leaflet.js',
  './vendor/leaflet/leaflet.css',
  './vendor/leaflet/images/marker-icon.png',
  './vendor/leaflet/images/marker-icon-2x.png',
  './vendor/leaflet/images/marker-shadow.png',
  './vendor/leaflet/images/layers.png',
  './vendor/leaflet/images/layers-2x.png',
  './vendor/jszip/jszip.min.js',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png',
];

self.addEventListener('install', event => {
  // 待機させずにすぐ新しい版へ切り替える。iPhone（Safari・ホーム画面アプリ）では、待機中の版へ
  // メッセージを送っても切り替わらず、待機のまま残り続けることがあったため。
  // アプリ本体はネットワーク優先で読むので、開いている画面とずれても困らない
  self.skipWaiting();
  // GitHub Pages は max-age=600 を返すので、HTTP キャッシュを通さず取り直す（新しい版に古いファイルが混ざらないように）
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE.map(u => new Request(u, { cache: 'reload' })))));
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith(PREFIX) && k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

// 以前の版（待機方式）で待機したまま残った端末向け
self.addEventListener('message', event => {
  if (event.data === 'skipWaiting') self.skipWaiting();
});

// 自分のスコープ内の GET だけを扱う。地図タイル・国土地理院の検索など外部への通信には関わらない
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(new URL(self.registration.scope).pathname)) return;
  event.respondWith(networkFirst(req));
});

// 通信できればネットワークの最新を使ってキャッシュも更新し、できなければ保存済みを返す。
// （キャッシュ優先にすると、アプリの更新が端末に届かなくなるため）
// 電波が弱いときは6秒待って保存済みに切り替える（通信はそのまま続け、届いたらキャッシュを更新する）。
// 保存済みが無いときは、遅くても通信の完了を待つ。
async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  const key = stripQuery(req);
  const net = fetch(req).then(res => {
    if (res.ok && res.type === 'basic') cache.put(key, res.clone());
    return res;
  });
  net.catch(() => {});   // 保存済みで返した後に通信が失敗しても、未処理エラーにしない
  const cached = () => cache.match(key).then(hit => hit || (req.mode === 'navigate' ? cache.match('./index.html') : undefined));
  const slow = new Promise(resolve => setTimeout(resolve, 6000)).then(cached);
  try {
    const first = await Promise.race([net, slow]);
    return first || await net;
  } catch (e) {
    const hit = await cached();
    if (hit) return hit;
    throw e;
  }
}
// ?v=… などの検索文字列で別物扱いにならないよう、キャッシュのキーはパスだけにする
function stripQuery(req) {
  const u = new URL(req.url);
  u.search = '';
  return u.toString();
}
