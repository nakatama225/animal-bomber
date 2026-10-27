import { CPU_LEVELS } from '../ai/CpuLevel.js';
import { CpuInputSource, cpuSeed } from '../ai/CpuInputSource.js';
import type { InputSource } from '../domain/input/InputSource.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import { CombinedInputSource } from '../platform/CombinedInputSource.js';
import { GameSpeed } from '../platform/FrameLoop.js';
import { GamepadInputSource, PadChoice, PadMenuInput, type PadSnapshot } from '../platform/GamepadInput.js';
import {
  KeyboardInputSource,
  PLAYER1_KEYS,
  PLAYER2_KEYS,
  SOLO_KEYS,
  type KeyBinding,
  type KeyboardState,
} from '../platform/Keyboard.js';
import { BannerOverlay } from '../platform/ui/BannerOverlay.js';
import { pointerButton, scrollToTop } from '../platform/ui/dom.js';
import { MenuNavigator } from '../platform/ui/MenuNavigator.js';
import { MenuView } from '../platform/ui/MenuView.js';
import { SidePanel, type KeyHelpFor } from '../platform/ui/SidePanel.js';
import { speedControl } from '../platform/ui/SpeedControl.js';
import { Toasts } from '../platform/ui/Toasts.js';
import { Countdown } from '../presentation/audio/Countdown.js';
import type { SoundBank } from '../presentation/audio/SoundBank.js';
import { describeKeyHelp } from '../presentation/hud/keyHelp.js';
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

