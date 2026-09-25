import { assertNever, type SimEvent } from '../domain/events/SimEvent.js';

/**
 * 鳴らせる音の名前。
 *
 * ルールの層はこの一覧を知らない。どのイベントにどの音を当てるかは
 * この層の判断で、変えてもゲームの結果は1ミリも変わらない。
 */
export type SoundName =
  | 'place'
  | 'explode'
  | 'breakBlock'
  | 'item'
  | 'burn'
  | 'hurt'
  | 'down'
  | 'effect';

/** 音を鳴らすもの。 */
export interface SoundBank {
  /**
   * @param intensity 大きさの手がかり（連鎖数など）。使うかどうかは実装しだい
   */
  play(name: SoundName, intensity?: number): void;
}

/**
 * 何も鳴らさない実装。
 *
 * 検証のときはこれを差す……という説明をしたくなるが、**実際には
 * それすら要らない**。`Presenter` を作らなければ音は鳴らない。
 * このクラスは「画面は出すが音は消したい」場合のためにある。
 */
export class NullSoundBank implements SoundBank {
  play(): void {
    // 何もしない。
  }
}

/** 画面に短く出す通知。 */
export interface NoticeSink {
  show(message: string): void;
}

/** どこにも出さない通知。 */
export class NullNoticeSink implements NoticeSink {
  show(): void {
    // 何もしない。
  }
}

/**
 * ルールの層が返したイベントを、音と通知に変える。
 *
 * ## ここが受け取らなければ、何も起きない
 *
 * 原型では `update()` の中から音と画面を直接呼んでいたため、
 * 「ルールだけを動かす」ができなかった。この版ではイベントが
 * 戻り値で返るので、受け取らないという選択ができる。
 *
 * ```
 * const events = simulation.step(world, intents);
 * // 遊ぶとき
 * presenter.consume(events);
 * // 1万試合を測るとき（何も書かない）
 * ```
 *
 * 音を消すフラグもテスト用のモードも要らない。
 *
 * ## 扱い漏れが型検査で落ちる
 *
 * `switch` のすべての分岐を通ったあとに `assertNever` を置いてある。
 * イベントを1種類足すと、そこへ到達しうるようになり
 * 「`never` に代入できない」というコンパイルエラーになる。
 * 足した本人が、音を当てるかどうかを必ず1度は考えることになる。
 */
export class Presenter {
  constructor(
    private readonly sounds: SoundBank = new NullSoundBank(),
    private readonly notices: NoticeSink = new NullNoticeSink(),
  ) {}

  consume(events: readonly SimEvent[]): void {
    for (const event of events) this.#handle(event);
  }

  #handle(event: SimEvent): void {
    switch (event.type) {
      case 'bombPlaced':
        this.sounds.play('place');
        return;
      case 'exploded':
        // 連鎖数を渡す。まとめて爆発したときに大きな音になる。
        this.sounds.play('explode', event.chained);
        return;
      case 'blockDestroyed':
        this.sounds.play('breakBlock');
        return;
      case 'itemDropped':
        // 落ちた瞬間は鳴らさない。壊した音と重なってうるさくなる。
        return;
      case 'itemTaken':
        this.sounds.play('item');
        return;
      case 'itemBurned':
        this.sounds.play('burn');
        return;
      case 'effectApplied':
        this.sounds.play('effect');
        this.notices.show(`${event.effect} がかかった`);
        return;
      case 'playerHurt':
        this.sounds.play('hurt');
        return;
      case 'playerDown':
        this.sounds.play('down');
        return;
      default:
        // ここに到達する型が残っていれば、コンパイルが通らない。
        assertNever(event);
    }
  }
}
