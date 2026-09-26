/**
 * 鳴らせる音の名前。
 *
 * ルールの層はこの一覧を知らない。どのイベントにどの音を当てるかは
 * この層の判断で、変えてもゲームの結果は1ミリも変わらない。
 */
export type SoundName =
  | 'place'
  | 'explode'
  | 'breakBlock'
  | 'item'
  | 'chicken'
  | 'burn'
  | 'hurt'
  | 'down'
  | 'slip'
  | 'cry'
  | 'poop'
  | 'roundEnd'
  | 'draw'
  | 'sudden'
  | 'fanfare'
  | 'hop'
  | 'lineBombs'
  | 'tongue'
  | 'special'
  | 'scatter'
  | 'charge'
  | 'dig'
  | 'foxfire'
  | 'slime'
  | 'leek'
  | 'leekBlock'
  | 'leekHit'
  | 'lanesClosed';

/** すべての音の名前。表の漏れを検査するのに使う。 */
export const SOUND_NAMES: readonly SoundName[] = [
  'place',
  'explode',
  'breakBlock',
  'item',
  'chicken',
  'burn',
  'hurt',
  'down',
  'slip',
  'cry',
  'poop',
  'roundEnd',
  'draw',
  'sudden',
  'fanfare',
  'hop',
  'lineBombs',
  'tongue',
  'special',
  'scatter',
  'charge',
  'dig',
  'foxfire',
  'slime',
  'leek',
  'leekBlock',
  'leekHit',
  'lanesClosed',
];

/** 音を鳴らすもの。 */
export interface SoundBank {
  /**
   * @param intensity 大きさの手がかり（連鎖数など）。使うかどうかは実装しだい
   */
  play(name: SoundName, intensity?: number): void;
}

/**
 * 何も鳴らさない実装。
 *
 * 検証のときはこれを差す……という説明をしたくなるが、**実際には
 * それすら要らない**。`Presenter` を作らなければ音は鳴らない。
 * このクラスは「画面は出すが音は消したい」場合のためにある。
 */
export class NullSoundBank implements SoundBank {
  play(): void {
    // 何もしない。
  }
}
