/* 死因の内訳を数える。⛔「きつねが自滅する」を言うには、他の4匹と比べないと始まらない
   （全員そこそこ自爆するゲームなので）。
   自爆の判定：死んだマスの爆風の持ち主が自分自身かどうか（blastOwner）。 */
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '../animal-bomber.html'), 'utf8');
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (blocks.length !== 1) { console.error('script ブロックが1個じゃない'); process.exit(1); }

const noop = () => {};
const ctxStub = new Proxy({}, { get: (t, k) => (k === 'canvas' ? { width: 0, height: 0 } : noop) });
const makeEl = () => ({
  classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
  style: {}, kids: [], appendChild(c){ this.kids.push(c); return c; },
  innerHTML: '', textContent: '', onclick: null,
  getContext: () => ctxStub, width: 0, height: 0, addEventListener: noop,
});
const els = {};
global.document = {
  getElementById: id => (els[id] ||= makeEl()),
  querySelectorAll: () => [], querySelector: () => null,
  createElement: makeEl, addEventListener: noop, body: makeEl(),
};
global.window = { addEventListener: noop, removeEventListener: noop,
                  matchMedia: () => ({ matches: false, addEventListener: noop }) };
global.requestAnimationFrame = () => 0; global.cancelAnimationFrame = noop;
global.performance = { now: () => 0 };
global.navigator = global.navigator || {};
global.setInterval = () => 0; global.clearInterval = noop;
global.setTimeout = () => 0;  global.clearTimeout = noop;

new Function(blocks[0] + `
global.__D = { get G(){return G}, get players(){return players},
  get blastOwner(){return blastOwner}, startGame, update, CFG };`)();
const X = global.__D;

const LV = process.argv[2] || 'oni';
const ROUNDS = +(process.argv[3] || 40);
const tally = {};   // 動物 → {自爆, 他人, ふめい, 死んだ数, 生存}

for (let r = 0; r < ROUNDS; r++) {
  Object.assign(X.CFG, { mode:'1p', hpP1:1, hpP2:1, hpCPU:1, time:180,
                         wins:9, sudden:false, sfx:false, bgm:false });
  X.CFG.cpuLevel = [LV, LV, LV];
  X.CFG.pick.p1 = ['fox','rabbit','elephant','mole','frog'][r % 5];
  X.startGame();
  for (const p of X.players) p.isCPU = true;
  const was = new Map(X.players.map(p => [p, p.state]));
  for (let f = 0; f < 60 * 60 && X.G.phase === 'play'; f++) {
    X.update(1/60);
    for (const p of X.players) {
      if (was.get(p) === 'ALIVE' && p.state !== 'ALIVE') {
        was.set(p, p.state);
        const t = tally[p.animal.name] ||= { self:0, other:0, unknown:0, died:0 };
        t.died++;
        /* ⭐ ゲーム本体が damageCheck で p.lastHitBy を入れている（爆風の持ち主）。
           自分で blastOwner を引き直すと、死んだ時点では既に爆風が消えていて
           全部「ふめい」になる（最初そう書いて 100% ふめいになった）。 */
        const by = p.lastHitBy;
        if (by === undefined || by === null || by < 0) t.unknown++;
        else if (by === p.id) t.self++;
        else t.other++;
      }
    }
  }
}
console.log(`\n=== 死因の内訳（強さ=${LV}・${ROUNDS}ラウンド・全員CPU・HP1） ===`);
console.log('動物     死んだ数   自爆   他人   ふめい   自爆率');
for (const [name, t] of Object.entries(tally).sort((a,b)=>b[1].self/b[1].died - a[1].self/a[1].died)) {
  const rate = t.died ? (100*t.self/t.died).toFixed(0) : '-';
  console.log(`${name.padEnd(6)} ${String(t.died).padStart(7)} ${String(t.self).padStart(6)} `
            + `${String(t.other).padStart(6)} ${String(t.unknown).padStart(7)} ${String(rate).padStart(6)}%`);
}
console.log('※ ふめい＝死んだマスに爆風の記録が無い（葱・落とし穴・サドンデス・時間差の消滅）');
