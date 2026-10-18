import { abilityOf } from '../abilities/registry.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { PlayerState } from '../state/PlayerState.js';
import { isAlive, isFrozen, justPressed } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 技のボタンを見て、動物ごとの振る舞いを始める・進める。
 *
 * ## 通常技ととくぎを1つのボタンで分ける
 *
 * ボタンを増やさずに2つの技を持たせるため、押した瞬間と押し続けた長さで分けている
 * （原型の humanUpdate と同じ）。
 *
 * - 押した瞬間 … 通常技（通常技の無い動物は、チキンがあればとくぎ。原型の doAction）
 * - 押し続けてしきい値に届いた瞬間 … とくぎ（動物ごとに必要な長さが違う。原型の doSpecial）
 *
 * ⚠️ とくぎを出そうと押し続けると、押した瞬間の通常技も出る（跳んでから撒く、など）。原型も同じ。
 * 通常技がボタンを受け付けない振る舞い（`ActiveAction.blocksButtons`）を始める動物は、その振る舞いが
 * しきい値より前に終わらない限り、押し続けてもとくぎが出ない。
 *
 * どちらが何になるかは `abilities/` の各動物が決める。
 *
 * もう1つ、とくぎを直に出すボタン（`PlayerInput.special`）がある。押した瞬間に、通常技を挟まずに
 * とくぎが出る。人間の操作には割り当てておらず、CPU だけが押す（原型の CPU はボタンを通らずに
 * とくぎを呼んでいた）。出せる条件（動けない間・ボタンを受け付けない振る舞いの最中・チキンが無い）は
 * 長押しのとくぎと同じ。
 *
 * とくぎはチキンを拾って溜めた回数ぶんだけ使える。しきい値は押し方1回につき1回だけ見る
 * （`actionFired`）。届いた tick に出せなければ（動けない・チキンが無い・ボタンを受け付けない
 * 振る舞いの最中）、その押し方のとくぎはそれきり。離すと数え直す。
 *
 * ## ⚠️ ラウンドの開始時に押していたボタンは、一度離すまで効かない
 *
 * キーボードでは、押しっぱなしでも文字入力の繰り返し遅延（およそ 0.5 秒）が
 * 偶然の緩衝材になっていた。ゲームパッドは次の tick で押下が戻るため、
 * ラウンドが始まって 0.5 秒でとくぎが暴発する。
 *
 * 開始時は、前の tick にボタンを押していた扱い（押した瞬間にならない）・とくぎは出し終えた扱い
 * （`actionFired`）にしておく。一度離すと、どちらも元に戻る（原型の startRound と同じ）。
 *
 * ## 動けない間（泣いている・落とし穴にはまっている）は技を出さない
 *
 * 押した瞬間・しきい値に届いた瞬間に動けなければ、何もしない。あとから遅れて出ない
 * （チキンも減らない）。押し始めに動けなくても、動けるようになってからしきい値に届けば、
 * とくぎは出る。どれも原型と同じ。
 *
 * ## 進めるのと始めるのを分ける
 *
 * 続いている振る舞いを進める（`advanceFor`）のと、ボタンを見て技を出す（`watchFor`）のは
 * 別の番にある。原型は、プレイヤーごとの効果の処理の中で技を進め、全員ぶん済ませたあとの、
 * プレイヤーごとの入力の処理（動く → 爆弾を置く → 技を始める）で技を出す。どちらの番で
 * 呼ぶかは `Simulation` が決める。
 *
 * 振る舞いの最中もボタンは見る。振る舞いが終わった tick のうちに押せば、次の技が出る（原型と同じ）。
 *
 * ## この System は動物の種類を知らない
 *
 * 何の技かは `Ability` が決め、始まった振る舞いは `ActiveAction` が
 * 自分で進める。ここは押し方を見て呼び分けるだけ。
 */
export class ActionSystem {
  /**
   * 1人ぶん。技の間隔を1 tick 減らし、乗っ取り中の振る舞いを1 tick 進める。
   *
   * 間隔を減らすのは、入力を受け取っているプレイヤーだけ（通信対戦で入力の届いていない番は
   * 進めない。今までと同じ）。
   */
  advanceFor(world: WorldState, player: PlayerState, hasInput: boolean): SimEvent[] {
    if (!hasInput) return [];
    if (player.abilityCooldown > 0) {
      player.abilityCooldown = tick(player.abilityCooldown - 1);
    }
    return this.#advance(world, player);
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

  /** 技のボタンの押し方を見て、通常技ととくぎを呼び分ける（原型の humanUpdate の終わり）。 */
  #watchButton(
    world: WorldState,
    player: PlayerState,
    playerInput: PlayerInput,
  ): SimEvent[] {
    const events: SimEvent[] = [];
    // とくぎを直に出すボタン（人間の操作には無い。`PlayerInput.special`）。技のボタンの長さには触れない。
    if (justPressed(player, playerInput, 'special') && this.#accepts(player) && player.hasSpecial) {
      events.push(...this.#special(world, player));
    }
    if (justPressed(player, playerInput, 'action')) events.push(...this.#tap(world, player));
    if (!playerInput.action) {
      player.actionHeld = tick(0);
      player.actionFired = false;
      return events;
    }
    player.actionHeld = tick(player.actionHeld + 1);
    if (player.actionHeld >= abilityOf(player.animal).holdTicks && !player.actionFired) {
      // ⚠️ 出せるかを見る前に立てる。出せなくても、この押し方のとくぎはそれきり。
      player.actionFired = true;
      if (this.#accepts(player) && player.hasSpecial) events.push(...this.#special(world, player));
    }
    return events;
  }

  /** 技のボタンが効くか。動けない間と、ボタンを受け付けない振る舞いの最中は効かない。 */
  #accepts(player: PlayerState): boolean {
    return !isFrozen(player) && player.action?.blocksButtons !== true;
  }

  /** 押した瞬間。通常技（原型の doAction）。 */
  #tap(world: WorldState, player: PlayerState): SimEvent[] {
    if (!this.#accepts(player)) return [];
    const ability = abilityOf(player.animal);
    // 通常技の無い動物は、押した瞬間にとくぎが出る（チキンがあれば）。
    if (ability.onTap === undefined) return player.hasSpecial ? this.#special(world, player) : [];
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

  /**
   * とくぎを出す。チキンを1つ使う（出せる形かどうかは呼び出し側が見る）。
   *
   * 回数を1つ減らし、0 になったら持っている印を外す（原型の useSpecial L2607-2608 と同じ。原型は回数が無くても
   * 印があれば1回ぶんとして数える `(回数 || 1) − 1` の形なので、そのまま写した）。
   */
  #special(world: WorldState, player: PlayerState): SimEvent[] {
    const ability = abilityOf(player.animal);
    if (ability.onHold === undefined) return [];
    player.specialCharges = Math.max(0, (player.specialCharges || 1) - 1);
    if (player.specialCharges <= 0) player.hasSpecial = false;
    const result = ability.onHold(world, player);
    if (result.action !== null) player.action = result.action;
    return [{ type: 'techniqueUsed', player: player.id, special: true }, ...result.events];
  }
}
