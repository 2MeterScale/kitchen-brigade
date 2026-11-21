# 厨房の決まり（どの持ち場も最初に読む。七キロ以下に保つ）

## Start here (6 lines)
1. Read your `MEMORY.md` index only; never all notes.
2. Before asking or re-deriving: `python3 Tools/kitchen/notes.py recall "<words>" [--role r]`, then `notes.py show <slug> [--lines a-b]`.
3. Before reading code: `python3 Tools/kitchen/codemap.py find <Name> [--refs]` / `outline <path>` / `where "<words>"`.
4. Read line ranges (Read offset/limit), not whole files.
5. Write learnings with `notes.py add <role> --title … --tags … [--supersedes <slug>] < body`. One topic per note. Do not hand-append to `MEMORY.md`.
6. Narrate in English, tersely. Full report to a file `/tmp/<project>/reports/<job>.md`, five lines back (done?, branch and head, tests, key finding, report path).

## 何を作っているか
<目的を三、四行。何ができたら成功で、何が失敗か。本人が一貫して嫌う事>

## 正本
- <設計書、原稿、仕様の場所>。仕事に関わる所を、仕事の前に読む。
- <本人が承認した物の場所>。変えない。
- 進みの記録: <場所>（シェフが書く）。

## 作業の場所
- <どこで作業するか。作業場所を分けるなら、最初にどこまで進めるか>
- <保存、コミット、名前の決まり>
- 自分の持ち場の外の物は、どうしても要るときだけ、少しだけ。報告に「どこを、なぜ」と書く。
- <まとめ役だけが変えてよい物>

## この環境の仕掛け
- <役が毎回つまずいた事と、抜け方>
- <使ってはいけない操作。外へ出してはいけない物>

## 確かめ
- <何を、どう確かめるか。試験、通し読み、絵を出して見る、など>
- 確かめをゆるめて通さない。決まりを変えたら、何をなぜ変えたかを報告に書く。
- 見るのは、頼まれた項目ではなく、目的。受け取る人のやり方で、自分が先に受け取る。

## 仕事の終わりに（毎回）
1. **札を足す。** `notes.py add`。次に同じ持ち場の仕事をする自分が知っていたら早かった事。外れた札は `--supersedes`。経過は書かない。
2. 報告はファイルへ書き、五行を返す。できた物、途中の物、手を付けていない物。確かめの結果。ほかの持ち場に手を入れた所。**自分で見て弱い所。** 見ていない物を「確かめた」と書かない。

## 経緯と長い説明
- 決まりの理由や経緯は、`kitchen` 持ち場の札へ（`notes.py recall "<話題>" --role kitchen`）。この頁は決まりだけ。
