import { describe, expect, it } from 'vitest';

import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { makeWorld } from '../helpers.js';

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

  it('技の音は、使った動物で決まる', () => {
    const { played, presenter } = recorder();
    const world = makeWorld(1, ['rabbit', 'elephant']);
    presenter.consume(
      [
        { type: 'techniqueUsed', player: 0, special: false },
        { type: 'techniqueUsed', player: 1, special: true },
      ],
      world,
    );
    expect(played).toEqual(['hop', 'charge']);
  });
});
