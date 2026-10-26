import { describe, expect, it } from 'vitest';

import { tick } from '../../src/domain/core/Tick.js';
import * as notices from '../../src/presentation/notices.js';

/**
 * 通知の文（原型の `toast` の 22 種）。
 *
 * 期待する文は、Python 版の `presentation/notices.py` の文（原型の文から、リポの文の決まりで書かない語を
 * 言い換えたもの）を1字ずつ写した。差し込む所には、Python 版のテストと同じ値を入れる。
 */

const HOLE = '\u{1F573}\uFE0F';

describe('試合の中の 17 種', () => {
  it('アイテム：バナナ・たまねぎ・チキン・うんこ（原型 L1609・L1613・L1619・L1633）', () => {
    expect(notices.slipped('ぞう', 1)).toBe('🍌 ぞう すべる！');
    expect(notices.slipped('かえる', 2)).toBe('🍌 かえる すべる！（2倍！）');
    expect(notices.cried('ぞう', 1)).toBe('🧅 ぞう 涙で動けない！');
    expect(notices.cried('かえる', 2)).toBe('🧅 かえる 涙で動けない！（2倍！）');
    expect(notices.chickenTaken('ぞう', '突進', 1)).toBe('🍗 ぞう とくぎ「突進」！');
    expect(notices.chickenTaken('かえる', '粘膜爆弾', 2)).toBe('🍗 かえる とくぎ「粘膜爆弾」 ×2！');
    expect(notices.pooped('かえる', 'そうさ反転', 2)).toBe('💩 かえる そうさ反転！（2倍！）');
    expect(notices.pooped('ぞう', '爆風1マス', 1)).toBe('💩 ぞう 爆風1マス！');
  });

  it('葱ボン：外周へ回った・入れ替わった・外周が閉じた（原型 L2269・L2354・L2362）', () => {
    expect(notices.toLane('うさぎ')).toBe('🌿 うさぎ は葱ボンへ！ 外周から葱を撃って復活をねらえ');
    expect(notices.revived('1P', 'かえる')).toBe('🌿 1P 復活！ かえる が葱ボンへ');
    expect(notices.LANES_CLOSED).toBe('🌿 葱ボン 退場！ もう復活できない');
  });

  it('舌：焼き切れた・根元まで焼けた舌を出そうとした・1マス戻った（原型 L2488・L2498・L4307）', () => {
    expect(notices.tongueBurnt('かえる', 1)).toBe('👅🔥 かえる の舌が焼き切れた！このラウンドは 1マスまで');
    expect(notices.tongueGone('かえる', tick(600))).toBe('👅🔥 かえる の舌は焼け落ちてる（10秒で1マス戻る）');
    expect(notices.tongueRegrown('かえる', 4)).toBe('👅 かえる の舌が1マス回復（4マス）');
  });

  it('穴ととくぎ：掘り終えた・はまった・とくぎを使った（原型 L2575・L2597・L2611）', () => {
    expect(notices.pitDug('もぐら')).toBe(`${HOLE} もぐら 落とし穴をしかけた`);
    expect(notices.pitFallen('うさぎ', tick(180))).toBe(`${HOLE} うさぎ 落とし穴！ 3秒うごけない`);
    expect(notices.specialUsed('🐗', 'ぞう', '突進')).toBe('🐗 ぞう 突進！');
  });

  it('体当たりと鼻水：吸い込んだ・押しつけた・鼻水で消した（原型 L2818・L2880・L3036）', () => {
    expect(notices.swept('🔥', 'ぞう', '火力+1')).toBe('🔥 ぞう 突進で 火力+1 を吸い込んだ！');
    expect(notices.pushed('ぞう', 'かえる', 2)).toBe('💥 ぞう が かえる に 2個 ぶつけた！');
    expect(notices.sprayed('ぞう', 2, 1)).toBe('💧 ぞう 鼻水で 爆弾2個の火を消した・うんこ1個を流した！');
    expect(notices.sprayed('ぞう', 1, 0)).toBe('💧 ぞう 鼻水で 爆弾1個の火を消した！');
    expect(notices.sprayed('ぞう', 0, 3)).toBe('💧 ぞう 鼻水で うんこ3個を流した！');
    // 何も消さなければ出さない（原型 L3036 の `if (msg.length)`）。
    expect(notices.sprayed('ぞう', 0, 0)).toBeNull();
  });

  it('延長戦：わけと、延長戦の決まりの値（原型 L4463。体力は爆風何回ぶんか）', () => {
    expect(notices.suddenDeath('timeUp')).toBe('⚡ サドンデス！（時間切れ） 全員HP1・💣13・🔥13・👟13・60秒');
    expect(notices.suddenDeath('allDown')).toBe('⚡ サドンデス！（同時にやられた） 全員HP1・💣13・🔥13・👟13・60秒');
  });
});

describe('試合の外の 5 種', () => {
  it('パッド・中継・ホスト・CPU が引き継いだ（原型 L3498・L3527・L3735・L3787・L3793）', () => {
    expect(notices.padUnsupported('Generic USB Joystick')).toBe(
      '🎮 このコントローラーには対応していません（Generic USB Joystick）',
    );
    expect(notices.PAD_FOUND).toBe('🎮 コントローラーを認識しました');
    expect(notices.SERVER_LOST).toBe('サーバとの接続が切れました');
    expect(notices.HOST_LOST).toBe('ホストとの接続が切れました');
    expect(notices.cpuTookOver('きつね')).toBe('きつね の回線が切れた → CPU が引き継ぐ');
  });
});

describe('差し込む値', () => {
  it('2倍と添えるのは、効果の倍率が 1 より大きいときだけ', () => {
    expect(notices.doubled(1)).toBe('');
    expect(notices.doubled(2)).toBe('（2倍！）');
  });

  it('秒は切り上げる（原型の Math.ceil）', () => {
    expect([0, 1, 59, 60, 61, 120, 600].map((ticks) => notices.ceilSeconds(ticks))).toEqual([0, 1, 1, 1, 2, 2, 10]);
    expect(notices.tongueGone('かえる', tick(61))).toBe('👅🔥 かえる の舌は焼け落ちてる（2秒で1マス戻る）');
  });
});
