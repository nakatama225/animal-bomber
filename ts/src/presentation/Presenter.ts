import { lookOf } from '../content/animals.js';
import { tongueReachOf } from '../domain/abilities/frog/TongueAction.js';
import { HOLD_TIME } from '../domain/abilities/mole/PitAction.js';
import { abilityOf } from '../domain/abilities/registry.js';
import type { SimEvent } from '../domain/events/SimEvent.js';
import { assertNever } from '../domain/events/SimEvent.js';
import { itemDefinition, POOP_EFFECTS, POWER_UP_KINDS, type ItemKind } from '../domain/rules/items.js';
import type { EffectKind } from '../domain/state/EffectBag.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { NullSoundBank, type SoundBank, type SoundName } from './audio/SoundBank.js';
import { MOMENT_SOUNDS, techniqueSounds } from './audio/techniqueSounds.js';
import { isCpu, labelOf, numberedName, type Roster } from './hud/roster.js';
import * as notices from './notices.js';

/** 画面に短く出す通知。 */
export interface NoticeSink {
  readonly show: (message: string) => void;
}

/**
 * いまの名札の一覧（誰が操作しているか）を返す関数。
 *
 * どのプレイヤーを CPU が動かしているかはルールの層に無いので、外から渡す。通信対戦では抜けたプレイヤーが
 * CPU に替わるので、値ではなく関数で受け取り、通知を出すたびに尋ねる。
 */
export type RosterOf = () => Roster;

/** どこにも出さない通知。 */
export class NullNoticeSink implements NoticeSink {
  show(): void {
    // 何もしない。
  }
}

