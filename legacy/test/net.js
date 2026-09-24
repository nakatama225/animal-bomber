/* LAN対戦（ホスト権威）の検証。ソケットも Python も使わない。

   同じ HTML を `new Function(code)()` で2回評価すると、クロージャの中の
   let が別々に作られるので、**1つの node プロセスの中に独立した2つの世界**ができる。
   片方をホスト、片方をゲストに見立てて、スナップショットを手渡しで往復させる。

   ⚠️ どちらのクロージャも global.__X に代入するので、
      各 new Function() の直後に必ず捕まえる。後でまとめて読むと両方2つ目になる。

   ここで守りたいのは主に3つ:
     1. 送ったものがゲスト側で同じ状態として組み上がる
     2. デコードのたびに draw() と renderCards() が例外を出さない
        （描画の例外は実ゲームでは画面が固まる形で出るので、状態比較では捕まらない）
     3. エンコーダが新しいフィールドを黙って落としていない
*/
const fs = require('fs');
const HTML = require('path').join(__dirname, '..', 'animal-bomber.html');
const src = fs.readFileSync(HTML, 'utf8');
const blocks = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (blocks.length !== 1) {
  console.error(`❌ <script> ブロックが ${blocks.length} 個ある。1個である前提で書かれている`);
  process.exit(1);
}

const EXPORTS = `
global.__X = {
  get G(){return G}, get players(){return players}, get bombs(){return bombs},
  get blasts(){return blasts}, get items(){return items}, get grid(){return grid},
  get negis(){return negis}, get foxfires(){return foxfires},
  get slimes(){return slimes}, get pits(){return pits},
  get particles(){return particles}, get poroporos(){return poroporos},
  get keys(){return keys}, get pressed(){return pressed},
  NET, NET_SKIP, inputOf, startGame, startRound, update, draw, renderCards,
  CFG, CONTROLS, ANIMALS, COLS, ROWS, getPower, humanUpdate, spawnBomb, placeBomb,
  hurt, toNegibon, fireNegi, castFoxfire, frogSlime, rabbitPoroporo,
  elephantCharge, startTongue, startDigPit, makeSnapshotTarget: () => null,
  showScreen, buildLobby, MENU, MENU_ORDER,
};`;

/** 世界をひとつ作る。DOM と時間は世界ごとに別に用意する */
function makeWorld(name) {
  const noop = () => {};
  const gradStub = { addColorStop: noop };
  const ctxStub = new Proxy({}, {
    get(_, k) {
      if (k === 'canvas') return { width: 0, height: 0 };
      if (k === 'measureText') return () => ({ width: 10 });
      if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => gradStub;
      return () => {};
    }, set() { return true; },
  });
  const makeEl = () => ({
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    style: {}, kids: [], appendChild(c) { this.kids.push(c); return c; },
    innerHTML: '', textContent: '', onclick: null,
    getContext: () => ctxStub, width: 0, height: 0, addEventListener: noop,
  });
  const cache = new Map();
  const clock = { t: 0 };

  global.window = { addEventListener: noop, innerWidth: 1280, innerHeight: 800 };
  global.document = {
    getElementById(id) { if (!cache.has(id)) cache.set(id, makeEl()); return cache.get(id); },
    createElement: makeEl, addEventListener: noop,
    querySelector: () => makeEl(), querySelectorAll: () => [],
  };
  global.performance = { now: () => clock.t };
  global.requestAnimationFrame = () => 0;
  global.cancelAnimationFrame = noop;
  global.setInterval = () => 0; global.clearInterval = noop;
  global.setTimeout = () => 0;  global.clearTimeout = noop;

  new Function(blocks[0] + EXPORTS)();
  const X = global.__X;          // ★ここで捕まえる。後回しにすると両方2つ目になる
  return { name, X, clock };
}

let pass = 0, fail = 0;
const results = [];
function t(name, fn) {
  try { const msg = fn(); pass++; results.push(['✅', name, msg || '']); }
  catch (e) { fail++; results.push(['❌', name, e.message]); }
}
function ok(c, what) { if (!c) throw new Error(what); }
function eq(a, b, what) { if (a !== b) throw new Error(`${what}: expected ${b}, got ${a}`); }

/** ホストとゲストの2つの世界を立てて、同じ設定で試合を始める。
    `clear: true` を渡すと、ホストのソフトブロックを消して動きやすくする
    （囲まれたままだと10秒程度では移動が観測できない）。 */
function pair(opts = {}) {
  const host = makeWorld('host');
  const guest = makeWorld('guest');
  for (const w of [host, guest]) {
    Object.assign(w.X.CFG, {
      mode: opts.mode || '1p', hpP1: 3, hpP2: 3, hpCPU: 3,
      time: opts.time ?? 180, wins: 5, sudden: true, sfx: false, bgm: false,
    });
    w.X.CFG.cpuLevel = ['oni', 'oni', 'oni'];
    w.X.CFG.pick.p1 = opts.p1 || 'rabbit';
    w.X.CFG.pick.p2 = opts.p2 || 'fox';
    w.clock.t = 0;
    w.X.startGame();
  }
  if (opts.clear) {
    const { grid, ROWS, COLS } = host.X;
    for (let y = 1; y < ROWS - 1; y++) for (let x = 1; x < COLS - 1; x++) {
      if (grid[y][x] === 2) grid[y][x] = 0;   // SOFT -> EMPTY
    }
  }
  host.X.NET.role = 'host';
  guest.X.NET.role = 'guest';
  return { host, guest };
}

/** ホストを1フレーム進めて、盤面をゲストへ渡す */
function tick(host, guest, dt = 1 / 60) {
  host.clock.t += dt * 1000;
  host.X.update(dt);
  const snap = JSON.parse(JSON.stringify(host.X.NET.encode()));  // 通信を経由した形にする
  guest.X.NET.apply(snap);
  return snap;
}

