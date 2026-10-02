import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { secondsToTicks, tick } from '../../src/domain/core/Tick.js';
import { IdleInputSource } from '../../src/domain/input/InputSource.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { OUT } from '../../src/domain/state/Life.js';
import { Countdown } from '../../src/presentation/audio/Countdown.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { RoundBanner } from '../../src/presentation/hud/RoundBanner.js';
import { displayName, lanRoster, tagOf, type Roster } from '../../src/presentation/hud/roster.js';
import {
  describeClock,
  describePlayers,
  hearts,
  type HudSource,
} from '../../src/presentation/hud/scoreboard.js';

const ROSTER: Roster = [
  { kind: 'human', label: '1P', local: false },
  { kind: 'cpu', level: 'hard' },
];

function game(overrides: Partial<ReturnType<typeof defaultMatchConfig>> = {}): GameSession {
  const session = new GameSession({ ...defaultMatchConfig(5, ['rabbit', 'elephant']), ...overrides });
  for (const player of session.world.players) session.attach(new IdleInputSource(player.id));
  return session;
}

function hudOf(session: GameSession, roster: Roster = ROSTER): HudSource {
  return {
    world: session.world,
    match: session.match,
    config: session.config,
    roster,
    betweenRounds: session.betweenRounds,
  };
}

/** 1 tick 進め、進める前の盤面と一緒にイベントを幕へ渡す。画面のループと同じ順。 */
function step(session: GameSession, banner: RoundBanner): void {
  const before = hudOf(session);
  banner.onEvents(session.tick(), before);
}

describe('名札', () => {
  it('人間は番号、この端末の人には「あなた」、CPU は強さを出す', () => {
    const roster: Roster = [...ROSTER, { kind: 'human', label: '3P', local: true }];
    expect([0, 1, 2].map((id) => tagOf(roster, id as 0 | 1 | 2))).toEqual(['1P', 'CPU・つよい', '3P（あなた）']);
  });

  it('通知の呼び方は動物の名前を先に出す', () => {
    expect(displayName(ROSTER, 0, 'rabbit')).toBe('うさぎ（1P）');
    expect(displayName(ROSTER, 1, 'elephant')).toBe('ぞう（CPU）');
  });

  it('通信対戦では、抜けて CPU に替わった人を CPU として出す', () => {
    const roster = lanRoster([0, 1, 2, 3], [0, 2], 2, (id) => (id === 1 ? 'easy' : 'oni'));
    expect(roster).toEqual([
      { kind: 'human', label: '1P', local: false },
      { kind: 'cpu', level: 'easy' },
      { kind: 'human', label: '3P', local: true },
      { kind: 'cpu', level: 'oni' },
    ]);
  });
});

describe('時計', () => {
  it('残り時間を分と秒で出し、端数は切り上げる', () => {
    const session = game({ roundLimit: secondsToTicks(90) });
    expect(describeClock(hudOf(session)).time).toBe('1:30');
    session.tick();
    // 1 tick ぶん減っても、切り上げなので 1:30 のまま（0:00 は時間切れの瞬間だけ）。
    expect(describeClock(hudOf(session)).time).toBe('1:30');
  });

  it('残り30秒から目立たせる', () => {
    const session = game({ roundLimit: secondsToTicks(31) });
    expect(describeClock(hudOf(session)).warn).toBe(false);
    session.world.now = tick(secondsToTicks(1));
    expect(describeClock(hudOf(session)).warn).toBe(true);
  });

  it('決着のあとの待ちの間は、決まったばかりのラウンドの番号を出す', () => {
    // 試合の側は、決まった tick に番号を次へ進めている。待ちの間の盤面は前のラウンドのもの。
    const session = game({ winsToTake: 3 });
    session.world.players[1]!.life = OUT;
    session.tick();
    expect(session.betweenRounds).toBe(true);
    expect(session.match.round).toBe(2);
    expect(describeClock(hudOf(session)).round).toBe(1);
  });
});