/** 名札の一覧が無い（全員を人間として、番号で呼ぶ）。 */
const NO_ROSTER: RosterOf = () => [];

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
 * presenter.consume(events, world);
 * // 1万試合を測るとき（何も書かない）
 * ```
 *
 * 音を消すフラグもテスト用のモードも要らない。
 *
 * ## 鳴らす場面は原型に合わせる
 *
 * 原型の効果音の呼び出し（`SE.xxx()`）1つずつについて、同じ場面で同じ回数だけ鳴らす。
 * イベント1つでは場面が決まらない所が4つあり、1 tick ぶんのイベントをまとめて見て決める（`TickEvents`）。
 *
 * - 倒れる被弾は、倒れる音だけ（原型の `hurt` は、体力が尽きれば `kill` の音だけを鳴らす）
 * - 被弾して吐き出したアイテムには吐き出す音（原型の `spitPowerup`）。吐き出したことを知らせるイベントは
 *   無く、被弾のすぐあとに落ちた強くなる系のアイテム（`itemDropped`）で見分ける
 * - 技が一列に並べた爆弾は、何本でも置く音1回（原型の `placeLineBombs`）
 * - 優勝が決まったラウンドは、優勝の音だけ（原型の `endGame`）
 *
 * 同じ音を一定時間まとめて1回にする仕組みは持たない（原型もまとめない）。原型が1回しか鳴らさない所は、
 * 上のように場面を見分けて1回にする。同じ tick に別々の連鎖が2つ爆発すれば爆発の音を2回、2体が同じ
 * tick に葱を撃てば葱の音を2回鳴らす（原型と同じ）。
 *
 * ## 通知は原型の文と場面に合わせる
 *
 * 文は `notices.ts`（原型の `toast` の 22 種）。出す場面と順も原型に合わせ、原型が通知を出さない場面
 * （ラウンドと試合の決着。幕が出す）には出さない。原型の通知は1枚だけで、新しいものが前のものを置き換えるので、
 * 同じ tick に2つ出せば、あとのものが見える。出す順を原型と同じにしておくのはこのため（通知の状態の
 * `hud/toast.ts` も1枚で置き換える）。
 *
 * プレイヤーの呼び方は動物の名前（原型の `p.animal.name`）。葱が当たって入れ替わった通知だけが原型の
 * `label`（`hud/roster.ts` の `labelOf`）で呼ぶ。盤面で倒れて外周へ回った通知は、人間のプレイヤーに
 * だけ出す（原型 L2269）。
 *
 * イベントだけでは決まらない通知は、tick を進めたあとの盤面（`consume` の `world`）から決める。
 *
 * - 盤面で倒れて外周へ回ったか：進めたあとのプレイヤーが外周にいるか。⚠️ 全員が同じ tick に倒れて
 *   延長戦に入った tick は、倒れたプレイヤーが盤面へ戻っているので出さない。原型はこのとき葱ボンへの
 *   通知を出してから延長戦の通知を出すので、見える通知は同じ
 * - 舌が焼き切れたあとに伸ばせる長さ：進めたあとの焼けた舌（`BurntTongueActor`）
 *
 * 体当たりで進む間に吸い込んだアイテム（原型 L2818 の通知）は、拾った知らせの項目（`itemTaken.swept`）で
 * 見分ける。前の tick に体当たりしていたかでは見分けない（体当たりが終わった tick に、ふつうに歩いて
 * 拾ったものまで吸い込んだと数えてしまう）。
 *
 * ## 扱い漏れで型検査が失敗する
 *
 * `switch` のすべての分岐を通ったあとに `assertNever` を置いてある。
 * イベントを1種類足すと、そこへ到達しうるようになり
 * 「`never` に代入できない」というコンパイルエラーになる。
 * 足した側は、音を当てるか・何と出すかを必ず1度は考える。
 */
export class Presenter {
  constructor(
    private readonly sounds: SoundBank = new NullSoundBank(),
    private readonly notices: NoticeSink = new NullNoticeSink(),
    private readonly rosterOf: RosterOf = NO_ROSTER,
  ) {}

  /**
   * 1 tick ぶんのイベントを、起きた順に扱う。
   *
   * ⚠️ 1 tick ぶんをまとめて渡す（説明の4つの場面を見分けるため）。1つずつ渡すと、倒れる被弾で
   * 被弾の音も鳴り、優勝の tick に勝ちの音も鳴る。
   *
   * @param world その tick を進めたあとの盤面。誰の技かから動物を取得するのと、盤面を読んで決める通知に使う
   */
  consume(events: readonly SimEvent[], world: Readonly<WorldState>): void {
    const batch = new TickEvents(events);
    for (let index = 0; index < events.length; index += 1) {
      this.#sound(batch, index, world);
      this.#notify(batch, index, world);
    }
  }

  #sound(batch: TickEvents, index: number, world: Readonly<WorldState>): void {
    const play = (name: SoundName, intensity?: number): void => this.sounds.play(name, intensity);
    const event = batch.at(index);
    switch (event.type) {
      case 'bombPlaced':
        // 技が並べた爆弾は、技の側で1回だけ鳴らす（下の 'techniqueUsed'）。
        if (!batch.placedByTechnique(index, event.owner)) play('place');
        return;
      case 'exploded':
        // 連鎖数を渡す。まとめて爆発したときに大きな音になる。
        play('explode', event.chained);
        // ブロックの壊れる音は、1つでも壊した連鎖に1回だけ（原型の explodeChain）。
        if (event.blocks > 0) play('breakBlock');
        return;
      case 'blockDestroyed':
        // ここでは鳴らさない。爆発で壊したぶんは上の 'exploded' でまとめて鳴らす。体当たりで
        // 壊したブロックには、原型も音を鳴らさない。
        return;
      case 'itemDropped':
        // 落ちた瞬間は鳴らさない（壊れたブロックから出たもの・撒いたもの）。被弾して吐き出したものは
        // 'playerHurt' で鳴らす。
        return;
      case 'itemTaken': {
        const sound = takenSound(event.kind);
        if (sound !== null) play(sound);
        return;
      }
      case 'itemBurned':
        // 原型も、焼けたアイテムには音を鳴らさない（煙だけ）。
        return;
      case 'itemBlown':
        play('blowPoop');
        return;
      case 'itemExpired':
      case 'itemWashed':
      case 'bombDoused':
      case 'sprayed':
        // 原型も、これらには音を鳴らさない（煙・しぶきだけ）。鼻水の音は技を使ったとき（techniqueUsed）に鳴らす。
        return;
      case 'effectApplied':
        play(effectSound(event.effect));
        return;
      case 'playerHurt':
        // 原型の hurt：吐き出せたら吐き出す音、そのあと体力が残れば被弾の音。尽きれば倒れる音だけ
        // （'playerDown' で鳴らす）。
        if (batch.spatAfter(index)) play('spit');
        if (!batch.downed.has(event.target)) play('hurt');
        return;
      case 'playerDown':
        play('down');
        return;
      case 'techniqueUsed': {
        const animal = world.players[event.player]?.animal;
        if (animal !== undefined) for (const sound of techniqueSounds(animal, event.special)) play(sound);
        // 技が並べた爆弾は、何本でも置く音1回（原型の placeLineBombs）。
        if (batch.placesAfter(index, event.player)) play('place');
        return;
      }
      case 'techniqueMoment':
        play(MOMENT_SOUNDS[event.moment]);
        return;
      case 'burntOff':
        // 音は泣く状態（'effectApplied'）で鳴らす。ここは煙を出すためのもので、絵の側が扱う。
        return;
      case 'techniqueRefused':
        // 根元まで焼けた舌を出そうとした。原型は画面の操作の音（L2498）。
        play('ui');
        return;
      case 'reachRestored':
        // 原型も、焼けた舌が戻ったときは音を鳴らさない（通知だけ。L4307）。
        return;
      case 'leekThrown':
        // 同じ tick に2体が撃てば2回鳴らす（まとめない。クラスの説明）。
        play('leek');
        return;
      case 'leekStopped':
        // 音を鳴らすのは爆弾に弾かれたときだけ。盾にして防いだことが分かるように。
        if (event.by === 'bomb') play('leekBlock');
        return;
      case 'revived':
        play('leekHit');
        return;
      case 'lanesClosed':
        play('lanesClosed');
        return;
      case 'suddenDeath':
        play('sudden');
        return;
      case 'roundEnded':
        // 優勝が決まった tick には、ラウンドの終わりと試合の終わりが一緒に来る。2つの曲を重ねると
        // 聞き取れないので、優勝のファンファーレだけを鳴らす（原型の endGame）。
        if (!batch.matchEnded) play(event.winner === null ? 'draw' : 'roundEnd');
        return;
      case 'matchEnded':
        play('fanfare');
        return;
      default:
        // ここに到達する型が残っていれば、コンパイルが通らない。
        assertNever(event);
    }
  }

  /** 通知を出す（原型の `toast`・`flash` を呼ぶ場面。文は `notices.ts`）。 */
  #notify(batch: TickEvents, index: number, world: Readonly<WorldState>): void {
    const show = (message: string): void => this.notices.show(message);
    const event = batch.at(index);
    switch (event.type) {
      case 'effectApplied': {
        const text = this.#effectNotice(batch, index, event.target, event.effect, world);
        if (text !== null) show(text);
        const count = batch.pushedCount(index);
        if (count !== null && event.pushedBy !== null) {
          show(notices.pushed(this.#name(event.pushedBy, world), this.#name(event.target, world), count));
        }
        return;
      }
      case 'itemTaken': {
        const name = this.#name(event.taker, world);
        const animal = world.players[event.taker]?.animal;
        if (event.kind === 'chicken' && animal !== undefined) {
          show(notices.chickenTaken(name, lookOf(animal).special.name, abilityOf(animal).itemMultiplier));
        }
        // 体当たりで進む間に吸い込んだもの。原型は、チキンの通知のあとに出す（L2818）。
        if (event.swept) {
          const definition = itemDefinition(event.kind);
          show(notices.swept(definition.emoji, name, definition.label));
        }
        return;
      }
      case 'playerDown':
        // 盤面で倒れて外周へ回った（人間だけ。原型 L2269）。
        if (this.#human(event.target) && world.players[event.target]?.life.kind === 'negibon') {
          show(notices.toLane(this.#name(event.target, world)));
        }
        return;
      case 'revived':
        // 原型の negiHit は、当たった側を外周へ送る処理（toNegibon）の通知を先に出し、そのあと
        // 入れ替わりの通知で置き換える（L2340・L2354）。
        if (this.#human(event.replaced)) show(notices.toLane(this.#name(event.replaced, world)));
        show(notices.revived(this.#label(event.player, world), this.#label(event.replaced, world)));
        return;
      case 'lanesClosed':
        show(notices.LANES_CLOSED);
        return;
      case 'burntOff': {
        const player = world.players[event.player];
        if (player !== undefined) show(notices.tongueBurnt(this.#name(event.player, world), tongueReachOf(world, player)));
        return;
      }
      case 'techniqueRefused':
        show(notices.tongueGone(this.#name(event.player, world), event.wait));
        return;
      case 'reachRestored':
        show(notices.tongueRegrown(this.#name(event.player, world), event.reach));
        return;
      case 'techniqueMoment':
        if (event.moment === 'pitDug') show(notices.pitDug(this.#name(event.player, world)));
        return;
      case 'techniqueUsed': {
        const animal = world.players[event.player]?.animal;
        if (!event.special || animal === undefined) return;
        const special = lookOf(animal).special;
        show(notices.specialUsed(special.emoji, this.#name(event.player, world), special.name));
        return;
      }
      case 'sprayed': {
        const text = notices.sprayed(this.#name(event.player, world), batch.dousedBefore(index), event.washed);
        if (text !== null) show(text);
        return;
      }
      case 'suddenDeath':
        show(notices.suddenDeath(event.reason));
        return;
      case 'bombPlaced':
      case 'exploded':
      case 'blockDestroyed':
      case 'itemDropped':
      case 'itemBurned':
      case 'itemBlown':
      case 'itemExpired':
      case 'itemWashed':
      case 'bombDoused':
      case 'playerHurt':
      case 'leekThrown':
      case 'leekStopped':
      case 'roundEnded':
      case 'matchEnded':
        // 原型も通知を出さない。ラウンドと試合の決着は幕が出す（`hud/RoundBanner.ts`）。両方に出すと、
        // 同じ文が2か所に並ぶ。
        return;
      default:
        assertNever(event);
    }
  }

  /** 状態がかかったときの通知（原型の applyItem など）。無ければ null。 */
  #effectNotice(
    batch: TickEvents,
    index: number,
    target: PlayerId,
    effect: EffectKind,
    world: Readonly<WorldState>,
  ): string | null {
    const name = this.#name(target, world);
    const animal = world.players[target]?.animal;
    const times = animal === undefined ? 1 : abilityOf(animal).itemMultiplier;
    switch (effect) {
      case 'slide':
        return notices.slipped(name, times);
      case 'stun':
        // 舌が焼き切れて泣くときは、たまねぎの通知を出さない（原型の tongueBurnCheck は applyItem を通らない）。
        return batch.burntBefore(index, target) ? null : notices.cried(name, times);
      case 'pitfall':
        return notices.pitFallen(name, HOLD_TIME);
      case 'reverse':
      case 'nobomb':
      case 'runaway':
      case 'weak':
      case 'autobomb':
      case 'slow':
        return notices.pooped(name, poopLabel(effect), times);
      case 'leap':
      case 'scattering':
        // ルールの層は、跳び上がる・撒く身ぶりがかかったことを知らせない。原型も通知を出さない
        // （とくぎの通知は 'techniqueUsed' で出す）。
        return null;
      default:
        return assertNever(effect);
    }
  }

  /** そのプレイヤーを人間が操作しているか。名札の一覧にいなければ人間として扱う。 */
  #human(id: PlayerId): boolean {
    const roster = this.rosterOf();
    return id >= roster.length || !isCpu(roster, id);
  }

  /** 通知での呼び方（動物の名前）。盤面にいない番号なら番号（「1P」）。 */
  #name(id: PlayerId, world: Readonly<WorldState>): string {
    const animal = world.players[id]?.animal;
    return animal === undefined ? numberedName(id) : lookOf(animal).name;
  }

  /**
   * 原型の `label` の呼び方（`hud/roster.ts` の `labelOf` を呼ぶ）。
   *
   * 人間は「1P」、CPU は動物の名前。通信対戦で抜けて CPU に替わったプレイヤーは、人間だったときの
   * 「2P」のまま。名札の一覧にいないプレイヤーは、`#human` と同じく人間として番号で呼ぶ。
   */
  #label(id: PlayerId, world: Readonly<WorldState>): string {
    const roster = this.rosterOf();
    if (id >= roster.length) return numberedName(id);
    return labelOf(roster, id, this.#name(id, world));
  }
}

