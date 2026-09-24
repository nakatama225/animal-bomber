/* きつねのCPUが開始直後に同じマスを往復して戦闘に参加しない、という報告の裏取り。
   各CPUについて 訪れたマス数 / 置いた爆弾 / a.mode の内訳 / 往復(A-B-A-B)回数 を数え、
   きつねと他の動物を並べて比べる。 */
const fs = require('fs');
const HTML = require('path').join(__dirname, '..', 'animal-bomber.html');
const src = fs.readFileSync(HTML, 'utf8');
const code0 = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];

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

// canEscapeAfterBomb の判定回数を動物別に数える（ラッパを差し込む）
const code = code0 + `
global.__ESC = { calls:{}, ok:{}, okAny:{} };
const __origEsc = canEscapeAfterBomb;
canEscapeAfterBomb = function(p,tx,ty,cap){
  const k=p.animal.key;
  const r=__origEsc(p,tx,ty,cap);
  // きつねは本数を減らしながら何度も呼ばれる。「その位置で最終的に置けたか」を見たいので
  // 満載(cap==null か cap==最大)の1回だけを分母に数え、どれか1本でも通れば ok に入れる
  const budget=p.maxBombs-p.activeBombs;
  if (cap==null || cap===budget) global.__ESC.calls[k]=(global.__ESC.calls[k]||0)+1;
  if (r) global.__ESC.okAny[k]=(global.__ESC.okAny[k]||0)+1;
  if (r && (cap==null || cap===budget)) global.__ESC.ok[k]=(global.__ESC.ok[k]||0)+1;
  return r;
};
global.__X = {
  get G(){return G}, get players(){return players}, get bombs(){return bombs},
  get grid(){return grid}, get items(){return items},
  startGame, startRound, update, draw, CFG, plannedLineBombs,
  COLS, ROWS, EMPTY, HARD, SOFT,
};`;
new Function(code.replace(/^const canEscapeAfterBomb|function canEscapeAfterBomb/m, 'var canEscapeAfterBomb = function'))();
const X = global.__X;

function run(label, p1, seconds = 40, level = 'futsu') {
  Object.assign(X.CFG, { mode: '1p', hpP1: 3, hpP2: 3, hpCPU: 3, time: 180,
                         wins: 9, sudden: false, sfx: false, bgm: false });
  X.CFG.cpuLevel = [level, level, level];
  X.CFG.pick.p1 = p1;
  VT = 0;
  X.startGame();
  for (const p of X.players) p.isCPU = true;
  global.__ESC.calls = {}; global.__ESC.ok = {}; global.__ESC.okAny = {};

  const DT = 1 / 60;
  const stats = X.players.map(p => ({
    key: p.animal.key, name: p.animal.name, label: p.label,
    tiles: new Set(), modes: {}, bombs: 0, flip: 0, hist: [], alive: 0,
  }));
  const seen = new WeakSet();
  const frames = Math.ceil(seconds * 60);
  for (let f = 0; f < frames && X.G.phase === 'play'; f++) {
    VT += DT * 1000;
    X.update(DT);
    for (let i = 0; i < X.players.length; i++) {
      const p = X.players[i], s = stats[i];
      if (p.state !== 'ALIVE') continue;
      s.alive++;
      const t = `${Math.floor(p.cx)},${Math.floor(p.cy)}`;
      s.tiles.add(t);
      const m = p.ai.mode || '?';
      s.modes[m] = (s.modes[m] || 0) + 1;
      if (s.hist[s.hist.length - 1] !== t) {
        s.hist.push(t);
        // A-B-A の形（1マス往復）を数える
        const h = s.hist;
        if (h.length >= 3 && h[h.length - 1] === h[h.length - 3]) s.flip++;
      }
    }
    for (const b of X.bombs) if (!seen.has(b)) {
      seen.add(b);
      const s = stats.find(z => z.label === X.players[b.owner]?.label);
      if (s) s.bombs++;
    }
  }
  console.log(`\n=== ${label}（${seconds}秒・4人戦・全員CPU）===`);
  for (const s of stats) {
    const modes = Object.entries(s.modes).sort((a, b) => b[1] - a[1])
      .slice(0, 4).map(([k, v]) => `${k}:${(v / 60).toFixed(0)}s`).join(' ');
    const esc = global.__ESC.calls[s.key]
      ? `満載で逃走可 ${global.__ESC.ok[s.key] || 0}/${global.__ESC.calls[s.key]}`
        + `（本数を減らして通った回数 ${global.__ESC.okAny[s.key] || 0}）`
      : '置こうとすらしてない';
    const sec = s.alive / 60;
    const per = sec > 0.5 ? (s.flip / sec).toFixed(1) : '-';
    console.log(`  ${s.name.padEnd(4)} 生存${String(sec.toFixed(0)).padStart(2)}s `
      + `／訪れたマス${String(s.tiles.size).padStart(3)} `
      + `／置いた爆弾${String(s.bombs).padStart(3)} ／往復${String(s.flip).padStart(3)}回(${per}/秒) `
      + `／${esc}\n        mode: ${modes}`);
  }
}

const LV = process.argv[2] || 'futsu';
run(`きつねが 1P 枠 / 強さ=${LV}`, 'fox', 40, LV);
run(`うさぎが 1P 枠（比較）/ 強さ=${LV}`, 'rabbit', 40, LV);
console.log('\n※ ⚠️ 「訪れたマス」は生存時間に比例する。早死にすると勝手に小さくなるので、');
console.log('※    必ず 生存秒 と 往復/秒 を見る。ここを見ずに「往復してる」と誤診した（2026-08-08）。');
console.log('※ 「満載で逃走可」が低いのに「本数を減らして通った回数」が高い＝きつね救済が効いてる状態。');
console.log('※ 2026-08-06 の実測: 救済前 訪れたマス3・爆弾0本・往復190回 → 救済後 マス7・爆弾5本・往復10回。');
