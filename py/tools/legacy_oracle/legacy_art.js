/* 原型の描く関数を、いろいろな入力で呼んで、canvas へ出した命令の列を JSON に書き出す。
   Python 版の描く関数が、同じ入力で同じ命令の列を出すかを確かめる正解に使う。
   node legacy_art.js <出力.json> */
const env = require('./legacy_env.js');
const { X, rec } = env;
const out = process.argv[2];

const cases = [];
/** 乱数の列（0〜1）。ケースごとに頭から使い、使った数を記録する。 */
const RANDOM = Array.from({ length: 64 }, (_, i) => Number((((i + 1) * 0.6180339887498949) % 1).toFixed(6)));

function emptyGrid() {
  const g = [];
  for (let y = 0; y < X.ROWS; y++) {
    const row = [];
    for (let x = 0; x < X.COLS; x++) {
      const border = x === 0 || y === 0 || x === X.COLS - 1 || y === X.ROWS - 1;
      row.push(border || (x % 2 === 0 && y % 2 === 0) ? X.HARD : X.EMPTY);
    }
    g.push(row);
  }
  return g;
}

function setTile(tile) {
  X.TILE = tile; X.OX = X.LANE * tile; X.OY = X.LANE * tile;
  X.CW = Math.round((X.COLS + X.LANE * 2) * tile);
  X.CH = Math.round((X.ROWS + X.LANE * 2) * tile);
}

function run(fn, name, inputs, call) {
  setTile(inputs.tile);
  X.G.elapsed = inputs.elapsedTicks / 60;
  env.resetCanvas();
  const used = [];
  env.setRandomLog(used);
  env.setRandom(RANDOM);
  call();
  env.setRandom(null);
  env.setRandomLog(null);
  cases.push({ fn, name, inputs, random: used, ops: rec.ops.slice() });
}

const TILES = [44, 60];
const ELAPSED = [0, 37, 600, 1234];

/* ---------- drawTile ---------- */
for (const tile of TILES) {
  const g = emptyGrid();
  g[3][3] = X.SOFT;
  X.grid = g;
  for (const [x, y, what] of [[0, 0, 'hard'], [3, 3, 'soft'], [3, 2, 'empty-odd'], [1, 1, 'empty-even']]) {
    run('drawTile', `${what}@${tile}`, { tile, elapsedTicks: 0, x, y, tileKind: what.split('-')[0] }, () => X.drawTile(x, y));
  }
}

/* ---------- drawItem ---------- */
const KINDS = ['bomb', 'fire', 'shoe', 'banana', 'onion', 'chicken', 'poop'];
for (const tile of TILES) {
  for (const [i, kind] of KINDS.entries()) {
    const e = ELAPSED[i % ELAPSED.length];
    const it = { x: 2 + i, y: 3, kind, born: e / 60 };
    run('drawItem', `${kind}@${tile}`, { tile, elapsedTicks: e, item: { ...it, bornTicks: e } }, () => X.drawItem(it));
  }
  // うさぎが撒いたうんこ（ピンクの枠）
  {
    const it = { x: 5, y: 7, kind: 'poop', poro: true, born: 0 };
    run('drawItem', `poro@${tile}`, { tile, elapsedTicks: 600, item: { ...it, bornTicks: 0 } }, () => X.drawItem(it));
  }
  // 消える寸前のうんこ（点滅）：残り 2 秒
  for (const e of [757, 800]) {
    const bornTicks = e - (15 - 2) * 60;
    const it = { x: 4, y: 5, kind: 'poop', born: bornTicks / 60 };
    run('drawItem', `poop-blink-${e}@${tile}`, { tile, elapsedTicks: e, item: { ...it, bornTicks } }, () => X.drawItem(it));
  }
  // 撒いたうんこが消える寸前（寿命 60 秒）
  {
    const e = 3700; const bornTicks = e - 58 * 60;
    const it = { x: 6, y: 5, kind: 'poop', poro: true, born: bornTicks / 60 };
    run('drawItem', `poro-blink@${tile}`, { tile, elapsedTicks: e, item: { ...it, bornTicks } }, () => X.drawItem(it));
  }
  // 鼻水で流されている途中（残りの秒）
  for (const meltTicks of [27, 10, 0]) {
    const it = { x: 3, y: 9, kind: 'banana', born: 0, melt: meltTicks / 60 };
    run('drawItem', `melt-${meltTicks}@${tile}`, { tile, elapsedTicks: 300, item: { ...it, bornTicks: 0, meltTicks } }, () => X.drawItem(it));
  }
}

