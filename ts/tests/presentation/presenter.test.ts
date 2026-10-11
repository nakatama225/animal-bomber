import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { TONGUE_REACH, TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitAction } from '../../src/domain/abilities/mole/PitAction.js';
import { cellOf, centerOf } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { clearBoard, makeWorld, press, sameForAll } from '../helpers.js';

function recorder(): { played: SoundName[]; presenter: Presenter } {
  const played: SoundName[] = [];
  return { played, presenter: new Presenter({ play: (name) => played.push(name) }) };
}

describe('イベントから音へ', () => {
  it('優勝が決まった tick は、ファンファーレだけを鳴らす', () => {
    // ラウンドの終わりの曲と重ねると、どちらも聞き取れない。
    const { played, presenter } = recorder();
    presenter.consume(
      [
        { type: 'roundEnded', round: 3, winner: 0 },
        { type: 'matchEnded', champion: 0 },
      ],
      makeWorld(),
    );
    expect(played).toEqual(['fanfare']);
  });

  it('優勝が決まらないラウンドの終わりでは、ラウンドの音を鳴らす', () => {
    const { played, presenter } = recorder();
    presenter.consume([{ type: 'roundEnded', round: 1, winner: 0 }], makeWorld());
    expect(played).toEqual(['roundEnd']);
  });

  it('技の音は、使った動物で決まる。とくぎはどの動物でも共通の音を先に鳴らす（原型の useSpecial）', () => {
    const { played, presenter } = recorder();
    const world = makeWorld(1, ['rabbit', 'elephant', 'fox', 'mole']);
    presenter.consume(
      [
        { type: 'techniqueUsed', player: 0, special: false },
        { type: 'techniqueUsed', player: 1, special: true },
        { type: 'techniqueUsed', player: 1, special: false },
        { type: 'techniqueUsed', player: 2, special: true },
        { type: 'techniqueUsed', player: 3, special: false },
      ],
      world,
    );
    expect(played).toEqual(['hop', 'special', 'charge', 'snot', 'special', 'foxLeap', 'foxfire']);
  });

  it('技の途中で起きたこと・落とし穴は、原型と同じ専用の音を鳴らす', () => {
    const { played, presenter } = recorder();
    presenter.consume(
      [
        { type: 'techniqueMoment', player: 0, moment: 'tongueCaught' },
        { type: 'techniqueMoment', player: 0, moment: 'pitDug' },
        { type: 'techniqueMoment', player: 0, moment: 'slimeHopped' },
        { type: 'techniqueMoment', player: 0, moment: 'itemsSpat' },
        { type: 'techniqueMoment', player: 0, moment: 'chargeHit' },
        { type: 'techniqueMoment', player: 0, moment: 'foxfireHit' },
        { type: 'effectApplied', target: 1, effect: 'pitfall' },
        { type: 'effectApplied', target: 1, effect: 'stun' },
      ],
      makeWorld(),
    );
    expect(played).toEqual(['tongueCatch', 'pitDone', 'slimeHop', 'spit', 'charge', 'foxfireHit', 'pitFall', 'cry']);
  });
});

describe('技の途中で起きたことを、ルールの層が知らせる', () => {
  // 音を鳴らす側が受け取れるかは上で見た。ここでは、ルールの層がその瞬間に知らせるかを見る。
  it('舌が掴んだ・穴を掘り終えた・跳ね回る爆弾が跳ねた・体当たりが当たった・抱えたものを撒いた・炎が当たった', () => {
    const moments = new Set<string>();
    const collect = (events: readonly SimEvent[]): void => {
      for (const event of events) if (event.type === 'techniqueMoment') moments.add(event.moment);
    };

    // 舌
    {
      const world = makeWorld(5, ['frog', 'rabbit']);
      clearBoard(world);
      world.items = [{ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'fire' }];
      const frog = world.players[0]!;
      frog.position = centerOf({ col: 3, row: 7 });
      frog.facing = 'right';
      const tongue = new TongueAction(cellOf(frog.position), frog.facing, TONGUE_REACH);
      for (let t = 0; t < 60; t += 1) collect(tongue.tick(world, frog).events);
    }
    // 穴
    {
      const world = makeWorld(5, ['mole', 'rabbit']);
      clearBoard(world);
      const mole = world.players[0]!;
      const dig = new PitAction(cellOf(mole.position));
      for (let t = 0; t < 120; t += 1) if (dig.tick(world, mole).done) break;
      collect(dig.finish(world, mole));
    }
    // 跳ね回る爆弾
    {
      const world = makeWorld(5, ['frog', 'rabbit']);
      clearBoard(world);
      const slime = new SlimeBombActor({ col: 9, row: 7 }, world.players[0]!, 5);
      for (let t = 0; t < 60; t += 1) collect(slime.tick(world).events);
    }
    // 体当たり（通り道に相手）と、抱えたものを撒く（通り道にたまねぎ、相手は通り道の外）
    for (const scene of ['hit', 'spit'] as const) {
      const world = makeWorld(5, ['elephant', 'rabbit']);
      clearBoard(world);
      world.items = scene === 'spit' ? [{ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'onion' }] : [];
      const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
      elephant.position = centerOf({ col: 3, row: 7 });
      rabbit.position = centerOf(scene === 'hit' ? { col: 8, row: 7 } : { col: 19, row: 13 });
      rabbit.invulnerableUntil = tick(0);
      elephant.action = new ChargeAction('right');
      const sim = new Simulation();
      for (let t = 0; t < 120; t += 1) collect(sim.step(world, sameForAll(world, press({}))));
    }
    // 炎
    {
      const world = makeWorld(5, ['fox', 'rabbit']);
      clearBoard(world);
      const [fox, rabbit] = world.players as [PlayerState, PlayerState];
      fox.position = centerOf({ col: 3, row: 7 });
      rabbit.position = centerOf({ col: 5, row: 7 });
      rabbit.invulnerableUntil = tick(0);
      const fire = new FoxfireActor(fox.position, fox.id);
      for (let t = 0; t < 40; t += 1) collect(fire.tick(world).events);
    }

    expect([...moments].sort()).toEqual(
      ['chargeHit', 'foxfireHit', 'itemsSpat', 'pitDug', 'slimeHopped', 'tongueCaught'].sort(),
    );
  });
});
