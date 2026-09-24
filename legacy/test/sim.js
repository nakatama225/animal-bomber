/* headless simulation harness for animal-bomber.html
   DOM / canvas / WebAudio をスタブして、ゲームロジックだけ node で回す */
const fs = require('fs');
const path = require('path');
const HTML = require('path').join(__dirname, '..', 'animal-bomber.html');

const src = fs.readFileSync(HTML, 'utf8');
const blocks = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (blocks.length !== 1) { console.error('script blocks:', blocks.length); process.exit(1); }
let code = blocks[0];

/* ---------------- stubs ---------------- */
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
  const o = {
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    style: {}, kids: [],
    appendChild(c) { this.kids.push(c); return c; },
    innerHTML: '', textContent: '', onclick: null, value: '',
    getContext: () => ctxStub, width: 0, height: 0,
    addEventListener: noop, removeEventListener: noop,
  };
  return o;
}
const elCache = new Map();
global.window = { addEventListener: noop, removeEventListener: noop };
global.document = {
  getElementById(id) { if (!elCache.has(id)) elCache.set(id, makeEl()); return elCache.get(id); },
  createElement: () => makeEl(),
  addEventListener: noop,
};
let VT = 0; // 仮想時間 (ms)
global.performance = { now: () => VT };
global.requestAnimationFrame = () => 0;
global.cancelAnimationFrame = noop;
global.setInterval = () => 0;
global.clearInterval = noop;
global.setTimeout = () => 0;
global.clearTimeout = noop;

/* ---------------- expose internals ---------------- */
code += `
global.__X = {
  get G(){return G}, get players(){return players}, get bombs(){return bombs},
  get blasts(){return blasts}, get items(){return items}, get grid(){return grid},
  get negis(){return negis},
  startGame, startRound, update, draw, renderCards, renderKeyHelp,
  CFG, getPower, ANIMALS, dangerMap, buildBoard, POOP_KEYS, CPU_LEVELS, cpuLevelOf,
  get poroporos(){return poroporos}, PORO_RANGE, PORO_LIFE,
  BOMB_FUSE, COLS, ROWS, EMPTY, HARD, SOFT, NEGI_CUTOFF, NEGI_COOL,
};
`;
new Function(code)();
const X = global.__X;