/* ---------- drawBomb ---------- */
for (const tile of TILES) {
  for (const [j, fuse] of [144, 100, 70, 40, 5].entries()) {
    const e = ELAPSED[j % ELAPSED.length] + j;
    const b = { x: 3, y: 5, timer: fuse / 60 };
    run('drawBomb', `fuse-${fuse}@${tile}`, { tile, elapsedTicks: e, bomb: { x: 3, y: 5, fuseTicks: fuse } }, () => X.drawBomb(b));
  }
}

/* ---------- drawBlast ----------
   原型の爆風の残り t は BLAST_DUR（0.46 秒）から始まり、update ごとに 1/60 秒ずつ引かれる。
   Python 版は 0.46 秒を tick に切り上げた 28 tick から数えるので、残り left tick の爆風の
   t は、出てから引いた tick の数（28 − left）を BLAST_DUR から引いたものになる。 */
const BLAST_TICKS = Math.ceil(X.BLAST_DUR * 60);
for (const tile of TILES) {
  for (const left of [28, 27, 20, 9, 1]) {
    const bl = { x: 6, y: 7, t: X.BLAST_DUR - (BLAST_TICKS - left) / 60, center: left % 2 === 0 };
    run('drawBlast', `left-${left}@${tile}`, { tile, elapsedTicks: 100, blast: { x: 6, y: 7, remainingTicks: left, center: bl.center } }, () => X.drawBlast(bl));
  }
}

/* ---------- drawPlayer（体・頭・尻尾・目・耳・舌・掘る・状態の印） ---------- */
const ANIMAL_KEYS = ['rabbit', 'elephant', 'mole', 'fox', 'frog'];
const DIRS = ['down', 'up', 'left', 'right'];
function playerOf(key, over) {
  // makePlayer は CPU の揺らぎに Math.random を1つ引く（描画には関わらない）
  env.setRandom([0.5]);
  const p = X.makePlayer({ id: 0, label: '1P', animal: key, spawn: { x: 5, y: 5 } });
  env.setRandom(null);
  p.cx = 5.5; p.cy = 5.5; p.lastMoveAt = -9;
  Object.assign(p, over || {});
  return p;
}
function playerInputs(p, extra) {
  return {
    animal: p.animal.key, cx: p.cx, cy: p.cy, dir: p.dir, walk: p.walk, lastMoveAt: p.lastMoveAt,
    invuln: p.invuln, hurtFlash: p.hurtFlash, effects: { ...p.effects }, chicken: p.chicken,
    actHold: p.actHold, actFired: p.actFired, tongue: p.tongue ? { ...p.tongue } : null,
    digging: p.digging ? { ...p.digging } : null, ...(extra || {}),
  };
}
function playerCase(name, tile, e, p, tileUnder) {
  const g = emptyGrid();
  if (tileUnder) g[Math.floor(p.cy)][Math.floor(p.cx)] = tileUnder;
  X.grid = g;
  X.players = [p];
  run('drawPlayer', `${name}@${tile}`, { tile, elapsedTicks: e, player: playerInputs(p, { tileUnder: tileUnder || X.EMPTY }) },
    () => X.drawPlayer(p));
}
for (const tile of TILES) {
  for (const key of ANIMAL_KEYS) {
    for (const dir of DIRS) {
      playerCase(`${key}-${dir}-still`, tile, 600, playerOf(key, { dir }));
      // 歩いている（直前に動いた）
      const e = 640;
      playerCase(`${key}-${dir}-walk`, tile, e, playerOf(key, { dir, walk: 1.37, lastMoveAt: (e - 3) / 60 }));
    }
  }
}
const T0 = 44;
// 無敵の点滅（消える側と出る側）。floor(invuln×14) が偶数のとき薄くなる。
// 0.75 は floor(10.5) = 10 で薄く、0.65 は floor(9.1) = 9 で薄くならない。
// （初めは消える側も 0.7 にしていたが、floor(9.8) = 9 で薄くならず、薄くなる側を確かめていなかった）
playerCase('rabbit-invuln-dim', T0, 300, playerOf('rabbit', { invuln: 0.75 }));
playerCase('rabbit-invuln-lit', T0, 300, playerOf('rabbit', { invuln: 0.65 }));
// ブロックの中を通っている（薄く描く）。点滅で薄いときは、薄いほう（0.35）を採る
playerCase('mole-in-block', T0, 300, playerOf('mole', { dir: 'right' }), X.SOFT);
playerCase('mole-in-block-invuln', T0, 300, playerOf('mole', { dir: 'right', invuln: 0.75 }), X.SOFT);
// 落とし穴にはまっている
for (const dir of ['down', 'left']) {
  playerCase(`elephant-pitfall-${dir}`, T0, 300, playerOf('elephant', { dir, effects: { pitfall: 1.8 } }));
}
playerCase('fox-pitfall-60', 60, 300, playerOf('fox', { dir: 'up', effects: { pitfall: 2.9 } }));
// 被弾の揺れ（乱数を2つ引く）
playerCase('frog-hurt', T0, 300, playerOf('frog', { hurtFlash: 0.2 }));
// 状態の印（3つまで）
playerCase('rabbit-icons', T0, 300, playerOf('rabbit', { chicken: 'rabbit',
  effects: { stun: 1, slide: 1, reverse: 2, weak: 3 } }));
