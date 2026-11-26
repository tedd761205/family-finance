(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FamilyReceiptParser = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TYPE_LABELS = {
    electronic_invoice: "電子發票證明聯",
    two_part_invoice: "二聯式統一發票",
    three_part_invoice: "三聯式統一發票",
    receipt: "一般收據",
    handwritten: "手寫憑證",
    unknown: "尚待判斷"
  };

  function validDate(year, month, day) {
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
    return String(year).padStart(4, "0") + "-" + String(month).padStart(2, "0") + "-" + String(day).padStart(2, "0");
  }

  function decodeBase64Utf8(value) {
    try {
      const binary = typeof atob === "function"
        ? atob(value)
        : (typeof Buffer !== "undefined" ? Buffer.from(value, "base64").toString("binary") : "");
      if (!binary) return value;
      const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
      return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    } catch (_error) {
      return value;
    }
  }

  function decodeItemName(value, encoding) {
    if (!value) return "";
    if (String(encoding) === "2") return decodeBase64Utf8(value);
    if (String(encoding) === "0") {
      try {
        const bytes = Uint8Array.from(value, (character) => character.charCodeAt(0) & 255);
        return new TextDecoder("big5", { fatal: false }).decode(bytes);
      } catch (_error) {
        return value;
      }
    }
    return value;
  }

  function parseItemTriples(parts, encoding, startAt) {
    const items = [];
    for (let index = startAt || 0; index + 2 < parts.length; index += 3) {
      const name = decodeItemName(parts[index], encoding).trim();
      const quantity = Number(String(parts[index + 1] || "").replace(/,/g, ""));
      const unitPrice = Number(String(parts[index + 2] || "").replace(/,/g, ""));
      if (!name || !Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(unitPrice) || unitPrice < 0) continue;
      items.push({
        name: name.slice(0, 120),
        quantity: quantity,
        unitPrice: unitPrice
      });
    }
    return items;
  }

  function parseTaiwanInvoiceQr(leftValue, rightValue) {
    const left = String(leftValue || "").trim();
    const right = String(rightValue || "").trim();
    if (!/^[A-Z]{2}\d{8}\d{7}\d{4}[0-9A-F]{16}/i.test(left)) return null;

    // The official payload has a fixed 45-character header before buyer tax ID,
    // followed by seller tax ID and a 24-character encrypted verification field.
    // Locate the separator before the optional item extension so older padded
    // seller-ID samples remain readable without shifting the remaining fields.
    // The first 77 characters are the fixed invoice header. Item details after
    // that header are optional; a valid left QR must still be accepted when no
    // colon-delimited extension is printed on the code.
    const extensionSeparator = left.indexOf(":", 45);
    // When there is no extension separator, the final 24 characters are the
    // authentication field. This also tolerates legacy samples with a padded
    // seller tax-ID field (the normal domestic layout is 77 characters).
    const authStart = extensionSeparator >= 0 ? extensionSeparator - 24 : left.length - 24;
    if (authStart < 53 || authStart > 55) return null;
    const fixedHeaderEnd = authStart + 24;
    if (left.length < fixedHeaderEnd) return null;
    if (extensionSeparator >= 0 && extensionSeparator !== fixedHeaderEnd) return null;

    const invoiceNumber = left.slice(0, 10).toUpperCase();
    const rocDate = left.slice(10, 17);
    const randomCode = left.slice(17, 21);
    const salesHex = left.slice(21, 29);
    const totalHex = left.slice(29, 37);
    const buyerTaxIdRaw = left.slice(37, 45);
    const sellerTaxIdRaw = left.slice(45, authStart);
    const dateMatch = rocDate.match(/^(\d{3})(\d{2})(\d{2})$/);
    const date = dateMatch
      ? validDate(Number(dateMatch[1]) + 1911, Number(dateMatch[2]), Number(dateMatch[3]))
      : null;
    const parsedTotal = Number.parseInt(totalHex, 16);
    const parsedSales = Number.parseInt(salesHex, 16);
    const authEnd = extensionSeparator >= 0 ? extensionSeparator : fixedHeaderEnd;
    const auth = left.slice(authStart, authEnd);
    if (auth.length !== 24 || !/^[A-Za-z0-9+/=]{24}$/.test(auth)) return null;

    const extension = extensionSeparator >= 0 ? left.slice(extensionSeparator + 1) : "";
    const extensionParts = extension ? extension.split(":") : [];
    const encoding = extensionParts[3] || "1";
    const items = parseItemTriples(extensionParts, encoding, 4);
    let rightItems = [];
    if (right.startsWith("**")) {
      rightItems = parseItemTriples(right.slice(2).split(":"), encoding, 0);
    }

    const normalizeTaxId = (value) => {
      const digits = String(value || "");
      if (!/^\d{8,10}$/.test(digits) || /^0+$/.test(digits)) return null;
      const normalized = digits.slice(-8);
      return /^\d{8}$/.test(normalized) ? normalized : null;
    };

    return {
      invoiceNumber: invoiceNumber,
      date: date,
      randomCode: randomCode,
      salesAmount: Number.isFinite(parsedSales) && parsedSales > 0 ? String(parsedSales) : null,
      totalAmount: Number.isFinite(parsedTotal) && parsedTotal > 0 ? String(parsedTotal) : null,
      buyerTaxId: normalizeTaxId(buyerTaxIdRaw),
      sellerTaxId: normalizeTaxId(sellerTaxIdRaw),
      items: items.concat(rightItems),
      itemCount: Number(extensionParts[2]) || null,
      source: "qr"
    };
  }

    function extractTextDate(text) {
    let match = text.match(/(?:^|[^\d])(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})(?!\d)/);
    if (match) {
      const date = validDate(Number(match[1]), Number(match[2]), Number(match[3]));
      if (date) return date;
    }
    match = text.match(/(?:民國\s*)?(\d{2,3})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?/);
    if (match) return validDate(Number(match[1]) + 1911, Number(match[2]), Number(match[3]));
    match = text.match(/(?:^|[^\d])(\d{3})(\d{2})(\d{2})(?!\d)/);
    if (match) return validDate(Number(match[1]) + 1911, Number(match[2]), Number(match[3]));
    return null;
  }

  function parseMoney(value) {
    if (!value) return null;
    const normalized = String(value).replace(/[，,\s$元]/g, "").replace(/[^\d.]/g, "");
    const amount = Number(normalized);
    return Number.isFinite(amount) && amount > 0 ? String(amount) : null;
  }

  function extractTextAmount(text) {
    const labelPattern = /(?:總計額|總計|應付金額|應付|合計|實付金額|實付|總金額|總額|金額|TOTAL|AMOUNT\s*DUE)\s*[：:=]?\s*(?:(?:NTD|TWD|NT\s*\$)\s*)?\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)/gi;
    const matches = Array.from(text.matchAll(labelPattern));
    if (matches.length) return parseMoney(matches[matches.length - 1][1]);

    const lineMatches = text.split(/\r?\n/).map((line) => {
      if (!/(總計|應付|合計|實付|TOTAL)/i.test(line)) return null;
      const values = Array.from(line.matchAll(/(?:NTD|TWD|NT\s*\$)?\s*\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)/gi));
      return values.length ? parseMoney(values[values.length - 1][1]) : null;
    }).filter(Boolean);
    return lineMatches.length ? lineMatches[lineMatches.length - 1] : null;
  }

  function extractLabeledValue(text, labels, pattern) {
    for (const label of labels) {
      const expression = new RegExp("(?:" + label + ")\\s*[：:]?\\s*(" + pattern + ")", "i");
      const match = text.match(expression);
      if (match) return match[1].trim();
    }
    return null;
  }

  function extractMerchant(text) {
    const explicit = extractLabeledValue(
      text,
      ["商家名稱", "營業人名稱", "賣方名稱", "店家名稱", "店名", "商號"],
      "[^\\r\\n]{2,60}"
    );
    if (explicit) return explicit.replace(/^[：:\s]+/, "").trim().slice(0, 100);

    const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const titleIndex = lines.findIndex((line) => /電子發票證明聯|統一發票/.test(line));
    const candidates = lines.slice(0, titleIndex >= 0 ? Math.min(titleIndex, 5) : 3);
    const ignored = /^(電子發票|發票|統一發票|收據|買方|賣方|日期|時間|總計|隨機碼|統編|統一編號|號碼)/;
    const candidate = candidates.find((line) =>
      line.length >= 2 &&
      line.length <= 40 &&
      !ignored.test(line) &&
      !/^\d[\d\s./:-]*$/.test(line) &&
      /[\u3400-\u9fffA-Za-z]/.test(line)
    );
    return candidate ? candidate.replace(/^[#*·\s]+|[#*·\s]+$/g, "").slice(0, 100) : null;
  }

  function detectReceiptType(text, hasElectronicQr) {
    if (hasElectronicQr) return "electronic_invoice";
    if (/三聯式(?:統一)?發票|三聯式/.test(text)) return "three_part_invoice";
    if (/二聯式(?:統一)?發票|二聯式/.test(text)) return "two_part_invoice";
    if (/收據|receipt/i.test(text)) return /手寫|手開/.test(text) ? "handwritten" : "receipt";
    if (/手寫|手開/.test(text)) return "handwritten";
    return "unknown";
  }

  function extractBarcodeInvoiceNumber(codes) {
    for (const code of codes || []) {
      if (!/barcode|code.?39|code.?128|ean/i.test(String(code.format || ""))) continue;
      const value = String(code.value || "").replace(/^\*|\*$/g, "").trim().toUpperCase();
      const match = value.match(/^\d{5}([A-Z]{2}\d{8})\d{4}$/);
      if (match) return match[1];
    }
    return null;
  }

  function parseReceiptData(text, codeResults) {
    const sourceText = String(text || "");
    const codes = Array.isArray(codeResults) ? codeResults : [];
    const qrCodes = codes.filter((item) => /qr/i.test(String(item.format || "")) || String(item.value || "").startsWith("**"));
    let leftQr = qrCodes.find((item) => item.side === "left" && !String(item.value || "").startsWith("**"));
    let rightQr = qrCodes.find((item) => item.side === "right" && String(item.value || "").startsWith("**"));
    if (!leftQr) leftQr = qrCodes.find((item) => !String(item.value || "").startsWith("**") && String(item.value || "").length >= 77);
    if (!rightQr) rightQr = qrCodes.find((item) => String(item.value || "").startsWith("**"));

    const qr = leftQr ? parseTaiwanInvoiceQr(leftQr.value, rightQr && rightQr.value) : null;
    const textInvoiceNumber = (sourceText.match(/\b([A-Z]{2})[\s-]?(\d{8})\b/i) || []);
    const barcodeInvoiceNumber = extractBarcodeInvoiceNumber(codes);
    const invoiceNumber = qr && qr.invoiceNumber
      ? qr.invoiceNumber
      : (textInvoiceNumber[1] ? textInvoiceNumber[1].toUpperCase() + textInvoiceNumber[2] : barcodeInvoiceNumber);
    const invoiceNumberSource = qr && qr.invoiceNumber
      ? "qr"
      : (textInvoiceNumber[1] ? "ocr" : (barcodeInvoiceNumber ? "barcode" : "none"));

    const sellerTaxId = qr && qr.sellerTaxId
      ? qr.sellerTaxId
      : extractLabeledValue(sourceText, ["賣方統編", "賣方統一編號", "賣方"], "\\d{8}");
    const buyerTaxId = qr && qr.buyerTaxId
      ? qr.buyerTaxId
      : extractLabeledValue(sourceText, ["買方統編", "買方統一編號", "買方"], "\\d{8}");

    const fields = {
      type: detectReceiptType(sourceText, Boolean(qr)),
      merchant: extractMerchant(sourceText),
      date: qr && qr.date ? qr.date : extractTextDate(sourceText),
      amount: qr && qr.totalAmount ? qr.totalAmount : extractTextAmount(sourceText),
      invoiceNumber: invoiceNumber || null,
      sellerTaxId: sellerTaxId || null,
      buyerTaxId: buyerTaxId || null,
      items: qr ? qr.items : [],
      source: qr ? "qr" : "ocr",
      hasElectronicQr: Boolean(qr),
      codeCount: codes.length,
      // Per-field provenance distinguishes QR values from OCR candidates.
      fieldSources: {
        merchant: extractMerchant(sourceText) ? "ocr" : "none",
        date: qr && qr.date ? "qr" : (extractTextDate(sourceText) ? "ocr" : "none"),
        amount: qr && qr.totalAmount ? "qr" : (extractTextAmount(sourceText) ? "ocr" : "none"),
        invoiceNumber: invoiceNumberSource
      }
    };
    fields.typeLabel = TYPE_LABELS[fields.type] || TYPE_LABELS.unknown;
    return fields;
  }

  return {
    TYPE_LABELS: TYPE_LABELS,
    parseTaiwanInvoiceQr: parseTaiwanInvoiceQr,
    parseReceiptData: parseReceiptData,
    detectReceiptType: detectReceiptType
  };
});
