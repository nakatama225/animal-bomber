import { CPU_LEVELS } from '../ai/CpuLevel.js';
import { CpuIntentSource, cpuSeed } from '../ai/CpuIntentSource.js';
import { defaultMatchConfig, type MatchConfig } from '../domain/rules/MatchConfig.js';
import { FrameLoop } from '../platform/FrameLoop.js';
import { parseRelayAddress } from '../platform/WebSocketLink.js';
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
import { LanMatch } from './LanMatch.js';
import { LocalMatch, type MatchRunner } from './MatchRunner.js';

/**
 * 起動の入口。**配線だけを行い、判断を持たない。**
 *
 * この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が
 * 見つかっていないということなので、ここで処理せず置き場所を探す。
 *
 * 下の並びが、この実装の全体像になっている。
 *
 * 1. 試合の設定を作る
 * 2. 操作の出どころを各プレイヤーに割り当てる（1台で遊ぶか、通信対戦か）
 * 3. 実時間のループを tick に換えて回す
 * 4. 起きたイベントを受け取る側（音・画面）へ渡す
 *
 * 通信対戦にするには、URL に `?relay` を付ける。このページを配っている端末の 8777 番の
 * 中継サーバにつなぐ。別の場所の中継なら `?relay=端末名.local:8777` と書く。
 */

const CANVAS_ID = 'stage';
const ANIMALS = ['rabbit', 'elephant', 'fox', 'frog'];

/** 中継サーバの既定のポート。`server/` の `DEFAULT_PORT` と同じ値。 */
const DEFAULT_RELAY_PORT = 8777;

function findElement<T extends HTMLElement>(id: string, type: new () => T): T {
  const element = document.getElementById(id);
  if (!(element instanceof type)) {
    throw new Error(`#${id} が見つからないか、${type.name} ではない`);
  }
  return element;
}

/**
 * URL の `?relay` の値。付いていなければ null（1台で遊ぶ）。
 *
 * 値を省いたときは、このページを配っている端末の中継サーバを指す。
 */
function relayParameter(): string | null {
  const value = new URLSearchParams(window.location.search).get('relay');
  if (value === null) return null;
  return value === '' ? `${window.location.hostname}:${DEFAULT_RELAY_PORT}` : value;
}

/**
 * 1台で遊ぶ試合。
 *
 * プレイヤー 0・1 はキーボード、2・3 は CPU。ゲーム本体からは区別がつかない。
 * 強さを選ぶ画面は段階10で足す。
 */
function localMatch(config: MatchConfig, keyboard: KeyboardWatcher): MatchRunner {
  const game = new GameSession(config)
    .attach(new KeyboardIntentSource(0, keyboard, PLAYER1_KEYS))
    .attach(new KeyboardIntentSource(1, keyboard, PLAYER2_KEYS))
    .attach(new CpuIntentSource(2, CPU_LEVELS.normal, cpuSeed(config.seed, 2)))
    .attach(new CpuIntentSource(3, CPU_LEVELS.normal, cpuSeed(config.seed, 3)));
  return new LocalMatch(game);
}

function main(): void {
  const canvas = findElement(CANVAS_ID, HTMLCanvasElement);
  const context = canvas.getContext('2d');
  if (context === null) {
    throw new Error('2D の描画コンテキストを取得できない');
  }

  // 種は起動のたびに変えたいが、ルールの層で乱数や時刻に触れない。
  // 実時間を読むのはブラウザに近いこの層の役目なので、ここで決める。
  // 通信対戦では、ホストの種が全員に配られる。
  const seed = Math.floor(Date.now() % 0xffffffff);
  const config = defaultMatchConfig(seed, ANIMALS);

  const keyboard = new KeyboardWatcher();
  keyboard.attach();

  const relay = relayParameter();
  const address = relay === null ? null : parseRelayAddress(relay);
  if (relay !== null && address === null) {
    // 1台で遊ぶ形に黙って切り替えない。通信対戦のつもりで開いた人が、理由を知らないまま
    // CPU と遊び始めてしまう。
    const status = findElement('lan-status', HTMLElement);
    status.textContent = `?relay の値が読めない：${relay}（例：?relay=端末名.local:8777）`;
    status.hidden = false;
    return;
  }
  const match: MatchRunner =
    address === null
      ? localMatch(config, keyboard)
      : new LanMatch({
          address,
          settings: { match: config, cpu: config.animals.map(() => 'normal') },
          keyboard,
          status: findElement('lan-status', HTMLElement),
          startButton: findElement('lan-start', HTMLButtonElement),
        });

  const synth = new Synth();
  const music = new Music(synth);
  const presenter = new Presenter(new WebAudioSoundBank(synth));
  const renderer = new Renderer(context, canvas.width, canvas.height);

  // ブラウザは、画面を操作するまで音を出させない。キーやクリックのたびに
  // 音を鳴らす仕組みを（初回だけ）作り、止まっていれば動かし直す（何度呼んでもよい）。
  // 曲は試合の間だけ鳴らす。
  const unlockAudio = (): void => {
    synth.unlock();
    if (match.inProgress) music.start();
  };
  window.addEventListener('keydown', unlockAudio);
  window.addEventListener('pointerdown', unlockAudio);

  const loop = new FrameLoop({
    onTick: () => {
      const world = match.world;
      // 通信対戦では、全員の入力がそろうまで進めない。
      if (world === null || !match.ready) return;
      // ラウンドが終わると盤面が作り直されるので、進める前の盤面を控えて渡す。
      renderer.beforeTick(world);
      const events = match.step();
      presenter.consume(events, world);
      renderer.afterTick(events, world);
    },
    onDraw: (alpha) => {
      const world = match.world;
      if (world !== null) renderer.draw(world, alpha);
      match.afterDraw();
      // 試合が終わったときだけでなく、通信対戦が止まったとき（ずれ・切断）も止める。
      // 止まると tick が進まないので、tick の側ではなく毎回描く側で見る。
      if (!match.inProgress) music.stop();
    },
  });
  loop.start();
}

main();