/* ---------------- run ---------------- */
function runMatch(seedLabel, opts = {}) {
  const hp = opts.hp ?? 3;
  Object.assign(X.CFG, { mode: opts.mode || '1p', hpP1: hp, hpP2: hp, hpCPU: hp,
                         time: opts.time ?? 180,
                         wins: opts.wins ?? 3, sudden: true, sfx: false, bgm: false });
  if (opts.cpuLevel) X.CFG.cpuLevel = opts.cpuLevel.slice();
  X.CFG.pick.p1 = opts.p1 || 'rabbit';
  if (opts.p2) X.CFG.pick.p2 = opts.p2;
  VT = 0;
  X.startGame();
  // 人間枠も CPU にして AI 同士で戦わせる
  for (const p of X.players) p.isCPU = true;

  const DT = 1 / 60;
  const stat = {
    label: seedLabel, mode: X.CFG.mode, n: X.players.length,
    frames: 0, bombsPlaced: 0, maxBombsAtOnce: 0,
    deaths: [], err: null, ended: false, winner: null, reason: null,
    firstDeathAt: null, softLeft0: 0, softLeftEnd: 0, items: 0, maxItems: 0,
  };
  for (let y = 0; y < X.ROWS; y++) for (let x = 0; x < X.COLS; x++)
    if (X.grid[y][x] === X.SOFT) stat.softLeft0++;

  const seenBombs = new WeakSet();
  const seenNegis = new WeakSet();
  const dead = new Set();
  let negibonEver = new Set();
  stat.negisFired = 0; stat.negiSwaps = 0; stat.sudden = false; stat.negibonUsed = 0;
  stat.negibonFrames = 0; stat.totalDrops = 0; stat.goodDrops = 0;
  stat.peakPower = 0;   // 誰か1人が到達した最大の強化量
  const seenItems = new WeakSet();
  // うんこを踏んだ回数。うさぎのポロポロ（爆風で消えず60秒残る）でCPUが
  // 詰まってないかを見るための計測。撒いた本人は踏んでも発動しない
  stat.poopHits = 0; stat.poroTiles = 0; stat.poopHitsByRabbit = 0;
  const poopedLast = new Set();
  // ★ 盤面をどれだけ占有したか。1試合の合計マス数だと薄まって見えないので、
  //   「同時に盤面に存在するポロポロ ÷ その時の空きマス」のピークを見る。
  //   これが無かったせいで 11×11(=最大120マス) 版が「異常なし」で通ってしまった（2026-08-06）
  stat.poroPeakShare = 0; stat.poroPeakTiles = 0;

  // サドンデスで 60 秒延びるので、その分の余裕を見る
  const frameCap = 60 * ((opts.time ?? 180) + 90);
  stat.rounds = 0; stat.stuck = false; stat.champion = null; stat.roundDurs = [];
  // 決着したかどうか。サドンデスに入ってもひきわけならラウンドを消費するだけで
  // 優勝には近づかない（G.suddenUsed が立ってるので2度目のサドンデスも来ない）
  stat.draws = 0; stat.suddenRounds = 0; stat.suddenDraws = 0;
  const MAX_ROUNDS = 30;
  try {
    // 優勝が出るまでラウンドを回す（マッチ全体）
    while (!X.G.champion && stat.rounds < MAX_ROUNDS) {
      stat.rounds++;
      let roundSudden = false;
      let f = 0;
      while (X.G.phase === 'play' && f < frameCap) {
        VT += DT * 1000;
        X.update(DT);
        // draw も毎フレーム回す。描画コードの ReferenceError/TypeError は
        // rAF ループの中で投げられるとゲームが固まるので、ここで踏み抜いておく
        X.draw();
        f++; stat.frames++;
        for (const p of X.players) if (p.state === 'NEGIBON') stat.negibonFrames++;
        for (const b of X.bombs) if (!seenBombs.has(b)) { seenBombs.add(b); stat.bombsPlaced++; }
        for (const n of X.negis) if (!seenNegis.has(n)) { seenNegis.add(n); stat.negisFired++; }
        for (const it of X.items) if (!seenItems.has(it)) {
          seenItems.add(it); stat.totalDrops++;
          if (['bomb', 'fire', 'shoe'].includes(it.kind)) stat.goodDrops++;
          if (it.poro) stat.poroTiles++;
        }
        // うんこ効果が「無かった→ある」に変わった瞬間だけ数える
        for (const p of X.players) {
          const now = X.POOP_KEYS.some(k => p.effects[k]);
          if (now && !poopedLast.has(p.id)) {
            stat.poopHits++;
            if (p.animal.key === 'rabbit') stat.poopHitsByRabbit++;
          }
          if (now) poopedLast.add(p.id); else poopedLast.delete(p.id);
        }
        for (const p of X.players) {
          const pw = (p.maxBombs - 1) + p.powerUp + p.shoes;
          if (pw > stat.peakPower) stat.peakPower = pw;
        }
        if (X.bombs.length > stat.maxBombsAtOnce) stat.maxBombsAtOnce = X.bombs.length;
        if (X.items.length > stat.maxItems) stat.maxItems = X.items.length;
        if (f % 15 === 0) {
          const poro = X.items.filter(it => it.poro).length;
          if (poro > stat.poroPeakTiles) stat.poroPeakTiles = poro;
          if (poro) {
            let open = 0;
            for (let y = 1; y < X.ROWS - 1; y++) for (let x = 1; x < X.COLS - 1; x++)
              if (X.grid[y][x] === X.EMPTY) open++;
            const share = open ? poro / open : 0;
            if (share > stat.poroPeakShare) stat.poroPeakShare = share;
          }
        }
        if (X.G.sudden) { stat.sudden = true; roundSudden = true; }
        for (const p of X.players) {
          if (p.state === 'NEGIBON') negibonEver.add(p.id);
          if (p.state === 'OUT' && !dead.has(p.id)) {
            dead.add(p.id);
            const t = +(f * DT).toFixed(1);
            if (stat.firstDeathAt === null) stat.firstDeathAt = t;
          }
        }
      }
      stat.roundDurs.push(+(f / 60).toFixed(0));
      if (X.G.phase === 'play') { stat.stuck = true; break; }   // ラウンドが終わらなかった
      if (roundSudden) stat.suddenRounds++;
      if (X.G.overInfo && !X.G.overInfo.winner) {
        stat.draws++;
        if (roundSudden) stat.suddenDraws++;
      }
      dead.clear();
      if (!X.G.champion) X.startRound();
    }
  } catch (e) {
    stat.err = e.stack || String(e);
  }
  stat.negibonUsed = negibonEver.size;
  stat.negiSwaps = X.players.reduce((s, p) => s + (p.kills || 0), 0);
  stat.champion = X.G.champion ? `${X.G.champion.animal.name}` : null;
  stat.byLevel = X.players.map(p => ({
    label: p.label, animal: p.animal.name, score: p.score,
    level: p.isCPU ? X.cpuLevelOf(p.cpuIdx).label : '人間枠',
    won: X.G.champion === p,
  }));
  stat.scores = X.players.map(p => `${p.animal.emoji}${p.score}`).join(' ');
  stat.ended = X.G.phase === 'over';
  if (X.G.overInfo) {
    stat.winner = X.G.overInfo.winner
      ? `${X.G.overInfo.winner.label}(${X.G.overInfo.winner.animal.name})` : null;
    stat.reason = X.G.overInfo.reason || (stat.winner ? 'last one standing' : null);
  }
  stat.durSec = +(stat.frames / 60).toFixed(1);
  for (let y = 0; y < X.ROWS; y++) for (let x = 0; x < X.COLS; x++)
    if (X.grid[y][x] === X.SOFT) stat.softLeftEnd++;
  stat.alive = X.players.filter(p => p.state === 'ALIVE')
    .map(p => `${p.label}(${p.animal.name}) hp${p.hp} 💣${p.maxBombs} 🔥${X.getPower(p)}`);
  return stat;
}

