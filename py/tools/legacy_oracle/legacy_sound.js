/* 原型の効果音 36 種と BGM の 32 刻みを鳴らし、作られた部品（発音・削り・音量）と
   その値の動きを JSON に書き出す。Python 版の音の表が原型と同じ値かを検証する正解に使う。
   node legacy_sound.js <出力.json> */
const env = require('./legacy_env.js');
const { X, audio, chainOf } = env;

const out = process.argv[2];
X.CFG.sfx = true; X.CFG.bgm = true;
env.setRandom(Array.from({ length: 48000 }, (_, i) => (i % 7) / 7));
X.A.init();
env.setRandom(null);
const busNames = new Map([[X.A.sfx, 'sfx'], [X.A.bgm, 'bgm']]);
const buses = { sfx: X.A.sfx.gain.value, bgm: X.A.bgm.gain.value };

function capture(fn) {
  audio.voices = [];
  fn();
  return audio.voices.map(v => chainOf(v, busNames));
}

const names = Object.keys(X.SE);
const sounds = {};
for (const name of names) {
  sounds[name] = capture(() => X.SE[name]());
}
// 連鎖した爆発は音が変わる（引数あり）
sounds['explode(2)'] = capture(() => X.SE.explode(2));
sounds['explode(5)'] = capture(() => X.SE.explode(5));

// BGM：刻み s を、時刻 t に予約したときの部品（t は 0 から刻みの長さずつ）
const dt = 60 / X.BGM.tempo / 4;
const bgm = [];
for (let s = 0; s < 32; s++) {
  bgm.push({ step: s, t: s * dt, voices: capture(() => X.BGM.play(s, s * dt)) });
}

const result = {
  source: 'legacy/animal-bomber.html（A・noiseBurst・tone・SE・BGM）',
  sampleRate: X.A.ctx.sampleRate,
  noiseSeconds: X.A.noise.length / X.A.noise.sampleRate,
  buses,
  tempo: X.BGM.tempo,
  bassPat: X.BGM.bassPat,
  arpPat: X.BGM.arpPat,
  seNames: names,
  sounds,
  bgm,
};
require('fs').writeFileSync(out, JSON.stringify(result, null, 1));
console.log('SE', names.length, names.join(','));
console.log('bgm steps', bgm.length, 'voices', bgm.reduce((a, b) => a + b.voices.length, 0));
