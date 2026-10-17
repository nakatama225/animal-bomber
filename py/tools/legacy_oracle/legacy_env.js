/* 原型（legacy/animal-bomber.html）を node で読み込み、描画の命令と音の部品を記録する環境。
   legacy/test/unit.js の読み込み方を写し、canvas と AudioContext だけを記録する偽物に替えた。
   使い方: const env = require('./legacy_env.js'); env.X（原型の中身）・env.rec（描画の記録）・env.audio（音の記録） */
const fs = require('fs');
const path = require('path');

// このファイルは py/tools/legacy_oracle/ に置いてある。原型はリポジトリの頂の legacy/ にある。
const HTML = process.env.LEGACY_HTML
  || path.join(__dirname, '..', '..', '..', 'legacy', 'animal-bomber.html');
const src = fs.readFileSync(HTML, 'utf8');
let code = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];

/* ---------- 乱数：種つきの列に差し替える（原型の Math.random を引く順を、Python の見た目の乱数に渡せるように） ---------- */
let randomQueue = null;   // 配列を入れると、その順に返す（使い切ったら例外）
let randomLog = null;     // 配列を入れると、返した値を足していく
function seededRandom() {
  if (randomQueue === null) throw new Error('Math.random を呼んだが、列を用意していない');
  if (randomQueue.length === 0) throw new Error('用意した乱数の列を使い切った');
  const v = randomQueue.shift();
  if (randomLog) randomLog.push(v);
  return v;
}

/* ---------- 描画の記録 ---------- */
const rec = { ops: [], gradients: 0 };
function num(v) { return v; }
function makeGradient(kind, args) {
  const id = rec.gradients++;
  const g = { __gradient: id, addColorStop(offset, color) { rec.ops.push(['addColorStop', id, offset, color]); } };
  rec.ops.push([kind, id, ...args]);
  return g;
}
const STATE_KEYS = ['fillStyle', 'strokeStyle', 'lineWidth', 'globalAlpha', 'lineCap', 'lineJoin',
  'font', 'textAlign', 'textBaseline'];
const DEFAULT_STATE = { fillStyle: '#000000', strokeStyle: '#000000', lineWidth: 1, globalAlpha: 1,
  lineCap: 'butt', lineJoin: 'miter', font: '10px sans-serif', textAlign: 'start', textBaseline: 'alphabetic' };
let state = { ...DEFAULT_STATE };
const stack = [];
const ctxTarget = {
  canvas: { width: 0, height: 0 },
  measureText: (s) => ({ width: 10 * String(s).length }),
  createLinearGradient: (...a) => makeGradient('createLinearGradient', a),
  createRadialGradient: (...a) => makeGradient('createRadialGradient', a),
  save() { stack.push({ ...state }); rec.ops.push(['save']); },
  restore() { if (stack.length) state = stack.pop(); rec.ops.push(['restore']); },
};
const ctxRec = new Proxy(ctxTarget, {
  get(t, k) {
    if (k in t) return t[k];
    if (STATE_KEYS.includes(k)) return state[k];
    if (typeof k === 'symbol') return undefined;
    return (...args) => {
      rec.ops.push([k, ...args.map(a => (Array.isArray(a) ? a.slice() : a))]);
    };
  },
  set(t, k, v) {
    if (STATE_KEYS.includes(k)) {
      state[k] = v;
      rec.ops.push(['set', k, v && v.__gradient !== undefined ? { gradient: v.__gradient } : v]);
      return true;
    }
    rec.ops.push(['set', k, v]);
    return true;
  },
});
function resetCanvas() {
  rec.ops = []; rec.gradients = 0; state = { ...DEFAULT_STATE }; stack.length = 0;
}

/* ---------- 音の記録 ---------- */
const audio = { voices: [], nodes: 0, currentTime: 0 };
function makeParam(owner, name, initial) {
  const p = {
    _v: initial,
    get value() { return this._v; },
    set value(v) { this._v = v; owner.log.push([name, 'value', v]); },
    setValueAtTime(v, t) { owner.log.push([name, 'setValueAtTime', v, t]); },
    exponentialRampToValueAtTime(v, t) { owner.log.push([name, 'exponentialRampToValueAtTime', v, t]); },
    linearRampToValueAtTime(v, t) { owner.log.push([name, 'linearRampToValueAtTime', v, t]); },
  };
  return p;
}
function makeNode(kind) {
  const n = { kind, id: audio.nodes++, log: [], out: null };
  n.connect = (dest) => { n.out = dest; return dest; };
  return n;
}
class FakeAudioContext {
  constructor() { this.sampleRate = 48000; this.state = 'running'; this.destination = { kind: 'destination', id: -1 }; }
  get currentTime() { return audio.currentTime; }
  resume() { return Promise.resolve(); }
  createGain() { const n = makeNode('gain'); n.gain = makeParam(n, 'gain', 1); return n; }
  createOscillator() {
    const n = makeNode('oscillator'); n.frequency = makeParam(n, 'frequency', 440);
    let type = 'sine';
    Object.defineProperty(n, 'type', { get: () => type, set: (v) => { type = v; n.log.push(['type', v]); } });
    n.start = (t) => { n.log.push(['start', t]); audio.voices.push(n); };
    n.stop = (t) => n.log.push(['stop', t]);
    return n;
  }
  createBufferSource() {
    const n = makeNode('bufferSource');
    n.start = (t) => { n.log.push(['start', t]); audio.voices.push(n); };
    n.stop = (t) => n.log.push(['stop', t]);
    let loop = false;
    Object.defineProperty(n, 'loop', { get: () => loop, set: (v) => { loop = v; n.log.push(['loop', v]); } });
    return n;
  }
  createBiquadFilter() {
    const n = makeNode('biquad'); n.frequency = makeParam(n, 'frequency', 350); n.Q = makeParam(n, 'Q', 1);
    let type = 'lowpass';
    Object.defineProperty(n, 'type', { get: () => type, set: (v) => { type = v; n.log.push(['type', v]); } });
    return n;
  }
  createBuffer(ch, len, rate) {
    const data = new Float32Array(len);
    return { numberOfChannels: ch, length: len, sampleRate: rate, getChannelData: () => data };
  }
}
/** 鳴らした音1つ（発音の部品）から、出口までの部品の並びをたどって平らにする。 */
function chainOf(src, busNames) {
  const chain = [];
  let n = src;
  while (n && n.kind !== 'destination') {
    if (busNames.has(n)) { chain.push({ bus: busNames.get(n) }); break; }
    chain.push({ kind: n.kind, log: n.log.slice() });
    n = n.out;
  }
  return chain;
}

