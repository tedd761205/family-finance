# 本機發票辨識試用

## 目標

先驗證無需付費 OCR API 的瀏覽器端辨識方式，供家庭記帳系統的紙本發票／收據辨識進行小規模試用。

## 隱私與費用

- 使用者選取的照片只交給目前瀏覽器中的 OCR worker，不呼叫本站 OCR API、Google Cloud Vision 或附件上傳 API。
- OCR 使用 Tesseract.js 7.0.0、`chi_tra` 繁體中文及 `eng` 英文語言模型。
- QR Code 優先使用瀏覽器本機解碼；支援 BarcodeDetector 的瀏覽器也會嘗試解碼常見一維條碼。
- 第一次使用需要從 CDN 下載 OCR 程式、WebAssembly 核心及語言模型。這不是 OCR API 計價，但會使用網路流量；手機電信商是否計收流量依使用者方案而定。
- Tesseract.js 的模型快取由瀏覽器管理；清除網站資料、使用無痕模式或瀏覽器清除快取後，可能需要重新下載。
- 若程式／模型無法下載或辨識失敗，功能會顯示錯誤，不會自動改用付費雲端辨識。

## 試用範圍

- 目前接受 JPEG、PNG、WebP 圖片，單張上限 10 MiB。
- 支援拍照或選取手機既有照片。
- 本機抽取文字、嘗試 QR Code／瀏覽器支援的一維條碼解碼。
- 從文字提出日期、金額及台灣統一發票號碼候選值。
- 使用者可以把候選值帶入既有收支表單，但仍需選擇帳戶、分類並手動提交。
- 照片不會在試用版保存；辨識內容也不會自動建立交易。
- PDF、載具官方 API 匯入、發票憑證長期保存及完整電子發票 QR Code 欄位解析不在此試用版範圍。

## 已知限制

- Tesseract.js 是通用文字辨識引擎，並非台灣發票專用模型；手寫字、反光、熱感紙褪色、低解析度及複雜排版可能辨識錯誤。
- 瀏覽器端 OCR 會使用使用者裝置 CPU／記憶體，較舊手機可能較慢或因記憶體不足而失敗。
- 一維條碼解碼依瀏覽器是否提供 BarcodeDetector；QR Code 有本機 jsQR fallback。
- 日期與金額只列為候選值，使用者必須對照原始發票確認，不能視為正式帳務資料。

## 後續驗收

用三星 Android、iPhone Safari、iPad 及桌面 Chrome 測試：
1. 首次下載模型、再次使用快取及清除快取後重新下載。
2. 傳統二聯式、三聯式、手寫發票、熱感紙收據及模糊照片。
3. 不同方向、裁切、反光及多語言內容。
4. 電子發票證明聯左右 QR Code 讀取情況。
5. 離線或 CDN 不可用時的錯誤提示。
6. 瀏覽器網路面板確認發票影像沒有送往本站 API 或 Google Vision。
7. 核對 OCR 只填入表單候選值，未確認提交前沒有建立交易。

## 來源

- Tesseract.js 官方文件：<https://github.com/naptha/tesseract.js>
- Tesseract.js API：<https://github.com/naptha/tesseract.js/blob/master/docs/api.md>
- jsQR：<https://github.com/cozmo/jsQR>