describe('ハート', () => {
  it.each([
    [6, 6, '❤️❤️❤️'],
    [5, 6, '❤️❤️💔'],
    [2, 6, '❤️🖤🖤'],
    [1, 8, '💔🖤🖤🖤'],
    [0, 6, '🖤🖤🖤'],
  ])('体力 %i・始まり %i → %s', (hp, max, expected) => {
    expect(hearts(hp, max)).toBe(expected);
  });

  it('始まりの体力は、設定の値に動物ごとの上乗せを足したもの', () => {
    const session = game({ startingHp: [2, 2] });
    session.world.players[1]!.hp = 2;
    const [rabbit, elephant] = describePlayers(hudOf(session));
    expect(rabbit?.condition).toBe('❤️');
    // ぞうは爆風1回ぶん多く始まる。まだ1回も当たっていなくても、減ったぶんに見える。
    expect(elephant?.condition).toBe('❤️🖤');
  });
});

describe('名札の中身', () => {
  it('退場した人には、残っているとくぎや状態を出さない', () => {
    // 残り1分を切ってから倒れた人は退場するだけで、とくぎの回数や状態は試合の側に残る。
    const session = game();
    const rabbit = session.world.players[0]!;
    rabbit.specialCharges = 2;
    rabbit.effects.add('slow', tick(60), tick(600));
    rabbit.life = OUT;
    expect(describePlayers(hudOf(session))[0]).toMatchObject({ condition: '💀 退場', effects: [] });
  });

  it('勝ち星・盤面にいないわけ・かかっている状態を出す', () => {
    const session = game({ winsToTake: 3 });
    session.match.wins.set(0, 2);
    const rabbit = session.world.players[0]!;
    rabbit.specialCharges = 2;
    rabbit.effects.add('slow', tick(60), tick(600));
    session.world.players[1]!.life = OUT;

    const [first, second] = describePlayers(hudOf(session));
    expect(first).toMatchObject({ stars: '★★☆', tag: '1P' });
    expect(first?.effects).toEqual(['💩うんこポロポロ×2', '🐌超スロー']);
    expect(second).toMatchObject({ state: 'out', condition: '💀 退場', stars: '☆☆☆' });
  });
});

describe('ラウンドの間の幕', () => {
  it('決着で出て、次の盤面に替わったら消える', () => {
    const session = game({ winsToTake: 3 });
    const banner = new RoundBanner();
    session.world.players[1]!.life = OUT;
    step(session, banner);

    const shown = banner.current(session.world);
    expect(shown).toMatchObject({ title: 'ラウンド1 うさぎ（1P）の かち', final: false });
    expect(shown?.lines).toEqual(['3勝先取まで あと 2勝', '🐰1  🐘0']);

    while (session.betweenRounds) step(session, banner);
    expect(banner.current(session.world)).toBeNull();
  });

  it('引き分けの幕には番号と勝ち数を出し、延長戦のあとならそう添える', () => {
    const session = game({ winsToTake: 3 });
    const banner = new RoundBanner();
    session.world.suddenDeath = true;
    banner.onEvents([{ type: 'roundEnded', round: 2, winner: null }], hudOf(session));
    expect(banner.current(session.world)).toMatchObject({
      emoji: '🤝',
      title: 'ラウンド2 ひきわけ',
      lines: ['🐰0  🐘0', '⚡サドンデスでも決まらなかった'],
    });
  });

  it('延長戦で決まったら、ラウンドの幕にも試合が決まった幕にもそう添える', () => {
    const session = game({ winsToTake: 1 });
    session.world.suddenDeath = true;
    session.world.players[1]!.life = OUT;
    const banner = new RoundBanner();
    step(session, banner);
    expect(banner.current(session.world)?.lines.at(-1)).toBe('⚡サドンデス決着');

    const round = new RoundBanner();
    const suddenRound = game({ winsToTake: 3 });
    suddenRound.world.suddenDeath = true;
    round.onEvents([{ type: 'roundEnded', round: 1, winner: 0 }], hudOf(suddenRound));
    expect(round.current(suddenRound.world)?.lines.at(-1)).toBe('⚡サドンデス決着');
  });

  it('待ちの間は出たまま', () => {
    const session = game({ winsToTake: 3 });
    const banner = new RoundBanner();
    session.world.players[1]!.life = OUT;
    step(session, banner);
    step(session, banner);
    expect(session.betweenRounds).toBe(true);
    expect(banner.current(session.world)).not.toBeNull();
  });

  it('試合が決まった幕は消えない', () => {
    const session = game({ winsToTake: 1 });
    const banner = new RoundBanner();
    session.world.players[0]!.life = OUT;
    step(session, banner);
    step(session, banner);

    expect(banner.current(session.world)).toMatchObject({
      emoji: '🏆',
      title: 'ぞう（CPU） 優勝！',
      lines: ['1勝先取を達成（全1ラウンド）', '🐰0  🐘1'],
      final: true,
    });
    // 試合が決まったあとは盤面が作り直されないが、別の盤面を渡されても消さない。
    // 「もういっかい」を押すまで結果を見せておくため。
    expect(banner.current(game().world)).toMatchObject({ final: true });
  });
});

