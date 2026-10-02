import type { InputSource } from '../domain/input/InputSource.js';
import {
  IDLE_INPUT,
  MAX_INPUT_BITS,
  packInput,
  unpackInput,
  type PlayerInput,
} from '../domain/input/PlayerInput.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';

/**
 * 記録の文字列で、途中で抜けた人の区画の見出し（区画と見出しは `InputLog.encode` の説明にある）。
 * プレイヤー番号と取り違えないよう、数字にしない。
 */
const DEPARTED = 'departed';

/**
 * いま何番目の tick を進めているかを答えるもの。`GameSession` と `LockstepDriver` がこの形を持つ。
 *
 * ⚠️ 記録と通信の時刻にはこちらを使い、盤面の時刻（`world.now`）は使わない。
 * `world.now` はラウンドごとに 0 へ戻り、決着のあとの待ちの間は止まるので、
 * 同じ値が試合の中で何度も現れる。
 */
export interface MatchClock {
  /** 試合が始まってから進め終えた tick の数。進めている最中は、その tick の番号。 */
  readonly elapsed: number;
}

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
 *
 * ## 時刻は試合通算の tick
 *
 * 記録の時刻は `MatchClock.elapsed`（試合が始まってからの tick）で持つ。
 * 通信対戦で届いた入力の記録（`ConfirmedInputs.log`）も同じ時刻なので、
 * `ReplayInputSource` で流し直せる。CPU の枠は設定から作り直す（`ConfirmedInputs.log` の説明と docs/05）。
 *
 * ## 途中で抜けた人
 *
 * 通信対戦で途中で抜けた人は、その人の入力を記録から最後に使う tick（`departedAfter`）を持つ。
 * 本物の端末（`LockstepDriver`）はその次の tick から CPU に替え、再生の窓口も同じ tick で
 * 代わりの窓口に任せる。これが無いと、記録はその人の最後の入力を返し続けるので、
 * 例外も出ずに別の試合になる。
 *
 * ⚠️ 似た名前が3つある。このクラスの `lastTick` は、記録にある最後の変化の tick。
 * 約束の `peer_left` の `lastTick` は、中継がその人の入力を最後に配った tick。
 * `departedAfter` は、その人の入力を記録から最後に使う tick で、`peer_left` の `lastTick` をそのまま入れる。
 */
export class InputLog {
  /** プレイヤーごとの、変化した時点の一覧。tick の昇順で並ぶ。 */
  readonly #changes = new Map<PlayerId, { tick: number; bits: number }[]>();
  /** 途中で抜けた人と、その人の入力を記録から最後に使う tick。 */
  readonly #departedAfter = new Map<PlayerId, number>();

