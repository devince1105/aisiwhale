# 成員自己的 3D 人物（D-196）

不對外提供的原始檔。網站載入的是匯出後的 `public/models/characters/<avatar_key>.glb`。

## 做法

在 Blender（5.2）裡用 Python 建模：先載入 Kenney `character-female-f.glb`，**只保留骨架與 32 段動畫**，網格全部刪掉；再用球體、圓管、圓角方塊與曲線，照使用者提供的角色圖（`avatars-source/q`、`back`、`stand-side`）拼出動森風的 Q 版人物。每個部位都整塊綁在一根骨頭上（`root`、`torso`、`head`、`arm-left`、`arm-right`、`leg-left`、`leg-right`），所以辦公室原有的姿勢（`AvatarController` 的打字、思考、看稿、趴下）和 Kenney 的動畫都能直接用。

- 座標：Blender 是 Z 軸朝上，人物面向 −Y，她的左邊是 +X；靜止姿勢是 T 字（手臂平舉），必須和 Kenney 一樣，動畫才會對。
- 顏色是平面材質，沒有貼圖；頭髮是單層網格、雙面顯示。
- 匯出時把各部位合併成一個網格，超過預算就減面到 3,000 個三角形以下（`check-assets` 的人物上限，文件 04 §10）。

## 檔案

| 檔案 | 用途 |
|---|---|
| `blender/lib.py` | 共用工具：載入骨架（`reset`）、材質、橢球／圓管／圓角方塊／曲線，以及貼在頭上的五官（`Head`） |
| `blender/tifa.py` | Tifa 的造型 |
| `blender/export.py` | 合併、減面、匯出 GLB（需先設定 `OUT`、`BUDGET`） |
| `blender/tifa.blend` | 建好的場景，可以直接打開手動修改 |
| `blender/bl.py` | 把腳本送進開著的 Blender（MCP for Blender 附加元件，`localhost:9876`）；`shot` 拍視圖截圖 |
| `blender/render.py`、`montage.py`、`pose.py` | 預覽：背景算圖、拼圖、套動畫 |

## 重做一位

1. 在 Blender 開啟 MCP for Blender 附加元件，按 Start MCP Server。
2. `python3 blender/bl.py run blender/lib.py blender/tifa.py`：在 Blender 裡建好人物。
3. `python3 blender/bl.py run <(echo "OUT='$PWD/../public/models/characters/tifa.glb'; BUDGET=2950") blender/export.py`
4. `pnpm -F web check-assets`、`pnpm -F web exec vitest run src/office3d/assets`

沒有 MCP 也可以在背景執行：把 `lib.py`、`tifa.py`、`export.py` 串成一個檔案，前面加上 `OUT`、`BUDGET` 的設定，再用 `Blender -b --python` 執行。

新增一位時，把她的 `avatar_key` 加進 `src/office3d/assets/characters.ts` 的 `OWN_FIGURES`，並在 `src/office3d/assets/LICENSES.md` 登記檔案。
