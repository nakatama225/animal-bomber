import { CPU_LEVELS } from '../ai/CpuLevel.js';
import { CpuInputSource, cpuSeed } from '../ai/CpuInputSource.js';
import { lookOf } from '../content/animals.js';
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
import { BannerOverlay, NO_BUTTONS, type BannerButtons } from '../platform/ui/BannerOverlay.js';
import { ConfirmDialog } from '../platform/ui/ConfirmDialog.js';
import { scrollToTop } from '../platform/ui/dom.js';
import { MenuNavigator } from '../platform/ui/MenuNavigator.js';
import { MenuView } from '../platform/ui/MenuView.js';
import { SidePanel, type KeyHelpFor, type SideControls } from '../platform/ui/SidePanel.js';
import { Toasts } from '../platform/ui/Toasts.js';
import { Countdown } from '../presentation/audio/Countdown.js';
import type { SoundBank } from '../presentation/audio/SoundBank.js';
import { describeKeyHelp } from '../presentation/hud/keyHelp.js';
import { PanelRefresh } from '../presentation/hud/panelRefresh.js';
import { takenOver, type Roster } from '../presentation/hud/roster.js';
import { RoundBanner, type BannerView } from '../presentation/hud/RoundBanner.js';
import { LobbyChoices } from '../presentation/menu/lanSetup.js';
import { planLocalMatch, type LocalController, type LocalSetup } from '../presentation/menu/localSetup.js';
import type { NavCommand } from '../presentation/menu/MenuCursor.js';
import { MenuFlow, type SoundSetting } from '../presentation/menu/MenuFlow.js';
import { cpuTookOver, PAD_FOUND, padUnsupported } from '../presentation/notices.js';
import { Presenter } from '../presentation/Presenter.js';
import { boardLayoutFor, layoutFor, type Layout } from '../presentation/render/Layout.js';
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
  /** 試合の横の板（原型の `#side`）。中身は試合ごとに `SidePanel` が組む。 */
  readonly side: HTMLElement;
  /** ラウンドの幕と優勝の幕（原型の `#banner`）。`#app` の外にあり、窓の全体を覆う。 */
  readonly banner: HTMLElement;
  /** 確認の画面（原型の `#cfmWrap`）。`#app` の外にあり、盤面の上にもメニューの上にも出る。 */
  readonly confirm: HTMLElement;
  /** 画面の上に出す通知（原型の `#toast`）。1つだけで、`#app` の外にあり、どの画面の上にも出る。 */
  readonly toast: HTMLElement;
  /** 通信対戦の案内の帯。盤面の下の端に重ねる（`LanMatch`）。 */
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
  /**
   * 起動したときの音の設定（原型と同じく BGM + 効果音）。起動の入口が音の部品に当てたものと同じ値を渡す。
   *
   * 選び直した設定は起動の間だけ持ち、ブラウザには残さない（原型・Python 版と同じ。通信対戦へ移るときも抜けるときも
   * ページを開き直さないので、残さなくても消えない）。
   */
  readonly sound: SoundSetting;
  /** 音の設定を変える。 */
  readonly setSound: (sound: SoundSetting) => void;
  /** 試合の種を作る。実時間を読むのは起動の入口の役目なので、外から受け取る。 */
  readonly newSeed: () => number;
  /**
   * LAN の画面の「たてる」「さんかする」でつなぐ中継の「ホスト名:ポート」（`parseRelayAddress` で検証したもの）。
   *
   * 起動の入口が、URL の `?relay=名前` の値か、ページを配った端末の中継（`defaultRelayAddress`）から作る。ここは窓を読まない。
   */
  readonly relayAddress: string;
  /** 中継につなぐ。省くとブラウザの WebSocket を使う（テストで差し替える）。 */
  readonly connect?: LanMatchOptions['connect'];
}

/**
 * 1台の試合と通信対戦とで違う、幕と抜け方の扱い。
 *
 * 試合をやめてタイトルへ戻る口（横の板の「設定へ」・幕の「⚙ 設定をやりなおす」・確認の画面の「設定へもどる」）は、
 * どちらも `showMenu`（原型の `backToSetup`。通信対戦は接続を閉じる）。
 */