/**
 * 1 tick ぶんのイベントと、まとめて見ておく事柄（Python 版の `presenter.py` の `_Tick` と同じ見分け方）。
 *
 * ⚠️ どれも、ルールの層がイベントを並べる順に頼っている。並びを変えると、音や通知が原型とずれる
 * （`tests/presentation/presenter.test.ts` の、試合を進めて確認するテストが失敗する）。
 */
class TickEvents {
  /** この tick に倒れたプレイヤー。 */
  readonly downed: ReadonlySet<PlayerId>;
  /** この tick に試合が決まったか。 */
  readonly matchEnded: boolean;

  constructor(private readonly events: readonly SimEvent[]) {
    this.downed = new Set(events.flatMap((event) => (event.type === 'playerDown' ? [event.target] : [])));
    this.matchEnded = events.some((event) => event.type === 'matchEnded');
  }

  at(index: number): SimEvent {
    const event = this.events[index];
    if (event === undefined) throw new Error(`イベント ${index} が無い`);
    return event;
  }

  /**
   * `index` の被弾のすぐあとに、吐き出したアイテムが落ちたか。
   *
   * 吐き出すのは強くなる系のアイテムだけ（`POWER_UP_KINDS`）なので、種類も見る。吐き出す場所が無かった
   * 被弾のすぐあとに、同じ tick に撒く本体が撒いたうんこが続くことがある（原型は、吐き出せなければ吐き出す
   * 音を鳴らさない）。⚠️ 被弾の処理（`domain/mutations/damage.ts` の `hurt`）が、被弾・吐き出したアイテム・
   * 倒れた、の順にイベントを並べることに頼っている。
   */
  spatAfter(index: number): boolean {
    const next = this.events[index + 1];
    return next?.type === 'itemDropped' && POWER_UP_KINDS.includes(next.kind);
  }