/* ============ 9. スナップショットの往復 ============ */
t('600フレーム往復してもホストとゲストの盤面が一致する', () => {
  const { host, guest } = pair();
  let maxBytes = 0, total = 0;
  for (let i = 0; i < 600; i++) {
    const snap = tick(host, guest);
    const size = JSON.stringify(snap).length;
    total += size; if (size > maxBytes) maxBytes = size;
  }
  eq(guest.X.grid.map(r => r.join('')).join(''),
     host.X.grid.map(r => r.join('')).join(''), '盤面');
  eq(guest.X.players.length, host.X.players.length, 'プレイヤー数');
  for (let i = 0; i < host.X.players.length; i++) {
    const h = host.X.players[i], g = guest.X.players[i];
    eq(g.state, h.state, `players[${i}].state`);
    eq(g.hp, h.hp, `players[${i}].hp`);
    eq(Math.round(h.cx * 100) / 100, g.cx, `players[${i}].cx`);
  }
  eq(guest.X.bombs.length, host.X.bombs.length, '爆弾の数');
  return `平均 ${Math.round(total / 600)}B / ピーク ${maxBytes}B / 60Hz で ${Math.round(total / 600 * 60 / 1024)}KB/s`;
});

/* ============ 10. animal は参照で繋ぎ直す ============ */
t('ゲストの p.animal は ANIMALS の実体を指す（コピーではない）', () => {
  const { host, guest } = pair();
  tick(host, guest);
  for (let i = 0; i < guest.X.players.length; i++) {
    const g = guest.X.players[i];
    eq(g.animal, guest.X.ANIMALS[g.animal.key], `players[${i}].animal が ANIMALS の実体でない`);
  }
  return 'ok';
});

t('ゲストの getPower がホストと同じ値を返す（powerBonus を正しく引けている）', () => {
  const { host, guest } = pair();
  host.X.players[0].powerUp = 3;
  tick(host, guest);
  eq(guest.X.getPower(guest.X.players[0]), host.X.getPower(host.X.players[0]), '火力');
  return 'ok';
});

/* ============ 11. デコードのたびに描画が通る（★これが本命） ============ */
t('毎フレーム draw() と renderCards() を呼んでも例外が出ない', () => {
  const { host, guest } = pair();
  for (let i = 0; i < 600; i++) {
    tick(host, guest);
    guest.X.draw();                        // 描画の例外は実ゲームでは画面停止になる
    if (i % 15 === 0) guest.X.renderCards();
  }
  return '600フレーム描画して例外なし';
});

t('とくぎが全部出ている状態でもゲスト側の描画が通る', () => {
  const { host, guest } = pair({ mode: 'vs', p1: 'fox', p2: 'frog' });
  const [a, b] = host.X.players;
  a.cx = 3.5; a.cy = 3.5; b.cx = 9.5; b.cy = 9.5;
  host.X.castFoxfire(a);
  host.X.frogSlime(b);
  host.X.rabbitPoroporo(a);
  host.X.startTongue(b);
  host.X.startDigPit(a);
  host.X.elephantCharge(b);
  let sawFox = false, sawSlime = false;
  for (let i = 0; i < 240; i++) {
    tick(host, guest);
    if (guest.X.foxfires.length) sawFox = true;
    if (guest.X.slimes.length) sawSlime = true;
    guest.X.draw();
    guest.X.renderCards();
  }
  ok(sawFox, '狐火がゲスト側に届いていない');
  ok(sawSlime, 'スライムがゲスト側に届いていない');
  return `狐火・スライムとも届いた`;
});

t('葱ボン中でもゲスト側の描画が通る', () => {
  const { host, guest } = pair({ mode: 'vs' });
  const [a] = host.X.players;
  host.X.toNegibon(a);
  for (let i = 0; i < 60; i++) {
    a.negiCool = 0; host.X.fireNegi(a);
    tick(host, guest); guest.X.draw(); guest.X.renderCards();
  }
  ok(guest.X.players[0].state === 'NEGIBON', 'ゲスト側で葱ボン状態になっていない');
  return `葱 ${guest.X.negis.length} 本が同期`;
});

/* ============ 12. 入力の端から端まで ============ */
t('ゲストのキー入力がホストのプレイヤーを動かす', () => {
  const { host, guest } = pair({ mode: 'vs', clear: true });
  const hp = host.X.players[1];             // 2P をゲストが操作する想定
  hp.cx = 11.5; hp.cy = 7.5;                // 固定ブロックは x,y とも偶数。奇数行なら横に進める
  const cx0 = hp.cx;
  for (let i = 0; i < 30; i++) {
    // ゲスト側でキーを押している状態を作り、その入力をホストへ渡す
    guest.X.keys.add('ArrowRight');
    const msg = guest.X.NET.buildInput(guest.X.CONTROLS.solo);
    host.X.NET.receiveInput(hp, msg);
    tick(host, guest);
  }
  ok(hp.cx > cx0 + 0.3, `右へ動いていない（${cx0} → ${hp.cx}）`);
  return `${cx0.toFixed(2)} → ${hp.cx.toFixed(2)}`;
});

