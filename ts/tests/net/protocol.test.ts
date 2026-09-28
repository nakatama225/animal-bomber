import { describe, expect, expectTypeOf, it } from 'vitest';

import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import {
  cpuLevelOf,
  parseLanSettings,
  parseRelayMessage,
  ProtocolError,
  type FROM_PEER,
  type FROM_RELAY,
  type HashReport,
  type LanSettings,
  type PeerMessage,
  type RelayMessage,
  type REPORT_FIELDS,
} from '../../src/net/protocol.js';

/** 種類 `K` のメッセージの、`t` 以外の項目名。 */
type FieldsOf<U extends { t: string }, K extends U['t']> = Exclude<keyof Extract<U, { t: K }>, 't'>;

const SETTINGS: LanSettings = {
  match: {
    ...defaultMatchConfig(42, ['rabbit', 'elephant', 'fox', 'frog']),
    // 1人ずつ違う値にしておく。並びが入れ替わって届いても気づけるように。
    startingHp: [2, 4, 6, 12],
  },
  cpu: ['easy', 'normal', 'hard', 'oni'],
};

describe('約束の表と型', () => {
  // 表は中継（Python）との突き合わせに使う。型は端末の中で使う。
  // この2つが食い違うと、突き合わせが通っても端末は別の項目を読む。
  it('端末から送るメッセージ', () => {
    expectTypeOf<keyof typeof FROM_PEER>().toEqualTypeOf<PeerMessage['t']>();
    expectTypeOf<FieldsOf<PeerMessage, 'start'>>().toEqualTypeOf<(typeof FROM_PEER)['start'][number]>();
    expectTypeOf<FieldsOf<PeerMessage, 'input'>>().toEqualTypeOf<(typeof FROM_PEER)['input'][number]>();
    expectTypeOf<FieldsOf<PeerMessage, 'hash'>>().toEqualTypeOf<(typeof FROM_PEER)['hash'][number]>();
    expectTypeOf<FieldsOf<PeerMessage, 'settings'>>().toEqualTypeOf<(typeof FROM_PEER)['settings'][number]>();
  });

  it('中継から届くメッセージ', () => {
    type T = typeof FROM_RELAY;
    expectTypeOf<keyof T>().toEqualTypeOf<RelayMessage['t']>();
    expectTypeOf<FieldsOf<RelayMessage, 'welcome'>>().toEqualTypeOf<T['welcome'][number]>();
    expectTypeOf<FieldsOf<RelayMessage, 'peer_joined'>>().toEqualTypeOf<T['peer_joined'][number]>();
    expectTypeOf<FieldsOf<RelayMessage, 'peer_left'>>().toEqualTypeOf<T['peer_left'][number]>();
    expectTypeOf<FieldsOf<RelayMessage, 'start'>>().toEqualTypeOf<T['start'][number]>();
    expectTypeOf<FieldsOf<RelayMessage, 'input'>>().toEqualTypeOf<T['input'][number]>();
    expectTypeOf<FieldsOf<RelayMessage, 'desync'>>().toEqualTypeOf<T['desync'][number]>();
    expectTypeOf<FieldsOf<RelayMessage, 'settings'>>().toEqualTypeOf<T['settings'][number]>();
    expectTypeOf<keyof HashReport>().toEqualTypeOf<(typeof REPORT_FIELDS)[number]>();
  });

  it('型の検査は、項目の食い違いを実際に止める', () => {
    // 上の検査が「何を渡しても通る」になっていないことの対照。
    // @ts-expect-error input に bits が無い型は、表と一致しない
    expectTypeOf<'tick'>().toEqualTypeOf<(typeof FROM_PEER)['input'][number]>();
  });
});

