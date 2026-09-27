import type { IntentSource } from '../domain/intent/IntentSource.js';
import type { PlayerIntent } from '../domain/intent/PlayerIntent.js';
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
export class CombinedIntentSource implements IntentSource {
  readonly playerId: IntentSource['playerId'];
  readonly #sources: readonly IntentSource[];

  /** @throws Error 窓口が無いとき、別のプレイヤーの窓口が混ざっているとき */
  constructor(sources: readonly IntentSource[]) {
    const first = sources[0];
    if (first === undefined) throw new Error('まとめる窓口が無い');
    if (sources.some((source) => source.playerId !== first.playerId)) {
      throw new Error('別のプレイヤーの窓口はまとめられない');
    }
    this.playerId = first.playerId;
    this.#sources = sources;
  }

  next(world: Readonly<WorldState>): PlayerIntent {
    // 全部の窓口を毎回読む。途中で打ち切ると、読まれなかった機器が前の状態を覚えたままになる
    // （スティックの戻りの判定などが、次に読まれたときにずれる）。
    const intents = this.#sources.map((source) => source.next(world));
    return {
      up: intents.some((intent) => intent.up),
      down: intents.some((intent) => intent.down),
      left: intents.some((intent) => intent.left),
      right: intents.some((intent) => intent.right),
      bomb: intents.some((intent) => intent.bomb),
      action: intents.some((intent) => intent.action),
    };
  }
}
