/* CPU の強さを「体感」ではなく数字で見る。
   ・自爆率（自分の爆風で喰らった回数 ÷ 全被弾）
   ・相手に到達したか（対戦相手といちばん近づいた距離）
   ・与えたダメージ / 受けたダメージ
   4段階を同じ動物で総当たりに戦わせる。 */
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
global.window = { addEventListener: noop, removeEventListener: noop, innerWidth: 1280, innerHeight: 800 };
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
  get G(){return G}, get players(){return players}, get bombs(){return bombs},
  get grid(){return grid},
  startGame, startRound, update, draw, CFG, CPU_LEVELS, cpuLevelOf, getPower, getSpeed,
  COLS, ROWS, EMPTY, HARD, SOFT,
};`;
new Function(code)();
const X = global.__X;

function duel(levelA, levelB, animal, matches) {
  const st = [
    { lv: levelA, hits: 0, selfHits: 0, wins: 0, minDist: 99, bombs: 0 },
    { lv: levelB, hits: 0, selfHits: 0, wins: 0, minDist: 99, bombs: 0 },
  ];
  let rounds = 0, none = 0;
  for (let m = 0; m < matches; m++) {
    Object.assign(X.CFG, { mode: 'vs', hpP1: 1, hpP2: 1, hpCPU: 1,
      time: 180, wins: 3, sudden: true, sfx: false, bgm: false });
    X.CFG.pick.p1 = animal; X.CFG.pick.p2 = animal;
    X.CFG.cpuLevel = [levelA, levelB, levelB];
    VT = 0;
    X.startGame();
    X.players[0].isCPU = true; X.players[0].cpuIdx = 0;
    X.players[1].isCPU = true; X.players[1].cpuIdx = 1;
    const DT = 1 / 60;
    const cap = 60 * 270;
    const seen = new WeakSet();
    let guard = 0;
    while (!X.G.champion && guard++ < 30) {
      let f = 0;
      let hp = X.players.map(p => p.hp);
      while (X.G.phase === 'play' && f < cap) {
        // 葱ボン復活やサドンデスで HP が増えた時は基準を作り直す（増分を被弾に数えない）
        for (let i = 0; i < 2; i++) if (X.players[i].hp > hp[i]) hp[i] = X.players[i].hp;
        VT += DT * 1000; X.update(DT); X.draw(); f++;
        for (let i = 0; i < 2; i++) {
          const p = X.players[i];
          // ★ 被弾は state を見る前に数える。HP1 だと死亡と同時に OUT になるので、
          //   state で弾くと1件も拾えない（最初こう書いて全部0になった）
          if (p.hp < hp[i]) {
            st[i].hits += hp[i] - p.hp;
            if (p.lastHitBy === p.id) st[i].selfHits += hp[i] - p.hp;
          }
          hp[i] = p.hp;
          if (p.state !== 'ALIVE') continue;
          const q = X.players[1 - i];
          if (q.state === 'ALIVE') {
            const d = Math.abs(Math.floor(p.cx) - Math.floor(q.cx))
                    + Math.abs(Math.floor(p.cy) - Math.floor(q.cy));
            if (d < st[i].minDist) st[i].minDist = d;
          }
        }
        for (const b of X.bombs) if (!seen.has(b)) {
          seen.add(b);
          if (st[b.owner]) st[b.owner].bombs++;
        }
      }
      rounds++;
      if (X.G.phase === 'play') break;
      if (X.G.overInfo && X.G.overInfo.winner) {
        const w = X.G.overInfo.winner.id;
        if (st[w]) st[w].wins++;
      }
      if (!X.G.champion) X.startRound();
    }
    if (!X.G.champion) none++;
  }
  const line = st.map(z => {
    const rate = z.hits ? Math.round(z.selfHits / z.hits * 100) : 0;
    return `${X.CPU_LEVELS[z.lv].label.padEnd(4)} 勝${String(z.wins).padStart(2)} `
      + `被弾${String(z.hits).padStart(3)}(自爆${String(z.selfHits).padStart(3)}=${String(rate).padStart(3)}%) `
      + `最接近${String(z.minDist).padStart(2)}マス 爆弾${String(z.bombs).padStart(4)}`;
  });
  console.log(`  ${animal.padEnd(8)} ${line[0]}`);
  console.log(`  ${''.padEnd(8)} ${line[1]}${none ? `  （決着せず ${none}）` : ''}`);
  return st;
}

const N = Number(process.argv[2] || 4);
console.log(`同じ動物同士のタイマン（両方CPU）で ${N} マッチずつ。3勝先取・HP1・3分\n`);
for (const [a, b] of [['tsuyo', 'oni'], ['futsu', 'oni'], ['futsu', 'tsuyo']]) {
  console.log(`--- ${X.CPU_LEVELS[a].label} vs ${X.CPU_LEVELS[b].label} ---`);
  for (const animal of ['rabbit', 'fox']) duel(a, b, animal, N);
}
console.log('\n※ 自爆% が高い＝自分の爆弾で死んでる（強さ設定より先にここを直す）');
console.log('※ 最接近が大きい＝相手の陣地まで到達できてない（追跡距離が足りない）');
