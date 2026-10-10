import { abilityOf } from '../abilities/registry.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { isAlive, isFrozen } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 技のボタンを見て、動物ごとの振る舞いを始める・進める。
 *
 * ## タップととくぎを1つのボタンで分ける
 *
 * ボタンを増やさずに2つの技を持たせるため、押した長さで分けている。
 *
 * - 押して離す … 通常技
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
 * 続いている振る舞いを進めるのを先に全員ぶん済ませ、ボタンを見て新しく始めるのはそのあと。
 * 原型も、効果の処理の中で全員の技を進め、そのあとの入力の処理で技を始める。
 * 進めるときは1人ずつ、そのプレイヤーの「あとで呼ぶ処理」（`Simulation` が「勝手に設置」を
 * 渡す）をすぐに呼ぶ。原型はプレイヤーごとに「技を進める → 勝手に設置」と回すので、番号の
 * 大きいプレイヤーの技が番号の小さいプレイヤーの爆弾を押しのけたり起爆したりする順まで同じになる。
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
   * @param afterAdvance 1人ぶんの振る舞いを進めた直後に呼ぶ処理。番号の順に全員ぶん呼ぶ
   *   （振る舞いが無いプレイヤーも、入力が無いプレイヤーも）
   */
  step(
    world: WorldState,
    playerInputs: ReadonlyMap<PlayerId, PlayerInput>,
    afterAdvance: (player: PlayerState) => SimEvent[] = () => [],
  ): SimEvent[] {
    const events: SimEvent[] = [];
    const advanced = new Set<PlayerId>();
    for (const player of world.players) {
      if (playerInputs.has(player.id)) {
        if (player.abilityCooldown > 0) {
          player.abilityCooldown = tick(player.abilityCooldown - 1);
        }
        if (player.action !== null) {
          advanced.add(player.id);
          events.push(...this.#advance(world, player));
        }
      }
      events.push(...afterAdvance(player));
    }

    for (const player of world.players) {
      const playerInput = playerInputs.get(player.id);
      if (playerInput === undefined || advanced.has(player.id)) continue;
      if (!isAlive(player)) continue;
      events.push(...this.#watchButton(world, player, playerInput));
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
        if (ability.onHold === undefined) return [];
        player.specialCharges -= 1;
        const result = ability.onHold(world, player);
        if (result.action !== null) player.action = result.action;
        return [{ type: 'techniqueUsed', player: player.id, special: true }, ...result.events];
      }
      return [];
    }

    // 離した。しきい値に届いていなければ通常技。
    const held = player.actionHeld;
    player.actionHeld = tick(0);
    if (held <= 0 || held >= ability.holdTicks) return [];
    // 動けない間に離した押し方と、動けない間に押し始めた押し方は捨てる。
    if (frozen || player.tapVoided) return [];
    if (ability.onTap === undefined) return [];
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
}
