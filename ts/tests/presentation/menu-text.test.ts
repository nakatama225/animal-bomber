import { describe, expect, it } from 'vitest';

import { ANIMAL_LOOKS } from '../../src/content/animals.js';
import {
  CPU_HEADING,
  CPU_NOTE,
  cpuTag,
  DIALOG_NO,
  DIALOG_TEXTS,
  HIT_LABELS,
  HIT_NOTE,
  LOG_LABEL,
  LOGO,
  MANUAL_HEADING,
  MANUAL_LABEL,
  pickerHeading,
  SOUND_CHOICES,
  SOUND_LABEL,
  SPLASH_PROMPT,
  SUBTITLE,
  SUDDEN_LABEL,
  SUDDEN_NOTE,
  TIME_LABEL,
  TIME_NOTE,
  TITLE_ITEMS,
  WINS_LABEL,
  WINS_NOTE,
} from '../../src/presentation/menu/menuText.js';

/**
 * 試合の外の画面の文が、Python 版（`presentation/menu/screens.py`・`choices.py`・`animal_text.py`）の文と
 * 同じか。期待値は Python 版の値を書き出して写したもの（原型の行番号は `menuText.ts` の説明）。
 */

/** 文字の並び（絵文字の異体字セレクタ U+FE0F の有無まで見る）。 */
const codePoints = (text: string): number[] => [...text].map((ch) => ch.codePointAt(0) ?? 0);

describe('試合の外の画面の文', () => {
  it('タイトルの5つの項目は原型の文（LAN対戦と、設定・マニュアル・更新履歴は小さい形）', () => {
    expect(TITLE_ITEMS.map((item) => [item.choice, item.title, item.detail, item.small])).toEqual([
      ['solo', '1人 vs CPU×3', 'CPU の強さは あとで1体ずつ決められる', false],
      ['duo', '2人 vs CPU×2', '1P と 2P が協力せず殴り合ってもいい', false],
      ['versus', '2人タイマン', 'CPU なし。1P vs 2P だけ', false],
      ['lan', 'LAN対戦', '同じ Wi-Fi 内の別の Mac と対戦する（最大4人）', true],
      ['manual', '設定・マニュアル・更新履歴', 'サウンド設定／そうさとルールの説明／バージョンの履歴', true],
    ]);
    expect(TITLE_ITEMS.map((item) => codePoints(item.icon))).toEqual([
      [0x1f579, 0xfe0f],
      [0x1f465],
      [0x2694, 0xfe0f],
      [0x1f4f6],
      [0x1f4d6],
    ]);
  });

  it('ロゴ・題・起動の幕の案内', () => {
    expect(LOGO).toBe('Nakatando');
    expect(SUBTITLE).toBe('🐰💣🐘 どうぶつボンバー');
    expect(SPLASH_PROMPT).toBe('クリック か なにかキーを押す');
  });

  it('キャラ選びの段の見出しは「P1 のどうぶつ」の形（原型の鍵を大文字にした形。「1P」ではない）', () => {
    expect([pickerHeading(0), pickerHeading(1)]).toEqual(['P1 のどうぶつ', 'P2 のどうぶつ']);
  });

  it('ルールの画面の見出しと注記', () => {
    expect(HIT_LABELS).toEqual({ p1: '1P が爆風にたえる回数', p2: '2P が爆風にたえる回数', cpu: 'CPU が爆風にたえる回数' });
    expect(HIT_NOTE).toBe('ハンデをつけたい時に使う（例：1P だけ 3回にする）。🐘ぞうは常に +1回');
    expect(CPU_HEADING).toBe('CPU の強さ（1体ずつ）');
    expect([0, 1, 2].map(cpuTag)).toEqual(['CPU1', 'CPU2', 'CPU3']);
    expect(CPU_NOTE).toEqual([
      'よわい＝反応が鈍く、危険に気づかず、あまり攻めてこない。おに＝盤面の端からでも追ってくる。',
      'CPU の動物はランダムに決まる',
    ]);
    expect(WINS_LABEL).toBe('何勝先取で優勝');
    expect(WINS_NOTE).toBe('1ラウンド勝つと★1つ。先に取りきったら優勝');
    expect(TIME_LABEL).toBe('制限時間');
    expect(TIME_NOTE).toEqual([
      { kind: 'text', text: '🌿 葱ボンは残り1分で退場するので、' },
      { kind: 'bold', text: '1:00 にすると葱ボンなし' },
      { kind: 'text', text: 'になる' },
    ]);
    expect(SUDDEN_LABEL).toBe('サドンデス（同時死・時間切れ）');
    expect(SUDDEN_NOTE).toBe('ONだと、決着つかない時にソフトブロック全消し・全員MAX装備・60秒で延長');
  });

  it('設定の画面の見出しと音の3択（曲だけの選択肢は無い）', () => {
    expect(MANUAL_HEADING).toBe('設定・マニュアル・更新履歴');
    expect([SOUND_LABEL, MANUAL_LABEL, LOG_LABEL]).toEqual(['① 設定 ／ サウンド', '② マニュアル ／ そうさ・ルール', '③ 更新履歴']);
    expect(SOUND_CHOICES).toEqual([
      { value: 'both', label: 'BGM + 効果音' },
      { value: 'sfx', label: '効果音だけ' },
      { value: 'off', label: '無音' },
    ]);
  });

  it('キャラ選びのカードの説明は原型の文（もぐらの「👟の効果」だけ言い換え）', () => {
    expect(Object.fromEntries(ANIMAL_LOOKS.map((look) => [look.key, look.description]))).toEqual({
      rabbit:
        '移動が速い。1マス跳んでブロックを越える（2秒に1回）。とくぎ「うんこポロポロ」＝周囲5×5の25マスを埋め尽くす（爆風でも消えず1分残る・自分は平気）',
      elephant:
        '爆風+2、HP+1。鼻水噴射は正面2マスの爆弾とうんこを消す（5秒に1回）。とくぎ「突進」＝1.5秒長押して柱までブロックを壊しながら直進する（爆風を受けると0.5ダメージ）',
      mole:
        'ソフトブロックのみ通り抜け可能（通り抜け中はとても遅いが、👟の効果は通常と同じ倍率で伸びる）。とくぎ「落とし穴」穴に落ちると3秒動けない（自分には発動しない）',
      fox:
        '爆弾を最初から1個多く持つ。技ボタンで「1マス前」から手持ちぶん一列ドン設置。とくぎ「狐火」＝青い炎が1.5秒 敵を追いかける。放つ時にキツネ跳びで1秒 無敵',
      frog:
        '舌で遠くのアイテムを引き寄せる（良いも悪いも全部食う）。アイテムの効果が2倍。とくぎ「粘膜爆弾」＝3マス先へ飛ばして跳ね回ってから爆発（アイテム2倍なので2回ぶん持てる）',
    });
    // 原型のもぐらの説明の語（字の番号で持つ。Python 版の言い換えは「効果」）を書かない。
    const original = String.fromCodePoint(0x52b9, 0x304d);
    expect(ANIMAL_LOOKS.some((look) => look.description.includes(original))).toBe(false);
  });

  it('確認の画面の文と右のボタンは原型の文（Python 版の DialogKind と同じ）。左はいつも「やめる」', () => {
    expect(DIALOG_TEXTS).toEqual({
      backToSetup: { message: '設定へもどりますか？', yes: '設定へもどる' },
      disconnect: { message: 'せつぞくを切ります。よいですか？', yes: 'せつぞくを切る' },
    });
    expect(DIALOG_NO).toBe('やめる');
  });
});