t('ゲストが手を離せばホストのプレイヤーも止まる', () => {
  const { host, guest } = pair({ mode: 'vs', clear: true });
  const hp = host.X.players[1];
  hp.cx = 11.5; hp.cy = 7.5;
  for (let i = 0; i < 20; i++) {
    guest.X.keys.add('ArrowRight');
    host.X.NET.receiveInput(hp, guest.X.NET.buildInput(guest.X.CONTROLS.solo));
    tick(host, guest);
  }
  guest.X.keys.clear();                      // 手を離した
  for (let i = 0; i < 5; i++) {
    host.X.NET.receiveInput(hp, guest.X.NET.buildInput(guest.X.CONTROLS.solo));
    tick(host, guest);
  }
  const stopped = hp.cx;
  for (let i = 0; i < 20; i++) {
    host.X.NET.receiveInput(hp, guest.X.NET.buildInput(guest.X.CONTROLS.solo));
    tick(host, guest);
  }
  ok(Math.abs(hp.cx - stopped) < 0.05, `離しても動き続けている（${stopped} → ${hp.cx}）`);
  return '停止した';
});

t('ネット入力のエッジは1フレームに1回しか消費されない（バグ#10 のテスト）', () => {
  const { host } = pair({ mode: 'vs', clear: true });
  const p = host.X.players[1];
  p.cx = 5.5; p.cy = 5.5;
  host.X.NET.receiveInput(p, { up:false, down:false, left:false, right:false,
                               bomb:true, act:false });
  ok(p.net.eBomb, 'エッジが立っていない');
  // 3倍速相当で細かく回しても、爆弾は1個だけ
  for (let i = 0; i < 3; i++) { host.X.update(1 / 180); host.X.NET.clearEdges(); }
  eq(host.X.bombs.length, 1, '1回の押しで置かれた爆弾の数');
  return '爆弾1個';
});

/* ============ 13. 切断 → CPU 引き継ぎ ============ */
t('回線が切れた枠は CPU が引き継いで動き続ける', () => {
  const { host, guest } = pair({ mode: 'vs', clear: true });
  const p = host.X.players[1];
  host.X.NET.receiveInput(p, { up:false,down:false,left:false,right:false,bomb:false,act:false });
  // 切断時にやること。CPU には人間と同じ操作の出口を使わせているので、
  // 状態の作り直しもラウンドの中断も要らない
  p.net = null; p.isCPU = true;
  const x0 = p.cx, y0 = p.cy;
  for (let i = 0; i < 600; i++) tick(host, guest);
  const moved = Math.abs(p.cx - x0) + Math.abs(p.cy - y0);
  ok(moved > 2, `CPU が引き継いでいない（移動量 ${moved.toFixed(2)}）`);
  return `移動量 ${moved.toFixed(1)} タイル`;
});

t('突進の途中で回線が切れても固まらない', () => {
  // ⛔ ぞうの突進は移動・破壊・取得・被弾に同時に割り込むので、
  //    状態の途中で持ち主が変わると止まりやすい。名指しで見張る
  const { host, guest } = pair({ mode: 'vs', p1: 'elephant', p2: 'elephant', clear: true });
  const p = host.X.players[1];
  p.cx = 11.5; p.cy = 7.5;
  host.X.NET.receiveInput(p, { up:false,down:false,left:false,right:true,bomb:false,act:false });
  host.X.elephantCharge(p);
  tick(host, guest);
  p.net = null; p.isCPU = true;              // 突進の最中に切断
  const x0 = p.cx, y0 = p.cy;
  for (let i = 0; i < 600; i++) { tick(host, guest); guest.X.draw(); }
  const moved = Math.abs(p.cx - x0) + Math.abs(p.cy - y0);
  ok(moved > 1, `突進中に切断したら固まった（移動量 ${moved.toFixed(2)}）`);
  return `移動量 ${moved.toFixed(1)} タイル`;
});

/* ============ 14. ラウンド遷移 ============ */
t('ラウンドが変わってもゲストの盤面が1スナップショットで追いつく', () => {
  const { host, guest } = pair();
  for (let i = 0; i < 60; i++) tick(host, guest);
  host.X.startRound();                       // ホストだけ新しい盤面を作る
  const before = guest.X.grid.map(r => r.join('')).join('');
  const after = (tick(host, guest), guest.X.grid.map(r => r.join('')).join(''));
  ok(before !== after, '盤面が更新されていない');
  eq(after, host.X.grid.map(r => r.join('')).join(''), 'ラウンド後の盤面');
  return 'ok';
});

/* ============ 15. エンコーダのキー監査（長期的に一番効く） ============ */
t('★エンコーダが落としているフィールドが無い（除外リストに書いたものを除く）', () => {
  // テスト9は「名前を挙げたフィールド」しか見ない。半年後に誰かが makePlayer へ
  // フィールドを足したとき、それが送られていなくてもテスト9は緑のままになる。
  // ここでは **集合として** 突き合わせて、判断を強制する。
  const { host, guest } = pair({ mode: 'vs', p1: 'fox', p2: 'frog' });
  const [a, b] = host.X.players;
  a.cx = 3.5; a.cy = 3.5;
  host.X.castFoxfire(a); host.X.frogSlime(b); host.X.rabbitPoroporo(a);
  host.X.startTongue(b); host.X.elephantCharge(a);
  host.X.spawnBomb(a, 3, 3);

  const missing = [];
  for (let i = 0; i < 300; i++) {
    const snap = tick(host, guest);
    const checks = [
      ['players', host.X.players, snap.players, host.X.NET_SKIP.players],
      ['bombs',   host.X.bombs,   snap.bombs,   host.X.NET_SKIP.bombs],
      ['blasts',  host.X.blasts,  snap.blasts,  host.X.NET_SKIP.blasts],
      ['items',   host.X.items,   snap.items,   host.X.NET_SKIP.items],
      ['negis',   host.X.negis,   snap.negis,   host.X.NET_SKIP.negis],
      ['foxfires',host.X.foxfires,snap.foxfires,host.X.NET_SKIP.foxfires],
      ['slimes',  host.X.slimes,  snap.slimes,  host.X.NET_SKIP.slimes],
    ];
    for (const [name, srcArr, encArr, skip] of checks) {
      for (let j = 0; j < srcArr.length; j++) {
        const sent = new Set(Object.keys(encArr[j] || {}));
        for (const k of Object.keys(srcArr[j])) {
          if (skip && skip[k]) continue;
          if (!sent.has(k)) {
            const tag = `${name}.${k}`;
            if (!missing.includes(tag)) missing.push(tag);
          }
        }
      }
    }
  }
  ok(missing.length === 0,
     `エンコーダが落としている: ${missing.join(', ')}\n` +
     `   送らないと決めたなら NET_SKIP に理由つきで足すこと`);
  return '落としているフィールドなし';
});

