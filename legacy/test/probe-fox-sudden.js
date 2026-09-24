/* きつねがサドンデス装備（💣8・🔥8・👟0）で一列ドン置きしたとき、
   自分が逃げ切れるマスがどれだけあるかを数える。
   CPU は canEscapeAfterBomb で置くのをやめるので sim では表に出ない。 */
const fs = require('fs');
const HTML = require('path').join(__dirname, '..', 'animal-bomber.html');
const src = fs.readFileSync(HTML, 'utf8');
const blocks = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
let code = blocks[0];

const noop = () => {};
const gradStub = { addColorStop: noop };
const fnCache = {};
const ctxStub = new Proxy({}, {
  get(_, k) {
    if (k === 'canvas') return { width: 0, height: 0 };
    if (k === 'measureText') return () => ({ width: 10 });
    if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => gradStub;
    if (!fnCache[k]) fnCache[k] = () => {};
    return fnCache[k];
  },
  set() { return true; },
});
function makeEl() {
  return {
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    style: {}, kids: [], appendChild(c) { this.kids.push(c); return c; },
    innerHTML: '', textContent: '', onclick: null, value: '',
    getContext: () => ctxStub, width: 0, height: 0,
    addEventListener: noop, removeEventListener: noop,
    querySelector: () => makeEl(), querySelectorAll: () => [],
  };
}
const elCache = new Map();
global.window = { addEventListener: noop, removeEventListener: noop };
global.document = {
  getElementById(id) { if (!elCache.has(id)) elCache.set(id, makeEl()); return elCache.get(id); },
  createElement: () => makeEl(), addEventListener: noop,
  querySelector: () => makeEl(), querySelectorAll: () => [],
};
let VT = 0;
global.performance = { now: () => VT };
global.requestAnimationFrame = () => 0;
global.cancelAnimationFrame = noop;
global.setInterval = () => 0; global.clearInterval = noop;
global.setTimeout = () => 0; global.clearTimeout = noop;

code += `
global.__X = {
  get G(){return G}, get players(){return players}, get grid(){return grid},
  get bombs(){return bombs},
  startGame, startRound, CFG, plannedLineBombs, canEscapeAfterBomb, dangerMap,
  getPower, getSpeed, BOMB_MAX, POWER_MAX, SHOE_MAX, BOMB_FUSE,
  COLS, ROWS, EMPTY, HARD, SOFT, DIRV,
};`;
new Function(code)();
const X = global.__X;

Object.assign(X.CFG, { mode: 'vs', hpP1: 1, hpP2: 1, hpCPU: 1, time: 180,
                       wins: 3, sudden: true, sfx: false, bgm: false });
X.CFG.pick.p1 = 'fox'; X.CFG.pick.p2 = 'rabbit';
X.startGame();
const fox = X.players[0];

// サドンデス盤面を手で作る（ソフトブロック全消し・装備MAX・👟0）
for (let y = 1; y < X.ROWS - 1; y++) for (let x = 1; x < X.COLS - 1; x++)
  if (X.grid[y][x] === X.SOFT) X.grid[y][x] = X.EMPTY;
X.players[1].state = 'OUT';

function survey(maxBombs, power, shoes) {
  fox.maxBombs = maxBombs; fox.powerUp = power; fox.shoes = shoes; fox.activeBombs = 0;
  let total = 0, safe = 0;
  const worst = [];
  for (let y = 1; y < X.ROWS - 1; y++) for (let x = 1; x < X.COLS - 1; x++) {
    if (X.grid[y][x] !== X.EMPTY) continue;
    for (const dir of ['up', 'down', 'left', 'right']) {
      fox.cx = x + 0.5; fox.cy = y + 0.5; fox.dir = dir;
      const plan = X.plannedLineBombs(fox, x, y);
      if (!plan.length) continue;
      total++;
      const okEsc = X.canEscapeAfterBomb(fox, x, y);
      if (okEsc) safe++; else worst.push(`(${x},${y})${dir}×${plan.length}発`);
    }
  }
  return { total, safe, rate: total ? (safe / total * 100) : 0, worst };
}

console.log(`盤面 ${X.COLS}×${X.ROWS} / 導火線=${X.BOMB_FUSE}s\n`);
const M=`💣${X.BOMB_MAX} 🔥${X.POWER_MAX} 👟${X.SHOE_MAX}`;
const rows = [
  ['ラウンド開始時（💣2 🔥1 👟0）', 1, 0, 0],   // きつねは bombBonus+1 で maxBombs=2
  [`サドンデス 現状（${M}）`, X.BOMB_MAX, X.POWER_MAX, X.SHOE_MAX],
  [`参考: 💣${X.BOMB_MAX} 🔥${X.POWER_MAX} 👟0`, X.BOMB_MAX, X.POWER_MAX, 0],
  [`参考: 💣4 🔥${X.POWER_MAX} 👟${X.SHOE_MAX}`, 4, X.POWER_MAX, X.SHOE_MAX],
];
for (const [label, mb, pw, sh] of rows) {
  const r = survey(mb, pw, sh);
  console.log(`${label.padEnd(30)} 速度${X.getSpeed(fox).toFixed(2)} / `
    + `置けた ${String(r.total).padStart(4)}通り / `
    + `逃げ切れる ${String(r.safe).padStart(4)} = ${r.rate.toFixed(0)}%`);
}
console.log('\n※ 「逃げ切れる」は CPU が使う canEscapeAfterBomb（安全側の見積り）で判定。');
console.log('※ 0% に近いと、人間のきつねはサドンデスで爆弾ボタンを押した瞬間に自滅する。');