describe('秒読み', () => {
  function counter(): { played: SoundName[]; countdown: Countdown } {
    const played: SoundName[] = [];
    return { played, countdown: new Countdown({ play: (name) => played.push(name) }) };
  }

  it('残り10秒から1秒ごとに1回だけ鳴らす', () => {
    const session = game({ roundLimit: secondsToTicks(12) });
    const { played, countdown } = counter();
    for (let i = 0; i < secondsToTicks(12); i += 1) {
      session.world.now = tick(i);
      countdown.observe(session.world);
    }
    // 残り 10, 9, …, 1 の10回（0 秒になる tick はまだ来ていない）。
    expect(played).toEqual(Array.from({ length: 10 }, () => 'tick'));
  });

  it('次のラウンドでは、前のラウンドと同じ秒でも鳴らす', () => {
    // 秒の値だけを覚えていると、残り10秒で決まった次のラウンドの残り10秒で鳴らない。
    const { played, countdown } = counter();
    const first = game({ roundLimit: secondsToTicks(10) });
    countdown.observe(first.world);
    const second = game({ roundLimit: secondsToTicks(10) });
    countdown.observe(second.world);
    expect(played).toEqual(['tick', 'tick']);
  });

  it('残り0秒では鳴らさない（ラウンドが決まる音と重ねない）', () => {
    const session = game({ roundLimit: secondsToTicks(2) });
    const { played, countdown } = counter();
    for (let i = 0; i <= secondsToTicks(2); i += 1) {
      session.world.now = tick(i);
      countdown.observe(session.world);
    }
    expect(played).toEqual(['tick', 'tick']);
  });

  it('止まった盤面では鳴らし続けない', () => {
    const session = game({ roundLimit: secondsToTicks(5) });
    const { played, countdown } = counter();
    for (let i = 0; i < 30; i += 1) countdown.observe(session.world);
    expect(played).toEqual(['tick']);
  });
});

describe('通知', () => {
  it('状態がかかったら、名前と状態の呼び方で知らせる', () => {
    const shown: string[] = [];
    const session = game();
    const presenter = new Presenter(
      { play: () => undefined },
      { show: (message) => shown.push(message) },
      (id, world) => displayName(ROSTER, id, world.players[id]!.animal),
    );
    presenter.consume([{ type: 'effectApplied', target: 1, effect: 'reverse' }], session.world);
    expect(shown).toEqual(['ぞう（CPU）：🔄そうさ反転']);
  });

  it('ラウンドと試合の決着は通知に出さない（幕が出す）', () => {
    const shown: string[] = [];
    const presenter = new Presenter({ play: () => undefined }, { show: (message) => shown.push(message) });
    presenter.consume([{ type: 'roundEnded', round: 1, winner: 0 }], game().world);
    presenter.consume([{ type: 'roundEnded', round: 2, winner: null }], game().world);
    presenter.consume(
      [
        { type: 'roundEnded', round: 3, winner: 0 },
        { type: 'matchEnded', champion: 0 },
      ],
      game().world,
    );
    expect(shown).toEqual([]);
  });
});
