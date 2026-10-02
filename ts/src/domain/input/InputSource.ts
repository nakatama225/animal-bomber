import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import { IDLE_INPUT, type PlayerInput } from './PlayerInput.js';

/**
 * 1人ぶんの入力を、tick ごとに返す窓口。
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
 * 1. 盤面を直接書き換えず、入力を返すだけにする
 * 2. 状態は読むだけ（`WorldState` を受け取るが変更しない）
 * 3. 判断に時間がかかっても tick の同期を崩さない
 *    （間に合わなければ前回の入力を使い回すなど、この層の内側で吸収する）
 */
export interface InputSource {
  /** どのプレイヤーの入力を返すか。 */
  readonly playerId: PlayerId;

  /**
   * この tick の入力を返す。
   *
   * ⚠️ `world` は読むだけ。ここで書き換えると、入力を返す前に
   * 状態が変わることになり、リプレイと通信対戦の前提が崩れる。
   */
  readonly next: (world: Readonly<WorldState>) => PlayerInput;
}

/**
 * 何も押さない窓口。
 *
 * 接続が切れたプレイヤーや、まだ誰も操作していないプレイヤーを、`undefined` の分岐を
 * 増やさずに扱うために使う。
 */
export class IdleInputSource implements InputSource {
  constructor(readonly playerId: PlayerId) {}

  next(): PlayerInput {
    return IDLE_INPUT;
  }
}

/**
 * 窓口を集めて、1 tick ぶんの入力をまとめて取り出す。
 *
 * プレイヤーごとに窓口が違ってよい。人間1人・CPU3人でも、人間2人・記録の再生2人でも、
 * ゲーム本体から見ると区別がつかない。
 */
export class InputGatherer {
  readonly #sources = new Map<PlayerId, InputSource>();

  add(source: InputSource): this {
    this.#sources.set(source.playerId, source);
    return this;
  }

  /** この tick の入力を、プレイヤーごとに集める。 */
  gather(world: Readonly<WorldState>): ReadonlyMap<PlayerId, PlayerInput> {
    const result = new Map<PlayerId, PlayerInput>();
    // プレイヤー番号の順に集める。窓口を登録した順ではない。登録順に依存すると、
    // 参加の仕方で結果が変わりうる。
    for (const player of world.players) {
      const source = this.#sources.get(player.id);
      result.set(player.id, source === undefined ? IDLE_INPUT : source.next(world));
    }
    return result;
  }
}