  /** `index` の技のすぐあとに、そのプレイヤーの爆弾が置かれたか。 */
  placesAfter(index: number, player: PlayerId): boolean {
    const next = this.events[index + 1];
    return next?.type === 'bombPlaced' && next.owner === player;
  }

  /**
   * `index` の爆弾が、技が並べたものか。
   *
   * 技を出したイベントのすぐあとに続く、同じプレイヤーの爆弾の並びの中にあれば、技が並べたもの。ボタンや
   * 「勝手に設置」で置いた爆弾は、1 tick の処理の順で技より前に来る（`domain/systems/Simulation.ts`）ので、
   * この並びに入らない。⚠️ 技を出す処理（`domain/systems/ActionSystem.ts` の `#tap`）が、技を出したイベントを
   * 技が起こしたイベントの前に置くことに頼っている。
   */
  placedByTechnique(index: number, owner: PlayerId): boolean {
    let before = index - 1;
    for (;;) {
      const event = this.events[before];
      if (event === undefined) return false;
      if (event.type === 'bombPlaced' && event.owner === owner) {
        before -= 1;
        continue;
      }
      return event.type === 'techniqueUsed' && event.player === owner;
    }
  }

  /**
   * `index` の状態のすぐ前に、そのプレイヤーの舌が焼き切れたか。
   *
   * ⚠️ 舌が焼き切れる処理（`TongueAction` の `#burn`）が、焼き切れた・泣く状態、の順にイベントを並べることに
   * 頼っている。
   */
  burntBefore(index: number, player: PlayerId): boolean {
    const before = this.events[index - 1];
    return before?.type === 'burntOff' && before.player === player;
  }

