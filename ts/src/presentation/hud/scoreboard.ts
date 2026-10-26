import { lookOf } from '../../content/animals.js';
import { burntTongueOf, TONGUE_REACH } from '../../domain/abilities/frog/TongueAction.js';
import { PitActor } from '../../domain/abilities/mole/PitAction.js';
import { abilityOf } from '../../domain/abilities/registry.js';
import { TICKS_PER_SECOND, type Tick } from '../../domain/core/Tick.js';
import { POOP_EFFECTS } from '../../domain/rules/items.js';
import type { MatchConfig } from '../../domain/rules/MatchConfig.js';
import { SUDDEN_DEATH_HP } from '../../domain/rules/suddenDeath.js';
import { winsOf, type MatchState } from '../../domain/state/MatchState.js';
import { powerOf, type PlayerId, type PlayerState } from '../../domain/state/PlayerState.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import { formatSeconds } from '../menu/choices.js';
import { HOLE, PICK, POOP_MARKS } from './effectLabels.js';
import { isCpu, tagOf, type Roster } from './roster.js';

/**
 * 試合の横に出す板（時計と、プレイヤーごとの名札）の中身（原型の `renderCards` L5497-5548）。
 *
 * **文と値を返すだけで、画面に書かない。** どこにどう並べるかは `platform/ui/` が決める。
 * 分けてあるので、中身はブラウザ無しで確認できる。文は Python 版の `hud/scoreboard.py` と同じ。
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

/** 残り時間がこれ以下（秒）になったら時計を目立たせる（原型 L5547 の `t<=30`）。 */
const WARN_SECONDS = 30;

/** 時計の下の行（原型 L520）。延長戦に入っても変えない（原型も変えない）。 */
export const CLOCK_CAPTION = 'TIME';

/** 退場したプレイヤーの体力の行（原型 L5503）。 */
const OUT_CONDITION = '💀 退場';

/** 外周にいるプレイヤーの体力の行（原型 L5504）。 */
const NEGIBON_CONDITION = '🌿 葱ボン（場外）';

/** 外周にいるプレイヤーの名札に足す札（原型 L5509）。 */
const NEGIBON_TAG = '葱ボン';

/** 時計の中身（原型 L517-521 と L5542-5547）。 */
export interface ClockView {
  /** いま戦っている（決着のあとの待ちの間は、決まったばかりの）ラウンド。 */
  readonly round: number;
  readonly winsToTake: number;
  /** 上の行（「ROUND 1」と「3勝先取」を全角の空白でつなぐ。原型 L5546）。 */
  readonly heading: string;
  /** 残り時間（「2:59」）。 */
  readonly time: string;
  /** 残りが `WARN_SECONDS` 以下か（原型の `.warn`。数字を赤くする）。 */
  readonly warn: boolean;
}

/**
 * 時計の中身。
 *
 * ⚠️ ラウンドが決まった tick に、試合の側はもう次のラウンドの番号へ進めている。決着のあとの待ちの間の
 * 盤面は決まったラウンドのものなので、番号も1つ前を出す（原型は幕を出している間も、決まったラウンドの
 * 番号のまま。番号を進めるのは次のラウンドを始めるとき）。試合が決まったときは番号を進めないので、そのまま。
 */
export function describeClock(source: HudSource): ClockView {
  const { world, match, config } = source;
  const left = remainingSeconds(world);
  const round = source.betweenRounds ? match.round - 1 : match.round;
  return {
    round,
    winsToTake: config.winsToTake,
    heading: `ROUND ${round}\u3000${config.winsToTake}勝先取`,
    time: formatSeconds(left),
    warn: left <= WARN_SECONDS,
  };
}

/**
 * 残り秒（切り上げ。原型の `Math.ceil(G.time)`）。0 より下にもなる。
 *
 * @param limit 時間切れの時刻（`WorldState.endsAt`）
 */
export function secondsLeft(now: Tick, limit: Tick): number {
  return Math.ceil((limit - now) / TICKS_PER_SECOND);
}

/**
 * 残り時間（秒）。端数は切り上げ、0 より下にしない（0.2 秒残っていれば「0:01」）。
 *
 * 原型の `max(0, ceil(G.time))`。延長戦に入ると、時間切れの時刻が置き直される（`WorldState.endsAt`）ので、
 * 延長戦の長さから数え直す（原型も `G.time=60` から数え直す）。
 */
export function remainingSeconds(world: Readonly<WorldState>): number {
  return Math.max(0, secondsLeft(world.now, world.endsAt));
}

/** 名札の札の色の種類（原型の `.tag`。L5506-5509）。人間・CPU・外周にいる。 */
export type TagStyle = 'human' | 'cpu' | 'negibon';

/** 名札の1行目で、動物の名前の横に並べる札1つ。 */
export interface CardTag {
  readonly text: string;
  readonly style: TagStyle;
}

/** プレイヤー1人ぶんの名札（原型 L5530-5538 の並び）。 */
export interface PlayerCardView {
  readonly id: PlayerId;
  /** 左に大きく出す動物の絵文字。 */
  readonly emoji: string;
  /** 動物の名前（1行目）。 */
  readonly name: string;
  /** 名前の横の札（「1P」か「CPU1・ふつう」と、外周にいる間は「葱ボン」）。 */
  readonly tags: readonly CardTag[];
  /** 取った勝ち星と、優勝までの残り（「★☆☆」）。 */
  readonly stars: string;
  /** 盤面にいるか・外周にいるか・退場したか（原型の `.pcard` に足す名前。L5502）。 */
  readonly state: PlayerState['life']['kind'];
  /** 体力のハート、または盤面にいないわけ。 */
  readonly condition: string;
  /** 爆弾・火力・靴（「💣1」「🔥2」「👟0」。原型は3つの span）。 */
  readonly stats: readonly [string, string, string];
  /** かかっている状態と、使えるとくぎ（原型の `.fx`。空白でつないで1行に出す）。 */
  readonly effects: readonly string[];
}

