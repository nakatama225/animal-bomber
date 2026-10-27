import { CPU_LEVEL_KEYS, CPU_LEVELS } from '../../ai/CpuLevel.js';
import { ANIMAL_LOOKS, type AnimalLook } from '../../content/animals.js';
import { formatSeconds, HIT_CHOICES, TIME_CHOICES, WIN_CHOICES } from '../../presentation/menu/choices.js';
import { keyHintsFor } from '../../presentation/menu/keyHints.js';
import type { LocalSetup } from '../../presentation/menu/localSetup.js';
import {
  CHANGELOG,
  LEGEND,
  MANUAL,
  VERSION_LINE,
  type ManualLine,
  type ManualSpan,
  type VersionKind,
} from '../../presentation/menu/manual.js';
import {
  BACK_LABEL,
  CPU_HEADING,
  CPU_NOTE,
  cpuTag,
  HIT_LABELS,
  HIT_NOTE,
  hitsLabel,
  LOG_LABEL,
  LOGO,
  MANUAL_HEADING,
  MANUAL_LABEL,
  NEXT_LABEL,
  onOff,
  PICK_HEADING,
  PICK_STEP,
  pickerHeading,
  RULES_HEADING,
  RULES_STEP,
  SOUND_CHOICES,
  SOUND_LABEL,
  START_LABEL,
  SUBTITLE,
  SUDDEN_LABEL,
  SUDDEN_NOTE,
  TIME_LABEL,
  TIME_NOTE,
  TITLE_ITEMS,
  WINS_LABEL,
  WINS_NOTE,
  winsLabel,
  type TitleChoice,
  type TitleItem,
} from '../../presentation/menu/menuText.js';
import type { MenuFlow, MenuScreen, SoundSetting } from '../../presentation/menu/MenuFlow.js';
import { chipBox, el, pointerButton, scrollToTop } from './dom.js';

/** 画面の外へ知らせること。 */
export interface MenuHooks {
  /** 「はじめる」が押された。 */
  readonly start: (setup: LocalSetup) => void;
  /** 音の設定が変わった。 */
  readonly soundChanged: (sound: SoundSetting) => void;
  /** LAN対戦を選んだ。 */
  readonly openLan: () => void;
  /**
   * 画面の操作の音を鳴らす（原型の `A.init(); A.resume(); SE.ui();`）。音を出せるようにする（解錠）のも、
   * 呼ぶ側がここで行う。
   */
  readonly uiSound: () => void;
  /** 画面が替わった（原型の `showScreen`）。確認の画面を畳むのに使う（`showScreen` の `MENU.closeDialog`。L5687）。 */
  readonly screenChanged: () => void;
}

/** CPU の行の頭の札に、原型が直に付けた見た目（L5952）。 */
const CPU_TAG_STYLE = 'margin:0 8px 0 0;opacity:.8;align-self:center';

/**
 * 試合の前の画面（タイトル・キャラ選び・ルール・設定とマニュアルと更新履歴）。
 *
 * どの画面にいて何を選んだかは `MenuFlow` が持つ。ここはそれを写し、押されたら
 * `MenuFlow` を呼んで写し直すだけ。文は `presentation/menu/menuText.ts`（と `manual.ts`・`keyHints.ts`・
 * `content/animals.ts`）から読む。要素の並びとクラス名は原型の HTML（L245-511）と同じにして、原型の CSS を
 * そのまま当てる（`style.css`）。
 *
 * ⚠️ ボタンは全部 `pointerButton`（キーボードで起きたクリックを捨てる）で作る。
 * キーボードやパッドで動かすときは、メニューのカーソル（`MenuNavigator`）が同じ中身を呼ぶ。
 * カーソルに載せる項目には `data-nav`（グループの名前）を付ける。縦に並ぶものは1つずつ別の名前に、
 * 横に並ぶもの（動物の一覧・選択肢の1行）は同じ名前にする。
 *
 * ## 画面の操作の音
 *
 * 原型と同じ所で鳴らす：タイトルの5つ・「← もどる」・「つぎへ ▶」・チップ全部・動物のカード・B で1つ前の
 * 画面へ戻ったとき（原型 L5706・L5642・L6014・L3337）。カーソルで決めたときも同じ中身を呼ぶので同じく鳴る。
 * 「はじめる」は鳴らさない（原型 L6027）。
 * 音のチップは、選んだあとの設定で聞こえ方が決まる（原型と同じ）。「無音」は鳴らしてから音を切り（ほとんど聞こえない）、
 * 「無音」から戻すときは音を戻してから鳴らす（`#chooseSound`）。
 */