  /**
   * `index` の鼻水のすぐ前に続く、火を消した爆弾の数。
   *
   * ⚠️ 鼻水の処理が、消した爆弾を並べてから水しぶき（'sprayed'）を足すことに頼っている。
   */
  dousedBefore(index: number): number {
    let count = 0;
    while (this.events[index - 1 - count]?.type === 'bombDoused') count += 1;
    return count;
  }

  /**
   * `index` が押しつけた状態の並びの最後なら、並びの長さ。そうでなければ null。
   *
   * 体当たりで抱えていた悪いアイテムは、相手に1つずつ効果をかける（'effectApplied' が押しつけたプレイヤー
   * 付きで続く）。原型はそれぞれのアイテムの通知のあとに「n個 ぶつけた！」を出すので、並びの最後で数える。
   */
  pushedCount(index: number): number | null {
    const event = this.at(index);
    if (event.type !== 'effectApplied' || event.pushedBy === null) return null;
    if (samePush(this.events[index + 1], event)) return null;
    let count = 1;
    while (samePush(this.events[index - count], event)) count += 1;
    return count;
  }
}

/** `other` が、`event` と同じプレイヤーから同じ相手へ押しつけた状態か。 */
function samePush(
  other: SimEvent | undefined,
  event: Extract<SimEvent, { type: 'effectApplied' }>,
): boolean {
  return other?.type === 'effectApplied' && other.pushedBy === event.pushedBy && other.target === event.target;
}

