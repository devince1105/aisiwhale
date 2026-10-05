# 成員自己的 3D 人物（D-196、D-197）

不對外提供的原始檔。網站載入的是匯出後的 `public/models/characters/<avatar_key>.glb`。

## 做法：高模雕刻 → 低模 → 烘焙（D-197）

D-196 第一版是把球、管、方塊拼起來，各自上平面顏色。接縫明顯、頭髮薄得像紙、轉折生硬，跟參考圖差很遠。D-197 改用遊戲角色常見的流程：

1. **高模**（`<名字>_hi.py`，約 16 萬面，只當烘焙來源，不會出貨）
   - **身體**：先把軀幹、四肢、手、大腿等形體合在一起，用體素重建網格（voxel remesh）成一整塊，再用平滑把接合處抹順。這等於雕刻師手動「融合」的步驟，所以沒有插進去的接縫。
   - **頭**：照動森的樣子做：圓頭、臉頰較飽滿、下巴略平。五官是貼在雕好的臉上的薄片，位置用射線打到真正的表面上（`Surface`），不是理想的橢球。
   - **衣服**：從身體表面切一塊出來往外推，切口的邊緣先順過，再沿著邊緣加滾邊（`layer`、`trim`）。所以衣服不會和皮膚重疊、互相穿插。
   - **頭髮**：一整片從頭頂往下的殼（使用者希望頭髮是「一整片」），加上厚度。髮束用圓脊和尖銳的分線雕出來，每束的尾端收成尖。瀏海從分線斜掃過去；太陽穴的髮束和馬尾另外用掃掠（`sweep`）做。
2. **低模**（`lowpoly.py`，每個人的設定在 `<名字>_low.py`）
   - 每組高模（頭、頭髮、身體、靴子）各自合併、粗略重建網格，再減到分配好的三角形數。身體的外殼往外撐 4 mm，把衣服層包在裡面。
   - 裙子、腰帶、耳環直接做成低模（32 面的百褶）。
   - 全部合在 3,000 個三角形以內（`check-assets` 的上限），超過時 `export.py` 仍會減面。
3. **權重**：頭、頭髮、裙子、靴子整塊綁在一根骨頭上。身體依部位分配權重，關節處平滑過渡（`body_weights`）。不能用 Blender 的自動權重（bone heat）：Kenney 的腿骨是從髖部往上長的，自動權重會把小腿分給兩腿中間的 `root` 骨。
4. **烘焙**（Cycles）：顏色、法線、環境遮蔽烘到同一張 1024 的圖集，遮蔽再乘進顏色。每塊低模只從自己那組高模烘焙（`BAKE_FROM`），所以頭髮邊緣不會吃到底下的皮膚。臉另外用正面投影當成一個 UV 島，給 3.5 倍的解析度；被頭髮蓋住的頭皮只給 0.6 倍（`UV_SCALE`）。
5. **匯出**：一個網格、一個材質，顏色貼圖和法線貼圖以 JPEG 包在 GLB 裡。

座標：Blender 是 Z 軸朝上，人物面向 −Y，她的左邊是 +X。靜止姿勢是 T 字（手臂平舉），必須和 Kenney 一樣，動畫才會對。

## 檔案

| 檔案 | 用途 |
|---|---|
| `blender/lib.py` | 載入 Kenney 骨架（`reset`）、材質、基本形體（橢球、圓管、`lathe`、圓角方塊、曲線） |
| `blender/sculpt.py` | 高模工具：`union`（合併＋體素重建＋平滑）、`layer`、`trim`、`sweep`、`Surface`、`pleated_skirt` |
| `blender/tifa_hi.py` | Tifa 的高模 |
| `blender/tifa_low.py` | Tifa 的低模設定：三角形分配、權重、烘焙來源、UV 密度 |
| `blender/lowpoly.py` | 通用：建低模、權重、UV、烘焙、組材質 |
| `blender/export.py` | 匯出 GLB（需先設定 `OUT`、`BUDGET`） |
| `blender/tifa.blend` | 成品低模（含烘焙圖），可以直接打開；高模不存，重跑 `tifa_hi.py` 約 1 秒 |
| `blender/bl.py` | 把腳本送進開著的 Blender（MCP for Blender 附加元件，`localhost:9876`）；`shot` 拍視圖截圖 |
| `blender/render.py`、`montage.py`、`pose.py` | 預覽：背景算圖（可套動畫）、拼圖 |

## 重做一位

1. 在 Blender 開啟 MCP for Blender 附加元件，按 Start MCP Server。
2. `python3 blender/bl.py run blender/lib.py blender/sculpt.py blender/tifa_hi.py`：建高模（約 1 秒）。
3. `python3 blender/bl.py run blender/lib.py blender/sculpt.py blender/tifa_low.py blender/lowpoly.py`：低模與烘焙（約 1.5 分鐘）。
4. `python3 blender/bl.py run <(echo "OUT='$PWD/../public/models/characters/tifa.glb'; BUDGET=2990") blender/export.py`
5. 套動畫看關節：`Blender -b --python blender/render.py -- <glb> <輸出前綴> sit 0.5`
6. `pnpm -F web check-assets`、`pnpm -F web exec vitest run src/office3d/assets`

新增一位時，複製 `tifa_hi.py`、`tifa_low.py` 改造型和設定，把她的 `avatar_key` 加進 `src/office3d/assets/characters.ts` 的 `OWN_FIGURES`，並在 `src/office3d/assets/LICENSES.md` 登記檔案。