export class MenuView {
  readonly #root: HTMLElement;
  readonly #flow: MenuFlow;
  readonly #hooks: MenuHooks;
  /** 最後に組み立てた画面。替わったときだけページの先頭へ戻す。 */
  #shown: MenuScreen | null = null;

  constructor(root: HTMLElement, flow: MenuFlow, hooks: MenuHooks) {
    this.#root = root;
    this.#flow = flow;
    this.#hooks = hooks;
  }

  /**
   * いまの画面を組み立て直す。
   *
   * タイトルは箱（`.card`）で包まない（原型 L245-263）。ほかの画面は箱で包む。画面が替わったら、
   * ページの先頭へ戻し（原型の `showScreen` の `window.scrollTo(0,0)`。L5697）、外へ知らせる（`screenChanged`）。
   * 同じ画面で選び直しただけなら、どちらもしない。
   */
  render(): void {
    const screen = this.#flow.screen;
    const body =
      screen === 'title'
        ? el('div', { data: { screen } }, this.#title())
        : el('div', { className: 'card', data: { screen } }, { pick: () => this.#pick(), rules: () => this.#rules(), manual: () => this.#manual() }[screen]());
    this.#root.replaceChildren(body);
    if (screen === this.#shown) return;
    this.#shown = screen;
    scrollToTop(this.#root);
    this.#hooks.screenChanged();
  }

  /** 1つ前の画面へ戻る（Escape・B）。戻ったら画面の操作の音を鳴らす。タイトルでは何もしない（音も鳴らさない）。 */
  back(): void {
    if (this.#flow.screen === 'title') return;
    this.#hooks.uiSound();
    this.#flow.back();
    this.render();
  }

  /** 押されたら画面の操作の音を鳴らし、`change` を呼んで、画面を写し直す。 */
  #press(change: () => void): () => void {
    return () => {
      this.#hooks.uiSound();
      change();
      this.render();
    };
  }

  #title(): HTMLElement[] {
    return [
      el('div', { className: 'titleWrap' }, [
        el('div', { className: 'logoPlate' }, [el('span', { className: 'logo', text: LOGO })]),
        el('div', { className: 'logoSub', text: SUBTITLE }),
        el('div', { className: 'ver', text: VERSION_LINE }),
      ]),
      el('div', { className: 'menu' }, TITLE_ITEMS.map((item) => this.#titleButton(item))),
    ];
  }

  #titleButton(item: TitleItem): HTMLElement {
    // 縦に並ぶので、1つずつ別のグループにする（上下で選ぶ）。
    const button = pointerButton('', this.#press(() => this.#choose(item.choice)), {
      className: item.small ? 'mbtn sub' : 'mbtn',
      data: { choice: item.choice, nav: `choice-${item.choice}` },
    });
    // 題は `.mbtn` の字のまま（原型も題に要素を作らない）。
    button.append(
      el('span', { className: 'mi', text: item.icon }),
      el('span', {}, [document.createTextNode(item.title), el('span', { className: 'md', text: item.detail })]),
    );
    return button;
  }

  #choose(choice: TitleChoice): void {
    if (choice === 'lan') this.#hooks.openLan();
    else if (choice === 'manual') this.#flow.openManual();
    else this.#flow.chooseMode(choice);
  }

  /** 画面の頭（原型の `.shead`）。「← もどる」はカーソルに載せない（戻るは Escape・B）。 */
  #head(title: string, step?: string): HTMLElement {
    return el('div', { className: 'shead' }, [
      pointerButton(BACK_LABEL, this.#press(() => this.#flow.back()), { className: 'backb', data: { action: 'back' } }),
      el('h2', { text: title }),
      step === undefined ? null : el('span', { className: 'step', text: step }),
    ]);
  }

  /** 下のボタンの列（原型の `.navbar`）。 */
  #navbar(button: HTMLElement): HTMLElement {
    return el('div', { className: 'navbar' }, [button]);
  }

  #pick(): HTMLElement[] {
    const pickers: HTMLElement[] = [];
    keyHintsFor(this.#flow.sizes.humans).forEach((hint, index) => {
      const human = index as 0 | 1;
      // 原型は P1 と P2 の段の間に、高さ 6px の空きを挟む（L6019）。
      if (index > 0) pickers.push(el('div', { style: 'height:6px' }));
      pickers.push(
        el('div', { data: { human: String(human) } }, [
          el('div', { className: 'pickhdr' }, [
            el('span', { className: 'who', text: pickerHeading(human) }),
            el('span', { className: 'keys', text: hint }),
          ]),
          el('div', { className: 'animals' }, ANIMAL_LOOKS.map((look) => this.#animalCard(human, look))),
        ]),
      );
    });
    return [
      this.#head(PICK_HEADING, PICK_STEP),
      el('div', { className: 'row' }, pickers),
      this.#navbar(pointerButton(NEXT_LABEL, this.#press(() => this.#flow.next()), { className: 'go', data: { action: 'next', nav: 'go' } })),
    ];
  }

  /**
   * 動物のカード（原型の `.acard`）。
   *
   * 原型の要素は `div` だが、ここは `pointerButton` の `button`（キーボードで起きたクリックを捨てる）にして、
   * 原型の CSS を当てる。
   */
  #animalCard(human: 0 | 1, look: AnimalLook): HTMLElement {
    const chosen = this.#flow.setup.picks[human] === look.key;
    const card = pointerButton('', this.#press(() => this.#flow.pick(human, look.key)), {
      className: chosen ? 'acard on' : 'acard',
      data: { animal: look.key, nav: `pick-${human}` },
    });
    card.append(
      el('div', { className: 'ae', text: look.emoji }),
      el('div', {}, [el('div', { className: 'an', text: look.name }), el('div', { className: 'ad', text: look.description })]),
    );
    return card;
  }

