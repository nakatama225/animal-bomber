/* 作者が報告したバグを名指しで検証するユニットテスト
   1. HP を超過して被弾したら必ず死ぬ（葱ボン or 退場になる）
   2. きつねは初期から爆弾を1個多く持つ／方向キー押しながらで一列設置
   3. 他人が足元に爆弾を置いても詰まない
   4. うんこは爆風で焼けずに吹き飛ぶ
   5. 葱ボンの交代・残1分退場
   6. サドンデス
*/
const fs = require('fs');
const HTML = require('path').join(__dirname, '..', 'animal-bomber.html');
const src = fs.readFileSync(HTML, 'utf8');
let code = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];

/* ---- stubs ---- */
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
/** ⭐ innerHTML='' で子を「画面から切り離す」ところまで真似る。
    本物のブラウザでは、ビルダーが wrap.innerHTML='' したあと、
    古い箱を掴んだままのコールバックがそこに要素を足しても画面には出ない
    （el.isConnected === false）。スタブがそこを再現していないと、
    「カーソルは乗るのに画面には何も無い」類のバグがテストで緑のまま通る。 */
function detachEl(el) {
  if (!el || el._det) return;
  el._det = true;
  for (const k of (el.kids || [])) detachEl(k);
}
const makeEl = () => ({
  classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
  style: {}, kids: [], _det: false, _html: '',
  appendChild(c) { this.kids.push(c); if (c) c._det = this._det; return c; },
  get isConnected() { return !this._det; },
  get innerHTML() { return this._html; },
  set innerHTML(v) {
    this._html = v;
    // 空文字は「中身を捨てる」。それ以外の代入は、このスタブでは中身を作らない
    if (v === '') { for (const k of this.kids) detachEl(k); this.kids = []; }
  },
  textContent: '', onclick: null,
  getContext: () => ctxStub, width: 0, height: 0, addEventListener: noop,
});
const cache = new Map();
global.window = { addEventListener: noop };
global.document = {
  getElementById(id) { if (!cache.has(id)) cache.set(id, makeEl()); return cache.get(id); },
  createElement: makeEl, addEventListener: noop,
  querySelector: () => makeEl(), querySelectorAll: () => [],
};
let VT = 0;
global.performance = { now: () => VT };
global.requestAnimationFrame = () => 0;
global.cancelAnimationFrame = noop;
global.setInterval = () => 0; global.clearInterval = noop;
global.setTimeout = () => 0;  global.clearTimeout = noop;

code += `
global.__X = {
  get G(){return G}, get players(){return players}, get bombs(){return bombs},
  get blasts(){return blasts}, get items(){return items}, get grid(){return grid},
  get negis(){return negis}, set negis(v){negis=v},
  get foxfires(){return foxfires},
  castFoxfire, updateFoxfires, foxfireStep, FOXFIRE_LIFE, FOXFIRE_STEP,
  specialOf, elephantCharge, updateCharge, CHARGE_TIME, CHARGE_ARMOR, heartsOf,
  rabbitPoroporo, updatePoroporos, get poroporos(){return poroporos},
  frogSlime, updateSlimes, slimeBurst, get slimes(){return slimes},
  SLIME_THROW, SLIME_FLY, SLIME_HOP_MIN, SLIME_HOP_MAX, SLIME_HOP_DIST, SLIME_DIRS,
  SNOT_MELT,
  foxLineShot, elephantSnot, HOP_COOL, SNOT_RANGE, SNOT_COOL,
  PORO_RANGE, PORO_TIME, PORO_LIFE,
  tongueReach, tongueBurnCheck, TONGUE_BURN_STUN, TONGUE_REGEN, foePathDist,
  chargeSweep, chargeDrop, CPU_LEVELS, CPU_LEVEL_KEYS, cpuLevelOf, cpuUpdate, planCPU,
  startGame, update, draw, CFG, ANIMALS, ANIMAL_LIST, SPECIALS, POOP_KEYS, POOPS,
  POWERUPS, ITEM_DEF, spitPowerup, isBorder, isUntouchable,
  startRound, resetPlayersForRound, advanceBanner, drawAnimalBody, FOX_LEAP,
  showScreen, setupScreenNav, buildSetup, buildPickers, buildHpRows, buildCpuRows,
  MENU, MENU_ORDER, MENU_SLOT, MENU_BACK, KEY_TO_PAD, askConfirm, askDisconnect, chips,
  backToSetup,
  VERSION, SCREENS,
  movePlayer, isBlastProof, isBusy, canPlaceBomb, isFrozen,
  startTongue, updateTongue, hop,
  get pits(){return pits}, startDigPit, updateDigging, pitAt, pitfallCheck,
  TONGUE_STEP, TONGUE_MAX, PIT_DIG, PIT_HOLD, BLAST_HITBOX,
  getPower, getSpeed, placeBomb, placeLineBombs, plannedLineBombs, spawnBomb,
  explodeChain, hurt, kill, damageCheck, checkEnd, enterSuddenDeath,
  toNegibon, fireNegi, negiHit, negiPos, updateNegis, negibonAvailable, negiMove, LANE, PERIM,
  applyItem, pickupCheck, blowPoop, useSpecial, doAction, doSpecial, collides, isSolidFor,
  CONTROLS, KEYHINT, BOMB_MAX, POWER_MAX, SHOE_MAX, SPEED_MAX, BASE_SPEED, SHOE_STEP, DIG_PENALTY, skillLabelOf,
  fitBoard, TILE_MIN, TILE_MAX, SIDE_W, get TILE(){return TILE}, get CW(){return CW}, get CH(){return CH},
  humanUpdate, SPECIAL_HOLD, inputOf, NET, setupPlayersLan, buildLobby,
  pollGamepads, PAD, PAD_BTN, togglePause, askBackToSetup, renderKeyHelp,
  get keys(){return keys}, get pressed(){return pressed},
  bombAt, itemAt, overlapsTile, dangerMap, bombCells, canEscapeAfterBomb, walkableFor, nextToBomb,
  refreshBombIgnore,
  BOMB_FUSE, BLAST_DUR, INVULN, COLS, ROWS, EMPTY, HARD, SOFT, RADIUS,
  NEGI_CUTOFF, POOP_LIFE, POOP_STACK_MAX,
  IT_POOP, IT_BANANA, IT_ONION, IT_CHICKEN, IT_BOMB, IT_FIRE, IT_SHOE,
};`;
try {
  new Function(code)();
} catch (e) {
  // R1 テスト：NET などのオブジェクトがトップレベルで location / WebSocket に
  // 触ると、ここで ReferenceError になり164件全部がテスト開始前に落ちる。
  // 生のスタックトレースではなく理由を名指しして落とす。
  console.error(`❌ トップレベル実行時エラー: ${e.message}`);
  console.error('   R1: location / WebSocket はトップレベルで参照しない。');
  console.error('   ロビーのクリックからしか到達しない関数の中に置くこと。');
  process.exit(1);
}
const X = global.__X;

let pass = 0, fail = 0;
const results = [];
function t(name, fn) {
  try { const msg = fn(); pass++; results.push(['✅', name, msg || '']); }
  catch (e) { fail++; results.push(['❌', name, e.message]); }
}
function eq(a, b, what) {
  if (a !== b) throw new Error(`${what}: expected ${b}, got ${a}`);
}
function ok(c, what) { if (!c) throw new Error(what); }

/** 盤面を作って、素の状態のプレイヤーを取る */
function fresh(opts = {}) {
  const hp = opts.hp ?? 3;
  Object.assign(X.CFG, { mode: opts.mode || '2p',
    hpP1: hp, hpP2: hp, hpCPU: hp,
    time: opts.time ?? 180, sudden: opts.sudden ?? true, sfx: false, bgm: false });
  X.CFG.pick.p1 = opts.p1 || 'rabbit';
  X.CFG.pick.p2 = opts.p2 || 'frog';
  VT = 0;
  X.startGame();
  // 盤面を全部空にして実験しやすくする
  if (opts.clear !== false) {
    for (let y = 1; y < X.ROWS - 1; y++) for (let x = 1; x < X.COLS - 1; x++)
      if (X.grid[y][x] === X.SOFT) X.grid[y][x] = X.EMPTY;
  }
  return X.players;
}
const step = (n = 1, dt = 1 / 60) => { for (let i = 0; i < n; i++) { VT += dt * 1000; X.update(dt); } };

/* ============ 1. HP 超過で必ず死ぬ ============ */
t('HP3 のキャラは3回被弾でちょうど死ぬ（葱ボン行き）', () => {
  const [p] = fresh({ hp: 3, p1: 'rabbit' });
  eq(p.maxHp, 3, 'maxHp');
  const hits = [];
  for (let i = 0; i < 3; i++) {
    p.invuln = 0;
    X.hurt(p);
    hits.push(p.hp);
  }
  eq(p.hp, 0, 'hp after 3 hits');
  ok(p.state !== 'ALIVE', `3回被弾しても ALIVE のまま（state=${p.state}）`);
  eq(p.state, 'NEGIBON', 'state（葱ボンが有効な時間なので NEGIBON になるべき）');
  return `hp ${hits.join('→')} → ${p.state}`;
});

t('HP1〜6 すべてで「設定回数ぶん耐えて、次で死ぬ」', () => {
  const log = [];
  for (const hp of [1, 2, 3, 4, 5, 6]) {
    const [p] = fresh({ hp, p1: 'rabbit' });
    eq(p.maxHp, hp, `maxHp for hp=${hp}`);
    for (let i = 0; i < hp - 1; i++) { p.invuln = 0; X.hurt(p); }
    eq(p.state, 'ALIVE', `hp=${hp}: ${hp - 1}回目でまだ生きてるべき`);
    p.invuln = 0; X.hurt(p);
    ok(p.state !== 'ALIVE', `hp=${hp}: ${hp}回目で死ぬべきなのに ALIVE`);
    log.push(`${hp}→ok`);
  }
  return log.join(' ');
});

t('ぞうは設定HP+1 ぶん耐える', () => {
  const [p] = fresh({ hp: 3, p1: 'elephant' });
  eq(p.maxHp, 4, 'ぞうの maxHp');
  for (let i = 0; i < 3; i++) { p.invuln = 0; X.hurt(p); }
  eq(p.state, 'ALIVE', '3回では死なないべき');
  p.invuln = 0; X.hurt(p);
  ok(p.state !== 'ALIVE', '4回目で死ぬべき');
  return 'maxHp=4, 4発で退場';
});

t('実際の爆風でも HP ぶん被弾して死ぬ（無敵フレーム込み）', () => {
  const [p, q] = fresh({ hp: 2, p1: 'rabbit' });
  q.state = 'OUT';
  p.cx = 1.5; p.cy = 1.5;
  let hp0 = p.hp, rounds = 0;
  while (p.state === 'ALIVE' && rounds < 12) {
    rounds++;
    // 足元で爆発させる
    const b = X.spawnBomb(p, 1, 1);
    b.timer = 0.001;
    step(Math.ceil((X.BLAST_DUR + X.INVULN + 0.2) * 60));
  }
  ok(p.state !== 'ALIVE', `爆風を${rounds}回浴びても死なない（hp=${p.hp}）`);
  eq(rounds, hp0, '死ぬまでの被弾回数が HP と一致すべき');
  return `hp${hp0} → ${rounds}回の爆発で ${p.state}`;
});

t('1回の爆発で HP が2以上減らない（無敵フレームが効いてる）', () => {
  const [p, q] = fresh({ hp: 6, p1: 'rabbit' });
  q.state = 'OUT';
  p.cx = 1.5; p.cy = 1.5;
  p.powerUp = 4;                        // 爆風を伸ばして複数マス重ねる
  const b = X.spawnBomb(p, 1, 1);
  b.timer = 0.001;
  step(Math.ceil((X.BLAST_DUR + 0.1) * 60));
  eq(p.hp, 5, '1回の爆発でのダメージ');
  return 'hp6 → 5';
});

t('残り1分を切ってから死ぬと葱ボンではなく退場', () => {
  const [p] = fresh({ hp: 1, time: 180 });
  X.G.time = X.NEGI_CUTOFF - 1;
  p.invuln = 0; X.hurt(p);
  eq(p.state, 'OUT', 'カットオフ後の state');
  return 'OUT';
});

/* ============ 1.2 HP を 1P / 2P / CPU で別々に設定できる ============ */
t('1P / 2P / CPU で爆風にたえる回数を別々に設定できる', () => {
  Object.assign(X.CFG, { mode: '2p', hpP1: 5, hpP2: 3, hpCPU: 1,
    time: 180, wins: 3, sudden: true, sfx: false, bgm: false });
  X.CFG.pick.p1 = 'rabbit'; X.CFG.pick.p2 = 'frog';
  VT = 0; X.startGame();
  const ps = X.players;
  const p1 = ps.find(p => p.label === '1P');
  const p2 = ps.find(p => p.label === '2P');
  const cpus = ps.filter(p => p.isCPU);
  eq(p1.maxHp, 5, '1P の HP');
  eq(p2.maxHp, 3, '2P の HP');
  ok(cpus.length >= 1, 'CPU がいる');
  for (const c of cpus) {
    eq(c.maxHp, 1 + (c.animal.hpBonus || 0), `CPU(${c.animal.name}) の HP`);
  }
  return `1P=5 / 2P=3 / CPU=1`;
});

t('HP設定はラウンドをまたいでも維持される', () => {
  Object.assign(X.CFG, { mode: '2p', hpP1: 4, hpP2: 2, hpCPU: 1,
    time: 180, wins: 5, sudden: true, sfx: false, bgm: false });
  VT = 0; X.startGame();
  const p1 = X.players.find(p => p.label === '1P');
  const p2 = X.players.find(p => p.label === '2P');
  p1.hp = 1;
  X.startRound();
  eq(p1.maxHp, 4, 'ラウンド2でも 1P は 4');
  eq(p1.hp, 4, '満タンで復帰');
  eq(p2.maxHp, 2, 'ラウンド2でも 2P は 2');
  return 'ok';
});

t('ぞうの +1 は各枠の設定に上乗せされる', () => {
  Object.assign(X.CFG, { mode: '2p', hpP1: 3, hpP2: 1, hpCPU: 1,
    time: 180, wins: 3, sudden: true, sfx: false, bgm: false });
  X.CFG.pick.p1 = 'elephant'; X.CFG.pick.p2 = 'elephant';
  VT = 0; X.startGame();
  eq(X.players.find(p => p.label === '1P').maxHp, 4, '1P ぞう = 3+1');
  eq(X.players.find(p => p.label === '2P').maxHp, 2, '2P ぞう = 1+1');
  return 'ok';
});

/* ============ 1.3 ゲーム速度（倍速）============ */
t('倍速でも当たり判定をすり抜けない（サブステップで回してる）', () => {
  // 3倍速相当の進み方を「大きな dt 1回」ではなく「小さな dt を複数回」で再現し、
  // 爆風の上に立ってるプレイヤーが必ず被弾することを確かめる
  const [p, q] = fresh({ hp: 6, mode: 'vs', clear: true });
  q.state = 'OUT';
  p.cx = 5.5; p.cy = 5.5; p.invuln = 0;
  const b = X.spawnBomb(q, 5, 5);
  b.timer = 0.001;
  const hp0 = p.hp;
  // 3倍速の1フレーム = 1/60*3 秒ぶんを 3 サブステップで進める
  const rdt = 1 / 60, speed = 3, steps = Math.ceil(speed), sub = rdt * speed / steps;
  for (let f = 0; f < 40; f++) {
    for (let i = 0; i < steps; i++) { VT += sub * 1000; X.update(sub); }
  }
  ok(p.hp < hp0, `3倍速で爆風をすり抜けた（hp ${hp0}→${p.hp}）`);
  return `hp ${hp0}→${p.hp}`;
});

t('👟MAX + 3倍速でも 柱と爆風をすり抜けない（本番と同じサブステップ計算で）', () => {
  // ★ 上限を 13 に上げたので、1フレームの移動距離が RADIUS(0.36) を超えないか確かめる。
  //   本番 loop() と同じ式でサブステップ数を出す（式を変えたらここも合わせる）
  const SUB_MAX = 0.12;
  const subStepsOf = (rdt, speed, fastest) =>
    Math.min(16, Math.max(1, Math.ceil(speed), Math.ceil(rdt * speed * fastest / SUB_MAX)));

  // --- 柱をすり抜けないか ---
  const [p, q] = fresh({ hp: 9, mode: 'vs', clear: true });
  q.state = 'OUT';
  p.shoes = X.SHOE_MAX; p.powerUp = X.POWER_MAX; p.maxBombs = X.BOMB_MAX;
  const spd = X.getSpeed(p);
  ok(spd > 8, `👟MAX で速くなってない (${spd.toFixed(2)})`);
  eq(X.grid[2][2], X.HARD, '前提: (2,2) は柱');
  p.cx = 1.5; p.cy = 2.5;                   // 柱の左どなり
  const rdt = 1 / 60, speed = 3;
  const steps = subStepsOf(rdt, speed, spd), sub = rdt * speed / steps;
  ok(sub * spd < 0.36, `1刻みの移動が RADIUS を超えてる (${(sub * spd).toFixed(3)})`);
  for (let f = 0; f < 30; f++)
    for (let i = 0; i < steps; i++) { X.movePlayer(p, 1, 0, sub); VT += sub * 1000; }
  ok(p.cx < 2.0, `柱をすり抜けた (cx=${p.cx.toFixed(2)})`);

  // --- 爆風をすり抜けないか ---
  const [r, s2] = fresh({ hp: 9, mode: 'vs', clear: true });
  s2.state = 'OUT';
  r.shoes = X.SHOE_MAX; r.invuln = 0;
  r.cx = 5.5; r.cy = 5.5;
  const b = X.spawnBomb(s2, 5, 5);
  b.timer = 0.001;
  const hp0 = r.hp;
  const st2 = subStepsOf(rdt, speed, X.getSpeed(r)), sub2 = rdt * speed / st2;
  for (let f = 0; f < 40; f++)
    for (let i = 0; i < st2; i++) { VT += sub2 * 1000; X.update(sub2); }
  ok(r.hp < hp0, `3倍速+👟MAX で爆風をすり抜けた（hp ${hp0}→${r.hp}）`);
  return `速度${spd.toFixed(2)} / ${steps}サブステップ / 1刻み${(sub * spd).toFixed(3)}タイル`;
});

t('上限は 💣13 🔥13 👟13', () => {
  eq(X.BOMB_MAX, 13, '爆弾の上限');
  eq(X.POWER_MAX, 13, '火力の上限');
  eq(X.SHOE_MAX, 13, '👟の上限');
  const [p] = fresh({ mode: 'vs', clear: true });
  for (let i = 0; i < 20; i++) { X.applyItem(p, X.IT_BOMB); X.applyItem(p, X.IT_FIRE); X.applyItem(p, X.IT_SHOE); }
  eq(p.maxBombs, 13, '爆弾が上限で止まってない');
  eq(X.getPower(p), 13, '火力が上限で止まってない');
  eq(p.shoes, 13, '👟が上限で止まってない');
  ok(X.getSpeed(p) <= X.SPEED_MAX, '速度が SPEED_MAX を超えてる');
  // うんこ「爆風1マス」は上限に関係なく効くこと
  p.effects.weak = 5;
  eq(X.getPower(p), 1, 'うんこの爆風1マスが効いてない');
  return `💣13 🔥13 👟13 速度${X.getSpeed(p).toFixed(2)}`;
});

t('Space でラウンドを送っても初期位置に爆弾が置かれない（押下を持ち越さない）', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  p.isCPU = false; p.controls = X.CONTROLS.solo;
  q.isCPU = false; q.controls = X.CONTROLS.p2;
  // バナー送りの Space が押されたまま次ラウンドへ入る状況を作る
  X.keys.clear(); X.pressed.clear();
  X.keys.add('Space'); X.pressed.add('Space');
  X.startRound();
  eq(X.keys.size, 0, 'ラウンド開始時に押下状態が残ってる');
  eq(X.pressed.size, 0, 'ラウンド開始時に「押した瞬間」が残ってる');
  X.humanUpdate(X.players[0], 1 / 60);
  eq(X.bombs.length, 0, '初期位置に爆弾が置かれてしまった（詰む）');
  return 'ok';
});

t('倍速でも「押した瞬間」の入力は1回きり（うさぎが3マス跳ばない）', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.isCPU = false; p.controls = X.CONTROLS.solo;
  p.cx = 1.5; p.cy = 7.5; p.dir = 'right';
  X.keys.clear(); X.pressed.clear();
  // 3倍速の1フレーム＝3サブステップ。edge は最初のサブステップだけで消費されるべき
  X.keys.add('ShiftLeft'); X.pressed.add('ShiftLeft');
  for (let i = 0; i < 3; i++) { X.humanUpdate(p, 1 / 180); X.pressed.clear(); }
  X.keys.clear();
  eq(Math.floor(p.cx), 3, `1回の押しで跳ぶのは1回だけ（着地 ${Math.floor(p.cx)}）`);
  return '(1,7) → (3,7) の1回だけ';
});

t('盤面は画面サイズに合わせて拡大する（マス数は変えない）', () => {
  const cols = X.COLS, rows = X.ROWS;
  const sizes = [];
  for (const [w, h] of [[1280, 800], [1900, 1000], [2560, 1440], [700, 500]]) {
    global.window.innerWidth = w; global.window.innerHeight = h;
    X.fitBoard();
    sizes.push(`${w}×${h}→TILE${X.TILE}`);
    ok(X.TILE >= X.TILE_MIN && X.TILE <= X.TILE_MAX, `TILE が範囲外 (${X.TILE})`);
    eq(X.COLS, cols, 'マス数が変わってしまった');
    eq(X.ROWS, rows, 'マス数が変わってしまった');
    // 小さすぎる窓では TILE_MIN で下打ち切りするので、はみ出しは許す
    // （そこまで縮めると駒が見えない。サイドパネルは下へ回り込む）
    if (w >= 1100) {
      // サイドパネルが右に居られる幅を必ず残す（残さないと盤面の真下に回り込む）
      ok(X.CW + X.SIDE_W <= w,
         `サイドパネルの場所が残ってない (${X.CW}+${X.SIDE_W} > ${w})`);
      ok(X.CH <= h - 40, `canvas が縦にはみ出す (${X.CH} > ${h}-40)`);
    } else {
      eq(X.TILE, X.TILE_MIN, '小さい窓では下限に張り付くべき');
    }
  }
  // 画面が広いほど1マスが大きい
  global.window.innerWidth = 1280; global.window.innerHeight = 800; X.fitBoard();
  const small = X.TILE;
  global.window.innerWidth = 2560; global.window.innerHeight = 1440; X.fitBoard();
  ok(X.TILE > small, `大画面で大きくなってない (${small}→${X.TILE})`);
  // テストの他のケースに影響しないよう既定へ戻す
  global.window.innerWidth = 1280; global.window.innerHeight = 800; X.fitBoard();
  return sizes.join(' / ');
});

t('G.speed の既定は1倍', () => {
  fresh({ mode: 'vs' });
  eq(X.G.speed, 1, '初期のゲーム速度');
  return 'ok';
});

/* ============ 1.5 爆風の当たり判定がシビアすぎない ============ */
t('壊れるブロックに密着していても、隣のマスの爆風では死なない', () => {
  const [p, q] = fresh({ hp: 3, mode: 'vs', clear: true });
  q.state = 'OUT';
  // (3,1) にソフトブロック。p はその手前 (2,1) のタイル中心に立つ
  X.grid[1][3] = X.SOFT;
  p.cx = 2.5; p.cy = 1.5;
  const hp0 = p.hp;
  // (2,1) には爆風が来ないように、離れた (6,1) から火力3で (3,1) だけ焼く
  const b = X.spawnBomb(q, 6, 1);
  b.power = 3;                     // (5,1)(4,1)(3,1) まで → ブロックを壊して止まる
  b.timer = 0.001;
  p.invuln = 0;
  step(Math.ceil((X.BLAST_DUR + 0.2) * 60));
  ok(!X.blastSetHas || true, '');
  eq(p.hp, hp0, 'ブロックに密着してるだけで被弾してはいけない');
  eq(X.grid[1][3], X.EMPTY, 'ブロックは壊れてるべき（テストの前提確認）');
  return 'ok';
});

t('爆風マスの中心に立っていればちゃんと当たる（緩めすぎてない）', () => {
  const [p, q] = fresh({ hp: 3, mode: 'vs', clear: true });
  q.state = 'OUT';
  p.cx = 3.5; p.cy = 1.5;
  const hp0 = p.hp;
  const b = X.spawnBomb(q, 6, 1);
  b.power = 3;                     // (3,1) まで届く
  b.timer = 0.001;
  p.invuln = 0;
  step(Math.ceil((X.BLAST_DUR + 0.2) * 60));
  eq(p.hp, hp0 - 1, '爆風マスの中心に立ってたら1発もらうべき');
  return 'ok';
});

t('爆風の当たり判定は移動の当たり判定より小さい', () => {
  ok(X.BLAST_HITBOX < X.RADIUS,
     `BLAST_HITBOX(${X.BLAST_HITBOX}) が RADIUS(${X.RADIUS}) 以上になってる`);
  ok(X.BLAST_HITBOX <= 0.2, `まだシビアすぎる (${X.BLAST_HITBOX})`);
  return `hitbox ${X.BLAST_HITBOX} vs radius ${X.RADIUS}`;
});

/* ============ 2. きつね ============ */
t('きつねは初期から爆弾2個', () => {
  const [p] = fresh({ p1: 'fox' });
  eq(p.animal.key, 'fox', 'animal');
  eq(p.maxBombs, 2, 'きつねの初期 maxBombs');
  const [r] = fresh({ p1: 'rabbit' });
  eq(r.maxBombs, 1, 'ほかの動物の初期 maxBombs');
  return 'fox=2, others=1';
});

t('きつね：技ボタンで一列ドン設置（爆弾ボタンは1個置き）', () => {
  const [p, q] = fresh({ p1: 'fox' });
  q.state = 'OUT';
  p.cx = 1.5; p.cy = 1.5; p.dir = 'right';
  // 爆弾ボタンは普通の1個置き
  X.placeBomb(p);
  eq(X.bombs.length, 1, '爆弾ボタンは1個だけのはず');
  // 技ボタンで一列
  const [p2, q2] = fresh({ p1: 'fox' });
  q2.state = 'OUT';
  p2.cx = 1.5; p2.cy = 1.5; p2.dir = 'right';
  X.doAction(p2);
  eq(X.bombs.length, 2, '技ボタンで手持ち2個ぶん一列に置かれるべき');
  // 足元(1,1)ではなく 1マス前から並ぶ
  ok(!X.bombAt(1, 1), '足元に置かれてる（1マス前から並ぶはず）');
  ok(X.bombAt(2, 1) && X.bombAt(3, 1), '(2,1)と(3,1)に並ぶべき');
  return '爆弾ボタン=1個 / 技ボタン=1マス前から2個ドン';
});

t('きつね以外は1個だけ', () => {
  const [p, q] = fresh({ p1: 'rabbit' });
  q.state = 'OUT';
  p.cx = 1.5; p.cy = 1.5; p.dir = 'right';
  X.placeBomb(p);
  eq(X.bombs.length, 1, '通常キャラは1個');
  return 'ok';
});

t('きつね：アイテムで増えると一列も伸びる', () => {
  const [p, q] = fresh({ p1: 'fox' });
  q.state = 'OUT';
  X.applyItem(p, X.IT_BOMB); X.applyItem(p, X.IT_BOMB);
  eq(p.maxBombs, 4, 'アイテム2個ぶん増えた maxBombs');
  p.cx = 1.5; p.cy = 1.5; p.dir = 'right';
  X.doAction(p);
  eq(X.bombs.length, 4, '一列に置かれた数');
  return '4個ドン';
});

t('きつねの一列はブロックで止まる', () => {
  const [p, q] = fresh({ p1: 'fox', clear: true });
  q.state = 'OUT';
  X.applyItem(p, X.IT_BOMB); X.applyItem(p, X.IT_BOMB);  // maxBombs 4
  p.cx = 1.5; p.cy = 1.5; p.dir = 'right';
  X.grid[1][3] = X.SOFT;                    // 前から2マス目を塞ぐ
  X.doAction(p);
  eq(X.bombs.length, 1, '(2,1) だけ置いて (3,1) のブロックで止まるべき');
  ok(X.bombAt(2, 1), '(2,1) に無い');
  return '1個で停止';
});

