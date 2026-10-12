import { abilityOf } from '../abilities/registry.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { PlayerState } from '../state/PlayerState.js';
import { isAlive, isFrozen } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 技のボタンを見て、動物ごとの振る舞いを始める・進める。
 *
 * ## タップととくぎを1つのボタンで分ける
 *
 * ボタンを増やさずに2つの技を持たせるため、押した長さで分けている。
 *
 * - 押して離す … 通常技（通常技の無い動物は、チキンがあればとくぎ。原型の doAction）
 * - 押し続ける … とくぎ（動物ごとに必要な長さが違う）
 *
 * どちらが何になるかは `abilities/` の各動物が決める。
 *
 * とくぎはチキンを拾って溜めた回数ぶんだけ使える。
 *
 * ## ⚠️ ラウンドの開始時に押していたボタンは、一度離すまで効かない
 *
 * キーボードでは、押しっぱなしでも文字入力の繰り返し遅延（およそ 0.5 秒）が
 * 偶然の緩衝材になっていた。ゲームパッドは次の tick で押下が戻るため、
 * ラウンドが始まって 0.5 秒でとくぎが暴発する。
 *
 * 開始時は「ロックされた」状態にしておき、**一度離したときに解除**する。
 * キーボード側も同じだけ安全になる。
 *
 * ## 動けない間（泣いている・落とし穴にはまっている）は技を出さない
 *
 * 原型は押した瞬間に通常技を、しきい値に届いた瞬間にとくぎを出し、どちらも動けなければ
 * 何もせずに帰る。その押し方の分は捨てる（あとから遅れて出ない。チキンも減らない）。
 * この版は離した瞬間に通常技を出すので、次の3か所で見る。
 *
 * - 押し始めた tick に動けなければ、その押し方では通常技を出さない（`tapVoided`）
 * - しきい値に届いた tick に動けなければ、とくぎを出さない（その押し方のとくぎはそれきり）
 * - 離した tick に動けなければ、通常技を出さない
 *
 * ⚠️ 3つ目は原型と揃わない。原型は押した瞬間（動けるうち）に通常技を出し終えている。
 * この版で出すと泣いたまま技が出る（跳んで逃げる、など）ので、出さないことにした。
 * 押し始めに動けなくても、動けるようになってからしきい値に届けば、とくぎは出る（原型と同じ）。
 *
 * ## 進めるのと始めるのを分ける
 *
 * 続いている振る舞いを進める（`advanceFor`）のと、ボタンを見て新しく始める（`watchFor`）のは
 * 別の番にある。原型は、プレイヤーごとの効果の処理の中で技を進め、全員ぶん済ませたあとの、
 * プレイヤーごとの入力の処理（動く → 爆弾を置く → 技を始める）で技を始める。どちらの番で
 * 呼ぶかは `Simulation` が決める。
 *
 * ⚠️ この tick に振る舞いを進めたプレイヤーは、同じ tick には新しく始めない（終わった tick でも）。
 * 原型は、技が終わったフレームのうちに次の技を始められる。1 tick の違いで、今までの形のままにしてある。
 *
 * ## この System は動物の種類を知らない
 *
 * 何の技かは `Ability` が決め、始まった振る舞いは `ActiveAction` が
 * 自分で進める。ここは押した長さを数えて呼び分けるだけ。
 */
export class ActionSystem {
  /**
   * 1人ぶん。技の間隔を1 tick 減らし、乗っ取り中の振る舞いを1 tick 進める。
   *
   * 間隔を減らすのは、入力を受け取っているプレイヤーだけ（通信対戦で入力の届いていない番は
   * 進めない。今までと同じ）。
   *
   * @returns 起きたイベントと、振る舞いを進めたか（進めたら、この tick は新しく始めない）
   */
  advanceFor(world: WorldState, player: PlayerState, hasInput: boolean): { events: SimEvent[]; advanced: boolean } {
    if (!hasInput) return { events: [], advanced: false };
    if (player.abilityCooldown > 0) {
      player.abilityCooldown = tick(player.abilityCooldown - 1);
    }
    if (player.action === null) return { events: [], advanced: false };
    return { events: this.#advance(world, player), advanced: true };
  }

  /** 1人ぶん。技のボタンの押し方を見て、技を出す。盤面にいるプレイヤーだけ。 */
  watchFor(world: WorldState, player: PlayerState, playerInput: PlayerInput): SimEvent[] {
    if (!isAlive(player)) return [];
    return this.#watchButton(world, player, playerInput);
  }

  /**
   * 被弾を見たあとに、振る舞いが爆風に触れたかを見る（`ActiveAction.afterDamage`）。
   * 盤面にいるプレイヤーだけ。終わったら後始末を呼んで外す。
   */
  afterDamage(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      const action = player.action;
      if (action === null || action.afterDamage === undefined || !isAlive(player)) continue;
      const result = action.afterDamage(world, player);
      events.push(...result.events);
      if (!result.done) continue;
      if (action.finish !== undefined) events.push(...action.finish(world, player));
      player.action = null;
    }
    return events;
  }