t('★G のフィールドも落としていない（意図的に送らないものを除く）', () => {
  // G は画面遷移とラウンド管理が混ざっていて、増えやすい。
  const { host, guest } = pair();
  const snap = tick(host, guest);
  // 送らないと決めたもの: speed は各自のローカル設定（ネット中は変えさせない）、
  // frame / lastDeaths / lastDeathFrame は update() の中でしか読まない
  const SKIP_G = ['speed', 'frame', 'lastDeaths', 'lastDeathFrame'];
  const sent = new Set(Object.keys(snap.G));
  const missing = Object.keys(host.X.G).filter(k => !SKIP_G.includes(k) && !sent.has(k));
  ok(missing.length === 0, `G で落としている: ${missing.join(', ')}`);
  return `送っている ${sent.size} 個 / 意図的に除外 ${SKIP_G.length} 個`;
});

/* ============ fx（音・トースト） ============ */
t('ホストで鳴った音がスナップショットに載る', () => {
  const { host, guest } = pair({ mode: 'vs', clear: true });
  const p = host.X.players[0];
  p.cx = 5.5; p.cy = 5.5;
  host.X.placeBomb(p);                       // 音を鳴らすのは placeBomb（spawnBomb は無音）
  const snap = tick(host, guest);
  const kinds = (snap.fx || []).map(e => e[0]);
  ok(kinds.includes('se'), `音が載っていない（fx=${JSON.stringify(snap.fx)}）`);
  return `fx ${snap.fx.length} 件`;
});

t('fx は送ったら空になる（同じ音が鳴り続けない）', () => {
  const { host, guest } = pair({ mode: 'vs', clear: true });
  const p = host.X.players[0];
  p.cx = 5.5; p.cy = 5.5;
  host.X.placeBomb(p);
  tick(host, guest);
  const snap2 = tick(host, guest);
  eq(snap2.fx.length, 0, '2フレーム目の fx');
  return 'ok';
});

t('ゲストは受け取った fx を送り返さない', () => {
  const { host, guest } = pair({ mode: 'vs', clear: true });
  const p = host.X.players[0];
  p.cx = 5.5; p.cy = 5.5;
  host.X.placeBomb(p);
  tick(host, guest);
  eq(guest.X.NET.fx.length, 0, 'ゲスト側に fx が溜まっている');
  return 'ok';
});

/* ============ G.phase の二重書き込み ============ */
t('ロビーに居るゲストへ roundEnd が飛んできても画面を奪われない', () => {
  // G.phase は showScreen() が画面名を書き、ラウンド処理が roundEnd/over を書く。
  // 1つのフィールドに意味が2つ乗っているので、無条件に上書きすると
  // まだロビーに居るゲストの画面が消える。
  const { host, guest } = pair();
  guest.X.G.phase = 'title';                 // ゲストはまだロビー
  host.X.G.phase = 'roundEnd';
  tick(host, guest);
  eq(guest.X.G.phase, 'title', 'ロビーのゲストの画面');
  return 'ロビーを保持';
});

t('試合中のゲストには roundEnd が反映される', () => {
  const { host, guest } = pair();
  tick(host, guest);
  eq(guest.X.G.phase, 'play', '前提: ゲストが試合画面に居る');
  host.X.G.phase = 'roundEnd';
  tick(host, guest);
  eq(guest.X.G.phase, 'roundEnd', '試合中のゲストの画面');
  return 'ok';
});

/* ============ ローカル対戦への非退行 ============ */
t('NET を使わないローカル対戦の挙動が変わっていない', () => {
  const w = makeWorld('local');
  Object.assign(w.X.CFG, { mode: '2p', hpP1: 3, hpP2: 3, hpCPU: 3,
    time: 180, wins: 3, sudden: true, sfx: false, bgm: false });
  w.X.startGame();
  eq(w.X.NET.role, null, 'ローカルでは role は null のまま');
  for (let i = 0; i < 300; i++) { w.clock.t += 16.6; w.X.update(1 / 60); w.X.draw(); }
  eq(w.X.NET.fx.length, 0, 'ローカルでは fx を積まない（ホストではないので）');
  ok(w.X.players.every(p => !p.net), 'ローカルでは p.net が付かない');
  return 'ok';
});