  /**
   * ある tick の入力を記録する。
   *
   * 直前と同じ値なら何もしない。tick は 0 以上の安全な整数（`Number.MAX_SAFE_INTEGER` 以下で、
   * 隣の整数と区別できる整数）を昇順に渡す。
   *
   * @throws Error tick が 0 以上の安全な整数でないとき（文字列にすると `decode` が読めない形になる）か、
   *   直前と違う値で tick が戻っているとき
   */
  record(atTick: number, playerId: PlayerId, playerInput: PlayerInput): void {
    // 直前と同じ値のときも確かめる。一覧を作るより前に止めないと、空の一覧が残って `encode` が読めない区画を書く。
    if (!Number.isSafeInteger(atTick) || atTick < 0) {
      throw new Error(`記録する tick が 0 以上の安全な整数ではない: ${atTick}`);
    }
    const bits = packInput(playerInput);
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
   * ある tick の入力を取り出す。
   *
   * 記録の無いプレイヤーと、記録が始まる前の tick には何も押していない入力を返す。
   */
  at(atTick: number, playerId: PlayerId): PlayerInput {
    const list = this.#changes.get(playerId);
    if (list === undefined || list.length === 0) return IDLE_INPUT;

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
    if (found < 0) return IDLE_INPUT;
    return unpackInput((list[found] as { tick: number; bits: number }).bits);
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
   * 途中で抜けた人を記録する。その人の入力は `afterTick` まで記録から使い、次の tick からは
   * 代わりの窓口（CPU）に任せる。
   *
   * @param afterTick 中継が知らせた `peer_left` の `lastTick`。入力が1つも配られないうちに抜けた人は -1
   * @throws Error `afterTick` が -1 以上の安全な整数でないとき（文字列にすると `decode` が読めない形になる）か、
   *   同じ人を2度記録しようとしたとき
   */
  depart(afterTick: number, playerId: PlayerId): void {
    if (!Number.isSafeInteger(afterTick) || afterTick < -1) {
      throw new Error(`プレイヤー ${playerId} の departedAfter が -1 以上の安全な整数ではない: ${afterTick}`);
    }
    if (this.#departedAfter.has(playerId)) {
      throw new Error(`プレイヤー ${playerId} が抜けたことを2度記録しようとした`);
    }
    this.#departedAfter.set(playerId, afterTick);
  }

  /** その人の入力を記録から最後に使う tick。途中で抜けていなければ undefined。 */
  departedAfter(playerId: PlayerId): number | undefined {
    return this.#departedAfter.get(playerId);
  }

  /**
   * `atTick` の時点で、その人が代わりの窓口に替わっているか（`departedAfter` の次の tick から）。
   *
   * 本物の端末（`LockstepDriver`）と再生の窓口（`ReplayInputSource`）は、どちらもこの判定で替える。
   */
  replacedAt(atTick: number, playerId: PlayerId): boolean {
    const last = this.#departedAfter.get(playerId);
    return last !== undefined && atTick > last;
  }

  /**
   * 保存できる文字列にする。
   *
   * 形式は `プレイヤー番号:tick,ビット;tick,ビット|プレイヤー番号:...`。`|` で区切った1つを区画、
   * 区画の最初の「:」より前を見出し、`;` で区切った1つを項目と呼ぶ。途中で抜けた人がいれば、
   * 最後に `|departed:プレイヤー番号,tick;...`（tick は `departedAfter`）を足す。抜けた人を変化の一覧と
   * 別に書くのは、入力が1つも配られないうちに抜けた人は変化の一覧に居ないため。
   * 読んで確かめられることを優先し、圧縮はしていない。3分の試合でも数キロバイトに収まる。
   */
  encode(): string {
    const parts: string[] = [];
    // プレイヤー番号の順に並べる。Map の挿入順に依存させない。
    for (const playerId of [...this.#changes.keys()].sort((a, b) => a - b)) {
      const list = this.#changes.get(playerId);
      if (list === undefined) continue;
      const body = list.map((e) => `${e.tick},${e.bits}`).join(';');
      parts.push(`${playerId}:${body}`);
    }
    if (this.#departedAfter.size > 0) {
      const body = [...this.#departedAfter.entries()]
        .sort(([a], [b]) => a - b)
        .map(([playerId, afterTick]) => `${playerId},${afterTick}`)
        .join(';');
      parts.push(`${DEPARTED}:${body}`);
    }
    return parts.join('|');
  }

  /**
   * 保存した文字列から戻す。抜けた人の区画が無ければ、誰も抜けていない記録になる。
   *
   * 数は `encode` が書く形（頭に 0 を付けない10進の整数）で、`record`・`depart` が受け付ける範囲
   * （変化の一覧の tick は 0 以上、抜けた人の区画の tick（`departedAfter`）は -1 以上の安全な整数。
   * ビットは6つのボタンまで）のものだけを読む。
   * 同じ tick の変化が続くのは `record` も書く形（あとの値が勝つ）なので受け付ける。同じビットが続く項目は、
   * `record` は書かないが、入力が変わらず流し直しの答えも変わらないので受け付ける。
   *
   * @throws Error 読めない区画か項目（範囲の外の数を含む）、戻っている tick、同じ人の区画の2度目、
   *   同じ人が抜けたことの2度目があるとき。黙って読み飛ばしたりあとの値で上書きしたりすると、その人の
   *   入力が記録と違うまま（あるいは違う tick で替わって）、例外も出ずに別の試合になる
   */
  static decode(text: string): InputLog {
    const log = new InputLog();
    if (text.length === 0) return log;
    for (const part of text.split('|')) {
      // 見出しと中身は最初の「:」で分ける。中身に「:」が混じっていれば、その項目が読めずに止まる。
      const colon = part.indexOf(':');
      if (colon < 0) throw new Error(`記録の区画に「:」が無い: ${part}`);
      const head = part.slice(0, colon);
      const body = part.slice(colon + 1);
      if (head === DEPARTED) {
        for (const entry of body.split(';')) {
          // プレイヤー番号は 0〜3、tick は -1 以上の安全な整数（`depart` と同じ範囲）。
          const found = /^([0-3]),(-1|0|[1-9]\d*)$/.exec(entry);
          if (found === null || !Number.isSafeInteger(Number(found[2]))) {
            throw new Error(`記録の抜けた人の区画の項目が読めない: ${entry}`);
          }
          log.depart(Number(found[2]), Number(found[1]) as PlayerId);
        }
        continue;
      }
      // `Number` は空の文字列を 0 と読み、前後の空白も読み飛ばすので、形を先に確かめる。
      if (!/^[0-3]$/.test(head)) throw new Error(`記録の区画が読めない: ${part}`);
      const playerId = Number(head) as PlayerId;
      if (log.#changes.has(playerId)) throw new Error(`記録にプレイヤー ${playerId} の区画が2度ある`);
      const list: { tick: number; bits: number }[] = [];
      for (const entry of body.split(';')) {
        // tick は 0 以上の安全な整数（`record` と同じ範囲）。抜けた人の区画と違い、-1 は無い。
        const found = /^(0|[1-9]\d*),(0|[1-9]\d*)$/.exec(entry);
        if (found === null || !Number.isSafeInteger(Number(found[1])) || Number(found[2]) > MAX_INPUT_BITS) {
          throw new Error(`記録のプレイヤー ${playerId} の項目が読めない: ${entry}`);
        }
        const tick = Number(found[1]);
        const last = list[list.length - 1];
        // `at` は tick の昇順に並んでいる前提で探す。同じ tick が続くのは `record` と同じく受け付ける。
        if (last !== undefined && last.tick > tick) {
          throw new Error(`記録のプレイヤー ${playerId} の tick が戻っている: ${last.tick} のあとに ${tick}`);
        }
        list.push({ tick, bits: Number(found[2]) });
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
 *
 * 途中で抜けた人は、`departedAfter` の次の tick から、代わりの窓口（`replacement` で作るもの）に任せる。
 * 本物の端末（`LockstepDriver`）が CPU に繋ぎ替えるのと同じ tick になる。
 */
export class ReplayInputSource implements InputSource {
  readonly #replacement: ((playerId: PlayerId) => InputSource) | undefined;
  #replaced: InputSource | null = null;

  /**
   * @param replacement 抜けた人を受け持つ窓口を作る。本物の端末と同じものを返すこと
   *   （通信対戦なら `lanCpuSource` に同じ設定を渡す）。記録でこの人が途中で抜けているなら必ず渡す
   * @throws Error 記録でこの人が途中で抜けているのに、`replacement` が無いとき
   */
  constructor(
    readonly playerId: PlayerId,
    private readonly log: InputLog,
    private readonly clock: MatchClock,
    replacement?: (playerId: PlayerId) => InputSource,
  ) {
    this.#replacement = replacement;
    // 再生の途中で止まるより、始める前に止まるほうが原因に近い。
    if (log.departedAfter(playerId) !== undefined) this.#requireReplacement();
  }

  next(world: Readonly<WorldState>): PlayerInput {
    const tick = this.clock.elapsed;
    if (!this.log.replacedAt(tick, this.playerId)) return this.log.at(tick, this.playerId);
    // 作るのは初めて任せるとき。本物の端末は `departedAfter` の次の tick を進める直前に作るので、
    // 決着のあとの待ち（操作を集めない）に当たると作る時点がずれるが、CPU は作るときに盤面を
    // 読まないので同じ手を指す。1度作ったら作り直さない（CPU は考えた内容を覚えている）。
    this.#replaced ??= this.#requireReplacement()(this.playerId);
    return this.#replaced.next(world);
  }

  #requireReplacement(): (playerId: PlayerId) => InputSource {
    if (this.#replacement === undefined) {
      throw new Error(`プレイヤー ${this.playerId} は途中で抜けているのに、代わりの窓口の作り方が無い`);
    }
    return this.#replacement;
  }
}

/**
 * 実際に流れた操作を記録しながら、元の窓口へそのまま通す。
 *
 * 試合中はこれで包んでおけば、あとから記録を取り出して再生できる。
 * 包まれている側は、記録されていることを知らない。
 */
export class RecordingInputSource implements InputSource {
  constructor(
    private readonly inner: InputSource,
    private readonly log: InputLog,
    private readonly clock: MatchClock,
  ) {}

  get playerId(): PlayerId {
    return this.inner.playerId;
  }

  next(world: Readonly<WorldState>): PlayerInput {
    const playerInput = this.inner.next(world);
    this.log.record(this.clock.elapsed, this.inner.playerId, playerInput);
    return playerInput;
  }
}