interface MatchRoutes {
  /**
   * 幕に並べるボタン。描くたびに呼ぶ（通信対戦では、ホストかどうかがつないだあとで分かり、ずれたら
   * 「もういっかい」を消す）。
   */
  readonly bannerButtons: (view: BannerView) => BannerButtons;
  /** 優勝の幕の1つ目のボタン（「もういっかい」）。 */
  readonly again: () => void;
  /** 通信対戦の接続（接続の段階を見て、画面を替える）。1台の試合は null。 */
  readonly lan: LanMatch | null;
  /** ゲームの速さの倍率を適用するか。1台で遊ぶときだけ。通信対戦は全員が同じ速さで進める。 */
  readonly paced: boolean;
  /**
   * パッドを試合に繋ぐ遊び方か（原型の `active`。L3570）。1人で遊ぶとき（`drivesPad`）と通信対戦のとき。
   *
   * 真のときだけ、幕でパッドを受け付け（幕の間は毎フレーム枠を出す）、試合の最中のパッドの Start・Select を
   * 受け付ける。1台で2人のときは（CPU の有無によらず）、パッドを試合に繋がないので、幕でも試合の最中も受け付けない。
   * 机に置いたパッドに肘が当たっただけで次のラウンドへ進んだり止まったりしないようにするため（原型の注意書き）。
   * キーボードは受け付ける。
   */
  readonly padOnBanner: boolean;
}

/** 1試合ぶんの部品。試合ごとに作り直す（前の試合の粒子や幕を持ち越さない）。 */
interface ActiveMatch extends MatchParts, MatchRoutes {
  readonly runner: MatchRunner;
  readonly side: SidePanel;
  /** 部品を作ったときの `runner.generation`。変わったら次の試合なので、部品を作り直す。 */
  readonly generation: number;
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
  /** 横の板の名札と時計を作り直す時（原型の 0.25 秒ごとと、被弾などの場面）。 */
  readonly refresh: PanelRefresh;
}

const KEY_LAYOUTS: Readonly<Record<'solo' | 'left' | 'right', KeyBinding>> = {
  solo: SOLO_KEYS,
  left: PLAYER1_KEYS,
  right: PLAYER2_KEYS,
};

/** 1台の試合の幕のボタン。どちらの幕にも2つとも出す（原型 L548-549）。 */
const LOCAL_BUTTONS: BannerButtons = { advance: true, setup: true };

/** 幕にボタンを1つでも並べるか（通信対戦のラウンドの幕は並べない）。 */
const hasButtons = (buttons: BannerButtons): boolean => buttons.advance || buttons.setup;

