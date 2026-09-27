import type { IntentSource } from '../domain/intent/IntentSource.js';
import type { PlayerIntent } from '../domain/intent/PlayerIntent.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import type { NavCommand } from '../presentation/menu/MenuCursor.js';

/**
 * どのキーがどの操作に当たるか。
 *
 * 1台のキーボードで2人が同時に触るため、1P は左側、2P は右側に
 * 固めてある。加えて、移動をどちらの手でやっても反対の手で爆弾を
 * 押せるよう、爆弾のキーを左右に1つずつ持たせている。
 *
 * ⛔ Option（Alt）を主のキーにしない。macOS は修飾キーを押している間
 * 他のキーの keyup を送らないことがあり、「たまに効かない」が起きる。
 * ⛔ Command（Meta）はどのプレイヤーの操作にも使えない。ブラウザが予約していて
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

/** 2人で遊ぶときの、キーボードの左側を使うプレイヤー。 */
export const PLAYER1_KEYS: KeyBinding = {
  up: ['KeyW'],
  down: ['KeyS'],
  left: ['KeyA'],
  right: ['KeyD'],
  bomb: ['Space', 'KeyZ'],
  action: ['KeyE', 'KeyQ', 'ShiftLeft'],
};

/** 2人で遊ぶときの、キーボードの右側を使うプレイヤー。 */
export const PLAYER2_KEYS: KeyBinding = {
  up: ['ArrowUp'],
  down: ['ArrowDown'],
  left: ['ArrowLeft'],
  right: ['ArrowRight'],
  bomb: ['Enter', 'Slash'],
  action: ['Period', 'Comma', 'ShiftRight'],
};

/** どの配置かにかかわらず、試合の操作に使うキー。 */
export const GAME_KEYS: readonly string[] = [
  ...new Set(
    [SOLO_KEYS, PLAYER1_KEYS, PLAYER2_KEYS].flatMap((binding) => [
      ...binding.up,
      ...binding.down,
      ...binding.left,
      ...binding.right,
      ...binding.bomb,
      ...binding.action,
    ]),
  ),
];

/**
 * メニューを動かすキーと、その操作（原型と同じ）。
 *
 * 決定は Enter と Space。どちらも爆弾のキーなので、決定で「はじめる」を押すと、押したまま
 * 試合が始まる。ルールの層が、ラウンドの始まりに押していた爆弾のボタンを離すまで効かなくして
 * いるので、開始位置に爆弾は置かれない（`WorldState.ts` の `HELD_AT_ROUND_START`）。
 */
const NAV_COMMANDS: Readonly<Record<string, NavCommand>> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
  Enter: 'confirm',
  Space: 'confirm',
  Escape: 'back',
  Backspace: 'back',
};

/** その操作に当たるキー（表の順）。遊び方の説明に使う。 */
export function navKeysOf(command: NavCommand): string[] {
  return Object.entries(NAV_COMMANDS)
    .filter(([, bound]) => bound === command)
    .map(([code]) => code);
}

/**
 * メニューの画面の間、ブラウザの既定の動きを止めるキー。
 *
 * 矢印と Space は、画面が縦に収まらないときにページを動かす。メニューでは、動かす代わりに
 * カーソルの項目が見える所までだけ動かす。Escape は止めない（全画面の解除などに使う）。
 */
export const MENU_KEYS: readonly string[] = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space', 'Enter'];

/**
 * キーを押したことを、メニューの操作に翻訳する。メニューの操作に使わないキーなら null。
 *
 * 押し続けたときの繰り返し（`repeat`）は数えない。Command・Ctrl・Option と一緒のときも数えない
 * （ブラウザの操作に使う）。
 */
export function navCommandOf(
  event: Pick<KeyboardEvent, 'code' | 'repeat' | 'metaKey' | 'ctrlKey' | 'altKey'>,
): NavCommand | null {
  if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return null;
  return NAV_COMMANDS[event.code] ?? null;
}

/**
 * 押されているキーを答えるもの。
 *
 * `KeyboardIntentSource` がこの形だけに依存するので、テストでは
 * ブラウザのイベントを起こさずに好きな状態を渡せる。
 */
export interface KeyStateReader {
  readonly anyOf: (codes: readonly string[]) => boolean;
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
  #captured: ReadonlySet<string> = new Set();

  readonly #onDown = (event: KeyboardEvent): void => {
    this.#pressed.add(event.code);
    // Command・Ctrl・Option と一緒のときは止めない（ブックマークや保存など、ブラウザの操作に使う）。
    // Shift は技のキーなので、一緒でも止める。
    const withModifier = event.metaKey || event.ctrlKey || event.altKey;
    if (this.#captured.has(event.code) && !withModifier) event.preventDefault();
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

  /**
   * このキーの、ブラウザの既定の動きを止める（止めるキーを差し替える）。
   *
   * 矢印と Space は、画面が縦に収まらないときにページを動かす。試合の最中に盤面が
   * ずれて見えなくなるので、試合の画面の間は `GAME_KEYS` を、メニューの間は `MENU_KEYS` を渡して止める。
   * 押されたことは、止めても止めなくても数える。
   */
  capture(codes: readonly string[]): void {
    this.#captured = new Set(codes);
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
