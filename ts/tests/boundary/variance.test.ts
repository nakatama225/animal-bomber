import { describe, expect, it } from 'vitest';

import type { CpuBehavior } from '../../src/ai/CpuBehavior.js';
import type { CpuContext } from '../../src/ai/CpuContext.js';
import type { Ability } from '../../src/domain/abilities/Ability.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import type { InputSource } from '../../src/domain/input/InputSource.js';
import { IDLE_INPUT } from '../../src/domain/input/PlayerInput.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';

/**
 * 窓口の引数を、実装の側で狭められないこと。
 *
 * interface の関数を `next(world): …`（メソッドの形）で書くと、TS は引数の型の向きを
 * 検査しない。「特定の状態のときしか受け取れない判断」のように引数を狭めた実装を
 * 渡しても型エラーにならず、その前提の外の値が来たときに、実行して初めて壊れる。
 *
 * そこで interface の関数は `next: (world) => …` の形で書き、lint で強制している
 * （`eslint.config.js` の `method-signature-style`）。ここでは、その結果として
 * 引数を狭めた実装が型エラーになることを確かめる。
 *
 * ⚠️ 本体は型の検査（`tsc --noEmit`）。`@ts-expect-error` の行でエラーが出なくなると
 * （interface をメソッドの形に戻すと）、tsc が「使われていない `@ts-expect-error`」として落ちる。
 * 実行時の `expect` は、組み立てた値が使えることを見ているだけ。
 *
 * ⚠️ 狭めた型は、元の型に項目を足したもの（`元の型 & { … }`）で作る。元の型と無関係な型だと、
 * メソッドの形でもエラーになるので、どちらの形で書いたかを区別できない。
 */

/** 盤面に項目を1つ足した型。元の盤面は、この型の値として使えない。 */
type NarrowWorld = Readonly<WorldState> & { readonly extra: number };
type NarrowContext = CpuContext & { readonly extra: number };
type NarrowPlayer = PlayerState & { readonly extra: number };

describe('窓口の引数を、実装の側で狭められない', () => {
  it('入力を返す窓口（InputSource）', () => {
    const same = { playerId: 0 as const, next: (_world: Readonly<WorldState>) => IDLE_INPUT };
    const narrowed = { playerId: 0 as const, next: (_world: NarrowWorld) => IDLE_INPUT };

    const accepted: InputSource = same;
    // @ts-expect-error 狭めた盤面しか受け取れない窓口は、InputSource として渡せない
    const rejected: InputSource = narrowed;

    expect([accepted, rejected]).toEqual([same, narrowed]);
  });

  it('CPU の判断の規則（CpuBehavior）', () => {
    const same = { name: 'same', decide: (_ctx: CpuContext) => null };
    const narrowed = { name: 'narrowed', decide: (_ctx: NarrowContext) => null };

    const accepted: CpuBehavior = same;
    // @ts-expect-error 狭めた状況しか受け取れない規則は、CpuBehavior として渡せない
    const rejected: CpuBehavior = narrowed;

    expect([accepted.name, rejected.name]).toEqual(['same', 'narrowed']);
  });

  it('動物の能力（Ability）', () => {
    const base = abilityOf('rabbit');
    const noAction = () => ({ action: null, events: [] });
    const same = { ...base, onTap: (_world: WorldState, _player: PlayerState) => noAction() };
    const narrowed = { ...base, onTap: (_world: WorldState, _player: NarrowPlayer) => noAction() };

    const accepted: Ability = same;
    // @ts-expect-error 狭めたプレイヤーしか受け取れない技は、Ability として渡せない
    const rejected: Ability = narrowed;

    expect([accepted.key, rejected.key]).toEqual([base.key, base.key]);
  });
});