playerCase('fox-icons-poop', T0, 300, playerOf('fox', { effects: { nobomb: 2, runaway: 1, autobomb: 1, slow: 1 } }));
playerCase('mole-icon-chicken', T0, 300, playerOf('mole', { chicken: 'mole' }));
// とくぎの長押しのゲージ（たまり途中・たまり切り）
playerCase('elephant-gauge-half', T0, 300, playerOf('elephant', { chicken: 'elephant', actHold: 0.6, actFired: false }));
playerCase('fox-gauge-full', T0, 300, playerOf('fox', { chicken: 'fox', actHold: 0.7, actFired: false }));
playerCase('fox-gauge-fired', T0, 300, playerOf('fox', { chicken: 'fox', actHold: 0.7, actFired: true }));
// キツネ跳び（宙返り）
for (const [dir, left] of [['right', 0.7], ['left', 0.3], ['down', 0.5]]) {
  playerCase(`fox-leap-${dir}`, T0, 300, playerOf('fox', { dir, effects: { foxLeap: left } }));
}
// うんこポロポロ中（ぶるぶる）
for (const left of [1.9, 1.0, 0.2]) {
  playerCase(`rabbit-poro-${left}`, T0, 433, playerOf('rabbit', { dir: 'left', effects: { poro: left } }));
}
// かえるの舌（伸びる途中・戻る途中・掴んだアイテム）
for (const [dir, dx, dy] of [['right', 1, 0], ['up', 0, -1]]) {
  playerCase(`frog-tongue-out-${dir}`, T0, 300, playerOf('frog', { dir,
    tongue: { phase: 'out', len: 2, t: 0.05, dx, dy, item: null } }));
  playerCase(`frog-tongue-in-${dir}`, T0, 300, playerOf('frog', { dir,
    tongue: { phase: 'in', len: 3, t: 0.1, dx, dy, item: 'fire' } }));
}
playerCase('frog-tongue-start', 60, 300, playerOf('frog', { dir: 'left',
  tongue: { phase: 'out', len: 0, t: 0, dx: -1, dy: 0, item: null } }));
// もぐらが掘っている（進み具合・土くれが飛ぶ瞬間）
for (const [left, e] of [[1.4, 300], [0.75, 301], [0.1, 302]]) {
  playerCase(`mole-dig-${left}-${e}`, T0, e, playerOf('mole', { digging: { t: left } }));
}
// 土くれが飛ぶ（|sin(elapsed*17)| > 0.85 の瞬間）
{
  let e = 0;
  while (Math.abs(Math.sin((e / 60) * 17)) <= 0.85) e++;
  playerCase(`mole-dig-spray-${e}`, T0, e, playerOf('mole', { digging: { t: 0.9 } }));
}

/* ---------- drawSlimes ---------- */
for (const tile of TILES) {
  const flying = { x: 8, y: 5, sx: 5.5, sy: 5.5, owner: 0, phase: 'fly', t: 0.17, hopT: 0, wob: 0, hopsLeft: 7, squash: 0 };
  X.slimes = [flying];
  run('drawSlimes', `fly@${tile}`, { tile, elapsedTicks: 200, slime: { ...flying } }, () => X.drawSlimes());
  for (const [squash, wob, hops, e] of [[0, 0, 7, 200], [0.6, 0.1, 5, 210], [0, 0.4, 2, 222], [1, 0, 1, 230]]) {
    const sl = { x: 9, y: 7, sx: 5.5, sy: 5.5, owner: 0, phase: 'hop', t: 0, hopT: 0.2, wob, hopsLeft: hops, squash };
    X.slimes = [sl];
    run('drawSlimes', `hop-${squash}-${wob}-${hops}@${tile}`, { tile, elapsedTicks: e, slime: { ...sl } }, () => X.drawSlimes());
  }
}

