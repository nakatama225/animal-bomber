import type { SimEvent } from '../domain/events/SimEvent.js';
import { assertNever } from '../domain/events/SimEvent.js';
import { SUDDEN_DEATH_SECONDS } from '../domain/rules/suddenDeath.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { NullSoundBank, type SoundBank, type SoundName } from './audio/SoundBank.js';
import { techniqueSound } from './audio/techniqueSounds.js';
import { effectText } from './hud/effectLabels.js';

/** 画面に短く出す通知。 */
export interface NoticeSink {
  readonly show: (message: string) => void;
}

/**
 * 通知に出すプレイヤーの呼び方。
 *
 * 誰が人間で誰が CPU かはルールの層に無いので、呼び出し側から受け取る。
 */
export type PlayerNamer = (id: PlayerId, world: Readonly<WorldState>) => string;

/** 番号だけの呼び方（「1P」）。 */
export const numberedName: PlayerNamer = (id) => `${id + 1}P`;

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
 * const events = simulation.step(world, playerInputs);
 * // 遊ぶとき
 * presenter.consume(events);
 * // 1万試合を測るとき（何も書かない）
 * ```
 *
 * 音を消すフラグもテスト用のモードも要らない。
 *
 * ## 扱い漏れで型検査が失敗する
 *
 * `switch` のすべての分岐を通ったあとに `assertNever` を置いてある。
 * イベントを1種類足すと、そこへ到達しうるようになり
 * 「`never` に代入できない」というコンパイルエラーになる。
 * 足した側が、音を当てるかどうかを必ず1度は考えることになる。
 *
 * ## ラウンドと試合の決着は通知に出さない
 *
 * 盤面に重ねる幕（`hud/RoundBanner.ts`）が出す。両方に出すと、同じ文が2か所に並ぶ。
 */
export class Presenter {
  constructor(
    private readonly sounds: SoundBank = new NullSoundBank(),
    private readonly notices: NoticeSink = new NullNoticeSink(),
    private readonly nameOf: PlayerNamer = numberedName,
  ) {}

  /**
   * @param world イベントが起きた盤面。誰の技かから動物を引くのに使う
   */
  consume(events: readonly SimEvent[], world: Readonly<WorldState>): void {
    // 優勝が決まった tick には、ラウンドの終わりと試合の終わりが一緒に来る。
    // 2つの曲を重ねると聞き取れないので、優勝のファンファーレだけを鳴らす。
    const matchOver = events.some((event) => event.type === 'matchEnded');
    for (const event of events) {
      if (matchOver && event.type === 'roundEnded') continue;
      this.#handle(event, world);
    }
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
      case 'itemExpired':
      case 'itemWashed':
      case 'bombDoused':
        // 原型も、これらには音を鳴らさない（煙だけ）。鼻水の音は技を使ったとき（techniqueUsed）に鳴らす。
        return;
      case 'effectApplied':
        this.sounds.play(effectSound(event.effect));
        this.notices.show(`${this.nameOf(event.target, world)}：${effectText(event.effect)}`);
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
      case 'leekThrown':
        this.sounds.play('leek');
        return;
      case 'leekStopped':
        // 音を鳴らすのは爆弾に弾かれたときだけ。盾にして防いだことが分かるように。
        if (event.by === 'bomb') this.sounds.play('leekBlock');
        return;
      case 'revived':
        this.sounds.play('leekHit');
        this.notices.show(
          `${this.nameOf(event.player, world)} が復活！ ${this.nameOf(event.replaced, world)} が葱ボンへ`,
        );
        return;
      case 'lanesClosed':
        this.sounds.play('lanesClosed');
        this.notices.show('葱ボンは退場！ もう復活できない');
        return;
      case 'suddenDeath':
        this.sounds.play('sudden');
        this.notices.show(
          `サドンデス！（${event.reason === 'allDown' ? '同時に倒れた' : '時間切れ'}）` +
            `体力1つ・爆弾と火力と靴は最大・${SUDDEN_DEATH_SECONDS}秒`,
        );
        return;
      case 'roundEnded':
        this.sounds.play(event.winner === null ? 'draw' : 'roundEnd');
        return;
      case 'matchEnded':
        this.sounds.play('fanfare');
        return;
      default:
        // ここに到達する型が残っていれば、コンパイルが通らない。
        assertNever(event);
    }
  }
}

/**
 * 悪い状態にかかったときの音。滑る・泣くは専用の音、うんこの効果はまとめて1つ。
 *
 * ⚠️ 落とし穴は泣くのと同じ音にしている。原型は専用の音（SE.pitFall）を鳴らすが、この版の
 * 音の表にはまだ無い。
 */
function effectSound(effect: string): SoundName {
  if (effect === 'slide') return 'slip';
  if (effect === 'stun' || effect === 'pitfall') return 'cry';
  return 'poop';
}