  /**
   * ルールをきめる（原型 L315-349・`buildHpRows`・`buildCpuRows`）。2列で、左の列は体力と CPU の強さ、右の列は
   * 勝ち数・制限時間・サドンデス。カーソルは要素の並びの順に集めるので、左の列を降りてから右の列へ行く（原型と同じ）。
   */
  #rules(): HTMLElement[] {
    const { humans, cpus } = this.#flow.sizes;
    const setup = this.#flow.setup;
    const who: ('p1' | 'p2' | 'cpu')[] = ['p1'];
    if (humans > 1) who.push('p2');
    if (cpus > 0) who.push('cpu');
    const hits = el('div', { className: 'row' }, [
      ...who.flatMap((key) => [
        el('label', { className: 'lb', text: HIT_LABELS[key] }),
        this.#chips(`hits-${key}`, HIT_CHOICES, setup.hits[key], hitsLabel, (n) => this.#flow.setHits(key, n), 'margin-bottom:12px'),
      ]),
      el('div', { className: 'note', text: HIT_NOTE }),
    ]);
    // CPU のいない遊び方では、箱だけを残して中を空にする（原型の `#cpuWrap`）。
    const cpuRows = setup.cpuLevels.slice(0, cpus).flatMap((level, index) => [
      el('span', { className: 'lb', text: cpuTag(index), style: CPU_TAG_STYLE }),
      this.#chips(`cpu-${index}`, CPU_LEVEL_KEYS, level, (key) => CPU_LEVELS[key].label, (key) => this.#flow.setCpuLevel(index as 0 | 1 | 2, key), 'margin-bottom:8px'),
    ]);
    const cpu = el(
      'div',
      { className: 'row' },
      cpus === 0
        ? []
        : [
            el('label', { className: 'lb', text: CPU_HEADING }),
            ...cpuRows,
            el('div', { className: 'note' }, [document.createTextNode(CPU_NOTE[0]), el('br'), document.createTextNode(CPU_NOTE[1])]),
          ],
    );
    const right = el('div', {}, [
      this.#ruleRow(WINS_LABEL, this.#chips('wins', WIN_CHOICES, setup.winsToTake, winsLabel, (n) => this.#flow.setWinsToTake(n)), [
        document.createTextNode(WINS_NOTE),
      ]),
      this.#ruleRow(TIME_LABEL, this.#chips('time', TIME_CHOICES, setup.roundSeconds, formatSeconds, (n) => this.#flow.setRoundSeconds(n)), TIME_NOTE.map(spanNode)),
      this.#ruleRow(SUDDEN_LABEL, this.#chips('sudden', [true, false], setup.suddenDeath, onOff, (on) => this.#flow.setSuddenDeath(on)), [
        document.createTextNode(SUDDEN_NOTE),
      ]),
    ]);
    return [
      this.#head(RULES_HEADING, RULES_STEP),
      el('div', { className: 'cols' }, [el('div', {}, [hits, cpu]), right]),
      // 「はじめる」は画面の操作の音を鳴らさない（原型 L6027）。
      this.#navbar(pointerButton(START_LABEL, () => this.#hooks.start(this.#flow.setup), { className: 'go', data: { action: 'start', nav: 'go' } })),
    ];
  }

  /** 右の列の1行（見出し・チップ・注記）。 */
  #ruleRow(label: string, chips: HTMLElement, note: readonly Node[]): HTMLElement {
    return el('div', { className: 'row' }, [el('label', { className: 'lb', text: label }), chips, el('div', { className: 'note' }, note)]);
  }

  /**
   * 設定・マニュアル・更新履歴（原型 L352-511）。カーソルに載るのは音の設定の1行だけ。マニュアルと更新履歴は
   * 高さの決まった箱の中をマウスのホイールで読む（原型と同じ。矢印ではページも箱も動かない）。
   */
  #manual(): HTMLElement[] {
    const label = (value: SoundSetting): string => SOUND_CHOICES.find((choice) => choice.value === value)?.label ?? value;
    return [
      this.#head(MANUAL_HEADING),
      el('div', { className: 'row' }, [
        el('label', { className: 'lb', text: SOUND_LABEL }),
        chipBox('sound', SOUND_CHOICES.map((choice) => choice.value), this.#flow.sound, label, (value) => this.#chooseSound(value)),
      ]),
      el('div', { className: 'msec' }),
      el('label', { className: 'lb', text: MANUAL_LABEL }),
      el('div', { className: 'manual hb' }, manualNodes(MANUAL)),
      el('div', { className: 'msec' }),
      el('div', { className: 'row' }, [
        el('label', { className: 'lb', text: LOG_LABEL }),
        el(
          'div',
          { className: 'note', style: 'margin-bottom:8px;opacity:.85' },
          LEGEND.flatMap((entry) => [versionTag(entry.kind, entry.label), document.createTextNode(entry.after)]),
        ),
        el(
          'div',
          { className: 'log' },
          CHANGELOG.map((entry) =>
            el('div', { className: entry.large ? 'lg' : 'lp' }, [versionTag(entry.kind, entry.version), ...entry.body.map(spanNode)]),
          ),
        ),
      ]),
    ];
  }

  /**
   * 音のチップが押された。画面の操作の音は、選んだあとの設定で効果音が鳴るかどうかで聞こえ方が決まる（原型と同じ）。
   *
   * 原型は操作の音を予約してから、同じ処理の中で効果音の音量を変える（L5642・L5780-5782・L850）。そのため
   * 「無音」を選ぶとほとんど聞こえず、「無音」から戻すと聞こえる。この版は、効果音を切っている間は音の部品を作らない
   * （`WebAudioSoundBank.play`）。そこで、音を切る向き（「無音」）は鳴らしてから切り、音を戻す向きは音の設定を
   * 変えてから鳴らす。
   */
  #chooseSound(value: SoundSetting): void {
    const apply = (): void => {
      this.#flow.setSound(value);
      this.#hooks.soundChanged(value);
    };
    if (value === 'off') {
      this.#hooks.uiSound();
      apply();
    } else {
      apply();
      this.#hooks.uiSound();
    }
    this.render();
  }

  /** チップの箱。押されたら画面の操作の音を鳴らしてから選び（原型 L5642 と同じ順）、写し直す。 */
  #chips<T>(id: string, choices: readonly T[], current: T, text: (value: T) => string, choose: (value: T) => void, style?: string): HTMLElement {
    return chipBox(
      id,
      choices,
      current,
      text,
      (value) => {
        this.#hooks.uiSound();
        choose(value);
        this.render();
      },
      style,
    );
  }
}

/** 文の1区切りを要素にする（太字は `b`、キーは `kbd`、プログラムの字は `code`。原型と同じ要素）。 */
function spanNode(span: ManualSpan): Node {
  switch (span.kind) {
    case 'text':
      return document.createTextNode(span.text);
    case 'bold':
      return el('b', { text: span.text });
    case 'key':
      return el('kbd', { text: span.text });
    case 'code':
      return el('code', { text: span.text });
  }
}

/** マニュアルの行を `br` で区切って並べる（空の行は、空けた行になる。原型の `<br><br>`）。 */
function manualNodes(lines: readonly ManualLine[]): Node[] {
  return lines.flatMap((line, index) => [...(index > 0 ? [el('br')] : []), ...line.map(spanNode)]);
}

/** 更新履歴の版の札（原型：MAJOR と MINOR は `b`、PATCH は `span`）。 */
function versionTag(kind: VersionKind, text: string): HTMLElement {
  switch (kind) {
    case 'major':
      return el('b', { className: 'vmaj', text });
    case 'minor':
      return el('b', { className: 'vmin', text });
    case 'patch':
      return el('span', { className: 'vpat', text });
  }
}