/* ============ LAN対戦 Phase 4（ロビー・begin の座席保護） ============ */
t('★begin配信後もゲストのCFG.lanLocalは自分の本当の座席のまま（サーバの welcome だけが出どころ）', () => {
  // プランの警告：begin に lanLocal を乗せて Object.assign すると、
  // 全ゲストの席番号が host の値（常に0）で塗り潰される。
  // このテストは「begin のたびに実際に壊れていないか」を確認する回帰テスト。
  const host = makeWorld('host');
  const guest = makeWorld('guest');

  // 1. 各ワールドがサーバの welcome を受け取った状態を作る
  //    （host=座席0・guest=座席2。あえて0以外にして、0での塗り潰しが
  //     起きたら即座に矛盾が出るようにする）
  host.X.NET.role = 'host'; host.X.NET.seat = 0; host.X.CFG.lanLocal = 0;
  guest.X.NET.role = 'guest'; guest.X.NET.seat = 2; guest.X.CFG.lanLocal = 2;

  // 2. ホストがロビーで設定を決めて「はじめる」を押す＝ NET.beginAsHost() の中身を
  //    そのまま再現する（lanLocal を含めない cfg を作る）
  Object.assign(host.X.CFG, { mode: 'lan', lanHumans: 3,
    lanPicks: ['rabbit', 'frog', 'fox', 'elephant'] });
  const cfg = { mode: 'lan', lanHumans: host.X.CFG.lanHumans,
                lanPicks: host.X.CFG.lanPicks.slice() };
  ok(!('lanLocal' in cfg), 'cfg に lanLocal を含めてはいけない');

  // 3. ゲストが begin を受け取ったときの処理をそのまま再現する
  Object.assign(guest.X.CFG, cfg);
  guest.X.startGame();

  eq(guest.X.CFG.lanLocal, 2, 'begin 受信後に lanLocal が書き換わってしまった');
  const me = guest.X.players[guest.X.CFG.lanLocal];
  ok(me, 'players[lanLocal] が存在しない（席番号が壊れている証拠）');
  eq(me.controls, guest.X.CONTROLS.solo, 'players[lanLocal].controls が solo でない');
  return `lanLocal=${guest.X.CFG.lanLocal} で正しい枠を指せている`;
});

t('★「はじめる」でホスト自身もLANモードになる（beginAsHost を実際に呼ぶ）', () => {
  /* 2026-08-22、家族と初めて実機で繋いだときに出たバグの回帰テスト。

     症状：ロビーでは2人繋がっているのに、ホストが「はじめる」を押すと
           ホストの画面が「1人＋CPU3」になる。ゲスト側からは、その
           ホストの1人プレイがリアルタイムに正しく見える。
     原因：beginAsHost() が cfg を「ゲストに送る」だけで
           「自分の CFG に適用する」のを忘れていた。ホストの CFG.mode は
           既定の '1p' のままなので setupPlayers() が LAN 分岐に入らない。
     厄介な点：通信は完全に正常なので、原因がネットワーク側に見える。

     ⚠️ なぜ既存のテストで捕まらなかったか：上の lanLocal のテストは
        「beginAsHost() の中身をそのまま再現する」書き方をしていた。
        実装をコピーしたテストは、実装側の抜けを構造的に検出できない。
        だからこのテストは NET.beginAsHost() を**実際に呼ぶ**。 */
  const host = makeWorld('host');
  host.X.NET.role = 'host'; host.X.NET.seat = 0; host.X.CFG.lanLocal = 0;

  /* 前提：この世界はタイトルの「LAN対戦」ボタンを通っていないので CFG.mode は既定のまま
     （ここが 2026-08-22 の事故の起点）。
     ⚠️ v4.2.1 から、実機では tm4 のクリックが CFG.mode='lan' を立てる。
        それでも beginAsHost 側で mode を書く責任は残す——ボタンを通らない
        経路（ここのように直接呼ぶ／将来の別の入口）で 1p のまま試合が始まると、
        「ホストだけ1人プレイ」に戻る */
  eq(host.X.CFG.mode, '1p', '前提が変わった: CFG.mode の既定は 1p のはず');

  host.X.CFG.lanHumans = 3;
  host.X.CFG.lanPicks = ['rabbit', 'frog', 'fox', 'elephant'];
  // 3人ぶんの席が実際に埋まっている状態にする。beginAsHost() は
  // 座っている数を超える人間枠を作らない（下の「分身」テストを参照）ので、
  // ここを省くと人数が 1 に切り詰められる
  host.X.NET.roster = new Set([0, 1, 2]);

  // WebSocket のスタブ。送信内容を捕まえるだけ
  let sent = null;
  host.X.NET.ws = { readyState: 1, send(s) { sent = JSON.parse(s); } };

  host.X.NET.beginAsHost();

  eq(host.X.CFG.mode, 'lan',
     'ホスト自身の CFG.mode が lan になっていない（ゲストにだけ送って自分に適用し忘れ）');
  const humans = host.X.players.filter(p => !p.isCPU).length;
  eq(humans, 3, `ホスト側の人間枠が lanHumans と一致しない（1 なら 1p 分岐に落ちている）`);
  eq(host.X.players.length, 4, 'LAN は4枠固定');

  // 送信内容も同時に見張る（座席の塗り潰し事故の再発防止）
  eq(sent.t, 'begin', 'begin メッセージが送られていない');
  eq(sent.cfg.mode, 'lan', '送る cfg の mode が lan でない');
  ok(!('lanLocal' in sent.cfg), 'cfg に lanLocal を含めてはいけない');
  eq(host.X.CFG.lanLocal, 0, 'ホスト自身の lanLocal が壊れた');

  return `mode=${host.X.CFG.mode} 人間${humans}人 CPU${4 - humans}人`;
});

/* ============ Phase 5: 切断→CPU引き継ぎ（実際の handleMessage 経路） ============ */
t('★peer_leftを実際のhandleMessage経由で受けてもCPU引き継ぎが起きる', () => {
  // 「回線が切れた枠は CPU が引き継いで動き続ける」テストは p.net/p.isCPU を
  // 手で書き換えて確認していた。ここでは実際にサーバから届く形の JSON を
  // NET.handleMessage に通し、本物の配線（peer_left ハンドラの2行）が
  // 正しく動くかを見る。
  const { host, guest } = pair({ mode: 'vs', clear: true });
  const p = host.X.players[1];
  ok(!p.isCPU, '前提: 切断前は人間のはず');

  host.X.NET.handleMessage(JSON.stringify({ t: 'peer_left', seat: 1, host: false }));

  eq(p.isCPU, true, 'peer_left を受けても isCPU が true にならない');
  eq(p.net, null, 'peer_left を受けても p.net が残っている');

  const x0 = p.cx, y0 = p.cy;
  for (let i = 0; i < 300; i++) tick(host, guest);
  const moved = Math.abs(p.cx - x0) + Math.abs(p.cy - y0);
  ok(moved > 1, `CPU 引き継ぎ後に動いていない（移動量 ${moved.toFixed(2)}）`);
  return `isCPU化 + 移動量 ${moved.toFixed(1)} タイル`;
});

