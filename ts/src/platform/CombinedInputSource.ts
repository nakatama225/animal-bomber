import type { InputSource } from '../domain/input/InputSource.js';
import type { PlayerInput } from '../domain/input/PlayerInput.js';
import type { WorldState } from '../domain/state/WorldState.js';

/**
 * 同じプレイヤーを、複数の入力機器で操作できるようにする窓口。
 *
 * キーボードとゲームパッドのどちらで押しても効くように、ボタンごとに OR をとる。
 * 試合の側から見ると、窓口は1つのまま。
 *
 * ⚠️ 窓口を2つそのまま試合に繋がない。同じプレイヤーの窓口が2つあると、
 * 後に繋いだほうが前のほうを置き換え、片方の機器が効かなくなる。
 */
export class CombinedInputSource implements InputSource {
  readonly playerId: InputSource['playerId'];
  readonly #sources: readonly InputSource[];

  /** @throws Error 窓口が無いとき、別のプレイヤーの窓口が混ざっているとき */
  constructor(sources: readonly InputSource[]) {
    const first = sources[0];
    if (first === undefined) throw new Error('まとめる窓口が無い');
    if (sources.some((source) => source.playerId !== first.playerId)) {
      throw new Error('別のプレイヤーの窓口はまとめられない');
    }
    this.playerId = first.playerId;
    this.#sources = sources;
  }

  next(world: Readonly<WorldState>): PlayerInput {
    // 全部の窓口を毎回読む。途中で打ち切ると、読まれなかった機器が前の状態を覚えたままになる
    // （スティックの戻りの判定などが、次に読まれたときにずれる）。
    const playerInputs = this.#sources.map((source) => source.next(world));
    return {
      up: playerInputs.some((playerInput) => playerInput.up),
      down: playerInputs.some((playerInput) => playerInput.down),
      left: playerInputs.some((playerInput) => playerInput.left),
      right: playerInputs.some((playerInput) => playerInput.right),
      bomb: playerInputs.some((playerInput) => playerInput.bomb),
      action: playerInputs.some((playerInput) => playerInput.action),
      special: playerInputs.some((playerInput) => playerInput.special),
    };
  }
}
