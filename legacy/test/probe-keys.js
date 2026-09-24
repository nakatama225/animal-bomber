/* エンコーダ設計のための実測。
   各エンティティに「実行時に本当に存在するキー」を集める。
   宣言のコメントは古い（slimes に squash があるのにコメントに無い）ので実物を見る。
   出現しにくいエンティティ（葱・狐火・落とし穴・ポロポロ）は、とくぎを直接呼んで作る。 */
const fs = require('fs');
const HTML = require('path').join(__dirname, '..', 'animal-bomber.html');
const src = fs.readFileSync(HTML, 'utf8');
let code = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];

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
  get negis(){return negis}, get foxfires(){return foxfires},
  get poroporos(){return poroporos}, get slimes(){return slimes},
  get pits(){return pits}, get particles(){return particles},
  startGame, update, draw, CFG, CONTROLS, ANIMALS,
  castFoxfire, rabbitPoroporo, frogSlime, startDigPit, startTongue,
  elephantCharge, elephantSnot, toNegibon, fireNegi, spawnBomb, applyItem,
  hurt, doSpecial, ITEM_DEF,
};`;
new Function(code)();
const X = global.__X;

const ARRAYS = ['players','bombs','blasts','items','particles','negis','foxfires','pits','poroporos','slimes'];
const seen = {};
for (const n of ARRAYS) seen[n] = new Map();

function sample() {
  for (const name of ARRAYS) {
    for (const e of X[name]) {
      const m = seen[name];
      for (const k of Object.keys(e)) {
        if (!m.has(k)) m.set(k, new Set());
        const v = e[k];
        m.get(k).add(v === null ? 'null' : Array.isArray(v) ? 'array' : typeof v);
      }
    }
  }
}
const step = (n) => { for (let i = 0; i < n; i++) { VT += 16.6; X.update(1/60); sample(); } };

function fresh(p1, p2) {
  Object.assign(X.CFG, { mode: 'vs', hpP1: 6, hpP2: 6, hpCPU: 6,
    time: 180, wins: 9, sudden: true, sfx: false, bgm: false });
  X.CFG.cpuLevel = ['oni','oni','oni'];
  X.CFG.pick.p1 = p1; X.CFG.pick.p2 = p2;
  VT = 0; X.startGame();
  return X.players;
}

// --- 1. 各動物のとくぎを直接発動させて、出にくいエンティティを作る ---
{ // きつね：狐火
  const [a] = fresh('fox', 'rabbit');
  a.cx = 3.5; a.cy = 3.5;
  X.castFoxfire(a); step(60);
}
{ // うさぎ：うんこポロポロ
  const [a] = fresh('rabbit', 'fox');
  a.cx = 5.5; a.cy = 5.5;
  X.rabbitPoroporo(a); step(120);
}
{ // かえる：粘膜スライム と 舌
  const [a] = fresh('frog', 'fox');
  a.cx = 4.5; a.cy = 4.5;
  X.frogSlime(a); step(150);
  X.startTongue(a); step(40);
}
{ // もぐら：落とし穴
  const [a] = fresh('mole', 'fox');
  a.cx = 6.5; a.cy = 6.5;
  X.startDigPit(a); step(180);
}
{ // ぞう：突進 と 鼻水
  const [a] = fresh('elephant', 'fox');
  a.cx = 2.5; a.cy = 4.5;
  X.elephantCharge(a); step(90);
  X.elephantSnot(a); step(60);
}
{ // 葱ボン：撃つ
  const [a, b] = fresh('rabbit', 'fox');
  X.toNegibon(a); step(10);
  for (let i = 0; i < 6; i++) { a.negiCool = 0; X.fireNegi(a); step(20); }
}
{ // アイテムを全種類まとめて拾わせる（effects の中身を出す）
  const [a] = fresh('rabbit', 'fox');
  for (const kind of Object.keys(X.ITEM_DEF)) {
    try { X.applyItem(a, { kind }); } catch (e) { /* 対象外の形なら飛ばす */ }
    step(5);
  }
}

// --- 2. 通常の試合も長めに回す（CPU が自然に作るものを拾う） ---
{
  Object.assign(X.CFG, { mode: '1p', hpP1: 3, hpP2: 3, hpCPU: 3,
    time: 60, wins: 9, sudden: true, sfx: false, bgm: false });
  X.CFG.cpuLevel = ['oni','oni','oni'];
  VT = 0; X.startGame();
  for (const p of X.players) p.isCPU = true;
  step(9000);
}

console.log('=== 実測: 各エンティティに存在したキー ===\n');
for (const name of ARRAYS) {
  const m = seen[name];
  if (!m.size) { console.log(`${name}: ★1件も出現しなかった\n`); continue; }
  console.log(`${name} (${m.size} keys)`);
  console.log('   ' + [...m.keys()].sort().join(', '));
  console.log('');
}
console.log('=== G のキー ===');
console.log(Object.keys(X.G).sort().join(', '));
console.log('\n=== players[0].effects に出たキー ===');
const fx = new Set();
for (const p of X.players) for (const k of Object.keys(p.effects || {})) fx.add(k);
console.log([...fx].sort().join(', ') || '(なし)');

console.log('\n=== ★object 型フィールドの実体（Set/Map は JSON で {} に化ける） ===');
const OBJ_TARGETS = {
  players: ['ai','animal','controls','effects','spawn','tongue','digging'],
  bombs: ['ignore'],
};
for (const [arr, keys] of Object.entries(OBJ_TARGETS)) {
  for (const e of X[arr]) {
    for (const k of keys) {
      const v = e[k];
      if (v === null || v === undefined) continue;
      const ctor = v.constructor ? v.constructor.name : '?';
      const json = JSON.stringify(v);
      const lost = (ctor === 'Set' || ctor === 'Map');
      console.log(`  ${arr}.${k}: ${ctor}${lost ? '  ★JSONで消える' : ''}  json=${String(json).slice(0,60)}`);
    }
    break;
  }
}