/* ---------- drawFoxfires ---------- */
for (const tile of TILES) {
  const f = { x: 7, y: 5, owner: 0, t: 0.05, life: 1.0,
    trail: [{ x: 5, y: 5, a: 0.4 }, { x: 6, y: 5, a: 0.9 }] };
  X.foxfires = [f];
  run('drawFoxfires', `trail@${tile}`, { tile, elapsedTicks: 321, foxfire: JSON.parse(JSON.stringify(f)) }, () => X.drawFoxfires());
}

/* ---------- drawParticle ---------- */
for (const tile of TILES) {
  for (const q of [
    { x: 4.3, y: 6.1, vx: 1, vy: -2, life: 0.4, col: '#ffd23f', sz: 5 },
    { x: 4.3, y: 6.1, vx: 1, vy: -2, life: 0.9, col: '#ffd23f', sz: 5 },
    { x: 5.5, y: 5.5, vx: 0, vy: -1.2, life: 0.6, col: '#fff', sz: 20, txt: '💣' },
    { x: 5.5, y: 5.3, vx: 0, vy: -0.7, life: 1.1, col: '#fff', sz: 26, txt: '💀', spin: true },
  ]) {
    run('drawParticle', `${q.txt || 'rect'}-${q.life}@${tile}`, { tile, elapsedTicks: 0, particle: { ...q } }, () => X.drawParticle(q));
  }
}

/* ---------- draw（1枚まるごと：背景・揺れ・並べる順） ---------- */
{
  const tile = 44;
  const g = emptyGrid();
  g[1][3] = X.SOFT; g[5][7] = X.SOFT;
  X.grid = g;
  const p0 = playerOf('rabbit', { id: 0, cx: 3.5, cy: 7.5, dir: 'right' });
  const p1 = playerOf('frog', { id: 1, cx: 9.5, cy: 3.5, dir: 'down' });
  const p2 = playerOf('elephant', { id: 2, cx: 12.5, cy: 9.5, dir: 'left', state: 'OUT' });
  X.players = [p0, p1, p2];
  X.items = [{ x: 4, y: 3, kind: 'fire', born: 0 }];
  X.bombs = [{ x: 5, y: 5, timer: 1.0 }];
  // 残り 18 tick の爆風（t の出し方は上の drawBlast のケースと同じ）
  X.blasts = [{ x: 6, y: 5, t: X.BLAST_DUR - (BLAST_TICKS - 18) / 60, center: true }];
  X.foxfires = []; X.slimes = []; X.negis = [];
  X.particles = [{ x: 4.3, y: 6.1, vx: 1, vy: -2, life: 0.4, col: '#ffd23f', sz: 5 }];
  X.G.paused = false;
  for (const shake of [0, 6]) {
    X.shakeAmt = shake;
    run('draw', `frame-shake-${shake}@${tile}`, { tile, elapsedTicks: 500, shake,
      players: [p0, p1, p2].map(p => playerInputs(p, { id: p.id, state: p.state })) }, () => X.draw());
  }
}

/* ---------- ここから下は、drawPlayer の中で呼ばれる部品を単独で呼ぶケース ----------
   drawPlayer は足元の影・色の輪・状態の印も描くので、体・頭・尻尾・目だけを先に確かめるために
   部品を直接呼ぶ。上の 187 通りは並びも数も変えない。 */

/* ---------- roundRect（角の丸みが辺の半分より大きい形・幅 0 も） ---------- */
for (const [name, x, y, w, h, r] of [
  ['plate', 10.5, 20.25, 38, 38, 9],
  ['gauge-short', 5, 6, 44 * 0.6 * 0.1, 44 * 0.09, 4],
  ['gauge-empty', 5, 6, 0, 44 * 0.09, 4],
  ['square-corner', 3, 4, 40, 30, 0],
]) {
  run('roundRect', name, { tile: 44, elapsedTicks: 0, x, y, w, h, r }, () => X.roundRect(x, y, w, h, r));
}

/* ---------- drawEye（白目・黒目・照り、閉じた目） ---------- */
for (const [name, x, y, r, mode, opt] of [
  ['plain', 20, 30, 5.2, 'front', null],
  ['rabbit-front', 20, 30, 5.2, 'front', { iris: '#7a0f2a' }],
  ['rabbit-side', 20, 30, 4.9, 'side', { iris: '#7a0f2a', look: 1 }],
  ['narrow', 20, 30, 6, 'front', { iris: '#3a1400', tall: 0.78 }],
  ['white-look', 20, 30, 6, 'side', { iris: '#141a06', white: '#fff8d8', look: 1 }],
  ['closed-thin', 20, 30, 2.2, 'front', { closed: true }],
  ['closed-thick', 20, 30, 5, 'side', { closed: true }],
]) {
  run('drawEye', name, { tile: 44, elapsedTicks: 0, x, y, r, mode, opt },
    () => X.drawEye(x, y, r, mode, opt || undefined));
}

