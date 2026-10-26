import { CPU_LEVELS, type CpuLevelKey } from '../../ai/CpuLevel.js';
import type { PlayerId } from '../../domain/state/PlayerState.js';

/**
 * そのプレイヤーを誰が操作しているか。画面の名札と通知に出す。
 *
 * 試合（ルールの層）はこれを知らない。人間か CPU かで試合の進め方は変わらず、
 * 操作の窓口が違うだけだから。見せるためだけに、画面の側で持つ。
 *
 * 名札の札（`tagOf`）は、名札の1行目で動物の名前の横に出す短い印。原型の `renderCards`（L5506-5508）と
 * 同じく、人間は「1P」、CPU は「CPU1・ふつう」（何体目かと強さ）。原型は名札に「（あなた）」を付けない
 * （付けるのはロビーの枠の見出しだけ。L5831）。
 */
export type Controller =
  | {
      readonly kind: 'human';
      /** 画面での呼び方（1P・2P など）。 */
      readonly label: string;
      /**
       * この端末で操作しているプレイヤーか。通信対戦で、この端末のキーの案内を出すプレイヤーを選ぶのに使う
       * （原型の `lanLocal`）。1台の試合ではいつも false（1台を囲む全員が同じ画面を見ている）。
       */
      readonly local: boolean;
    }
  | {
      readonly kind: 'cpu';
      /** 何体目の CPU か（1から）。名札の「CPU1」の数（原型の `cpuIdx + 1`）。 */
      readonly number: number;
      readonly level: CpuLevelKey;
      /**
       * 原型の `label` の呼び方を、動物の名前でなくこれにする（`labelOf`）。
       *
       * 通信対戦で抜けて CPU に替わったプレイヤーだけが持つ（人間だったときの「2P」のまま。原型は
       * 抜けたプレイヤーを CPU にするとき `label` を書き換えない。L3793）。ほかの CPU は持たず、動物の名前で呼ぶ。
       */
      readonly label?: string;
    };

/** 全員ぶんの `Controller`。プレイヤー番号の順。 */
export type Roster = readonly Controller[];

/** 番号だけの呼び方（「1P」）。 */
export function numberedName(id: PlayerId): string {
  return `${id + 1}P`;
}

/**
 * 名札の札（「1P」「CPU1・ふつう」。原型の `renderCards` L5506-5508）。
 *
 * @throws Error その番号のプレイヤーが一覧にいないとき
 */
export function tagOf(roster: Roster, id: PlayerId): string {
  const controller = controllerOf(roster, id);
  if (controller.kind === 'cpu') return `CPU${controller.number}・${CPU_LEVELS[controller.level].label}`;
  return controller.label;
}

/** そのプレイヤーを CPU が操作しているか。 */
export function isCpu(roster: Roster, id: PlayerId): boolean {
  return controllerOf(roster, id).kind === 'cpu';
}

/**
 * 原型の `label` の呼び方。人間は「1P」、CPU は `cpuName`（動物の名前）。
 *
 * 原型は CPU の名前を動物の名前そのままにしている（L1160「渾名だと何の動物か分からなくなる」）。
 * 通信対戦で抜けて CPU に替わったプレイヤーは、人間だったときの「2P」のまま（`Controller` の `label`。
 * 原型 L3793 は `label` を書き換えない）。
 *
 * 呼び方の決まりはここだけに置き、幕（`RoundBanner.ts`）と通知（`Presenter.ts`）がここを呼ぶ。
 * CPU の呼び名は呼ぶ側が決めて渡す。
 *
 * @throws Error その番号のプレイヤーが一覧にいないとき
 */
export function labelOf(roster: Roster, id: PlayerId, cpuName: string): string {
  const controller = controllerOf(roster, id);
  if (controller.kind === 'human') return controller.label;
  return controller.label ?? cpuName;
}

function controllerOf(roster: Roster, id: PlayerId): Controller {
  const controller = roster[id];
  if (controller === undefined) throw new Error(`プレイヤー ${id} が名札の一覧にいない`);
  return controller;
}

/**
 * 1台の試合の名札の一覧。人間が先（1P・2P）、CPU があと（1体目から）。
 *
 * 「あなた」の印は付けない。1台を囲んでいる全員が同じ画面を見ている。
 *
 * @param humans 人間の数
 * @param cpuLevels CPU の強さ。1体目から順に、CPU の数だけ
 */
export function localRoster(humans: number, cpuLevels: readonly CpuLevelKey[]): Roster {
  return [
    ...Array.from({ length: humans }, (_, index): Controller => ({
      kind: 'human',
      label: numberedName(index as PlayerId),
      local: false,
    })),
    ...cpuLevels.map((level, index): Controller => ({ kind: 'cpu', number: index + 1, level })),
  ];
}

/**
 * 通信対戦の名札の一覧。
 *
 * 人間は番号（「1P」…）。始めた時点でつながっていなかった枠は CPU で、CPU の番号はその枠どうしの中で
 * 前から数える（原型の `setupPlayersLan` の `cpuIdx`。L1268）。途中で抜けて CPU に替わったプレイヤーは、
 * 名札の札が「CPU1」になる（原型は替わったプレイヤーの `cpuIdx` を人間のときの 0 のまま CPU にする。
 * L3793）が、入れ替わりの通知（原型 L2354）での呼び方は人間だったときの「2P」のまま（`Controller` の
 * `label`。原型は `label` を書き換えない）。強さはどれも、試合で実際に使う強さ（設定の枠ごとの強さ。
 * `net/lanCpu.ts` と同じ値）。Python 版の `hud/roster.py` の `lan_roster` と同じ番号の付け方。
 *
 * @param players 試合にいるプレイヤー（プレイヤー番号の順）
 * @param humans 試合を始めたときに人間が操作していたプレイヤー
 * @param local この端末で操作しているプレイヤー
 * @param replaced 抜けて CPU に替わったプレイヤー（`humans` のうち）
 * @param cpuLevelOf そのプレイヤーを受け持つ CPU の強さ
 */
export function lanRoster(
  players: readonly PlayerId[],
  humans: readonly PlayerId[],
  local: PlayerId,
  replaced: readonly PlayerId[],
  cpuLevelOf: (id: PlayerId) => CpuLevelKey,
): Roster {
  let cpus = 0;
  return players.map((id): Controller => {
    const level = cpuLevelOf(id);
    if (!humans.includes(id)) {
      cpus += 1;
      return { kind: 'cpu', number: cpus, level };
    }
    if (replaced.includes(id)) return { kind: 'cpu', number: 1, level, label: numberedName(id) };
    return { kind: 'human', label: numberedName(id), local: id === local };
  });
}
