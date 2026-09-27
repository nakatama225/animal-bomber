import { CPU_LEVEL_KEYS, type CpuLevelKey } from '../ai/CpuLevel.js';
import { abilityOf } from '../domain/abilities/registry.js';
import { tick } from '../domain/core/Tick.js';
import type { MatchConfig } from '../domain/rules/MatchConfig.js';
import type { PlayerId } from '../domain/state/PlayerState.js';

/**
 * ロックステップの通信で使うメッセージの約束。
 *
 * 中継サーバの `server/src/animal_bomber_server/protocol.py` と**同じ約束を、
 * もう一方の言語で書いたもの**。どちらか一方だけを変えると、相手が知らない
 * 項目を送ったり、必要な項目を待ち続けたりする。
 *
 * 食い違いは2段で見つける。
 *
 * 1. 下の表（`FROM_PEER` / `FROM_RELAY` / `REPORT_FIELDS`）と、このファイルの型が
 *    一致しているかを、型のテスト（`tests/net/protocol.test.ts`）が見る
 * 2. 下の表と Python 側の表が一致しているかを、中継のテスト
 *    （`server/tests/test_protocol_sync.py`）がこのファイルを読んで見る
 *
 * ⚠️ 表の書き方を変えないこと。2 の検査は、このファイルを文字列として読んで表を取り出す。
 * 1行に1種類、`種類: ['項目', ...],` の形で書く。
 *
 * ## プレイヤー番号
 *
 * 中継での名前は `seat`。番号 N の端末がプレイヤー N を操作するので、
 * 値はそのままプレイヤー番号として使う。変換は `playerIdOf` の1か所だけで行う。
 */

/** ロックステップの中継につなぐときの WebSocket のパス。 */
export const LOCKSTEP_PATH = '/lockstep';

/**
 * 中継が、入れない接続（定員いっぱい・試合中）を閉じるときの番号。
 *
 * ただ切れた場合と見分けて、「前の試合が続いている」と案内するために使う。
 */
export const REFUSED_CLOSE_CODE = 1013;

/** 端末から中継へ送るメッセージの種類と、`t` 以外の項目。 */
export const FROM_PEER = {
  start: ['config'],
  input: ['tick', 'bits'],
  hash: ['tick', 'hash', 'rngCalls'],
} as const;

/** 中継から端末へ届くメッセージの種類と、`t` 以外の項目。 */
export const FROM_RELAY = {
  welcome: ['seat', 'role', 'seats'],
  peer_joined: ['seat'],
  peer_left: ['seat', 'lastTick'],
  start: ['seats', 'config'],
  input: ['seat', 'tick', 'bits'],
  desync: ['tick', 'reports'],
} as const;

/** `desync` の `reports` に並ぶ、1人ぶんの報告の項目。 */
export const REPORT_FIELDS = ['seat', 'hash', 'rngCalls'] as const;

/**
 * 試合の設定として、ホストが全員へ配るもの。
 *
 * 中継はこれを読まずに流す。人間が操作しないプレイヤーは全員この強さの CPU になる。
 */
export interface LanSettings {
  readonly match: MatchConfig;
  readonly cpu: CpuLevelKey;
}

/** 状態の要約の、1人ぶんの報告。 */
export interface HashReport {
  readonly seat: PlayerId;
  readonly hash: number;
  readonly rngCalls: number;
}

/** 端末から中継へ送るメッセージ。 */
export type PeerMessage =
  | { readonly t: 'start'; readonly config: LanSettings }
  | { readonly t: 'input'; readonly tick: number; readonly bits: number }
  | {
      readonly t: 'hash';
      readonly tick: number;
      readonly hash: number;
      readonly rngCalls: number;
    };