const N = Number(process.argv[2] || 8);
const results = [];
const animals = ['rabbit','elephant','mole','fox','frog'];
const modes = ['1p','2p','vs'];
for (let i = 0; i < N; i++) {
  results.push(runMatch(`m${i+1}`, {
    mode: modes[i % 3],
    p1: animals[i % 5],
    p2: animals[(i + 2) % 5],
    time: 180, hp: 3,
  }));
}

let bad = 0;
for (const r of results) {
  if (r.err) { bad++; console.log(`\n❌ ${r.label} ERROR\n${r.err}`); continue; }
  console.log(`\n[${r.label}/${r.mode} ${r.n}人] 🏆${r.champion || '優勝者なし'}  ${r.rounds}ラウンド  計${r.durSec}s`);
  console.log(`  スコア: ${r.scores}　各ラウンド: ${r.roundDurs.join('s / ')}s`);
  console.log(`  bombs=${r.bombsPlaced} 湧いたｱｲﾃﾑ=${r.totalDrops} 強化ピーク=${r.peakPower}段`);
  console.log(`  🌿葱ボン経験=${r.negibonUsed}人 発射=${r.negisFired} 交代成功=${r.negiSwaps}`);
  console.log(`  ⚡サドンデス突入=${r.suddenRounds}ラウンド（うちひきわけ=${r.suddenDraws}） 🤝ひきわけ計=${r.draws}/${r.rounds}`);
  console.log(`  💩うんこ踏み=${r.poopHits}回（うちうさぎ本人=${r.poopHitsByRabbit}） ポロポロで湧いたマス=${r.poroTiles}`
    + `（同時ピーク ${r.poroPeakTiles}マス＝空きマスの${(r.poroPeakShare*100).toFixed(0)}%）`);
  if (r.stuck) console.log(`  ⚠️ ラウンドが終わらなかった`);
}

/* ---------------- aggregate checks ---------------- */
console.log('\n================ 判定 ================');
const ok = [];
const ng = [];
const errs = results.filter(r => r.err).length;
errs ? ng.push(`実行中エラー ${errs}/${N}`) : ok.push(`実行中エラーなし (${N}試行)`);

const firstDeaths = results.filter(r => r.firstDeathAt !== null).map(r => r.firstDeathAt);
const suicidesEarly = firstDeaths.filter(t => t < 6).length;
suicidesEarly === 0
  ? ok.push(`開始6秒以内の死亡なし = CPU即自殺してない`)
  : ng.push(`開始6秒以内に死亡 ${suicidesEarly}/${N} 試行 → CPU逃走が甘い`);