describe('中継から届いたメッセージを読む', () => {
  it('すべての種類を読める', () => {
    const cases: RelayMessage[] = [
      { t: 'welcome', seat: 1, role: 'guest', seats: [0] },
      { t: 'peer_joined', seat: 2 },
      { t: 'peer_left', seat: 2, lastTick: -1 },
      { t: 'start', seats: [0, 1], config: SETTINGS, match: 1 },
      { t: 'input', seat: 3, tick: 12, bits: 63, match: 1 },
      { t: 'desync', tick: 19, reports: [{ seat: 0, hash: 4294967295, rngCalls: 0 }] },
      { t: 'settings', config: SETTINGS },
    ];
    for (const message of cases) {
      expect(parseRelayMessage(JSON.stringify(message))).toEqual(message);
    }
  });

  it.each([
    ['JSON でない', '{{{'],
    ['辞書でない', '[1]'],
    ['知らない種類', '{"t":"snap"}'],
    ['Object の持ち物の名前', '{"t":"toString"}'],
    ['項目が足りない', '{"t":"input","seat":1,"tick":0}'],
    ['プレイヤー番号が範囲の外', '{"t":"input","seat":4,"tick":0,"bits":0,"match":1}'],
    ['プレイヤー番号が文字列', '{"t":"peer_joined","seat":"1"}'],
    ['tick が負', '{"t":"input","seat":1,"tick":-1,"bits":0,"match":1}'],
    ['tick が小数', '{"t":"input","seat":1,"tick":1.5,"bits":0,"match":1}'],
    ['ビットが6つのボタンを超える', '{"t":"input","seat":1,"tick":0,"bits":64,"match":1}'],
    ['lastTick が -1 より小さい', '{"t":"peer_left","seat":1,"lastTick":-2}'],
    ['role が知らない値', '{"t":"welcome","seat":0,"role":"owner","seats":[]}'],
    ['報告が辞書でない', '{"t":"desync","tick":0,"reports":[1]}'],
    // 始まる前の設定も、始めるときの設定と同じく読む。読めないまま画面に出すと、ずれた版どうしでつないだことに気づけない
    ['始まる前の設定が読めない', '{"t":"settings","config":{"match":{}}}'],
  ])('約束に合わないものは止める: %s', (_label, text) => {
    expect(() => parseRelayMessage(text)).toThrow(ProtocolError);
  });

  it('余分な項目は読み飛ばす', () => {
    // 中継が項目を足しても、古い端末が止まらないようにする。
    expect(parseRelayMessage('{"t":"peer_joined","seat":1,"note":"x"}')).toEqual({
      t: 'peer_joined',
      seat: 1,
    });
  });
});

describe('試合の設定を読む', () => {
  it('CPU の強さはプレイヤーごとに引く', () => {
    expect([0, 1, 2, 3].map((id) => cpuLevelOf(SETTINGS, id as PlayerId))).toEqual(['easy', 'normal', 'hard', 'oni']);
    expect(() => cpuLevelOf({ ...SETTINGS, cpu: ['easy'] }, 3)).toThrow(ProtocolError);
  });

  it('送ったとおりに戻る', () => {
    expect(parseLanSettings(JSON.parse(JSON.stringify(SETTINGS)))).toEqual(SETTINGS);
  });

  // 動物を2匹にするときは、1人ぶんずつ持つ値（体力・CPU の強さ）も2人ぶんにそろえる。
  // そろえないと、動物名の確かめより先に数の確かめで止まり、動物名の確かめが見えなくなる。
  const twoAnimals = (animals: string[]): unknown => ({
    match: { ...SETTINGS.match, animals, startingHp: [6, 6] },
    cpu: ['easy', 'easy'],
  });

  it.each([
    ['CPU の強さが無い', { match: SETTINGS.match }, /CPU の強さ/],
    ['CPU の強さが知らない値', { ...SETTINGS, cpu: ['easy', 'normal', 'hard', 'god'] }, /CPU の強さ/],
    ['CPU の強さが1つだけ（前の形）', { ...SETTINGS, cpu: 'hard' }, /CPU の強さ/],
    ['CPU の強さが動物より少ない', { ...SETTINGS, cpu: ['easy', 'normal', 'hard'] }, /CPU の強さ/],
    ['体力が1つだけ（前の形）', { ...SETTINGS, match: { ...SETTINGS.match, startingHp: 6 } }, /startingHp/],
    ['体力が動物より多い', { ...SETTINGS, match: { ...SETTINGS.match, startingHp: [6, 6, 6, 6, 6] } }, /startingHp/],
    ['体力に 0 がある', { ...SETTINGS, match: { ...SETTINGS.match, startingHp: [6, 0, 6, 6] } }, /startingHp/],
    ['体力に小数がある', { ...SETTINGS, match: { ...SETTINGS.match, startingHp: [6, 6, 6.5, 6] } }, /startingHp/],
    ['知らない動物', twoAnimals(['rabbit', 'dragon']), /知らない動物: dragon/],
    ['延長戦の有無が文字列', { ...SETTINGS, match: { ...SETTINGS.match, suddenDeath: 'yes' } }, /延長戦/],
    ['制限時間が 0', { ...SETTINGS, match: { ...SETTINGS.match, roundLimit: 0 } }, /roundLimit/],
    ['種が無い', { ...SETTINGS, match: { ...SETTINGS.match, seed: undefined } }, /seed/],
  ])('読めない設定は既定値で埋めずに止める: %s', (_label, raw, reason) => {
    // 埋めると、その端末だけ別の設定で試合を作ってずれる。
    // 止めた理由まで比べる。確かめが並んでいるので、別の確かめが先に止めても通ってしまう。
    const read = (): unknown => parseLanSettings(JSON.parse(JSON.stringify(raw)));
    expect(read).toThrow(ProtocolError);
    expect(read).toThrow(reason);
  });

  it('2匹の設定でも、そろっていれば読める', () => {
    // 上の「知らない動物」の行が、動物名の確かめまで届いていることの対照。
    expect(() => parseLanSettings(twoAnimals(['rabbit', 'fox']))).not.toThrow();
  });
});