/** 中継から端末へ届くメッセージ。 */
export type RelayMessage =
  | {
      readonly t: 'welcome';
      readonly seat: PlayerId;
      readonly role: 'host' | 'guest';
      /** 自分より先に居た人。自分は含まない。 */
      readonly seats: readonly PlayerId[];
    }
  | { readonly t: 'peer_joined'; readonly seat: PlayerId }
  | {
      readonly t: 'peer_left';
      readonly seat: PlayerId;
      /** 抜けた人の入力を最後に配った tick。1通も配っていなければ -1。 */
      readonly lastTick: number;
    }
  | {
      readonly t: 'start';
      /** 試合を始めた時点で接続していた人。人間が操作するプレイヤーはこれで決まる。 */
      readonly seats: readonly PlayerId[];
      readonly config: LanSettings;
    }
  | {
      readonly t: 'input';
      readonly seat: PlayerId;
      readonly tick: number;
      readonly bits: number;
    }
  | { readonly t: 'desync'; readonly tick: number; readonly reports: readonly HashReport[] };

/**
 * メッセージを中継へ送る口。WebSocket で送る実物は `platform/` に置く。
 *
 * ⚠️ `send(message): void` のようなメソッドの形で書かない。メソッドの形だと、
 * 引数の型を狭めた実装（`input` しか送れないものなど）を渡しても型エラーにならない。
 */
export interface PeerLink {
  readonly send: (message: PeerMessage) => void;
}

/** 約束に合わないメッセージが届いた。相手の実装が食い違っている。 */
export class ProtocolError extends Error {
  override readonly name = 'ProtocolError';
}

/** 送るメッセージを文字列にする。 */
export function encodePeerMessage(message: PeerMessage): string {
  return JSON.stringify(message);
}

/**
 * 中継から届いた文字列を読む。
 *
 * 項目が足りない・型が違う・知らない種類は `ProtocolError` にする。
 * 読み飛ばして進めると、足りない項目を待ったまま試合が止まり、
 * 原因が「通信が遅い」に見える。
 *
 * @throws ProtocolError 約束に合わないとき
 */
export function parseRelayMessage(text: string): RelayMessage {
  const data = parseObject(text);
  const raw = data['t'];
  // ⚠️ `in` で調べない。`'toString' in FROM_RELAY` は真になる。
  if (typeof raw !== 'string' || !Object.hasOwn(FROM_RELAY, raw)) {
    throw new ProtocolError(`知らない種類のメッセージ: ${String(raw)}`);
  }
  const kind = raw as keyof typeof FROM_RELAY;
  const read = new FieldReader(data, kind);

  switch (kind) {
    case 'welcome': {
      const role = read.text('role');
      if (role !== 'host' && role !== 'guest') {
        throw new ProtocolError(`welcome の role が host でも guest でもない: ${role}`);
      }
      return { t: 'welcome', seat: read.seat('seat'), role, seats: read.seats('seats') };
    }
    case 'peer_joined':
      return { t: 'peer_joined', seat: read.seat('seat') };
    case 'peer_left':
      return { t: 'peer_left', seat: read.seat('seat'), lastTick: read.int('lastTick', -1) };
    case 'start':
      return {
        t: 'start',
        seats: read.seats('seats'),
        config: parseLanSettings(read.raw('config')),
      };
    case 'input':
      return {
        t: 'input',
        seat: read.seat('seat'),
        tick: read.int('tick', 0),
        bits: read.bits('bits'),
      };
    case 'desync':
      return { t: 'desync', tick: read.int('tick', 0), reports: read.reports('reports') };
    default:
      // FROM_RELAY に種類を足して、ここに分岐を足し忘れると、ここが型エラーになる。
      return unhandled(kind);
  }
}

function unhandled(kind: never): never {
  throw new ProtocolError(`読み方を決めていない種類: ${String(kind)}`);
}

/**
 * ホストが配った試合の設定を読む。
 *
 * ⚠️ 全員が同じ設定から試合を作ることが、ロックステップの前提そのもの。
 * 読めない値を既定値で埋めると、その端末だけ別の試合になる。埋めずに止める。
 *
 * @throws ProtocolError 約束に合わないとき
 */
