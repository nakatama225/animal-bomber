import { CPU_LEVELS } from '../ai/CpuLevel.js';
import { CpuIntentSource, cpuSeed } from '../ai/CpuIntentSource.js';
import type { IntentSource } from '../domain/intent/IntentSource.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import { CombinedIntentSource } from '../platform/CombinedIntentSource.js';
import { GameSpeed } from '../platform/FrameLoop.js';
import { GamepadIntentSource, PadChoice, PadMenuInput, type PadSnapshot } from '../platform/GamepadInput.js';
import { GAMEPAD_HELP, keyHelpFor, type KeyHelp } from '../platform/keyHelp.js';
import {
  KeyboardIntentSource,
  PLAYER1_KEYS,
  PLAYER2_KEYS,
  SOLO_KEYS,
  type KeyBinding,
  type KeyStateReader,
} from '../platform/Keyboard.js';
import { BannerOverlay } from '../platform/ui/BannerOverlay.js';
import { pointerButton } from '../platform/ui/dom.js';
import { MenuNavigator } from '../platform/ui/MenuNavigator.js';
import { MenuView } from '../platform/ui/MenuView.js';
import { SidePanel, type KeyHelpEntry, type KeyHelpFor } from '../platform/ui/SidePanel.js';
import { speedControl } from '../platform/ui/SpeedControl.js';
import { Toasts } from '../platform/ui/Toasts.js';
import { Countdown } from '../presentation/audio/Countdown.js';
import type { SoundBank } from '../presentation/audio/SoundBank.js';
import { displayName } from '../presentation/hud/roster.js';
import type { HudSource } from '../presentation/hud/scoreboard.js';
import { RoundBanner } from '../presentation/hud/RoundBanner.js';
import { planLocalMatch, type LocalController, type LocalSetup } from '../presentation/menu/localSetup.js';
import type { NavCommand } from '../presentation/menu/MenuCursor.js';
import { MenuFlow, type SoundSetting } from '../presentation/menu/MenuFlow.js';
import { Presenter } from '../presentation/Presenter.js';
import { Renderer } from '../presentation/render/Renderer.js';
import { GameSession } from './GameSession.js';
import { LanMatch, type LanMatchOptions } from './LanMatch.js';
import { LocalMatch, type MatchRunner } from './MatchRunner.js';

/** 画面の部品。`index.html` にある要素。 */
export interface ShellElements {
  /** 試合の前の画面と、通信対戦のロビーを出す場所。 */
  readonly menu: HTMLElement;
  /** 試合の画面。 */
  readonly play: HTMLElement;
  readonly canvas: HTMLCanvasElement;
  readonly side: HTMLElement;
  readonly banner: HTMLElement;
  readonly toasts: HTMLElement;
  readonly pause: HTMLElement;
  readonly toolbar: HTMLElement;
  readonly lanStatus: HTMLElement;
}

/** 曲を鳴らす・止める。 */
export interface MusicControl {
  /** 鳴っていなければ頭から鳴らす。鳴っていれば何もしない。 */
  readonly start: () => void;
  readonly stop: () => void;
  /** ゲームの速さの倍率に合わせて、曲の速さを変える。 */
  readonly setSpeed: (multiplier: number) => void;
}