t('ゲスト側でホストの切断（peer_left host:true）を受けてもタイトルへ戻るだけで例外が出ない', () => {
  const guest = makeWorld('guest');
  guest.X.NET.role = 'guest'; guest.X.NET.seat = 1; guest.X.NET.ws = null;

  guest.X.NET.handleMessage(JSON.stringify({ t: 'peer_left', seat: 0, host: true }));

  eq(guest.X.NET.role, null, 'ホスト切断後は role がリセットされるべき');
  eq(guest.X.G.phase, 'title', 'ホスト切断後はタイトルへ戻るべき');
  return 'ok';
});

t('もし誤って cfg に lanLocal:0 を含めてしまったら、このテストが壊れて教えてくれる', () => {
  // ↑のテストが「正しい実装」を守るのに対し、こちらは
  // 「間違った実装をしたら本当に検出できるか」を確認する対照実験。
  const guest = makeWorld('guest');
  guest.X.NET.role = 'guest'; guest.X.NET.seat = 2; guest.X.CFG.lanLocal = 2;

  // ⛔ わざとやってはいけない書き方（lanLocal を含む cfg）を再現する
  const brokenCfg = { mode: 'lan', lanHumans: 1,
                      lanPicks: ['rabbit', 'frog', 'fox', 'elephant'], lanLocal: 0 };
  Object.assign(guest.X.CFG, brokenCfg);
  guest.X.startGame();

  // lanHumans:1 の場合、座席0だけが人間で1〜3はCPU。
  // 本当の座席は2なのに、塗り潰された0を読んでしまうと
  // 「自分のはずの枠（座席2・本来CPU）が誤って人間の枠であるかのように扱われる」
  eq(guest.X.CFG.lanLocal, 0, '（対照実験）意図的に壊した値が入っている');
  eq(guest.X.players[2].isCPU, true, '座席2は本来 CPU のはず（lanHumans:1 のため）');
  eq(guest.X.players[guest.X.CFG.lanLocal].isCPU, false,
     '壊れた lanLocal が指す座席0は human 側になっている（矛盾の再現）');
  return '対照実験: 壊れた状態を再現できた（＝上のテストは実際に効く）';
});

/* ============ ロビーで決めたルールがゲストまで届く（v4.2.0） ============ */

t('★「はじめる」で配る cfg にロビーのルールが全部乗る（beginAsHost を実際に呼ぶ）', () => {
  /* ⛔ v4.1.0 の cfg は { mode, lanHumans, lanPicks } の3項目だけだった。
     体力も勝利数も時間もサドンデスも乗っていないので、ロビーでルールを
     決められるようにしても、ゲストの盤面には何も伝わらない。
     ⚠️ 実装をコピーしたテストは実装の抜けを検出できないので、
        ここは NET.beginAsHost() を実際に呼ぶ（上のテストと同じ方針）。 */
  const host = makeWorld('host');
  host.X.NET.role = 'host'; host.X.NET.seat = 0; host.X.CFG.lanLocal = 0;
  host.X.NET.roster = new Set([0, 1]);
  Object.assign(host.X.CFG, {
    lanHumans: 2, lanPicks: ['rabbit', 'frog', 'fox', 'mole'],
    lanHp: [1, 2, 3, 4], wins: 5, time: 60, sudden: false,
  });

  let sent = null;
  host.X.NET.ws = { readyState: 1, send(s) { sent = JSON.parse(s); } };
  host.X.NET.beginAsHost();

  eq(sent.t, 'begin', 'begin が送られていない');
  eq(String(sent.cfg.lanHp), '1,2,3,4', '送る cfg に lanHp が乗っていない');
  eq(sent.cfg.wins, 5, '送る cfg に wins が乗っていない');
  eq(sent.cfg.time, 60, '送る cfg に time が乗っていない');
  eq(sent.cfg.sudden, false, '送る cfg に sudden が乗っていない');
  // ⛔ 席番号だけは絶対に乗せない（全ゲストが「自分は座席0」だと誤解する）
  ok(!('lanLocal' in sent.cfg), 'cfg に lanLocal を含めてはいけない');
  // lanHp は配列。参照をそのまま渡すと、ホストが後でロビーを触ったときに
  // 送信済みの内容が書き換わる（JSON 化済みなので実害は無いが、写しを渡す）
  ok(sent.cfg.lanHp !== host.X.CFG.lanHp, 'lanHp は写しを渡すこと（slice）');
  return `lanHp=${sent.cfg.lanHp} wins=${sent.cfg.wins} time=${sent.cfg.time} sd=${sent.cfg.sudden}`;
});

