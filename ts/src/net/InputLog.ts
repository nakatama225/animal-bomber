import type { IntentSource } from '../domain/intent/IntentSource.js';
import {
  IDLE_INTENT,
  packIntent,
  unpackIntent,
  type PlayerIntent,
} from '../domain/intent/PlayerIntent.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';

/**
 * 操作の記録。
 *
 * 試合を再現するのに必要なのは「種」と「誰がいつ何をしたか」だけで、
 * 盤面もプレイヤーの座標も保存しない。同じ入力からは必ず同じ結果に
 * なるため、記録から状態を作り直せる。
 *
 * この仕組みを段階1で作るのには理由がある。あとで通信対戦を作るとき、
 * 送るべきものがちょうどこの記録と同じ形になる。記録を再生する窓口を
 * 通信から受け取る窓口に差し替えるだけで済む。
 *
 * ## 変化した時点だけを持つ
 *
 * 押しっぱなしの間は同じ値が続くので、値が変わった tick だけを記録する。
 * 3分の試合を 60Hz で全部持つと 1 万件を超えるが、実際に変化するのは
 * その数十分の1しかない。
 */
export class InputLog {
  /** 席ごとの、変化した時点の一覧。tick の昇順で並ぶ。 */
  readonly #changes = new Map<PlayerId, { tick: number; bits: number }[]>();

  /**
   * ある tick の意思を記録する。
   *
   * 直前と同じ値なら何もしない。tick は昇順に渡す。
   */
  record(atTick: number, playerId: PlayerId, intent: PlayerIntent): void {
    const bits = packIntent(intent);
    let list = this.#changes.get(playerId);
    if (list === undefined) {
      list = [];
      this.#changes.set(playerId, list);
    }
    const last = list[list.length - 1];
    if (last !== undefined && last.bits === bits) return;
    if (last !== undefined && last.tick > atTick) {
      throw new Error(`tick が戻っている: ${last.tick} のあとに ${atTick}`);
    }
    list.push({ tick: atTick, bits });
  }

  /**
   * ある tick の意思を取り出す。
   *
   * 記録の無い席と、記録が始まる前の tick には何もしない意思を返す。
   */
  at(atTick: number, playerId: PlayerId): PlayerIntent {
    const list = this.#changes.get(playerId);
    if (list === undefined || list.length === 0) return IDLE_INTENT;

    // 記録は昇順なので、二分探索で「atTick 以下の最後の変化」を探す。
    let low = 0;
    let high = list.length - 1;
    let found = -1;
    while (low <= high) {
      const mid = (low + high) >> 1;
      const entry = list[mid];
      if (entry === undefined) break;
      if (entry.tick <= atTick) {
        found = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
    if (found < 0) return IDLE_INTENT;
    return unpackIntent((list[found] as { tick: number; bits: number }).bits);
  }

  /** 記録されている最後の tick。何も無ければ -1。 */
  get lastTick(): number {
    let last = -1;
    for (const list of this.#changes.values()) {
      const entry = list[list.length - 1];
      if (entry !== undefined && entry.tick > last) last = entry.tick;
    }
    return last;
  }

  /**
   * 保存できる文字列にする。
   *
   * 形式は `席:tick,ビット;tick,ビット|席:...`。読んで確かめられることを
   * 優先し、圧縮はしていない。3分の試合でも数キロバイトに収まる。
   */
  encode(): string {
    const parts: string[] = [];
    // 席の順に並べる。Map の挿入順に依存させない。
    for (const playerId of [...this.#changes.keys()].sort((a, b) => a - b)) {
      const list = this.#changes.get(playerId);
      if (list === undefined) continue;
      const body = list.map((e) => `${e.tick},${e.bits}`).join(';');
      parts.push(`${playerId}:${body}`);
    }
    return parts.join('|');
  }

  /** 保存した文字列から戻す。 */
  static decode(text: string): InputLog {
    const log = new InputLog();
    if (text.length === 0) return log;
    for (const part of text.split('|')) {
      const [head, body] = part.split(':');
      if (head === undefined || body === undefined) continue;
      const playerId = Number(head) as PlayerId;
      const list: { tick: number; bits: number }[] = [];
      for (const entry of body.split(';')) {
        const [rawTick, rawBits] = entry.split(',');
        if (rawTick === undefined || rawBits === undefined) continue;
        list.push({ tick: Number(rawTick), bits: Number(rawBits) });
      }
      log.#changes.set(playerId, list);
    }
    return log;
  }
}

/**
 * 記録した操作を流す窓口。
 *
 * 人間のキーボードや CPU と同じ資格で `Simulation` に繋がる。
 * 繋ぎ替えるのはここ1点だけで、ゲーム本体は変わらない。
 */
export class ReplayIntentSource implements IntentSource {
  constructor(
    readonly playerId: PlayerId,
    private readonly log: InputLog,
  ) {}

  next(world: Readonly<WorldState>): PlayerIntent {
    return this.log.at(world.now, this.playerId);
  }
}

/**
 * 実際に流れた操作を記録しながら、元の窓口へそのまま通す。
 *
 * 試合中はこれで包んでおけば、あとから記録を取り出して再生できる。
 * 包まれている側は、記録されていることを知らない。
 */
export class RecordingIntentSource implements IntentSource {
  constructor(
    private readonly inner: IntentSource,
    private readonly log: InputLog,
  ) {}

  get playerId(): PlayerId {
    return this.inner.playerId;
  }

  next(world: Readonly<WorldState>): PlayerIntent {
    const intent = this.inner.next(world);
    this.log.record(world.now, this.inner.playerId, intent);
    return intent;
  }
}
