(() => {
  "use strict";

  const TESSERACT_SRC = "https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.min.js";
  const JSQR_SRC = "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js";
  const LANGUAGE_PATH = "https://tessdata.projectnaptha.com/4.0.0";
  const MAX_FILE_BYTES = 10 * 1024 * 1024;
  const MAX_BARCODE_IMAGE_EDGE = 1800;
  const MAX_OCR_IMAGE_EDGE = 2600;

  const $ = (id) => document.getElementById(id);
  const cameraButton = $("local-receipt-camera");
  const chooseButton = $("local-receipt-choose");
  const cameraInput = $("local-receipt-camera-input");
  const fileInput = $("local-receipt-file-input");
  const status = $("local-receipt-status");
  const workspace = $("local-receipt-workspace");
  const preview = $("local-receipt-preview");
  const progressBar = $("local-receipt-progress-bar");
  const textArea = $("local-receipt-text");
  const candidates = $("local-receipt-candidates");
  const fillButton = $("local-receipt-fill");
  const clearButton = $("local-receipt-clear");
  const receiptTypeSelect = $("local-receipt-type");
  const reviewPanel = $("local-receipt-review");
  const merchantInput = $("local-receipt-merchant");
  const amountInput = $("local-receipt-amount");
  const dateInput = $("local-receipt-date");
  const invoiceNumberInput = $("local-receipt-invoice-number");
  const sellerTaxIdInput = $("local-receipt-seller-tax-id");
  const buyerTaxIdInput = $("local-receipt-buyer-tax-id");
  const itemsInput = $("local-receipt-items");

  if (!cameraButton || !chooseButton || !cameraInput || !fileInput || !window.FamilyReceiptParser) return;

  let workerPromise = null;
  let worker = null;
  let activeFile = null;
  let previewUrl = null;
  let parsedFields = null;
  let isProcessing = false;

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle("error", isError);
  }

  function setBusy(busy) {
    isProcessing = busy;
    cameraButton.disabled = busy;
    chooseButton.disabled = busy;
    fillButton.disabled = busy || !hasReviewData();
    clearButton.disabled = busy;
  }

  function loadScript(src, globalName) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    return new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-local-receipt-src="' + src + '"]');
      if (existing) {
        existing.addEventListener("load", () => window[globalName] ? resolve(window[globalName]) : reject(new Error("辨識程式載入失敗")), { once: true });
        existing.addEventListener("error", () => reject(new Error("無法下載本機辨識程式，請確認網路連線後重試")), { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.crossOrigin = "anonymous";
      script.dataset.localReceiptSrc = src;
      script.onload = () => window[globalName] ? resolve(window[globalName]) : reject(new Error("辨識程式載入後無法啟動"));
      script.onerror = () => {
        script.remove();
        reject(new Error("無法下載本機辨識程式，請確認網路連線後重試"));
      };
      document.head.appendChild(script);
    });
  }

  async function getWorker() {
    if (worker) return worker;
    if (!workerPromise) {
      workerPromise = (async () => {
        setStatus("第一次使用：正在下載本機辨識引擎與繁體中文模型。這是程式／模型下載，不會上傳照片，也不會呼叫付費 OCR API。");
        const tesseract = await loadScript(TESSERACT_SRC, "Tesseract");
        const created = await tesseract.createWorker(["chi_tra", "eng"], 1, {
          langPath: LANGUAGE_PATH,
          cacheMethod: "write",
          gzip: true,
          logger: (message) => {
            if (message && typeof message.progress === "number") {
              const percent = Math.max(0, Math.min(100, Math.round(message.progress * 100)));
              progressBar.style.width = percent + "%";
              if (message.status) setStatus("本機辨識準備中：" + message.status + "（" + percent + "%）");
            } else if (message && message.status) {
              setStatus("本機辨識準備中：" + message.status);
            }
          }
        });
        worker = created;
        return created;
      })().catch((error) => {
        workerPromise = null;
        worker = null;
        throw error;
      });
    }
    return workerPromise;
  }

  function validDate(year, month, day) {
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
    return String(year).padStart(4, "0") + "-" + String(month).padStart(2, "0") + "-" + String(day).padStart(2, "0");
  }

  function extractCandidates(text) {
    let date = null;
    let match = text.match(/(?:^|[^\d])(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})(?!\d)/);
    if (match) date = validDate(Number(match[1]), Number(match[2]), Number(match[3]));
    if (!date) {
      match = text.match(/(?:民國\s*)?(\d{2,3})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?/);
      if (match) date = validDate(Number(match[1]) + 1911, Number(match[2]), Number(match[3]));
    }

    const amountPattern = /(?:總計|合計|應付(?:金額)?|實付(?:金額)?|實收(?:金額)?|付款金額|消費金額|總金額|總額|金額|TOTAL|NT\s*\$)\s*[：:=]?\s*(?:(?:NTD|TWD|NT\s*\$)\s*)?([0-9][0-9,]*(?:\.[0-9]{1,2})?)/gi;
    const amountMatches = Array.from(text.matchAll(amountPattern));
    let amount = null;
    if (amountMatches.length) {
      const raw = amountMatches[amountMatches.length - 1][1].replace(/,/g, "");
      const value = Number(raw);
      if (Number.isFinite(value) && value > 0) amount = value.toFixed(2).replace(/\.00$/, "");
    }

    const invoiceMatch = text.match(/\b([A-Z]{2})[\s-]?(\d{8})\b/i);
    return {
      amount,
      date,
      invoiceNumber: invoiceMatch ? invoiceMatch[1].toUpperCase() + invoiceMatch[2] : null
    };
  }

  async function loadImageCanvas(file, maxEdge = MAX_BARCODE_IMAGE_EDGE) {
    const image = typeof createImageBitmap === "function"
      ? await createImageBitmap(file)
      : await new Promise((resolve, reject) => {
          const imageElement = new Image();
          const temporaryUrl = URL.createObjectURL(file);
          imageElement.onload = () => {
            URL.revokeObjectURL(temporaryUrl);
            resolve(imageElement);
          };
          imageElement.onerror = () => {
            URL.revokeObjectURL(temporaryUrl);
            reject(new Error("無法讀取照片"));
          };
          imageElement.src = temporaryUrl;
        });

    const scale = Math.min(1, maxEdge / Math.max(image.width, image.height));
    const width = Math.max(1, Math.round(image.width * scale));
    const height = Math.max(1, Math.round(image.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("目前瀏覽器無法處理照片，請改用其他瀏覽器。");
    context.drawImage(image, 0, 0, width, height);
    if (typeof image.close === "function") image.close();
    return canvas;
  }

  async function decodeLocalCodes(file) {
    const found = [];
    const addCode = (value, format, side = null) => {
      if (!value) return;
      const existing = found.find((item) => item.value === value);
      if (existing) {
        if (side && !existing.side) existing.side = side;
        return;
      }
      found.push({ format: format || "條碼", value: value, side: side });
    };

    try {
      const canvas = await loadImageCanvas(file, MAX_BARCODE_IMAGE_EDGE);
      const detectorSupported = "BarcodeDetector" in window;
      if (detectorSupported && typeof createImageBitmap === "function") {
        try {
          const desiredFormats = ["qr_code", "code_128", "ean_13", "ean_8", "upc_a", "upc_e", "code_39", "itf"];
          const supportedFormats = typeof BarcodeDetector.getSupportedFormats === "function"
            ? await BarcodeDetector.getSupportedFormats()
            : desiredFormats;
          const formats = desiredFormats.filter((format) => supportedFormats.includes(format));
          if (formats.length) {
            const detector = new BarcodeDetector({ formats });
            const bitmap = await createImageBitmap(canvas);
            const detected = await detector.detect(bitmap);
            bitmap.close();
            for (const code of detected) addCode(code.rawValue, code.format || "條碼");
          }
        } catch (_error) {
          // Some browsers expose BarcodeDetector but do not implement every format.
        }
      }

      const jsQR = await loadScript(JSQR_SRC, "jsQR");
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) return found;
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      const full = jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: "attemptBoth" });
      if (full && full.data) addCode(full.data, "QR Code");

      // 台灣電子發票左右 QR Code 分開解碼，保留左右位置以便合併解析。
      const middle = Math.floor(canvas.width / 2);
      for (const region of [
        { x: 0, width: middle, side: "left" },
        { x: middle, width: canvas.width - middle, side: "right" }
      ]) {
        if (region.width < 2) continue;
        const crop = document.createElement("canvas");
        crop.width = region.width;
        crop.height = canvas.height;
        const cropContext = crop.getContext("2d", { willReadFrequently: true });
        if (!cropContext) continue;
        cropContext.drawImage(canvas, region.x, 0, region.width, canvas.height, 0, 0, region.width, canvas.height);
        const cropData = cropContext.getImageData(0, 0, crop.width, crop.height);
        const result = jsQR(cropData.data, cropData.width, cropData.height, { inversionAttempts: "attemptBoth" });
        if (result && result.data) addCode(result.data, "QR Code", region.side);
      }
    } catch (_error) {
      // OCR can still proceed when the optional local barcode decoder is unavailable.
    }
    return found;
  }

  function hasReviewData() {
    if (!parsedFields) return false;
    return Boolean(
      (amountInput && amountInput.value.trim()) ||
      (dateInput && dateInput.value.trim()) ||
      (invoiceNumberInput && invoiceNumberInput.value.trim()) ||
      (merchantInput && merchantInput.value.trim())
    );
  }

  function effectiveReceiptType() {
    if (receiptTypeSelect && receiptTypeSelect.value !== "auto") return receiptTypeSelect.value;
    return parsedFields ? parsedFields.type : "unknown";
  }

  function receiptTypeLabel() {
    const labels = window.FamilyReceiptParser.TYPE_LABELS || {};
    return labels[effectiveReceiptType()] || labels.unknown || "尚待判斷";
  }

  function renderReview(fields) {
    if (!reviewPanel || !fields) return;
    merchantInput.value = fields.merchant || "";
    amountInput.value = fields.amount || "";
    dateInput.value = fields.date || "";
    invoiceNumberInput.value = fields.invoiceNumber || "";
    sellerTaxIdInput.value = fields.sellerTaxId || "";
    buyerTaxIdInput.value = fields.buyerTaxId || "";
    itemsInput.value = (fields.items || []).map((item) =>
      item.name + " × " + item.quantity + "，單價 " + item.unitPrice
    ).join("\n");
    receiptTypeSelect.value = "auto";
    reviewPanel.classList.remove("hidden");
    fillButton.disabled = !hasReviewData();
  }

  function renderCandidates(fields, codeResults) {
    candidates.replaceChildren();
    const pieces = [];
    const typeName = receiptTypeLabel();
    pieces.push("憑證種類：" + typeName);
    if (fields.merchant) pieces.push("商家：" + fields.merchant);
    if (fields.date) pieces.push("日期：" + fields.date);
    if (fields.amount) pieces.push("總金額：NT$ " + fields.amount);
    if (fields.invoiceNumber) pieces.push("發票號碼：" + fields.invoiceNumber);
    if (fields.sellerTaxId) pieces.push("賣方統編：" + fields.sellerTaxId);
    if (fields.buyerTaxId) pieces.push("買方統編：" + fields.buyerTaxId);
    if (fields.items && fields.items.length) pieces.push("商品明細：" + fields.items.length + " 項");
    if (codeResults.length) pieces.push("本機解碼 " + codeResults.length + " 個 QR Code／條碼");
    for (const value of pieces) {
      const item = document.createElement("span");
      item.className = "local-receipt-candidate";
      item.textContent = value;
      candidates.appendChild(item);
    }
    candidates.classList.toggle("hidden", pieces.length === 0);
    fillButton.disabled = isProcessing || !hasReviewData();
  }

  function clearPhoto() {
    activeFile = null;
    parsedFields = null;
    cameraInput.value = "";
    fileInput.value = "";
    textArea.value = "";
    progressBar.style.width = "0%";
    workspace.classList.add("hidden");
    candidates.replaceChildren();
    candidates.classList.add("hidden");
    reviewPanel?.classList.add("hidden");
    if (receiptTypeSelect) receiptTypeSelect.value = "auto";
    fillButton.disabled = true;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    preview.removeAttribute("src");
    setStatus("照片已清除。尚未上傳或儲存任何發票照片。");
  }

  async function handleFile(file) {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setStatus("目前試用版只支援 JPG、PNG、WebP 圖片；PDF 與其他格式尚未開放。", true);
      return;
    }
    if (file.size <= 0 || file.size > MAX_FILE_BYTES) {
      setStatus("照片大小必須大於 0，且不可超過 10 MB。", true);
      return;
    }

    activeFile = file;
    cameraInput.value = "";
    fileInput.value = "";
    parsedFields = null;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    preview.src = previewUrl;
    textArea.value = "";
    progressBar.style.width = "0%";
    workspace.classList.remove("hidden");
    candidates.replaceChildren();
    candidates.classList.add("hidden");
    reviewPanel?.classList.add("hidden");
    fillButton.disabled = true;
    setBusy(true);

    try {
      // QR / 1D barcode decoding also happens in this browser; it does not upload the photo.
      const codeResults = await decodeLocalCodes(file);
      const currentWorker = await getWorker();
      setStatus("正在本機辨識照片，照片不會傳送到伺服器或 Google。");
      const ocrCanvas = await loadImageCanvas(file, MAX_OCR_IMAGE_EDGE);
      const result = await currentWorker.recognize(ocrCanvas);
      const recognizedText = (result && result.data && result.data.text || "").trim();
      const codeText = codeResults.map((item, index) => "\n[" + item.format + " " + (index + 1) + "] " + item.value).join("");
      textArea.value = recognizedText + (codeText ? "\n\n本機條碼解碼結果：" + codeText : "");
      parsedFields = window.FamilyReceiptParser.parseReceiptData(recognizedText, codeResults);
      renderReview(parsedFields);
      renderCandidates(parsedFields, codeResults);
      if (!recognizedText && !codeResults.length) {
        setStatus("沒有辨識到文字或條碼。請把憑證放平、拍清楚、避免反光後再試一次。", true);
      } else if (parsedFields.type === "unknown") {
        setStatus("已取得文字，但無法可靠判斷憑證種類。請手動選擇種類並核對欄位；不確定的資料請自行補上。", true);
      } else {
        setStatus("本機辨識完成。請先確認憑證種類，再核對或修改欄位；資料不會自動建立支出。");
      }
    } catch (error) {
      parsedFields = null;
      fillButton.disabled = true;
      setStatus(error && error.message ? error.message : "本機辨識失敗，請重新拍照或稍後再試。", true);
    } finally {
      setBusy(false);
      if (parsedFields) fillButton.disabled = !hasReviewData();
    }
  }

  function fillTransactionForm() {
    if (!hasReviewData()) return;
    if (typeof window.resetTransactionForm === "function") window.resetTransactionForm();
    const type = $("transaction-type");
    type.value = "expense";
    type.dispatchEvent(new Event("change", { bubbles: true }));

    const merchant = merchantInput.value.trim();
    const amount = amountInput.value.trim();
    const date = dateInput.value.trim();
    const invoiceNumber = invoiceNumberInput.value.trim();
    const sellerTaxId = sellerTaxIdInput.value.trim();
    const buyerTaxId = buyerTaxIdInput.value.trim();
    const itemLines = itemsInput.value.trim();

    if (amount) $("transaction-amount").value = amount;
    if (date) $("transaction-date").value = date;
    if (invoiceNumber) $("transaction-reference").value = invoiceNumber;
    if (merchant) $("transaction-description").value = merchant.slice(0, 255);
    else if (!$("transaction-description").value.trim()) $("transaction-description").value = "發票／收據消費（請補商家名稱）";

    const noteParts = [];
    noteParts.push("憑證種類：" + receiptTypeLabel());
    if (sellerTaxId) noteParts.push("賣方統編：" + sellerTaxId);
    if (buyerTaxId) noteParts.push("買方統編：" + buyerTaxId);
    if (itemLines) noteParts.push("商品明細：\n" + itemLines);
    if (noteParts.length && !$("transaction-note").value.trim()) {
      $("transaction-note").value = noteParts.join("\n");
    }

    $("transaction-form-panel").classList.remove("hidden");
    $("transaction-form-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    setStatus("已將可辨識資料帶入記帳表單。請再核對金額、商家、帳戶及分類，最後按「新增紀錄」才會正式入帳。");
  }

    function disposeLocalReceiptSession() {
    clearPhoto();
    if (worker) {
      const currentWorker = worker;
      worker = null;
      workerPromise = null;
      currentWorker.terminate().catch(() => {});
    }
  }

  // Do not leave a previous family member's receipt photo in the page after changing family or signing out.
  $("logout-button")?.addEventListener("click", disposeLocalReceiptSession);
  $("family-list")?.addEventListener("click", (event) => {
    if (event.target.closest(".family-card")) clearPhoto();
  });
  $("close-transactions")?.addEventListener("click", clearPhoto);

  cameraButton.addEventListener("click", () => cameraInput.click());
  chooseButton.addEventListener("click", () => fileInput.click());
  cameraInput.addEventListener("change", () => handleFile(cameraInput.files && cameraInput.files[0]));
  fileInput.addEventListener("change", () => handleFile(fileInput.files && fileInput.files[0]));
  clearButton.addEventListener("click", clearPhoto);
  fillButton.addEventListener("click", fillTransactionForm);
  receiptTypeSelect?.addEventListener("change", () => {
    if (parsedFields) renderCandidates(parsedFields, []);
    if (parsedFields) {
      fillButton.disabled = !hasReviewData();
      if (receiptTypeSelect.value !== "auto") {
        setStatus("已手動選擇「" + receiptTypeLabel() + "」。請再核對辨識欄位；分類不會自動變更帳務金額。");
      }
    }
  });
  [merchantInput, amountInput, dateInput, invoiceNumberInput].forEach((input) => {
    input?.addEventListener("input", () => {
      fillButton.disabled = !hasReviewData();
    });
  });
})();