t('きつね：真ん前が壁なら技ボタンでは置かない（足元は爆弾ボタンで置く）', () => {
  const [p, q] = fresh({ p1: 'fox', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  p.cx = 1.5; p.cy = 7.5; p.dir = 'right';
  X.grid[7][2] = X.SOFT;                    // 真ん前を塞ぐ
  X.doAction(p);                            // 技ボタン
  eq(X.bombs.length, 0, '前が壁なのに技ボタンで置かれた');
  X.placeBomb(p);                           // 爆弾ボタンなら足元に置ける
  eq(X.bombs.length, 1, '爆弾ボタンで足元に置けてない');
  ok(X.bombAt(1, 7), '足元に置かれてない');
  return '技=0個 / 爆弾ボタン=足元に1個';
});

/* ============ キツネ跳び ============ */
t('狐火：キツネ跳びで放たれ、1秒の無敵とシンクロする', () => {
  const [p, q] = fresh({ hp: 3, p1: 'fox', mode: 'vs' });
  p.cx = 1.5; p.cy = 1.5;
  q.cx = 9.5; q.cy = 1.5;                    // 敵は同じ行の先
  p.chicken = 'fox';
  X.useSpecial(p);
  ok(p.effects.foxLeap > 0, 'キツネ跳びが発動してない');
  eq(Math.round(p.effects.foxLeap * 10) / 10, X.FOX_LEAP, '滞空時間');
  eq(X.foxfires.length, 1, '狐火が出てない');
  ok(X.isUntouchable(p), '跳んでる間は無敵であるべき');
  return `狐火1発・滞空${X.FOX_LEAP}s`;
});

t('狐火は敵を追いかけて当てる', () => {
  const [p, q] = fresh({ hp: 2, p1: 'fox', mode: 'vs', clear: true });
  p.cx = 1.5; p.cy = 1.5;
  q.cx = 7.5; q.cy = 1.5;                    // 6マス先。2秒で届く距離
  q.invuln = 0;
  const hp0 = q.hp;
  p.chicken = 'fox';
  X.useSpecial(p);
  for (let i = 0; i < 150 && q.hp === hp0 && X.foxfires.length; i++) step(1);
  ok(q.hp < hp0, `狐火が敵に当たってない（hp ${hp0}→${q.hp}）`);
  return `hp ${hp0}→${q.hp}`;
});

t('狐火は自分には当たらない', () => {
  const [p, q] = fresh({ hp: 3, p1: 'fox', mode: 'vs', clear: true });
  p.cx = 5.5; p.cy = 5.5;
  q.cx = 9.5; q.cy = 5.5;
  const hp0 = p.hp;
  p.chicken = 'fox';
  X.useSpecial(p);
  for (let i = 0; i < 150; i++) step(1);
  eq(p.hp, hp0, '自分の狐火で自分がダメージを受けてはいけない');
  return 'ok';
});

t('狐火は設定した時間で消える', () => {
  const [p, q] = fresh({ hp: 9, p1: 'fox', mode: 'vs', clear: true });
  p.cx = 1.5; p.cy = 1.5;
  q.cx = 13.5; q.cy = 11.5; q.invuln = 999;  // 遠くて無敵＝当たらない
  p.chicken = 'fox';
  X.useSpecial(p);
  eq(X.foxfires.length, 1, '出てる');
  step(Math.ceil((X.FOXFIRE_LIFE - 0.2) * 60));
  eq(X.foxfires.length, 1, '寿命前はまだ残ってるべき');
  step(Math.ceil(0.4 * 60));
  eq(X.foxfires.length, 0, '寿命を超えたら消えるべき');
  return `寿命 ${X.FOXFIRE_LIFE}秒`;
});

t('狐火は爆弾を起爆しない（一斉起爆は廃止）', () => {
  const [p, q] = fresh({ hp: 3, p1: 'fox', mode: 'vs', clear: true });
  p.cx = 1.5; p.cy = 1.5;
  q.cx = 9.5; q.cy = 9.5;
  X.placeBomb(p);
  const n = X.bombs.length;
  ok(n >= 1, '爆弾が置かれた');
  p.chicken = 'fox';
  X.useSpecial(p);
  eq(X.bombs.length, n, '狐火で自分の爆弾が消えてはいけない');
  return `爆弾${n}個そのまま`;
});

t('狐火はとくぎ名も「狐火」になってる', () => {
  eq(X.SPECIALS.fox.name, '狐火', 'とくぎ名');
  return X.SPECIALS.fox.desc;
});

t('キツネ跳びが終わると無敵も切れる（1秒）', () => {
  const [p, q] = fresh({ hp: 3, p1: 'fox', mode: 'vs' });
  q.state = 'OUT';
  p.chicken = 'fox';
  X.useSpecial(p);
  ok(X.isUntouchable(p), '発動直後は無敵');
  step(Math.ceil((X.FOX_LEAP - 0.15) * 60));
  ok(X.isUntouchable(p), `${X.FOX_LEAP}秒たつ前に切れてる`);
  step(Math.ceil(0.3 * 60));
  ok(!p.effects.foxLeap, `${X.FOX_LEAP}秒後には切れてるべき`);
  ok(!X.isUntouchable(p), '無敵も切れてるべき');
  return 'ok';
});

t('キツネ跳び中は葱も当たらない', () => {
  const [a, b] = fresh({ hp: 3, p1: 'rabbit', p2: 'fox', mode: 'vs' });
  a.hp = 0; X.kill(a);
  a.negiT = 0;
  b.cx = 1.5; b.cy = 8.5; b.invuln = 0;
  b.chicken = 'fox';
  X.useSpecial(b);                           // 跳んで待つ
  a.negiCool = 0;
  X.fireNegi(a);
  for (let i = 0; i < 200 && X.negis.length; i++) step(1);
  eq(a.state, 'NEGIBON', 'キツネ跳び中に当たってはいけない');
  return 'ok';
});

/* ============ 先取（ラウンド）制 ============ */
t('ラウンドに勝つと★が増え、先取数に届いたら優勝', () => {
  Object.assign(X.CFG, { mode: 'vs', hpP1: 1, hpP2: 1, hpCPU: 1, time: 180, wins: 3, sudden: false,
                         sfx: false, bgm: false });
  X.CFG.pick.p1 = 'rabbit'; X.CFG.pick.p2 = 'frog';
  VT = 0;
  X.startGame();
  eq(X.G.round, 1, '最初のラウンド番号');
  const [a, b] = X.players;
  eq(a.score, 0, '初期スコア');

  const winRound = (loser) => {
    loser.invuln = 0; loser.hp = 1; X.hurt(loser);   // 相手を落とす
    X.checkEnd();
  };
  winRound(b);
  eq(a.score, 1, '1勝目');
  eq(X.G.phase, 'roundEnd', 'ラウンド終了フェーズ');
  ok(!X.G.champion, 'まだ優勝ではない');

  X.startRound();
  eq(X.G.round, 2, 'ラウンド2');
  eq(a.score, 1, 'スコアはラウンド間で持ち越す');
  eq(a.hp, a.maxHp, 'HPはリセットされる');
  eq(a.state, 'ALIVE', '生き返ってる');
  winRound(X.players[1]);
  eq(a.score, 2, '2勝目');

  X.startRound();
  winRound(X.players[1]);
  eq(a.score, 3, '3勝目');
  eq(X.G.phase, 'over', '優勝でマッチ終了');
  eq(X.G.champion, a, '優勝者');
  return `${a.animal.name} が3勝で優勝（${X.G.round}ラウンド）`;
});

t('やり直し機能は存在しない（R も確認ダイアログも無い）', () => {
  ok(typeof X.askRestart === 'undefined', 'askRestart が残ってる');
  ok(typeof X.closeRestart === 'undefined', 'closeRestart が残ってる');
  ok(!('confirming' in X.G) || !X.G.confirming, '確認状態が残ってる');
  return 'ok';
});

t('startRound は必ずラウンド番号を進める', () => {
  Object.assign(X.CFG, { mode: 'vs', hpP1: 1, hpP2: 1, hpCPU: 1, time: 180, wins: 5,
    sudden: false, sfx: false, bgm: false });
  VT = 0; X.startGame();
  eq(X.G.round, 1, '開始時のラウンド番号');
  X.startRound();
  eq(X.G.round, 2, '2ラウンド目');
  X.startRound(true);                     // 引数を渡しても素通り
  eq(X.G.round, 3, '3ラウンド目');
  return 'ROUND 1→2→3';
});

t('ラウンド間でパワーアップはリセットされる', () => {
  Object.assign(X.CFG, { mode: 'vs', hpP1: 2, hpP2: 2, hpCPU: 2, time: 180, wins: 5, sudden: false,
                         sfx: false, bgm: false });
  VT = 0; X.startGame();
  const [a, b] = X.players;
  X.applyItem(a, X.IT_BOMB); X.applyItem(a, X.IT_FIRE); X.applyItem(a, X.IT_SHOE);
  ok(a.maxBombs > 1 && a.powerUp > 0 && a.shoes > 0, '強化されてる');
  X.startRound();
  eq(a.maxBombs, 1 + (a.animal.bombBonus || 0), '爆弾数リセット');
  eq(a.powerUp, 0, '火力リセット');
  eq(a.shoes, 0, '靴リセット');
  return 'ok';
});

t('引き分けラウンドでは誰もスコアが増えない', () => {
  Object.assign(X.CFG, { mode: 'vs', hpP1: 1, hpP2: 1, hpCPU: 1, time: 180, wins: 3, sudden: false,
                         sfx: false, bgm: false });
  VT = 0; X.startGame();
  const [a, b] = X.players;
  X.G.time = 0;
  X.checkEnd();
  eq(a.score, 0, 'a のスコア');
  eq(b.score, 0, 'b のスコア');
  eq(X.G.phase, 'roundEnd', '次ラウンドへ進む');
  return 'ok';
});

/* ============ 3. 足元に置かれても詰まない ============ */
t('他人が自分の足元に爆弾を置いても動ける', () => {
  const [a, b] = fresh({ p1: 'rabbit', p2: 'frog' });
  a.cx = 3.5; a.cy = 1.5;
  b.cx = 3.5; b.cy = 1.5;               // 同じマスに重なる
  X.placeBomb(b, false);                // b が置く
  const bomb = X.bombAt(3, 1);
  ok(bomb, '爆弾が置かれた');
  ok(bomb.ignore.has(a.id), 'a も通れる扱いになってるべき（詰み防止）');
  ok(bomb.ignore.has(b.id), 'b も通れる扱い');
  ok(!X.collides(a, 3.5, 1.5), 'a がその場で詰まってない');
  // 実際に隣へ動けるか
  const before = a.cx;
  for (let i = 0; i < 30; i++) { VT += 16; X.update(1 / 60); }
  return `ignore=${[...bomb.ignore].join(',')}`;
});

t('きつねの一列が他人を貫いても、その他人は詰まない', () => {
  const [a, b] = fresh({ p1: 'fox', p2: 'frog' });
  X.applyItem(a, X.IT_BOMB);            // maxBombs 3
  a.cx = 1.5; a.cy = 1.5; a.dir = 'right';
  b.cx = 2.5; b.cy = 1.5;               // 一列の途中に立ってる
  X.doAction(a);
  const bomb = X.bombAt(2, 1);
  ok(bomb, '(2,1) に爆弾');
  ok(bomb.ignore.has(b.id), '巻き込まれた b が通れる扱いになってるべき');
  return 'ok';
});

t('爆弾から降りると固体化する', () => {
  const [p, q] = fresh({ p1: 'rabbit' });
  q.state = 'OUT';
  p.cx = 3.5; p.cy = 1.5;
  X.placeBomb(p, false);
  const bomb = X.bombAt(3, 1);
  ok(bomb.ignore.has(p.id), '置いた直後は通れる');
  p.cx = 5.5;                            // 完全に離れる
  step(2);
  ok(!bomb.ignore.has(p.id), '離れたら固体化すべき');
  ok(X.isSolidFor(p, 3, 1), '戻ろうとしても入れない');
  return 'ok';
});

/* ============ 4. うんこ ============ */
t('うんこは爆風で焼けずに吹き飛ぶ', () => {
  const [p, q] = fresh({ p1: 'rabbit' });
  q.state = 'OUT';
  X.items.length = 0;
  X.items.push({ x: 5, y: 1, kind: X.IT_POOP, born: 0 });
  // (3,1) で爆発、火力3 で (5,1) に届く
  p.cx = 3.5; p.cy = 1.5; p.powerUp = 3;
  const b = X.spawnBomb(p, 3, 1);
  b.timer = 0.001;
  step(3);
  const poop = X.items.find(i => i.kind === X.IT_POOP);
  ok(poop, 'うんこが焼けて消えてはいけない');
  ok(!(poop.x === 5 && poop.y === 1), `吹き飛んでいない (${poop.x},${poop.y})`);
  return `(5,1) → (${poop.x},${poop.y})`;
});

t('ふつうのアイテムは爆風で焦げて消える', () => {
  const [p, q] = fresh({ p1: 'rabbit' });
  q.state = 'OUT';
  X.items.length = 0;
  X.items.push({ x: 5, y: 1, kind: X.IT_BOMB, born: 0 });
  p.cx = 3.5; p.cy = 1.5; p.powerUp = 3;
  const b = X.spawnBomb(p, 3, 1);
  b.timer = 0.001;
  step(3);
  eq(X.items.length, 0, '焼却後のアイテム数');
  return 'ok';
});

t('うんこは15秒で消える', () => {
  // CPU が新しいアイテムを出すと数が変わるので、タイマン(操作なし=静止)で測る
  fresh({ mode: 'vs' });
  X.items.length = 0;
  const poop = { x: 5, y: 5, kind: X.IT_POOP, born: X.G.elapsed };
  X.items.push(poop);
  step(Math.ceil((X.POOP_LIFE - 1) * 60));
  ok(X.items.includes(poop), '14秒では残ってるべき');
  step(Math.ceil(2 * 60));
  ok(!X.items.includes(poop), '15秒超で消えるべき');
  return 'ok';
});

/* 2026-08-23 に「重ねがけしない（＝踏むたび上書き）」を捨てた。
   上書きだと何個踏んでも常に1効果ぶんのコストで頭打ちになり、
   CPU がうさぎのポロポロ（25マス）へ平然と突っ込んできた。 */
t('うんこは重ねがけできる（別の効果を消さない）', () => {
  const [p] = fresh();
  // どの効果が出るかはランダムなので、2種類引くまで踏ませる。
  // 上書きだった頃は何回踏んでもここが 1 のままだった
  for (let i = 0; i < 30; i++) X.applyItem(p, X.IT_POOP);
  const n = X.POOP_KEYS.filter(k => p.effects[k]).length;
  ok(n >= 2, `同時にかかってるうんこ効果の数が ${n} しかない`);
  return `${n}種類 同時にかかった`;
});

t('同じうんこ効果を重ねて踏むと時間が延びる（上限は元の3倍）', () => {
  const [p] = fresh();
  for (let i = 0; i < 60; i++) X.applyItem(p, X.IT_POOP);
  let extended = 0; const over = [];
  for (const k of X.POOP_KEYS) {
    const v = p.effects[k];
    if (v == null) continue;
    if (v > X.POOPS[k].sec + 1e-9) extended++;
    // 上限が無いとポロポロ25マスを踏み抜いた人が1分以上動けなくなる
    if (v > X.POOPS[k].sec * X.POOP_STACK_MAX + 1e-9) over.push(`${k}=${v.toFixed(1)}`);
  }
  ok(extended > 0, '60回踏んでも延びた効果が1つも無い');
  eq(over.length, 0, `上限(元の${X.POOP_STACK_MAX}倍)を超えた効果: ${over.join(' ')}`);
  return `延長 ${extended}種類 / 上限超え 0`;
});

/* 重ねがけを入れて初めて起きるようになった逆転のテスト。
   getSpeed の「とまれない」は Math.max で速度の下限を敷く効果なので、
   下限そのものに slow を掛けないと、超スローを踏んだ人が
   とまれないを踏んだ瞬間に**速くなる**（後のうんこが前のうんこを打ち消す）。 */
t('🚫爆弾おけない と 🎰勝手に設置 が重なったら「勝手に設置」が勝つ', () => {
  const [p] = fresh();
  p.effects.nobomb = 4;
  ok(!X.canPlaceBomb(p), 'nobomb だけなら置けないべき');
  p.effects.autobomb = 4;
  ok(X.canPlaceBomb(p), 'autobomb が重なったら置けるべき（勝手に設置が優先）');
  delete p.effects.autobomb;
  ok(!X.canPlaceBomb(p), 'autobomb が切れたら nobomb が効いて置けなくなるべき');
  return 'nobomb → +autobomb → autobomb切れ の順で 不可→可→不可';
});

t('とまれない中でも超スローは効く（後から踏んだうんこが前のを打ち消さない）', () => {
  const [p] = fresh();
  p.effects.runaway = 5;
  const fast = X.getSpeed(p);
  p.effects.slow = 5;
  const slowed = X.getSpeed(p);
  ok(slowed < fast, `超スローが効いていない: ${fast.toFixed(3)} → ${slowed.toFixed(3)}`);
  return `runaway ${fast.toFixed(2)} → +slow ${slowed.toFixed(2)}`;
});

/* ============ 4.5 被弾でパワーアップを吐き出す ============ */
t('爆風を喰らうたびにパワーアップを1つ近くに吐き出す', () => {
  const [p, q] = fresh({ hp: 4, mode: 'vs' });
  q.state = 'OUT';
  X.items.length = 0;
  p.cx = 5.5; p.cy = 5.5;
  p.invuln = 0; X.hurt(p);
  eq(X.items.length, 1, '1回目の被弾で吐き出された数');
  const it = X.items[0];
  ok(X.POWERUPS ? X.POWERUPS.includes(it.kind) : ['bomb', 'fire', 'shoe'].includes(it.kind),
     `吐き出されたのがパワーアップでない (${it.kind})`);
  const dist = Math.abs(it.x - 5) + Math.abs(it.y - 5);
  ok(dist <= 2, `近くに出てない (${it.x},${it.y})`);
  p.invuln = 0; X.hurt(p);
  eq(X.items.length, 2, '2回目の被弾でも吐き出すべき');
  return `${it.kind} @(${it.x},${it.y})`;
});

t('吐き出したアイテムは他人も拾える', () => {
  const [p, q] = fresh({ hp: 4, mode: 'vs' });
  X.items.length = 0;
  p.cx = 5.5; p.cy = 5.5;
  p.invuln = 0; X.hurt(p);
  const it = X.items[0];
  const before = q.maxBombs + q.powerUp + q.shoes;
  q.cx = it.x + 0.5; q.cy = it.y + 0.5;
  X.pickupCheck(q);
  const after = q.maxBombs + q.powerUp + q.shoes;
  eq(after, before + (q.animal.itemMul || 1), '拾って強化されるべき');
  eq(X.items.length, 0, 'アイテムは消える');
  return 'ok';
});

/* ============ 4.6 葱の防ぎ方 ============ */
t('葱は爆風にふれると焼き切れる', () => {
  const [a, b] = fresh({ hp: 3, mode: 'vs' });
  a.hp = 0; X.kill(a);
  a.negiT = 0;                        // 内部 x=1 の列を下向き
  b.cx = 1.5; b.cy = 4.5;
  a.negiCool = 0;
  X.fireNegi(a);
  eq(X.negis.length, 1, '葱が出た');
  // 葱の進路上 (1,4) で爆発させる
  b.invuln = 99;                      // b は死なないようにする
  const bomb = X.spawnBomb(b, 1, 3);
  bomb.timer = 0.001;
  step(3);
  ok(X.blasts.length > 0, '爆風が出てる');
  for (let i = 0; i < 200 && X.negis.length; i++) step(1);
  eq(X.negis.length, 0, '葱が消えるべき');
  eq(a.state, 'NEGIBON', '爆風で焼かれたので復活してはいけない');
  return 'ok';
});

t('葱は爆弾に当たって弾かれる（爆弾が盾になる）', () => {
  const [a, b] = fresh({ hp: 3, mode: 'vs' });
  a.hp = 0; X.kill(a);
  a.negiT = 0;
  b.cx = 1.5; b.cy = 4.5;
  // 進路上 (1,3) に爆弾を置いて盾にする
  const bomb = X.spawnBomb(b, 1, 3);
  bomb.timer = 99;                    // 爆発させない
  a.negiCool = 0;
  X.fireNegi(a);
  for (let i = 0; i < 200 && X.negis.length; i++) step(1);
  eq(X.negis.length, 0, '葱は弾かれて消えるべき');
  eq(a.state, 'NEGIBON', '盾で防いだので復活してはいけない');
  eq(b.state, 'ALIVE', 'b は無傷');
  ok(X.bombAt(1, 3), '盾になった爆弾は残る');
  return 'ok';
});

t('盾が無ければ葱は通る（対照）', () => {
  const [a, b] = fresh({ hp: 3, mode: 'vs' });
  a.hp = 0; X.kill(a);
  a.negiT = 0;
  b.cx = 1.5; b.cy = 4.5; b.invuln = 0;
  a.negiCool = 0;
  X.fireNegi(a);
  for (let i = 0; i < 200 && a.state === 'NEGIBON'; i++) step(1);
  eq(a.state, 'ALIVE', '何も無ければ当たって復活すべき');
  return 'ok';
});

/* ============ 5. アイテム効果 ============ */
t('バナナで滑る／たまねぎで止まる', () => {
  const [p] = fresh();
  X.applyItem(p, X.IT_BANANA);
  ok(p.effects.slide > 0, 'slide が付く');
  X.applyItem(p, X.IT_ONION);
  ok(p.effects.stun > 0, 'stun が付く');
  ok(!p.effects.slide, 'たまねぎで滑りは打ち消される');
  return 'ok';
});

t('チキンでとくぎが使える（かえるだけは とくぎ無し）', () => {
  const log = [];
  for (const key of ['rabbit', 'elephant', 'mole', 'fox']) {
    const [p] = fresh({ p1: key });
    X.applyItem(p, X.IT_CHICKEN);
    eq(p.chicken, key, `${key}: chicken セット`);
    const uses = X.ANIMALS[key].itemMul || 1;
    eq(p.chickenCharges, uses, `${key}: 使える回数`);
    for (let i = 0; i < uses; i++) {
      ok(p.chicken === key, `${key}: ${i + 1}回目が使えるべき`);
      X.useSpecial(p);
    }
    eq(p.chicken, null, `${key}: 使い切ったら消える`);
    log.push(`${key}=${X.SPECIALS[key].name}`);
  }
  return log.join(' ');
});

t('かえるのとくぎは粘膜爆弾。アイテム2倍なので🍗1個で2回ぶん', () => {
  const [f] = fresh({ p1: 'frog' });
  ok(!X.ANIMALS.frog.noSpecial, 'noSpecial が残ってる（かえるにもとくぎが付いた）');
  ok(X.SPECIALS.frog, 'かえるのとくぎ定義が無い');
  eq(X.SPECIALS.frog.name, '粘膜爆弾', 'とくぎ名');
  X.applyItem(f, X.IT_CHICKEN);
  eq(f.chicken, 'frog', 'チキンでとくぎが付いてない');
  eq(f.chickenCharges, 2, 'アイテム2倍なので2回ぶん持てるはず');
  // ポン押しは通常技（舌）のまま
  X.doAction(f);
  ok(f.tongue, 'ポン押しでは舌が出るべき');
  eq(f.chicken, 'frog', 'ポン押しでとくぎを消費してはいけない');
  return 'ok';
});

t('粘膜爆弾：3マス先へ飛んで、6〜8回 跳ねてから爆発する', () => {
  const [f, q] = fresh({ p1: 'frog', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5; q.invuln = 999;
  f.cx = 3.5; f.cy = 7.5; f.dir = 'right'; f.invuln = 999;
  const act0 = f.activeBombs;
  f.chicken = 'frog'; f.chickenCharges = 1;
  X.doSpecial(f);
  eq(X.slimes.length, 1, '粘膜爆弾が出てない');
  eq(X.slimes[0].x, 6, '3マス先 (6,7) に飛ぶべき');
  const hops = X.slimes[0].hopsLeft;
  ok(hops >= 6 && hops <= 8, `跳ねる回数が範囲外 (${hops})`);
  // 爆発までの時間は 跳ね回数×間隔 + 飛行時間 の範囲に収まる
  let t = 0;
  const cap = Math.ceil((X.SLIME_FLY + 8 * X.SLIME_HOP_MAX + 0.5) * 60);
  for (let i = 0; i < cap && X.slimes.length; i++) { step(1); t += 1 / 60; }
  eq(X.slimes.length, 0, '爆発してない');
  ok(t >= X.SLIME_FLY + 6 * X.SLIME_HOP_MIN - 0.1, `早すぎる (${t.toFixed(2)}s)`);
  ok(t <= X.SLIME_FLY + 8 * X.SLIME_HOP_MAX + 0.2, `遅すぎる (${t.toFixed(2)}s)`);
  // 手持ちの爆弾数は消費しない（とくぎなので）
  step(Math.ceil((X.BLAST_DUR + 0.3) * 60));
  eq(f.activeBombs, act0, `手持ちの爆弾数が戻ってない (${f.activeBombs})`);
  return `${hops}回跳ねて ${t.toFixed(2)}秒で爆発`;
});

t('粘膜爆弾：2マスずつ 縦横斜めに跳ぶ／柱の上にも載る／盤面の外へは出ない', () => {
  const [f, q] = fresh({ p1: 'frog', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5; q.invuln = 999;
  eq(X.SLIME_HOP_DIST, 2, '1回で跳ぶマス数');
  eq(X.SLIME_DIRS.length, 8, '縦横斜めの8方向');
  f.cx = 3.5; f.cy = 7.5; f.dir = 'right'; f.invuln = 999;
  f.chicken = 'frog'; f.chickenCharges = 1;
  X.doSpecial(f);
  step(Math.ceil((X.SLIME_FLY + 0.02) * 60));
  const sl = X.slimes[0];
  ok(sl, '飛行が終わってない');
  let hops = 0, onPillar = 0;
  let prev = { x: sl.x, y: sl.y };
  for (let i = 0; i < 60 * 6 && X.slimes.length; i++) {
    step(1);
    if (!X.slimes.length) break;
    const cur = X.slimes[0];
    if (cur.x !== prev.x || cur.y !== prev.y) {
      const dx = Math.abs(cur.x - prev.x), dy = Math.abs(cur.y - prev.y);
      ok((dx === 2 || dx === 0) && (dy === 2 || dy === 0) && (dx + dy > 0),
         `跳び方が 2マス単位の8方向になってない (${dx},${dy})`);
      ok(cur.x >= 1 && cur.y >= 1 && cur.x <= X.COLS - 2 && cur.y <= X.ROWS - 2,
         `盤面の外（葱ボンレーン）へ出た (${cur.x},${cur.y})`);
      if (X.grid[cur.y][cur.x] === X.HARD) onPillar++;
      hops++;
      prev = { x: cur.x, y: cur.y };
    }
  }
  ok(hops >= 4, `跳んだ回数が少なすぎる (${hops})`);
  return `${hops}回跳んだ（うち柱の上 ${onPillar}回）`;
});

t('粘膜爆弾：柱の上で爆発する時は隣へ転がって、火力ぶん燃える', () => {
  const [f, q] = fresh({ p1: 'frog', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5; q.invuln = 999;
  f.cx = 3.5; f.cy = 7.5; f.invuln = 999;
  X.applyItem(f, X.IT_FIRE);                       // かえるは2倍
  const pw = X.getPower(f);
  eq(X.grid[8][8], X.HARD, '前提: (8,8) は柱');
  // 柱の上に居る粘膜爆弾を手で作って爆発させる
  X.slimeBurst({ x: 8, y: 8, owner: f.id, phase: 'hop' });
  const bomb = X.bombs.find(b => b.slime);
  ok(bomb, '柱の上で不発になった（転がってない）');
  ok(X.grid[bomb.y][bomb.x] === X.EMPTY, '爆弾が柱の上に置かれてる');
  eq(bomb.power, pw, '火力が反映されてない');
  ok(Math.abs(bomb.x - 8) <= 1 && Math.abs(bomb.y - 8) <= 1, '遠くへ飛びすぎ');
  return `(8,8)→(${bomb.x},${bomb.y}) 火力${pw}`;
});

t('粘膜爆弾：爆風にふれると即爆発する', () => {
  const [f, q] = fresh({ p1: 'frog', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5; q.invuln = 999;
  f.cx = 3.5; f.cy = 7.5; f.dir = 'right'; f.invuln = 999;
  f.chicken = 'frog'; f.chickenCharges = 1;
  X.doSpecial(f);
  step(Math.ceil((X.SLIME_FLY + 0.05) * 60));
  eq(X.slimes.length, 1, '飛行が終わってない');
  const sl = X.slimes[0];
  const b = X.spawnBomb(q, sl.x, sl.y === 7 ? 7 : sl.y);
  // 同じマスに置けない場合は隣に置いて爆風を被せる
  b.timer = 0.001;
  step(4);
  eq(X.slimes.length, 0, '爆風にふれても爆発してない');
  return 'ok';
});

t('粘膜爆弾の火力は爆発する時の火力ぶん', () => {
  const [f, q] = fresh({ p1: 'frog', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5; q.invuln = 999;
  f.cx = 3.5; f.cy = 7.5; f.dir = 'right'; f.invuln = 999;
  X.applyItem(f, X.IT_FIRE);              // かえるは2倍なので +2
  const pw = X.getPower(f);
  ok(pw >= 3, `前提: 火力が上がってる (${pw})`);
  f.chicken = 'frog'; f.chickenCharges = 1;
  X.doSpecial(f);
  const sl = X.slimes.pop();               // 自前で爆発させて、爆弾になった瞬間を見る
  const act0 = f.activeBombs;
  X.slimeBurst(sl);
  const bomb = X.bombs.find(b => b.slime);
  ok(bomb, '爆弾になってない');
  eq(bomb.power, pw, '火力が反映されてない');
  eq(f.activeBombs, act0, '手持ちの爆弾数を消費してしまってる');
  return `火力${pw}`;
});

t('うんこポロポロ：5×5＝25マスを、2秒かけて足元から輪ごとに埋める', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.cx = 11.5; p.cy = 7.5;                   // 盤面の真ん中
  X.items.length = 0;
  X.applyItem(p, X.IT_CHICKEN);
  X.useSpecial(p);
  eq(X.PORO_RANGE, 2, '中心からの距離（5×5 なので2）');
  eq(X.PORO_TIME, 2.0, '展開にかかる時間');
  eq(X.items.length, 0, '発動した瞬間はまだ1個も出てないべき（足元から徐々に）');
  eq(X.poroporos.length, 1, '展開が始まってない');
  ok(p.effects.poro > 0, 'ブリブリのモーションが付いてない');

  // 足元 → 1周目 → 2周目 の3段。1段あたり PORO_TIME/3 秒
  const per = X.PORO_TIME / (X.PORO_RANGE + 1);
  step(Math.ceil((per * 0.5) * 60));
  ok(X.itemAt(11, 7), '足元 (11,7) が出てない');
  ok(!X.itemAt(11, 6), '1周目がもう出てしまってる（一気に置いてる）');

  step(Math.ceil(per * 60));
  ok(X.itemAt(11, 6), '1周目の (11,6) が出てない');
  ok(!X.itemAt(13, 9), '2周目がもう出てしまってる（一気に置いてる）');

  // 展開しきるまで
  step(Math.ceil((X.PORO_TIME + 0.2) * 60));
  eq(X.poroporos.length, 0, '展開が終わってない');
  ok(X.itemAt(13, 9), '角 (13,9) が出てない ← 十字のままになってる');
  ok(!X.itemAt(14, 7), '5×5 の外（3マス先）まで出てしまってる');
  ok(!X.itemAt(11, 4), '5×5 の外（3マス先）まで出てしまってる');

  let n = 0, holes = 0;
  for (let dy = -X.PORO_RANGE; dy <= X.PORO_RANGE; dy++)
    for (let dx = -X.PORO_RANGE; dx <= X.PORO_RANGE; dx++) {
      const x = 11 + dx, y = 7 + dy;
      if (X.grid[y][x] !== X.EMPTY) { holes++; continue; }   // 柱は飛ばす
      const it = X.itemAt(x, y);
      ok(it && it.kind === X.IT_POOP, `(${x},${y}) にうんこが無い`);
      ok(it.poro, `(${x},${y}) がポロポロ扱いになってない`);
      eq(it.owner, p.id, `(${x},${y}) の撒いた本人が違う`);
      n++;
    }
  eq(n + holes, 25, `5×5 の25マスを見てない (${n + holes})`);
  ok(n >= 18, `面で埋まってない (${n}マス)`);
  // 25マスを超えて撒いてないこと
  eq(X.items.filter(it => it.poro).length, n, '25マスの外にも撒いてる');
  eq(p.chicken, null, 'とくぎを消費すべき');
  ok(!p.effects.poro, 'モーションが終わってない');
  return `${n}マス埋めた（柱で不可 ${holes}／計25マス）`;
});

t('うんこポロポロ 1回の占有率は盤面の空きマスの15%以下（広すぎ検出）', () => {
  // ★ この検査が無かったせいで 11×11(距離5) 版が「異常なし」で通ってしまった（2026-08-06）。
  //   sim の平均値は CPU が滅多に撒かないので薄まって見えない。1回の面積を直に測る。
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  let open = 0;
  for (let y = 1; y < X.ROWS - 1; y++) for (let x = 1; x < X.COLS - 1; x++)
    if (X.grid[y][x] === X.EMPTY) open++;
  p.cx = 11.5; p.cy = 7.5;
  X.items.length = 0;
  X.applyItem(p, X.IT_CHICKEN);
  X.useSpecial(p);
  step(Math.ceil((X.PORO_TIME + 0.3) * 60));
  const placed = X.items.filter(it => it.poro).length;
  const share = placed / open;
  ok(share <= 0.15,
     `1回で空きマスの${(share * 100).toFixed(0)}%（${placed}/${open}マス）を埋めてる → 広すぎる`);
  return `${placed}/${open}マス = ${(share * 100).toFixed(0)}%`;
});

t('うんこポロポロ：撒いた本人は踏んでも発動しない・盤面からも消えない', () => {
  const [p, q] = fresh({ p1: 'rabbit', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  p.cx = 11.5; p.cy = 7.5;
  X.items.length = 0;
  X.items.push({ x: 12, y: 7, kind: X.IT_POOP, born: X.G.elapsed, poro: true, owner: p.id });
  // 本人が乗る
  p.cx = 12.5;
  X.pickupCheck(p);
  ok(X.itemAt(12, 7), '本人が踏んだら消えてしまった（自分の壁が崩れる）');
  ok(!X.POOP_KEYS.some(k => p.effects[k]), '本人に効果が出てしまった');
  // 他のヤツが乗ると発動する
  q.cx = 12.5; q.cy = 7.5;
  X.pickupCheck(q);
  ok(!X.itemAt(12, 7), '他のヤツが踏んでも消えない');
  ok(X.POOP_KEYS.some(k => q.effects[k]), '他のヤツに効果が出てない');
  return 'ok';
});

t('うんこポロポロ：爆風で消えない・吹き飛ばない', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  p.cx = 1.5; p.cy = 1.5; p.invuln = 99;
  X.items.length = 0;
  X.items.push({ x: 2, y: 1, kind: X.IT_POOP, born: X.G.elapsed, poro: true, owner: p.id });
  const b = X.spawnBomb(p, 1, 1);
  b.timer = 0.001;
  step(Math.ceil((X.BLAST_DUR + 0.2) * 60));
  const it = X.itemAt(2, 1);
  ok(it && it.poro, '爆風で消えた（または吹き飛んだ）');
  return '(2,1) のまま残る';
});

t('うんこポロポロ：60秒で消える（ふつうのうんこは15秒）', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  p.cx = 1.5; p.cy = 1.5;
  eq(X.PORO_LIFE, 60, '寿命');
  X.items.length = 0;
  X.items.push({ x: 9, y: 9, kind: X.IT_POOP, born: X.G.elapsed });                    // ふつうの
  X.items.push({ x: 9, y: 11, kind: X.IT_POOP, born: X.G.elapsed, poro: true, owner: p.id });
  step(Math.ceil((X.POOP_LIFE + 1) * 60));
  ok(!X.itemAt(9, 9), 'ふつうのうんこが15秒で消えてない');
  ok(X.itemAt(9, 11), 'ポロポロが15秒で消えてしまった');
  step(Math.ceil((X.PORO_LIFE - X.POOP_LIFE + 1) * 60));
  ok(!X.itemAt(9, 11), `${X.PORO_LIFE}秒たっても消えてない`);
  return `${X.POOP_LIFE}秒→残る / ${X.PORO_LIFE}秒→消える`;
});

t('うさぎは自分のうんこの上を跳び越えて動ける', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.cx = 11.5; p.cy = 7.5; p.dir = 'right';
  X.items.length = 0;
  X.applyItem(p, X.IT_CHICKEN);
  X.useSpecial(p);
  step(Math.ceil((X.PORO_TIME + 0.2) * 60));
  ok(X.itemAt(12, 7), '1マス目にうんこが無い（前提が崩れてる）');
  X.doAction(p);                              // 跳ぶ＝2マス先へ
  eq(Math.floor(p.cx), 13, 'うんこを跳び越えて (13,7) へ行くべき');
  ok(X.itemAt(13, 7), '2マス目にもうんこがあるのが正しい（連続なので）');
  X.pickupCheck(p);
  ok(X.itemAt(13, 7), '自分のうんこなので着地しても消えないべき');
  return 'ok';
});

t('狐火は寿命1.5秒・1マス0.17秒（前より遅く・短く）', () => {
  eq(X.FOXFIRE_LIFE, 1.5, '追尾時間');
  eq(X.FOXFIRE_STEP, 0.17, '1マスあたりの秒数');
  const [p, q] = fresh({ p1: 'fox', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  p.cx = 1.5; p.cy = 1.5;
  X.castFoxfire(p);
  eq(X.foxfires.length, 1, '狐火が出てない');
  eq(X.foxfires[0].life, X.FOXFIRE_LIFE, '寿命が設定と違う');
  step(Math.ceil((X.FOXFIRE_LIFE + 0.2) * 60));
  eq(X.foxfires.length, 0, `${X.FOXFIRE_LIFE}秒を過ぎても消えてない`);
  return `寿命${X.FOXFIRE_LIFE}s / ${X.FOXFIRE_STEP}s per tile = 最大${Math.floor(X.FOXFIRE_LIFE/X.FOXFIRE_STEP)}マス`;
});

t('狐火はブロックを回り込んで進む（貫通しない）', () => {
  const [p, q] = fresh({ hp: 2, p1: 'fox', mode: 'vs', clear: true });
  p.cx = 1.5; p.cy = 1.5;
  q.cx = 5.5; q.cy = 1.5; q.invuln = 0;
  // 間を縦に塞ぐ（(3,1) は柱ではないので SOFT を置ける）
  X.grid[1][3] = X.SOFT;
  const hp0 = q.hp;
  p.chicken = 'fox';
  X.useSpecial(p);
  for (let i = 0; i < 150 && X.foxfires.length; i++) {
    step(1);
    for (const f of X.foxfires) {
      eq(X.grid[f.y][f.x], X.EMPTY, `狐火がブロック(${f.x},${f.y})の上に乗ってる`);
    }
  }
  return 'ブロックの上を通らない';
});

/* ============ 動物の能力入れ替え（うさぎ跳躍 / かえる舌 / もぐら潜り） ============ */
t('跳躍はうさぎに移り、かえるからは無くなった', () => {
  ok(X.ANIMALS.rabbit.jump, 'うさぎが跳べない');
  ok(!X.ANIMALS.frog.jump, 'かえるがまだ跳べる');
  ok(X.ANIMALS.frog.tongue, 'かえるに舌が無い');
  eq(X.ANIMALS.frog.itemMul, 2, 'かえるのアイテム倍率');
  eq(X.SPECIALS.mole.name, '落とし穴', 'もぐらのとくぎ名');
  ok(X.ANIMALS.mole.pit, 'もぐらに落とし穴フラグが無い');
  ok(!X.ANIMALS.mole.burrow, '潜伏システムは廃止されてるべき');
  return 'ok';
});

t('うさぎはブロックを1マス跳び越える', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs' });
  q.state = 'OUT';
  p.cx = 1.5; p.cy = 1.5; p.dir = 'right';
  X.grid[1][2] = X.SOFT;                    // 隣を塞ぐ
  X.doAction(p);                            // とくぎボタン＝跳ぶ
  eq(Math.floor(p.cx), 3, 'ブロックを越えて (3,1) に着地すべき');
  return 'ok';
});

/* --- 技ボタン1つで 通常技 と とくぎ を分ける（ポン押し / 長押し） --- */
t('うさぎ：とくぎを持ってても ポン押しでは跳ぶだけ（とくぎを消費しない）', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs' });
  q.state = 'OUT';
  p.cx = 1.5; p.cy = 1.5; p.dir = 'right';
  X.applyItem(p, X.IT_CHICKEN);
  ok(p.chicken === 'rabbit', 'チキンを拾えてない');
  X.items.length = 0;
  X.doAction(p);
  eq(Math.floor(p.cx), 3, '跳んで前方へ移動すべき（空いてれば2マス先）');
  eq(p.chicken, 'rabbit', 'ポン押しでとくぎを消費してはいけない');
  eq(X.poroporos.length, 0, 'ポン押しでうんこポロポロが始まってはいけない');
  return 'ok';
});

t('うさぎ：技ボタンを長押しすると とくぎが出る（キーは増やさない）', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.isCPU = false; p.controls = X.CONTROLS.solo;
  p.cx = 11.5; p.cy = 7.5;
  X.applyItem(p, X.IT_CHICKEN);
  X.items.length = 0;
  X.keys.clear(); X.pressed.clear();
  /* ⛔ 何も押していない1フレームを挟む。v4.0.0 から resetPlayersForRound が
     actFired=true で始める（技ボタンを押したままバナーを送っても とくぎが
     暴発しない仕様）ので、これが無いと「離す」機会が無いまま長押しに入り、
     何秒押しても とくぎが出ない。実プレイでは指を離すので起きない */
  X.humanUpdate(p, 1 / 60);
  // 押した瞬間（edge）＝通常技。ここでは とくぎは出ない
  X.keys.add('ShiftLeft'); X.pressed.add('ShiftLeft');
  X.humanUpdate(p, 1 / 60);
  X.pressed.clear();
  eq(p.chicken, 'rabbit', '押した瞬間に とくぎが出てしまった');
  // 押し続ける
  let t = 0;
  for (let i = 0; i < 120 && p.chicken; i++) { X.humanUpdate(p, 1 / 60); t += 1 / 60; }
  X.keys.clear();
  eq(p.chicken, null, `長押ししても とくぎが出ない (${t.toFixed(2)}s)`);
  ok(t >= X.SPECIAL_HOLD - 0.05, `${X.SPECIAL_HOLD}秒より早く出てしまった (${t.toFixed(2)}s)`);
  eq(X.poroporos.length, 1, 'うんこポロポロが始まってない');
  step(Math.ceil((X.PORO_TIME + 0.2) * 60));
  ok(X.items.some(it => it.poro), 'うんこが1個も出てない');
  return `${t.toFixed(2)}秒 長押しで発動`;
});

t('技ボタンを離すと長押しがリセットされる（2回目も必要秒数だけ待つ）', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.isCPU = false; p.controls = X.CONTROLS.solo;
  X.keys.clear(); X.pressed.clear();
  X.keys.add('ShiftLeft');
  for (let i = 0; i < 15; i++) X.humanUpdate(p, 1 / 60);   // 0.25秒だけ押す
  ok(p.actHold > 0.15, 'たまってない');
  X.keys.clear();
  X.humanUpdate(p, 1 / 60);
  eq(p.actHold, 0, '離してもリセットされてない');
  eq(p.actFired, false, 'actFired が残ってる');
  return 'ok';
});

t('ぞう：ポン押しは鼻水（とくぎを消費しない）', () => {
  const [p, q] = fresh({ p1: 'elephant', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  p.cx = 5.5; p.cy = 7.5; p.dir = 'right';
  X.applyItem(p, X.IT_CHICKEN);
  const b = X.spawnBomb(q, 7, 7);          // 正面2マス先の爆弾
  b.timer = 99;
  X.doAction(p);
  eq(p.chicken, 'elephant', 'ポン押しで とくぎを消費してはいけない');
  ok(!p.effects.charge, 'ポン押しで突進が出てはいけない');
  ok(!X.bombAt(7, 7), '鼻水で爆弾の火が消えてない');
  ok(p.snotCool > 0, 'リロードが入ってない');
  return 'ok';
});

t('ぞうの鼻水：うんこを流して消す（うさぎのポロポロは流せない）', () => {
  const [e, r] = fresh({ p1: 'elephant', p2: 'rabbit', mode: 'vs', clear: true });
  r.cx = 19.5; r.cy = 13.5;
  e.cx = 3.5; e.cy = 7.5; e.dir = 'right';
  X.items.length = 0;
  X.items.push({ x: 4, y: 7, kind: X.IT_POOP, born: X.G.elapsed });                      // ふつう
  X.items.push({ x: 5, y: 7, kind: X.IT_POOP, born: X.G.elapsed, poro: true, owner: r.id }); // ポロポロ
  X.doAction(e);
  const ord = X.itemAt(4, 7), poro = X.itemAt(5, 7);
  ok(ord && ord.melt != null, 'ふつうのうんこが流されてない');
  ok(poro && poro.melt == null, 'うさぎのポロポロが流されてしまった');
  // 溶けきると消える
  step(Math.ceil((X.SNOT_MELT + 0.1) * 60));
  ok(!X.itemAt(4, 7), 'ふつうのうんこが消えてない');
  ok(X.itemAt(5, 7), 'ポロポロが消えてしまった');
  return 'ふつう=流れる / ポロポロ=残る';
});

t('ぞうの鼻水：溶けかけのうんこは踏んでも効かない', () => {
  const [e, r] = fresh({ p1: 'elephant', p2: 'rabbit', mode: 'vs', clear: true });
  r.cx = 19.5; r.cy = 13.5;
  e.cx = 3.5; e.cy = 7.5; e.dir = 'right';
  X.items.length = 0;
  X.items.push({ x: 4, y: 7, kind: X.IT_POOP, born: X.G.elapsed });
  X.doAction(e);
  e.cx = 4.5;                                   // 流れてる最中に踏む
  X.pickupCheck(e);
  ok(!X.POOP_KEYS.some(k => e.effects[k]), '溶けかけを踏んで効果が出てしまった');
  ok(X.itemAt(4, 7), '踏んで消えてしまった');
  return 'ok';
});

t('ぞうの鼻水：リロード中は出ない', () => {
  const [e, r] = fresh({ p1: 'elephant', p2: 'rabbit', mode: 'vs', clear: true });
  r.cx = 19.5; r.cy = 13.5;
  e.cx = 3.5; e.cy = 7.5; e.dir = 'right';
  eq(X.SNOT_COOL, 5, 'リロード秒数');
  X.doAction(e);
  ok(e.snotCool > 4.9, 'リロードが入ってない');
  X.items.length = 0;
  X.items.push({ x: 4, y: 7, kind: X.IT_POOP, born: X.G.elapsed });
  X.doAction(e);                                 // リロード中
  ok(X.itemAt(4, 7).melt == null, 'リロード中なのに鼻水が出た');
  return 'ok';
});

t('もぐら：通常技が無いのでポン押しで とくぎ（落とし穴）が出る', () => {
  const [p, q] = fresh({ p1: 'mole', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.cx = 5.5; p.cy = 5.5;
  X.applyItem(p, X.IT_CHICKEN);
  X.doAction(p);
  eq(p.chicken, null, 'ポン押しで とくぎが出るべき');
  ok(p.digging, '穴掘りが始まってない');
  return 'ok';
});

t('ぞう：長押しでも とくぎが出る', () => {
  const [p, q] = fresh({ p1: 'elephant', mode: 'vs' });
  q.state = 'OUT';
  p.cx = 5.5; p.cy = 5.5;
  X.applyItem(p, X.IT_CHICKEN);
  X.doSpecial(p);
  eq(p.chicken, null, '長押し経路で とくぎが出るべき');
  ok(p.effects.charge > 0, '突進が始まってない');
  return 'ok';
});

t('かえる：とくぎ扱いのフラグが立ってても ポン押しでは舌が出る', () => {
  const [p, f] = fresh({ p1: 'rabbit', p2: 'frog', mode: 'vs' });
  p.state = 'OUT';
  f.cx = 1.5; f.cy = 1.5; f.dir = 'right';
  f.chicken = 'frog'; f.chickenCharges = 1;   // 本来は拾えないが、取り合いが無いことの確認
  X.doAction(f);
  ok(f.tongue, '舌が出てない（とくぎに取られた）');
  eq(f.chicken, 'frog', 'ポン押しでとくぎを消費してはいけない');
  return 'ok';
});

t('1台のキーボードで手がぶつからない配置（1P=左側 / 2P=右側）', () => {
  // ⛔ 1P を右側・2P を左側へ動かすような作り替えはしない。
  //    1つのキーボードで2人が同時に触るので、物理的に手がぶつかる（2026-08-08 に一度やって戻した）
  const LEFTSIDE = new Set(['KeyQ','KeyW','KeyE','KeyR','KeyT','KeyA','KeyS','KeyD','KeyF','KeyG',
                            'KeyZ','KeyX','KeyC','KeyV','KeyB','ShiftLeft','AltLeft','Tab','Space']);
  const RIGHTSIDE = new Set(['KeyY','KeyU','KeyI','KeyO','KeyP','KeyH','KeyJ','KeyK','KeyL',
                             'KeyN','KeyM','Comma','Period','Slash','ShiftRight','AltRight','Enter',
                             'ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space']);
  const p1 = [].concat(X.CONTROLS.p1.up, X.CONTROLS.p1.down, X.CONTROLS.p1.left,
                       X.CONTROLS.p1.right, X.CONTROLS.p1.bomb, X.CONTROLS.p1.act);
  const p2 = [].concat(X.CONTROLS.p2.up, X.CONTROLS.p2.down, X.CONTROLS.p2.left,
                       X.CONTROLS.p2.right, X.CONTROLS.p2.bomb, X.CONTROLS.p2.act);
  const bad1 = p1.filter(k => !LEFTSIDE.has(k));
  const bad2 = p2.filter(k => !RIGHTSIDE.has(k));
  eq(bad1.length, 0, `1P に右側のキーが混ざってる: ${bad1.join(',')}`);
  eq(bad2.length, 0, `2P に左側のキーが混ざってる: ${bad2.join(',')}`);

  // 爆弾は左右に1つずつ。移動をどちらの手でやっても もう片方で押せる
  ok(X.CONTROLS.p1.bomb.includes('Space'), '1P の爆弾に Space が無い');
  ok(X.CONTROLS.p1.bomb.includes('KeyZ'), '1P の爆弾に Z が無い');
  ok(X.CONTROLS.p2.bomb.includes('Enter'), '2P の爆弾に Enter が無い');
  ok(X.CONTROLS.p2.bomb.includes('Slash'), '2P の爆弾に /（め）が無い');

  // ⛔ command はどの枠にも割り当てない。option は主キーにしない
  for (const slot of ['solo','p1','p2']){
    const c=X.CONTROLS[slot];
    ok(!c.act.some(k=>/^Meta/.test(k)), `${slot} に command を割り当ててはいけない`);
    ok(!/^Alt/.test(c.act[0]), `${slot} の技キーの主が option になってる`);
    ok(!c.sp, `${slot} に とくぎ専用キーが復活してる`);
  }
  // 1P と 2P で同じキーを取り合わない／枠の中で移動と爆弾・技が衝突しない
  const dup = p1.filter(k => p2.includes(k));
  eq(dup.length, 0, `1P と 2P でキーが衝突: ${dup.join(',')}`);
  for (const slot of ['solo','p1','p2']){
    const c=X.CONTROLS[slot];
    const mv=[].concat(c.up,c.down,c.left,c.right);
    const d2=[].concat(c.bomb,c.act).filter(k=>mv.includes(k));
    eq(d2.length, 0, `${slot} で移動キーと爆弾/技が衝突: ${d2.join(',')}`);
  }
  return `1P爆弾=${X.CONTROLS.p1.bomb.join('/')} 2P爆弾=${X.CONTROLS.p2.bomb.join('/')}`;
});

t('葱ボン中は 押したキーの向きへ動く（辺で上下左右が逆にならない）', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  p.isCPU = false; p.controls = X.CONTROLS.solo;
  X.toNegibon(p);
  eq(p.state, 'NEGIBON', '葱ボンになってない');

  /** 指定した辺のまん中に立たせて、キーを押し、画面上どちらへ動いたかを返す */
  const tryMove = (side, key) => {
    // その辺に入る t を探す
    let t0 = 0;
    for (let t = 0; t < 200; t += 0.5) {
      if (X.negiPos(t).side === side) { t0 = t + 3; break; }
    }
    p.negiT = t0;
    const before = X.negiPos(p.negiT);
    X.keys.clear(); X.pressed.clear();
    X.keys.add(key);
    for (let i = 0; i < 20; i++) X.humanUpdate(p, 1 / 60);
    X.keys.clear();
    const after = X.negiPos(p.negiT);
    return { dx: after.x - before.x, dy: after.y - before.y, side: before.side };
  };

  // 上辺：→ で右へ、← で左へ
  ok(tryMove('top', 'ArrowRight').dx > 0.1, '上辺で → を押したら右へ動くべき');
  ok(tryMove('top', 'ArrowLeft').dx < -0.1, '上辺で ← を押したら左へ動くべき');
  // 下辺：ここが逆になっていた（t が増えると左へ進む辺）
  ok(tryMove('bottom', 'ArrowRight').dx > 0.1, '下辺で → を押したら右へ動くべき（逆になってる）');
  ok(tryMove('bottom', 'ArrowLeft').dx < -0.1, '下辺で ← を押したら左へ動くべき');
  // 右辺：↓ で下へ
  ok(tryMove('right', 'ArrowDown').dy > 0.1, '右辺で ↓ を押したら下へ動くべき');
  ok(tryMove('right', 'ArrowUp').dy < -0.1, '右辺で ↑ を押したら上へ動くべき');
  // 左辺：ここも逆になっていた
  ok(tryMove('left', 'ArrowDown').dy > 0.1, '左辺で ↓ を押したら下へ動くべき（逆になってる）');
  ok(tryMove('left', 'ArrowUp').dy < -0.1, '左辺で ↑ を押したら上へ動くべき');
  return '4辺すべてで キーの向き＝画面の向き';
});

t('葱ボンは外周レーンの中に収まる（canvas からはみ出さない）', () => {
  // ±0.5 だと絵の半分が canvas の外へ出て切れていた
  fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  const half = 0.30;                       // 鍋の絵のだいたいの半径（タイル）
  for (let t = 0; t < 200; t += 1) {
    const pos = X.negiPos(t);
    const cx = X.LANE + pos.x, cy = X.LANE + pos.y;      // canvas 左上からのタイル数
    const w = X.COLS + X.LANE * 2, h = X.ROWS + X.LANE * 2;
    ok(cx - half >= -0.02 && cx + half <= w + 0.02, `t=${t} で横にはみ出す (${cx.toFixed(2)})`);
    ok(cy - half >= -0.02 && cy + half <= h + 0.02, `t=${t} で縦にはみ出す (${cy.toFixed(2)})`);
  }
  return 'ok';
});

t('操作ヒントに「長押しでとくぎ」が出る', () => {
  for (const slot of ['solo', 'p1', 'p2']) {
    ok(/長押し/.test(X.KEYHINT[slot]), `${slot} のヒントに 長押しが無い`);
    ok(/とくぎ/.test(X.KEYHINT[slot]), `${slot} のヒントに とくぎが無い`);
  }
  eq(X.skillLabelOf({ animal: X.ANIMALS.rabbit }), 'とぶ', 'うさぎの技 見出し');
  eq(X.skillLabelOf({ animal: X.ANIMALS.frog }), 'した', 'かえるの技 見出し');
  eq(X.skillLabelOf({ animal: X.ANIMALS.elephant }), 'はなみず', 'ぞうの技 見出し');
  eq(X.skillLabelOf({ animal: X.ANIMALS.fox }), 'ドン置き', 'きつねの技 見出し');
  eq(X.skillLabelOf({ animal: X.ANIMALS.mole }), 'とくぎ🍗', 'もぐらの技 見出し');
  return 'ok';
});

t('かえるのアイテム効果は2倍（良いのも悪いのも）', () => {
  const [f] = fresh({ p1: 'frog', mode: 'vs' });
  const b0 = f.maxBombs;
  X.applyItem(f, X.IT_BOMB);
  eq(f.maxBombs, b0 + 2, '爆弾+1 が +2 になるべき');
  X.applyItem(f, X.IT_FIRE);
  eq(f.powerUp, 2, '火力');
  X.applyItem(f, X.IT_ONION);
  eq(f.effects.stun, 6, 'たまねぎの拘束も2倍（3→6秒）');
  // 対照
  const [r] = fresh({ p1: 'rabbit', mode: 'vs' });
  X.applyItem(r, X.IT_BOMB);
  eq(r.maxBombs, 2, 'ほかの動物は等倍');
  return 'ok';
});

t('かえるの舌：良アイテムを掴んで自分のマスまで運ぶ', () => {
  const [f, q] = fresh({ p1: 'frog', mode: 'vs' });
  q.state = 'OUT';
  X.items.length = 0;
  f.cx = 1.5; f.cy = 1.5; f.dir = 'right';
  X.items.push({ x: 4, y: 1, kind: X.IT_FIRE, born: 0 });   // 3マス先
  const pw0 = f.powerUp;
  X.doAction(f);
  ok(f.tongue, '舌が出てない');
  // 3マス伸ばして3マス戻る = 0.6秒ぶん
  for (let i = 0; i < 80 && f.tongue; i++) step(1);
  ok(!f.tongue, '舌が戻ってない');
  eq(f.powerUp, pw0 + 2, '運んだアイテムが2倍で適用されるべき');
  eq(X.items.length, 0, '盤面からは消える');
  return 'ok';
});

t('かえるの舌：うんこも食う（悪いアイテムも掴む）', () => {
  const [f, q] = fresh({ p1: 'frog', mode: 'vs' });
  q.state = 'OUT';
  X.items.length = 0;
  f.cx = 1.5; f.cy = 1.5; f.dir = 'right';
  X.items.push({ x: 3, y: 1, kind: X.IT_POOP, born: 0 });   // 手前にうんこ
  X.items.push({ x: 5, y: 1, kind: X.IT_BOMB, born: 0 });   // その先に良いの
  const b0 = f.maxBombs;
  X.doAction(f);
  for (let i = 0; i < 120 && f.tongue; i++) step(1);
  ok(!X.itemAt(3, 1), 'うんこを食ってない（貫通してしまった）');
  ok(X.POOP_KEYS.some(k => f.effects[k]), 'うんこの効果が付いてない');
  eq(f.maxBombs, b0, '手前のうんこで止まるので、その先は取らないべき');
  ok(X.itemAt(5, 1), '先の良アイテムは残るべき');
  return 'うんこで打ち止め';
});

t('かえるの舌は最長10マス届く（0.125秒/マス）', () => {
  const [f, q] = fresh({ p1: 'frog', mode: 'vs', clear: true });
  q.state = 'OUT';
  eq(X.TONGUE_MAX, 10, '舌の上限');
  eq(X.TONGUE_STEP, 0.125, '1マスあたりの秒数');
  X.items.length = 0;
  f.cx = 1.5; f.cy = 7.5; f.dir = 'right';
  // 奇数行なので (2..11, 7) は柱にならない。10マス先にアイテムを置く
  eq(X.grid[7][11], X.EMPTY, '前提: (11,7) は空きマス');
  X.items.push({ x: 11, y: 7, kind: X.IT_FIRE, born: 0 });
  const pw0 = f.powerUp;
  X.doAction(f);
  for (let i = 0; i < 300 && f.tongue; i++) step(1);
  eq(f.powerUp, pw0 + 2, '10マス先が取れてない');
  return '10マス先を回収';
});

t('舌を出してる間は動けない・爆弾も置けない', () => {
  const [f, q] = fresh({ p1: 'frog', mode: 'vs' });
  q.state = 'OUT';
  f.cx = 5.5; f.cy = 5.5; f.dir = 'right';
  X.doAction(f);
  const x0 = f.cx;
  X.movePlayer(f, 0, 1, 0.2);
  eq(f.cx, x0, '動いてしまった');
  ok(!X.canPlaceBomb(f), '爆弾が置ける状態になってる');
  return 'ok';
});

t('落とし穴：1.5秒かけて掘って仕掛かる', () => {
  const [m, q] = fresh({ hp: 3, p1: 'mole', mode: 'vs', clear: true });
  q.state = 'OUT';
  m.cx = 5.5; m.cy = 5.5;
  m.chicken = 'mole'; m.chickenCharges = 1;
  eq(X.pits.length, 0, '最初は穴なし');
  X.doAction(m);
  ok(m.digging, '掘り始めてない');
  eq(X.pits.length, 0, '掘ってる途中はまだ仕掛かってない');
  ok(X.isBusy(m), '掘ってる間は操作を受け付けないべき');
  ok(!X.canPlaceBomb(m), '掘ってる間は爆弾を置けないべき');
  step(Math.ceil((X.PIT_DIG + 0.1) * 60));
  ok(!m.digging, '掘り終わってない');
  eq(X.pits.length, 1, '穴が仕掛かってない');
  eq(X.pits[0].x, 5, '穴の位置x');
  eq(X.pits[0].y, 5, '穴の位置y');
  return `${X.PIT_DIG}秒で仕掛かる`;
});

t('落とし穴：もぐら以外が踏むと5秒動けない', () => {
  const [m, r] = fresh({ hp: 3, p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  X.pits.length = 0;
  X.pits.push({ x: 7, y: 7, owner: m.id });
  r.cx = 7.5; r.cy = 7.5;
  step(2);
  ok(r.effects.pitfall > 0, 'うさぎが落ちてない');
  eq(Math.round(r.effects.pitfall), X.PIT_HOLD, '拘束時間');
  ok(X.isFrozen(r), '拘束中は動けないべき');
  ok(!X.canPlaceBomb(r), '拘束中は爆弾も置けないべき');
  eq(X.pits.length, 0, '踏まれた穴は埋まるべき');
  // 実際に動けない
  const x0 = r.cx;
  X.movePlayer(r, 1, 0, 0.3);
  eq(r.cx, x0, '拘束中に動けてしまった');
  // 5秒後に復帰
  step(Math.ceil((X.PIT_HOLD + 0.2) * 60));
  ok(!r.effects.pitfall, '拘束が解けてない');
  ok(!X.isFrozen(r), '動ける状態に戻るべき');
  return `${X.PIT_HOLD}秒拘束 → 復帰`;
});

t('落とし穴：もぐらは自分の穴でも他人の穴でも落ちない', () => {
  const [m, m2] = fresh({ hp: 3, p1: 'mole', p2: 'mole', mode: 'vs', clear: true });
  X.pits.length = 0;
  X.pits.push({ x: 7, y: 7, owner: m2.id });     // 相手のもぐらが掘った穴
  m.cx = 7.5; m.cy = 7.5;
  step(4);
  ok(!m.effects.pitfall, 'もぐらが落ちてしまった');
  eq(X.pits.length, 1, 'もぐらが通っても穴は残るべき');
  return 'ok';
});

t('落とし穴は CPU にも見えていない（避けるチートをしてない）', () => {
  const [m, r] = fresh({ p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  X.pits.length = 0;
  X.pits.push({ x: 7, y: 7, owner: m.id });
  // 経路探索が穴のマスを「通れる」扱いにしてる＝避けない
  ok(X.walkableFor(r, 7, 7), 'CPU の経路探索が穴を避けてしまってる');
  // 危険マップにも入ってない
  const d = X.dangerMap();
  eq(d[7][7], Infinity, '危険マップに穴が載ってる＝CPUに見えてる');
  return 'CPU は穴を避けない';
});

t('CPU は落とし穴を実際に踏む', () => {
  const [m, r] = fresh({ p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  r.isCPU = true;                                  // うさぎを CPU にする
  X.pits.length = 0;
  // うさぎの進路になりそうな範囲に穴を敷き詰めて、踏むかどうかを見る
  for (let y = 1; y <= X.ROWS - 2; y++)
    for (let x = 1; x <= X.COLS - 2; x++)
      if (X.grid[y][x] === X.EMPTY) X.pits.push({ x, y, owner: m.id });
  const n0 = X.pits.length;
  ok(n0 > 20, '穴を敷けてる');
  let fell = false;
  for (let i = 0; i < 600 && !fell; i++) { step(1); if (r.effects.pitfall) fell = true; }
  ok(fell, 'CPU が穴を踏まずに歩き回ってる＝穴が見えてる疑い');
  ok(X.pits.length < n0, '踏んだ穴が埋まってない');
  return `CPU が踏んだ（残り穴 ${X.pits.length}/${n0}）`;
});

t('落とし穴は設置数の上限なし', () => {
  const [m, q] = fresh({ hp: 3, p1: 'mole', mode: 'vs', clear: true });
  q.state = 'OUT';
  X.pits.length = 0;
  for (let i = 0; i < 6; i++) {
    m.cx = 1.5 + i * 2; m.cy = 3.5;
    m.chicken = 'mole'; m.chickenCharges = 1;
    X.doAction(m);
    step(Math.ceil((X.PIT_DIG + 0.1) * 60));
  }
  eq(X.pits.length, 6, '6個仕掛けられるべき');
  return '6個';
});

t('落とし穴は爆風では無敵にならない（潜伏は廃止）', () => {
  const [m, q] = fresh({ hp: 2, p1: 'mole', mode: 'vs', clear: true });
  m.cx = 5.5; m.cy = 5.5;
  m.chicken = 'mole'; m.chickenCharges = 1;
  X.doAction(m);
  ok(m.digging, '掘ってる');
  ok(!X.isBlastProof(m), '掘ってる間に無敵になってはいけない');
  const hp0 = m.hp;
  const b = X.spawnBomb(q, 5, 5);
  b.timer = 0.001;
  m.invuln = 0;
  step(Math.ceil((X.BLAST_DUR + 0.2) * 60));
  ok(m.hp < hp0, '掘ってる間も爆風は喰らうべき');
  return `hp ${hp0}→${m.hp}`;
});

t('拘束中のプレイヤーは爆風を喰らう（無敵ではない）', () => {
  const [m, r] = fresh({ hp: 3, p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  X.pits.length = 0;
  X.pits.push({ x: 7, y: 7, owner: m.id });
  r.cx = 7.5; r.cy = 7.5; r.invuln = 0;
  step(2);
  ok(r.effects.pitfall > 0, '落ちてる');
  const hp0 = r.hp;
  const b = X.spawnBomb(m, 7, 7);
  b.timer = 0.001;
  r.invuln = 0;
  step(Math.ceil((X.BLAST_DUR + 0.2) * 60));
  ok(r.hp < hp0, '穴にはまってる間も爆風は当たるべき');
  return `hp ${hp0}→${r.hp}`;
});

/* ============ 舌の焼き切れ（爆風でそのラウンド中 短くなる） ============ */
t('舌が爆風に触れると焼き切れて、そのラウンド中は手前までしか伸びない', () => {
  const [f, q] = fresh({ p1: 'frog', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  eq(X.tongueReach(f), X.TONGUE_MAX, '最初は上限いっぱい');
  X.items.length = 0;
  f.cx = 1.5; f.cy = 7.5; f.dir = 'right'; f.invuln = 99;
  X.doAction(f);
  // 4マス目まで伸ばす
  for (let i = 0; i < 200 && (f.tongue ? f.tongue.len : 0) < 4; i++) step(1);
  eq(f.tongue.len, 4, '4マスまで伸びてない');
  // 3マス目に爆風を出す（q の爆弾・火力1なので隣接だけ焼ける）
  const b = X.spawnBomb(q, 4, 7);
  b.timer = 0.001;
  step(3);
  ok(!f.tongue, '舌が引っ込んでない');
  ok(X.tongueReach(f) < X.TONGUE_MAX, `焼き切れてない (${X.tongueReach(f)})`);
  ok(f.effects.stun > 0, 'スタンしてない');
  eq(Math.round(f.effects.stun), X.TONGUE_BURN_STUN, 'スタン秒数');
  eq(X.TONGUE_BURN_STUN, 3, 'スタンは3秒');
  return `${X.TONGUE_MAX}マス → ${X.tongueReach(f)}マス`;
});

t('焼き切れは一番手前のマスで決まる（奥だけ見て長いままにしない）', () => {
  const [f, q] = fresh({ p1: 'frog', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  f.cx = 1.5; f.cy = 7.5; f.dir = 'right'; f.invuln = 99;
  X.items.length = 0;
  // (1,7) から右へ 8マス伸ばした舌。爆弾は (4,7) と (8,7)。
  // 火力1なので焼けるのは (3,7)=2マス目 と (7,7)=6マス目。
  // 採られるべきは手前の 2マス目 → 上限は 1マス
  f.tongue = { dx: 1, dy: 0, len: 8, phase: 'out', t: 0, item: null, ox: 1, oy: 7 };
  const b1 = X.spawnBomb(q, 4, 7); b1.timer = 0.001;
  const b2 = X.spawnBomb(q, 8, 7); b2.timer = 0.001;
  step(3);
  eq(X.tongueReach(f), 1, `手前(2マス目)基準になってない (${X.tongueReach(f)})`);
  return '2マス目で焼けたので上限1マス';
});

t('焼き切れた舌は10秒ごとに1マス回復する', () => {
  const [f, q] = fresh({ p1: 'frog', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  eq(X.TONGUE_REGEN, 10, '回復間隔');
  f.tongueLimit = 3; f.tongueRegen = X.TONGUE_REGEN;
  step(Math.ceil((X.TONGUE_REGEN - 1) * 60));
  eq(X.tongueReach(f), 3, '早く回復しすぎ');
  step(Math.ceil(2 * 60));
  eq(X.tongueReach(f), 4, '30秒たっても回復してない');
  return '3 → 4マス';
});

t('焼き切れはラウンドが変わるとリセットされる', () => {
  const [f] = fresh({ p1: 'frog', mode: 'vs', clear: true });
  f.tongueLimit = 2;
  eq(X.tongueReach(f), 2, '前提: 短くなってる');
  X.startRound();
  eq(X.tongueReach(X.players[0]), X.TONGUE_MAX, 'ラウンドをまたいで短いままになってる');
  return 'ok';
});

t('サドンデスでも焼き切れはリセットされる', () => {
  const ps = fresh({ p1: 'frog', hp: 3, time: 180, sudden: true, clear: false });
  ps[0].tongueLimit = 1;
  X.G.time = 0;
  X.checkEnd();
  eq(X.tongueReach(ps[0]), X.TONGUE_MAX, 'サドンデスで戻ってない');
  return 'ok';
});

t('根元まで焼けたら舌は出せない', () => {
  const [f, q] = fresh({ p1: 'frog', mode: 'vs', clear: true });
  q.state = 'OUT';
  f.tongueLimit = 0; f.cx = 5.5; f.cy = 5.5;
  X.doAction(f);
  ok(!f.tongue, '上限0なのに舌が出た');
  return 'ok';
});

/* ============ ぞうのとくぎ：突進（2026-08-04 に4案から確定） ============ */
function eleSetup(opts = {}) {
  Object.assign(X.CFG, { mode: 'vs', hpP1: opts.hp ?? 3, hpP2: opts.hp ?? 3, hpCPU: 3,
    time: 180, wins: 3, sudden: false, sfx: false, bgm: false });
  X.CFG.pick.p1 = 'elephant'; X.CFG.pick.p2 = opts.p2 || 'rabbit';
  VT = 0; X.startGame();
  for (let y = 1; y < X.ROWS - 1; y++) for (let x = 1; x < X.COLS - 1; x++)
    if (X.grid[y][x] === X.SOFT) X.grid[y][x] = X.EMPTY;
  return X.players;
}

t('🐗突進：無敵で直進し、ブロックを踏み潰す', () => {
  const [e, r] = eleSetup();
  r.state = 'OUT';
  e.cx = 1.5; e.cy = 1.5; e.dir = 'right';
  X.grid[1][3] = X.SOFT; X.grid[1][4] = X.SOFT; X.grid[1][5] = X.SOFT;
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  ok(e.effects.charge > 0, '突進が始まってない');
  ok(X.isUntouchable(e), '突進中は無敵であるべき');
  ok(!X.canPlaceBomb(e), '突進中は爆弾を置けないべき');
  const x0 = e.cx;
  step(Math.ceil(2.2 * 60));
  ok(e.cx > x0 + 3, `進んでない (${x0.toFixed(2)}→${e.cx.toFixed(2)})`);
  eq(X.grid[1][3], X.EMPTY, 'ブロックを踏み潰してない');
  eq(X.grid[1][4], X.EMPTY, '2枚目を踏み潰してない');
  ok(!e.effects.charge, '突進が終わってない');
  return `x ${x0.toFixed(1)}→${e.cx.toFixed(1)}・ブロック踏み潰し`;
});

t('🐗突進：ぶつかった敵にダメージ＋吹き飛ばし', () => {
  const [e, r] = eleSetup({ hp: 3 });
  e.cx = 1.5; e.cy = 1.5; e.dir = 'right';
  r.cx = 5.5; r.cy = 1.5; r.invuln = 0;
  const hp0 = r.hp, rx0 = r.cx;
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  step(Math.ceil(2.2 * 60));
  ok(r.hp < hp0, `敵にダメージが入ってない (hp ${hp0}→${r.hp})`);
  ok(r.cx > rx0, `敵が吹き飛んでない (${rx0.toFixed(2)}→${r.cx.toFixed(2)})`);
  return `hp ${hp0}→${r.hp}・${rx0.toFixed(1)}→${r.cx.toFixed(1)} へ押し出し`;
});

/* ============ 突進のアイテム処理（2026-08-06 の報告） ============ */
t('突進：通り道の良アイテムは吸い込む', () => {
  const [e, r] = eleSetup();
  r.state = 'OUT';
  e.cx = 1.5; e.cy = 7.5; e.dir = 'right';
  X.items.length = 0;
  X.items.push({ x: 4, y: 7, kind: X.IT_FIRE, born: 0 });
  X.items.push({ x: 6, y: 7, kind: X.IT_BOMB, born: 0 });
  const pw0 = e.powerUp, b0 = e.maxBombs;
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  step(Math.ceil(2.2 * 60));
  eq(e.powerUp, pw0 + 1, '🔥を吸い込んでない');
  eq(e.maxBombs, b0 + 1, '💣を吸い込んでない');
  ok(!X.itemAt(4, 7) && !X.itemAt(6, 7), '盤面から消えてない');
  return '🔥💣 両方吸い込み';
});

t('突進：たまねぎを踏んでも止まらない（作者の報告）', () => {
  const [e, r] = eleSetup();
  r.state = 'OUT';
  e.cx = 1.5; e.cy = 7.5; e.dir = 'right';
  X.items.length = 0;
  X.items.push({ x: 3, y: 7, kind: X.IT_ONION, born: 0 });
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  const x0 = e.cx;
  step(Math.ceil(1.0 * 60));
  ok(!e.effects.stun, 'たまねぎで泣いてしまった');
  ok(e.cx > x0 + 4, `突進が止まった (${x0.toFixed(1)}→${e.cx.toFixed(1)})`);
  return `${x0.toFixed(1)}→${e.cx.toFixed(1)} まで進んだ`;
});

t('突進：抱えたハズレは ぶつかった敵に全部ぶつける', () => {
  const [e, r] = eleSetup({ hp: 3 });
  e.cx = 1.5; e.cy = 7.5; e.dir = 'right';
  r.cx = 9.5; r.cy = 7.5; r.invuln = 0;
  X.items.length = 0;
  X.items.push({ x: 3, y: 7, kind: X.IT_ONION, born: 0 });
  X.items.push({ x: 5, y: 7, kind: X.IT_BANANA, born: 0 });
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  step(Math.ceil(2.2 * 60));
  ok(r.effects.stun || r.effects.slide || r.hp < 3,
     'ぶつけた側に何も起きてない');
  eq((e.chargeCarry || []).length, 0, '抱えたままになってる');
  return 'ok';
});

t('突進：敵に当たらなければ止まった所の左右にハズレを撒く', () => {
  const [e, r] = eleSetup();
  r.state = 'OUT';
  e.cx = 1.5; e.cy = 7.5; e.dir = 'right';
  X.items.length = 0;
  X.items.push({ x: 3, y: 7, kind: X.IT_ONION, born: 0 });
  X.items.push({ x: 5, y: 7, kind: X.IT_POOP, born: 0 });
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  step(Math.ceil(2.6 * 60));
  eq((e.chargeCarry || []).length, 0, '抱えたままになってる');
  const bad = X.items.filter(it => X.ITEM_DEF[it.kind].bad);
  ok(bad.length >= 1, 'ハズレが撒かれてない');
  // 進行方向は横だったので、撒かれるのは縦（左右＝直交方向）
  const ex = Math.floor(e.cx);
  ok(bad.every(it => it.x === ex || Math.abs(it.y - Math.floor(e.cy)) >= 1),
     '進行方向にそのまま残ってる');
  return `${bad.length}個 撒いた`;
});

t('突進：もぐらの落とし穴にはハマって止まる', () => {
  const [e, m] = fresh({ p1: 'elephant', p2: 'mole', mode: 'vs', clear: true });
  e.cx = 1.5; e.cy = 7.5; e.dir = 'right';
  m.cx = 19.5; m.cy = 13.5;
  X.pits.length = 0;
  X.pits.push({ x: 5, y: 7, owner: m.id });
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  ok(e.effects.charge > 0, '突進が始まってない');
  step(Math.ceil(1.2 * 60));
  ok(e.effects.pitfall > 0, '落とし穴にハマってない（無敵ですり抜けた）');
  ok(!e.effects.charge, '突進が止まってない');
  return `(${Math.floor(e.cx)},${Math.floor(e.cy)}) で停止`;
});

t('突進中はハイパーアーマー：ダメージは0.5だけ入り、突進は止まらない', () => {
  const [e, q] = fresh({ p1: 'elephant', p2: 'rabbit', mode: 'vs', hp: 3, clear: true });
  q.cx = 19.5; q.cy = 13.5;
  e.cx = 3.5; e.cy = 7.5; e.dir = 'right'; e.invuln = 0;
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  ok(e.effects.charge > 0, '突進が始まってない');
  ok(!X.isBlastProof(e), '突進中が「爆風が当たらない」扱いになってる（ハイパーアーマーのはず）');
  ok(X.isUntouchable(e), '突進中は葱・激突は避けられるべき');
  const hp0 = e.hp, x0 = e.cx;
  X.items.length = 0;
  // 進路に爆弾を置いて、突っ込ませる
  const b = X.spawnBomb(q, 8, 7);
  b.timer = 99;
  for (let i = 0; i < 60 && X.bombAt(8, 7); i++) step(1);
  ok(!X.bombAt(8, 7), '突っ込んでも爆弾が起爆してない');
  step(6);
  eq(e.hp, hp0 - X.CHARGE_ARMOR, `ダメージが 0.5 じゃない (${hp0}→${e.hp})`);
  ok(e.effects.charge > 0, '爆風を受けて突進が止まってしまった');
  ok(e.cx > x0 + 3, `突進が進んでない (${x0.toFixed(1)}→${e.cx.toFixed(1)})`);
  ok(X.items.some(it => X.ITEM_DEF[it.kind].power), 'パワーアップが吐き出されてない');
  return `hp ${hp0}→${e.hp} で走り続ける`;
});

t('突進中は葱には当たらない（葱だけは無敵のまま）', () => {
  const [e, q] = fresh({ p1: 'elephant', p2: 'rabbit', mode: 'vs', hp: 3, clear: true });
  e.cx = 5.5; e.cy = 7.5; e.invuln = 0;
  q.cx = 19.5; q.cy = 13.5;
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  ok(X.isUntouchable(e), '突進中が「葱が当たらない」扱いになってない');
  const hp0 = e.hp;
  X.toNegibon(q);
  q.negiCool = 0;
  X.negis.length = 0;
  X.negis.push({ x: e.cx - 1, y: e.cy, vx: 6, vy: 0, owner: q.id });
  for (let i = 0; i < 30; i++) X.updateNegis(1 / 60);
  eq(e.hp, hp0, '突進中に葱でダメージを受けた');
  return 'ok';
});

t('突進の上限は5秒（ぞう同士がぶつかっても必ず止まる）', () => {
  eq(X.CHARGE_TIME, 5, '突進の上限秒数');
  const [e, q] = fresh({ p1: 'elephant', p2: 'rabbit', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  e.cx = 3.5; e.cy = 7.5; e.dir = 'right';
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  step(Math.ceil((X.CHARGE_TIME + 0.3) * 60));
  ok(!e.effects.charge, `${X.CHARGE_TIME}秒たっても突進が終わってない`);
  return `${X.CHARGE_TIME}秒で必ず終わる`;
});

t('突進中でも狐火は当たる（0.5だけ）', () => {
  const [e, f] = fresh({ p1: 'elephant', p2: 'fox', mode: 'vs', hp: 3, clear: true });
  e.cx = 5.5; e.cy = 7.5; e.dir = 'right'; e.invuln = 0;
  f.cx = 19.5; f.cy = 13.5;
  e.chicken = 'elephant'; e.chickenCharges = 1;
  X.doSpecial(e);
  const hp0 = e.hp;
  X.castFoxfire(f);
  X.foxfires[0].x = Math.floor(e.cx); X.foxfires[0].y = Math.floor(e.cy);
  X.updateFoxfires(1 / 60);
  eq(e.hp, hp0 - X.CHARGE_ARMOR, `狐火のダメージが 0.5 じゃない (${hp0}→${e.hp})`);
  return 'ok';
});

t('HP に 0.5 が出ても ❤️ 表示が壊れない', () => {
  const [p] = fresh({ hp: 3, mode: 'vs' });
  eq(X.heartsOf(p), '❤️❤️❤️', 'HP満タンの表示');
  p.hp = 2.5;
  eq(X.heartsOf(p), '❤️❤️💔', '半端が 💔 で出てない');
  p.hp = 0.5;
  eq(X.heartsOf(p), '💔🖤🖤', 'HP0.5 の表示');
  return 'ok';
});

/* ============ きつねCPU が置き場を探して往復する問題 ============ */
t('きつね：一列は足元ではなく1マス前から並ぶ（後ろへ下がって逃げられる）', () => {
  const [f, q] = fresh({ p1: 'fox', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  f.cx = 1.5; f.cy = 7.5; f.dir = 'right';
  f.maxBombs = 8; f.powerUp = X.POWER_MAX;
  // 満載＋火力MAX でも、足元が空くので後ろへ下がって逃げられる
  ok(X.canEscapeAfterBomb(f, 1, 7, 8), '満載だと逃げ切れない判定になってる（足元に置いてない？）');
  X.doAction(f);
  ok(!X.bombAt(1, 7), '足元に爆弾が置かれてる（1マス前から並ぶはず）');
  eq(X.bombs.length, 8, `8本置かれてない (${X.bombs.length})`);
  ok(X.bombAt(2, 7) && X.bombAt(9, 7), '(2,7)〜(9,7) に並んでない');
  return '足元は空いたまま 8本を前方へ';
});

t('きつねCPU：置ける本数を探して置く（cap 探索が生きてる）', () => {
  const [f, q] = fresh({ p1: 'fox', mode: 'vs', clear: true });
  q.cx = 19.5; q.cy = 13.5;
  f.isCPU = true;
  f.cx = 1.5; f.cy = 7.5; f.dir = 'right';
  f.maxBombs = 8; f.powerUp = 0;
  // think を正のままにして planCPU を走らせない＝「置きたい状態」を保ったまま置く判断だけ見る
  for (let i = 0; i < 120 && X.bombs.length === 0; i++) {
    f.ai.wantBomb = true; f.ai.think = 1; f.ai.bombBan = 0;
    X.cpuUpdate(f, 1 / 60);
  }
  ok(X.bombs.length > 0, 'CPU が1本も置けてない');
  ok(!X.bombs.some(b => b.x === Math.floor(f.cx) && b.y === Math.floor(f.cy)),
     'CPU が足元に置いてる');
  return `${X.bombs.length}本置いた`;
});

t('plannedLineBombs は cap で本数を絞れる', () => {
  const [f, q] = fresh({ p1: 'fox', mode: 'vs', clear: true });
  q.state = 'OUT';
  f.cx = 1.5; f.cy = 7.5; f.dir = 'right'; f.maxBombs = 6;
  eq(X.plannedLineBombs(f, 1, 7).length, 6, 'cap なしなら満載');
  eq(X.plannedLineBombs(f, 1, 7, 2).length, 2, 'cap=2 で2本');
  eq(X.plannedLineBombs(f, 1, 7, 1).length, 1, 'cap=1 で1本');
  // 足元ではなく1マス前から
  eq(X.plannedLineBombs(f, 1, 7, 1)[0].x, 2, '1本目が足元になってる');
  return 'ok';
});

t('人間のきつねは技ボタンで常に満載（lineCap は CPU 専用）', () => {
  const [f, q] = fresh({ p1: 'fox', mode: 'vs', clear: true });
  q.state = 'OUT';
  f.cx = 1.5; f.cy = 7.5; f.dir = 'right'; f.maxBombs = 4;
  eq(f.lineCap, null, '初期値が null じゃない');
  X.doAction(f);
  eq(X.bombs.length, 4, '満載で置いてない');
  ok(!X.bombAt(1, 7), '足元に置かれてる');
  ok(X.bombAt(2, 7) && X.bombAt(5, 7), '(2,7)〜(5,7) に並んでない');
  return 'ok';
});

/* ============ CPU の強さ設定 ============ */
t('CPU の強さは1体ずつ設定できる（4段階・既定はふつう）', () => {
  eq(X.CPU_LEVEL_KEYS.length, 4, '段階数');
  eq(X.CFG.cpuLevel.length, 3, 'CPU 3体ぶんの設定枠');
  const lv = X.CPU_LEVELS;
  // よわい→つよい で 反応が速く・見落としが減り・攻めが強くなる
  ok(lv.yowa.think > lv.futsu.think && lv.futsu.think > lv.tsuyo.think, '反応の順序');
  ok(lv.yowa.sloppy > lv.futsu.sloppy && lv.futsu.sloppy >= lv.tsuyo.sloppy, '見落としの順序');
  ok(lv.yowa.aggro < lv.futsu.aggro && lv.futsu.aggro < lv.tsuyo.aggro, '攻めの順序');
  return X.CPU_LEVEL_KEYS.map(k => `${lv[k].label}`).join('/');
});

t('CPU ごとに違う強さが割り当たる', () => {
  X.CFG.cpuLevel = ['yowa', 'tsuyo', 'oni'];
  fresh({ mode: '1p', p1: 'rabbit' });
  const cpus = X.players.filter(p => p.isCPU);
  eq(cpus.length, 3, 'CPU が3体いない');
  const got = cpus.map(p => X.cpuLevelOf(p.cpuIdx).label);
  eq(got.join(','), 'よわい,つよい,おに', `割り当てが違う: ${got.join(',')}`);
  X.CFG.cpuLevel = ['futsu', 'futsu', 'futsu'];
  return got.join(',');
});

t('よわい CPU は危険に気づかないことがある（つよいは必ず気づく）', () => {
  // sloppy=0 のつよい CPU は「気づかない」状態に入らない
  X.CFG.cpuLevel = ['tsuyo', 'tsuyo', 'tsuyo'];
  const ps = fresh({ mode: '1p', p1: 'rabbit', clear: true });
  const cpu = ps.find(p => p.isCPU);
  cpu.cx = 5.5; cpu.cy = 5.5;
  const b = X.spawnBomb(cpu, 5, 5); b.timer = 1.2;
  let blind = 0;
  for (let i = 0; i < 60; i++) { X.cpuUpdate(cpu, 1 / 60); if ((cpu.ai.blind || 0) > 0) blind++; }
  eq(blind, 0, 'つよい CPU が危険を見落とした');
  X.CFG.cpuLevel = ['futsu', 'futsu', 'futsu'];
  return 'ok';
});

/* ============ CPU のとくぎタイミング（2026-08-06 の報告） ============ */
t('きつねCPU：ブロックで隔てられた相手には狐火を撃たない', () => {
  const [f, r] = fresh({ p1: 'fox', p2: 'rabbit', mode: 'vs', clear: true });
  f.isCPU = true;
  // 通路（奇数行）で 4マス離す。まず「素の状態では撃つ」ことを確かめる
  f.cx = 3.5; f.cy = 7.5; r.cx = 7.5; r.cy = 7.5;
  f.chicken = 'fox'; f.chickenCharges = 1;
  f.ai.skillCool = 0;
  // skillReady() は外れると 0.4秒待つので、抽選が確実に何度も回るよう毎回リセットする
  // （リセットしないと 60フレームで数回しか引かれず、確率で落ちるテストになる）
  let fired = false;
  for (let i = 0; i < 300 && !fired; i++) {
    f.ai.skillCool = 0;
    X.cpuUpdate(f, 1 / 60);
    fired = !f.chicken;
  }
  ok(fired, '前提: 見通しがあれば撃つはず');

  // 間をソフトブロックで塞ぐ。回り道すると寿命内に届かないので撃つべきでない
  const [f2, r2] = fresh({ p1: 'fox', p2: 'rabbit', mode: 'vs', clear: true });
  f2.isCPU = true;
  f2.cx = 3.5; f2.cy = 7.5; r2.cx = 7.5; r2.cy = 7.5;
  for (let y = 1; y < X.ROWS - 1; y++) X.grid[y][5] = X.SOFT;   // 縦に壁を作って分断
  f2.chicken = 'fox'; f2.chickenCharges = 1;
  f2.ai.skillCool = 0;
  for (let i = 0; i < 120; i++) { X.cpuUpdate(f2, 1 / 60); f2.ai.skillCool = 0; }
  eq(f2.chicken, 'fox', 'ブロック越しなのに狐火を消費した');
  return 'ok';
});

t('foePathDist は壁を迂回した実距離を返す（マンハッタンではない）', () => {
  const [p, q] = fresh({ p1: 'fox', p2: 'rabbit', mode: 'vs', clear: true });
  p.cx = 3.5; p.cy = 7.5; q.cx = 7.5; q.cy = 7.5;
  eq(X.foePathDist(p, 3, 7, 12), 4, '見通しがある時は素直な距離');
  for (let y = 1; y < X.ROWS - 1; y++) X.grid[y][5] = X.SOFT;
  eq(X.foePathDist(p, 3, 7, 12), Infinity, '塞がれてるのに届く判定になってる');
  return 'ok';
});

t('とくぎの抽選は毎フレーム引かない（よわい CPU は使い損ねる）', () => {
  X.CFG.cpuLevel = ['yowa', 'yowa', 'yowa'];
  const [foe, cpu] = fresh({ p1: 'rabbit', p2: 'rabbit', mode: 'vs', clear: true });
  cpu.isCPU = true; cpu.cpuIdx = 0;
  // 撒く条件（歩いて5マス以内に敵）を満たす位置に置く
  foe.cx = 7.5; foe.cy = 7.5;
  cpu.cx = 4.5; cpu.cy = 7.5;
  // 外れたら skillCool が入って、しばらく引き直さないこと
  let sawCool = false;
  for (let i = 0; i < 300 && !sawCool; i++) {
    cpu.ai.skillCool = 0;
    cpu.chicken = 'rabbit'; cpu.chickenCharges = 1;
    X.cpuUpdate(cpu, 1 / 60);
    if ((cpu.ai.skillCool || 0) > 0) sawCool = true;
  }
  ok(sawCool, '抽選に外れても待たない（毎フレーム引いてる＝実質100%）');
  X.CFG.cpuLevel = ['futsu', 'futsu', 'futsu'];
  return 'ok';
});

/* ============ 画面遷移（タイトル → キャラ選択 → ルール → プレイ） ============ */
t('画面は タイトル → キャラ選択 → ルール → プレイ の順に進む', () => {
  X.showScreen('title');
  eq(X.G.phase, 'title', 'タイトルになってない');
  X.showScreen('pick');
  eq(X.G.phase, 'pick', 'キャラ選択になってない');
  X.showScreen('rules');
  eq(X.G.phase, 'rules', 'ルールになってない');
  X.showScreen('manual');
  eq(X.G.phase, 'manual', 'マニュアルになってない');
  X.showScreen('title');
  return Object.keys(X.SCREENS).join(' → ');
});

/* ============ LAN対戦 Phase 4（setupPlayersLan・ロビー画面） ============ */
t('setupPlayersLan: lanHumans=1〜4 のどれでも4枠が埋まる', () => {
  const log = [];
  for (const n of [1, 2, 3, 4]) {
    Object.assign(X.CFG, { mode: 'lan', lanHumans: n,
      lanPicks: ['rabbit', 'frog', 'fox', 'elephant'] });
    X.setupPlayersLan();
    eq(X.players.length, 4, `lanHumans=${n} で4枠にならない`);
    const humans = X.players.filter(p => !p.isCPU);
    const cpus = X.players.filter(p => p.isCPU);
    eq(humans.length, n, `lanHumans=${n} の人間の数`);
    eq(cpus.length, 4 - n, `lanHumans=${n} のCPUの数`);
    log.push(`${n}人+CPU${4 - n}`);
  }
  return log.join(' / ');
});

t('setupPlayersLan: 人間枠は全員 CONTROLS.solo（LANでは1台1人なので衝突しない）', () => {
  Object.assign(X.CFG, { mode: 'lan', lanHumans: 4,
    lanPicks: ['rabbit', 'frog', 'fox', 'elephant'] });
  X.setupPlayersLan();
  for (const p of X.players) {
    eq(p.controls, X.CONTROLS.solo, `${p.label} の controls が solo でない`);
  }
  return 'ok';
});

t('setupPlayersLan: CPU枠のcpuIdxは前から通し番号（cpuLevelの引き先と一致させる）', () => {
  Object.assign(X.CFG, { mode: 'lan', lanHumans: 1,
    lanPicks: ['rabbit', 'frog', 'fox', 'elephant'],
    cpuLevel: ['yowa', 'futsu', 'oni'] });
  X.setupPlayersLan();
  const cpus = X.players.filter(p => p.isCPU);
  eq(cpus.map(p => p.cpuIdx).join(','), '0,1,2', 'cpuIdx の採番');
  eq(X.cpuLevelOf(cpus[2].cpuIdx).label, 'おに', '3体目CPUの強さが cpuLevel[2] を引けてない');
  X.CFG.cpuLevel = ['futsu', 'futsu', 'futsu'];
  return 'ok';
});

t('mode:lan を足しても 1p/2p/vs の挙動は変わらない（スナップショット比較）', () => {
  // 既存の分岐を1行も触っていないことの確認。
  // setupPlayers() の early-return を追加しただけなら、
  // 'lan' 以外のモードの結果は前後で完全に同じになるはず。
  // ⚠️ 1p/2p の CPU は「どの動物になるか」も「(ぞう等の+HPが)どの枠に乗るか」も
  //    プールからの抽選（Math.random）で決まる仕様。個々の CPU の identity/HP は
  //    比較できないので、「人間の枠」と「人数・CPU数」という決定的な部分だけを見る
  //    （vs は CPU が居ないので動物名まで含めて比較できる）
  const snapshotDeterministic = (mode) => {
    Object.assign(X.CFG, { mode, hpP1: 2, hpP2: 2, hpCPU: 2,
      time: 180, wins: 3, sudden: true, sfx: false, bgm: false });
    X.CFG.pick.p1 = 'rabbit'; X.CFG.pick.p2 = 'frog';
    X.startGame();
    const humans = X.players.filter(p => !p.isCPU)
      .map(p => `${p.label}:${p.animal.key}:${p.maxHp}`).join('|');
    const cpuCount = X.players.filter(p => p.isCPU).length;
    return `${humans}#人数${X.players.length}#CPU${cpuCount}`;
  };
  const before = { '1p': snapshotDeterministic('1p'), '2p': snapshotDeterministic('2p'),
                   vs: snapshotDeterministic('vs') };
  // LAN を挟んでから、もう一度同じ設定で確認する
  Object.assign(X.CFG, { mode: 'lan', lanHumans: 2,
    lanPicks: ['mole', 'elephant', 'rabbit', 'frog'] });
  X.setupPlayersLan();
  const after = { '1p': snapshotDeterministic('1p'), '2p': snapshotDeterministic('2p'),
                  vs: snapshotDeterministic('vs') };
  eq(after['1p'], before['1p'], '1p モードが変わった');
  eq(after['2p'], before['2p'], '2p モードが変わった');
  eq(after.vs, before.vs, 'vs モードが変わった');
  return '1p/2p/vs とも不変';
});

t('画面組み立てのループに lan/lobby を追加しても例外を出さない', () => {
  for (const mode of ['1p', '2p', 'vs', 'lan']) {
    X.CFG.mode = mode;
    if (mode === 'lan') {
      X.CFG.lanHumans = 2;
      X.CFG.lanPicks = ['rabbit', 'frog', 'fox', 'elephant'];
    }
    X.buildSetup();
    X.buildPickers(); X.buildHpRows(); X.buildCpuRows();
    for (const sc of ['title', 'pick', 'rules', 'manual', 'lan', 'lobby']) X.showScreen(sc);
  }
  X.CFG.mode = '1p';
  X.showScreen('title');
  return '4モード × 6画面';
});

t('buildLobby: ホストは設定変更UIが組み立てられる（例外なし）', () => {
  X.NET.role = 'host'; X.NET.seat = 0; X.NET.roster = new Set([0]);
  X.CFG.mode = 'lan'; X.CFG.lanHumans = 2;
  X.CFG.lanPicks = ['rabbit', 'frog', 'fox', 'elephant'];
  X.CFG.cpuLevel = ['futsu', 'futsu', 'futsu'];
  X.showScreen('lobby');
  X.buildLobby();
  X.NET.role = null; X.NET.seat = null; X.NET.roster = new Set();
  return 'ok';
});

t('buildLobby: ゲストは設定変更UIを組み立てない（表示のみ）', () => {
  X.NET.role = 'guest'; X.NET.seat = 1; X.NET.roster = new Set([0, 1]);
  X.CFG.mode = 'lan'; X.CFG.lanHumans = 2;
  X.showScreen('lobby');
  X.buildLobby();
  X.NET.role = null; X.NET.seat = null; X.NET.roster = new Set();
  return 'ok';
});

t('startGame は CFG だけで動く（画面の状態に依存しない）', () => {
  // ★ ここが崩れるとテストとシミュレータが全部死ぬ
  X.showScreen('title');
  Object.assign(X.CFG, { mode: 'vs', hpP1: 2, hpP2: 2, hpCPU: 2,
    time: 180, wins: 3, sudden: false, sfx: false, bgm: false });
  X.CFG.pick.p1 = 'fox'; X.CFG.pick.p2 = 'mole';
  X.startGame();
  eq(X.G.phase, 'play', 'startGame でプレイに入ってない');
  eq(X.players.length, 2, 'CFG の内容が反映されてない');
  eq(X.players[0].animal.key, 'fox', 'キャラ選択が反映されてない');
  return 'ok';
});

t('設定の選択肢は 先取 3/5/7/9 と 制限時間 1/3/5/7分', () => {
  // 既定値がその中に無いと、開いた時にどれも選ばれてない見た目になる
  ok([3,5,7,9].includes(X.CFG.wins), `既定の先取数が選択肢に無い (${X.CFG.wins})`);
  ok([60,180,300,420].includes(X.CFG.time), `既定の制限時間が選択肢に無い (${X.CFG.time})`);
  return `先取${X.CFG.wins}勝 / ${X.CFG.time}秒`;
});

t('バージョン番号が定義されてる', () => {
  ok(/^v\d+\.\d+\.\d+$/.test(X.VERSION), `形式がおかしい: ${X.VERSION}`);
  return X.VERSION;
});

t('各画面の組み立てが例外を出さない（要素の付け替え漏れ検出）', () => {
  // ※ テストの DOM スタブは どの id でも要素を作ってしまうので、
  //   「id が存在するか」はここでは検出できない。実ページで1度クリックして確かめる。
  //   ここで見るのは 例外を出さずに組み立てられるかだけ
  for (const mode of ['1p', '2p', 'vs']) {
    X.CFG.mode = mode;
    X.buildSetup();
    X.buildPickers(); X.buildHpRows(); X.buildCpuRows();
    for (const sc of ['title', 'pick', 'rules', 'manual']) X.showScreen(sc);
  }
  X.CFG.mode = '1p';
  X.showScreen('title');
  return '3モード × 4画面';
});

/* ============ collides を触ったことによるデグレ検査 ============
   「いま重なってるタイルは移動先判定から外す」を入れたので、
   壁抜けが起きてないかを全方向・最高速で確かめる */
t('デグレ検査：ふつうの動物は硬ブロックを最高速でもすり抜けない', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  const log = [];
  // 盤面の四隅の内側に立って、外壁へ向かって押し続ける
  const cases = [
    { sx: 1.5, sy: 1.5, dx: -1, dy: 0, lim: x => x.cx > 1.0, what: '左の外壁' },
    { sx: 1.5, sy: 1.5, dx: 0, dy: -1, lim: x => x.cy > 1.0, what: '上の外壁' },
    { sx: X.COLS - 2.5, sy: X.ROWS - 2.5, dx: 1, dy: 0, lim: x => x.cx < X.COLS - 1, what: '右の外壁' },
    { sx: X.COLS - 2.5, sy: X.ROWS - 2.5, dx: 0, dy: 1, lim: x => x.cy < X.ROWS - 1, what: '下の外壁' },
  ];
  for (const c of cases) {
    p.cx = c.sx; p.cy = c.sy; p.shoes = 6;      // 最高速
    for (let i = 0; i < 600; i++) { VT += 16; X.movePlayer(p, c.dx, c.dy, 1 / 60); }
    ok(c.lim(p), `${c.what}をすり抜けた (${p.cx.toFixed(2)},${p.cy.toFixed(2)})`);
    log.push(c.what);
  }
  return log.join('/') + ' すべて貫通なし';
});

t('デグレ検査：ふつうの動物はソフトブロックをすり抜けない', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.cx = 3.5; p.cy = 1.5; p.shoes = 6;
  X.grid[1][4] = X.SOFT;
  for (let i = 0; i < 600; i++) { VT += 16; X.movePlayer(p, 1, 0, 1 / 60); }
  ok(p.cx < 4.0, `ソフトブロックをすり抜けた (cx=${p.cx.toFixed(2)})`);
  return `cx=${p.cx.toFixed(2)} で止まる`;
});

t('デグレ検査：他人の爆弾は最高速でもすり抜けない（全動物）', () => {
  const log = [];
  for (const key of ['rabbit', 'elephant', 'mole', 'fox', 'frog']) {
    const [p, q] = fresh({ p1: key, p2: 'rabbit', mode: 'vs', clear: true });
    p.cx = 3.5; p.cy = 1.5; p.shoes = 6;
    q.cx = 15.5; q.cy = 11.5;
    const b = X.spawnBomb(q, 4, 1);
    b.timer = 99;
    for (let i = 0; i < 600; i++) { VT += 16; X.movePlayer(p, 1, 0, 1 / 60); }
    ok(p.cx < 4.0, `${key} が爆弾をすり抜けた (cx=${p.cx.toFixed(2)})`);
    log.push(key);
  }
  return log.join(',') + ' 全部止まる';
});

t('デグレ検査：自分の爆弾から降りたら戻れない', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.cx = 3.5; p.cy = 1.5;
  X.placeBomb(p);
  const b = X.bombAt(3, 1);
  ok(b.ignore.has(p.id), '置いた直後は通れる');
  // 右へ完全に離れる
  for (let i = 0; i < 120; i++) { VT += 16; X.movePlayer(p, 1, 0, 1 / 60); X.refreshBombIgnore(); }
  ok(!b.ignore.has(p.id), '離れたら固体化すべき');
  const far = p.cx;
  // 左へ戻ろうとしても爆弾より手前で止まる
  for (let i = 0; i < 300; i++) { VT += 16; X.movePlayer(p, -1, 0, 1 / 60); X.refreshBombIgnore(); }
  ok(p.cx > 4.0, `爆弾の中まで戻れてしまった (cx=${p.cx.toFixed(2)})`);
  return `離れて cx=${far.toFixed(2)} → 戻っても cx=${p.cx.toFixed(2)} で止まる`;
});

t('デグレ検査：斜め入力でも壁の角をすり抜けない', () => {
  const [p, q] = fresh({ p1: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  p.shoes = 6;
  // (2,2) は柱（even,even）。その左下から右上へ押し込む
  eq(X.grid[2][2], X.HARD, '前提: (2,2) は硬ブロック');
  p.cx = 1.5; p.cy = 3.5;
  for (let i = 0; i < 600; i++) { VT += 16; X.movePlayer(p, 1, -1, 1 / 60); }
  const insidePillar = Math.floor(p.cx) === 2 && Math.floor(p.cy) === 2;
  ok(!insidePillar, `柱の中に入った (${p.cx.toFixed(2)},${p.cy.toFixed(2)})`);
  return `(${p.cx.toFixed(2)},${p.cy.toFixed(2)})`;
});

/* ============ もぐら × 爆弾のすり抜け ============ */
t('もぐらは爆弾のマスに入れない', () => {
  const [m, q] = fresh({ p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  m.cx = 3.5; m.cy = 1.5;
  q.cx = 15.5; q.cy = 11.5;
  const b = X.spawnBomb(q, 4, 1);          // もぐらと重なってない他人の爆弾
  b.timer = 99;
  ok(X.isSolidFor(m, 4, 1), '爆弾のマスが通れる扱いになってる');
  ok(X.collides(m, 4.5, 1.5), '爆弾のマスに入れてしまう');
  ok(!X.walkableFor(m, 4, 1), 'CPU の経路探索でも通れる扱いになってる');
  for (let i = 0; i < 240; i++) { VT += 16; X.movePlayer(m, 1, 0, 1 / 60); }
  ok(m.cx < 4.0, `4秒押し続けて爆弾をすり抜けた（cx=${m.cx.toFixed(2)}）`);
  return `cx=${m.cx.toFixed(2)} で止まる`;
});

t('もぐらは自分が置いた爆弾の足元から、隣のブロックへ抜けられる', () => {
  const [m, q] = fresh({ p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  m.cx = 3.5; m.cy = 1.5; m.shoes = 6;     // 掘りを速くして待ち時間を短縮
  X.grid[1][4] = X.SOFT;                   // 右隣のブロック（逃げ道）
  X.placeBomb(m);                          // 足元に自分の爆弾
  const bb = X.bombAt(3, 1);
  ok(bb, '爆弾が置かれた');
  ok(bb.ignore.has(m.id), '自分の爆弾は通れる扱いになってるべき');
  ok(!X.isSolidFor(m, 4, 1), '自分の爆弾のせいで隣のブロックが塞がってる');
  ok(X.walkableFor(m, 4, 1), 'CPU 経路でも塞がってる');
  for (let i = 0; i < 400; i++) { VT += 16; X.movePlayer(m, 1, 0, 1 / 60); }
  ok(m.cx > 4.0, `自分の爆弾を置いた後、隣のブロックへ入れない（cx=${m.cx.toFixed(2)}）`);
  return `cx=${m.cx.toFixed(2)} まで潜れる`;
});

t('もぐらは自分の爆弾から、ブロックを2枚3枚と連続で掘り進める', () => {
  const [m, q] = fresh({ p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  m.cx = 3.5; m.cy = 1.5; m.shoes = 6;
  // 右に3枚ブロックを並べる
  X.grid[1][4] = X.SOFT; X.grid[1][5] = X.SOFT; X.grid[1][6] = X.SOFT;
  X.placeBomb(m);
  const seen = new Set();
  for (let i = 0; i < 900; i++) {
    VT += 16; X.movePlayer(m, 1, 0, 1 / 60);
    seen.add(Math.floor(m.cx));
    X.refreshBombIgnore();                 // 実ゲームと同じく毎フレーム更新
  }
  ok(seen.has(4), '1枚目(4,1) に入れてない');
  ok(seen.has(5), '2枚目(5,1) に進めてない ← ここで詰まるのが報告されたバグ');
  ok(seen.has(6), '3枚目(6,1) に進めてない');
  return `到達したx: ${[...seen].sort((a,b)=>a-b).join(',')}`;
});

t('もぐらは自分の爆弾から掘って逃げれば生き延びる（報告されたバグの再現）', () => {
  const [m, q] = fresh({ hp: 1, p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  q.state = 'OUT';
  m.cx = 3.5; m.cy = 1.5; m.shoes = 6; m.powerUp = 1;   // 火力2＝(4,1)(5,1)まで届く
  X.grid[1][4] = X.SOFT; X.grid[1][5] = X.SOFT;
  X.grid[1][6] = X.SOFT; X.grid[1][7] = X.SOFT;
  X.placeBomb(m);
  const b = X.bombAt(3, 1);
  ok(b, '爆弾が置かれた');
  // 爆発するまで右へ掘り続ける
  const frames = Math.ceil((X.BOMB_FUSE + X.BLAST_DUR + 0.3) * 60);
  for (let i = 0; i < frames; i++) {
    VT += 1000 / 60;
    X.movePlayer(m, 1, 0, 1 / 60);
    X.update(1 / 60);
  }
  eq(m.state, 'ALIVE', `自分の爆弾から掘って逃げたのに死んだ（cx=${m.cx.toFixed(2)}）`);
  return `cx=${m.cx.toFixed(2)} まで逃げて生存`;
});

t('もぐらは他人の爆弾のとなりのソフトブロックは掘り抜けられない', () => {
  const [m, q] = fresh({ p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  m.cx = 3.5; m.cy = 1.5;
  q.cx = 15.5; q.cy = 11.5;
  const b = X.spawnBomb(q, 4, 1);
  b.timer = 99;
  X.grid[2][4] = X.SOFT;                   // 爆弾の真下（迂回路）
  ok(!b.ignore.has(m.id), 'もぐらは他人の爆弾に乗ってない');
  ok(X.isSolidFor(m, 4, 2), '他人の爆弾のとなりを迂回できてしまう');
  ok(!X.walkableFor(m, 4, 2), 'CPU 経路でも迂回できてしまう');
  return 'ok';
});

t('爆弾から離れたソフトブロックはちゃんと掘れる（緩めすぎてない）', () => {
  const [m, q] = fresh({ p1: 'mole', p2: 'rabbit', mode: 'vs', clear: true });
  m.cx = 3.5; m.cy = 1.5;
  q.cx = 15.5; q.cy = 11.5;
  const b = X.spawnBomb(q, 15, 11);        // 遠くの爆弾
  b.timer = 99;
  X.grid[1][4] = X.SOFT;
  ok(!X.isSolidFor(m, 4, 1), '離れたブロックが掘れなくなってる');
  ok(X.walkableFor(m, 4, 1), 'CPU 経路でも掘れるべき');
  // もぐら以外はそもそも通れない
  ok(X.isSolidFor(q, 4, 1), 'もぐら以外がブロックを通れてしまう');
  return 'ok';
});

t('👟 の効きは 通り抜け中も DIG_PENALTY と同じ倍率（特別扱いで弱めない）', () => {
  const [m] = fresh({ p1: 'mole', mode: 'vs' });
  m.cx = 3.5; m.cy = 3.5;
  // 通常のマスでの 👟1個ぶんの伸び
  X.grid[3][3] = X.EMPTY;
  const walk0 = X.getSpeed(m);
  X.applyItem(m, X.IT_SHOE);
  const walk1 = X.getSpeed(m);
  const walkGain = walk1 - walk0;
  eq(Math.round(walkGain * 100) / 100, X.SHOE_STEP, '通常マスでの 👟1個ぶんの伸び');

  // 通り抜け中（ブロックの中）での 👟1個ぶんの伸び
  m.shoes = 0;
  X.grid[3][3] = X.SOFT;
  const dig0 = X.getSpeed(m);
  X.applyItem(m, X.IT_SHOE);
  const dig1 = X.getSpeed(m);
  const digGain = dig1 - dig0;
  X.grid[3][3] = X.EMPTY;

  ok(digGain > 0, '👟でまったく速くならないのは行き過ぎ');
  // 10%まで弱めすぎたのを 2026-08-09 に戻した。DIG_PENALTY（18%）と同じ比率のはず
  const rate = digGain / walkGain;
  ok(Math.abs(rate - X.DIG_PENALTY) < 0.02,
     `通り抜け中の 👟 の効きが DIG_PENALTY(${X.DIG_PENALTY}) と揃ってない (${(rate * 100).toFixed(0)}%)`);

  // 👟MAX でも通常歩行より遅いまま
  m.shoes = X.SHOE_MAX;
  X.grid[3][3] = X.SOFT;
  const digMax = X.getSpeed(m);
  X.grid[3][3] = X.EMPTY;
  ok(digMax < walk0, `👟MAX の掘り速度が素の歩行より速い (${digMax.toFixed(2)} vs ${walk0.toFixed(2)})`);
  return `通常 +${walkGain.toFixed(2)} / 掘り +${digGain.toFixed(2)} = ${(rate * 100).toFixed(0)}%`
    + `（👟MAXでも ${digMax.toFixed(2)} tiles/s）`;
});

t('もぐらはブロックの中で激おそになる', () => {
  const [p] = fresh({ p1: 'mole' });
  p.cx = 3.5; p.cy = 1.5;
  const open = X.getSpeed(p);
  X.grid[1][3] = X.SOFT;                 // 自分のマスをブロックにする
  const inside = X.getSpeed(p);
  ok(inside < open * 0.3, `潜航中が遅くなってない (${open.toFixed(2)}→${inside.toFixed(2)})`);
  return `${open.toFixed(2)} → ${inside.toFixed(2)} tiles/s`;
});

/* ============ 6. 葱ボン ============ */
t('葱ボンは外周のどこにいても盤面内向きに撃つ', () => {
  const seen = new Set();
  for (let t0 = 0; t0 < 2 * (X.COLS + X.ROWS); t0 += 1) {
    const pos = X.negiPos(t0);
    seen.add(pos.dir);
    ok(['up', 'down', 'left', 'right'].includes(pos.dir), 'dir が変');
  }
  eq(seen.size, 4, '4辺ぶんの向きが出るべき');
  return [...seen].join(',');
});

t('葱が当たると撃った側が復活し、当たった側が葱ボンへ', () => {
  const [a, b] = fresh({ hp: 2 });
  // a を葱ボンにする
  a.hp = 0; X.kill(a);
  eq(a.state, 'NEGIBON', 'a が葱ボン');
  b.powerUp = 3; b.maxBombs = 4; b.shoes = 2;   // b は強化済み
  a.powerUp = 2; a.maxBombs = 3; a.shoes = 1;   // a も強化済みのまま場外にいる
  X.negiHit(a, b);
  eq(a.state, 'ALIVE', 'a 復活');
  eq(b.state, 'NEGIBON', 'b が葱ボンへ');
  // 復活してもパワーアップは維持する（終盤に初期火力へ戻ると勝負がつかない）
  eq(a.powerUp, 2, '復活側の火力は維持されるべき');
  eq(a.maxBombs, 3, '復活側の爆弾数も維持');
  eq(a.shoes, 1, '復活側の靴も維持');
  eq(a.hp, Math.min(a.maxHp, 1), '復活時のHPは1');
  ok(a.invuln > 0, '復活直後は無敵');
  return 'ok';
});

t('場外に落ちてもパワーアップは失わない', () => {
  const [a, b] = fresh({ hp: 2, mode: 'vs' });
  X.applyItem(a, X.IT_FIRE); X.applyItem(a, X.IT_BOMB);
  const pw = a.powerUp, mb = a.maxBombs;
  a.hp = 0; X.kill(a);
  eq(a.state, 'NEGIBON', '葱ボンへ');
  eq(a.powerUp, pw, '場外でも火力を保持');
  eq(a.maxBombs, mb, '場外でも爆弾数を保持');
  return 'ok';
});

t('被弾でアイテムを吐き出しても自分のパワーアップは減らない', () => {
  const [p, q] = fresh({ hp: 4, mode: 'vs' });
  q.state = 'OUT';
  X.applyItem(p, X.IT_FIRE); X.applyItem(p, X.IT_BOMB); X.applyItem(p, X.IT_SHOE);
  const pw = p.powerUp, mb = p.maxBombs, sh = p.shoes;
  p.invuln = 0; X.hurt(p);
  eq(p.powerUp, pw, '火力が減ってはいけない');
  eq(p.maxBombs, mb, '爆弾数が減ってはいけない');
  eq(p.shoes, sh, '靴が減ってはいけない');
  return 'ok';
});

t('葱は飛んでいって当たる（すり抜けない・外壁で砕けない）', () => {
  const [a, b] = fresh({ hp: 2, mode: 'vs' });
  a.hp = 0; X.kill(a);
  // 上辺の奇数列（柱が無い列）を狙う
  a.negiT = 0;                       // 内部 x=1 の列
  const pos = X.negiPos(a.negiT);
  eq(Math.floor(pos.x), 1, '発射列');
  b.cx = 1.5; b.cy = 5.5;            // 葱の軌道上に立たせる
  a.negiCool = 0;
  X.fireNegi(a);
  eq(X.negis.length, 1, '葱が出た');
  for (let i = 0; i < 200 && a.state === 'NEGIBON'; i++) step(1);
  eq(a.state, 'ALIVE', '葱が当たって復活すべき');
  eq(b.state, 'NEGIBON', '当たった側が場外へ');
  return 'ok';
});

t('葱は柱（内部の硬ブロック）では砕ける', () => {
  const [a, b] = fresh({ hp: 2, mode: 'vs' });
  a.hp = 0; X.kill(a);
  a.negiT = 1;                       // 内部 x=2 = 偶数列 → y=2 に柱
  const pos = X.negiPos(a.negiT);
  eq(Math.floor(pos.x), 2, '発射列');
  b.cx = 2.5; b.cy = 4.5;
  a.negiCool = 0;
  X.fireNegi(a);
  for (let i = 0; i < 200; i++) step(1);
  eq(a.state, 'NEGIBON', '柱で止まるので復活しないべき');
  return 'ok';
});

t('葱ボンは自分が撃った葱では復活しない（自分に当たらない）', () => {
  const [a, b] = fresh({ hp: 2, mode: 'vs' });
  a.hp = 0; X.kill(a);
  b.state = 'OUT';                   // 生きてる相手がいない
  a.negiCool = 0;
  X.fireNegi(a);
  for (let i = 0; i < 200; i++) step(1);
  eq(a.state, 'NEGIBON', '誰にも当たらないので葱ボンのまま');
  return 'ok';
});

t('残り1分で葱ボンは全員退場する', () => {
  const [a, b] = fresh({ hp: 1, time: 180 });
  a.hp = 0; X.kill(a);
  eq(a.state, 'NEGIBON', '葱ボン');
  X.G.time = X.NEGI_CUTOFF - 0.5;
  X.checkEnd();
  eq(a.state, 'OUT', 'カットオフで退場すべき');
  return 'ok';
});

t('盤面に1人になったら葱ボンが場外に居ても即決着（待たされない）', () => {
  const [a, b] = fresh({ hp: 1, time: 180, mode: 'vs' });
  a.hp = 0; X.kill(a);
  eq(a.state, 'NEGIBON', 'a 葱ボン');
  eq(b.state, 'ALIVE', 'b 生存');
  ok(X.G.time > X.NEGI_CUTOFF, 'まだカットオフ前');
  X.checkEnd();
  ok(X.G.overInfo, '1分以上残ってるのに決着してない（葱ボン待ちになってる）');
  eq(X.G.overInfo.winner, b, '勝者');
  return 'ok';
});

t('4人戦：2人残ってる間は葱ボンが居ても決着しない', () => {
  const ps = fresh({ hp: 1, time: 180, mode: '2p' });
  eq(ps.length, 4, '人数');
  ps[0].hp = 0; X.kill(ps[0]);
  ps[1].hp = 0; X.kill(ps[1]);
  eq(ps.filter(p => p.state === 'ALIVE').length, 2, '2人生存');
  X.checkEnd();
  ok(!X.G.overInfo, '2人残ってるのに決着してしまった');
  return 'ok';
});

/* ============ 7. サドンデス ============ */
t('時間切れで複数生存 → サドンデス（HP1・ブロック全消し・60秒）', () => {
  const ps = fresh({ hp: 3, time: 180, sudden: true, clear: false });
  X.G.time = 0;
  X.checkEnd();
  ok(X.G.suddenUsed, 'サドンデスに入ってない');
  ok(!X.G.overInfo, 'まだ決着してはいけない');
  eq(Math.round(X.G.time), 60, '延長時間');
  const alive = ps.filter(p => p.state === 'ALIVE');
  ok(alive.length >= 2, '2人以上生きてるべき');
  for (const p of alive) { eq(p.hp, 1, 'HP'); eq(p.maxHp, 1, 'maxHp'); }
  let soft = 0;
  for (let y = 0; y < X.ROWS; y++) for (let x = 0; x < X.COLS; x++)
    if (X.grid[y][x] === X.SOFT) soft++;
  eq(soft, 0, 'ソフトブロックが残ってる');
  return `${alive.length}人でサドンデス`;
});

t('サドンデスは 火力・爆弾数・足の速さ 全部MAX', () => {
  const ps = fresh({ hp: 3, time: 180, sudden: true, clear: false });
  for (const p of ps) { p.shoes = 0; p.powerUp = 0; }
  const spd0 = X.getSpeed(ps[0]);
  X.G.time = 0;
  X.checkEnd();
  const alive = ps.filter(p => p.state === 'ALIVE');
  ok(alive.length >= 2, '2人以上生きてるべき');
  for (const p of alive) {
    eq(p.maxBombs, X.BOMB_MAX, `${p.animal.name} の爆弾数がMAXでない`);
    eq(X.getPower(p), X.POWER_MAX, `${p.animal.name} の火力がMAXでない`);
    eq(p.shoes, X.SHOE_MAX, `${p.animal.name} の👟がMAXでない`);
  }
  ok(X.getSpeed(ps[0]) > spd0, '足が速くなってない');
  return `💣${X.BOMB_MAX} 🔥${X.POWER_MAX} 👟${X.SHOE_MAX}（速度 ${spd0.toFixed(2)}→${X.getSpeed(ps[0]).toFixed(2)}）`;
});

t('きつね：サドンデス装備（💣MAX 🔥MAX 👟0）で一列ドン置きしても逃げ切れる', () => {
  const [f, q] = fresh({ p1: 'fox', p2: 'rabbit', mode: 'vs' });
  q.state = 'OUT';
  // 柱の無い通路（奇数行・奇数列）で、前方が8マス空いてる所に立つ
  f.cx = 3.5; f.cy = 1.5; f.dir = 'right';
  f.maxBombs = X.BOMB_MAX; f.powerUp = X.POWER_MAX; f.shoes = 0;
  f.hp = 1; f.maxHp = 1; f.invuln = 0;
  const plan = X.plannedLineBombs(f, 3, 1);
  eq(plan.length, X.BOMB_MAX, '一列に爆弾数ぶん置けるはず');
  eq(X.getPower(f), X.POWER_MAX, '火力MAXのはず');
  X.placeLineBombs(f);
  // 後ろへ下がって、爆弾の無い列で行から外れる（(2,2) は柱なので (1,2) まで下がる）
  // マスの真ん中まで入り切ること。境界に立つと当たり判定が隣のマスにも跨る
  for (let i = 0; i < 120 && f.cx > 1.5; i++) { X.movePlayer(f, -1, 0, 1 / 60); step(1); }
  for (let i = 0; i < 120 && f.cy < 2.5; i++) { X.movePlayer(f, 0, 1, 1 / 60); step(1); }
  eq(`${Math.floor(f.cx)},${Math.floor(f.cy)}`, '1,2', '逃げ先まで届いてない');
  ok(X.G.elapsed < X.BOMB_FUSE, `逃げるのに ${X.G.elapsed.toFixed(2)}s＝導火線に間に合ってない`);
  step(Math.ceil((X.BOMB_FUSE + X.BLAST_DUR + 0.3) * 60));
  eq(f.state, 'ALIVE', `自分の一列ドン置きで自滅した（${Math.floor(f.cx)},${Math.floor(f.cy)}）`);
  return `💣${X.BOMB_MAX}本 🔥${X.POWER_MAX} でも生存`;
});

t('穴を掘ってる途中にサドンデスへ入っても固まらない', () => {
  const ps = fresh({ hp: 2, time: 180, sudden: true, mode: '2p', p1: 'mole' });
  const m = ps[0];
  m.chicken = 'mole'; m.chickenCharges = 1;
  X.doAction(m);
  ok(m.digging, '掘ってる');
  X.G.time = 0;
  X.checkEnd();
  ok(X.G.suddenUsed, 'サドンデスに入った');
  ok(!m.digging, '掘り状態が解除されてないと動けないまま固まる');
  ok(!X.isBusy(m), '操作を受け付ける状態に戻ってるべき');
  const x0 = m.cx;
  X.movePlayer(m, 1, 0, 0.15);
  ok(m.cx !== x0, '動けてない');
  return 'ok';
});

t('舌を出してる途中にサドンデスへ入っても固まらない', () => {
  const ps = fresh({ hp: 2, time: 180, sudden: true, mode: '2p', p1: 'frog' });
  const f = ps[0];
  f.cx = 5.5; f.cy = 5.5; f.dir = 'right';
  X.doAction(f);
  ok(f.tongue, '舌が出てる');
  X.G.time = 0;
  X.checkEnd();
  ok(!f.tongue, '舌が解除されてない');
  ok(!X.isBusy(f), '操作を受け付ける状態に戻ってるべき');
  return 'ok';
});

t('サドンデスは1回だけ。2回目は引き分け', () => {
  fresh({ hp: 3, time: 180, sudden: true });
  X.G.time = 0; X.checkEnd();
  ok(X.G.suddenUsed, '1回目');
  X.G.time = 0; X.checkEnd();
  ok(X.G.overInfo, '2回目は決着（引き分け）すべき');
  return 'ok';
});

t('サドンデス OFF なら時間切れで引き分け', () => {
  fresh({ hp: 3, time: 180, sudden: false });
  X.G.time = 0; X.checkEnd();
  ok(X.G.overInfo, '決着してない');
  eq(X.G.overInfo.winner, null, '引き分けのはず');
  ok(!X.G.suddenUsed, 'OFFなのにサドンデスに入った');
  return 'ok';
});

t('同時死でサドンデス（葱ボン退場後）', () => {
  // time < cutoff なので葱ボンなし。タイマンにして「全員死亡」を作る
  const [a, b] = fresh({ hp: 1, time: 30, sudden: true, mode: 'vs' });
  a.invuln = 0; b.invuln = 0;
  X.hurt(a); X.hurt(b);                 // 同じフレームで2人死ぬ
  eq(a.state, 'OUT', 'a 退場');
  eq(b.state, 'OUT', 'b 退場');
  X.checkEnd();
  ok(X.G.suddenUsed, '同時死でサドンデスに入るべき');
  eq(X.players.filter(p => p.state === 'ALIVE').length, 2, '2人が復帰');
  return 'ok';
});

/* ============ 8. 一般 ============ */
t('タイマンモードは2人だけ', () => {
  const ps = fresh({ mode: 'vs' });
  eq(ps.length, 2, '人数');
  eq(ps.filter(p => p.isCPU).length, 0, 'CPU がいてはいけない');
  return 'ok';
});
t('1人モードは自分＋CPU3', () => {
  const ps = fresh({ mode: '1p' });
  eq(ps.length, 4, '人数');
  eq(ps.filter(p => p.isCPU).length, 3, 'CPU数');
  ok(ps.slice(1).every(p => p.label === p.animal.name), 'CPU名が動物名になってない');
  return ps.map(p => p.label).join(',');
});
t('2人+CPU2モード', () => {
  const ps = fresh({ mode: '2p' });
  eq(ps.length, 4, '人数');
  eq(ps.filter(p => !p.isCPU).length, 2, '人間の数');
  return 'ok';
});
t('うんこ「爆風1マス」中は火力が1になる', () => {
  const [p] = fresh({ p1: 'elephant' });
  ok(X.getPower(p) >= 3, 'ぞうの素の火力');
  p.effects.weak = 5;
  eq(X.getPower(p), 1, 'weak 中の火力');
  return 'ok';
});
t('うんこ「爆弾おけない」中は置けない', () => {
  const [p, q] = fresh();
  q.state = 'OUT';
  p.effects.nobomb = 5;
  X.placeBomb(p, false);
  eq(X.bombs.length, 0, '置けてしまった');
  return 'ok';
});

/* ============ 9. LAN対戦 Phase 1（inputOf の抽象化） ============ */
t('HTML内の <script> ブロックはちょうど1個', () => {
  // sim.js のブロック抽出・python 側の抽出スクリプト（[-1]）は、
  // どちらも「ブロックは1個だけ」という前提に依存している。
  // <script src> や type="module" を足すとここが黙って壊れる。
  const blocks = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  eq(blocks.length, 1, 'script ブロック数');
  return `${blocks.length}個`;
});
t('inputOf: p.net が無ければキーボードの hold/edge をそのまま返す', () => {
  const [p] = fresh();
  p.net = null;
  X.keys.add(p.controls.left[0]);
  X.pressed.add(p.controls.bomb[0]);
  const I = X.inputOf(p);
  eq(I.left, true, 'left は keys 由来のはず');
  eq(I.right, false, 'right は押してないはず');
  eq(I.eBomb, true, 'eBomb は pressed 由来のはず');
  eq(I.eAct, false, 'eAct は押してないはず');
  X.keys.delete(p.controls.left[0]);
  X.pressed.delete(p.controls.bomb[0]);
  return 'ok';
});
t('inputOf: p.net があればキーボードを無視して p.net をそのまま返す', () => {
  const [p] = fresh();
  X.keys.add(p.controls.left[0]);  // キーボードは左を押しているが
  p.net = { up:false, down:false, left:false, right:true,
            bomb:false, act:false, eBomb:false, eAct:false };
  const I = X.inputOf(p);
  eq(I.left, false, 'キーボードでなく p.net を見るべき');
  eq(I.right, true, 'p.net の値をそのまま返すべき');
  X.keys.delete(p.controls.left[0]);
  p.net = null;
  return 'ok';
});
t('NET.clearEdges: p.net のエッジは1回消費したら false に戻る（バグ#10 のテスト）', () => {
  const [p] = fresh();
  p.net = { up:false, down:false, left:false, right:false,
            bomb:true, act:false, eBomb:true, eAct:false };
  X.NET.clearEdges();
  eq(p.net.eBomb, false, 'eBomb は消費後にクリアされるべき');
  eq(p.net.eAct, false, 'eAct はそもそも false のままのはず');
  eq(p.net.bomb, true, '押しっぱなし相当の bomb はクリア対象外のはず');
  p.net = null;
  return 'ok';
});
t('NET.clearEdges: p.net が無いプレイヤー（ローカル操作）には触らない', () => {
  const ps = fresh();
  for (const p of ps) eq(p.net, undefined, '初期状態で p.net は無いはず');
  X.NET.clearEdges();  // 例外が出ないことも確認
  return 'ok';
});
t('humanUpdate は inputOf 経由でも従来どおりキーボード操作で動く（bit-identical の確認）', () => {
  // p.net を一切設定しないケースでは、164件の既存テストと同じ経路
  // （humanUpdate → inputOf → hold/edge → keys/pressed）を通ることの確認。
  const [p, q] = fresh({ mode: 'vs', clear: true });
  q.state = 'OUT';
  const cx0 = p.cx;
  X.keys.add(p.controls.right[0]);
  step(10);
  X.keys.delete(p.controls.right[0]);
  ok(p.cx > cx0, `右キー押しっぱなしで右へ動くべき（${cx0}→${p.cx}）`);
  return `${cx0}→${p.cx}`;
});

/* ============ 12. ゲームパッド ============ */

/** 標準マッピングの偽パッド。down=押しているボタン番号、ax=軸 */
function fakePad(down = [], ax = [0, 0, 0, 0]) {
  const buttons = [];
  for (let i = 0; i < 17; i++) buttons.push({ pressed: down.includes(i), value: down.includes(i) ? 1 : 0 });
  return { id: 'Fake (STANDARD GAMEPAD)', mapping: 'standard', connected: true,
           index: 1, buttons, axes: ax };
}
/** 1回ポーリングする。index 0 は null にしておく
    （先頭決め打ちのテスト。実機の STK-7043 は index 1 に入っていた） */
const padPoll = (pad) => X.pollGamepads(pad ? [null, pad] : []);
/** 全部離してグローバルを綺麗にする。テストの頭と尻で必ず呼ぶ
    （keys / PAD はテスト間で共有なので、漏れると無関係なテストが落ちる）。
    ⛔ PAD.prev を手で消さない。pollGamepads([]) に解放させるのが仕様の確認も兼ねる */
const padOff = () => { X.pollGamepads([]); X.keys.clear(); X.pressed.clear(); };

t('パッド: バナーを A で送って押しっぱなしでも、次ラウンドの初期位置に爆弾が置かれない（事故#11 のテスト）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  X.G.phase = 'roundEnd';
  const r0 = X.G.round;
  padPoll(fakePad([0]));                    // ① A でバナーを送る（指は離していない）
  eq(X.G.phase, 'play', 'A でラウンドが始まらない');
  eq(X.G.round, r0 + 1, 'ラウンドが進んでいない');
  eq(X.pressed.size, 0, 'startRound が「押した瞬間」を捨てていない（注入→遷移の順序が逆）');
  padPoll(fakePad([0]));                    // ② 次フレーム。A はまだ押されたまま
  eq(X.pressed.has('Pad:A'), false, 'keys.clear() 後の再ポーリングで偽エッジが立った＝事故#11 の再発');
  ok(X.keys.has('Pad:A'), '押しっぱなしの hold は復帰しているべき');
  X.humanUpdate(X.players[0], 1 / 60);
  eq(X.bombs.length, 0, '初期位置に爆弾が置かれてしまった（詰む）');
  padOff();
  return '押しっぱなし → 爆弾0本';
});

t('パッド: いったん離して押し直せば爆弾は置ける（事故#11 対策で入力を殺していない）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  X.G.phase = 'roundEnd';
  padPoll(fakePad([0]));                    // バナーを送る
  padPoll(fakePad([0]));                    // 押しっぱなし
  X.humanUpdate(X.players[0], 1 / 60);
  eq(X.bombs.length, 0, '押しっぱなしで置けてしまった');
  X.pressed.clear();
  padPoll(fakePad([]));                     // 指を離す
  X.pressed.clear();
  padPoll(fakePad([0]));                    // 押し直し
  ok(X.pressed.has('Pad:A'), '押し直しのエッジが立っていない（入力が死んでいる）');
  X.humanUpdate(X.players[0], 1 / 60);
  eq(X.bombs.length, 1, '押し直しても爆弾が置けない');
  padOff();
  return '押しっぱなし=0本 / 押し直し=1本';
});

t('パッド: ラウンド開始時に押していた技ボタンは、一度離すまで とくぎ判定に入らない', () => {
  /* ⚠️ ドラフト段階では「押しっぱなしで とくぎが暴発する」を直接測るつもりだったが、
     doSpecial は p.chicken を持っている時しか撃たず、resetPlayersForRound が
     ラウンド頭で chicken を消すので、そのままでは差が出ない（常に緑になる）。
     実害が出るのは「押しっぱなしのまま走り回って 🍗 を拾った瞬間」なので、
     そこを測る。仕様変更（actFired=true）を外すとこのテストは落ちる。 */
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  X.G.phase = 'roundEnd';
  padPoll(fakePad([0, 1]));                 // A でバナー送り。B（技）は押しっぱなし
  eq(X.players[0].actFired, true, 'ラウンド開始時に actFired が立っていない（仕様変更が入っていない）');
  X.applyItem(X.players[0], X.IT_CHICKEN);  // 押しっぱなしのまま 🍗 を拾う
  X.items.length = 0;
  for (let i = 0; i < 60; i++) { padPoll(fakePad([1])); X.humanUpdate(X.players[0], 1 / 60); }
  eq(X.players[0].chicken, 'rabbit', '押しっぱなしのまま とくぎが暴発した');
  padPoll(fakePad([]));                     // 指を離す
  X.humanUpdate(X.players[0], 1 / 60);
  eq(X.players[0].actFired, false, '離しても actFired が戻らない');
  for (let i = 0; i < 60; i++) { padPoll(fakePad([1])); X.humanUpdate(X.players[0], 1 / 60); }
  eq(X.players[0].chicken, null, '押し直しても とくぎが出ない（入力を殺している）');
  padOff();
  return '押しっぱなし=不発 / 離して押し直し=発動';
});

t('パッド: エッジは押した瞬間の1回だけ', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  padPoll(fakePad([0]));
  ok(X.pressed.has('Pad:A'), '押した瞬間のエッジが立たない');
  X.pressed.clear();
  for (let i = 0; i < 5; i++) padPoll(fakePad([0]));
  eq(X.pressed.size, 0, '押しっぱなしでエッジが立ち続けている（連射になる）');
  ok(X.keys.has('Pad:A'), 'hold は立っているべき');
  padOff();
  return '1回だけ';
});

t('パッド: 十字キーとスティックが同じ合成コードになる', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  padPoll(fakePad([14]));                              // 十字 左
  ok(X.keys.has('Pad:Left'), '十字 左が入らない');
  padOff();
  padPoll(fakePad([], [-0.9, 0, 0, 0]));               // スティック 左
  ok(X.keys.has('Pad:Left'), 'スティック 左が入らない');
  /* 両方倒してから十字だけ離す。出どころ別のコードに分けていると
     ここで Pad:Left が消える（＝スティックを倒しているのに止まる） */
  padPoll(fakePad([14], [-0.9, 0, 0, 0]));
  padPoll(fakePad([], [-0.9, 0, 0, 0]));
  ok(X.keys.has('Pad:Left'), '十字を離した瞬間にスティックの入力まで消えた');
  padOff();
  return '十字・スティック・併用すべて Pad:Left';
});

t('パッド: スティックは優勢な軸だけを採る（斜めで横に流れない）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  padPoll(fakePad([], [0.5, -0.87, 0, 0]));            // 真上から30°
  ok(X.keys.has('Pad:Up'), '上が入らない');
  eq(X.keys.has('Pad:Right'), false, '横も同時に入った（movePlayer の水平優先で必ず横に歩く）');
  padOff();
  return '上だけ';
});

t('パッド: デッドゾーンは入り0.5／抜け0.35（ヒステリシス）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  padPoll(fakePad([], [0.49, 0, 0, 0]));
  eq(X.keys.has('Pad:Right'), false, '0.49 で入ってしまった（ドリフトを拾う）');
  padPoll(fakePad([], [0.51, 0, 0, 0]));
  ok(X.keys.has('Pad:Right'), '0.51 で入らない');
  padPoll(fakePad([], [0.40, 0, 0, 0]));
  ok(X.keys.has('Pad:Right'), '0.40 で抜けた（ヒステリシスが効いていない＝境界で向きがバタつく）');
  padPoll(fakePad([], [0.30, 0, 0, 0]));
  eq(X.keys.has('Pad:Right'), false, '0.30 でも抜けない');
  padOff();
  return '0.49✗ 0.51✓ 0.40✓ 0.30✗';
});

t('パッド: index 0 が null でも拾う（実機は index 1 だった）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  X.pollGamepads([null, fakePad([0])]);
  eq(X.PAD.on, true, 'index 1 のパッドを見つけられない（pads[0] 決め打ちになっている）');
  ok(X.keys.has('Pad:A'), 'ボタンが注入されていない');
  eq(X.PAD.index, 1, 'ラッチした index が違う');
  padOff();
  return 'index 1 を拾えた';
});

t('パッド: 使用中のパッドから勝手に乗り換えない', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  X.pollGamepads([null, fakePad([])]);                 // index 1 を掴む
  eq(X.PAD.index, 1, '掴めていない');
  const other = fakePad([]); other.index = 0;          // あとから index 0 が目を覚ます
  X.pollGamepads([other, fakePad([])]);
  eq(X.PAD.index, 1, '試合中に別のパッドへ選択が移った（操作が突然効かなくなる）');
  padOff();
  return 'index 1 のまま';
});

t('パッド: 切断したら押下が残らない（電池切れで歩きっぱなしにならない）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  padPoll(fakePad([15]));                              // 右を入れる
  ok(X.keys.has('Pad:Right'), '右が入らない');
  X.pollGamepads([]);                                  // 電池切れ／Bluetooth 切断
  eq(X.keys.has('Pad:Right'), false, '最後の入力が残って壁に向かって歩き続ける');
  eq(X.PAD.on, false, 'PAD.on が落ちていない');
  padOff();
  return '切断で解放';
});

t('パッド: 非標準マッピングは無視する', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  const odd = fakePad([0]); odd.mapping = '';
  X.pollGamepads([odd]);
  eq(X.PAD.on, false, '非標準を掴んでしまった（ボタン番号が製品ごとに違うので当て推量になる）');
  eq(X.keys.has('Pad:A'), false, '非標準のボタンを注入してしまった');
  padOff();
  return '無視した';
});

t('パッド: navigator に getGamepads が無くても落ちない（テストハーネスのテスト）', () => {
  /* ⛔ Node 26 には navigator が「存在する」（getGamepads だけ無い）。
     typeof navigator !== 'undefined' でガードすると素通りして TypeError になる */
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  X.pollGamepads();                                    // 引数なし＝素の navigator を見に行く
  eq(X.PAD.on, false, 'getGamepads が無いのに掴んだことになっている');
  padOff();
  return '例外なし';
});

t('パッド: 2人プレイでは操作にもポーズにも効かない（1台に1人ぶん）', () => {
  fresh({ p1: 'rabbit', p2: 'frog', mode: '2p', clear: true });
  padOff();
  const paused0 = X.G.paused;
  padPoll(fakePad([9]));                               // Start
  eq(X.G.paused, paused0, '2人プレイでパッドのポーズが効いた（肘が当たって止まる）');
  padPoll(fakePad([0]));                               // A
  eq(X.keys.has('Pad:A'), false, '2人プレイでパッドのボタンが注入された');
  /* ⭐ prev は 2p 中も更新されている、のテスト。
     ここで早期 return して prev を止めると、1p に戻ったとき
     ①離したはずのボタンが押しっぱなし扱い ②押し直してもエッジが立たない */
  X.CFG.mode = '1p';
  padPoll(fakePad([0]));                               // A を押しっぱなしのまま 1p へ
  eq(X.pressed.has('Pad:A'), false, '2p で押していたボタンが 1p 復帰で偽エッジになった');
  padOff();
  return '注入なし・prev は最新';
});

t('パッド: Start を押しっぱなしにしてもポーズが即解除されない（pressed の掃除に依存しない）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  X.G.phase = 'play'; X.G.paused = false;
  padPoll(fakePad([9]));                    // Start
  eq(X.G.paused, true, 'Start でポーズできない');
  /* ⛔ ここで pressed.clear() を挟まない。画面遷移のトリガに pressed.has() を使うと
     「loop() の末尾が毎フレーム掃除してくれる」前提に依存する。その前提は
     ハーネスが loop() を呼ばないのでテストで守れず、将来 loop の構造が変わると
     Start 押しっぱなしでポーズが即解除される形で静かに壊れる */
  padPoll(fakePad([9]));
  eq(X.G.paused, true, '押しっぱなしでポーズが自己解除された');
  padPoll(fakePad([]));                     // 離す
  padPoll(fakePad([9]));                    // 押し直し
  eq(X.G.paused, false, '押し直しで解除できない');
  X.G.paused = false;
  padOff();
  return '押しっぱなし=維持 / 押し直し=解除';
});

t('LAN: 自分から切ったときは onclose の後始末が走らない', () => {
  /* onclose は「意図しない切断」の後始末（backToSetup）を持っている。
     ロビーの「もどる」など自分から切る経路でこれが走ると、非同期に画面と raf を
     畳みにくるので、その間に始めた1人プレイが止まる */
  let closed = false;
  const fake = { close() { closed = true; if (this.onclose) this.onclose(); },
                 onclose: () => { throw new Error('自分から切ったのに onclose が走った'); } };
  X.NET.ws = fake; X.NET.role = 'guest';
  try { X.NET.disconnect(); } finally { X.NET.ws = null; X.NET.role = null; }
  ok(closed, 'close() が呼ばれていない');
  eq(X.NET.role, null, 'role が消えていない');
  return '自分から切る経路では onclose 不発';
});

t('パッド: ゲストは Start を押してもポーズできない', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  const paused0 = X.G.paused;
  X.NET.role = 'guest';
  try { padPoll(fakePad([9])); } finally { X.NET.role = null; }
  eq(X.G.paused, paused0, 'ゲストが試合を止められてしまった');
  padOff();
  return 'ポーズ不可';
});

t('ゲストは advanceBanner でラウンドを進められない（キーボード・ボタン・パッドの3経路をまとめて塞ぐ）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  X.G.phase = 'roundEnd';
  const r0 = X.G.round;
  X.NET.role = 'guest';
  try { X.advanceBanner(); } finally { X.NET.role = null; }
  eq(X.G.round, r0, 'ゲストがラウンドを進めた（ホストと無関係な盤面ができる）');
  return 'ラウンド不変';
});

t('パッドの割り当ては solo だけ（1台に1人ぶん）', () => {
  const pads = (c) => [].concat(c.up, c.down, c.left, c.right, c.bomb, c.act)
                        .filter(k => k.startsWith('Pad:'));
  ok(pads(X.CONTROLS.solo).length > 0, 'solo にパッドが1つも入っていない');
  eq(pads(X.CONTROLS.p1).length, 0, 'p1 にパッドが入っている（1台で2人あそぶ時に両方動く）');
  eq(pads(X.CONTROLS.p2).length, 0, 'p2 にパッドが入っている');
  const c = X.CONTROLS.solo;
  const move = new Set([].concat(c.up, c.down, c.left, c.right).filter(k => k.startsWith('Pad:')));
  for (const k of c.bomb) if (k.startsWith('Pad:')) ok(!move.has(k), `${k} が移動と爆弾で重複`);
  for (const k of c.act)  if (k.startsWith('Pad:')) ok(!move.has(k), `${k} が移動と技で重複`);
  for (const k of c.bomb) if (k.startsWith('Pad:')) ok(!c.act.includes(k), `${k} が爆弾と技で重複`);
  return `solo に ${pads(X.CONTROLS.solo).length} 個・交差ゼロ`;
});

t('CONTROLS.solo の Pad: コードが全部 PAD_BTN に存在する（タイポ検出）', () => {
  /* これが無いと 'Pad:RB' のような存在しないコードを書いても全テストが通る
     （どこにも注入されないので、ただ効かないだけ） */
  const known = new Set(X.PAD_BTN.filter(Boolean));
  const c = X.CONTROLS.solo;
  for (const k of [].concat(c.up, c.down, c.left, c.right, c.bomb, c.act)) {
    if (k.startsWith('Pad:')) ok(known.has(k), `${k} は PAD_BTN に無い（タイポ）`);
  }
  return `${known.size} 個の合成コードと照合`;
});

t('パッド: LAN のゲストが送る入力にもパッドが乗る（ネットコード無改造で通ることの証明）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  padPoll(fakePad([0, 15]));                           // A ＋ 十字 右
  const msg = X.NET.buildInput(X.CONTROLS.solo);
  eq(msg.right, true, 'ゲストの送信データに右が乗らない');
  eq(msg.bomb, true, 'ゲストの送信データに爆弾が乗らない');
  eq(msg.left, false, '押していない左が乗っている');
  padOff();
  return 'buildInput に {right, bomb}';
});

t('パッド: 右を倒すと枠が右へ動く（humanUpdate まで通る）', () => {
  fresh({ p1: 'rabbit', mode: '1p', clear: true });
  padOff();
  const p = X.players[0];
  const x0 = p.cx;
  for (let i = 0; i < 10; i++) { padPoll(fakePad([], [1, 0, 0, 0])); X.humanUpdate(p, 1 / 60); }
  ok(p.cx > x0 + 0.1, `右へ動いていない (${x0.toFixed(2)} → ${p.cx.toFixed(2)})`);
  eq(p.dir, 'right', '向きが右になっていない');
  padOff();
  return `${x0.toFixed(2)} → ${p.cx.toFixed(2)}`;
});

/* ============ 13. メニューのカーソル（コントローラー・矢印キー） ============ */

/** メニューでボタンを「押して離す」。エッジを1回だけ立てる。
    ⛔ 押しっぱなしにしない。pollGamepads は PAD.prev との差分でエッジを作るので、
       離さずに2回呼んでも2回目は何も起きない（それ自体が下のテストの対象） */
const menuTap = (btn) => { padPoll(fakePad([btn])); padPoll(null); };

/** カーソルが既に出ている状態から始める。
    最初の一押しは「枠を出すだけ」に使われる仕様なので、その分を先に済ませる */
const menuWake = () => { X.MENU.on = true; };

t('メニュー: 最初の一押しは枠を出すだけで、決定は飛ばない', () => {
  padOff();
  X.CFG.mode = '1p';
  X.showScreen('title');
  X.MENU.on = false;
  eq(X.MENU.on, false, '前提：枠は出ていない');
  menuTap(0);                                   // いきなり A
  eq(X.MENU.on, true, '枠が出ていない');
  eq(X.G.phase, 'title', 'A が決定として消費された（持ち替えた瞬間に画面が飛ぶ）');
  padOff();
  return '枠が出るだけ・画面は title のまま';
});

t('メニュー: タイトルで十字下を押すとカーソルが1つ下へ動く', () => {
  padOff();
  X.CFG.mode = '1p';
  X.showScreen('title');
  menuWake(); X.MENU.gi = 0; X.MENU.ii = 0;
  menuTap(13);                                  // 十字下
  eq(X.MENU.gi, 1, 'カーソルが動いていない');
  menuTap(13);
  eq(X.MENU.gi, 2, '2回目が効いていない');
  menuTap(12);                                  // 十字上
  eq(X.MENU.gi, 1, '上で戻っていない');
  padOff();
  return 'gi 0→1→2→1';
});

t('メニュー: タイトルのボタンは縦並びなので上下で移る（左右では移らない）', () => {
  padOff();
  X.CFG.mode = '1p';
  X.showScreen('title');
  menuWake(); X.MENU.gi = 0; X.MENU.ii = 0;
  menuTap(15);                                  // 十字右
  eq(X.MENU.gi, 0, '左右で縦の並びを辿っている（グループの切り方が違う）');
  eq(X.MENU.ii, 0, '1グループ1項目なのに ii が動いた');
  padOff();
  return '左右では動かない';
});

t('メニュー: A を押すと そのボタンのクリックが走る（タイトル→キャラ選択）', () => {
  padOff();
  X.CFG.mode = 'vs';
  X.showScreen('title');
  menuWake(); X.MENU.gi = 0; X.MENU.ii = 0;     // tm1 =「1人 vs CPU×3」
  menuTap(0);                                   // A
  eq(X.G.phase, 'pick', 'キャラ選択へ進んでいない');
  eq(X.CFG.mode, '1p', 'tm1 のハンドラ（CFG.mode を書く）が走っていない');
  padOff();
  return 'phase=pick / mode=1p';
});

t('メニュー: B を押すと1つ前の画面へ戻る', () => {
  padOff();
  X.CFG.mode = '1p';
  X.showScreen('rules');
  menuWake();
  menuTap(1);                                   // B
  eq(X.G.phase, 'pick', 'rules から pick へ戻っていない');
  menuTap(1);
  eq(X.G.phase, 'title', 'pick から title へ戻っていない');
  padOff();
  return 'rules → pick → title';
});

t('メニュー: タイマンを選んでもカーソルが動く（active ゲートの外にあることのテスト）', () => {
  padOff();
  /* ⛔ このテストが守っているもの：エッジ(hit)を active の内側で作ると、
     CFG.mode が 2p/vs のときメニューのカーソルが一切動かなくなる。
     しかも backToSetup は CFG.mode を戻さないので、一度タイマンを選ぶと
     タイトルに戻っても直らない＝「急にコントローラーが効かなくなった」になる */
  X.CFG.mode = 'vs';
  X.showScreen('title');
  menuWake(); X.MENU.gi = 0; X.MENU.ii = 0;
  menuTap(13);
  eq(X.MENU.gi, 1, 'タイマン中にカーソルが死んでいる（hit が active の中で作られている）');
  X.CFG.mode = '1p';
  padOff();
  return 'mode=vs でも動く';
});

t('メニュー: 試合中はメニューのカーソルが動かない', () => {
  fresh({ mode: '1p', clear: true });
  padOff();
  eq(X.G.phase, 'play', '前提：試合中');
  const gi0 = X.MENU.gi;
  menuWake();
  menuTap(13);
  eq(X.MENU.gi, gi0, '試合中に十字下でメニューのカーソルが動いた');
  padOff();
  return 'phase=play では無反応';
});

t('メニュー: MENU_SLOT の行き先が全部 MENU_ORDER に実在する（タイポ検出）', () => {
  const bad = [];
  for (const id of Object.keys(X.MENU_SLOT)) {
    const [sc, gr] = X.MENU_SLOT[id];
    const order = X.MENU_ORDER[sc];
    if (!order) { bad.push(`${id}: 画面 '${sc}' が MENU_ORDER に無い`); continue; }
    if (!order.includes(gr)) bad.push(`${id}: '${sc}' に グループ '${gr}' が無い`);
  }
  ok(bad.length === 0, bad.join(' / '));
  return `${Object.keys(X.MENU_SLOT).length} 個の行き先を照合`;
});

t('メニュー: MENU_SLOT の id が HTML に実在する（DOM スタブでは捕まらない）', () => {
  /* ⛔ document.getElementById はハーネスではどんな id でも要素を返すので、
     id のタイポは実行時に一切エラーにならない。生の HTML を見るしかない */
  const bad = Object.keys(X.MENU_SLOT).filter(id => !src.includes(`id="${id}"`));
  ok(bad.length === 0, `HTML に無い id: ${bad.join(', ')}`);
  return `${Object.keys(X.MENU_SLOT).length} 個の id を HTML と照合`;
});

t('メニュー: KEY_TO_PAD の行き先が全部 PAD_BTN に実在する（タイポ検出）', () => {
  const known = new Set(X.PAD_BTN.filter(Boolean));
  const bad = Object.keys(X.KEY_TO_PAD).filter(k => !known.has(X.KEY_TO_PAD[k]));
  ok(bad.length === 0, `PAD_BTN に無い: ${bad.map(k => `${k}→${X.KEY_TO_PAD[k]}`).join(', ')}`);
  return `${Object.keys(X.KEY_TO_PAD).length} 個`;
});

t('メニュー: ビルダーを何度呼んでも名簿が二重にならない', () => {
  /* ⛔ これが落ちるのは MENU.clear を忘れたとき。キャラを1個選ぶたびに
     名簿が倍に増え、カーソルが「見えない残骸」の上を回るようになる */
  X.CFG.mode = '1p';
  X.showScreen('pick');
  const n1 = X.MENU.reg.pick.p1.length;
  X.buildPickers();
  X.buildPickers();
  eq(X.MENU.reg.pick.p1.length, n1, `名簿が増えた (${n1} → ${X.MENU.reg.pick.p1.length})`);
  return `${n1} 個のまま`;
});

t('メニュー: 1人プレイに切り替えると 2P のぶんが名簿から消える', () => {
  X.CFG.mode = 'vs';
  X.showScreen('pick');
  ok(X.MENU.reg.pick.p2.length > 0, '前提：タイマンでは 2P の動物が並ぶ');
  X.CFG.mode = '1p';
  X.buildPickers();
  eq(X.MENU.reg.pick.p2.length, 0, '1人プレイなのに 2P の動物カードが名簿に残っている');
  return 'p2 が 0 個になる';
});

t('メニュー: HP の行が減るモードで名簿も減る（rules）', () => {
  X.CFG.mode = 'vs';          // vs は hpP1 / hpP2 の2行（hpCPU は出ない）
  X.showScreen('rules');
  eq(X.MENU.reg.rules.hp2.length, 0, 'タイマンなのに3行目が名簿に残っている');
  X.CFG.mode = '1p';          // 1p は hpP1 / hpCPU の2行
  X.buildHpRows();
  eq(X.MENU.reg.rules.hp2.length, 0, '1人プレイなのに3行目が名簿に残っている');
  ok(X.MENU.reg.rules.hp0.length > 0, '1行目が空');
  return 'hp2 は常に空・hp0 は埋まる';
});

t('メニュー: 「せつぞくを切る」は即座に切らず確認を出す', () => {
  /* 作者の指示（2026-09-20）：B でも「せつぞくを切る」でも、切断の前に必ず確認。
     ⛔ confirm() は使わない（コントローラーで押せないダイアログになる） */
  X.MENU.dialog = null;
  let cut = 0;
  const realDisconnect = X.NET.disconnect;
  X.NET.disconnect = () => { cut++; };
  X.askDisconnect();
  eq(cut, 0, '確認を出さずに切断した');
  ok(!!X.MENU.dialog, '確認ダイアログが名簿に載っていない');
  eq(X.MENU.dialog.items.length, 2, '選択肢が2つでない');
  eq(X.MENU.ii, 0, 'カーソルが危ない方（切る）に乗っている');
  X.MENU.dialog.items[1].act();               // 「せつぞくを切る」を選ぶ
  eq(cut, 1, '確認したのに切断されていない');
  eq(X.MENU.dialog, null, 'ダイアログが閉じていない');
  X.NET.disconnect = realDisconnect;
  return '確認 → 切断の順に通る';
});

t('メニュー: 確認ダイアログ中はカーソルがダイアログの中だけを回る', () => {
  X.CFG.mode = '1p';
  X.showScreen('title');
  X.MENU.dialog = null;
  X.askConfirm('テスト', 'やる', () => {});
  const gs = X.MENU.list();
  eq(gs.length, 1, 'ダイアログ以外のグループが混ざっている');
  eq(gs[0].length, 2, '選択肢が2つでない');
  menuWake();
  menuTap(15);                                 // 右
  eq(X.MENU.ii, 1, 'ダイアログの中で右へ動かない');
  menuTap(1);                                  // B = やめる
  eq(X.MENU.dialog, null, 'B でダイアログが閉じない');
  padOff();
  return '2択の中だけを回り、B で閉じる';
});

t('メニュー: チップを押し直しても名簿が二重にならない', () => {
  /* ⛔ chips() はクリックのたびに自分を呼んで DOM を作り直す。
     その中の MENU.clear を落とすと、押すたびに名簿が伸びて
     カーソルが「もう画面に無いチップ」の上を回るようになる。
     buildPickers / buildHpRows は自前で clear するので、
     この経路は chips の clear でしか守れない */
  X.CFG.mode = '1p';
  X.showScreen('rules');
  const n1 = X.MENU.reg.rules.wins.length;
  ok(n1 > 1, '前提：勝数のチップが複数ある');
  X.MENU.reg.rules.wins[1].act();
  eq(X.MENU.reg.rules.wins.length, n1, `1回押して名簿が伸びた (${n1} → ${X.MENU.reg.rules.wins.length})`);
  X.MENU.reg.rules.wins[0].act();
  eq(X.MENU.reg.rules.wins.length, n1, '2回押して名簿が伸びた');
  return `${n1} 個のまま`;
});

t('メニュー: 隠れているボタンにはカーソルが乗らない', () => {
  /* ロビーの「はじめる ▶」はゲスト側で display:none になる。
     ⛔ 飛ばさないと、ゲストが押しても何も起きないボタンにカーソルが止まる */
  X.CFG.mode = '1p';
  if (!X.NET.roster) X.NET.roster = new Set();
  X.showScreen('lobby');                    // NET.role は null ＝ ゲスト扱い
  const el = document.getElementById('lobbyStart');
  eq(el.style.display, 'none', '前提：ゲストでは「はじめる ▶」が隠れる');
  const flat = [].concat(...X.MENU.list());
  ok(!flat.some(it => it.el === el), '隠れているボタンが名簿に出てきた');
  X.showScreen('title');
  return 'ゲストの名簿に「はじめる ▶」が出ない';
});

t('メニュー: 枠が出ていなくても十字は効く（飲み込むのは決定だけ）', () => {
  /* ⛔ 枠は mousemove のたびに消える。移動まで飲み込むと、マウスに少し触れた
     あとの一押しが毎回捨てられて「たまに効かない」になる */
  padOff();
  X.CFG.mode = '1p';
  X.showScreen('title');
  X.MENU.on = false; X.MENU.gi = 0; X.MENU.ii = 0;
  menuTap(13);                                  // 枠が出ていない状態で十字下
  eq(X.MENU.on, true, '枠が出ていない');
  eq(X.MENU.gi, 1, '一押し目の移動が飲み込まれた');
  X.MENU.on = false;
  menuTap(1);                                   // 枠が出ていない状態で B
  eq(X.G.phase, 'title', '前提：title の B は行き先が無い');
  padOff();
  return '移動は通る・決定だけ飲む';
});

t('メニュー: 設定画面へ戻ると枠が消える（触るまで出ない）', () => {
  padOff();
  X.CFG.mode = '1p';
  X.showScreen('title');
  X.MENU.on = true;
  X.backToSetup();
  eq(X.MENU.on, false, '試合から戻ったのに枠が出たまま（触っていないのに光る）');
  padOff();
  return 'backToSetup で枠が消える';
});

t('メニュー: 確認ダイアログ中に画面を畳まれても残骸が残らない', () => {
  /* ホストが落ちると ws.onclose → backToSetup が走る。ゲストがちょうど
     「せつぞくを切りますか？」を開いていると、名簿だけダイアログのまま残る */
  X.CFG.mode = '1p';
  X.MENU.dialog = null;
  X.askConfirm('テスト', 'やる', () => {});
  ok(!!X.MENU.dialog, '前提：ダイアログが開いている');
  X.backToSetup();
  eq(X.MENU.dialog, null, 'ダイアログの名簿が残っている');
  return 'backToSetup が畳む';
});

t('メニュー: リザルト画面で「設定をやりなおす」にカーソルが届く', () => {
  /* ⛔ 2026-09-20 実機で作者が発見。A が advanceBanner 直結だった v4.0.0 では
     「⚙ 設定をやりなおす」にコントローラーから永久に辿りつけなかった */
  fresh({ mode: '1p', clear: true });
  padOff();
  X.G.phase = 'roundEnd';
  X.MENU.reset();
  X.MENU.on = true; X.MENU.gi = 0; X.MENU.ii = 0;
  const gs = X.MENU.list();
  eq(gs.length, 2, 'リザルト画面のボタンが2つ名簿に出ていない');
  menuTap(13);                                  // 十字下
  eq(X.MENU.gi, 1, '下が効かない（「設定をやりなおす」へ行けない）');
  const it = X.MENU.list()[1][0];
  it.act();                                     // ＝ backToSetup
  ok(X.G.phase !== 'roundEnd', '「設定をやりなおす」が実行されていない');
  padOff();
  return '「つぎのラウンド ▶」→「⚙ 設定をやりなおす」';
});

t('メニュー: リザルト画面の A は枠が出ていなくても1回目から効く', () => {
  /* ⛔ 「最初の一押しは枠を出すだけ」をここに適用すると、
     A＝次へ の1回目が毎回捨てられ、事故#11 のテストも落ちる */
  fresh({ mode: '1p', clear: true });
  padOff();
  X.G.phase = 'roundEnd';
  X.MENU.reset();
  X.MENU.on = false;                            // 枠が出ていない状態から
  menuTap(0);                                   // A
  eq(X.G.phase, 'play', 'バナーで A の1回目が飲み込まれた');
  padOff();
  return '枠が無くても1回目で進む';
});

t('メニュー: 優勝したあとの画面でも「もういっかい」と「設定をやりなおす」を選べる', () => {
  /* ラウンド終わり（roundEnd）と優勝（over）は同じ2つのボタンを使い回していて、
     上の文字だけが「つぎのラウンド ▶」→「もういっかい」に変わる。
     ⛔ 名簿は画面ごとなので、roundEnd に登録しただけでは over で空になる */
  fresh({ mode: '1p', clear: true });
  padOff();
  X.G.phase = 'over';
  X.MENU.reset();
  X.MENU.on = true; X.MENU.gi = 0; X.MENU.ii = 0;
  const gs = X.MENU.list();
  eq(gs.length, 2, '優勝の画面でボタンが2つ名簿に出ていない');
  eq(gs[0][0].el, document.getElementById('bAgain'), '1つ目が「もういっかい」でない');
  eq(gs[1][0].el, document.getElementById('bSetup'), '2つ目が「設定をやりなおす」でない');
  menuTap(13);
  eq(X.MENU.gi, 1, '下が効かない（「設定をやりなおす」へ行けない）');
  menuTap(12);
  eq(X.MENU.gi, 0, '上で戻れない');
  padOff();
  return 'もういっかい ↕ 設定をやりなおす';
});

/* ============ ロビーのカーソル（v4.2.0） ============ */

t('★ロビーでキャラを選んでもカーソルがその場に残る（1P の左上へ飛ばない）', () => {
  /* ⛔ 2026-09-20 実機。作者「選んだキャラに黄色いカーソルは残るけど、
     コントローラーの現在地を表す白い枠が 1P の左上のうさぎに毎回もどる」。
     真因は chips() の末尾の MENU.refresh()（= clamp + paint）が、
     buildLobby の「名簿の組み立て途中」で走ること。そのとき名簿には
     humans と nav の2グループしか無いので、gi/ii がそこへ丸められる。
     キャラカードはそのあと足されるが、丸められた値はもう戻らない。 */
  X.NET.role = 'host'; X.NET.seat = 0; X.NET.roster = new Set([0, 1]);
  Object.assign(X.CFG, { mode: 'lan', lanHumans: 2,
    lanPicks: ['rabbit', 'frog', 'fox', 'elephant'],
    cpuLevel: ['futsu', 'futsu', 'futsu'] });
  X.showScreen('lobby');
  X.buildLobby();
  X.MENU.on = true;

  // キャラ列のグループ番号を拾う（登録時の className に .acard が入る）
  const cardGroups = [];
  X.MENU.list().forEach((g, i) => {
    if (g[0] && String(g[0].base || '').indexOf('acard') >= 0) cardGroups.push(i);
  });
  ok(cardGroups.length >= 3, `キャラ列が3つ以上見つからない（${cardGroups.length}）`);

  X.MENU.gi = cardGroups[2];   // 3枠目のキャラ列（先頭から離れた所を選ぶ）
  X.MENU.ii = 2;
  X.MENU.paint();
  const g0 = X.MENU.gi, i0 = X.MENU.ii;

  X.MENU.list()[g0][i0].act();          // ＝そのキャラを選ぶ

  eq(X.MENU.gi, g0, 'キャラを選んだらグループが動いた');
  eq(X.MENU.ii, i0, 'キャラを選んだら項目が動いた');
  X.NET.role = null; X.NET.seat = null; X.NET.roster = new Set();
  X.MENU.on = false;
  return `gi=${g0} ii=${i0} を保持`;
});

t('★ロビーでグループが減ってもカーソルは名簿の中へ丸められる', () => {
  /* 上の直しで chips() から clamp を外したので、丸めるのは
     ビルダー末尾の MENU.refresh() だけになった。その唯一の担い手のテスト。
     ⛔ これが無いと、グループが減った瞬間にカーソルが消えたグループを指したまま
        になり、A を押すと存在しないボタンの act が走る。
     ⚠️ 人数を「増やす」と名簿は縮む。CPU 枠の強さチップが消えるから
        （1人 = humans+pick0..3+cpu1..3+nav で 9、4人 = humans+pick0..3+nav で 6）。
        減る向きを取り違えると、丸めが要らない側を試して緑のままになる。 */
  X.NET.role = 'host'; X.NET.seat = 0; X.NET.roster = new Set([0, 1, 2, 3]);
  Object.assign(X.CFG, { mode: 'lan', lanHumans: 1,
    lanPicks: ['rabbit', 'frog', 'fox', 'elephant'],
    cpuLevel: ['futsu', 'futsu', 'futsu'] });
  X.showScreen('lobby');
  X.buildLobby();
  X.MENU.on = true;

  const wide = X.MENU.list().length;
  X.MENU.gi = wide - 1; X.MENU.ii = 0;   // いちばん後ろのグループ（はじめる ▶）

  X.CFG.lanHumans = 4;                   // CPU 枠が消える＝グループが減る
  X.buildLobby();

  const gs = X.MENU.list();
  ok(gs.length < wide, `グループが減っていない（${wide} → ${gs.length}）＝このテストは効いていない`);
  ok(X.MENU.gi < gs.length, `gi=${X.MENU.gi} が名簿の外（グループ数 ${gs.length}）`);
  ok(X.MENU.ii < gs[X.MENU.gi].length,
     `ii=${X.MENU.ii} が名簿の外（そのグループは ${gs[X.MENU.gi].length} 個）`);
  X.NET.role = null; X.NET.seat = null; X.NET.roster = new Set();
  X.MENU.on = false;
  return `${wide} グループ → ${gs.length} グループ、カーソルは中に収まる`;
});

/* ============ LAN の体力（v4.2.0 で足したもの） ============ */

/** LAN の4枠を、体力だけ指定して立てる */
function lanBoard(hp, opts = {}) {
  Object.assign(X.CFG, {
    mode: 'lan',
    lanHumans: opts.humans ?? 4,
    lanHp: hp.slice(),
    lanPicks: opts.picks || ['rabbit', 'frog', 'fox', 'mole'],
    cpuLevel: ['futsu', 'futsu', 'futsu'],
    /* ⛔ 1p/2p/vs 用の3つはわざと別の値にしておく。3P/4P が 1P の枠に
       落ちていたら（v4.1.0 までの makePlayer の label==='2P' 判定）、
       maxHp がこの 6 になるので一発で分かる */
    hpP1: 6, hpP2: 6, hpCPU: 6,
    time: 180, sudden: true, sfx: false, bgm: false,
  });
  X.startGame();
  return X.players;
}

t('★LAN: 4枠の体力を1つずつ設定できる（3P/4P が 1P と共有しない）', () => {
  /* ⛔ 2026-09-20 に実装中に発見。makePlayer のスロット判定は
       o.isCPU ? 'cpu' : (o.label==='2P' ? 'p2' : 'p1')
     で、setupPlayersLan は 1P〜4P を振るので 3P と 4P が p1 に落ちていた。
     家族の「体力を増やしたい」要望に答えられなかったのはこれ */
  const ps = lanBoard([1, 2, 3, 4]);
  eq(ps.length, 4, '4枠そろっていない');
  ps.forEach((p, i) => {
    const want = [1, 2, 3, 4][i] + (p.animal.hpBonus || 0);
    eq(p.maxHp, want, `${i + 1}P の maxHp`);
    eq(p.hp, want, `${i + 1}P の hp`);
  });
  return ps.map(p => p.maxHp).join(' / ');
});

t('★LAN: ラウンドが変わっても4枠の体力が保たれる', () => {
  /* ⛔ resetPlayersForRound が baseHpOf(p.hpSlot) で毎ラウンド引き直す。
     makePlayer だけ直して p.hpSlot をそのままにすると、
     1ラウンド目だけ正しくて2ラウンド目から 1P の値に戻る
     ——「最初は効いていたのに途中から違う」のがいちばん追いにくい */
  const ps = lanBoard([1, 2, 3, 4]);
  ps.forEach(p => { p.hp = 1; p.maxHp = 1; });    // 試合で削られた状態にする
  X.resetPlayersForRound();
  X.players.forEach((p, i) => {
    const want = [1, 2, 3, 4][i] + (p.animal.hpBonus || 0);
    eq(p.maxHp, want, `${i + 1}P の maxHp（次ラウンド）`);
  });
  return X.players.map(p => p.maxHp).join(' / ');
});

t('★LAN: 動物ごとの体力ボーナス（ぞう +1）は LAN でも乗る', () => {
  // ⚠️ 直接指定の口を作るときに hpBonus を足し忘れると、ぞうの硬さが消える
  const ps = lanBoard([2, 2, 2, 2], { picks: ['elephant', 'rabbit', 'frog', 'fox'] });
  eq(X.ANIMALS.elephant.hpBonus, 1, '前提: ぞうの hpBonus が 1 でない');
  eq(ps[0].maxHp, 3, 'ぞうの体力（2 + ボーナス1）');
  eq(ps[1].maxHp, 2, 'うさぎの体力');
  return `ぞう ${ps[0].maxHp} / うさぎ ${ps[1].maxHp}`;
});

t('★LAN: lanHp が未設定でも落ちない（古い設定から上がってきた時の既定）', () => {
  // ⛔ ゲストが古い版から begin を受けた場合など、lanHp が undefined でも動くこと
  const keep = X.CFG.lanHp;
  X.CFG.lanHp = undefined;
  Object.assign(X.CFG, { mode: 'lan', lanHumans: 2, hpP1: 6, hpP2: 6, hpCPU: 6,
    lanPicks: ['rabbit', 'frog', 'fox', 'mole'], sfx: false, bgm: false });
  X.startGame();
  X.players.forEach((p, i) => {
    ok(p.maxHp >= 1, `${i + 1}P の maxHp が壊れた（${p.maxHp}）`);
  });
  X.CFG.lanHp = keep;
  return X.players.map(p => p.maxHp).join(' / ');
});

/* ============ ロビーでルールを決める（v4.2.0） ============ */

/** ホストとしてロビーに立つ。戻り値は MENU.list() */
function lobbyAsHost(humans) {
  X.NET.role = 'host'; X.NET.seat = 0; X.NET.roster = new Set([0, 1, 2, 3]);
  Object.assign(X.CFG, {
    mode: 'lan', lanHumans: humans,
    lanPicks: ['rabbit', 'frog', 'fox', 'mole'],
    lanHp: [1, 1, 1, 1], cpuLevel: ['futsu', 'futsu', 'futsu'],
    wins: 3, time: 180, sudden: true, sfx: false, bgm: false,
  });
  X.showScreen('lobby');
  X.buildLobby();
  X.MENU.on = true;
  return X.MENU.list();
}
function lobbyOff() {
  X.NET.role = null; X.NET.seat = null; X.NET.roster = new Set();
  X.MENU.on = false;
}

t('★ロビーに4枠ぶんの体力と、勝利数・じかん・サドンデスが並ぶ', () => {
  /* ⛔ v4.1.0 のロビーはキャラと人数しか決められなかった。
     家族が「体力を増やしたい」と言ったとき、LAN では別モードを経由して
     ルールを通すという回避策しか無かった（2026-09-20） */
  lobbyAsHost(4);
  const reg = X.MENU.reg.lobby || {};
  for (const g of ['hp0', 'hp1', 'hp2', 'hp3', 'wins', 'time', 'sd']) {
    ok((reg[g] || []).length > 0, `ロビーに ${g} のグループが無い`);
  }
  // 名簿の順（MENU_ORDER.lobby）に載っていなければカーソルは届かない
  for (const g of ['hp0', 'hp1', 'hp2', 'hp3', 'wins', 'time', 'sd']) {
    ok(X.MENU_ORDER.lobby.indexOf(g) >= 0, `MENU_ORDER.lobby に ${g} が無い`);
  }
  lobbyOff();
  return `体力4枠 + 勝利数 + じかん + サドンデス`;
});

t('★ロビーの体力チップは枠ごとに独立して効く', () => {
  // ⛔ 4枠を1つずつ独立に、が作者の指示（2026-09-20）
  lobbyAsHost(4);
  const reg = X.MENU.reg.lobby;
  [0, 1, 2, 3].forEach(i => {
    const items = reg['hp' + i];
    ok(items.length >= 3, `hp${i} の選択肢が少ない（${items.length}）`);
    items[2].act();                       // 3番目 = 3回
  });
  eq(String(X.CFG.lanHp), '3,3,3,3', '体力が枠ごとに入っていない');
  reg.hp1[0].act();                        // 2P だけ 1回に戻す
  eq(String(X.CFG.lanHp), '3,1,3,3', '1枠だけ変えたつもりが他まで動いた');
  lobbyOff();
  return `lanHp=${X.CFG.lanHp}`;
});

t('★ロビーの勝利数・じかん・サドンデスが CFG に入る', () => {
  lobbyAsHost(2);
  const reg = X.MENU.reg.lobby;
  const w0 = X.CFG.wins, t0 = X.CFG.time;
  reg.wins[1].act();  ok(X.CFG.wins !== w0, '勝利数が変わらない');
  reg.time[0].act();  ok(X.CFG.time !== t0, 'じかんが変わらない');
  reg.sd[1].act();    eq(X.CFG.sudden, false, 'サドンデスを OFF にできない');
  reg.sd[0].act();    eq(X.CFG.sudden, true, 'サドンデスを ON に戻せない');
  lobbyOff();
  return `wins=${X.CFG.wins} time=${X.CFG.time} sudden=${X.CFG.sudden}`;
});

t('★ロビーのカーソルは「枠ごと」に縦へ進む（キャラ→強さ→体力→次の枠）', () => {
  /* ⭐ 上下＝グループ移動。1P の体力は 1P の情報なので、種類ごとに
     まとめず枠の中に置く（離すと画面を目で往復することになる）。
     作者の指示「置き方1がいい」（2026-09-20） */
  const order = X.MENU_ORDER.lobby;
  const at = g => order.indexOf(g);
  ok(at('humans') === 0, '先頭は人数のはず');
  for (let i = 0; i < 4; i++) {
    ok(at('pick' + i) < at('hp' + i), `${i}枠: キャラより体力が先に来ている`);
    ok(at('cpu' + i) < at('hp' + i), `${i}枠: CPU強さより体力が先に来ている`);
    if (i < 3) ok(at('hp' + i) < at('pick' + (i + 1)),
                  `${i}枠の体力が次の枠のキャラより後ろにある`);
  }
  ok(at('hp3') < at('wins'), '枠の設定より先に勝利数が来ている');
  ok(at('sd') < at('nav'), '「はじめる」より後ろにサドンデスがある');
  return order.join(' ');
});

t('★ゲストのロビーは名簿が空のまま（見るだけ・触れない）', () => {
  /* ⛔ ゲストが自分の CFG を書き換えても、begin でホストの cfg に
     上書きされるだけ。「選んだのに反映されない」体験を作らないため、
     ゲスト側は表示だけにする。カーソルが何も掴まないのが正しい状態 */
  X.NET.role = 'guest'; X.NET.seat = 1; X.NET.roster = new Set([0, 1]);
  Object.assign(X.CFG, { mode: 'lan', lanHumans: 2,
    lanPicks: ['rabbit', 'frog', 'fox', 'mole'], lanHp: [1, 2, 3, 4],
    cpuLevel: ['futsu', 'futsu', 'futsu'], sfx: false, bgm: false });
  X.showScreen('lobby');
  X.buildLobby();
  X.MENU.on = true;
  const gs = X.MENU.list();
  eq(gs.length, 0, `ゲストのロビーで名簿に ${gs.length} グループ出ている`);
  lobbyOff();
  return 'ゲストは何も掴まない';
});

/** rules 画面を組んで、カーソルをいちばん後ろのグループに置く */
function rulesCursorAtEnd(mode) {
  Object.assign(X.CFG, { mode, hpP1: 1, hpP2: 1, hpCPU: 1, sfx: false, bgm: false });
  X.showScreen('rules');
  X.MENU.on = true;
  const n = X.MENU.list().length;
  X.MENU.gi = n - 1; X.MENU.ii = 0;
  return n;
}
function rulesCursorInside(wide) {
  const gs = X.MENU.list();
  ok(gs.length < wide, `グループが減っていない（${wide} → ${gs.length}）＝このテストは効いていない`);
  ok(X.MENU.gi < gs.length, `gi=${X.MENU.gi} が名簿の外（グループ数 ${gs.length}）`);
  ok(X.MENU.ii < gs[X.MENU.gi].length, `ii=${X.MENU.ii} が名簿の外`);
  X.MENU.on = false;
  return `${wide} グループ → ${gs.length} グループ、カーソルは中に収まる`;
}

/* ⛔ 下の2本は buildHpRows / buildCpuRows を**1本ずつ**呼ぶ。
   まとめて呼ぶと、buildCpuRows の早期 return（`if (!n){ MENU.refresh(); return; }`）が
   両方の丸めを肩代わりしてしまい、**片方の refresh を消しても緑のまま通る**
   ——最初にそう書いて、逆向き確認で落ちないことに気づいた（README #31）。
   ⚠️ showScreen は末尾で MENU.reset() するので、画面遷移だけを試してもいつでも緑。
      ビルダーを直接呼ぶ。 */

t('★「ルールをきめる」: 体力の行が減ってもカーソルは名簿の中（buildHpRows）', () => {
  // 2人プレイ = 1P/2P/CPU の3行 → タイマン = 1P/2P の2行
  const wide = rulesCursorAtEnd('2p');
  X.CFG.mode = 'vs';
  X.buildHpRows();
  const msg = rulesCursorInside(wide);
  X.CFG.mode = '1p';
  return msg;
});

t('★「ルールをきめる」: CPU の行が減ってもカーソルは名簿の中（buildCpuRows）', () => {
  // 1人プレイ = CPU3行 → 2人プレイ = CPU2行（0行にはしない。
  // 0行だと早期 return の refresh が拾ってしまい、末尾の refresh を守れない）
  const wide = rulesCursorAtEnd('1p');
  X.CFG.mode = '2p';
  X.buildCpuRows();
  const msg = rulesCursorInside(wide);
  X.CFG.mode = '1p';
  return msg;
});

t('★ロビーの人数チップを押しても、名簿が画面から切れた要素を掴まない', () => {
  /* ⛔ chips() は set(v) を呼んだ**あとに自分自身を作り直す**。人数の set は
     枠の数が変わるので buildLobby() を呼ばざるを得ないが、そこで
     wrap.innerHTML='' が走り、この chips が握っている箱は親から切り離される。
     戻ってきた chips がそこに名簿を登録し直すと、
     **カーソルは乗るのに画面には何も無い**（白い枠が消えて見える）。
     2026-09-22 に v4.2.0 の実装中に発見。DOM スタブに isConnected を足して
     捕まえられるようにしてから直した */
  lobbyAsHost(2);
  X.MENU.reg.lobby.humans.forEach((it, i) =>
    ok(it.el.isConnected, `組み立て直後なのに humans[${i}] が切れている（スタブの問題）`));

  X.MENU.reg.lobby.humans[2].act();          // 3人にする＝枠の数が変わる
  eq(X.CFG.lanHumans, 3, '人数が変わっていない');

  X.MENU.reg.lobby.humans.forEach((it, i) =>
    ok(it.el.isConnected, `humans[${i}] が画面から切れた要素を掴んでいる`));
  // ほかのグループも道連れになっていないこと
  for (const g of ['pick0', 'hp0', 'wins', 'sd']) {
    (X.MENU.reg.lobby[g] || []).forEach((it, i) =>
      ok(it.el.isConnected, `${g}[${i}] が画面から切れている`));
  }
  lobbyOff();
  return '名簿の要素は全部つながったまま';
});

t('★チップを押したら見た目も追いつく（set の戻り値で早期 return しない）', () => {
  /* ⛔ 2026-09-22、実装中に「set がビルダーを組み直したら true を返す」という
     約束で chips の自己再構築を止めたら、**「ルールをきめる」のサドンデスが壊れた**。
     `v=>CFG.sudden=v` は代入式なので v をそのまま返す。ON を押すと true が返り、
     約束に引っかかって作り直しが止まる——値は入るが `.on` の印が OFF に残る。
     → 約束（戻り値）をやめて、**箱が本当に画面から切れているか**を見る形にした。
     ⚠️ 既存の238件で捕まらなかったのは、chip の className を見るテストが
        1本も無かったから（README #37）。 */
  Object.assign(X.CFG, { mode: '1p', sudden: true, sfx: false, bgm: false });
  X.showScreen('rules');
  const sd = () => X.MENU.reg.rules.sd;
  const wins = () => X.MENU.reg.rules.wins;

  sd()[1].act();                              // OFF
  eq(X.CFG.sudden, false, 'OFF にできない');
  ok(sd()[1].base.indexOf('on') >= 0, 'OFF を押したのに印が付いていない');

  sd()[0].act();                              // ON に戻す（ここで true が返る）
  eq(X.CFG.sudden, true, 'ON に戻せない');
  ok(sd()[0].base.indexOf('on') >= 0, 'ON を押したのに印が OFF のまま');
  ok(sd()[1].base.indexOf('on') < 0, 'OFF 側の印が残っている');

  // 数値を返す set でも同じこと（wins は v=>CFG.wins=v）
  wins()[3].act();
  eq(X.CFG.wins, 9, '勝利数が変わらない');
  ok(X.MENU.reg.rules.wins[3].base.indexOf('on') >= 0, '勝利数の印が追いついていない');
  X.CFG.wins = 3; X.CFG.sudden = true;
  return 'ON / OFF / 数値 どれも印が追いつく';
});

/* ============ v4.2.1 で直した4件（G・H・D・C） ============ */

t('★G: タイトルで「LAN対戦」を選んだ時点で CFG.mode が lan になる', () => {
  /* ⛔ v4.2.0 まで tm4 だけ pickMode() を通っておらず、mode を立てていなかった。
     だからタイトル→LAN→ロビーの間、CFG.mode は**直前の値のまま**
     （既定の '1p'、または一度でも 2人プレイ／タイマンを開いていれば '2p'/'vs'）。
     pollGamepads の `active = (mode==='1p' || mode==='lan')` に効くので、
     **いまカーソルが動いているのは '1p' が既定値だからで、設計として保証がない** */
  padOff();
  Object.assign(X.CFG, { mode: '2p', sfx: false, bgm: false });   // 一度 2人プレイを開いた状態
  X.showScreen('title');
  const m3 = X.MENU.reg.title.m3;
  ok(m3 && m3.length, 'タイトルに「LAN対戦」が名簿に無い');
  m3[0].act();
  eq(X.CFG.mode, 'lan', '「LAN対戦」を選んでも mode が lan にならない');
  eq(X.G.phase, 'lan', 'LAN の画面へ行っていない');
  X.CFG.mode = '1p';
  return 'mode=lan / 画面=lan';
});

t('★G: 2人プレイを開いてからでも、LAN のロビーでカーソルが動く', () => {
  /* 上の既定値依存のピン留め。mode が '2p' のまま残ると active が偽になり、
     ロビーでパッドの入力が keys に入らなくなる（カーソルは動くが挙動が変わる） */
  padOff();
  Object.assign(X.CFG, { mode: '2p', lanHumans: 2, lanHp: [1, 1, 1, 1],
    lanPicks: ['rabbit', 'frog', 'fox', 'mole'], sfx: false, bgm: false });
  X.showScreen('title');
  X.MENU.reg.title.m3[0].act();            // LAN対戦
  X.NET.role = 'host'; X.NET.seat = 0; X.NET.roster = new Set([0, 1]);
  X.showScreen('lobby');
  X.MENU.on = true; X.MENU.gi = 0; X.MENU.ii = 0;
  menuTap(13);                             // 下
  ok(X.MENU.gi > 0, 'ロビーでカーソルが下に動かない');
  padOff();
  X.NET.role = null; X.NET.seat = null; X.NET.roster = new Set();
  X.MENU.on = false; X.CFG.mode = '1p';
  return 'カーソルは動く（mode に依存しない）';
});

t('★H: 「せつぞくを切る」の「はい」は backToSetup を通る', () => {
  /* ⛔ v4.2.0 まで `NET.disconnect(); showScreen('title');` だけで、
     raf・BGM・バナー・MENU.on・ダイアログの後始末が1箇所に揃っていなかった。
     出口を1本に揃える（backToSetup はそれを全部やる） */
  padOff();
  X.NET.role = 'guest'; X.NET.seat = 1;
  Object.assign(X.CFG, { mode: 'lan', sfx: false, bgm: false });
  X.showScreen('lobby');
  X.MENU.on = true;
  X.askDisconnect();
  ok(X.MENU.dialog, '確認ダイアログが開いていない');
  const items = X.MENU.dialog.items;
  eq(items.length, 2, 'ダイアログのボタンが2つでない');
  items[1].act();                          // 「せつぞくを切る」＝はい
  eq(X.MENU.on, false, '枠が消えていない＝backToSetup を通っていない');
  eq(X.MENU.dialog, null, 'ダイアログが残っている');
  eq(X.G.phase, 'title', 'タイトルに戻っていない');
  eq(X.NET.role, null, '接続が切れていない');
  return 'backToSetup が全部畳んだ';
});

t('★D: ダイアログが開いたまま画面が変わっても、覆いが残らない', () => {
  /* ⛔ ゲストがロビーで確認を開いたままホストが「はじめる」を押すと、
     begin → startGame() → showScreen('play') と進んでもダイアログが残る。
     .cfm は z-index:40 の全画面なので、ゲストの画面がそれで覆われる。
     MENU.list() は dialog があると**そこで打ち切る**ので、カーソルも
     見えない2択に閉じ込められる */
  padOff();
  X.NET.role = 'guest'; X.NET.seat = 1;
  Object.assign(X.CFG, { mode: 'lan', sfx: false, bgm: false });
  X.showScreen('lobby');
  X.askDisconnect();
  ok(X.MENU.dialog, '確認ダイアログが開いていない');
  X.showScreen('play');                    // ホストの begin で試合が始まった想定
  eq(X.MENU.dialog, null, '画面が変わったのにダイアログが残っている');
  X.NET.role = null; X.NET.seat = null;
  return '画面が変わればダイアログは畳まれる';
});

t('★C: ゲストはリザルト画面のカーソルを動かせない', () => {
  /* ⛔ ホストのスナップショットがゲストの G.phase を roundEnd/over に書く。
     バナー自体はゲストに表示されない（endGame はホスト専用）が、
     **名簿には載ったまま**。カーソルは動くので、下を押してから A で
     「⚙ 設定をやりなおす」が発火し、**ゲストが試合から抜ける**。
     ⚠️ C7（ゲストで A を押してもラウンドが進まない）が実機で ✅ だったのは、
        初期位置が「つぎのラウンド」で、それにはゲストガードがあるから。
        移動してから押すと別物が動く */
  /* ⛔ 前のテストのダイアログが残っていると MENU.list() がそこで打ち切り、
     グループが1つになって「下が効かない」が別の理由で成立してしまう
     （最初に書いたとき、実際にそれで緑になっていた） */
  padOff();
  X.MENU.closeDialog();
  Object.assign(X.CFG, { mode: 'lan', sfx: false, bgm: false });
  X.NET.role = 'guest'; X.NET.seat = 1;
  X.G.phase = 'roundEnd';
  /* ⛔ 枠が出ていない状態から始める。ここで見るのは
     「pollGamepads のリザルト分岐がゲストで **MENU.on を立てない**」こと。
     カーソルが動かないことは下のテスト（MENU.list が空）が別に守っている
     ——2枚のガードが何を守っているかを、テストの側でも分けておく */
  X.MENU.on = false; X.MENU.gi = 0; X.MENU.ii = 0;
  menuTap(13);                             // 下
  eq(X.MENU.on, false, 'ゲストなのにリザルト画面で枠が出た');
  menuTap(0);                              // A
  eq(X.G.phase, 'roundEnd', 'ゲストなのに A で画面が変わった');
  eq(X.MENU.gi, 0, 'ゲストなのにカーソルが動いた');
  padOff();
  X.NET.role = null; X.NET.seat = null; X.MENU.on = false;
  return 'ゲストは枠も出ないし決定も走らない';
});

t('★C: ホストはリザルト画面のカーソルを動かせる（殺しすぎていないことの対照）', () => {
  padOff();
  X.MENU.closeDialog();
  Object.assign(X.CFG, { mode: '1p', sfx: false, bgm: false });
  X.NET.role = null;
  X.G.phase = 'roundEnd';
  X.MENU.on = false; X.MENU.gi = 0; X.MENU.ii = 0;
  menuTap(13);
  eq(X.MENU.on, true, 'ローカルでも枠が出なくなった＝殺しすぎ');
  eq(X.MENU.gi, 1, 'ローカルでもカーソルが動かなくなった＝殺しすぎ');
  padOff();
  X.MENU.on = false;
  return 'ローカル／ホストは従来どおり（枠が出てカーソルも動く）';
});

t('★C: ゲストのリザルト画面は名簿そのものが空（経路を問わず止まる）', () => {
  /* `pollGamepads` のリザルト分岐に置いたゲストガードは**パッド経路だけ**を塞ぐ。
     キーボードの矢印は別のハンドラを通る：

       } else if (G.phase==='roundEnd' || G.phase==='over'){
         if (e.code==='Space'||e.code==='Enter') advanceBanner();   ← ここで止まる
       } else if (MENU_ORDER[G.phase]){ … MENU.nav(…) }

     いまは else-if の順序のおかげで矢印が MENU.nav へ行かないが、
     **順序が入れ替わった瞬間に穴になる**（しかも症状は「ゲストが試合から抜ける」）。
     ⭐ ロビーのゲストが「名簿が空」で成立しているのと同じ機構にして、
        経路によらず止める（MENU.nav は先頭に `if (!gs.length) return;` がある）。 */
  padOff();
  X.MENU.closeDialog();
  Object.assign(X.CFG, { mode: 'lan', sfx: false, bgm: false });
  X.NET.role = 'guest'; X.NET.seat = 1;
  X.G.phase = 'roundEnd';
  X.MENU.on = true; X.MENU.gi = 0; X.MENU.ii = 0;

  eq(X.MENU.list().length, 0, 'ゲストのリザルト画面で名簿が空になっていない');
  X.MENU.nav(new Set(['Pad:Down']));       // ⛔ ポーリングを通さず直接（キーボード経路の再現）
  eq(X.MENU.gi, 0, '名簿が空なのにカーソルが動いた');
  X.MENU.nav(new Set(['Pad:A']));
  eq(X.G.phase, 'roundEnd', '名簿が空なのに決定が走った');

  // ホスト側は従来どおり2つ見える（殺しすぎていないことの対照）
  X.NET.role = null;
  Object.assign(X.CFG, { mode: '1p' });
  eq(X.MENU.list().length, 2, 'ローカル／ホストで名簿まで消えた＝殺しすぎ');

  padOff(); X.NET.seat = null; X.MENU.on = false;
  return 'ゲスト=0グループ / ホスト=2グループ';
});


/* ============ 20. バトル中にコントローラーで設定へ戻る（v4.3.0） ============
   家族の質問「バトル中に、コントローラーで設定画面に戻る方法はあるか？」への実装。
   ⭐ Start でポーズしてから Select。試合中に一発で飛べると、テーブルに置いた
      コントローラーに肘が当たっただけで試合が消える（リザルト画面に
      2人プレイのゲートを残したのと同じ理由）。 */

/** 試合を始めて、パッドの状態も枠も畳んだところから始める。 */
function padPlay(opts = {}) {
  fresh({ p1: 'rabbit', mode: opts.mode || '1p', clear: true });
  X.NET.role = opts.role || null;
  padOff();
  X.MENU.closeDialog();
  X.MENU.on = false;
  X.G.paused = false;
}

t('設定へ: ポーズしていない試合中に Select を押しても何も出ない', () => {
  padPlay();
  eq(X.G.phase, 'play', '前提：試合中');
  eq(X.G.paused, false, '前提：ポーズしていない');
  menuTap(8);                                   // Select
  eq(X.MENU.dialog, null, '肘が当たっただけで確認が出てしまう');
  eq(X.G.phase, 'play', '試合が終わってしまった');
  padOff();
  return '出ない';
});

t('設定へ: Start でポーズしてから Select で確認が出る', () => {
  padPlay();
  menuTap(9);                                   // Start
  eq(X.G.paused, true, '前提：Start でポーズできていない');
  menuTap(8);                                   // Select
  ok(X.MENU.dialog, '確認が出ていない');
  eq(X.MENU.dialog.items.length, 2, '「やめる」と「設定へもどる」の2つが並んでいない');
  padOff();
  return 'ポーズ → Select → 確認';
});

t('設定へ: 確認を出した時点で枠が見えている', () => {
  padPlay();
  menuTap(9); menuTap(8);
  eq(X.MENU.on, true, '枠が出ていない＝どっちが選ばれているか見えない');
  padOff();
  return '枠が出ている';
});

t('設定へ: ⛔確認の上で十字右を押すとカーソルが動く（試合中はメニュー扱いされない）', () => {
  /* ⚠️ 確認は「やめる／設定へもどる」の横並び＝1グループなので、動くのは左右。
     上下はグループ移動で、グループが1つしかないため何も起きない（ロビーの確認と同じ）。 */
  padPlay();
  menuTap(9); menuTap(8);
  eq(X.MENU.ii, 0, '前提：初期位置は「やめる」');
  menuTap(15);                                  // 十字 右
  eq(X.MENU.ii, 1, 'カーソルが動かない（MENU_ORDER に play が無いため素通りしている）');
  padOff();
  return 'やめる → 設定へもどる';
});

t('設定へ: 「設定へもどる」を選ぶとタイトルまで戻る', () => {
  padPlay();
  menuTap(9); menuTap(8);
  menuTap(15);                                  // 「設定へもどる」へ（横並びなので右）
  menuTap(0);                                   // A
  eq(X.G.phase, 'title', 'タイトルに戻っていない');
  eq(X.MENU.dialog, null, '確認が開いたまま残っている');
  eq(X.MENU.on, false, '触ってもいないのに枠が光ったまま');
  padOff();
  return 'title へ';
});

t('設定へ: 「やめる」を選ぶと試合に戻る（ポーズは残す）', () => {
  padPlay();
  menuTap(9); menuTap(8);
  menuTap(0);                                   // A（初期位置＝やめる）
  eq(X.MENU.dialog, null, '確認が閉じていない');
  eq(X.G.phase, 'play', '試合から出てしまった');
  eq(X.G.paused, true, 'ポーズが解けた＝戻った瞬間に動き出して不意打ちになる');
  padOff();
  return '試合に戻る・ポーズのまま';
});

t('設定へ: ⛔確認の上では Start を押してもポーズが切り替わらない', () => {
  padPlay();
  menuTap(9); menuTap(8);
  eq(X.G.paused, true, '前提：ポーズ中');
  menuTap(9);                                   // Start をもう一度
  eq(X.G.paused, true, '確認の裏でポーズが解けた（戻ったら試合が動いている）');
  padOff();
  return 'ポーズのまま';
});

t('設定へ: ゲストはポーズできないので Select 単体で出る', () => {
  padPlay({ mode: 'lan', role: 'guest' });
  menuTap(9);                                   // Start（ゲストは効かない）
  eq(X.G.paused, false, '前提：ゲストはポーズできない');
  menuTap(8);                                   // Select
  ok(X.MENU.dialog, 'ゲストが確認を出せない＝コントローラーで抜けられない');
  X.MENU.closeDialog();
  X.NET.role = null;
  padOff();
  return 'ゲストは Select 単体';
});

t('設定へ: キーボードの矢印も同じ入口を通る（KEY_TO_PAD 経由）', () => {
  padPlay();
  menuTap(9); menuTap(8);
  X.MENU.nav(new Set([X.KEY_TO_PAD.ArrowRight]));
  eq(X.MENU.ii, 1, '矢印でカーソルが動かない');
  X.MENU.closeDialog();
  padOff();
  return '矢印でも動く';
});

/* ---------- report ---------- */
console.log('');
for (const [mark, name, msg] of results) {
  console.log(`${mark} ${name}${msg ? `  — ${msg}` : ''}`);
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