/** 外から受け取るもの。ブラウザの API に触れるものは、起動の入口が作って渡す。 */
export interface ShellTools {
  /** 盤面を描く先。 */
  readonly context: CanvasRenderingContext2D;
  /** 押しているキーと押した瞬間。押した瞬間をいつ忘れるかは、ここ（`Shell`）が決める。 */
  readonly keyboard: KeyboardState;
  readonly gamepads: () => readonly (PadSnapshot | null)[];
  readonly sounds: SoundBank;
  /**
   * 音を出せるようにする（ブラウザの音の解錠。何度呼んでもよい）。画面の操作の音を鳴らす前に呼ぶ。
   *
   * 起動の入口はキーとクリックのたびにも解錠するが、パッドだけで遊ぶと、それが一度も起きない
   * （原型も、操作の音を鳴らすボタンの中で解錠する。L5706）。
   */
  readonly unlockAudio: () => void;
  readonly music: MusicControl;
  /** 起動したときの音の設定（前に選んだもの）。 */
  readonly sound: SoundSetting;
  /** 音の設定を変える。 */
  readonly setSound: (sound: SoundSetting) => void;
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
interface ActiveMatch extends MatchParts {
  readonly runner: MatchRunner;
  readonly side: SidePanel;
  /** 部品を作ったときの `runner.generation`。変わったら次の試合なので、部品を作り直す。 */
  readonly generation: number;
  /**
   * 試合が決まった幕に並べるボタン。描くたびに呼ぶ（通信対戦では、ホストかどうかが
   * つないだあとで分かる。ホストにだけ「もういっかい」を出す）。
   */
  readonly finalActions: () => readonly HTMLElement[];
  /** ゲームの速さの倍率を適用するか。1台で遊ぶときだけ。通信対戦は全員が同じ速さで進める。 */
  readonly paced: boolean;
  /**
   * 試合が決まった幕を、パッドで動かせるか。パッドを試合に繋いだとき（1人で遊ぶとき。`drivesPad`）と
   * 通信対戦のとき（原型と同じ）。
   *
   * 1台で2人のときは（CPU の有無によらず）、パッドを試合に繋がない。幕でも受け付けないのは、机に置いた
   * パッドに肘が当たっただけで次の試合が始まらないようにするため（原型の注意書き）。キーボードは受け付ける。
   */
  readonly padOnBanner: boolean;
}

/**
 * 試合ごとに作り直す部品。同じ runner で次の試合が始まったとき（通信対戦の再戦）も作り直す。
 *
 * ⚠️ 作り直さないと、前の試合の「試合が決まった幕」が消えない（`RoundBanner` は決まった幕を、
 * 盤面が替わっても出し続ける）。描く側も、前の試合の位置から次の試合の開始位置へ動いて見える。
 */
interface MatchParts {
  readonly renderer: Renderer;
  readonly presenter: Presenter;
  readonly banner: RoundBanner;
  readonly countdown: Countdown;
}

const KEY_LAYOUTS: Readonly<Record<'solo' | 'left' | 'right', KeyBinding>> = {
  solo: SOLO_KEYS,
  left: PLAYER1_KEYS,
  right: PLAYER2_KEYS,
};

/**
 * ゲームパッドを繋ぐ操作か。1人で遊ぶときのキーボードの操作だけ（1台に1人ぶん）。
 * 2人のときに繋ぐと、どちらのプレイヤーのパッドか決められない。
 *
 * 試合に繋ぐか（`#sourceFor`）と、試合が決まった幕でパッドを受け付けるか（`padOnBanner`）を、
 * この1つで決める。別々に書くと、遊び方を足したときに片方だけが変わる。
 */
const drivesPad = (controller: LocalController): boolean => controller.kind === 'keys' && controller.layout === 'solo';

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
  /** キーボードとパッドで、メニュー・ロビー・試合が決まった幕を動かすカーソル。 */
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
      uiSound: () => this.#uiSound(),
    });
  }

  /** 画面の操作の音（原型の `A.init(); A.resume(); SE.ui();`）。解錠してから鳴らす（解錠の前に鳴らしても鳴らない）。 */
  #uiSound(): void {
    this.#tools.unlockAudio();
    this.#tools.sounds.play('ui');
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
    plan.controllers.forEach((controller, index) => {
      session.attach(this.#sourceFor(index as PlayerId, controller, plan.config.seed));
    });
    const runner = new LocalMatch(session, plan.roster);
    // 試合が決まった幕のボタンは横に並ぶので、カーソルの1グループにする。
    const actions = [
      pointerButton('もういっかい', () => this.restart(), { data: { action: 'again', nav: 'final' } }),
      pointerButton('タイトルへ', () => this.showMenu(), { data: { action: 'title', nav: 'final' } }),
    ];
    const padInMatch = plan.controllers.some(drivesPad);
    this.#begin(runner, this.#keyHelp(runner, { padInMatch, canPause: true }), () => actions, {
      paced: true,
      padOnBanner: padInMatch,
    });
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
    // ホストにだけ出す（原型も、次の試合を始められるのはホストだけだった）。押すと合図を送るだけで、
    // 次の試合は中継が配り直した start を受け取ってから始まる。
    const again = [pointerButton('もういっかい', () => runner.rematch(), { data: { action: 'again', nav: 'final' } })];
    // 自分のプレイヤー番号は、つないで受け取るまで分からない。キーの案内は、名札の一覧でこの端末のプレイヤー
    // （`local`）の分だけを出す（`describeKeyHelp`）。通信対戦ではだれもポーズできない。
    this.#begin(runner, this.#keyHelp(runner, { padInMatch: true, canPause: false }), () => (runner.canRematch ? again : []), {
      paced: false,
      padOnBanner: true,
    });
    // 通信対戦は等倍で進めるので、曲も等倍に戻す。盤面は同じ速さなのに曲だけ速いと、
    // 速さが変わったように見える。つまみの倍率（`#speed`）は、1台の試合に戻ったときのために残す。
    this.#tools.music.setSpeed(1);
    this.#setToolbar([pointerButton('ぬける', () => this.#tools.leaveLan(), { data: { action: 'leave' } })]);
  }

  /** 同じ選択で、新しい試合を始める（種は変わる）。1台で遊んだあとだけ有効。 */
  restart(): void {
    if (this.#lastSetup !== null) this.startLocal(this.#lastSetup);
  }

  /** 止める・再開する（1台で遊ぶときだけ有効）。 */
  togglePause(): void {
    this.#match?.runner.togglePause();
  }

  /**
   * キーボードやパッドの操作で、メニュー・ロビー・試合が決まった幕のカーソルを動かす。
   *
   * 1回に押し始めた操作をまとめて渡す（キーボードは1つ、パッドは1回に読んだぶん。`MenuCursor.handle`）。
   * 試合の最中は何もしない（幕にボタンが無いので、カーソルの並びが空になる）。
   * ⚠️ ロビーでは戻る（Escape・B）で何もしない。ぬけるとページを開き直すので、押し間違えると
   * 試合ごと抜けてしまう。ぬけるときは「← ぬける」をマウスで押す。
   */
  navigate(...commands: NavCommand[]): void {
    const root = this.#navRoot();
    // 試合が決まった幕だけは、枠が出ていなくても最初の決定を反映する（原型と同じ。`MenuCursor` の説明を参照）。
    const result = this.#nav.handle(root, commands, root === this.#elements.banner ? 'activate' : 'show');
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
   *
   * ## 押してすぐ離したキーを忘れる時
   *
   * キーボードとパッドは、押した瞬間を残す（押してから離すまでが 1 tick より短くても、爆弾と技を 1 tick は
   * 押したことにする。`KeyboardWatcher`・`PadChoice`）。忘れるのは、入力を tick へ取り込んだあと
   * （通信対戦では送ったあと。どちらも `#step` の中の `runner.step()`）だけ。倍速でも1回の押しは 1 tick ぶんになる。
   * 進めなかった呼び出し（0.5 倍で 0 tick の回・通信対戦で入力を待っている間）では忘れない。忘れると、
   * 押したことが読まれないまま消える。
   * ⚠️ ここ（`tick` の末尾）では忘れない。通信対戦は、送る入力を進める tick の中で読む（3 tick 先の入力）ので、
   * 進めなかった回に末尾で忘れると、押しが読まれない。
   * 例外は、1台の試合を止めている間（`MatchRunner.stopped`）と試合の外で、そのときは原型と同じく毎フレーム
   * 忘れる（`draw`）。
   */
  tick(): void {
    const match = this.#current();
    if (match === null || !this.#canStep(match)) return;
    const count = match.paced ? this.#speed.take() : 1;
    for (let i = 0; i < count && this.#canStep(match); i += 1) this.#step(this.#current() ?? match);
  }

  /**
   * いまの試合の部品。同じ runner で次の試合が始まっていたら、作り直してから返す。
   *
   * 通信対戦では、次の試合は中継から届いた1通で始まる（届くのは tick と描く合間）。
   */
  #current(): ActiveMatch | null {
    const match = this.#match;
    if (match === null || match.runner.generation === match.generation) return match;
    // 前の試合の通知も持ち越さない（1台の「もういっかい」は、試合を作り直すときに消している）。
    this.#toasts.clear();
    this.#match = { ...match, ...this.#partsFor(match.runner), generation: match.runner.generation };
    return this.#match;
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
    // 入力を取り込んだ（通信対戦では送った）ので、押した瞬間を忘れる（`tick` の説明）。
    this.#forgetTaps();
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
    // 試合の部品を読むより前に、パッドの操作を反映する。1回に押し始めた操作は、まとめてカーソルへ渡す。
    // ⚠️ 読むのは毎回。受け付けないときも、前回の状態を更新し続ける（押したままのボタンを、あとで
    // 新しい押下と取り違えないため。原型も同じ）。試合の操作の押した瞬間も、ここで読んだときに残る（`PadChoice`）。
    const commands = this.#padMenu.poll();
    if (commands.length > 0 && this.#padAccepted()) this.navigate(...commands);
    const match = this.#current();
    const music = this.#tools.music;
    if (match === null) {
      music.stop();
      this.#paintCursor();
      // 試合の外で押したキーは忘れる（原型も毎フレーム忘れる。`tick` の説明）。
      this.#forgetTaps();
      return;
    }
    const { runner } = match;
    const world = runner.world;
    this.#showBoard(world !== null);
    if (world !== null) match.renderer.draw(world, match.paced ? this.#speed.progress(alpha) : alpha);
    const hud = runner.hud;
    match.side.update(hud);
    this.#bannerView.show(world === null ? null : match.banner.current(world), match.finalActions());
    this.#elements.pause.hidden = !runner.paused;
    runner.afterDraw();
    this.#paintCursor();
    // 試合が始まる前（通信対戦のロビー）と、1台の試合を止めている間は、押したキーを毎フレーム忘れる
    // （`tick` の説明。止めている間に押した爆弾のキーで、再開した最初の tick に爆弾を置かない）。
    if (world === null || runner.stopped) this.#forgetTaps();
    // 試合が終わったとき・止めたとき・通信対戦が止まったとき（ずれ・切断）は曲を止める。
    // tick が進まない間も判断できるよう、描く側で毎回見る。鳴っていれば start は何もしない。
    if (runner.inProgress) music.start();
    else music.stop();
  }

  #begin(
    runner: MatchRunner,
    help: KeyHelpFor,
    finalActions: ActiveMatch['finalActions'],
    { paced, padOnBanner }: Pick<ActiveMatch, 'paced' | 'padOnBanner'>,
  ): void {
    this.#endMatch();
    this.#match = {
      runner,
      ...this.#partsFor(runner),
      side: new SidePanel(this.#elements.side, help),
      generation: runner.generation,
      finalActions,
      paced,
      padOnBanner,
    };
    this.#showBoard(runner.world !== null);
    // 試合を始めるたびにページの先頭へ戻す（原型の startGame → showScreen('play')。幕の「もういっかい」も同じ）。
    // 窓より縦に長いルールの画面を下まで動かして「はじめる」を押すと、盤面の上と時計が窓の外に残るため。
    // ⚠️ 盤面を出したかどうか（`#showBoard`）では決めない。「もういっかい」は試合の画面のまま次の試合になる。
    // 通信対戦でここを通るのは、つないだとき（ロビーを出すとき）だけ。試合が始まって盤面へ移るときは、まだ戻さない。
    scrollToTop(this.#elements.play);
  }

  #partsFor(runner: MatchRunner): MatchParts {
    // 名札の一覧は通知を出すたびに尋ねる（通信対戦では、抜けたプレイヤーが CPU に替わる）。
    const presenter = new Presenter(this.#tools.sounds, this.#toasts, () => runner.hud?.roster ?? []);
    return {
      renderer: new Renderer(this.#tools.context, this.#elements.canvas.width, this.#elements.canvas.height),
      presenter,
      banner: new RoundBanner(),
      countdown: new Countdown(this.#tools.sounds),
    };
  }

  /**
   * 盤面が有れば試合の画面を、無ければ試合の前の画面を出す。
   *
   * 通信対戦では、試合が始まるまで盤面が無い。その間は同じ場所にロビーを出す。
   */
  #showBoard(board: boolean): void {
    this.#elements.menu.hidden = board;
    this.#elements.play.hidden = !board;
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

  /**
   * 横の板のキーの案内を作る関数（`describeKeyHelp`）。ポーズ中か・パッドを認識しているかは、描くたびに読む。
   *
   * @param padInMatch パッドを試合に繋ぐ遊び方か（1人で遊ぶときと通信対戦）
   * @param canPause この端末でポーズできるか（1台の試合だけ）
   */
  #keyHelp(runner: MatchRunner, { padInMatch, canPause }: { padInMatch: boolean; canPause: boolean }): KeyHelpFor {
    return (source) =>
      describeKeyHelp({
        world: source.world,
        roster: source.roster,
        padConnected: this.#pads.connected,
        padInMatch,
        paused: runner.paused,
        canPause,
      });
  }

  /** 押してすぐ離したキーとボタンの、押した瞬間を忘れる（`tick` の説明）。 */
  #forgetTaps(): void {
    this.#tools.keyboard.forgetTaps();
    this.#pads.forgetTaps();
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

  #sourceFor(id: PlayerId, controller: LocalController, seed: number): InputSource {
    if (controller.kind === 'cpu') return new CpuInputSource(id, CPU_LEVELS[controller.level], cpuSeed(seed, id));
    const keyboard = new KeyboardInputSource(id, this.#tools.keyboard, KEY_LAYOUTS[controller.layout]);
    if (!drivesPad(controller)) return keyboard;
    return new CombinedInputSource([keyboard, new GamepadInputSource(id, this.#pads)]);
  }
}
