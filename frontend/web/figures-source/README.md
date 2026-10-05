# 成員自己的 3D 人物（D-196～D-199）

不對外提供的原始檔。網站載入的是匯出後的 `public/models/characters/<avatar_key>.glb`。

## 做法：乾淨的低模加上畫出來的細節（D-198）

動森的人物是「簡單平滑的形體，加上畫得很銳利的細節」。前兩版都沒做到：

- D-196 用基本形體拼裝，接縫明顯。
- D-197 先雕高模再減面、烘焙，結果表面坑坑疤疤，細節糊成一片。

D-198 改成直接做乾淨的低模，所有細節用畫的：

1. **形體**（`figure.py` 的 `surface`、`ring`、`sweep`）：每個部位是一圈圈刻意擺放的環，連成四邊形網格，對稱的部位用 `mirror` 鏡射。表面平滑，沒有減面造成的碎面。每個部位在建立時就有自己的 UV：
   - 環狀部位（身體、手臂、腿、靴子、裙子）：u 繞一圈、v 沿著長度。
   - 頭：正面平面投影（`planar_front`），畫在那裡的就是正面看到的樣子；側面和後面捲成一條帶子。
   - 頭髮：每一束沿著長度展開。
2. **細節全部用畫的**（`figure.py` 的 `Canvas`）：每個部位一張自己的畫布，單位是公尺。用抗鋸齒的形狀（橢圓、圓角方塊、色帶）和頭尾粗細不同的筆畫來畫眼睛、眉毛、腮紅、背心滾邊、吊帶、扣環、護臂、手套、靴子綁帶、髮絲。
3. **組裝**（`assemble`）：
   - 畫布排進一張 2048 的圖集。
   - 部位合成一個網格、一個材質，再依部位給權重。頭、頭髮、耳朵整塊跟 `head`；手臂在肩膀和軀幹平滑過渡；裙子前襬部分跟腿，坐下時會被大腿撐起。
   - 最後烘一次整個模型自己的環境遮蔽，乘進圖集，讓瀏海下、下巴下、裙子裡有柔和的陰影。
4. **匯出**（`export.py`）：GLB 內含 JPEG 貼圖。

比例是在參考圖上打格線量的，顏色從參考圖取樣：正面 `avatars-source/q`、背面 `back`、側面 `stand-side`。座標：Blender 是 Z 軸朝上，人物面向 −Y，她的左邊是 +X。靜止姿勢是 Kenney 的 T 字（手臂平舉），動畫才會對；手臂在待機時垂多低，是 Kenney 的 `idle` 決定的。

辦公室會把 Kenney 人物的頭縮成 0.8 倍（T-413）。自有人物是照參考圖的比例做的，所以頭維持 1 倍（`AvatarController` 的 `headScale`）。

## 預算

- 每個人物最多 10,000 個三角形（`check-assets`，D-198 起；原為 3,000）。
- Tifa 用了 5,616 個，GLB 645 KB；Ada 4,964 個，564 KB。
- 每個人物的貼圖在顯示卡裡約佔 21 MB（2048 圖集），這比三角形更吃資源。人數變多時，先考慮把圖集降到 1024 或改用壓縮貼圖。

## 檔案

| 檔案 | 用途 |
|---|---|
| `blender/lib.py` | 載入 Kenney 骨架（`reset`、`rig`）與一些舊版基本形體 |
| `blender/figure.py` | 共用：網格（`ring`、`surface`、`ellipsoid`、`sweep`、`mirror`、`rim`、`planar_front`）、畫布（`Canvas`）、動森的頭與臉（`ac_head`、`ac_face`、`ac_ears`、`ac_nose`）、頭髮（`Hair`：髮蓋、髮片、垂下的長髮）、組裝與烘焙（`part`、`assemble`） |
| `blender/tifa.py`、`ada.py` | 每個人自己的配色、服裝、髮型和畫上去的細節 |
| `blender/export.py` | 匯出 GLB（需先設定 `OUT`、`BUDGET`） |
| `blender/build.sh` | 背景執行整條流程：`./build.sh tifa` 寫出 `public/models/characters/tifa.glb` 和 `tifa.blend`（約 45 秒），並複製一份到使用者本機的存檔區 `data/blender/tifa-<三角形數>.blend`：做滿 1 萬上限（9,500 以上）的叫 `-9999`，其他直接寫實際面數（例如 `ada-4964`）；`data/` 不進 git |
| `blender/<avatar_key>.blend` | 成品，可以直接打開看 |
| `blender/bl.py` | 把腳本送進開著的 Blender（MCP for Blender 附加元件，`localhost:9876`）邊做邊看：`python3 bl.py run lib.py figure.py tifa.py`（約 15 秒）；`shot` 拍視圖截圖 |
| `blender/render.py`、`montage.py`、`pose.py` | 預覽：背景算圖（可套動畫）、拼圖 |

## 做下一位

**比例一律照 Tifa**（使用者的決定，D-199）：頭（`ac_head`）、身體、手臂的數字都沿用，頭到腳總高一樣。參考圖的比例不一定一致（例如 Ada 的參考圖腿太長），只取髮型、臉、服裝。

1. 複製最接近的一位（長髮看 `tifa.py`，短髮看 `ada.py`）成 `<avatar_key>.py`，改配色、服裝、髮型和畫布上的內容。共用的東西留在 `figure.py`。
2. 在參考圖上量比例。可以用 Blender 的 numpy 在圖上打格線、取樣顏色。
3. 開著 Blender 邊改邊看：`python3 bl.py run lib.py figure.py <avatar_key>.py`。
4. 完成後執行 `./build.sh <avatar_key>`，再跑 `pnpm -F web check-assets` 和 `pnpm -F web exec vitest run src/office3d`。
5. 把 `avatar_key` 加進 `src/office3d/assets/characters.ts` 的 `OWN_FIGURES`，並在 `src/office3d/assets/LICENSES.md` 登記檔案。
