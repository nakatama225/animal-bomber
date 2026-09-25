import { CPU_LEVELS } from '../ai/CpuLevel.js';
import { CpuIntentSource, cpuSeed } from '../ai/CpuIntentSource.js';
import { defaultMatchConfig } from '../domain/rules/MatchConfig.js';
import { FrameLoop } from '../platform/FrameLoop.js';
import {
  KeyboardIntentSource,
  KeyboardWatcher,
  PLAYER1_KEYS,
  PLAYER2_KEYS,
} from '../platform/Keyboard.js';
import { Music } from '../presentation/audio/Music.js';
import { Synth } from '../presentation/audio/Synth.js';
import { WebAudioSoundBank } from '../presentation/audio/WebAudioSoundBank.js';
import { Presenter } from '../presentation/Presenter.js';
import { Renderer } from '../presentation/render/Renderer.js';
import { GameSession } from './GameSession.js';

/**
 * 起動の入口。**配線だけを行い、判断を持たない。**
 *
 * この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が
 * 見つかっていないということなので、ここで処理せず置き場所を探す。
 *
 * 下の並びが、この実装の全体像になっている。
 *
 * 1. 試合の設定を作る
 * 2. 操作の出どころを各プレイヤーに割り当てる
 * 3. 実時間のループを tick に換えて回す
 * 4. 起きたイベントを受け取る側（音・画面）へ渡す
 *
 */

const CANVAS_ID = 'stage';

function findCanvas(): HTMLCanvasElement {
  const element = document.getElementById(CANVAS_ID);
  if (!(element instanceof HTMLCanvasElement)) {
    throw new Error(`#${CANVAS_ID} が見つからないか、canvas ではない`);
  }
  return element;
}

function main(): void {
  const canvas = findCanvas();
  const context = canvas.getContext('2d');
  if (context === null) {
    throw new Error('2D の描画コンテキストを取得できない');
  }

  // 種は起動のたびに変えたいが、ルールの層で乱数や時刻に触れない。
  // 実時間を読むのはブラウザに近いこの層の役目なので、ここで決める。
  const seed = Math.floor(Date.now() % 0xffffffff);
  const config = defaultMatchConfig(seed, ['rabbit', 'elephant', 'fox', 'frog']);

  const keyboard = new KeyboardWatcher();
  keyboard.attach();

  // プレイヤー 0・1 はキーボード、2・3 は CPU。ゲーム本体からは区別がつかない。
  // 強さを選ぶ画面は段階10で足す。
  const game = new GameSession(config)
    .attach(new KeyboardIntentSource(0, keyboard, PLAYER1_KEYS))
    .attach(new KeyboardIntentSource(1, keyboard, PLAYER2_KEYS))
    .attach(new CpuIntentSource(2, CPU_LEVELS.normal, cpuSeed(seed, 2)))
    .attach(new CpuIntentSource(3, CPU_LEVELS.normal, cpuSeed(seed, 3)));

  const synth = new Synth();
  const music = new Music(synth);
  const presenter = new Presenter(new WebAudioSoundBank(synth));
  const renderer = new Renderer(context, canvas.width, canvas.height);

  // ブラウザは、画面を操作するまで音を出させない。キーやクリックのたびに
  // 音を鳴らす仕組みを（初回だけ）作り、止まっていれば動かし直す（何度呼んでもよい）。
  // 曲は試合の間だけ鳴らす。
  const unlockAudio = (): void => {
    synth.unlock();
    if (!game.match.finished) music.start();
  };
  window.addEventListener('keydown', unlockAudio);
  window.addEventListener('pointerdown', unlockAudio);

  const loop = new FrameLoop({
    onTick: () => {
      // ラウンドが終わると盤面が作り直されるので、進める前の盤面を控えて渡す。
      const world = game.world;
      renderer.beforeTick(world);
      const events = game.tick();
      presenter.consume(events, world);
      renderer.afterTick(events, world);
      if (game.match.finished) music.stop();
    },
    onDraw: (alpha) => {
      renderer.draw(game.world, alpha);
    },
  });
  loop.start();
}

main();