export function parseLanSettings(raw: unknown): LanSettings {
  if (!isRecord(raw)) throw new ProtocolError('試合の設定が辞書ではない');
  const cpu = raw['cpu'];
  if (typeof cpu !== 'string' || !(CPU_LEVEL_KEYS as readonly string[]).includes(cpu)) {
    throw new ProtocolError(`CPU の強さが読めない: ${String(cpu)}`);
  }
  const match = raw['match'];
  if (!isRecord(match)) throw new ProtocolError('試合の設定に match が無い');
  const read = new FieldReader(match, 'match');

  const animals = read.raw('animals');
  if (!Array.isArray(animals) || animals.some((a) => typeof a !== 'string')) {
    throw new ProtocolError('動物の並びが文字列の配列ではない');
  }
  for (const animal of animals as string[]) {
    try {
      abilityOf(animal);
    } catch {
      throw new ProtocolError(`知らない動物: ${animal}`);
    }
  }
  const suddenDeath = read.raw('suddenDeath');
  if (typeof suddenDeath !== 'boolean') {
    throw new ProtocolError('延長戦の有無が真偽値ではない');
  }

  return {
    cpu: cpu as CpuLevelKey,
    match: {
      roundLimit: tick(read.int('roundLimit', 1)),
      winsToTake: read.int('winsToTake', 1),
      suddenDeath,
      startingHp: read.int('startingHp', 1),
      seed: read.int('seed', 0),
      animals: animals as string[],
    },
  };
}

/**
 * 中継での番号をプレイヤー番号にする。
 *
 * @throws ProtocolError 0〜3 の整数でないとき
 */
export function playerIdOf(seat: unknown): PlayerId {
  if (seat === 0 || seat === 1 || seat === 2 || seat === 3) return seat;
  throw new ProtocolError(`プレイヤー番号が 0〜3 の整数ではない: ${String(seat)}`);
}

/** 意思のビットの上限。6つのボタン（`packIntent`）で 6 ビット。 */
const MAX_BITS = 0b111111;

/** 1つのメッセージの項目を、型を確かめながら取り出す。 */
class FieldReader {
  constructor(
    private readonly data: Readonly<Record<string, unknown>>,
    private readonly kind: string,
  ) {}

  raw(name: string): unknown {
    if (!Object.hasOwn(this.data, name)) throw new ProtocolError(`${this.kind} に ${name} が無い`);
    return this.data[name];
  }

  /** `min` 以上の整数。 */
  int(name: string, min: number): number {
    const value = this.raw(name);
    if (typeof value !== 'number' || !Number.isInteger(value) || value < min) {
      throw new ProtocolError(`${this.kind} の ${name} が ${min} 以上の整数ではない: ${String(value)}`);
    }
    return value;
  }

  text(name: string): string {
    const value = this.raw(name);
    if (typeof value !== 'string') throw new ProtocolError(`${this.kind} の ${name} が文字列ではない`);
    return value;
  }

  seat(name: string): PlayerId {
    return playerIdOf(this.raw(name));
  }

  seats(name: string): PlayerId[] {
    const value = this.raw(name);
    if (!Array.isArray(value)) throw new ProtocolError(`${this.kind} の ${name} が配列ではない`);
    return value.map(playerIdOf);
  }

  bits(name: string): number {
    const value = this.int(name, 0);
    if (value > MAX_BITS) throw new ProtocolError(`${this.kind} の ${name} が大きすぎる: ${value}`);
    return value;
  }

  reports(name: string): HashReport[] {
    const value = this.raw(name);
    if (!Array.isArray(value)) throw new ProtocolError(`${this.kind} の ${name} が配列ではない`);
    return value.map((entry: unknown) => {
      if (!isRecord(entry)) throw new ProtocolError(`${this.kind} の ${name} の要素が辞書ではない`);
      const item = new FieldReader(entry, `${this.kind}.${name}`);
      const [seat, hash, rngCalls] = REPORT_FIELDS;
      return { seat: item.seat(seat), hash: item.int(hash, 0), rngCalls: item.int(rngCalls, 0) };
    });
  }
}

function parseObject(text: string): Readonly<Record<string, unknown>> {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new ProtocolError('JSON として読めない');
  }
  if (!isRecord(data)) throw new ProtocolError('メッセージが辞書ではない');
  return data;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
