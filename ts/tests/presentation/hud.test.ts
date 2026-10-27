import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { BurntTongueActor } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitAction, PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { cellOf } from '../../src/domain/core/Coord.js';
import { secondsToTicks, tick } from '../../src/domain/core/Tick.js';
import { IdleInputSource } from '../../src/domain/input/InputSource.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { EFFECT_KINDS } from '../../src/domain/state/EffectBag.js';
import { OUT } from '../../src/domain/state/Life.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Countdown } from '../../src/presentation/audio/Countdown.js';
import type { SoundName } from '../../src/presentation/audio/SoundBank.js';
import { formatSeconds } from '../../src/presentation/menu/choices.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { RoundBanner } from '../../src/presentation/hud/RoundBanner.js';
import { labelOf, lanRoster, localRoster, tagOf, takenOver, type Roster } from '../../src/presentation/hud/roster.js';
import {
  CLOCK_CAPTION,
  describeClock,
  describePlayers,
  hearts,
  type HudSource,
} from '../../src/presentation/hud/scoreboard.js';
import { grantSpecial } from '../helpers.js';

const ROSTER: Roster = [
  { kind: 'human', label: '1P', local: false },
  { kind: 'cpu', number: 1, level: 'hard' },
];

const HOLE = '\u{1F573}\uFE0F';
const PICK = '\u26CF\uFE0F';

