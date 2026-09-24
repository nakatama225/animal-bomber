/* CPU の強さ設定が本当に勝率に効いてるかを見る。
   タイマン（CPUなしモード）の2枠を両方 CPU にして、片方を「よわい」片方を「つよい」に固定。
   同じ動物同士で戦わせるので、差が出れば強さ設定が効いてる。
   ここで 50/50 に近かったら CPU_LEVELS のツマミが機能してないということ。 */
const fs = require('fs');
const HTML = require('path').join(__dirname, '..', 'animal-bomber.html');
const code0 = [...fs.readFileSync(HTML, 'utf8')
  .matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];

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

const code = code0 + `
global.__X = {
  get G(){return G}, get players(){return players},
  startGame, startRound, update, draw, CFG, CPU_LEVELS, cpuLevelOf,
};`;
new Function(code)();
const X = global.__X;

function duel(levelA, levelB, animal, matches) {
  let winA = 0, winB = 0, none = 0, rounds = 0;
  for (let m = 0; m < matches; m++) {
    Object.assign(X.CFG, { mode: 'vs', hpP1: 1, hpP2: 1, hpCPU: 1,
      time: 180, wins: 3, sudden: true, sfx: false, bgm: false });
    X.CFG.pick.p1 = animal; X.CFG.pick.p2 = animal;
    // 3体ぶんの枠に [A, B] を入れる（3つ目は使わない）
    X.CFG.cpuLevel = [levelA, levelB, levelB];
    VT = 0;
    X.startGame();
    X.players[0].isCPU = true; X.players[0].cpuIdx = 0;
    X.players[1].isCPU = true; X.players[1].cpuIdx = 1;
    const DT = 1 / 60;
    const cap = 60 * 270;
    let guard = 0;
    while (!X.G.champion && guard++ < 30) {
      let f = 0;
      while (X.G.phase === 'play' && f < cap) { VT += DT * 1000; X.update(DT); X.draw(); f++; }
      rounds++;
      if (X.G.phase === 'play') break;
      if (!X.G.champion) X.startRound();
    }
    if (!X.G.champion) none++;
    else if (X.G.champion === X.players[0]) winA++;
    else winB++;
  }
  const total = winA + winB;
  const rateA = total ? (winA / total * 100) : 0;
  const nameA = X.CPU_LEVELS[levelA].label, nameB = X.CPU_LEVELS[levelB].label;
  console.log(`${animal.padEnd(9)} ${nameA}(枠1) ${winA} 勝 vs ${nameB}(枠2) ${winB} 勝`
    + `${none ? `（決着せず ${none}）` : ''}　→ ${nameA} の勝率 ${rateA.toFixed(0)}%`
    + `　計${rounds}ラウンド`);
  return rateA;
}

const N = Number(process.argv[2] || 6);
console.log(`同じ動物同士のタイマンで ${N} マッチずつ（3勝先取・HP1・3分・サドンデスON）\n`);
const rows = [];
for (const animal of ['rabbit', 'elephant']) {
  rows.push(duel('yowa', 'tsuyo', animal, N));
  rows.push(duel('tsuyo', 'yowa', animal, N));   // 枠の有利不利を打ち消すため入れ替えても測る
}
console.log('\n※ 1行目3行目の「よわいの勝率」が低く、2行目4行目の「つよいの勝率」が高ければ効いてる。');
console.log('※ どれも 50% 前後なら CPU_LEVELS のツマミが機能してない。');
