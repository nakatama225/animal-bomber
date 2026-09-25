import { defaultMatchConfig } from '../domain/rules/MatchConfig.js';
import { FrameLoop } from '../platform/FrameLoop.js';
import {
  KeyboardIntentSource,
  KeyboardWatcher,
  PLAYER1_KEYS,
  PLAYER2_KEYS,
} from '../platform/Keyboard.js';
import { Presenter } from '../presentation/Presenter.js';
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
 * 2. 操作の出どころを席に割り当てる
 * 3. 実時間のループを tick に換えて回す
 * 4. 起きたイベントを受け取る側へ渡す
 *
 * ⚠️ 描画はまだ繋いでいない。段階7で `presentation/render` を足す。
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
  const config = defaultMatchConfig(seed, ['rabbit', 'elephant']);

  const keyboard = new KeyboardWatcher();
  keyboard.attach();

  const game = new GameSession(config)
    .attach(new KeyboardIntentSource(0, keyboard, PLAYER1_KEYS))
    .attach(new KeyboardIntentSource(1, keyboard, PLAYER2_KEYS));

  const presenter = new Presenter();

  const loop = new FrameLoop({
    onTick: () => {
      presenter.consume(game.tick());
    },
    onDraw: () => {
      context.fillStyle = '#101418';
      context.fillRect(0, 0, canvas.width, canvas.height);
    },
  });
  loop.start();
}

main();