/* ---------- drawTail（3種類 × 横・背・正面）。縁取りは原型の inkLine（体の outline と同じ中身） ---------- */
{
  const bodyW = 11.088, bodyH = 9.0992, bodyCY = -6.4;
  const col = '#ff6a00', dark = '#8a3000', fur = '#fff3e4';
  const views = [['side', true, false], ['back', false, true], ['front', false, false]];
  const tails = [];
  for (const kind of ['ball', 'bushy', 'thin', 'none']) for (const view of views) tails.push([kind, view, 0.6]);
  tails.push(['bushy', views[0], -1]);
  for (const [kind, [view, side, back], swing] of tails) {
    run('drawTail', `${kind}-${view}-${swing}`,
      { tile: 44, elapsedTicks: 0, kind, bodyW, bodyH, bodyCY, side, back, col, dark, fur, swing },
      () => X.drawTail(kind, bodyW, bodyH, bodyCY, side, back, col, dark, fur, X.inkLine, swing));
  }
}

/* ---------- headRabbit（正面・横・後頭部） ---------- */
for (const tile of TILES) {
  const r = tile * 0.29 * 0.96;
  for (const mode of ['front', 'side', 'back']) {
    run('headRabbit', `${mode}@${tile}`,
      { tile, elapsedTicks: 0, x: 0, y: -20.5, r, mode, col: '#ff2d78', dark: '#a30f46', fur: '#ffe3ee' },
      () => X.headRabbit(0, -20.5, r, mode, '#ff2d78', '#a30f46', '#ffe3ee'));
  }
}

/* ---------- drawAnimalBody（うさぎ。4方向 × 止まる・歩く、撒く身ぶり、跳び上がり） ---------- */
function bodyCase(name, tile, e, over) {
  // 秒の値は tick の数を 60 で割って作る（Python 版も同じ tick の数から作る）。
  const lastMoveTicks = over.lastMoveTicks;
  const poroTicks = over.poroTicks || 0;
  const leapTicks = over.leapTicks || 0;
  const p = playerOf('rabbit', {
    dir: over.dir, walk: over.walk || 0,
    lastMoveAt: lastMoveTicks === undefined ? -9 : lastMoveTicks / 60,
  });
  p.effects.poro = poroTicks / 60;
  p.effects.foxLeap = leapTicks / 60;
  run('drawAnimalBody', `${name}@${tile}`, {
    tile, elapsedTicks: e, animal: 'rabbit', dir: over.dir, walk: over.walk || 0,
    lastMoveTicks: lastMoveTicks === undefined ? null : lastMoveTicks, poroTicks, leapTicks,
  }, () => X.drawAnimalBody(p));
}
for (const tile of TILES) {
  for (const dir of DIRS) {
    bodyCase(`${dir}-still`, tile, 600, { dir });
    bodyCase(`${dir}-walk`, tile, 640, { dir, walk: 1.37, lastMoveTicks: 637 });
  }
}
for (const poroTicks of [114, 60, 12]) {
  bodyCase(`poro-${poroTicks}`, 44, 433, { dir: 'left', poroTicks });
}
bodyCase('poro-walk', 60, 433, { dir: 'up', poroTicks: 60, walk: 2.9, lastMoveTicks: 430 });
for (const [dir, leapTicks] of [['right', 42], ['left', 18], ['down', 30]]) {
  bodyCase(`leap-${dir}-${leapTicks}`, 44, 300, { dir, leapTicks });
}
// 止まってからの時間が 0.1 秒の境目（694 は小数の誤差で 0.1 よりわずかに短く、まだ歩いている扱い）
bodyCase('walk-edge-694', 44, 700, { dir: 'right', walk: 0.8, lastMoveTicks: 694 });
bodyCase('walk-stopped-693', 44, 700, { dir: 'right', walk: 0.8, lastMoveTicks: 693 });

require('fs').writeFileSync(out, JSON.stringify({
  source: 'legacy/animal-bomber.html の描く関数（draw・drawTile・drawItem・drawBomb・drawBlast・drawPlayer・drawSlimes・drawFoxfires・drawParticle）と、drawPlayer の中の部品（roundRect・drawEye・drawTail・headRabbit・drawAnimalBody）',
  randomValues: RANDOM,
  cases,
}, null, 0));
const byFn = {};
for (const c of cases) byFn[c.fn] = (byFn[c.fn] || 0) + 1;
console.log('cases', cases.length, JSON.stringify(byFn));
console.log('ops', cases.reduce((a, c) => a + c.ops.length, 0));