  /** 進行中の振る舞いを1 tick 進める。 */
  #advance(world: WorldState, player: PlayerState): SimEvent[] {
    const action = player.action;
    if (action === null) return [];

    // ⚠️ 前の tick のうちに盤面を離れていたら（倒れた・外周へ回った）、もう進めずに
    // 打ち切る。進めると、盤面にいない人の技が1 tick ぶん働く（拾った物が外周の
    // 葱ボンに渡る、など）。
    const result = isAlive(player) ? action.tick(world, player) : { events: [], done: true };
    const events = [...result.events];
    // 倒れたら途中でも打ち切る。
    if (result.done || !isAlive(player)) {
      if (action.finish !== undefined) events.push(...action.finish(world, player));
      player.action = null;
    }
    return events;
  }

  /** 技のボタンの押し方を見て、通常技ととくぎを呼び分ける。 */
  #watchButton(
    world: WorldState,
    player: PlayerState,
    playerInput: PlayerInput,
  ): SimEvent[] {
    // ラウンド開始時から押しっぱなしのぶんは、離すまで数え始めない。
    if (player.actionHeld < 0) {
      if (!playerInput.action) player.actionHeld = tick(0);
      return [];
    }

    const ability = abilityOf(player.animal);
    const frozen = isFrozen(player);

    if (playerInput.action) {
      player.actionHeld = tick(player.actionHeld + 1);
      // 押し始めに動けなければ、この押し方では通常技を出さない（離すまで覚えておく）。
      if (player.actionHeld === 1) player.tapVoided = frozen;
      // 長押しがしきい値に届いた瞬間に1回だけ出す。
      if (player.actionHeld === ability.holdTicks && player.specialCharges > 0) {
        // 動けなければ出さない。チキンは減らさず、この押し方のとくぎはそれきり。
        if (frozen) return [];
        return this.#special(world, player);
      }
      return [];
    }

    // 離した。しきい値に届いていなければ通常技。
    const held = player.actionHeld;
    player.actionHeld = tick(0);
    if (held <= 0 || held >= ability.holdTicks) return [];
    // 動けない間に離した押し方と、動けない間に押し始めた押し方は捨てる。
    if (frozen || player.tapVoided) return [];
    // 通常技の無い動物は、ポン押しでもとくぎが出る（チキンがあれば。原型の doAction）。
    if (ability.onTap === undefined) return player.specialCharges > 0 ? this.#special(world, player) : [];
    const cooldownBefore = player.abilityCooldown;
    const result = ability.onTap(world, player);
    if (result.action !== null) player.action = result.action;
    // 技が実際に出たかは、振る舞いが始まった・何かが起きた・間隔が始まった、の
    // どれかで判断する。間隔中に押しただけなら何も起きないので知らせない。
    const fired =
      result.action !== null ||
      result.events.length > 0 ||
      player.abilityCooldown !== cooldownBefore;
    if (!fired) return result.events;
    return [{ type: 'techniqueUsed', player: player.id, special: false }, ...result.events];
  }

  /** とくぎを出す。チキンを1つ使う（出せる形かどうかは呼び出し側が見る）。 */
  #special(world: WorldState, player: PlayerState): SimEvent[] {
    const ability = abilityOf(player.animal);
    if (ability.onHold === undefined) return [];
    player.specialCharges -= 1;
    const result = ability.onHold(world, player);
    if (result.action !== null) player.action = result.action;
    return [{ type: 'techniqueUsed', player: player.id, special: true }, ...result.events];
  }
}
