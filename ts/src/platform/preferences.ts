import type { SoundSetting } from '../presentation/menu/MenuFlow.js';

/** 音の設定を残す名前。 */
const SOUND_KEY = 'animal-bomber.sound';

const SOUNDS: readonly SoundSetting[] = ['both', 'sfx', 'off'];

/** 設定を残しておく場所。ブラウザの `localStorage` と同じ形。 */
export interface PreferenceStore {
  readonly getItem: (key: string) => string | null;
  readonly setItem: (key: string, value: string) => void;
}

/**
 * 前に選んだ音の設定。
 *
 * 通信対戦へ移るときと抜けるときは、ページを開き直す。残しておかないと、そのたびに
 * 既定（BGM + 効果音）に戻る。
 *
 * ⚠️ 残しておく場所は、プライベートのウィンドウなどで使えない（読むだけで例外になる）ことがある。
 * そのときは既定に戻すだけで、遊ぶのは止めない。
 *
 * @returns 残っていなければ null
 */
export function loadSound(store: () => PreferenceStore | null = browserStore): SoundSetting | null {
  try {
    const value = store()?.getItem(SOUND_KEY) ?? null;
    return SOUNDS.find((sound) => sound === value) ?? null;
  } catch {
    return null;
  }
}

/** 音の設定を残す。残せなくても何もしない。 */
export function saveSound(sound: SoundSetting, store: () => PreferenceStore | null = browserStore): void {
  try {
    store()?.setItem(SOUND_KEY, sound);
  } catch {
    // 残せない場所では、開き直すと既定に戻るだけ。
  }
}

function browserStore(): PreferenceStore | null {
  return typeof localStorage === 'undefined' ? null : localStorage;
}
