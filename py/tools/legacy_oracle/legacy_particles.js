/* 原型が粒子と画面の揺れを出す所を、決まった乱数の列で呼び、使った乱数・出た粒子・揺れを
   JSON に書き出す。Python 版の粒子を出す関数が、同じ乱数の列で同じ粒子と揺れを出すかを
   確かめる正解に使う。使った乱数には、ルールの層が引くもの（ブロックのあとのアイテムの抽選・
   被弾で吐き出すアイテムの種類）も入る（読む側が外す）。
   node legacy_particles.js <出力.json> */
const env = require('./legacy_env.js');
const { X } = env;
const out = process.argv[2];

const RANDOM = Array.from({ length: 200 }, (_, i) => Number((((i + 3) * 0.7548776662466927) % 1).toFixed(6)));

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
function playerOf(key, over) {
  env.setRandom([0.5]);
  const p = X.makePlayer({ id: 0, label: '1P', animal: key, spawn: { x: 5, y: 5 } });
  env.setRandom(null);
  p.cx = 5.5; p.cy = 5.5;
  Object.assign(p, over || {});
  return p;
}

const cases = [];
function run(name, inputs, call, setup) {
  X.grid = emptyGrid();
  X.particles = []; X.items = []; X.bombs = []; X.blasts = [];
  X.shakeAmt = 0;
  if (setup) setup();
  const used = [];
  env.setRandomLog(used);
  env.setRandom(RANDOM);
  call();
  env.setRandom(null); env.setRandomLog(null);
  cases.push({ name, inputs, random: used, particles: JSON.parse(JSON.stringify(X.particles)), shake: X.shakeAmt });
}

// puff：場所・色・絵文字（原型で使われている組み合わせ）
for (const [col, txt] of [['#6b5443', '🌑'], ['#8a6a3a', '💩'], ['#ffd23f', '💣'], ['#b98a5a', '🍌'],
  ['#ff7a5a', '👅'], ['#8a5a2a', '🕳️'], ['#8ce0ff', '💨'], ['#f7a8c4', '💩'], ['#c98a8a', '🧅'],
  ['#9fd8ff', '💧'], ['#f7a8c4', '💨']]) {
  run(`puff ${col} ${txt}`, { fn: 'puff', x: 4, y: 6, col, txt }, () => X.puff(4, 6, col, txt));
}
// ブロックが壊れた破片（そのあとのアイテムの抽選の乱数は、粒子とは別）
run('destroySoft', { fn: 'destroySoft', x: 3, y: 3 }, () => X.destroySoft(3, 3), () => { X.grid[3][3] = X.SOFT; });
// 倒れたとき（動物ごとの色と絵文字）
for (const key of ['rabbit', 'elephant', 'mole', 'fox', 'frog']) {
  const p = playerOf(key, { cx: 7.5, cy: 9.5 });
  X.players = [p];
  // 葱ボンへ回らないよう、時間切れ間際にしておく（toNegibon は乱数を引かないが、念のため外す）
  X.G.time = 1;
  run(`kill ${key}`, { fn: 'kill', animal: key, cx: 7.5, cy: 9.5 }, () => X.kill(p));
}
// 被弾（揺れの大きさだけ）
{
  const p = playerOf('rabbit', { hp: 3, maxHp: 3 });
  X.players = [p];
  run('hurt', { fn: 'hurt' }, () => X.hurt(p, 1));
}
// うさぎの跳躍
{
  const p = playerOf('rabbit', { dir: 'right' });
  X.players = [p];
  run('hop', { fn: 'hop', dir: 'right', from: [5.5, 5.5], dist: 1 }, () => X.hop(p, 1));
}
// ぞうの鼻水（正面2マスに水しぶき。1マス目に爆弾があれば消して puff）
for (const withBomb of [false, true]) {
  const p = playerOf('elephant', { dir: 'right', cx: 3.5, cy: 5.5 });
  X.players = [p];
  run(`snot${withBomb ? ' bomb' : ''}`, { fn: 'elephantSnot', dir: 'right', from: [3.5, 5.5], bombAt: withBomb ? [4, 5] : null },
    () => X.elephantSnot(p), () => { if (withBomb) X.spawnBomb(p, 4, 5); });
}
// ぞうの突進がアイテムを踏んだ（良いアイテムは吸い込み、悪いアイテムは抱える）
for (const kind of ['fire', 'banana']) {
  const p = playerOf('elephant', { dir: 'right', cx: 6.5, cy: 5.5, effects: { charge: 1 } });
  X.players = [p];
  run(`chargeSweep ${kind}`, { fn: 'chargeSweep', kind, at: [6, 5] }, () => X.chargeSweep(p),
    () => { X.items.push({ x: 6, y: 5, kind, born: 0 }); });
}
// 爆発の揺れ（連鎖の数ごと）
for (const n of [1, 2, 5]) {
  const p = playerOf('rabbit', { cx: 1.5, cy: 1.5 });
  X.players = [p];
  run(`explode chain ${n}`, { fn: 'explodeChain', count: n }, () => X.explodeChain(X.bombs[0]), () => {
    for (let i = 0; i < n; i++) { const b = X.spawnBomb(p, 3 + i * 2, 7); b.power = 3; }
  });
}
require('fs').writeFileSync(out, JSON.stringify({
  source: 'legacy/animal-bomber.html の puff・destroySoft・kill・hurt・hop・elephantSnot・chargeSweep・explodeChain',
  randomValues: RANDOM,
  cases,
}, null, 1));
console.log('cases', cases.length, cases.map(c => `${c.name}:${c.particles.length}/${c.random.length}/shake${c.shake}`).join(' | '));
