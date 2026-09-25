import type { SimEvent } from '../domain/events/SimEvent.js';
import { assertNever } from '../domain/events/SimEvent.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { NullSoundBank, type SoundBank, type SoundName } from './audio/SoundBank.js';
import { techniqueSound } from './audio/techniqueSounds.js';

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

  /**
   * @param world イベントが起きた盤面。誰の技かから動物を引くのに使う
   */
  consume(events: readonly SimEvent[], world: Readonly<WorldState>): void {
    // 優勝が決まった tick には、ラウンドの終わりと試合の終わりが一緒に来る。
    // 2つの曲を重ねると聞き取れないので、優勝のファンファーレだけを鳴らす。
    const matchOver = events.some((event) => event.type === 'matchEnded');
    for (const event of events) {
      if (matchOver && event.type === 'roundEnded') {
        this.#announceRound(event.round, event.winner);
        continue;
      }
      this.#handle(event, world);
    }
  }

  #announceRound(round: number, winner: number | null): void {
    this.notices.show(
      winner === null ? `ラウンド ${round} は引き分け` : `ラウンド ${round} は ${winner + 1}P の勝ち`,
    );
  }

  #handle(event: SimEvent, world: Readonly<WorldState>): void {
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
        // とくぎが増えるアイテムだけは別の音にする。拾った瞬間に分かるように。
        this.sounds.play(event.kind === 'chicken' ? 'chicken' : 'item');
        return;
      case 'itemBurned':
        this.sounds.play('burn');
        return;
      case 'effectApplied':
        this.sounds.play(effectSound(event.effect));
        this.notices.show(`${event.effect} がかかった`);
        return;
      case 'playerHurt':
        this.sounds.play('hurt');
        return;
      case 'playerDown':
        this.sounds.play('down');
        return;
      case 'techniqueUsed': {
        const animal = world.players[event.player]?.animal;
        const sound = animal === undefined ? null : techniqueSound(animal, event.special);
        if (sound !== null) this.sounds.play(sound);
        return;
      }
      case 'roundEnded':
        this.sounds.play(event.winner === null ? 'draw' : 'roundEnd');
        this.#announceRound(event.round, event.winner);
        return;
      case 'matchEnded':
        this.sounds.play('fanfare');
        this.notices.show(
          event.champion === null ? '引き分け' : `${event.champion + 1}P の優勝`,
        );
        return;
      default:
        // ここに到達する型が残っていれば、コンパイルが通らない。
        assertNever(event);
    }
  }
}

/** 悪い状態にかかったときの音。滑る・泣くは専用の音、うんこの効果はまとめて1つ。 */
function effectSound(effect: string): SoundName {
  if (effect === 'slide') return 'slip';
  if (effect === 'stun') return 'cry';
  return 'poop';
}
