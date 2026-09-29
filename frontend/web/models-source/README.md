# 辦公室角色 3D 模型：製作與交付規格（D-116）

目標：讓 3D 辦公室裡的角色接近角色設定圖（例如春麗的 Q 版全身圖），取代目前的方塊公仔。
先做**春麗一位**當試作，確認流程與效果後再做其他七位。

## 一、每位角色要交的檔案

放在 `frontend/web/models-source/<角色代號>/`，代號與大頭照相同：
`tifa`、`ada`、`sayla`、`rei`、`mari`、`shinobu`、`ami`、`chunli`。

| 檔案 | 內容 |
|---|---|
| `character.fbx` | 已綁骨架的角色（T-pose，含貼圖） |
| `sit.fbx` | 坐著待機（Mixamo：Sitting Idle） |
| `type.fbx` | 坐著打字（Mixamo：Typing） |
| `idle.fbx` | 站著待機（Mixamo：Standing Idle／Idle） |
| `walk.fbx` | 走路，**勾選 In Place**（Mixamo：Walking） |
| `yes.fbx` | 點頭（Mixamo：Head Nod Yes） |
| `no.fbx` | 搖頭（Mixamo：Shaking Head No） |
| `carry.fbx` | 撿起／拿著東西（Mixamo：Picking Up 或 Carrying） |

動畫檔都下載 **Without Skin**，30 fps；名稱照上表即可。

## 二、建議流程

1. **圖轉 3D**（Meshy、Tripo 或同類服務）
   - 上傳角色全身圖：正面、單一角色、乾淨背景；**雙手張開的 T 字或 A 字姿勢最好**，
     手貼著身體的圖在綁骨架時容易出錯。
   - 設定：低面數（約 1–3 萬面以內）、貼圖 1024 或 2048。
   - 匯出 **FBX**（或 OBJ）。
2. **綁骨架與動作**（Mixamo，免費，需 Adobe 帳號）
   - 上傳上一步的模型 → Auto-Rigger 標出下巴、手腕、手肘、膝蓋、胯部 → 完成。
   - 下載角色本身：Format FBX、Pose T-pose、**With Skin** → 存成 `character.fbx`。
   - 依上表逐一套用動作並下載（Without Skin）。
3. 把檔案放進 `models-source/chunli/`，告訴我。之後的轉檔（FBX → 網頁用的 GLB，
   合併動作、壓縮貼圖）與接進辦公室由我處理。

## 三、注意

- **授權**：先確認服務的條款。有些服務免費方案產出的模型要求標示出處或不可商用，
  付費方案才歸你。請確認可以用在艾矽鯨的後台（目前後台不對外公開）。
- **角色版權**：春麗等角色屬於原作者；目前只用在不對外的後台，影響小。
  若之後要放到公開網站或公開的 Discord，需要重新評估。
- **大小**：每位的 GLB 目標 2–5 MB 內；八位同時載入要考慮效能，必要時我會壓縮貼圖與簡化網格。
- 還沒有 3D 模型的人，辦公室會繼續顯示現在的上色公仔，不會壞掉。
