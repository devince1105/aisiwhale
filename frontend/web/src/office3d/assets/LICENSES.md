# 3D 辦公室素材授權（T-404）

每個放進 `frontend/web/public/models/` 的檔案都必須列在這裡；`pnpm -F web check-assets` 會檢查（沒列出的檔案會讓檢查失敗）。

## 第三方素材

### Kenney — Mini Characters 1.0

| 項目 | 內容 |
|---|---|
| 作者 | Kenney（www.kenney.nl） |
| 授權 | **Creative Commons Zero（CC0 1.0）**，公眾領域：可商用、可修改、不需署名（作者歡迎署名，非必要） |
| 來源頁 | https://kenney.nl/assets/mini-characters |
| 下載檔 | `kenney_mini-characters.zip`（2,403,059 bytes），https://kenney.nl/media/pages/assets/mini-characters/bfc7e272b4-1774770718/kenney_mini-characters.zip |
| 壓縮檔 SHA-256 | `9e1d48e6d7b8479ebbe84df71eb5bd8e1b3f0da546dea641890dccc8a02d0999` |
| 取得日期 | 2026-09-19（使用者於對話中核准下載） |
| 包內授權檔 | `License.txt`：「Mini Characters (1.0) … License: (Creative Commons Zero, CC0)」 |
| 修改 | 無（原檔照用；只取 GLB 格式的 12 個人物與共用貼圖，沒有取輪椅與輔具模型） |

使用的檔案：

- `models/characters/character-female-a.glb`
- `models/characters/character-female-b.glb`
- `models/characters/character-female-c.glb`
- `models/characters/character-female-d.glb`
- `models/characters/character-female-e.glb`
- `models/characters/character-female-f.glb`
- `models/characters/character-male-a.glb`
- `models/characters/character-male-b.glb`
- `models/characters/character-male-c.glb`
- `models/characters/character-male-d.glb`
- `models/characters/character-male-e.glb`
- `models/characters/character-male-f.glb`
- `models/characters/Textures/colormap.png`

## 自製內容（非第三方）

- **成員自己的人物模型（D-196～D-198）**：在 Blender 裡用腳本建的動森風 Q 版人物，原始檔與腳本在 `frontend/web/figures-source/blender/`（`figure.py`、`tifa.py`、`ada.py`、`rei.py`、`sayla.py`、`mari.py`、`shinobu.py`、`ami.py` 與各自的 `.blend`）。骨架與 32 段動畫沿用上面的 Kenney `character-female-f.glb`（CC0，未改動），網格、材質和貼圖（腳本畫的）是自製的。造型照使用者提供的角色圖（`avatars-source/q`、`back`、`stand-side`）做；**角色本身（Tifa，Square Enix《Final Fantasy VII》；Ada Wong，Capcom《Resident Evil》；綾波零、真希波・瑪麗・伊拉斯多莉亞斯，khara《福音戰士》系列；Sayla Mass，Sunrise《機動戰士鋼彈》；胡蝶忍，吾峠呼世晴／集英社《鬼滅之刃》；水野亞美，武內直子／講談社《美少女戰士》）不是我們的**，屬同人造型、沒有官方授權。
  - `models/characters/tifa.glb`
  - `models/characters/ada.glb`
  - `models/characters/rei.glb`
  - `models/characters/sayla.glb`
  - `models/characters/mari.glb`
  - `models/characters/shinobu.glb`
  - `models/characters/ami.glb`

- 房間、家具、植物、地板材質：全部由程式產生（`src/office3d/scene/`），沒有使用任何下載的模型或圖片。
- 風格參考（D-008、D-010）：《動物森友會》、《Good Job!》、使用者提供的等角辦公室渲染圖——**只參考風格，沒有使用或仿製其中任何素材**。
