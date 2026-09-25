import type { IntentSource } from '../domain/intent/IntentSource.js';
import type { PlayerIntent } from '../domain/intent/PlayerIntent.js';
import { IDLE_INTENT } from '../domain/intent/PlayerIntent.js';
import type { PlayerId } from '../domain/state/PlayerState.js';

/**
 * ゲームパッドの入力。
 *
 * ボタンの並びは、ブラウザが `mapping: "standard"` として正規化した
 * ものを前提にする。製品ごとの対応表を持たずに済む。
 *
 * 以下は実機（Xbox 互換モードを持つ製品）で確認した割り当て。
 *
 * | 番号 | ボタン |
 * |---|---|
 * | 0-3 | A / B / X / Y |
 * | 4-5 | L1 / R1 |
 * | 6-7 | L2 / R2 |
 * | 8-9 | Select / Start |
 * | 10-11 | L3 / R3 |
 * | 12-15 | 十字（上 / 下 / 左 / 右） |
 *
 * ⚠️ 十字キーは軸ではなくボタンとして届く。軸（0,1）は左スティック。
 * ⚠️ HOME は macOS がシステム側で握っていて届かない。
 */
const BUTTON = {
  a: 0,
  b: 1,
  x: 2,
  y: 3,
  l1: 4,
  r1: 5,
  start: 9,
  up: 12,
  down: 13,
  left: 14,
  right: 15,
} as const;

/**
 * スティックを倒したと判定するしきい値と、戻ったと判定するしきい値。
 *
 * 2つに分けてあるのは、境目でちらつくのを防ぐため。
 */
const STICK_ON = 0.5;
const STICK_OFF = 0.35;

/**
 * ⚠️ トリガ（L2 / R2）は割り当てていない。
 *
 * 技のボタンは複数を OR で見るため、トリガに指を乗せているだけで
 * 押しっぱなしと判定され、長押しのとくぎが暴発しうる。
 * `pressed` が立つしきい値はブラウザの実装によって違うので、
 * 実機で測るまで使わない。
 */

/** 読み取ったパッドの状態。テストから差し替えられるよう、配列で受け取る。 */
export type PadSnapshot = {
  readonly mapping: string;
  readonly connected: boolean;
  readonly index: number;
  readonly buttons: readonly { readonly pressed: boolean }[];
  readonly axes: readonly number[];
};

/**
 * パッドの入力を意思に変える窓口。
 *
 * ⚠️ 読み取りに使う関数を引数で受け取るのは、ブラウザの
 * `navigator.getGamepads` に直接触らずにテストできるようにするため。
 * Node には `navigator` が存在するが `getGamepads` は無いので、
 * 素直に書くと実行時に落ちる。
 */
export class GamepadIntentSource implements IntentSource {
  /** 一度つかんだパッドの番号。試合中に別のパッドへ移らないようにする。 */
  #index: number | null = null;

  /** 前回スティックが倒れていた向き。戻りのしきい値に使う。 */
  #stick = { x: 0, y: 0 };

  constructor(
    readonly playerId: PlayerId,
    private readonly read: () => readonly (PadSnapshot | null)[],
  ) {}

  next(): PlayerIntent {
    const pad = this.#pick();
    if (pad === null) return IDLE_INTENT;

    const held = (index: number): boolean => pad.buttons[index]?.pressed === true;
    const stick = this.#readStick(pad);

    return {
      up: held(BUTTON.up) || stick.y < 0,
      down: held(BUTTON.down) || stick.y > 0,
      left: held(BUTTON.left) || stick.x < 0,
      right: held(BUTTON.right) || stick.x > 0,
      bomb: held(BUTTON.a) || held(BUTTON.r1),
      action: held(BUTTON.b) || held(BUTTON.x) || held(BUTTON.y) || held(BUTTON.l1),
    };
  }

  /**
   * 使うパッドを選ぶ。
   *
   * ⚠️ 先頭が繋がっているとは限らない。実機では2番目に入っていた。
   * `mapping` が標準のものを探し、一度見つけたらその番号を覚える。
   */
  #pick(): PadSnapshot | null {
    const pads = this.read();
    if (this.#index !== null) {
      const remembered = pads.find((pad) => pad?.index === this.#index);
      if (remembered != null && remembered.connected) return remembered;
      this.#index = null;
    }
    for (const pad of pads) {
      if (pad == null || !pad.connected) continue;
      if (pad.mapping !== 'standard') continue;
      this.#index = pad.index;
      return pad;
    }
    return null;
  }

  /**
   * スティックの傾きを、上下左右のどれか1方向に落とす。
   *
   * ⚠️ 軸ごとに独立してしきい値を当てると、真上から少し倒しただけで
   * 縦横の両方がしきい値を超える。そのとき移動の側が横を優先するため、
   * 全周のうち3分の1ほどが「押した向きと違う方向」になる。
   * 傾きの大きいほうの軸だけを採る。
   */
  #readStick(pad: PadSnapshot): { x: number; y: number } {
    const rawX = pad.axes[0] ?? 0;
    const rawY = pad.axes[1] ?? 0;
    const horizontal = Math.abs(rawX) >= Math.abs(rawY);
    const value = horizontal ? rawX : rawY;

    // いま倒れている向きは弱いしきい値で保ち、新しく倒すときは強いほうで判定する。
    const active = this.#stick.x !== 0 || this.#stick.y !== 0;
    const threshold = active ? STICK_OFF : STICK_ON;
    if (Math.abs(value) < threshold) {
      this.#stick = { x: 0, y: 0 };
      return this.#stick;
    }
    this.#stick = horizontal
      ? { x: Math.sign(value), y: 0 }
      : { x: 0, y: Math.sign(value) };
    return this.#stick;
  }
}

/**
 * ブラウザからパッドを読む。
 *
 * ⚠️ `navigator` の有無だけで判定しない。Node にも `navigator` は
 * 存在し、`getGamepads` だけが無い。関数があるかまで確かめる。
 */
export function readBrowserGamepads(): readonly (PadSnapshot | null)[] {
  const nav = globalThis.navigator as { getGamepads?: () => readonly (Gamepad | null)[] };
  if (typeof nav?.getGamepads !== 'function') return [];
  return nav.getGamepads().map((pad) =>
    pad === null
      ? null
      : {
          mapping: pad.mapping,
          connected: pad.connected,
          index: pad.index,
          buttons: pad.buttons.map((button) => ({ pressed: button.pressed })),
          axes: [...pad.axes],
        },
  );
}
