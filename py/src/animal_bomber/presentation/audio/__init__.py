"""音。原型（`legacy/animal-bomber.html`）が Web Audio で合成していた音を numpy で写す。

原型は音のファイルを持たず、効果音も曲も、波形とノイズに音量と周波数の予定を入れて
その場で合成していた。この版も同じ数値と式から合成し、起動時に pygame の Sound に
焼いておく。流れは次のとおり。

1. 表（`recipes.py`・`added_recipes.py`・曲は `score.py`）… 原型の `SE` と `BGM` の
   数値と式
2. 値の動き（`voices.py`）… 原型の `tone()`・`noiseBurst()`・`BGM.note` が Web Audio に
   入れていた予定。原型を node で読み込んで書き出した固定値と、同じ予定かを確かめる
3. 合成（`synth.py`）… 予定を Web Audio の仕様の式で読み、音の配列にする
4. 焼く（`bank.py`・`music.py`）… pygame の mixer の周波数で焼き、鳴らすときは再生だけ

鳴らす場面を決めるのは `presenter.py`（イベントから効果音と、決着の tick に曲を
止めること）と `countdown.py`（残り時間の秒読み）と `music.py` の `RoundMusic`（曲の
鳴らし始め）。
"""