/** 外から受け取る道具。ブラウザの API に触れるものは、起動の入口が作って渡す。 */
export interface ShellTools {
  /** 盤面を描く先。 */
  readonly context: CanvasRenderingContext2D;
  readonly keyboard: KeyStateReader;
  readonly gamepads: () => readonly (PadSnapshot | null)[];
  readonly sounds: SoundBank;
  readonly music: MusicControl;
  /** 起動したときの音の設定（前に選んだもの）。 */
  readonly sound: SoundSetting;
  /** 音の設定を変える。 */
  readonly setSound: (sound: SoundSetting) => void;
  /**
   * 操作に使うキーの、ブラウザの既定の動き（矢印と Space でページが動く、など）を止める。
   * 試合の画面の間は試合の操作のキーを、メニューの間はメニューを動かすキーを止める。
   */
  readonly captureKeys: (screen: 'play' | 'menu') => void;
  /** 試合の種を作る。実時間を読むのは起動の入口の役目なので、外から受け取る。 */
  readonly newSeed: () => number;
  /** 通信対戦の画面へ移る（URL に `?relay` を付けて開き直す）。 */
  readonly openLan: () => void;
  /** 通信対戦から抜けてタイトルへ戻る（URL から `?relay` を外して開き直す）。 */
  readonly leaveLan: () => void;
  /** 中継につなぐ。省くとブラウザの WebSocket を使う（テストで差し替える）。 */
  readonly connect?: LanMatchOptions['connect'];
}

/** 1試合ぶんの部品。試合ごとに作り直す（前の試合の粒子や幕を持ち越さない）。 */
interface ActiveMatch {
  readonly runner: MatchRunner;
  readonly renderer: Renderer;
  readonly presenter: Presenter;
  readonly banner: RoundBanner;
  readonly countdown: Countdown;
  readonly side: SidePanel;
  /** 試合が決まった幕に並べるボタン。 */
  readonly finalActions: readonly HTMLElement[];
  /** ゲームの速さの倍率を効かせるか。1台で遊ぶときだけ。通信対戦は全員が同じ速さで進める。 */
  readonly paced: boolean;
  /**
   * 試合が決まった幕を、パッドで動かせるか。1人で遊ぶときと通信対戦のとき（原型と同じ）。
   *
   * 1台で2人のときは、パッドを試合に繋がない（`#sourceFor`）。幕でも受け付けないのは、机に置いた
   * パッドに肘が当たっただけで次の試合が始まらないようにするため（原型の注意書き）。キーボードは効く。
   */
  readonly padOnBanner: boolean;
}

const KEY_LAYOUTS: Readonly<Record<'solo' | 'left' | 'right', KeyBinding>> = {
  solo: SOLO_KEYS,
  left: PLAYER1_KEYS,
  right: PLAYER2_KEYS,
};

/**
 * 画面の切り替え（試合の前の画面 ⇄ 試合）と、試合ごとの部品の組み立て。
 *
 * **配線だけを行う。** どの画面を出すかは `MenuFlow`、試合の進め方は `MatchRunner`、
 * 何を表示するかは `presentation/hud/` が決める。ここはそれらを作ってつなぎ、
 * 画面のループから呼ばれたら順に呼ぶ。
 */
export class Shell {
  readonly #elements: ShellElements;
  readonly #tools: ShellTools;
  readonly #flow: MenuFlow;
  readonly #menu: MenuView;
  readonly #bannerView: BannerOverlay;
  readonly #toasts: Toasts;
  #match: ActiveMatch | null = null;
  #lastSetup: LocalSetup | null = null;
  /** ゲームの速さ。試合をまたいで持つ（もういっかいで等倍に戻さない。原型と同じ）。 */
  readonly #speed = new GameSpeed();
  /** キーボードとパッドで、メニュー・ロビー・優勝の幕を動かすカーソル。 */
  readonly #nav = new MenuNavigator();
  /** つかんでいるパッド。メニュー・ロビー・試合で1つを分け合う（`PadChoice` の説明を参照）。 */
  readonly #pads: PadChoice;
  readonly #padMenu: PadMenuInput;

