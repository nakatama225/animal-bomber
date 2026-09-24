import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import { IDLE_INTENT, type PlayerIntent } from './PlayerIntent.js';

/**
 * 「この tick に何をしたいか」を答えるもの。
 *
 * ゲーム本体はこの窓口だけを知っていて、その先が何かを知らない。
 * 実装は同じ資格で並ぶ。
 *
 * | 実装 | 置き場所 | いつ作るか |
 * |---|---|---|
 * | キーボード | `platform/` | 段階 4 |
 * | ゲームパッド | `platform/` | 段階 4 |
 * | CPU | `ai/` | 段階 6 |
 * | 記録の再生 | `net/` | 段階 1（この段階） |
 * | 通信で届いた操作 | `net/` | 段階 9 |
 *
 * ⚠️ 将来 CPU をルールベースから機械学習や強化学習に差し替える場合も、
 * 足すのはこの窓口の実装1つだけになる。ゲーム本体には手を入れない。
 * そのとき守る約束は3つ。
 *
 * 1. 盤面を直接書き換えず、意思を返すだけにする
 * 2. 状態は読むだけ（`WorldState` を受け取るが変更しない）
 * 3. 判断に時間がかかっても tick の同期を崩さない
 *    （間に合わなければ前回の意思を使い回すなど、この層の内側で吸収する）
 */
export interface IntentSource {
  /** どの席の意思を返すか。 */
  readonly playerId: PlayerId;

  /**
   * この tick の意思を返す。
   *
   * ⚠️ `world` は読むだけ。ここで書き換えると、意思を返す前に
   * 状態が変わることになり、リプレイと通信対戦の前提が崩れる。
   */
  next(world: Readonly<WorldState>): PlayerIntent;
}

/**
 * 何もしない窓口。
 *
 * 接続が切れた席や、まだ誰も座っていない席を、`undefined` の分岐を
 * 増やさずに扱うために使う。
 */
export class IdleIntentSource implements IntentSource {
  constructor(readonly playerId: PlayerId) {}

  next(): PlayerIntent {
    return IDLE_INTENT;
  }
}

/**
 * 窓口を集めて、1 tick ぶんの意思をまとめて取り出す。
 *
 * 席ごとに窓口が違ってよい。人間1人・CPU3人でも、人間2人・記録の再生2人でも、
 * ゲーム本体から見ると区別がつかない。
 */
export class IntentGatherer {
  readonly #sources = new Map<PlayerId, IntentSource>();

  add(source: IntentSource): this {
    this.#sources.set(source.playerId, source);
    return this;
  }

  /** この tick の意思を、席ごとに集める。 */
  gather(world: Readonly<WorldState>): ReadonlyMap<PlayerId, PlayerIntent> {
    const result = new Map<PlayerId, PlayerIntent>();
    // 席の順に集める。窓口を登録した順ではない。登録順に依存すると、
    // 参加の仕方で結果が変わりうる。
    for (const player of world.players) {
      const source = this.#sources.get(player.id);
      result.set(player.id, source === undefined ? IDLE_INTENT : source.next(world));
    }
    return result;
  }
}