/**
 * アイテムの効果が出たときの音。悪いアイテムは鳴らさない（null）。
 *
 * 原型の `applyItem` は、爆弾・火・靴で `item`、チキンで `chicken` を鳴らし、バナナ・たまねぎ・うんこは、
 * かかった状態の音（`slip`・`cry`・`poop`）だけを鳴らす。この版では状態の音は 'effectApplied' で鳴るので、
 * ここで鳴らすと二重になる。
 */
function takenSound(kind: ItemKind): SoundName | null {
  switch (kind) {
    case 'bomb':
    case 'fire':
    case 'shoe':
      return 'item';
    case 'chicken':
      return 'chicken';
    case 'banana':
    case 'onion':
    case 'poop':
      return null;
    default:
      return assertNever(kind);
  }
}

/**
 * 悪い状態にかかったときの音。滑る・泣く・落とし穴は専用の音、うんこの効果はまとめて1つ（原型と同じ）。
 */
function effectSound(effect: EffectKind): SoundName {
  if (effect === 'slide') return 'slip';
  if (effect === 'stun') return 'cry';
  if (effect === 'pitfall') return 'pitFall';
  return 'poop';
}

/** うんこでかかる状態の名前（原型の `POOPS` の `label`）。 */
function poopLabel(kind: EffectKind): string {
  const poop = POOP_EFFECTS.find((effect) => effect.kind === kind);
  if (poop === undefined) throw new Error(`うんこでかかる状態ではない: ${kind}`);
  return poop.label;
}