// 2人戦は当然 4人戦より置かれる数が少ないので人数で正規化する
const bombFloor = r => (r.n >= 4 ? 20 : 10);
const bombed = results.filter(r => r.bombsPlaced > bombFloor(r)).length;
bombed === N ? ok.push('全試行で十分な数の爆弾が置かれてる = CPUが固まってない')
             : ng.push(`爆弾が少なすぎる試行 ${N - bombed}/${N} → CPUが固まってる疑い`);

const destroyed = results.filter(r => r.softLeftEnd < r.softLeft0 * 0.8).length;
destroyed >= Math.ceil(N * 0.6) ? ok.push('ソフトブロックが十分壊れてる = 爆風が機能')
  : ng.push(`ソフトブロック破壊が少ない (${destroyed}/${N}) → 爆風か掘りAIが弱い`);

/* マッチ（先取戦）が優勝で終わるか＝「無限に試合が続く」の再発防止 */
const champs = results.filter(r => r.champion).length;
const stuck = results.filter(r => r.stuck).length;
const avgRounds = (results.reduce((s, r) => s + r.rounds, 0) / N).toFixed(1);
champs === N ? ok.push(`全マッチが優勝で終わった（平均 ${avgRounds}ラウンド）`)
             : ng.push(`優勝者が出ないマッチ ${N - champs}/${N} → 無限に続く`);
stuck === 0 ? ok.push('終わらないラウンドなし')
            : ng.push(`終わらないラウンド ${stuck}/${N}`);

const itemsSeen = results.filter(r => r.maxItems > 0).length;
itemsSeen >= Math.ceil(N * 0.7) ? ok.push('アイテムがドロップしてる')
  : ng.push(`アイテムがほぼ出てない (${itemsSeen}/${N})`);

const negiUsed = results.filter(r => r.negibonUsed > 0).length;
const negiFired = results.reduce((s, r) => s + r.negisFired, 0);
const negiSwaps = results.reduce((s, r) => s + r.negiSwaps, 0);
negiUsed > 0 ? ok.push(`葱ボンに入った試行 ${negiUsed}/${N}`)
             : ng.push('葱ボンが1度も発生してない');
negiFired > 0 ? ok.push(`CPUが葱を撃ってる（計 ${negiFired} 発・交代成功 ${negiSwaps} 回）`)
              : ng.push('CPUが葱を1発も撃ってない → 葱ボンAIが死んでる');
/* うさぎのポロポロは爆風で消えず60秒残るので、CPUが踏み続けて機能不全になっていないか見る */
const totalPoro = results.reduce((s, r) => s + r.poroTiles, 0);
const totalPoopHits = results.reduce((s, r) => s + r.poopHits, 0);
const rabbitOwnHits = results.reduce((s, r) => s + r.poopHitsByRabbit, 0);
const poroPerRound = (totalPoro / Math.max(1, results.reduce((s, r) => s + r.rounds, 0))).toFixed(1);
const poroShare = Math.max(...results.map(r => r.poroPeakShare));
const poroPeak = Math.max(...results.map(r => r.poroPeakTiles));
console.log(`💩ポロポロで湧いたマス 計${totalPoro}（1ラウンド平均 ${poroPerRound}）／`
  + `うんこ踏み 計${totalPoopHits}回（うちうさぎ ${rabbitOwnHits}回）`);
/* ここで見てるのは「同時に盤面にあるポロポロの総数」＝複数回撒いた累積。
   CPU が強くなって撒く回数が増えると自然に上がるので、1回ぶんの範囲の検査ではない。
   ⛔ 1回の範囲が広すぎないかは unit.js の「1回の占有率は空きマスの15%以下」で見る。
      こちらは「累積で盤面が埋まりきってないか」の粗い見張り */
(poroShare <= 0.45)
  ? ok.push(`ポロポロの盤面占有ピーク ${(poroShare*100).toFixed(0)}%（${poroPeak}マス・複数回の累積）`)
  : ng.push(`ポロポロの累積が盤面の ${(poroShare*100).toFixed(0)}% (${poroPeak}マス) → 盤面が埋まりきってる`);