t('★ゲストが begin を受けると4枠の体力がホストと同じになる', () => {
  /* ホスト権威なので盤面はホストの CFG で作られるが、ゲストも同じ cfg で
     startGame するので、カード（体力の表示）が食い違わないことを見る */
  const host = makeWorld('host');
  const guest = makeWorld('guest');
  host.X.NET.role = 'host'; host.X.NET.seat = 0; host.X.CFG.lanLocal = 0;
  host.X.NET.roster = new Set([0, 1]);
  guest.X.NET.role = 'guest'; guest.X.NET.seat = 1; guest.X.CFG.lanLocal = 1;
  // ゲスト側は 1p/2p/vs 用の値をわざと別にしておく。枠ごとの体力が
  // 届いていなければ、こちらの 6 が出る
  Object.assign(guest.X.CFG, { hpP1: 6, hpP2: 6, hpCPU: 6 });

  Object.assign(host.X.CFG, {
    lanHumans: 2, lanPicks: ['rabbit', 'frog', 'fox', 'mole'],
    lanHp: [1, 2, 3, 4], wins: 5, time: 60, sudden: false,
  });
  let sent = null;
  host.X.NET.ws = { readyState: 1, send(s) { sent = JSON.parse(s); } };
  host.X.NET.beginAsHost();

  guest.X.NET.handleMessage(JSON.stringify(sent));

  guest.X.players.forEach((p, i) => {
    const want = [1, 2, 3, 4][i] + (p.animal.hpBonus || 0);
    eq(p.maxHp, want, `ゲスト側 ${i + 1}P の maxHp`);
  });
  eq(guest.X.CFG.lanLocal, 1, 'begin でゲストの席番号が壊れた');
  eq(guest.X.CFG.sudden, false, 'サドンデスの設定が届いていない');
  return guest.X.players.map(p => p.maxHp).join(' / ');
});

/* ============ ロビーの設定がゲストまで届く（v4.2.0） ============ */

/** ロビーに立っているホストとゲストの組。send を捕まえる箱つき */
function lobbyPair() {
  const host = makeWorld('host');
  const guest = makeWorld('guest');
  host.X.NET.role = 'host'; host.X.NET.seat = 0; host.X.CFG.lanLocal = 0;
  host.X.NET.roster = new Set([0, 1]);
  guest.X.NET.role = 'guest'; guest.X.NET.seat = 1; guest.X.CFG.lanLocal = 1;
  guest.X.NET.roster = new Set([0, 1]);
  const common = { mode: 'lan', lanHumans: 2, lanPicks: ['rabbit', 'frog', 'fox', 'mole'],
                   lanHp: [1, 1, 1, 1], cpuLevel: ['futsu', 'futsu', 'futsu'],
                   wins: 3, time: 180, sudden: true, sfx: false, bgm: false };
  Object.assign(host.X.CFG, common);
  Object.assign(guest.X.CFG, common, { mode: '1p' });   // ゲストの mode は begin まで別物
  const outbox = [];
  host.X.NET.ws = { readyState: 1, send(s) { outbox.push(JSON.parse(s)); } };
  guest.X.showScreen('lobby');
  return { host, guest, outbox };
}

t('★ホストがロビーで決めたルールがゲストに届く（中継は中身を見ない）', () => {
  /* ⭐ server/relay.py の Room.route は「ホストからのものは全ゲストへ」
     流すだけで中身を一切見ない。だから新しい種類のメッセージを足すのに
     サーバ側の変更は1行も要らない ——中継を無知に作ったことの見返り */
  const { host, guest, outbox } = lobbyPair();
  host.X.CFG.lanHp = [1, 2, 5, 4];
  host.X.CFG.wins = 5; host.X.CFG.time = 60; host.X.CFG.sudden = false;
  host.X.CFG.cpuLevel = ['oni', 'futsu', 'futsu'];
  host.X.NET.sendLobby();

  eq(outbox.length, 1, 'lobby メッセージが送られていない');
  const msg = outbox[0];
  eq(msg.t, 'lobby', 'メッセージの種類が lobby でない');
  guest.X.NET.handleMessage(JSON.stringify(msg));

  eq(String(guest.X.CFG.lanHp), '1,2,5,4', 'ゲストに体力が届いていない');
  eq(guest.X.CFG.wins, 5, 'ゲストに勝利数が届いていない');
  eq(guest.X.CFG.time, 60, 'ゲストにじかんが届いていない');
  eq(guest.X.CFG.sudden, false, 'ゲストにサドンデスが届いていない');
  eq(guest.X.CFG.cpuLevel[0], 'oni', 'ゲストに CPU の強さが届いていない');
  return `lanHp=${guest.X.CFG.lanHp} wins=${guest.X.CFG.wins}`;
});

t('★lobby メッセージは席番号もモードも書き換えない', () => {
  /* ⛔ begin と同じ事故がここでも起きうる。Object.assign(CFG, msg) にすると
     t が混ざり、将来ホスト側が項目を足したとき lanLocal / mode まで
     流れ込む経路ができる。受け取る側は名指しの列挙で受ける */
  const { host, guest, outbox } = lobbyPair();
  host.X.CFG.lanHp = [3, 3, 3, 3];
  host.X.NET.sendLobby();
  const msg = outbox[0];
  ok(!('lanLocal' in msg), 'lobby メッセージに lanLocal を含めてはいけない');
  ok(!('mode' in msg), 'lobby メッセージに mode を含めてはいけない');

  guest.X.NET.handleMessage(JSON.stringify(msg));
  eq(guest.X.CFG.lanLocal, 1, 'ゲストの席番号が書き換わった');
  eq(guest.X.CFG.mode, '1p', 'lobby でゲストの mode まで書き換えた');
  ok(!('t' in guest.X.CFG), 'CFG にメッセージ種別 t が混ざった');
  return '席番号もモードも無傷';
});

t('★ホストは自分が送った lobby を受け取っても何も変えない', () => {
  const { host, outbox } = lobbyPair();
  host.X.CFG.lanHp = [2, 2, 2, 2];
  host.X.NET.sendLobby();
  host.X.CFG.lanHp = [4, 4, 4, 4];            // そのあとホストが更に触った
  host.X.NET.handleMessage(JSON.stringify(outbox[0]));
  eq(String(host.X.CFG.lanHp), '4,4,4,4', 'ホストが自分の送信で巻き戻された');
  return 'ホストは自分の送信を無視する';
});