/**
 * ゲームパッドを繋ぐ操作か。1人で遊ぶときのキーボードの操作だけ（1台に1人ぶん）。
 * 2人のときに繋ぐと、どちらのプレイヤーのパッドか決められない。
 *
 * 試合に繋ぐか（`#sourceFor`）と、幕と試合の最中にパッドを受け付けるか（`padOnBanner`）を、
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
  readonly #dialog: ConfirmDialog;
  readonly #toasts: Toasts;
  #match: ActiveMatch | null = null;
  #lastSetup: LocalSetup | null = null;
  /** 通信対戦のロビーでホストが選ぶもの。接続をまたいで持つ（原型の `CFG` と同じく、タイトルへ戻っても消さない）。 */
  readonly #lobbyChoices = new LobbyChoices();
  /** ゲームの速さ。試合をまたいで持つ（もういっかいで等倍に戻さない。原型と同じ）。 */
  readonly #speed = new GameSpeed();
  /** キーボードとパッドで、メニュー・ロビー・幕・確認の画面を動かすカーソル。 */
  readonly #nav = new MenuNavigator();
  /** つかんでいるパッド。メニュー・ロビー・試合で1つを分け合う（`PadChoice` の説明を参照）。 */
  readonly #pads: PadChoice;
  readonly #padMenu: PadMenuInput;
  /**
   * 盤面の寸法。窓の大きさから決める（`fitBoard`）。決めるまでは、canvas の大きさに収まる寸法
   * （テストは `fitBoard` を呼ばずに、渡した canvas の大きさで描く）。
   */
  #layout: Layout;

  constructor(elements: ShellElements, tools: ShellTools) {
    this.#elements = elements;
    this.#tools = tools;
    this.#pads = new PadChoice(tools.gamepads);
    this.#padMenu = new PadMenuInput(this.#pads);
    this.#flow = new MenuFlow(undefined, tools.sound);
    this.#bannerView = new BannerOverlay(elements.banner, {
      advance: () => this.#advanceBanner(),
      setup: () => this.showMenu(),
    });
    this.#dialog = new ConfirmDialog(elements.confirm, () => this.#uiSound());
    this.#toasts = new Toasts(elements.toast);
    this.#layout = layoutFor(elements.canvas.width, elements.canvas.height);
    this.#menu = new MenuView(elements.menu, this.#flow, {
      start: (setup) => this.startLocal(setup),
      soundChanged: (sound) => tools.setSound(sound),
      connectLan: () => this.startLan(tools.relayAddress),
      askDisconnect: () => this.#askDisconnect(false),
      uiSound: () => this.#uiSound(),
      // 画面が替わったら確認の画面を畳む（原型の showScreen の closeDialog）。⚠️ いまは、確認の画面を開いたまま画面が替わる
      // 道（つないでいる最中の LAN の画面から、ロビーへ移る・断られる・「せつぞくを切る」を選ぶ）のどれも、先に別の所が畳む
      // （`enteredLobby`・`#endMatch`）。ここが畳む道は無いが、原型の showScreen と同じ形の備えとして残す。
      screenChanged: () => this.#dialog.close(),
    });
  }

  /** 画面の操作の音（原型の `A.init(); A.resume(); SE.ui();`）。解錠してから鳴らす（解錠の前に鳴らしても鳴らない）。 */
  #uiSound(): void {
    this.#tools.unlockAudio();
    this.#tools.sounds.play('ui');
  }

  /**
   * 試合の前の画面を出す（試合や通信対戦から戻るときは、原型の `backToSetup`）。
   *
   * 試合を抜け（通信対戦なら接続を閉じ、案内の帯を空にして隠す）、確認の画面を畳み、カーソルの枠を消してタイトルを出す
   * （原型 L6058-6079。枠を消さないと、試合を終えてタイトルを出した瞬間に、触っていないのに枠が光る。枠はキーかパッドを
   * 触ったときだけ出す）。LAN の画面の「接続しています…」も消す（`MenuFlow.returnToTitle`）。
   */
  showMenu(): void {
    this.#endMatch();
    this.#flow.returnToTitle();
    this.#menu.render();
    this.#showBoard(false);
    this.#nav.hide(this.#elements.menu);
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
    const padInMatch = plan.controllers.some(drivesPad);
    // 2人で遊ぶ形では、メニューで出した枠を試合へ持ち越さない。原型は枠を出したまま（`MENU.on`）試合を始めるが、
    // この形の幕では塗らない（L3622 が L3637 より前で帰る）ので、幕のボタンに枠は付かない。この版は描くたびに
    // 幕を塗るので、持ち越すと「つぎのラウンド ▶」に枠が付く。2人の試合の間に枠を使う所は無い（幕でパッドを
    // 受け付けず、確認の画面も開かない）。⚠️ `#begin` には置かない（通信対戦のロビーの枠まで消える）。
    if (!padInMatch) this.#nav.hide(this.#elements.menu);
    // 横の板：つまみ・「⏸ ポーズ」・「設定へ」（原型 L522-537）。「設定へ」は確認を出さずにタイトルへ戻る
    // （原型の注記 L3377-3380。マウスで押しに行くこと自体が、戻るつもりで押したことを示すため）。どちらのボタンも
    // 操作の音を鳴らさない（原型と同じ。L6038・L6080）。
    const controls: SideControls = {
      speed: { rate: this.#speed.rate, change: (rate) => this.#setSpeed(rate) },
      pause: () => this.togglePause(),
      quit: () => this.showMenu(),
    };
    this.#begin(runner, this.#keyHelp(runner, { padInMatch, canPause: true }), controls, {
      bannerButtons: () => LOCAL_BUTTONS,
      again: () => this.restart(),
      lan: null,
      paced: true,
      padOnBanner: padInMatch,
    });
    // 試合を始めるたびにページの先頭へ戻す（原型の startGame → showScreen('play')。幕の「もういっかい」も同じ）。
    // 窓より縦に長いルールの画面を下まで動かして「はじめる」を押すと、盤面の上と時計が窓の外に残るため。
    // ⚠️ 盤面を出したかどうか（`#showBoard`）では決めない。「もういっかい」は試合の画面のまま次の試合になる。
    scrollToTop(this.#elements.play);
    // 曲の速さを、いまのゲームの速さに合わせる（通信対戦は曲を等倍に戻すので、そのあとの1台の試合で戻す。Python 版と
    // 同じく、始めるたびに合わせる）。合わせないと、盤面はつまみの倍率なのに曲は等倍のままになる。
    this.#tools.music.setSpeed(this.#speed.rate);
  }

  /**
   * 通信対戦の中継につなぎ始める（LAN の画面の「たてる」「さんかする」と、URL の `?relay` で開いたとき。原型の
   * `joinLan`）。
   *
   * LAN の画面へ移り、「たてる」「さんかする」を隠して「接続しています…」を出す。中継から番号を受け取ったらロビーへ移る
   * （`LanMatch` がロビーを写す）。止まったときの行き先は `#followLan`。もう接続を持っていれば何もしない（接続は1本だけ）。
   *
   * @param address 中継の「ホスト名:ポート」（`parseRelayAddress` で検証したもの）
   */
  startLan(address: string): void {
    if (!this.#flow.startConnecting()) return;
    const runner = new LanMatch({
      address,
      keyboard: this.#tools.keyboard,
      pads: this.#pads,
      lobby: this.#elements.menu,
      status: this.#elements.lanStatus,
      newSeed: this.#tools.newSeed,
      choices: this.#lobbyChoices,
      askDisconnect: () => this.#askDisconnect(false),
      uiSound: () => this.#uiSound(),
      // ロビーへ移ったら確認の画面を畳む（原型の showScreen('lobby') の closeDialog。つないでいる最中の LAN の画面で
      // 開いたままロビーへ移ったとき）。カーソルは、画面の名前が替わるので `MenuNavigator` が先頭へ戻す。
      enteredLobby: () => this.#dialog.close(),
      ...(this.#tools.connect === undefined ? {} : { connect: this.#tools.connect }),
    });
    // 自分のプレイヤー番号は、つないで受け取るまで分からない。キーの案内は、名札の一覧でこの端末のプレイヤー
    // （`local`）の分だけを出す（`describeKeyHelp`）。通信対戦ではだれもポーズできないので、横の板にはつまみも
    // 「⏸ ポーズ」も出さず、「設定へ」だけを出す（原型のゲストと同じ形。原型の `applyRoleUI`）。押すと接続を閉じて
    // タイトルへ戻る（原型の `backToSetup`）。
    const controls: SideControls = { speed: null, pause: null, quit: () => this.showMenu() };
    this.#begin(runner, this.#keyHelp(runner, { padInMatch: true, canPause: false }), controls, {
      // ラウンドの幕にはボタンを出さない（待ちで消える）。優勝の幕は、ホストで次の試合を始められるときだけ
      // 「もういっかい」を出し（原型も、次の試合を始められるのはホストだけだった）、全員に「⚙ 設定をやりなおす」を出す
      // （原型のゲストには幕が出ない。この版は全員に幕を出すので、ゲストにも抜ける道を出す）。
      bannerButtons: (view) => (view.final ? { advance: runner.canRematch, setup: true } : NO_BUTTONS),
      // 押すと合図を送るだけで、次の試合は中継が配り直した start を受け取ってから始まる。
      again: () => runner.rematch(),
      lan: runner,
      paced: false,
      padOnBanner: true,
    });
    this.#menu.render();
    // 通信対戦は等倍で進めるので、曲も等倍に戻す。盤面は同じ速さなのに曲だけ速いと、
    // 速さが変わったように見える。つまみの倍率（`#speed`）は、1台の試合に戻ったときのために残す。
    this.#tools.music.setSpeed(1);
  }

  /** 同じ選択で、新しい試合を始める（種は変わる）。1台で遊んだあとだけ有効。 */
  restart(): void {
    if (this.#lastSetup !== null) this.startLocal(this.#lastSetup);
  }

  /** 止める・再開する（1台で遊ぶときの、ラウンドの最中だけ有効。`LocalMatch.togglePause`）。 */
  togglePause(): void {
    this.#match?.runner.togglePause();
  }

  /**
   * P キーを押した（原型の keydown の `KeyP`。L3080-3081）。止める・再開する。
   *
   * 確認の画面が開いている間は何もしない（原型の keydown は確認の画面を先に見て返る。L3074-3078）。
   */
  pressPauseKey(): void {
    if (this.#dialog.open) return;
    this.togglePause();
  }

  /**
   * 窓の大きさから、盤面の大きさを決め直す（原型の `fitBoard`）。起動したときと、窓の大きさが替わったときに
   * 起動の入口が呼ぶ（ここは窓を読まない）。
   *
   * canvas の大きさを、描く面（`width`・`height`）と見た目（CSS の幅と高さ）の両方で置き直す（原型と同じ）。
   * 枠（3px）は CSS の大きさの内側に描かれるので、絵はその分だけ縮んで見える（原型と同じ）。
   * 試合の最中なら、描く部品の寸法も替える（粒子は残す）。
   */
  fitBoard(viewportWidth: number, viewportHeight: number): void {
    const layout = boardLayoutFor(viewportWidth, viewportHeight);
    this.#layout = layout;
    const canvas = this.#elements.canvas;
    canvas.width = layout.width;
    canvas.height = layout.height;
    canvas.style.width = `${layout.width}px`;
    canvas.style.height = `${layout.height}px`;
    this.#match?.renderer.resize(layout);
  }

  /**
   * キーボードのメニューのキー（矢印・Enter・Space・Escape・Backspace）を1つ押した（原型の keydown の振り分け。
   * L3074-3089）。
   *
   * 1. 確認の画面が開いていれば、確認の画面のカーソルを動かす（幕送りは届かない。P も `pressPauseKey` が止める）
   * 2. 盤面がある間（試合の画面）は、幕の Space・Enter（決定）で、カーソルの位置によらず幕を送るだけ。矢印と
   *    Escape は何もしない（原型 L3082-3084。幕のカーソルを動かせるのはパッドとマウスだけ）。試合の最中（幕が
   *    出ていない）は何も起きない
   * 3. メニューとロビーでは、カーソルを動かす（`#moveCursor`）
   */
  navigate(...commands: NavCommand[]): void {
    if (!this.#dialog.open && this.#onBoard()) {
      if (commands.includes('confirm')) this.#advanceBanner();
      return;
    }
    this.#moveCursor(commands);
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
   * 例外は、1台の試合を止めている間（ポーズ・ラウンドの幕・決まった試合。`MatchRunner.stopped`）と試合の外で、
   * そのときは原型と同じく毎フレーム忘れる（`draw`）。
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
    // 出ている通知は消さない。通知は時間でだけ消える（原型と同じ。`Toasts`）。
    // 確認の画面は畳み、ページの先頭へ戻す（原型は試合を始めるたびに startGame → showScreen('play') を通り、確認の画面を
    // 畳んで先頭へ戻す。通信対戦の最初の試合も、「もういっかい」の次の試合も同じ）。
    this.#dialog.close();
    scrollToTop(this.#elements.play);
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
    match.refresh.observe(events);
    match.renderer.afterTick(events, world);
    const after = runner.world;
    if (after !== null) match.countdown.observe(after);
    this.#noticeTakeovers(match, hud.roster);
  }

  /**
   * 通信対戦で、抜けたプレイヤーを CPU が引き継いだら（名札の一覧で人間から CPU に替わったら）、通知を出し、名札をすぐ
   * 作り直す（原型の `peer_left` の「（動物の名前） の回線が切れた → CPU が引き継ぐ」と `renderCards`。L3793。Python 版の
   * `_watch_roster` と同じく、替わった tick に出す）。呼び方は原型と同じく動物の名前。
   */
  #noticeTakeovers(match: ActiveMatch, before: Roster): void {
    const hud = match.runner.hud;
    if (hud === null) return;
    for (const id of takenOver(before, hud.roster)) {
      const player = hud.world.players.find((candidate) => candidate.id === id);
      if (player !== undefined) this.#toasts.show(cpuTookOver(lookOf(player.animal).name));
      match.refresh.request();
    }
  }

  /**
   * 画面のループから、1枚描くごとに呼ばれる。
   *
   * @param alpha 実時間での、次に `tick()` が呼ばれるまでの進み具合。1台で遊ぶときは、
   *   描く側へ渡す前に、ゲームの速さの倍率を掛けた試合の時間の進み具合に換える（`GameSpeed.progress`）。
   *   1台の試合を止めている間（`MatchRunner.stopped`）は使わず、1 を渡す
   */
  draw(alpha: number): void {
    // パッドは押したことを知らせてくれないので、描くたびに読む。決めた項目が画面を替えることがあるので、
    // 試合の部品を読むより前に、パッドの操作を反映する。1回に押し始めた操作は、まとめてカーソルへ渡す。
    // ⚠️ 読むのは毎回。受け付けないときも、前回の状態を更新し続ける（押したままのボタンを、あとで
    // 新しい押下と取り違えないため。原型も同じ）。試合の操作の押した瞬間も、ここで読んだときに残る（`PadChoice`）。
    const commands = this.#padMenu.poll();
    // パッドを見つけた知らせは、メニューの間も出す（原型もメニューの間にパッドを読み、見つけたら知らせる）。
    this.#showPadNotices();
    if (commands.length > 0) this.#padCommands(commands);
    const current = this.#current();
    // 通信対戦が止まっていたら、画面を替える（LAN の画面かタイトルへ。`#followLan`）。替えたら試合の外として描く。
    const match = current !== null && this.#followLan(current) ? null : current;
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
    // 止めている間は、盤面の上にポーズの幕を描く（原型も canvas に描く。L4566-4573）。
    // 止めている間（ポーズ・ラウンドの幕・決まった試合）は、いまの tick の位置に描く（進み具合を 1 にする）。tick を
    // 進めないので1つ前の tick の位置の控えが取り直されず、進み具合を渡し続けると、決着や止めた tick に歩いていた
    // プレイヤーが、1つ前の位置といまの位置の間を往復して見える（原型は止めている間、いまの位置に描く）。
    if (world !== null) {
      const progress = runner.stopped ? 1 : match.paced ? this.#speed.progress(alpha) : alpha;
      match.renderer.draw(world, progress, runner.paused);
    }
    const hud = runner.hud;
    match.side.update(hud, { refresh: world !== null && match.refresh.due(world), paused: runner.paused });
    // パッドを試合に繋ぐ遊び方では、ボタンのある幕の間は、毎フレーム枠を出しておく（原型 L3637。パッドを押さなくても、
    // パッドが無くても通る）。マウスを動かして消しても、次のフレームで出し直す（原型も同じ）。パッドの1回目の A を
    // 飲み込まないのは、`#padCommands` がカーソルへ渡す前にも枠を出すため（原型の注記 L3632-3636）。
    const banner = this.#syncBanner(match);
    if (banner !== null && hasButtons(banner) && match.padOnBanner) this.#nav.show(this.#navRoot());
    runner.afterDraw();
    this.#paintCursor();
    // 試合が始まる前（通信対戦のロビー）と、1台の試合を止めている間（ポーズ・ラウンドの幕・決まった試合）は、
    // 押したキーを毎フレーム忘れる（`tick` の説明。止めている間に押してすぐ離した爆弾のキーで、再開した最初の tick に
    // 爆弾を置かない。押したまま再開したときは置く。docs/06 の「原型に合わせない所」）。
    if (world === null || runner.stopped) this.#forgetTaps();
    // 試合が終わったとき・ラウンドが決まったとき・止めたとき・通信対戦が止まったとき（ずれ・切断）は曲を止める
    // （原型の `endGame` も、決まるたびに曲を止めてから勝ちの音を鳴らす）。tick が進まない間も判断できるよう、
    // 描く側で毎回見る。鳴っていれば start は何もしない（次のラウンドの頭で、曲を頭から鳴らし直す）。
    if (runner.inProgress) music.start();
    else music.stop();
  }

  /**
   * 試合の部品を作って持つ。ページの先頭へ戻すのは呼ぶ側（1台の試合は始めたとき。通信対戦は、つないだときには戻さず、
   * 試合が始まったとき。`#current`。原型も「たてる」「さんかする」では画面を替えない）。
   */
  #begin(runner: MatchRunner, help: KeyHelpFor, controls: SideControls, routes: MatchRoutes): void {
    this.#endMatch();
    this.#match = {
      runner,
      ...this.#partsFor(runner),
      ...routes,
      side: new SidePanel(this.#elements.side, help, controls),
      generation: runner.generation,
    };
    this.#showBoard(runner.world !== null);
  }

  /**
   * 通信対戦の接続の段階に合わせて、画面を替える（`LanStage`）。試合を抜けたら true。
   *
   * - ロビーへ移る前に止まった（断られた・中継に届かなかった）：接続を手放し、LAN の画面に留まって理由を出す
   *   （また押せる）。タイトルへは戻さない
   * - ロビーへ移ったあとに止まった（中継との接続が切れた・ロビーでホストが抜けた）：通知を出してタイトルへ戻す
   *   （原型の `onclose`・`peer_left` の `backToSetup`）
   *
   * ⚠️ いまの試合（`#match`）の段階だけを見る。抜けたあとの接続（閉じた `LanMatch`）は誰も持たないので、閉じたことが
   * 遅れて届いても、次につないだ接続や1台の試合に触らない。
   */
  #followLan(match: ActiveMatch): boolean {
    const stage = match.lan?.stage;
    if (stage?.kind === 'cannotJoin') {
      this.#endMatch();
      this.#flow.connectionFailed(stage.reason);
      this.#menu.render();
      this.#showBoard(false);
      return true;
    }
    if (stage?.kind === 'lost') {
      this.#toasts.show(stage.notice);
      this.showMenu();
      return true;
    }
    return false;
  }

  #partsFor(runner: MatchRunner): MatchParts {
    // 名札の一覧は通知を出すたびに尋ねる（通信対戦では、抜けたプレイヤーが CPU に替わる）。
    const presenter = new Presenter(this.#tools.sounds, this.#toasts, () => runner.hud?.roster ?? []);
    return {
      renderer: new Renderer(this.#tools.context, this.#layout),
      presenter,
      banner: new RoundBanner(),
      countdown: new Countdown(this.#tools.sounds),
      refresh: new PanelRefresh(),
    };
  }

  /**
   * 盤面が有れば試合の画面を、無ければ試合の前の画面を出す。
   *
   * 通信対戦では、試合が始まるまで盤面が無い。その間は同じ場所にロビーを出す。
   *
   * 切り替えるときは、確認の画面を畳む（原型の `showScreen` の `MENU.closeDialog`。L5679-5687）。⚠️ いまは、ここが畳む
   * 前に別の所が畳む。ロビーで確認の画面を開いたままホストが試合を始めたとき（原型の注記。畳まないと盤面が確認の画面に
   * 覆われたままになる）は、次の試合の部品を作る `#current` が先に畳み、1台の試合を始めるときと試合からタイトルへ戻る
   * ときは `#endMatch` が先に畳む。ここが畳む道は無いが、原型の showScreen と同じ形の備えとして残す。
   */
  #showBoard(board: boolean): void {
    if (this.#elements.play.hidden === board) this.#dialog.close();
    this.#elements.menu.hidden = board;
    this.#elements.play.hidden = !board;
  }

  /** 盤面がある間（試合の画面）か。 */
  #onBoard(): boolean {
    const match = this.#match;
    return match !== null && match.runner.world !== null;
  }

  /** いま出す幕（ラウンドの幕・優勝の幕）。無ければ null。 */
  #bannerOf(match: ActiveMatch): BannerView | null {
    const world = match.runner.world;
    return world === null ? null : match.banner.current(world);
  }

  /**
   * 幕を要素に写す（同じ幕なら要素に触れない）。幕を出していれば、並べたボタンを返す。出していなければ null。
   *
   * 描くときと、パッドの操作を反映する前に呼ぶ（決着の tick のあとの最初のフレームで押したパッドも、幕のボタンへ届く）。
   */
  #syncBanner(match: ActiveMatch): BannerButtons | null {
    const view = this.#bannerOf(match);
    const buttons = view === null ? NO_BUTTONS : match.bannerButtons(view);
    this.#bannerView.show(view, buttons);
    return view === null ? null : buttons;
  }

  /**
   * 幕を送る（原型の `advanceBanner`。L4514-4524）。1つ目のボタンを出している幕でだけ反映する。
   *
   * 入口はキーボードの Space・Enter・パッドの Start・1つ目のボタン（マウスとカーソル）。
   *
   * - 1台：ラウンドの幕なら次のラウンド（`MatchRunner.startNextRound`）、優勝の幕なら同じ設定で新しい試合
   *   （`restart`。CPU の動物も選び直す。原型の `startGame` と同じ）
   * - 通信対戦：ラウンドの幕にはボタンが無いので何もしない。優勝の幕は、ホストが次の試合の合図を送る（`rematch`）
   *
   * 押したまま送っても、次のラウンドの開始位置に爆弾は置かれない（ラウンドの始まりは、爆弾と技のボタンを押していた
   * 扱い。`WorldState.ts` の `HELD_AT_ROUND_START`）。
   */
  #advanceBanner(): void {
    const match = this.#current();
    if (match === null) return;
    const view = this.#bannerOf(match);
    if (view === null || !match.bannerButtons(view).advance) return;
    if (view.final) match.again();
    else match.runner.startNextRound();
  }

  /**
   * パッドで1回に押し始めた操作を渡す（原型の `pollGamepads` の画面の分かれ道。L3612-3652）。
   *
   * - メニューとロビー：カーソルへ
   * - 幕：パッドを試合に繋ぐ遊び方（`padOnBanner`）で、ボタンのある幕のときだけ受け付ける（通信対戦のラウンドの幕は
   *   何もしない。Python 版と同じ）。Start は幕を送る近道（確認の画面が開いていても。原型 L3631）、ほかは枠を出して
   *   からカーソルへ（1回目の A を飲み込まない。原型 L3637）
   * - 確認の画面が開いていれば、カーソルへ（Start で止めない。原型 L3612-3617）
   * - 試合の最中：パッドを試合に繋ぐ遊び方のときだけ。1台は Start で止める・再開する（原型 L3643-3645。止められるのは
   *   ラウンドの最中だけ。`LocalMatch.togglePause`）。Select は、1台ならポーズ中（同じ回の Start で止めたときも）、
   *   通信対戦ならいつでも「設定へもどりますか？」を開く（原型 L3651。通信対戦はだれも止められないので、原型の
   *   ゲストと同じく止めずに開く。開いている間も、試合への入力は止めない）
   */
  #padCommands(commands: readonly NavCommand[]): void {
    const match = this.#current();
    if (match === null || match.runner.world === null) {
      this.#moveCursor(commands);
      return;
    }
    const banner = this.#syncBanner(match);
    if (banner !== null) {
      if (!match.padOnBanner || !hasButtons(banner)) return;
      if (commands.includes('start')) {
        this.#advanceBanner();
        return;
      }
      // 枠を出してからカーソルへ渡す（原型も L3637 で枠を出してから L3639 の MENU.nav へ渡す）。描く側の毎フレームの
      // 枠（`draw`）だけでは、マウスを動かして枠を消した直後のフレームの A が、枠を出すだけで飲み込まれる。
      this.#nav.show(this.#navRoot());
      this.#moveCursor(commands);
      return;
    }
    if (this.#dialog.open) {
      this.#moveCursor(commands);
      return;
    }
    if (!match.padOnBanner) return;
    if (match.paced && commands.includes('start')) match.runner.togglePause();
    if (commands.includes('select') && (match.runner.paused || !match.paced)) this.#askBackToSetup();
  }

  /**
   * 「設定へもどりますか？」を開く（原型の `askBackToSetup`。L3384-3387）。
   *
   * 開くと枠を出す（原型の `MENU.on = true`）。パッドで開いたので、どちらを選んでいるかを見せる。
   */
  #askBackToSetup(): void {
    this.#dialog.ask('backToSetup', () => this.showMenu());
    this.#nav.show(this.#dialog.root);
  }

  /**
   * 「せつぞくを切ります。よいですか？」を開く（原型の `askDisconnect`。L3391-3398）。「せつぞくを切る」を選ぶと、接続を
   * 閉じてタイトルへ戻る（`showMenu`。原型の `NET.disconnect(); backToSetup();`）。
   *
   * 入口は、ロビーの「← せつぞくを切る」と B、つないでいる最中の LAN の画面の「← もどる」と B。
   * 枠は、キーかパッドで開いたときだけ出す（`viaKeys`）。原型は `askDisconnect` で `MENU.on` を立てない（L3381-3383：
   * マウスで押した端末に枠を出さない）。キーとパッドの B は、原型の `MENU.nav` が枠を出してから開く。
   *
   * 開いていれば何もしない（`ConfirmDialog.ask` は閉じているときに呼ぶ）。いまは届かない：開いている間のキーとパッドは
   * 確認の画面へ回り、マウスは確認の画面の覆いが下のボタンを押させない。
   */
  #askDisconnect(viaKeys: boolean): void {
    if (this.#dialog.open) return;
    this.#dialog.ask('disconnect', () => this.showMenu());
    if (viaKeys) this.#nav.show(this.#dialog.root);
  }

  /**
   * カーソルを動かす（原型の `MENU.nav`）。動かす画面は `#navRoot`。
   *
   * 戻る（Escape・B）は、確認の画面なら「やめる」（原型 L3329-3332）、ロビーと、つないでいる最中の LAN の画面なら
   * 切るかの確認の画面（原型 L3335）、ほかの試合の前の画面なら1つ前の画面。幕では何もしない（原型の `MENU_BACK` に
   * 幕が無い）。
   *
   * つないでいる最中の LAN の画面は「たてる」「さんかする」を出さないのでカーソルの項目が無く、カーソルは戻るを返さない。
   * それでも戻るで確認の画面を開く（原型はボタンが残るので、B で確認を開ける。Python 版と同じ）。ゲストのロビーも項目が
   * 無いが、こちらは原型のコードのとおり何も起きない（原型の `MENU.nav` は項目が無ければ何もしない。L3291）。
   */
  #moveCursor(commands: readonly NavCommand[]): void {
    const root = this.#navRoot();
    const result = this.#nav.handle(root, commands);
    if (root === this.#dialog.root) {
      if (result.kind === 'back') this.#dialog.cancel();
      return;
    }
    const match = this.#match;
    const lan = match?.lan ?? null;
    if (match !== null && lan !== null && match.runner.world === null) {
      if (result.kind === 'back' || (lan.stage.kind === 'connecting' && commands.includes('back'))) this.#askDisconnect(true);
      return;
    }
    if (result.kind === 'back' && match === null) {
      this.#menu.back();
      this.#nav.paint(root);
    }
  }

  /** パッドについての知らせ（見つけた・対応していない）を、通知に出す（`PadChoice` の「画面に知らせること」）。 */
  #showPadNotices(): void {
    for (const notice of this.#pads.takeNotices()) {
      this.#toasts.show(notice.kind === 'found' ? PAD_FOUND : padUnsupported(notice.id));
    }
  }

  /**
   * カーソルで動かす画面。確認の画面が開いていればそれ（下の画面の印には触らない。原型も確認の画面の2つだけを
   * 塗る）。試合の前はメニュー、通信対戦で盤面がまだ無い間はロビー（同じ場所に出す）、盤面があれば幕。
   */
  #navRoot(): HTMLElement {
    if (this.#dialog.open) return this.#dialog.root;
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

  /**
   * 試合を抜ける。横の板を空にし、幕と確認の画面を畳む。
   *
   * 出ている通知は消さない（原型の `backToSetup` も触らない。タイトルへ戻ったあとも、残りの時間だけ出る）。
   */
  #endMatch(): void {
    this.#match?.runner.close();
    this.#match = null;
    this.#bannerView.show(null);
    this.#dialog.close();
    this.#elements.side.replaceChildren();
  }

  #setSpeed(rate: number): void {
    this.#speed.set(rate);
    this.#tools.music.setSpeed(rate);
  }

  #sourceFor(id: PlayerId, controller: LocalController, seed: number): InputSource {
    if (controller.kind === 'cpu') return new CpuInputSource(id, CPU_LEVELS[controller.level], cpuSeed(seed, id));
    const keyboard = new KeyboardInputSource(id, this.#tools.keyboard, KEY_LAYOUTS[controller.layout]);
    if (!drivesPad(controller)) return keyboard;
    return new CombinedInputSource([keyboard, new GamepadInputSource(id, this.#pads)]);
  }
}
