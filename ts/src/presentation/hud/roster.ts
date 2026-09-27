import { CPU_LEVELS, type CpuLevelKey } from '../../ai/CpuLevel.js';
import type { PlayerId } from '../../domain/state/PlayerState.js';
import { lookOf } from '../../content/animals.js';

/**
 * そのプレイヤーを誰が操作しているか。画面の名札と通知に出す。
 *
 * 試合（ルールの層）はこれを知らない。人間か CPU かで試合の進め方は変わらず、
 * 操作の窓口が違うだけだから。見せるためだけに、画面の側で持つ。
 */
export type Controller =
  | {
      readonly kind: 'human';
      /** 画面での呼び方（1P・2P など）。 */
      readonly label: string;
      /** この端末で操作している人か。通信対戦で「あなた」を示すのに使う。 */
      readonly local: boolean;
    }
  | { readonly kind: 'cpu'; readonly level: CpuLevelKey };

/** 全員ぶんの `Controller`。プレイヤー番号の順。 */
export type Roster = readonly Controller[];

/**
 * 名札の短い印（「1P」「CPU・ふつう」など）。
 *
 * @throws Error その番号のプレイヤーが一覧にいないとき
 */
export function tagOf(roster: Roster, id: PlayerId): string {
  const controller = controllerOf(roster, id);
  if (controller.kind === 'cpu') return `CPU・${CPU_LEVELS[controller.level].label}`;
  return controller.local ? `${controller.label}（あなた）` : controller.label;
}

/**
 * 通知や幕に出す呼び方（「うさぎ（1P）」「ぞう（CPU）」）。
 *
 * 動物の名前を先に出す。遊んでいる人は、番号より動物で相手を覚えている。
 */
export function displayName(roster: Roster, id: PlayerId, animal: string): string {
  const controller = controllerOf(roster, id);
  const who = controller.kind === 'cpu' ? 'CPU' : controller.label;
  return `${lookOf(animal).name}（${who}）`;
}

function controllerOf(roster: Roster, id: PlayerId): Controller {
  const controller = roster[id];
  if (controller === undefined) throw new Error(`プレイヤー ${id} が名札の一覧にいない`);
  return controller;
}

/**
 * 通信対戦の名札。人間が操作しているプレイヤーは番号で、それ以外は設定の強さの CPU。
 *
 * @param players 試合にいるプレイヤー（プレイヤー番号の順）
 * @param humans いま人間が操作しているプレイヤー（抜けて CPU に替わった人は含めない）
 * @param local この端末で操作しているプレイヤー
 * @param cpuLevelOf そのプレイヤーを受け持つ CPU の強さ
 */
export function lanRoster(
  players: readonly PlayerId[],
  humans: readonly PlayerId[],
  local: PlayerId,
  cpuLevelOf: (id: PlayerId) => CpuLevelKey,
): Roster {
  return players.map((id) =>
    humans.includes(id)
      ? { kind: 'human', label: `${id + 1}P`, local: id === local }
      : { kind: 'cpu', level: cpuLevelOf(id) },
  );
}