/* ---------- DOM の偽物（unit.js と同じ） ---------- */
const noop = () => {};
const makeEl = () => ({
  classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
  style: {}, kids: [], appendChild(c) { this.kids.push(c); return c; },
  isConnected: true, innerHTML: '', textContent: '', onclick: null,
  getContext: () => ctxRec, width: 0, height: 0, addEventListener: noop,
});
const cache = new Map();
global.window = { addEventListener: noop, AudioContext: FakeAudioContext };
global.document = {
  getElementById(id) { if (!cache.has(id)) cache.set(id, makeEl()); return cache.get(id); },
  createElement: makeEl, addEventListener: noop,
  querySelector: () => makeEl(), querySelectorAll: () => [],
};
global.performance = { now: () => 0 };
global.requestAnimationFrame = () => 0;
global.cancelAnimationFrame = noop;
global.setInterval = () => 0; global.clearInterval = noop;
global.setTimeout = () => 0; global.clearTimeout = noop;

code += `
global.__X = {
  get G(){return G}, get players(){return players}, set players(v){players=v},
  get bombs(){return bombs}, set bombs(v){bombs=v},
  get blasts(){return blasts}, set blasts(v){blasts=v},
  get items(){return items}, set items(v){items=v},
  get grid(){return grid}, set grid(v){grid=v},
  get particles(){return particles}, set particles(v){particles=v},
  get foxfires(){return foxfires}, set foxfires(v){foxfires=v},
  get slimes(){return slimes}, set slimes(v){slimes=v},
  get negis(){return negis}, set negis(v){negis=v},
  get shakeAmt(){return shakeAmt}, set shakeAmt(v){shakeAmt=v},
  get TILE(){return TILE}, set TILE(v){TILE=v},
  get OX(){return OX}, set OX(v){OX=v}, get OY(){return OY}, set OY(v){OY=v},
  get CW(){return CW}, set CW(v){CW=v}, get CH(){return CH}, set CH(v){CH=v},
  draw, drawTile, drawItem, drawBomb, drawBlast, drawPlayer, drawAnimalBody, drawTongue, drawDigging,
  drawSlimes, drawFoxfires, drawParticle, drawNegibons, roundRect, drawEye, triEar, inkLine,
  headRabbit, headMole, headFox, headFrog, drawTail, drawElephantHead,
  puff, shake, kill, hurt, destroySoft, blowPoop, spitPowerup, makePlayer, startGame, startRound, update,
  hop, elephantSnot, chargeSweep, chargeDrop, explodeChain, spawnBomb,
  A, SE, BGM, tone, noiseBurst, CFG, ANIMALS, ITEM_DEF, POOPS, POOP_KEYS, SPECIALS, specialOf, specialHoldOf,
  COLS, ROWS, LANE, EMPTY, HARD, SOFT, BOMB_FUSE, BLAST_DUR, INVULN, FOX_LEAP, PORO_TIME, PORO_LIFE, POOP_LIFE,
  SNOT_MELT, PIT_DIG, PIT_HOLD, TONGUE_STEP, SLIME_FLY, IT_POOP, IT_BANANA, IT_ONION, IT_CHICKEN,
  IT_BOMB, IT_FIRE, IT_SHOE,
};`;
const realRandom = Math.random;
Math.random = seededRandom;
randomQueue = [];
// 読み込むときに Math.random を引く所があれば、ここで列を足す必要がある。
randomQueue = Array.from({ length: 100000 }, (_, i) => ((i * 0.6180339887498949) % 1));
new Function(code)();
randomQueue = null;
const X = global.__X;

module.exports = {
  X, rec, audio, resetCanvas, chainOf,
  setRandom(values) { randomQueue = values ? values.slice() : null; },
  randomLeft() { return randomQueue ? randomQueue.length : null; },
  setRandomLog(arr) { randomLog = arr; },
  realRandom,
};
