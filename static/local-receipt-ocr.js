(() => {
  "use strict";

  const TESSERACT_SRC = "https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.min.js";
  const JSQR_SRC = "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js";
  // ZBar WASM + BarcodeDetector polyfill: multi-QR detection with 0/90/180/270-degree orientation support.
  const ZBAR_WASM_SRC = "https://cdn.jsdelivr.net/npm/@undecaf/zbar-wasm@0.9.15/dist/index.js";
  const BARCODE_POLYFILL_SRC = "https://cdn.jsdelivr.net/npm/@undecaf/barcode-detector-polyfill@0.9.23/dist/index.js";
  const LANGUAGE_PATH = "https://tessdata.projectnaptha.com/4.0.0";
  const MAX_FILE_BYTES = 10 * 1024 * 1024;
  const MAX_BARCODE_IMAGE_EDGE = 2600;
  const MAX_OCR_IMAGE_EDGE = 2600;
  const INVOICE_CAMERA_STORAGE_KEY = "family_invoice_preferred_rear_camera_v1";

  const $ = (id) => document.getElementById(id);
  const cameraButton = $("local-receipt-camera");
  const chooseButton = $("local-receipt-choose");
  const invoiceScanButton = $("local-receipt-invoice-scan");
  const invoiceCameraPanel = $("local-receipt-invoice-camera");
  const invoiceVideo = $("local-receipt-invoice-video");
  const invoiceScanStatus = $("local-receipt-invoice-scan-status");
  const invoiceStopButton = $("local-receipt-invoice-stop");
  const invoiceCaptureButton = $("local-receipt-invoice-capture");
  const invoiceCameraSelect = $("local-receipt-invoice-camera-select");
  const invoiceZoomControl = $("local-receipt-invoice-zoom");
  const invoiceZoomValue = $("local-receipt-invoice-zoom-value");
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
  let invoiceCameraStream = null;
  let invoiceCameraDeviceId = "";
  let invoiceCameraTrack = null;
  let invoiceBarcodeDetector = null;
  let invoiceScanTimer = null;
  let invoiceScanBusy = false;
  let invoiceCaptureRequested = false;
  let invoiceCaptureGeneration = 0;
  let invoiceLeftQrValue = null;
  let invoiceRightQrValue = null;
  const invoiceScanCanvas = document.createElement("canvas");

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle("error", isError);
  }

  function setBusy(busy) {
    isProcessing = busy;
    cameraButton.disabled = busy;
    chooseButton.disabled = busy;
    invoiceScanButton.disabled = busy || Boolean(invoiceCameraStream);
    invoiceStopButton.disabled = busy || !invoiceCameraStream;
    if (invoiceCaptureButton) invoiceCaptureButton.disabled = busy || !invoiceCameraStream;
    fillButton.disabled = busy || !hasReviewData();
    clearButton.disabled = busy;
  }

  function loadScript(src, globalName) {
    const readyValue = () => globalName ? window[globalName] : true;
    if (globalName && readyValue()) return Promise.resolve(readyValue());
    return new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-local-receipt-src="' + src + '"]');
      if (existing) {
        if (existing.dataset.localReceiptLoaded === "true") {
          const value = readyValue();
          value ? resolve(value) : reject(new Error("辨識程式載入後無法啟動"));
          return;
        }
        existing.addEventListener("load", () => readyValue() ? resolve(readyValue()) : reject(new Error("辨識程式載入失敗")), { once: true });
        existing.addEventListener("error", () => reject(new Error("無法下載本機辨識程式，請確認網路連線後重試")), { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.crossOrigin = "anonymous";
      script.dataset.localReceiptSrc = src;
      script.onload = () => {
        script.dataset.localReceiptLoaded = "true";
        readyValue() ? resolve(readyValue()) : reject(new Error("辨識程式載入後無法啟動"));
      };
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


  // Single-QR still-image fallback. It is independent of the live multi-QR/WASM
  // detector, so a failed or stalled video detector cannot block the capture button.
  async function decodeInvoicePhotoWithJsQr(file) {
    const jsQR = await loadScript(JSQR_SRC, "jsQR");
    const sourceCanvas = await loadImageCanvas(file, MAX_BARCODE_IMAGE_EDGE);
    const width = sourceCanvas.width;
    const height = sourceCanvas.height;
    const regions = [
      [0, 0, width, height],
      [0, 0, Math.ceil(width / 2), height],
      [Math.floor(width / 2), 0, width - Math.floor(width / 2), height],
      [0, 0, width, Math.ceil(height / 2)],
      [0, Math.floor(height / 2), width, height - Math.floor(height / 2)]
    ];
    const results = [];
    for (const [x, y, regionWidth, regionHeight] of regions) {
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 2200 / Math.max(regionWidth, regionHeight));
      canvas.width = Math.max(1, Math.round(regionWidth * scale));
      canvas.height = Math.max(1, Math.round(regionHeight * scale));
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) continue;
      context.drawImage(
        sourceCanvas,
        x, y, regionWidth, regionHeight,
        0, 0, canvas.width, canvas.height
      );
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      const decoded = jsQR(
        imageData.data,
        imageData.width,
        imageData.height,
        { inversionAttempts: "attemptBoth" }
      );
      const value = String(decoded?.data || "").trim();
      if (value && !results.some((item) => item.value === value)) {
        results.push({ format: "QR Code", value });
      }
    }
    return results;
  }

  async function decodeInvoiceVideoFrameWithJsQr() {
    if (!invoiceVideo?.videoWidth || !invoiceVideo?.videoHeight) return null;
    const jsQR = await loadScript(JSQR_SRC, "jsQR");
    const maxEdge = 1800;
    const scale = Math.min(1, maxEdge / Math.max(invoiceVideo.videoWidth, invoiceVideo.videoHeight));
    invoiceScanCanvas.width = Math.max(1, Math.round(invoiceVideo.videoWidth * scale));
    invoiceScanCanvas.height = Math.max(1, Math.round(invoiceVideo.videoHeight * scale));
    const context = invoiceScanCanvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("目前瀏覽器無法讀取相機畫面。");
    context.drawImage(invoiceVideo, 0, 0, invoiceScanCanvas.width, invoiceScanCanvas.height);
    const imageData = context.getImageData(0, 0, invoiceScanCanvas.width, invoiceScanCanvas.height);
    const decoded = jsQR(
      imageData.data,
      imageData.width,
      imageData.height,
      { inversionAttempts: "attemptBoth" }
    );
    return decoded?.data ? String(decoded.data).trim() : null;
  }

  async function createLocalBarcodeDetector(formats) {
    // Prefer the ZBar WebAssembly polyfill: it returns every QR in the frame,
    // not just one, and reports orientation for sideways/upside-down symbols.
    try {
      await loadScript(ZBAR_WASM_SRC, null);
      const api = await loadScript(BARCODE_POLYFILL_SRC, "barcodeDetectorPolyfill");
      if (api && typeof api.BarcodeDetectorPolyfill === "function") {
        return new api.BarcodeDetectorPolyfill({ formats: formats || ["qr_code"] });
      }
    } catch (_error) {
      // Continue with the browser detector or jsQR fallback when CDN/WASM is unavailable.
    }

    if (typeof window.BarcodeDetector === "function") {
      try {
        const supported = typeof window.BarcodeDetector.getSupportedFormats === "function"
          ? await window.BarcodeDetector.getSupportedFormats()
          : (formats || ["qr_code"]);
        const selected = (formats || ["qr_code"]).filter((format) => supported.includes(format));
        if (selected.length) return new window.BarcodeDetector({ formats: selected });
      } catch (_error) {
        // Browser-native detector is optional; the local jsQR fallback remains available.
      }
    }
    return null;
  }

  async function decodeLocalCodes(file, preferredDetector = null, strict = false) {
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
      const desiredFormats = ["qr_code", "code_128", "ean_13", "ean_8", "upc_a", "upc_e", "code_39", "itf"];
      const detector = preferredDetector || await createLocalBarcodeDetector(desiredFormats);
      if (detector) {
        try {
          const detected = await detector.detect(canvas);
          for (const code of detected || []) {
            const format = code.format === "qr_code" ? "QR Code" : (code.format || "條碼");
            addCode(code.rawValue, format);
          }
        } catch (error) {
          if (strict) throw error;
          // A single decoder failure should not prevent trying the local fallback.
        }
      }

      // jsQR is a single-symbol fallback only.
      // The ZBar detector above scans the whole invoice and can return both QR payloads in one pass.
      if (found.filter((item) => item.format === "QR Code" || item.format === "qr_code").length < 2) {
        const jsQR = await loadScript(JSQR_SRC, "jsQR");
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) return found;
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        const full = jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: "attemptBoth" });
        if (full && full.data) addCode(full.data, "QR Code");
      }
    } catch (error) {
      if (strict) throw error;
      // OCR can still proceed when the optional local barcode decoder is unavailable.
    }
    return found;
  }

  function setInvoiceScanStatus(message, isError = false) {
    if (!invoiceScanStatus) return;
    invoiceScanStatus.textContent = message;
    invoiceScanStatus.classList.toggle("error", isError);
  }

  function stopInvoiceScanner(hidePanel = true) {
    if (invoiceScanTimer) {
      window.clearInterval(invoiceScanTimer);
      invoiceScanTimer = null;
    }
    invoiceScanBusy = false;
    if (invoiceCameraStream) {
      invoiceCameraStream.getTracks().forEach((track) => track.stop());
      invoiceCameraStream = null;
    }
    invoiceCameraTrack = null;
    if (invoiceCameraSelect) invoiceCameraSelect.disabled = true;
    if (invoiceZoomControl) { invoiceZoomControl.disabled = true; invoiceZoomControl.value = "1"; }
    if (invoiceZoomValue) invoiceZoomValue.textContent = "1.0×";
    if (invoiceVideo) {
      invoiceVideo.pause();
      invoiceVideo.srcObject = null;
    }
    if (hidePanel) invoiceCameraPanel?.classList.add("hidden");
    if (cameraButton) cameraButton.disabled = isProcessing;
    if (chooseButton) chooseButton.disabled = isProcessing;
    if (invoiceScanButton) invoiceScanButton.disabled = isProcessing;
    if (invoiceStopButton) invoiceStopButton.disabled = true;
    if (invoiceCaptureButton) invoiceCaptureButton.disabled = true;
  }

  function captureInvoiceCameraFrame() {
    return new Promise((resolve, reject) => {
      if (!invoiceVideo || !invoiceVideo.videoWidth || !invoiceVideo.videoHeight) {
        reject(new Error("相機畫面尚未準備好，請稍候再試。"));
        return;
      }
      const maxEdge = MAX_OCR_IMAGE_EDGE;
      const scale = Math.min(1, maxEdge / Math.max(invoiceVideo.videoWidth, invoiceVideo.videoHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(invoiceVideo.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(invoiceVideo.videoHeight * scale));
      const context = canvas.getContext("2d");
      if (!context) {
        reject(new Error("目前瀏覽器無法擷取相機畫面。"));
        return;
      }
      context.drawImage(invoiceVideo, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("無法建立發票影像，請重新掃描。"));
          return;
        }
        resolve(new File([blob], "electronic-invoice.jpg", {
          type: "image/jpeg",
          lastModified: Date.now()
        }));
      }, "image/jpeg", 0.94);
    });
  }

  async function completeInvoiceQrScan() {
    const leftValue = invoiceLeftQrValue;
    const rightValue = invoiceRightQrValue;
    if (!leftValue || isProcessing) return;

    // The left/basic QR is sufficient for invoice number, date, random code,
    // amount and tax IDs. The right/detail QR is optional enrichment only.
    const parsedPair = window.FamilyReceiptParser.parseTaiwanInvoiceQr(leftValue, rightValue);
    if (!parsedPair) {
      setInvoiceScanStatus("已讀取發票基本 QR，但資料格式無法解析。請重新掃描，或改用拍照辨識。", true);
      invoiceLeftQrValue = null;
      invoiceRightQrValue = null;
      return;
    }

    if (invoiceScanTimer) {
      window.clearInterval(invoiceScanTimer);
      invoiceScanTimer = null;
    }
    setInvoiceScanStatus(rightValue ? "已讀取發票基本資料與商品明細，正在擷取畫面…" : "已讀取發票基本資料，正在擷取畫面…");
    invoiceScanBusy = true;
    try {
      const file = await captureInvoiceCameraFrame();
      const codes = [
        { format: "QR Code", value: leftValue, side: "left" },
        ...(rightValue ? [{ format: "QR Code", value: rightValue, side: "right" }] : [])
      ];
      stopInvoiceScanner();
      await handleFile(file, codes);
    } catch (error) {
      stopInvoiceScanner(false);
      setInvoiceScanStatus(error && error.message ? error.message : "擷取發票失敗，請重新掃描。", true);
      invoiceScanButton.disabled = false;
    }
  }

  function acceptInvoiceQrPayload(value) {
    const raw = String(value || "").trim();
    if (!raw) return;
    if (raw.startsWith("**")) {
      if (!invoiceRightQrValue) {
        invoiceRightQrValue = raw;
      }
      return;
    }
    if (!invoiceLeftQrValue && window.FamilyReceiptParser.parseTaiwanInvoiceQr(raw, null)) {
      invoiceLeftQrValue = raw;
    }
  }

  async function captureAndDecodeInvoicePhoto() {
    if (!invoiceCameraStream) {
      setInvoiceScanStatus("相機尚未啟動，請先重新開啟雙 QR 掃描。", true);
      return;
    }
    if (invoiceCaptureRequested) {
      setInvoiceScanStatus("正在處理剛才的拍照，請稍候。");
      return;
    }

    // Pause the continuous scanner immediately. The previous implementation returned
    // silently whenever invoiceScanBusy was true, which is almost always during live
    // detection and made the button appear to do nothing.
    invoiceCaptureGeneration += 1;
    invoiceCaptureRequested = true;
    if (invoiceScanTimer) {
      window.clearInterval(invoiceScanTimer);
      invoiceScanTimer = null;
    }
    if (invoiceCaptureButton) {
      invoiceCaptureButton.disabled = true;
      invoiceCaptureButton.textContent = "正在拍攝…";
      invoiceCaptureButton.classList.add("is-capturing");
      invoiceCaptureButton.setAttribute("aria-busy", "true");
    }
    setInvoiceScanStatus("正在拍攝目前鏡頭畫面…");

    try {
      if (!invoiceCameraStream || !invoiceVideo.videoWidth) {
        throw new Error("相機畫面已停止，請重新啟動掃描。");
      }

      // Do not wait for the continuous detector. Snapshot decoding uses jsQR
      // directly and can proceed even while a WASM/video detection is in flight.
      const file = await captureInvoiceCameraFrame();
      setInvoiceScanStatus("已拍照，正在解析發票 QR Code…");
      if (invoiceCaptureButton) invoiceCaptureButton.textContent = "已拍照，分析中…";

      const codes = await decodeInvoicePhotoWithJsQr(file);
      const leftCode = codes.find((item) =>
        Boolean(window.FamilyReceiptParser.parseTaiwanInvoiceQr(item.value, null))
      );
      const rightCode = codes.find((item) => String(item.value || "").startsWith("**"));
      const leftValue = leftCode?.value || invoiceLeftQrValue;
      const rightValue = rightCode?.value || invoiceRightQrValue || null;

      if (leftValue) {
        const verified = window.FamilyReceiptParser.parseTaiwanInvoiceQr(leftValue, rightValue);
        if (verified) {
          invoiceLeftQrValue = leftValue;
          invoiceRightQrValue = rightValue;
          setInvoiceScanStatus(
            rightValue
              ? "已拍照並讀取發票基本資料及商品明細，正在帶入核對畫面…"
              : "已拍照並讀取發票基本資料；商品明細碼沒有讀到也不影響記帳，正在帶入核對畫面…"
          );
          const pair = [
            { format: "QR Code", value: leftValue, side: "left" },
            ...(rightValue ? [{ format: "QR Code", value: rightValue, side: "right" }] : [])
          ];
          stopInvoiceScanner();
          await handleFile(file, pair);
          return;
        }
      }

      if (rightValue && !leftValue) {
        setInvoiceScanStatus("已拍照，但目前只讀到商品明細碼；還需要發票基本資料碼才能帶入日期與金額。請調整角度再拍一次。", true);
      } else {
        setInvoiceScanStatus(
          "已拍照，但沒有讀到有效的發票基本資料 QR Code。請靠近一點、避免反光，再按「拍照辨識」。",
          true
        );
      }
    } catch (error) {
      setInvoiceScanStatus(error && error.message ? error.message : "拍照或 QR 解析失敗，請再試一次。", true);
    } finally {
      invoiceCaptureRequested = false;
      // The live scan callback owns invoiceScanBusy and will release it in its
      // own finally block; do not clear another operation's lock here.
      if (invoiceCaptureButton) {
        invoiceCaptureButton.textContent = "拍照辨識（備用）";
        invoiceCaptureButton.classList.remove("is-capturing");
        invoiceCaptureButton.removeAttribute("aria-busy");
        invoiceCaptureButton.disabled = !invoiceCameraStream;
      }
      // Resume automatic whole-frame scanning after an unsuccessful still-photo attempt.
      if (invoiceCameraStream && !invoiceScanTimer) {
        invoiceScanTimer = window.setInterval(scanInvoiceCameraFrame, 350);
      }
    }
  }

  async function createNativeInvoiceBarcodeDetector() {
    return createLocalBarcodeDetector(["qr_code"]);
  }

  async function scanInvoiceCameraFrame() {
    if (!invoiceCameraStream || invoiceScanBusy || invoiceCaptureRequested || !invoiceVideo.videoWidth) return;
    if (!invoiceBarcodeDetector && typeof window.jsQR !== "function") return;
    invoiceScanBusy = true;
    const scanGeneration = invoiceCaptureGeneration;
    try {
      // Prefer multi-QR detection, but never let one video/WASM decoder failure
      // turn off the camera or disable the user's manual capture fallback.
      if (invoiceBarcodeDetector) {
        try {
          const detected = await invoiceBarcodeDetector.detect(invoiceVideo);
          if (invoiceCaptureRequested || scanGeneration !== invoiceCaptureGeneration) return;
          for (const code of detected || []) acceptInvoiceQrPayload(code.rawValue);
        } catch (_error) {
          invoiceBarcodeDetector = null;
          setInvoiceScanStatus("多 QR 引擎暫時無法讀取，已切換單 QR 備援；相機會繼續保持開啟。");
        }
      }

      // jsQR reads one QR per frame. If the basic invoice QR is not yet found,
      // keep checking the full frame until the primary payload appears.
      if (!invoiceLeftQrValue && typeof window.jsQR === "function") {
        const fallbackValue = await decodeInvoiceVideoFrameWithJsQr();
        if (invoiceCaptureRequested || scanGeneration !== invoiceCaptureGeneration) return;
        if (fallbackValue) acceptInvoiceQrPayload(fallbackValue);
      }

      if (invoiceLeftQrValue) {
        setInvoiceScanStatus("已讀取發票基本資料，正在帶入記帳欄位…");
        await completeInvoiceQrScan();
      } else if (invoiceRightQrValue) {
        setInvoiceScanStatus("已找到商品明細碼，正在尋找發票基本資料碼…");
      } else {
        setInvoiceScanStatus("正在自動搜尋整個畫面的 QR Code。先讀到發票基本資料碼即可完成，不必等商品明細碼。");
      }
    } catch (_error) {
      // Keep the camera and capture button available so the user can retry with
      // a still frame instead of being left with an inert, disabled button.
      setInvoiceScanStatus("即時掃描暫時發生錯誤；相機仍保持開啟，可按下方「拍照辨識」重試。", true);
    } finally {
      invoiceScanBusy = false;
    }
  }

  function getRememberedInvoiceCameraId() {
    try { return localStorage.getItem(INVOICE_CAMERA_STORAGE_KEY) || ""; } catch (_error) { return ""; }
  }

  function rememberInvoiceCameraId(deviceId) {
    if (!deviceId) return;
    try { localStorage.setItem(INVOICE_CAMERA_STORAGE_KEY, deviceId); } catch (_error) {}
  }

  function isUltraWideCameraLabel(label) {
    return /ultra.?wide|ultra.?wide.?angle|0[.,]5\s*x|0[.,]6\s*x|0[.,]5x|0[.,]6x|超廣角|超广角|超廣角鏡頭/i.test(String(label || ""));
  }

  function preferredRearCamera(devices, rememberedId = "", activeDeviceId = "") {
    const rear = devices.filter((device) =>
      device.kind === "videoinput" &&
      !/front|user|selfie|前置/i.test(device.label)
    );
    if (rememberedId) {
      const remembered = rear.find((device) => device.deviceId === rememberedId);
      if (remembered && !isUltraWideCameraLabel(remembered.label)) return remembered;
    }
    const ranked = rear.map((device, index) => {
      const label = String(device.label || "");
      let score = -index;
      if (isUltraWideCameraLabel(label) || /telephoto|periscope|macro|depth|長焦|微距/i.test(label)) score -= 500;
      if (/main|primary|standard|normal|主鏡頭|主相機|標準鏡頭|1[.,]0\s*x/i.test(label)) score += 200;
      if (/back|rear|facing back|後置|後鏡頭/i.test(label)) score += 100;
      if (device.deviceId === activeDeviceId && !label) score += 50;
      return { device, score };
    }).sort((a, b) => b.score - a.score);
    return ranked[0]?.device || rear[0] || null;
  }

  async function refreshInvoiceCameraControls() {
    if (!invoiceCameraSelect || !navigator.mediaDevices?.enumerateDevices) return;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter((device) => device.kind === "videoinput" && !/front|user|前置/i.test(device.label));
    const selectedId = invoiceCameraTrack?.getSettings?.().deviceId || invoiceCameraDeviceId;
    invoiceCameraSelect.replaceChildren();
    cameras.forEach((device, index) => {
      const option = document.createElement("option");
      option.value = device.deviceId;
      option.textContent = device.label || ("後置鏡頭 " + (index + 1));
      invoiceCameraSelect.appendChild(option);
    });
    if (selectedId && cameras.some((device) => device.deviceId === selectedId)) {
      invoiceCameraSelect.value = selectedId;
    }
    invoiceCameraSelect.disabled = cameras.length < 2;
    const capabilities = invoiceCameraTrack?.getCapabilities?.() || {};
    if (invoiceZoomControl && capabilities.zoom) {
      const minZoom = Number(capabilities.zoom.min ?? 1);
      const maxZoom = Number(capabilities.zoom.max ?? 1);
      const reportedZoom = Number(invoiceCameraTrack?.getSettings?.().zoom);
      const displayZoom = Number.isFinite(reportedZoom)
        ? reportedZoom
        : Math.min(maxZoom, Math.max(minZoom, 1));
      invoiceZoomControl.min = String(minZoom);
      invoiceZoomControl.max = String(maxZoom);
      invoiceZoomControl.step = String(capabilities.zoom.step ?? 0.1);
      invoiceZoomControl.value = String(displayZoom);
      invoiceZoomControl.disabled = maxZoom <= minZoom;
      if (invoiceZoomValue) invoiceZoomValue.textContent = displayZoom.toFixed(1) + "×";
    } else if (invoiceZoomControl) {
      invoiceZoomControl.disabled = true;
      invoiceZoomControl.value = "1";
      if (invoiceZoomValue) invoiceZoomValue.textContent = "裝置不支援";
    }
  }

  async function configureInvoiceCameraTrack(track) {
    if (!track || typeof track.getCapabilities !== "function" || typeof track.applyConstraints !== "function") return;
    try {
      const capabilities = track.getCapabilities() || {};
      const advanced = {};
      if (capabilities.zoom) {
        const minZoom = Number(capabilities.zoom.min ?? 1);
        const maxZoom = Number(capabilities.zoom.max ?? 1);
        // 1.0x is the normal/main-camera view; never initialize to the minimum
        // zoom because many multi-lens Android phones expose 0.5x ultra-wide there.
        advanced.zoom = Math.min(maxZoom, Math.max(minZoom, 1));
      }
      if (Array.isArray(capabilities.focusMode) && capabilities.focusMode.includes("continuous")) {
        advanced.focusMode = "continuous";
      }
      if (Array.isArray(capabilities.exposureMode) && capabilities.exposureMode.includes("continuous")) {
        advanced.exposureMode = "continuous";
      }
      if (Object.keys(advanced).length) await track.applyConstraints({ advanced: [advanced] });
    } catch (_error) {
      // Unsupported zoom or focus controls must not prevent the camera from starting.
    }
  }

  async function applyInvoiceCamera(deviceId = "") {
    if (invoiceScanTimer) { window.clearInterval(invoiceScanTimer); invoiceScanTimer = null; }
    if (invoiceCameraStream) invoiceCameraStream.getTracks().forEach((track) => track.stop());
    invoiceCameraStream = null;
    invoiceCameraTrack = null;
    const video = {
      width: { ideal: 1920 },
      height: { ideal: 1080 },
      frameRate: { ideal: 30, max: 30 }
    };
    if (deviceId) video.deviceId = { exact: deviceId };
    else video.facingMode = { ideal: "environment" };
    invoiceCameraStream = await navigator.mediaDevices.getUserMedia({ audio: false, video });
    invoiceCameraTrack = invoiceCameraStream.getVideoTracks()[0] || null;
    invoiceCameraDeviceId = invoiceCameraTrack?.getSettings?.().deviceId || deviceId;
    await configureInvoiceCameraTrack(invoiceCameraTrack);
    invoiceVideo.srcObject = invoiceCameraStream;
    await invoiceVideo.play();
    await refreshInvoiceCameraControls();
    invoiceScanTimer = window.setInterval(scanInvoiceCameraFrame, 350);
  }

  async function startInvoiceScanner() {
    if (invoiceCameraStream) return;
    clearPhoto();
    invoiceCameraPanel.classList.remove("hidden");
    invoiceCameraPanel.classList.remove("camera-unavailable");
    invoiceScanButton.disabled = true;
    setInvoiceScanStatus("正在準備全畫面多 QR 辨識引擎與後置鏡頭…");
    invoiceLeftQrValue = null;
    invoiceRightQrValue = null;

    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      invoiceCameraPanel.classList.add("camera-unavailable");
      setInvoiceScanStatus("目前瀏覽器無法啟用即時相機。請改用「一般收據：拍照辨識」或「選擇照片／收據」。", true);
      setStatus("即時相機目前不可用，可改用一般收據拍照或選擇手機照片。");
      invoiceScanButton.disabled = false;
      return;
    }

    try {
      const detectorResult = await Promise.all([
        createNativeInvoiceBarcodeDetector().catch(() => null),
        loadScript(JSQR_SRC, "jsQR").catch(() => null)
      ]);
      invoiceBarcodeDetector = detectorResult[0];
      const jsQrAvailable = typeof detectorResult[1] === "function";
      if (!invoiceBarcodeDetector && !jsQrAvailable) {
        throw new Error("QR 掃描程式無法載入。請確認網路連線，或改用「選擇照片／收據」。");
      }
      await applyInvoiceCamera("");
      const availableCameras = await navigator.mediaDevices.enumerateDevices();
      const activeDeviceId = invoiceCameraTrack?.getSettings?.().deviceId || "";
      const preferredCamera = preferredRearCamera(
        availableCameras,
        getRememberedInvoiceCameraId(),
        activeDeviceId
      );
      if (preferredCamera?.deviceId && preferredCamera.deviceId !== activeDeviceId) {
        await applyInvoiceCamera(preferredCamera.deviceId);
      } else {
        await configureInvoiceCameraTrack(invoiceCameraTrack);
        await refreshInvoiceCameraControls();
      }
      invoiceCameraDeviceId = invoiceCameraTrack?.getSettings?.().deviceId || invoiceCameraDeviceId;
      invoiceCameraSelect && (invoiceCameraSelect.value = invoiceCameraDeviceId);
      invoiceCameraPanel.classList.remove("camera-unavailable");
      const activeCameraLabel = invoiceCameraSelect?.selectedOptions?.[0]?.textContent || "後置主鏡頭";
      const currentZoom = Number(invoiceCameraTrack?.getSettings?.().zoom);
      const zoomLabel = Number.isFinite(currentZoom) ? currentZoom.toFixed(1) + "×" : "預設倍率";
      setInvoiceScanStatus(
        (invoiceBarcodeDetector ? "已啟用全畫面多 QR 掃描與備援辨識。" : "已啟用 QR 備援掃描。") +
        "目前鏡頭：" + activeCameraLabel + "，" + zoomLabel +
        "；下次會沿用你手動選過的後置鏡頭。"
      );
      cameraButton.disabled = true;
      chooseButton.disabled = true;
      invoiceStopButton.disabled = false;
      if (invoiceCaptureButton) invoiceCaptureButton.disabled = false;
      invoiceScanButton.disabled = true;
    } catch (error) {
      stopInvoiceScanner(false);
      invoiceCameraPanel.classList.remove("hidden");
      invoiceCameraPanel.classList.add("camera-unavailable");
      setInvoiceScanStatus(
        error && error.name === "NotAllowedError"
          ? "相機權限未開啟。請允許瀏覽器使用相機，或改用拍照／選擇照片。"
          : (error && error.message ? error.message : "無法啟動相機，請改用拍照或選擇照片。"),
        true
      );
      invoiceScanButton.disabled = false;
    }
  }

  invoiceScanButton?.addEventListener("click", startInvoiceScanner);
  invoiceCameraSelect?.addEventListener("change", async () => {
    if (!invoiceCameraStream || !invoiceCameraSelect.value) return;
    try {
      setInvoiceScanStatus("正在切換鏡頭…");
      rememberInvoiceCameraId(invoiceCameraSelect.value);
      await applyInvoiceCamera(invoiceCameraSelect.value);
      const cameraLabel = invoiceCameraSelect.selectedOptions?.[0]?.textContent || "所選後置鏡頭";
      const zoom = Number(invoiceCameraTrack?.getSettings?.().zoom);
      setInvoiceScanStatus("已切換至 " + cameraLabel + (Number.isFinite(zoom) ? "（" + zoom.toFixed(1) + "×）" : "") + "；下次開啟會自動使用這個鏡頭。");
    } catch (error) {
      setInvoiceScanStatus("切換鏡頭失敗，請選擇其他鏡頭或重新啟動掃描。", true);
    }
  });
  invoiceZoomControl?.addEventListener("input", async () => {
    if (!invoiceCameraTrack?.applyConstraints) return;
    const zoom = Number(invoiceZoomControl.value);
    try {
      await invoiceCameraTrack.applyConstraints({ advanced: [{ zoom }] });
      if (invoiceZoomValue) invoiceZoomValue.textContent = zoom.toFixed(1) + "×";
    } catch (_error) {
      setInvoiceScanStatus("此鏡頭暫時無法調整縮放，請切換鏡頭。", true);
    }
  });
  invoiceCaptureButton?.addEventListener("click", (event) => {
    event.preventDefault();
    captureAndDecodeInvoicePhoto();
  });
  invoiceStopButton?.addEventListener("click", () => {
    stopInvoiceScanner();
    setInvoiceScanStatus("已停止掃描。你可以重新啟動相機，或改用收據拍照。");
    setStatus("已停止電子發票掃描。需要時可重新啟動雙 QR 掃描，或改用收據拍照。");
    invoiceScanButton.disabled = false;
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && invoiceCameraStream) {
      stopInvoiceScanner();
      setInvoiceScanStatus("切換到其他畫面後，相機已自動關閉。需要時請重新啟動雙 QR 掃描。");
      setStatus("相機已自動關閉。回到本頁後可重新啟動雙 QR 掃描。");
    }
  });
  window.addEventListener("pagehide", () => stopInvoiceScanner());

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
    stopInvoiceScanner();
    if (window.clearReceiptCaptureReturn) window.clearReceiptCaptureReturn();
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

  async function handleFile(file, predecodedCodes = null) {
    if (!file) return;
    window.__familyReceiptPhotoReturned = true;
    if (window.clearReceiptCaptureReturn) window.clearReceiptCaptureReturn();
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
      const codeResults = Array.isArray(predecodedCodes) && predecodedCodes.length
        ? predecodedCodes
        : await decodeLocalCodes(file);
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
      if (parsedFields) {
        fillButton.disabled = !hasReviewData();
        // Bring the review fields into view automatically after live scanning.
        workspace.scrollIntoView({ behavior: "smooth", block: "start" });
      }
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
    const structuredItems = Array.isArray(parsedFields && parsedFields.items)
      ? parsedFields.items
      : [];

    if (amount) $("transaction-amount").value = amount;
    if (window.setTransactionPurchaseItems) {
      window.setTransactionPurchaseItems(
        structuredItems.map((item) => ({
          item_name: item.name,
          quantity: item.quantity,
          unit: null,
          unit_price: item.unitPrice
        })),
        { autoAmount: false }
      );
    }
    if (date) $("transaction-date").value = date;
    if (invoiceNumber) $("transaction-reference").value = invoiceNumber;
    if (merchant) $("transaction-description").value = merchant.slice(0, 255);
    else if (!$("transaction-description").value.trim()) $("transaction-description").value = "發票／收據消費（請補商家名稱）";

    const noteParts = [];
    noteParts.push("憑證種類：" + receiptTypeLabel());
    if (sellerTaxId) noteParts.push("賣方統編：" + sellerTaxId);
    if (buyerTaxId) noteParts.push("買方統編：" + buyerTaxId);
    if (itemLines && !structuredItems.length) {
      noteParts.push("OCR 商品明細文字（尚未拆成結構化明細，請人工核對）：\\n" + itemLines);
    }
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

  cameraButton.addEventListener("click", () => {
    if (window.prepareReceiptCaptureReturn) window.prepareReceiptCaptureReturn();
    cameraInput.click();
  });
  chooseButton.addEventListener("click", () => {
    if (window.prepareReceiptCaptureReturn) window.prepareReceiptCaptureReturn();
    fileInput.click();
  });
  const handleFileInputChange = (input, label) => {
    const file = input.files && input.files[0];
    if (file) {
      handleFile(file);
    } else {
      if (window.clearReceiptCaptureReturn) window.clearReceiptCaptureReturn();
      setStatus(label + "已取消；目前資料沒有變更。");
    }
  };
  cameraInput.addEventListener("change", () => handleFileInputChange(cameraInput, "拍照"));
  fileInput.addEventListener("change", () => handleFileInputChange(fileInput, "選擇照片"));
  cameraInput.addEventListener("cancel", () => {
    if (window.clearReceiptCaptureReturn) window.clearReceiptCaptureReturn();
    setStatus("已取消拍照；仍可重新拍攝或選擇手機照片。");
  });
  fileInput.addEventListener("cancel", () => {
    if (window.clearReceiptCaptureReturn) window.clearReceiptCaptureReturn();
    setStatus("已取消選擇照片；目前資料沒有變更。");
  });
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
