import { FrameLoop } from '../platform/FrameLoop.js';
import { readBrowserGamepads } from '../platform/GamepadInput.js';
import { GAME_KEYS, KeyboardWatcher, MENU_KEYS, navCommandOf } from '../platform/Keyboard.js';
import { loadSound, saveSound } from '../platform/preferences.js';
import { parseRelayAddress } from '../platform/WebSocketLink.js';
import { Music } from '../presentation/audio/Music.js';
import { Synth } from '../presentation/audio/Synth.js';
import { WebAudioSoundBank } from '../presentation/audio/WebAudioSoundBank.js';
import type { SoundSetting } from '../presentation/menu/MenuFlow.js';
import { Shell } from './Shell.js';

/**
 * 起動の入口。**ブラウザから道具を集めて渡すだけで、判断を持たない。**
 *
 * この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が
 * 見つかっていないということなので、ここで処理せず置き場所を探す。
 *
 * 1. 画面の要素・キーボード・ゲームパッド・音を用意する
 * 2. 画面の切り替えと試合の組み立て（`Shell`）に渡す
 * 3. 実時間のループを tick に換えて回す
 *
 * 通信対戦にするには、URL に `?relay` を付ける（タイトルの「通信対戦」も同じことをする）。
 * このページを配っている端末の 8777 番の中継サーバにつなぐ。別の場所の中継なら
 * `?relay=端末名.local:8777` と書く。
 */

/** 中継サーバの既定のポート。`server/` の `DEFAULT_PORT` と同じ値。 */
const DEFAULT_RELAY_PORT = 8777;

/** 止める・再開するキー。どのプレイヤーの操作にも使っていないキーにする。 */
const PAUSE_KEY = 'KeyP';

function findElement<T extends HTMLElement>(id: string, type: new () => T): T {
  const element = document.getElementById(id);
  if (!(element instanceof type)) {
    throw new Error(`#${id} が見つからないか、${type.name} ではない`);
  }
  return element;
}

/**
 * URL の `?relay` の値。付いていなければ null（1台で遊ぶ）。
 *
 * 値を省いたときは、このページを配っている端末の中継サーバを指す。
 */
function relayParameter(): string | null {
  const value = new URLSearchParams(window.location.search).get('relay');
  if (value === null) return null;
  return value === '' ? `${window.location.hostname}:${DEFAULT_RELAY_PORT}` : value;
}

function main(): void {
  const canvas = findElement('stage', HTMLCanvasElement);
  const context = canvas.getContext('2d');
  if (context === null) {
    throw new Error('2D の描画コンテキストを取得できない');
  }

  const keyboard = new KeyboardWatcher();
  keyboard.attach();

  const synth = new Synth();
  const music = new Music(synth);
  const applySound = (sound: SoundSetting): void => {
    synth.setBusOn('sfx', sound !== 'off');
    music.setEnabled(sound === 'both');
  };
  const sound = loadSound() ?? 'both';
  applySound(sound);

  const shell = new Shell(
    {
      menu: findElement('menu', HTMLElement),
      play: findElement('play', HTMLElement),
      canvas,
      side: findElement('side-panel', HTMLElement),
      banner: findElement('banner', HTMLElement),
      toasts: findElement('toasts', HTMLElement),
      pause: findElement('pause', HTMLElement),
      toolbar: findElement('toolbar', HTMLElement),
      lanStatus: findElement('lan-status', HTMLElement),
    },
    {
      context,
      keyboard,
      gamepads: readBrowserGamepads,
      sounds: new WebAudioSoundBank(synth),
      music,
      sound,
      setSound: (chosen) => {
        applySound(chosen);
        saveSound(chosen);
      },
      captureKeys: (screen) => keyboard.capture(screen === 'play' ? GAME_KEYS : MENU_KEYS),
      // 種は試合ごとに変えたいが、ルールの層で乱数や時刻に触れない。
      // 実時間を読むのはブラウザに近いこの層の役目なので、ここで作る。
      // 通信対戦では、ホストの種が全員に配られる。
      newSeed: () => Math.floor(Date.now() % 0xffffffff),
      openLan: () => {
        window.location.search = '?relay';
      },
      leaveLan: () => {
        // 開き直すと接続が閉じ、中継はこの人を抜けたものとして扱う（残りの人の試合は CPU が引き継ぐ）。
        window.location.search = '';
      },
    },
  );

  // ブラウザは、画面を操作するまで音を出させない。キーやクリックのたびに
  // 音を鳴らす仕組みを（初回だけ）作り、止まっていれば動かし直す（何度呼んでもよい）。
  const unlockAudio = (): void => synth.unlock();
  window.addEventListener('keydown', unlockAudio);
  window.addEventListener('pointerdown', unlockAudio);
  window.addEventListener('keydown', (event: KeyboardEvent) => {
    if (event.code === PAUSE_KEY && !event.repeat) shell.togglePause();
    const command = navCommandOf(event);
    if (command !== null) shell.navigate(command);
  });
  // マウスを動かしたら、メニューのカーソルの枠を消す（枠はキーやパッドを触ったときだけ出す。原型と同じ）。
  window.addEventListener('mousemove', () => shell.hideCursor());

  const relay = relayParameter();
  if (relay === null) {
    shell.showMenu();
  } else {
    const address = parseRelayAddress(relay);
    if (address === null) {
      // 1台で遊ぶ形に黙って切り替えない。通信対戦のつもりで開いた人が、理由を知らないまま
      // CPU と遊び始めてしまう。
      const menu = findElement('menu', HTMLElement);
      menu.textContent = `?relay の値が読めない：${relay}（例：?relay=端末名.local:8777）`;
      return;
    }
    shell.startLan(address);
  }

  new FrameLoop({
    onTick: () => shell.tick(),
    onDraw: (alpha) => shell.draw(alpha),
  }).start();
}

main();