function game(
  overrides: Partial<ReturnType<typeof defaultMatchConfig>> = {},
  animals: string[] = ['rabbit', 'elephant'],
): GameSession {
  const session = new GameSession({ ...defaultMatchConfig(5, animals), ...overrides });
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

describe('名札の札（Python 版の hud/roster.py と同じ）', () => {
  it('人間は番号（この端末のプレイヤーにも「あなた」を付けない）、CPU は何体目かと強さ（原型 L5506-5508）', () => {
    const roster: Roster = [...ROSTER, { kind: 'human', label: '3P', local: true }];
    expect([0, 1, 2].map((id) => tagOf(roster, id as 0 | 1 | 2))).toEqual(['1P', 'CPU1・つよい', '3P']);
  });

  it('1台の試合は、人間が先（1P・2P）で、CPU は1体目から数える', () => {
    const roster = localRoster(2, ['oni', 'easy']);
    expect([0, 1, 2, 3].map((id) => tagOf(roster, id as 0 | 1 | 2 | 3))).toEqual([
      '1P',
      '2P',
      'CPU1・おに',
      'CPU2・よわい',
    ]);
  });

  it('原型の label の呼び方は、人間は番号、CPU は渡した名前（動物の名前）', () => {
    expect(labelOf(ROSTER, 0, 'うさぎ')).toBe('1P');
    expect(labelOf(ROSTER, 1, 'ぞう')).toBe('ぞう');
  });

  it('通信対戦では、始めたときにいなかった枠を前から CPU1・CPU2 と数え、抜けて替わった枠は CPU1 で、呼び方は元の番号のまま', () => {
    // 4人の枠のうち 0・1・3 が人間で始め、1 が抜けて CPU に替わった（原型 L1268・L3793）。
    const roster = lanRoster([0, 1, 2, 3], [0, 1, 3], 3, [1], (id) => (id === 1 ? 'easy' : 'oni'));
    expect(roster).toEqual([
      { kind: 'human', label: '1P', local: false },
      { kind: 'cpu', number: 1, level: 'easy', label: '2P' },
      { kind: 'cpu', number: 1, level: 'oni' },
      { kind: 'human', label: '4P', local: true },
    ]);
    expect([0, 1, 2, 3].map((id) => tagOf(roster, id as 0 | 1 | 2 | 3))).toEqual([
      '1P',
      'CPU1・よわい',
      'CPU1・おに',
      '4P',
    ]);
    expect(labelOf(roster, 1, 'ぞう')).toBe('2P');
    expect(labelOf(roster, 2, 'きつね')).toBe('きつね');
  });

  it('通信対戦で始めたときにいなかった枠が2つなら、CPU1・CPU2 と数える', () => {
    const roster = lanRoster([0, 1, 2, 3], [0, 2], 0, [], () => 'normal');
    expect([1, 3].map((id) => tagOf(roster, id as 1 | 3))).toEqual(['CPU1・ふつう', 'CPU2・ふつう']);
  });

  it('CPU が引き継いだプレイヤーは、前の一覧で人間・いまの一覧で CPU のプレイヤーだけ（始めから CPU の枠は含めない）', () => {
    const before = lanRoster([0, 1, 2, 3], [0, 1, 3], 0, [], () => 'normal');
    const after = lanRoster([0, 1, 2, 3], [0, 1, 3], 0, [1, 3], () => 'normal');
    expect(takenOver(before, after)).toEqual([1, 3]);
    expect(takenOver(after, after)).toEqual([]);
    expect(takenOver(before, before)).toEqual([]);
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

  it('上の行はラウンドと先取数を全角の空白でつなぎ、下の行は延長戦でも TIME（原型 L5546・L520）', () => {
    const session = game({ winsToTake: 5 });
    const clock = describeClock(hudOf(session));
    expect(clock.heading).toBe('ROUND 1\u30005勝先取');
    expect(clock.heading).not.toContain(' 5');
    expect(clock.heading).not.toContain('・');
    expect(CLOCK_CAPTION).toBe('TIME');
    session.world.suddenDeath = true;
    expect(describeClock(hudOf(session))).not.toHaveProperty('suddenDeath');
  });

  it('決着のあとの待ちの間は、決まったばかりのラウンドの番号を出す', () => {
    // 試合の側は、決まった tick に番号を次へ進めている。待ちの間の盤面は前のラウンドのもの。
    const session = game({ winsToTake: 3 });
    session.world.players[1]!.life = OUT;
    session.tick();
    expect(session.betweenRounds).toBe(true);
    expect(session.match.round).toBe(2);
    expect(describeClock(hudOf(session)).round).toBe(1);
    expect(describeClock(hudOf(session)).heading).toBe('ROUND 1\u30003勝先取');
  });

  it('秒を「分:秒」にし、秒は2桁に0で埋める', () => {
    expect([0, 1, 9, 10, 59, 60, 61, 180, 600].map(formatSeconds)).toEqual([
      '0:00',
      '0:01',
      '0:09',
      '0:10',
      '0:59',
      '1:00',
      '1:01',
      '3:00',
      '10:00',
    ]);
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

  it('延長戦では、延長戦の体力が上限（原型の enterSuddenDeath L4455 は上限も 1 にする）', () => {
    const session = game({ startingHp: [2, 2] });
    session.world.suddenDeath = true;
    for (const player of session.world.players) player.hp = 2;
    const [rabbit, elephant] = describePlayers(hudOf(session));
    expect([rabbit?.condition, elephant?.condition]).toEqual(['❤️', '❤️']);
  });
});

describe('名札の中身（原型 L5497-5538。文は Python 版の hud/scoreboard.py と同じ）', () => {
  it('人間は番号、CPU は何体目かと強さの札。動物の絵文字と名前', () => {
    const [human, cpu] = describePlayers(hudOf(game()));
    expect(human?.tags).toEqual([{ text: '1P', style: 'human' }]);
    expect(cpu?.tags).toEqual([{ text: 'CPU1・つよい', style: 'cpu' }]);
    expect([human?.emoji, human?.name]).toEqual(['🐰', 'うさぎ']);
  });

  it('退場したプレイヤーにも、残っているとくぎと状態を出す（原型は状態を見ずに組む）', () => {
    // 残り1分を切ってから倒れたプレイヤーは退場するだけで、とくぎの回数や状態は試合の側に残る（原型の kill も消さない）。
    const session = game();
    const rabbit = session.world.players[0]!;
    grantSpecial(rabbit, 2);
    rabbit.effects.add('slow', tick(60), tick(600));
    rabbit.life = OUT;
    expect(describePlayers(hudOf(session))[0]).toMatchObject({
      condition: '💀 退場',
      effects: ['💩うんこポロポロ×2', '🐌超スロー'],
    });
  });

  it('勝ち星・盤面にいないわけ・かかっている状態を出す', () => {
    const session = game({ winsToTake: 3 });
    session.match.wins.set(0, 2);
    const rabbit = session.world.players[0]!;
    grantSpecial(rabbit, 2);
    rabbit.effects.add('slow', tick(60), tick(600));
    session.world.players[1]!.life = OUT;

    const [first, second] = describePlayers(hudOf(session));
    expect(first).toMatchObject({ stars: '★★☆' });
    expect(first?.tags.map((tag) => tag.text)).toEqual(['1P']);
    expect(first?.effects).toEqual(['💩うんこポロポロ×2', '🐌超スロー']);
    expect(second).toMatchObject({ state: 'out', condition: '💀 退場', stars: '☆☆☆' });
  });

  it('外周にいる間は「葱ボン（場外）」と出し、「葱ボン」の札を足す（原型 L5502-5509）', () => {
    const session = game();
    session.world.players[0]!.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    const [card, playing] = describePlayers(hudOf(session));
    expect(card?.condition).toBe('🌿 葱ボン（場外）');
    expect(card?.tags).toEqual([
      { text: '1P', style: 'human' },
      { text: '葱ボン', style: 'negibon' },
    ]);
    expect(card?.condition).not.toContain('外周');
    expect(playing?.tags.map((tag) => tag.text)).not.toContain('葱ボン');
  });

  it('外周から戻って回数だけが残っている（持っている印が外れている）ときは、とくぎを出さない（原型の名札 L5512 は p.chicken で見る）', () => {
    // 原型の toNegibon（L2255）は chicken だけを消し、回数は残す。残った回数は使えないので、名札にも出ない。
    // 対照は上の「勝ち星・…」（印があれば「×2」まで出る）。
    const session = game();
    const rabbit = session.world.players[0]!;
    grantSpecial(rabbit, 2);
    rabbit.hasSpecial = false;
    rabbit.effects.add('slow', tick(60), tick(600));
    expect(describePlayers(hudOf(session))[0]?.effects).toEqual(['🐌超スロー']);
  });

  it('焼けた舌は、いま伸ばせる長さと次に戻るまでの秒数を出す（原型の名札と同じ形）', () => {
    // 盤面には描くものが無いので、名札に出さないと短くなったことが分からない。
    const session = game({}, ['frog', 'elephant']);
    const burnt = new BurntTongueActor(0, 3);
    for (let i = 0; i < 130; i += 1) burnt.tick();
    session.world.actors.push(burnt);
    const [frog, elephant] = describePlayers(hudOf(session));
    expect(frog?.effects).toEqual(['👅🔥舌 3/10マス（8秒で+1）']);
    expect(elephant?.effects).toEqual([]);
  });

  it('状態の並びと字は原型と同じ：とくぎ・ポロポロ・舌・焼けた舌・涙・すべり・うんこの6つ（原型 L5511-5527）', () => {
    const session = game({}, ['frog', 'elephant']);
    const frog = session.world.players[0]!;
    grantSpecial(frog, 2);
    for (const kind of EFFECT_KINDS) if (kind !== 'pitfall' && kind !== 'leap') frog.effects.set(kind, tick(60));
    frog.action = new TongueAction({ col: 1, row: 1 }, 'right');
    session.world.actors.push(new BurntTongueActor(0, 9));
    expect(describePlayers(hudOf(session))[0]?.effects).toEqual([
      '🟢粘膜爆弾×2',
      '💩ポロポロ中',
      '👅舌',
      '👅🔥舌 9/10マス（10秒で+1）',
      '😭涙',
      '🍌すべり',
      '🔄そうさ反転',
      '🚫爆弾おけない',
      '💨とまれない',
      '🕯️爆風1マス',
      '🎰勝手に設置',
      '🐌超スロー',
    ]);
  });

  it('掘っている・はまっている（残り秒は小数1桁）・しかけた穴の数（原型 L5518-5524）', () => {
    const session = game({}, ['mole', 'elephant']);
    const [mole] = session.world.players;
    mole!.action = new PitAction({ col: 1, row: 1 });
    mole!.effects.add('pitfall', tick(171), tick(180));
    for (const col of [3, 5]) session.world.actors.push(new PitActor({ col, row: 1 }, 0));
    session.world.actors.push(new PitActor({ col: 7, row: 1 }, 1));
    const [moleCard, elephantCard] = describePlayers(hudOf(session));
    expect(moleCard?.effects).toEqual([`${PICK}穴をほってる`, `${HOLE}落とし穴 2.9秒`, `${HOLE}しかけた穴 2個`]);
    expect(elephantCard?.effects).toEqual([`${HOLE}しかけた穴 1個`]);
    // 跳び上がり（leap）は名札に出さない（原型 L5511-5527 に無い）。
    mole!.effects.add('leap', tick(30), tick(60));
    expect(describePlayers(hudOf(session))[0]?.effects.join('')).not.toContain('🦊');
  });

  it('落とし穴の残り秒は、原型の toFixed(1) と同じく秒の小数を丸める', () => {
    const session = game({}, ['rabbit', 'elephant']);
    const rabbit = session.world.players[0]!;
    const shown = (left: number): string | undefined => {
      rabbit.effects.clear('pitfall');
      rabbit.effects.add('pitfall', tick(left), tick(180));
      return describePlayers(hudOf(session))[0]?.effects[0];
    };
    expect([180, 179, 3, 1].map(shown)).toEqual([
      `${HOLE}落とし穴 3.0秒`,
      `${HOLE}落とし穴 3.0秒`,
      `${HOLE}落とし穴 0.1秒`,
      `${HOLE}落とし穴 0.0秒`,
    ]);
  });

  it('爆弾・火力・靴を3つに分けて出す（原型は3つの span）', () => {
    const session = game();
    const rabbit = session.world.players[0]!;
    rabbit.maxBombs = 4;
    rabbit.shoes = 2;
    const [first] = describePlayers(hudOf(session));
    expect(first?.stats).toEqual(['💣4', `🔥${rabbit.power}`, '👟2']);
  });
});

describe('ラウンドの間の幕（原型の endGame L4467-4511。文は Python 版の hud/banner.py と同じ）', () => {
  it('勝ちの幕は、題に動物の名前だけを出し、区切りは全角の空白。次の盤面に替わったら消える', () => {
    const session = game({ winsToTake: 3 });
    const banner = new RoundBanner();
    session.world.players[1]!.life = OUT;
    step(session, banner);

    const shown = banner.current(session.world);
    expect(shown).toEqual({
      emoji: '🐰',
      title: 'ラウンド1\u3000うさぎの かち',
      summary: '3勝先取まで あと 2勝',
      board: '🐰1\u3000🐘0',
      note: null,
      button: 'つぎのラウンド ▶',
      final: false,
    });
    expect(shown?.title).not.toContain('1P');

    while (session.betweenRounds) step(session, banner);
    expect(banner.current(session.world)).toBeNull();
  });

  it('ひきわけの幕は、わけと残ったプレイヤーを出す。だれもいなければ「同時にやられた」（原型 L4502-4504）', () => {
    const timeUp = game({ winsToTake: 3 });
    const banner = new RoundBanner();
    banner.onEvents([{ type: 'roundEnded', round: 2, winner: null }], hudOf(timeUp));
    expect(banner.current(timeUp.world)).toEqual({
      emoji: '🤝',
      title: 'ラウンド2\u3000ひきわけ',
      summary: '時間切れ\u3000のこり: うさぎ・ぞう',
      board: '🐰0\u3000🐘0',
      note: null,
      button: 'つぎのラウンド ▶',
      final: false,
    });

    const allDown = game({ winsToTake: 3 });
    allDown.world.suddenDeath = true;
    for (const player of allDown.world.players) player.life = OUT;
    const down = new RoundBanner();
    down.onEvents([{ type: 'roundEnded', round: 1, winner: null }], hudOf(allDown));
    // 延長戦のあとでも同じ形（延長戦の行は添えない）。
    expect(down.current(allDown.world)).toMatchObject({ summary: '同時にやられた', note: null });
  });

  it('延長戦で決まったラウンドの幕にだけ「⚡サドンデス決着」を添え、優勝の幕には添えない（原型 L4497・L4487-4488）', () => {
    const round = new RoundBanner();
    const suddenRound = game({ winsToTake: 3 });
    suddenRound.world.suddenDeath = true;
    round.onEvents([{ type: 'roundEnded', round: 1, winner: 0 }], hudOf(suddenRound));
    expect(round.current(suddenRound.world)?.note).toBe('⚡サドンデス決着');

    const session = game({ winsToTake: 1 });
    session.world.suddenDeath = true;
    session.world.players[1]!.life = OUT;
    const banner = new RoundBanner();
    step(session, banner);
    expect(banner.current(session.world)).toMatchObject({ final: true, note: null });
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

  it('試合が決まった幕は消えない。題は「動物の名前（CPU か番号） 優勝！」', () => {
    const session = game({ winsToTake: 1 });
    const banner = new RoundBanner();
    session.world.players[0]!.life = OUT;
    step(session, banner);
    step(session, banner);

    expect(banner.current(session.world)).toEqual({
      emoji: '🏆',
      title: 'ぞう（CPU） 優勝！',
      summary: '1勝先取を達成（全1ラウンド）',
      board: '🐰0\u3000🐘1',
      note: null,
      button: 'もういっかい',
      final: true,
    });
    // 試合が決まったあとは盤面が作り直されないが、別の盤面を渡されても消さない。
    // 「もういっかい」を押すまで結果を見せておくため。
    expect(banner.current(game().world)).toMatchObject({ final: true });
  });

  it('人間が優勝したら、題の括弧に番号を出す', () => {
    const session = game({ winsToTake: 1 });
    const banner = new RoundBanner();
    session.world.players[1]!.life = OUT;
    step(session, banner);
    expect(banner.current(session.world)?.title).toBe('うさぎ（1P） 優勝！');
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

  it('残り0秒でも鳴らす（原型 L4291-4293 の s>=0）', () => {
    const session = game({ roundLimit: secondsToTicks(2) });
    const { played, countdown } = counter();
    for (let i = 0; i <= secondsToTicks(2); i += 1) {
      session.world.now = tick(i);
      countdown.observe(session.world);
    }
    expect(played).toEqual(['tick', 'tick', 'tick']);
  });

  it('延長戦に入った tick も、延ばす前の時刻で数えて0秒を鳴らす（原型は延長戦に入る前に鳴らす）', () => {
    const session = game({ roundLimit: secondsToTicks(1) });
    const { played, countdown } = counter();
    const world: WorldState = session.world;
    world.now = tick(1);
    countdown.observe(world);
    expect(played).toEqual(['tick']);
    // 時間切れの tick に延長戦へ入り、時間切れの時刻が 60 秒先へ移った。
    world.now = tick(secondsToTicks(1));
    world.endsAt = tick(world.now + secondsToTicks(60));
    countdown.observe(world);
    expect(played).toEqual(['tick', 'tick']);
    // 次の tick からは延ばしたあとの時刻で数える（残り 60 秒なので鳴らない）。
    world.now = tick(world.now + 1);
    countdown.observe(world);
    expect(played).toEqual(['tick', 'tick']);
  });

  it('止まった盤面では鳴らし続けない', () => {
    const session = game({ roundLimit: secondsToTicks(5) });
    const { played, countdown } = counter();
    for (let i = 0; i < 30; i += 1) countdown.observe(session.world);
    expect(played).toEqual(['tick']);
  });

  it('盤面が替わったら、新しい盤面の時間切れの時刻で数える（延長戦で延びた前の盤面の時刻を持ち越さない）', () => {
    const { played, countdown } = counter();
    const first = game({ roundLimit: secondsToTicks(10) });
    // 延長戦に入って、時間切れの時刻が 60 秒先へ移った盤面（残り 70 秒なので鳴らない）。
    first.world.endsAt = tick(first.world.endsAt + secondsToTicks(60));
    countdown.observe(first.world);
    expect(played).toEqual([]);
    const second = game({ roundLimit: secondsToTicks(10) });
    countdown.observe(second.world);
    expect(played).toEqual(['tick']);
  });

  describe('延長戦（Python 版の test_countdown.py と同じ場面）', () => {
    function sessionOf(roundLimit: number, suddenDeath = true): GameSession {
      const session = new GameSession({ ...defaultMatchConfig(11, ['rabbit', 'elephant']), roundLimit: tick(roundLimit), suddenDeath });
      for (const player of session.world.players) session.attach(new IdleInputSource(player.id));
      return session;
    }

    /**
     * 画面のループ（`Shell` の `#step`）と同じく、1 tick 進めるたびに、イベントを進める前の盤面と一緒に `Presenter` へ、
     * 進めたあとの盤面を秒読みへ渡す。鳴らした音を、試合の始めから数えた tick ごとに控える。
     */
    function listener(): {
      run: (session: GameSession, count: number) => void;
      rang: ReadonlyMap<number, readonly SoundName[]>;
      countdownTicks: () => number[];
    } {
      const rang = new Map<number, SoundName[]>();
      let at = 0;
      const sounds = {
        play: (name: SoundName): void => {
          rang.set(at, [...(rang.get(at) ?? []), name]);
        },
      };
      const countdown = new Countdown(sounds);
      const presenter = new Presenter(sounds);
      return {
        rang,
        run: (session, count) => {
          for (let i = 0; i < count; i += 1) {
            at += 1;
            const before = session.world;
            presenter.consume(session.tick(), before);
            countdown.observe(session.world);
          }
        },
        countdownTicks: () => [...rang].filter(([, names]) => names.includes('tick')).map(([at]) => at),
      };
    }

    /** その tick に鳴らした音（同じ tick の中の順は見ない）。 */
    const sortedAt = (heard: ReturnType<typeof listener>, at: number): SoundName[] => [...(heard.rang.get(at) ?? [])].sort();

    it('時間切れで延長戦に入る tick に 0 秒を鳴らし、延長戦の残り 10 秒からまた鳴らす。延長戦の時間切れにも 0 秒を鳴らす', () => {
      // 制限時間 12 秒（720 tick）。延長戦は 60 秒なので、残り 10 秒は 3720 tick 目、時間切れは 4320 tick 目。
      const session = sessionOf(720);
      const heard = listener();
      heard.run(session, 4320);
      expect(session.world.suddenDeath).toBe(true);
      const first = Array.from({ length: 11 }, (_, k) => 120 + 60 * k);
      const later = Array.from({ length: 11 }, (_, k) => 3720 + 60 * k);
      expect(heard.countdownTicks()).toEqual([...first, ...later]);
      expect(sortedAt(heard, 720)).toEqual(['sudden', 'tick']);
      expect(sortedAt(heard, 4320)).toEqual(['draw', 'tick']);
    });

    it('延長戦を切ってあれば、時間切れの tick は 0 秒と引き分けの音', () => {
      const session = sessionOf(720, false);
      const heard = listener();
      heard.run(session, 720);
      expect(sortedAt(heard, 720)).toEqual(['draw', 'tick']);
      expect(session.world.suddenDeath).toBe(false);
    });

    it('残り 10 秒で全員が倒れて延長戦に入ると、延長戦の残り 10 秒は鳴らさない（原型の lastTickSecond は延長戦でも戻らない）', () => {
      // 制限時間 20 秒。残り 10 秒の tick（600 tick 目）に2体とも倒れて延長戦に入り、その tick に 10 秒を鳴らす。
      // 延長戦は 4200 tick 目まで。延長戦の残り 10 秒（3600 tick 目）は覚えている秒と同じなので鳴らさず、9 秒から鳴らす。
      const session = sessionOf(1200);
      const heard = listener();
      heard.run(session, 599);
      expect(heard.countdownTicks()).toEqual([]);
      for (const player of session.world.players) {
        player.hp = 1;
        addBlast(session.world, cellOf(player.position), player.id, true);
      }
      heard.run(session, 3660 - 599);
      expect(session.world.suddenDeath).toBe(true);
      expect(heard.rang.get(600)).toContain('sudden');
      expect(heard.rang.get(600)).toContain('tick');
      expect(heard.countdownTicks()).toEqual([600, 3660]);
    });
  });
});
