import { lookOf } from '../../content/animals.js';
import { BurntTongueActor, TONGUE_REACH } from '../../domain/abilities/frog/TongueAction.js';
import { abilityOf } from '../../domain/abilities/registry.js';
import { TICKS_PER_SECOND } from '../../domain/core/Tick.js';
import type { MatchConfig } from '../../domain/rules/MatchConfig.js';
import { winsOf, type MatchState } from '../../domain/state/MatchState.js';
import { powerOf, type PlayerId, type PlayerState } from '../../domain/state/PlayerState.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import { effectText } from './effectLabels.js';
import { tagOf, type Roster } from './roster.js';

/**
 * 試合の横に出す板（時計と、プレイヤーごとの名札）の中身。
 *
 * **文と値を返すだけで、画面に書かない。** どこにどう並べるかは `platform/ui/` が決める。
 * 分けてあるので、中身はブラウザ無しで確認できる。
 */

/** 板を作るのに要るもの。盤面だけでは足りない（勝ち数・設定・誰が操作しているかは盤面に無い）。 */
export interface HudSource {
  readonly world: Readonly<WorldState>;
  readonly match: Readonly<MatchState>;
  readonly config: MatchConfig;
  readonly roster: Roster;
  /** ラウンドが決まり、次の盤面を待っている最中か。 */
  readonly betweenRounds: boolean;
}

/** 残り時間がこれ以下になったら、時計を目立たせる（秒）。 */
const WARN_SECONDS = 30;

export interface ClockView {
  /** いま戦っている（決着のあとの待ちの間は、決まったばかりの）ラウンド。 */
  readonly round: number;
  readonly winsToTake: number;
  /** 残り時間（「2:59」）。 */
  readonly time: string;
  /** 残りが少ないか。 */
  readonly warn: boolean;
  /** 延長戦の最中か。 */
  readonly suddenDeath: boolean;
}

export function describeClock(source: HudSource): ClockView {
  const { world, match, config } = source;
  const left = remainingSeconds(world);
  return {
    // ⚠️ ラウンドが決まった tick に、試合の側はもう次のラウンドの番号へ進めている。
    // 待ちの間の盤面は前のラウンドのものなので、番号もそちらに合わせる。
    // 優勝が決まったときは進めていないので、そのまま。
    round: source.betweenRounds ? match.round - 1 : match.round,
    winsToTake: config.winsToTake,
    time: `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`,
    warn: left <= WARN_SECONDS,
    suddenDeath: world.suddenDeath,
  };
}

/** 残り時間（秒）。端数は切り上げる（0.2 秒残っていれば「0:01」）。 */
export function remainingSeconds(world: Readonly<WorldState>): number {
  return Math.max(0, Math.ceil((world.endsAt - world.now) / TICKS_PER_SECOND));
}

/** プレイヤー1人ぶんの名札。 */
export interface PlayerCardView {
  readonly id: PlayerId;
  readonly emoji: string;
  /** 動物の名前。 */
  readonly name: string;
  /** 誰が操作しているか（「1P」「CPU・ふつう」）。 */
  readonly tag: string;
  /** 取った勝ち星と、優勝までの残り（「★☆☆」）。 */
  readonly stars: string;
  readonly state: PlayerState['life']['kind'];
  /** 体力のハート、または盤面にいないわけ。 */
  readonly condition: string;
  /** 爆弾・火力・靴。 */
  readonly stats: string;
  /** かかっている状態と、使えるとくぎ。 */
  readonly effects: readonly string[];
}

export function describePlayers(source: HudSource): PlayerCardView[] {
  return source.world.players.map((player) => describePlayer(source, player));
}

function describePlayer(source: HudSource, player: Readonly<PlayerState>): PlayerCardView {
  const { match, config, roster } = source;
  const look = lookOf(player.animal);
  const wins = winsOf(match, player.id);
  return {
    id: player.id,
    emoji: look.emoji,
    name: look.name,
    tag: tagOf(roster, player.id),
    stars: '★'.repeat(wins) + '☆'.repeat(Math.max(0, config.winsToTake - wins)),
    state: player.life.kind,
    condition: conditionOf(player, maxHpOf(config, player)),
    stats: `💣${player.maxBombs} 🔥${powerOf(player)} 👟${player.shoes}`,
    effects: effectsOf(source.world, player, look.special),
  };
}

/** そのラウンドの始まりの体力（半分の単位）。減ったぶんを黒いハートで見せるのに使う。 */
function maxHpOf(config: MatchConfig, player: Readonly<PlayerState>): number {
  const base = config.startingHp[player.id] ?? player.hp;
  return base + abilityOf(player.animal).hpBonus;
}

function conditionOf(player: Readonly<PlayerState>, maxHp: number): string {
  switch (player.life.kind) {
    case 'negibon':
      return '🌿 葱ボン（外周）';
    case 'out':
      return '💀 退場';
    case 'alive':
      return hearts(player.hp, maxHp);
  }
}

/**
 * 体力をハートで表す。体力は半分の単位なので、2 で1個。
 *
 * 減ったぶんは黒いハートで残す。いくつ残っているかより、あといくつで倒れるかが
 * 一目で分かるように。
 */
export function hearts(hp: number, maxHp: number): string {
  const full = Math.floor(hp / 2);
  const half = hp % 2;
  const lost = Math.max(0, Math.ceil(maxHp / 2) - full - half);
  return '❤️'.repeat(full) + '💔'.repeat(half) + '🖤'.repeat(lost);
}

/**
 * かかっている状態と、使えるとくぎ。盤面にいるプレイヤーだけ。
 *
 * ⚠️ 盤面にいないプレイヤーは出さない。残り1分を切ってから倒れたプレイヤーは退場するだけで、
 * とくぎの印と回数やかかっていた状態は試合の側で消されずに残る（もう使われない）。
 *
 * とくぎは、持っている印（`hasSpecial`）があるときだけ出す。原型の名札（L5512）と同じく回数では見ない。
 * 外周から戻ったプレイヤーは、回数だけが残って印が外れていることがある（そのとくぎは出せない）。
 * 「×N」は回数が2以上のとき（原型の L5513）。
 */
function effectsOf(
  world: Readonly<WorldState>,
  player: Readonly<PlayerState>,
  special: { readonly name: string; readonly emoji: string },
): string[] {
  if (player.life.kind !== 'alive') return [];
  const effects: string[] = [];
  if (player.hasSpecial) {
    const times = player.specialCharges > 1 ? `×${player.specialCharges}` : '';
    effects.push(`${special.emoji}${special.name}${times}`);
  }
  for (const kind of player.effects.active()) effects.push(effectText(kind));
  // 焼けた舌は盤面に描くものが無いので、ここで知らせる（原型の名札と同じ形）。
  const burnt = world.actors.find(
    (actor): actor is BurntTongueActor => actor instanceof BurntTongueActor && actor.owner === player.id,
  );
  if (burnt !== undefined) {
    const seconds = Math.ceil(burnt.untilRegen / TICKS_PER_SECOND);
    effects.push(`👅🔥舌 ${burnt.limit}/${TONGUE_REACH}マス（${seconds}秒で+1）`);
  }
  return effects;
}