t('★lobby を受け取ってもゲストのカーソルは何も掴まない（見るだけ）', () => {
  /* ⛔ ゲスト側に chips を置くと、名簿に載せなくてもクリックで
     ローカルの CFG が動く。「選んだのに反映されない」体験になるので、
     ゲスト側は触れない表示にする */
  const { guest, host, outbox } = lobbyPair();
  host.X.CFG.lanHp = [1, 2, 3, 4];
  host.X.NET.sendLobby();
  guest.X.NET.handleMessage(JSON.stringify(outbox[0]));
  guest.X.MENU.on = true;
  const gs = guest.X.MENU.list();
  eq(gs.length, 0, `ゲストのロビーで名簿に ${gs.length} グループ出ている`);
  return 'ゲストは見るだけ';
});

t('★ゲストが遅れて入っても今の設定が届く（buildLobby が配り直す）', () => {
  /* ⛔ 送るのが「設定を変えた瞬間」だけだと、あとから参加した人には
     何も届かない（ロビーは待ち合わせ場所なので、参加は必ず後から来る）。
     peer_joined も buildLobby を通るので、そこで配り直せば拾える */
  const { host, outbox } = lobbyPair();
  host.X.CFG.lanHp = [1, 2, 3, 4];
  host.X.showScreen('lobby');
  /* ⛔ 箱を空にするのは showScreen の**あと**。showScreen も buildLobby を通るので、
     先に空にすると、peer_joined の経路を消してもそちらの送信で緑になる */
  outbox.length = 0;
  host.X.NET.handleMessage(JSON.stringify({ t: 'peer_joined', seat: 2 }));
  ok(outbox.some(m => m.t === 'lobby'),
     '新しい人が入っても設定が配られない（送ったもの: ' +
     outbox.map(m => m.t).join(',') + '）');
  return `peer_joined で ${outbox.filter(m => m.t === 'lobby').length} 回配った`;
});

/* ---------- report ---------- */
t('★誰も座っていない人間枠を作らない（ホストの分身が動き出すのを防ぐ）', () => {
  /* 2026-08-22 実測の回帰テスト。修正#1（ホストも LAN モードに入る）を入れた
     ことで初めて到達するようになった経路。

     setupPlayersLan() は i < lanHumans の枠を全部 isCPU:false + solo にする。
     誰も繋いでいない枠には p.net が付かない（receiveInput でしか付かない）ので、
     inputOf() がローカルのキーボードへ落ちる。結果、ホストが右を押すと
     空席の枠も一緒に右へ動く——ラウンド中ずっと付いてくる分身になる。

     ロビーは空席を「⚪ 空席・待機中」と表示するので、
     「あとで入れるように多めに」と人数を選ぶ操作でそのまま踏む。 */
  const w = makeWorld('host');
  w.X.NET.role = 'host'; w.X.NET.seat = 0; w.X.CFG.lanLocal = 0;
  w.X.NET.roster = new Set([0]);            // 自分しか繋がっていない
  w.X.NET.ws = { readyState: 1, send() {} };
  Object.assign(w.X.CFG, { lanHumans: 3, lanPicks: ['rabbit','frog','fox','elephant'],
    hpP1: 3, hpP2: 3, hpCPU: 3, time: 180, wins: 3, sfx: false, bgm: false });

  w.X.NET.beginAsHost();

  eq(w.X.CFG.lanHumans, 1, '座っているのは1人なのに人間枠が減らされていない');
  const ghosts = w.X.players.filter((p, i) => !p.isCPU && !p.net && i !== w.X.CFG.lanLocal);
  eq(ghosts.length, 0, `操作者のいない人間枠が ${ghosts.length} 個ある（分身になる）`);

  // 実際に動かして、分身が付いてこないことを確かめる
  const before = w.X.players.map(p => ({ cx: p.cx, cy: p.cy }));
  w.X.keys.add('ArrowRight');
  for (let i = 0; i < 60; i++) { w.clock.t += 16.6; w.X.update(1 / 60); }
  const moved = w.X.players.map((p, i) =>
    Math.hypot(p.cx - before[i].cx, p.cy - before[i].cy));
  ok(moved[0] > 0.5, `操作している枠0が動いていない（${moved[0].toFixed(2)}）`);
  return `枠0=${moved[0].toFixed(2)}タイル移動 / 空席の人間枠 0 個`;
});

t('★穴あきの座席でも分身を作らない（座席1が抜けて2だけ残った状態）', () => {
  /* 「繋がっている人数」でクランプすると、ここで枠1が空席のまま
     人間扱いになって分身が復活する。先頭から連続して埋まっている数で
     切っているかを見張る。 */
  const w = makeWorld('host');
  w.X.NET.role = 'host'; w.X.NET.seat = 0; w.X.CFG.lanLocal = 0;
  w.X.NET.roster = new Set([0, 2]);          // 座席1が抜けている
  w.X.NET.ws = { readyState: 1, send() {} };
  Object.assign(w.X.CFG, { lanHumans: 3, lanPicks: ['rabbit','frog','fox','elephant'],
    hpP1: 3, hpP2: 3, hpCPU: 3, time: 180, wins: 3, sfx: false, bgm: false });

  w.X.NET.beginAsHost();

  eq(w.X.CFG.lanHumans, 1, '連続して埋まっているのは座席0だけなので人間枠は1');
  const ghosts = w.X.players.filter((p, i) => !p.isCPU && !p.net && i !== w.X.CFG.lanLocal);
  eq(ghosts.length, 0, '穴あきで分身が復活している');
  return '座席1の穴で分身が生まれない';
});

console.log('');
for (const [mark, name, msg] of results) {
  console.log(`${mark} ${name}${msg ? `  — ${msg}` : ''}`);
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);