  constructor(elements: ShellElements, tools: ShellTools) {
    this.#elements = elements;
    this.#tools = tools;
    this.#pads = new PadChoice(tools.gamepads);
    this.#padMenu = new PadMenuInput(this.#pads);
    this.#flow = new MenuFlow(undefined, tools.sound);
    this.#bannerView = new BannerOverlay(elements.banner);
    this.#toasts = new Toasts(elements.toasts);
    this.#menu = new MenuView(elements.menu, this.#flow, {
      start: (setup) => this.startLocal(setup),
      soundChanged: (sound) => tools.setSound(sound),
      openLan: () => tools.openLan(),
    });
  }

  /** 試合の前の画面を出す。 */
  showMenu(): void {
    this.#endMatch();
    this.#flow.returnToTitle();
    this.#menu.render();
    this.#showBoard(false);
  }

  /** 1台で遊ぶ試合を始める。 */
  startLocal(setup: LocalSetup): void {
    this.#lastSetup = setup;
    const plan = planLocalMatch(setup, this.#tools.newSeed());
    const session = new GameSession(plan.config);
    const help: KeyHelpEntry[] = [];
    plan.controllers.forEach((controller, index) => {
      const id = index as PlayerId;
      session.attach(this.#sourceFor(id, controller, plan.config.seed));
      if (controller.kind === 'keys') help.push({ playerId: id, help: this.#helpFor(id, controller.layout) });
    });
    const runner = new LocalMatch(session, plan.roster);
    // 優勝の幕のボタンは横に並ぶので、カーソルの1グループにする。
    this.#begin(runner, () => help, [
      pointerButton('もういっかい', () => this.restart(), { data: { action: 'again', nav: 'final' } }),
      pointerButton('タイトルへ', () => this.showMenu(), { data: { action: 'title', nav: 'final' } }),
    ], { paced: true, padOnBanner: setup.mode === 'solo' });
    this.#setToolbar([
      speedControl(this.#speed.rate, (rate) => this.#setSpeed(rate)),
      pointerButton('⏸ ポーズ', () => this.togglePause(), { data: { action: 'pause' } }),
      pointerButton('タイトルへ', () => this.showMenu(), { data: { action: 'quit' } }),
    ]);
  }

  /** 通信対戦に参加する。 */
  startLan(address: string): void {
    const runner = new LanMatch({
      address,
      keyboard: this.#tools.keyboard,
      pads: this.#pads,
      lobby: this.#elements.menu,
      status: this.#elements.lanStatus,
      newSeed: this.#tools.newSeed,
      leave: () => this.#tools.leaveLan(),
      ...(this.#tools.connect === undefined ? {} : { connect: this.#tools.connect }),
    });
    // 自分のプレイヤー番号は、つないで受け取るまで分からない。名札の「あなた」から選ぶ。
    this.#begin(runner, (source) => this.#localHelp(source), [], { paced: false, padOnBanner: true });
    // 通信対戦は等倍で進めるので、曲も等倍に戻す。盤面は同じ速さなのに曲だけ速いと、
    // 速さが変わったように見える。つまみの倍率（`#speed`）は、1台の試合に戻ったときのために残す。
    this.#tools.music.setSpeed(1);
    this.#setToolbar([pointerButton('ぬける', () => this.#tools.leaveLan(), { data: { action: 'leave' } })]);
  }

  /** 同じ選択で、新しい試合を始める（種は変わる）。1台で遊んだあとだけ効く。 */
  restart(): void {
    if (this.#lastSetup !== null) this.startLocal(this.#lastSetup);
  }

  /** 止める・再開する（1台で遊ぶときだけ効く）。 */
  togglePause(): void {
    this.#match?.runner.togglePause();
  }

  /**
   * キーボードやパッドの操作で、メニュー・ロビー・優勝の幕のカーソルを動かす。
   *
   * 試合の最中は何もしない（幕にボタンが無いので、カーソルの並びが空になる）。
   * ⚠️ ロビーでは戻る（Escape・B）で何もしない。ぬけるとページを開き直すので、押し間違えると
   * 試合ごと抜けてしまう。ぬけるときは「← ぬける」をマウスで押す。
   */
  navigate(command: NavCommand): void {
    const root = this.#navRoot();
    // 優勝の幕だけは、枠が出ていなくても最初の決定を効かせる（原型と同じ。`MenuCursor` の説明を参照）。
    const result = this.#nav.handle(root, command, root === this.#elements.banner ? 'activate' : 'show');
    if (result.kind === 'back' && this.#match === null) {
      this.#menu.back();
      this.#nav.paint(root);
    }
  }

  /** カーソルの枠を消す（マウスを動かしたとき）。 */
  hideCursor(): void {
    this.#nav.hide(this.#navRoot());
  }

  /**
   * 画面のループから、1 tick ぶんの時間が経つごとに呼ばれる。
   *
   * 1台で遊ぶときは、ゲームの速さの倍率ぶんの tick を進める（0.5 倍なら2回に1回）。
   */
  tick(): void {
    const match = this.#match;
    if (match === null || !this.#canStep(match)) return;
    const count = match.paced ? this.#speed.take() : 1;
    for (let i = 0; i < count && this.#canStep(match); i += 1) this.#step(match);
  }

  /** いま1 tick 進められるか。止めている間と、通信対戦で全員の入力がそろうまでは進めない。 */
  #canStep(match: ActiveMatch): boolean {
    return match.runner.hud !== null && match.runner.ready;
  }

  #step(match: ActiveMatch): void {
    const { runner } = match;
    const hud = runner.hud;
    if (hud === null) return;
    // ラウンドが終わると盤面が作り直されるので、進める前の盤面を控えて渡す。
    const world = hud.world;
    match.renderer.beforeTick(world);
    const events = runner.step();
    match.presenter.consume(events, world);
    match.banner.onEvents(events, hud);
    match.renderer.afterTick(events, world);
    const after = runner.world;
    if (after !== null) match.countdown.observe(after);
  }

  /**
   * 画面のループから、1枚描くごとに呼ばれる。
   *
   * @param alpha 実時間での、次に `tick()` が呼ばれるまでの進み具合。1台で遊ぶときは、
   *   描く側へ渡す前に、ゲームの速さの倍率を掛けた試合の時間の進み具合に換える（`GameSpeed.progress`）
   */
  draw(alpha: number): void {
    // パッドは押したことを知らせてくれないので、描くたびに読む。決めた項目が画面を替えることがあるので、
    // 試合の部品を読むより前に済ませる。
    // ⚠️ 読むのは毎回。受け付けないときも、前回の状態を更新し続ける（押したままのボタンを、あとで
    // 新しい押下と取り違えないため。原型も同じ）。
    const commands = this.#padMenu.poll();
    if (this.#padAccepted()) for (const command of commands) this.navigate(command);
    const match = this.#match;
    const music = this.#tools.music;
    if (match === null) {
      music.stop();
      this.#paintCursor();
      return;
    }
    const { runner } = match;
    const world = runner.world;
    this.#showBoard(world !== null);
    if (world !== null) match.renderer.draw(world, match.paced ? this.#speed.progress(alpha) : alpha);
    const hud = runner.hud;
    match.side.update(hud);
    this.#bannerView.show(world === null ? null : match.banner.current(world), match.finalActions);
    this.#elements.pause.hidden = !runner.paused;
    runner.afterDraw();
    this.#paintCursor();
    // 試合が終わったとき・止めたとき・通信対戦が止まったとき（ずれ・切断）は曲を止める。
    // tick が進まない間も判断できるよう、描く側で毎回見る。鳴っていれば start は何もしない。
    if (runner.inProgress) music.start();
    else music.stop();
  }

  #begin(
    runner: MatchRunner,
    help: KeyHelpFor,
    finalActions: readonly HTMLElement[],
    { paced, padOnBanner }: Pick<ActiveMatch, 'paced' | 'padOnBanner'>,
  ): void {
    this.#endMatch();
    const presenter = new Presenter(this.#tools.sounds, this.#toasts, (id, world) => {
      const roster = runner.hud?.roster;
      const animal = world.players[id]?.animal;
      return roster === undefined || animal === undefined ? `${id + 1}P` : displayName(roster, id, animal);
    });
    this.#match = {
      runner,
      renderer: new Renderer(this.#tools.context, this.#elements.canvas.width, this.#elements.canvas.height),
      presenter,
      banner: new RoundBanner(),
      countdown: new Countdown(this.#tools.sounds),
      side: new SidePanel(this.#elements.side, help),
      finalActions,
      paced,
      padOnBanner,
    };
    this.#showBoard(runner.world !== null);
  }

  /**
   * 盤面が有れば試合の画面を、無ければ試合の前の画面を出す。
   *
   * 通信対戦では、試合が始まるまで盤面が無い。その間は同じ場所にロビーを出す。
   */
  #showBoard(board: boolean): void {
    this.#elements.menu.hidden = board;
    this.#elements.play.hidden = !board;
    this.#tools.captureKeys(board ? 'play' : 'menu');
  }

  /** いまパッドでカーソルを動かしてよいか。メニューとロビーはいつでも、幕は `padOnBanner` のときだけ。 */
  #padAccepted(): boolean {
    const match = this.#match;
    return this.#navRoot() !== this.#elements.banner || match === null || match.padOnBanner;
  }

  /**
   * カーソルで動かす画面。試合の前はメニュー、通信対戦で盤面がまだ無い間はロビー
   * （同じ場所に出す）、盤面があればラウンドの間の幕。
   */
  #navRoot(): HTMLElement {
    const match = this.#match;
    if (match === null || match.runner.world === null) return this.#elements.menu;
    return this.#elements.banner;
  }

  /**
   * 画面が組み直されても印が残るよう、描くたびに付け直す。
   *
   * ⚠️ 枠が消えている間も呼ぶ（印は付かない）。画面が替わったことに気づくのはここなので、
   * 枠を出している間だけにすると、マウスで行って戻ってきた画面で、カーソルが前にいた番号から動き出す。
   */
  #paintCursor(): void {
    this.#nav.paint(this.#navRoot());
  }

  /** 通信対戦の、この端末の人のキー配置の説明。 */
  #localHelp(source: HudSource): KeyHelpEntry[] {
    return source.roster.flatMap((controller, index) => {
      if (controller.kind !== 'human' || !controller.local) return [];
      const id = index as PlayerId;
      return [{ playerId: id, help: this.#helpFor(id, 'solo') }];
    });
  }

  #endMatch(): void {
    this.#match?.runner.close();
    this.#match = null;
    this.#toasts.clear();
    this.#bannerView.show(null);
    this.#elements.pause.hidden = true;
    this.#setToolbar([]);
  }

  #setSpeed(rate: number): void {
    this.#speed.set(rate);
    this.#tools.music.setSpeed(rate);
  }

  #setToolbar(buttons: readonly HTMLElement[]): void {
    this.#elements.toolbar.replaceChildren(...buttons);
  }

  #sourceFor(id: PlayerId, controller: LocalController, seed: number): IntentSource {
    if (controller.kind === 'cpu') return new CpuIntentSource(id, CPU_LEVELS[controller.level], cpuSeed(seed, id));
    const keyboard = new KeyboardIntentSource(id, this.#tools.keyboard, KEY_LAYOUTS[controller.layout]);
    // ゲームパッドは1人で遊ぶときだけ繋ぐ（1台に1人ぶん）。2人のときに繋ぐと、
    // どちらのプレイヤーのパッドか決められない。
    if (controller.layout !== 'solo') return keyboard;
    return new CombinedIntentSource([keyboard, new GamepadIntentSource(id, this.#pads)]);
  }

  #helpFor(id: PlayerId, layout: 'solo' | 'left' | 'right'): KeyHelp {
    const help = keyHelpFor(`${id + 1}P`, KEY_LAYOUTS[layout]);
    return layout === 'solo' ? { ...help, lines: [...help.lines, ...GAMEPAD_HELP] } : help;
  }
}
