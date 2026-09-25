import type { IntentSource } from '../domain/intent/IntentSource.js';
import type { PlayerIntent } from '../domain/intent/PlayerIntent.js';
import type { PlayerId } from '../domain/state/PlayerState.js';

/**
 * どのキーがどの操作に当たるか。
 *
 * 1台のキーボードで2人が同時に触るため、1P は左側、2P は右側に
 * 固めてある。加えて、移動をどちらの手でやっても反対の手で爆弾を
 * 押せるよう、爆弾のキーを左右に1つずつ持たせている。
 *
 * ⛔ Option（Alt）を主のキーにしない。macOS は修飾キーを押している間
 * 他のキーの keyup を送らないことがあり、「たまに効かない」が起きる。
 * ⛔ Command（Meta）はどの席にも使えない。ブラウザが予約していて
 * `preventDefault` も効かないため、cmd+W でタブが閉じる。
 */
export interface KeyBinding {
  readonly up: readonly string[];
  readonly down: readonly string[];
  readonly left: readonly string[];
  readonly right: readonly string[];
  readonly bomb: readonly string[];
  readonly action: readonly string[];
}

/** 1人で遊ぶときの配置。WASD と矢印の両方を受ける。 */
export const SOLO_KEYS: KeyBinding = {
  up: ['KeyW', 'ArrowUp'],
  down: ['KeyS', 'ArrowDown'],
  left: ['KeyA', 'ArrowLeft'],
  right: ['KeyD', 'ArrowRight'],
  bomb: ['Space', 'Enter', 'KeyZ', 'Slash'],
  action: ['KeyE', 'KeyQ', 'ShiftLeft', 'ShiftRight'],
};

/** 2人で遊ぶときの、左側の席。 */
export const PLAYER1_KEYS: KeyBinding = {
  up: ['KeyW'],
  down: ['KeyS'],
  left: ['KeyA'],
  right: ['KeyD'],
  bomb: ['Space', 'KeyZ'],
  action: ['KeyE', 'KeyQ', 'ShiftLeft'],
};

/** 2人で遊ぶときの、右側の席。 */
export const PLAYER2_KEYS: KeyBinding = {
  up: ['ArrowUp'],
  down: ['ArrowDown'],
  left: ['ArrowLeft'],
  right: ['ArrowRight'],
  bomb: ['Enter', 'Slash'],
  action: ['Period', 'Comma', 'ShiftRight'],
};

/**
 * 押されているキーを答えるもの。
 *
 * `KeyboardIntentSource` がこの形だけに依存するので、テストでは
 * ブラウザのイベントを起こさずに好きな状態を渡せる。
 */
export interface KeyStateReader {
  anyOf(codes: readonly string[]): boolean;
}

/**
 * いま押されているキーを持つ。
 *
 * ブラウザの入力を受けるのはこのクラスだけで、ルールの層には
 * 「どのキーか」も「いつ押したか」も届かない。
 */
export class KeyboardWatcher implements KeyStateReader {
  readonly #pressed = new Set<string>();
  #attached = false;

  readonly #onDown = (event: KeyboardEvent): void => {
    this.#pressed.add(event.code);
  };

  readonly #onUp = (event: KeyboardEvent): void => {
    this.#pressed.delete(event.code);
  };

  /**
   * 画面から離れたときに、押しっぱなしの状態を消す。
   *
   * これが無いと、キーを押したままタブを切り替えて戻ったときに
   * 壁へ向かって歩き続ける。離したことがブラウザから通知されないため。
   */
  readonly #onBlur = (): void => {
    this.#pressed.clear();
  };

  attach(target: Window = window): void {
    if (this.#attached) return;
    target.addEventListener('keydown', this.#onDown);
    target.addEventListener('keyup', this.#onUp);
    target.addEventListener('blur', this.#onBlur);
    this.#attached = true;
  }

  detach(target: Window = window): void {
    if (!this.#attached) return;
    target.removeEventListener('keydown', this.#onDown);
    target.removeEventListener('keyup', this.#onUp);
    target.removeEventListener('blur', this.#onBlur);
    this.#pressed.clear();
    this.#attached = false;
  }

  /** そのキーのどれかが押されているか。 */
  anyOf(codes: readonly string[]): boolean {
    return codes.some((code) => this.#pressed.has(code));
  }
}

/**
 * キーボードの入力を意思に変える窓口。
 *
 * CPU や通信から届く窓口と同じ資格で `Simulation` に繋がる。
 * ゲーム本体はこれがキーボードだと知らない。
 */
export class KeyboardIntentSource implements IntentSource {
  constructor(
    readonly playerId: PlayerId,
    private readonly watcher: KeyStateReader,
    private readonly binding: KeyBinding,
  ) {}

  next(): PlayerIntent {
    return {
      up: this.watcher.anyOf(this.binding.up),
      down: this.watcher.anyOf(this.binding.down),
      left: this.watcher.anyOf(this.binding.left),
      right: this.watcher.anyOf(this.binding.right),
      bomb: this.watcher.anyOf(this.binding.bomb),
      action: this.watcher.anyOf(this.binding.action),
    };
  }
}