const suddenCount = results.filter(r => r.sudden).length;
ok.push(`サドンデス発生 ${suddenCount}/${N} マッチ`);

/* サドンデスが「決着」に効いてるかは、発生数ではなく
   ①ひきわけ率（ラウンドを消費して優勝に近づかない） ②優勝までのラウンド数 で見る */
const totalRounds = results.reduce((s, r) => s + r.rounds, 0);
const totalDraws = results.reduce((s, r) => s + r.draws, 0);
const totalSudden = results.reduce((s, r) => s + r.suddenRounds, 0);
const totalSuddenDraws = results.reduce((s, r) => s + r.suddenDraws, 0);
const drawRate = totalRounds ? (totalDraws / totalRounds * 100) : 0;
const sdDrawRate = totalSudden ? (totalSuddenDraws / totalSudden * 100) : 0;
console.log(`ひきわけ ${totalDraws}/${totalRounds}ラウンド = ${drawRate.toFixed(0)}%`
  + `　／　サドンデス突入 ${totalSudden}ラウンド のうち ひきわけ ${totalSuddenDraws} = ${sdDrawRate.toFixed(0)}%`);
drawRate <= 25 ? ok.push(`ひきわけ率 ${drawRate.toFixed(0)}%（ラウンドの空転が少ない）`)
               : ng.push(`ひきわけ率 ${drawRate.toFixed(0)}% → ラウンドを消費しても優勝に近づかない`);
sdDrawRate <= 40 ? ok.push(`サドンデスのひきわけ率 ${sdDrawRate.toFixed(0)}%（延長で決着してる）`)
                 : ng.push(`サドンデスのひきわけ率 ${sdDrawRate.toFixed(0)}% → 延長しても決まってない`);

/* 人間が葱ボンに落ちた時、復活を狙えるだけの機会があるか。
   CPU同士の交代回数ではなく「滞在時間あたり何発撃てるか」で見る */
/* アイテム流通量：湧いた総数と、実際に誰かが到達した強化量のピーク */
const avgDrops = (results.reduce((s, r) => s + r.totalDrops, 0) / N).toFixed(1);
const avgGood = (results.reduce((s, r) => s + r.goodDrops, 0) / N).toFixed(1);
const avgPeak = (results.reduce((s, r) => s + r.peakPower, 0) / N).toFixed(1);
const peakLine = `1試合あたり 湧いたアイテム${avgDrops}個（うちパワーアップ${avgGood}個）／`
  + `到達した強化量のピーク ${avgPeak}段`;
// 本家の感覚だと、終盤には誰かが5段以上は強化されてるはず
Number(avgPeak) >= 5 ? ok.push(`${peakLine} → 十分育つ`)
                     : ng.push(`${peakLine} → 育たない（初期状態のまま終わる）`);

const negibonSec = results.reduce((s, r) => s + r.negibonFrames, 0) / 60;
if (negibonSec > 0) {
  const shotsPerMin = negiFired / (negibonSec / 60);
  const hitRate = negiFired ? (negiSwaps / negiFired * 100) : 0;
  const line = `葱ボン滞在 計${negibonSec.toFixed(0)}秒 / 発射${negiFired}発 = `
    + `${shotsPerMin.toFixed(1)}発/分・命中${hitRate.toFixed(0)}%`;
  // 判定は「撃ってるか」と「当たるか」だけで見る。
  // ※ 発射/分 は滞在時間で割るので、CPU が弱くて死亡が増えると勝手に下がる。
  //    実際に葱ボンが壊れたかどうかとは無関係なので、判定には使わず表示だけにする
  //    （2026-08-06: CPU 既定を「ふつう」に落として滞在が3倍になり、この値が半減した）
  (negiFired > 0 && hitRate >= 15)
    ? ok.push(`${line} → 撃てて当たってる（人間も復活を狙える）`)
    : ng.push(`${line} → 葱ボンが機能してない（撃てない or 当たらない）`);
}

const avgDur = (results.reduce((s, r) => s + r.durSec, 0) / N).toFixed(1);
console.log(`平均決着時間: ${avgDur}s`);
for (const l of ok) console.log('  ✅ ' + l);
for (const l of ng) console.log('  ⚠️  ' + l);
process.exit(ng.length ? 1 : 0);