/** 全員ぶんの名札。プレイヤー番号の順（原型の `players` の順）。 */
export function describePlayers(source: HudSource): PlayerCardView[] {
  return source.world.players.map((player) => describePlayer(source, player));
}

function describePlayer(source: HudSource, player: Readonly<PlayerState>): PlayerCardView {
  const { match, config, roster } = source;
  const look = lookOf(player.animal);
  const wins = winsOf(match, player.id);
  const tags: CardTag[] = [{ text: tagOf(roster, player.id), style: isCpu(roster, player.id) ? 'cpu' : 'human' }];
  if (player.life.kind === 'negibon') tags.push({ text: NEGIBON_TAG, style: 'negibon' });
  return {
    id: player.id,
    emoji: look.emoji,
    name: look.name,
    tags,
    stars: '★'.repeat(wins) + '☆'.repeat(Math.max(0, config.winsToTake - wins)),
    state: player.life.kind,
    condition: conditionOf(source, player),
    stats: [`💣${player.maxBombs}`, `🔥${powerOf(player)}`, `👟${player.shoes}`],
    effects: cardEffects(source.world, player),
  };
}

function conditionOf(source: HudSource, player: Readonly<PlayerState>): string {
  switch (player.life.kind) {
    case 'negibon':
      return NEGIBON_CONDITION;
    case 'out':
      return OUT_CONDITION;
    case 'alive':
      return hearts(player.hp, maxHpOf(source, player));
  }
}

/**
 * そのプレイヤーの、いまの体力の上限（半分の単位。原型の `maxHp`）。減ったぶんを黒いハートで見せるのに使う。
 *
 * ラウンドの始まりの体力（設定の値に動物ごとの上乗せを足したもの。原型の `makePlayer` L1187）。延長戦に
 * 入ると、加わったプレイヤーの上限は延長戦の体力になる（原型の `enterSuddenDeath` L4455 の `p.maxHp=1`）。
 */
function maxHpOf(source: HudSource, player: Readonly<PlayerState>): number {
  if (source.world.suddenDeath) return SUDDEN_DEATH_HP;
  const base = source.config.startingHp[player.id] ?? player.hp;
  return base + abilityOf(player.animal).hpBonus;
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
 * 状態の行に並べるもの。並びと字は原型 L5511-5527 と同じ（Python 版の `card_effects` と同じ）。
 *
 * 原型は、プレイヤーの状態（盤面・外周・退場）を見ずに組む。退場したプレイヤーにも、残っているとくぎと
 * 状態を出す（倒れて退場したときは、かかっていた状態もとくぎも消えない。原型の `kill`、この版の
 * `domain/mutations/damage.ts` の `hurt`）。外周へ回ったときは状態ととくぎの印が消えるので、何も出ない
 * （原型の `toNegibon`）。
 *
 * とくぎは、持っている印（`hasSpecial`）で見る（原型の `p.chicken`。L5512）。外周から戻ったプレイヤーは、
 * 回数だけが残って印が外れていることがあり、そのとくぎは出せないので出さない。「×n」は回数が2以上の
 * とき（原型 L5513）。
 */
function cardEffects(world: Readonly<WorldState>, player: Readonly<PlayerState>): string[] {
  const { effects } = player;
  const out: string[] = [];
  if (player.hasSpecial) {
    const { special } = lookOf(player.animal);
    const times = player.specialCharges > 1 ? `×${player.specialCharges}` : '';
    out.push(`${special.emoji}${special.name}${times}`);
  }
  if (effects.has('scattering')) out.push('💩ポロポロ中');
  if (player.action?.kind === 'tongue') out.push('👅舌');
  // 焼けた舌は盤面に描くものが無いので、ここで知らせる（原型 L5516-5517）。
  const scar = burntTongueOf(world, player.id);
  if (scar !== undefined) {
    const seconds = Math.ceil(scar.untilRegen / TICKS_PER_SECOND);
    out.push(`👅🔥舌 ${scar.limit}/${TONGUE_REACH}マス（${seconds}秒で+1）`);
  }
  if (player.action?.kind === 'dig') out.push(`${PICK}穴をほってる`);
  // 残りの秒は小数1桁（原型の `p.effects.pitfall.toFixed(1)`。原型は秒の小数で持つので、tick を秒にしてから丸める）。
  if (effects.has('pitfall')) out.push(`${HOLE}落とし穴 ${(effects.remaining('pitfall') / TICKS_PER_SECOND).toFixed(1)}秒`);
  // 穴は盤面に描かないので、しかけた数をここで見せる（原型の注記 L5520）。
  const pits = world.actors.filter((actor) => actor instanceof PitActor && actor.owner === player.id).length;
  if (pits > 0) out.push(`${HOLE}しかけた穴 ${pits}個`);
  if (effects.has('stun')) out.push('😭涙');
  if (effects.has('slide')) out.push('🍌すべり');
  for (const [kind, mark] of POOP_MARKS) {
    if (!effects.has(kind)) continue;
    const label = POOP_EFFECTS.find((poop) => poop.kind === kind)?.label ?? kind;
    out.push(`${mark}${label}`);
  }
  return out;
}
