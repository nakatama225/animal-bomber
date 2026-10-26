import { afterEach, describe, expect, it, vi } from 'vitest';

import { Music } from '../../src/presentation/audio/Music.js';
import { SOUND_NAMES } from '../../src/presentation/audio/SoundBank.js';
import { SOUND_RECIPES } from '../../src/presentation/audio/soundRecipes.js';
import type {
  AudioBufferLike,
  AudioContextLike,
  AudioNodeLike,
  AudioParamLike,
} from '../../src/presentation/audio/webAudioTypes.js';
import { Synth, type NoiseOptions, type ToneOptions } from '../../src/presentation/audio/Synth.js';
import { WebAudioSoundBank } from '../../src/presentation/audio/WebAudioSoundBank.js';

/**
 * Synth が呼ぶものだけを手書きした、音を鳴らす仕組み（AudioContext）の偽物。
 *
 * 鳴らし始めた音源の数を数える。指数の変化に 0 以下を渡すと例外を投げる
 * ところだけはブラウザに合わせてある。node では本物が無いので、
 * この失敗はここで再現しないと、ブラウザで初めて見つかる。
 */
class FakeAudioContext implements AudioContextLike {
  currentTime = 0;
  readonly sampleRate = 100;
  state = 'suspended';
  readonly destination: AudioNodeLike = { connect: () => undefined };
  started = 0;
  resumed = 0;

  resume(): Promise<void> {
    this.resumed += 1;
    this.state = 'running';
    return Promise.resolve();
  }
  createGain() {
    return { gain: param(), connect: () => undefined };
  }
  createOscillator() {
    return {
      type: 'sine' as OscillatorType,
      frequency: param(),
      connect: () => undefined,
      start: () => {
        this.started += 1;
      },
      stop: () => undefined,
    };
  }
  createBufferSource() {
    return {
      buffer: null as AudioBufferLike | null,
      loop: false,
      connect: () => undefined,
      start: () => {
        this.started += 1;
      },
      stop: () => undefined,
    };
  }
  createBiquadFilter() {
    return {
      type: 'lowpass' as BiquadFilterType,
      frequency: param(),
      Q: param(),
      connect: () => undefined,
    };
  }
  createBuffer(_channels: number, length: number): AudioBufferLike {
    const data = new Float32Array(length);
    return { getChannelData: () => data };
  }
}

function param(): AudioParamLike {
  return {
    value: 0,
    setValueAtTime: () => undefined,
    exponentialRampToValueAtTime: (value: number) => {
      if (!(value > 0)) throw new RangeError(`指数の変化に ${value} は渡せない`);
    },
  };
}

function unlockedSynth(): { synth: Synth; ctx: FakeAudioContext } {
  const ctx = new FakeAudioContext();
  const synth = new Synth(() => ctx);
  synth.unlock();
  return { synth, ctx };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('効果音', () => {
  it('すべての音の名前に作り方がある', () => {
    const missing = SOUND_NAMES.filter((name) => typeof SOUND_RECIPES[name] !== 'function');
    expect(missing).toEqual([]);
  });

  it('unlock() の前に鳴らしても例外にならず、何もしない', () => {
    const bank = new WebAudioSoundBank(new Synth());
    for (const name of SOUND_NAMES) expect(() => bank.play(name)).not.toThrow();
  });

  it('unlock() を呼ぶと、止まっている仕組みを動かし直す', () => {
    const { synth, ctx } = unlockedSynth();
    expect(synth.ready).toBe(true);
    expect(ctx.resumed).toBe(1);
  });

  it('どの作り方も、例外なく1つ以上の音源を予約する', () => {
    const { synth, ctx } = unlockedSynth();
    for (const name of SOUND_NAMES) {
      for (const intensity of [1, 3]) {
        const before = ctx.started;
        expect(() => SOUND_RECIPES[name](synth, intensity), name).not.toThrow();
        expect(ctx.started, name).toBeGreaterThan(before);
      }
    }
  });

  it('連鎖すると音が増える', () => {
    const { synth, ctx } = unlockedSynth();
    SOUND_RECIPES.explode(synth, 1);
    const single = ctx.started;
    SOUND_RECIPES.explode(synth, 3);
    expect(ctx.started - single).toBeGreaterThan(single);
  });

  it('同じ瞬間に同じ音を2回鳴らせば、2回とも予約する（原型の SE もまとめない）', () => {
    // 原型が1回しか鳴らさない場面は、鳴らす側（Presenter）が場面を見分けて1回にする。
    const { synth, ctx } = unlockedSynth();
    const bank = new WebAudioSoundBank(synth);
    bank.play('breakBlock');
    const once = ctx.started;
    expect(once).toBeGreaterThan(0);
    bank.play('breakBlock');
    expect(ctx.started).toBe(once * 2);
  });

  it('画面の操作の音は、原型の SE.ui と同じ1音（760Hz・矩形波・0.05 秒・音量 0.12）', () => {
    const tones: ToneOptions[] = [];
    const noises: NoiseOptions[] = [];
    SOUND_RECIPES.ui({ tone: (options) => tones.push(options), noiseBurst: (options) => noises.push(options) }, 1);
    expect(tones).toEqual([{ f0: 760, type: 'square', dur: 0.05, vol: 0.12 }]);
    expect(noises).toEqual([]);
  });

  it('効果音を切っているあいだは音源を作らない', () => {
    const { synth, ctx } = unlockedSynth();
    const bank = new WebAudioSoundBank(synth);
    bank.setEnabled(false);
    bank.play('explode', 2);
    expect(ctx.started).toBe(0);
  });
});

describe('曲', () => {
  it('unlock() の前に始めても何もしない', () => {
    const music = new Music(new Synth());
    expect(() => music.start()).not.toThrow();
    expect(music.playing).toBe(false);
  });

  it('始めると予約し、時計が進めば次を予約し、止めると予約しなくなる', () => {
    vi.useFakeTimers();
    const { synth, ctx } = unlockedSynth();
    const music = new Music(synth);

    music.start();
    expect(music.playing).toBe(true);
    const first = ctx.started;
    expect(first).toBeGreaterThan(0);

    // 時計を少しずつ進め、タイマーが起きるたびに次の刻みを予約させる。
    for (let i = 0; i < 10; i += 1) {
      ctx.currentTime += 0.05;
      vi.advanceTimersByTime(25);
    }
    const second = ctx.started;
    expect(second).toBeGreaterThan(first);

    music.stop();
    ctx.currentTime += 0.5;
    vi.advanceTimersByTime(100);
    expect(ctx.started).toBe(second);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('大きく遅れても、過ぎた刻みをまとめて鳴らさない', () => {
    const { synth, ctx } = unlockedSynth();
    const music = new Music(synth);
    music.start();
    const before = ctx.started;
    // タイマーが10秒起きなかった場合と同じ状況を作る。
    ctx.currentTime += 10;
    music.schedule();
    // 過ぎた刻みを全部鳴らすと 90 以上になる。先読みの範囲の数個だけのはず。
    expect(ctx.started - before).toBeLessThan(10);
    music.stop();
  });

  it('速さは2倍で頭打ちになる', () => {
    const music = new Music(unlockedSynth().synth);
    music.setSpeed(3);
    expect(music.tempo).toBe(276);
  });

  it('曲を切ると止まり、切っているあいだは始まらない', () => {
    const { synth } = unlockedSynth();
    const music = new Music(synth);
    music.start();
    music.setEnabled(false);
    expect(music.playing).toBe(false);
    music.start();
    expect(music.playing).toBe(false);
  });
});
