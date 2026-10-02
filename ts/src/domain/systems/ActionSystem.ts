import { abilityOf } from '../abilities/registry.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { isAlive } from '../state/PlayerState.js';
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
 * ## この System は動物の種類を知らない
 *
 * 何の技かは `Ability` が決め、始まった振る舞いは `ActiveAction` が
 * 自分で進める。ここは押した長さを数えて呼び分けるだけ。
 */
export class ActionSystem {
  step(world: WorldState, playerInputs: ReadonlyMap<PlayerId, PlayerInput>): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      const playerInput = playerInputs.get(player.id);
      if (playerInput === undefined) continue;

      if (player.abilityCooldown > 0) {
        player.abilityCooldown = tick(player.abilityCooldown - 1);
      }

      if (player.action !== null) {
        events.push(...this.#advance(world, player));
        continue;
      }
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

    if (playerInput.action) {
      player.actionHeld = tick(player.actionHeld + 1);
      // 長押しがしきい値に届いた瞬間に1回だけ出す。
      if (player.actionHeld === ability.holdTicks && player.specialCharges > 0) {
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
