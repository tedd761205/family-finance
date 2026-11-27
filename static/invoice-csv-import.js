(() => {
  "use strict";

  const MAX_BYTES = 10 * 1024 * 1024;
  const MAX_LINES = 20000;
  const money = new Intl.NumberFormat("zh-TW", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  let parsedResult = null;
  let currentFilter = "all";
  let currentMonth = "all";
  let currentSearch = "";
  let currentPage = 1;
  let pageSize = 10;
  let previewSaved = false;
  let previewFamilyId = null;
  let historyPage = 1;
  let historyPageSize = 20;
  let historyRequestSequence = 0;
  let historySearchTimer = null;

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function decodeBytes(buffer) {
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(buffer).replace(/^\uFEFF/, "");
    } catch (_) {
      try {
        return new TextDecoder("big5").decode(buffer).replace(/^\uFEFF/, "");
      } catch (error) {
        throw new Error("檔案編碼無法辨識，請另存為 UTF-8 或 Big5/CP950 CSV。");
      }
    }
  }

  function splitPipe(line) {
    const fields = [];
    let value = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (ch === '"') {
        if (quoted && line[i + 1] === '"') {
          value += '"';
          i += 1;
        } else {
          quoted = !quoted;
        }
      } else if (ch === "|" && !quoted) {
        fields.push(value.trim());
        value = "";
      } else {
        value += ch;
      }
    }
    fields.push(value.trim());
    return fields;
  }

  function parseDate(value) {
    const raw = String(value || "").trim();
    if (!/^\d{8}$/.test(raw)) throw new Error("發票日期必須為 YYYYMMDD");
    const year = Number(raw.slice(0, 4));
    const month = Number(raw.slice(4, 6));
    const day = Number(raw.slice(6, 8));
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
      throw new Error("發票日期不是有效日期");
    }
    return raw.slice(0, 4) + "-" + raw.slice(4, 6) + "-" + raw.slice(6, 8);
  }

  function parseCents(value) {
    const raw = String(value || "").trim().replace(/[,NTD$元]/gi, "");
    if (!/^-?\d+(?:\.\d{1,2})?$/.test(raw)) throw new Error("金額格式無法辨識");
    const negative = raw.startsWith("-");
    const unsigned = negative ? raw.slice(1) : raw;
    const parts = unsigned.split(".");
    const whole = Number(parts[0]);
    const fraction = Number(((parts[1] || "") + "00").slice(0, 2));
    const cents = whole * 100 + fraction;
    if (!Number.isSafeInteger(cents)) throw new Error("金額超出可處理範圍");
    return negative ? -cents : cents;
  }

  function parseText(text) {
    const lines = text.split(/\r?\n/);
    if (lines.length > MAX_LINES) throw new Error("CSV 行數超過 20,000 行，請分批匯入。");

    const invoices = [];
    const invoiceByNumber = new Map();
    const detailsByNumber = new Map();
    const malformed = [];
    let detailCount = 0;
    let duplicateHeaders = 0;
    let recognizedHeaderRows = 0;

    lines.forEach((sourceLine, index) => {
      let line = sourceLine.trim();
      if (!line) return;
      line = line.replace(/^(?:表頭|明細)\s*=\s*/u, "");
      const fields = splitPipe(line);
      const kind = (fields[0] || "").trim().toUpperCase();

      if (kind === "M") {
        if ((fields[1] || "").trim() === "載具名稱") {
          recognizedHeaderRows += 1;
          return;
        }
        if (fields.length < 9) {
          malformed.push({ line: index + 1, message: "表頭欄位不足（需要 M 加 8 個欄位）" });
          return;
        }
        const carrierType = fields[1];
        const carrierNumber = fields[2];
        const invoiceNumber = fields[6].toUpperCase();
        try {
          if (!invoiceNumber) throw new Error("發票號碼不可空白");
          if (!/^[A-Z]{2}\d{8}$/.test(invoiceNumber)) throw new Error("發票號碼格式異常");
          const date = parseDate(fields[3]);
          const totalCents = parseCents(fields[7]);
          if (totalCents < 0) throw new Error("發票總金額不可為負數");
          const invoice = {
            date,
            carrierType,
            carrierNumber,
            merchantTaxId: fields[4],
            merchantName: fields[5],
            invoiceNumber,
            totalCents,
            invoiceStatus: fields[8],
            items: [],
            duplicate: false,
            errors: []
          };
          if (invoiceByNumber.has(invoiceNumber)) {
            duplicateHeaders += 1;
            invoice.duplicate = true;
            invoice.errors.push("檔案內出現重複發票號碼");
            invoiceByNumber.get(invoiceNumber).duplicate = true;
            invoiceByNumber.get(invoiceNumber).errors.push("檔案內出現重複發票號碼");
          } else {
            invoiceByNumber.set(invoiceNumber, invoice);
            invoices.push(invoice);
          }
        } catch (error) {
          malformed.push({ line: index + 1, invoiceNumber, message: error.message });
        }
        return;
      }

      if (kind === "D") {
        if ((fields[1] || "").trim() === "發票號碼") {
          recognizedHeaderRows += 1;
          return;
        }
        if (fields.length < 4) {
          malformed.push({ line: index + 1, message: "明細欄位不足（需要 D 加 3 個欄位）" });
          return;
        }
        const invoiceNumber = (fields[1] || "").trim().toUpperCase();
        const itemName = fields.slice(3).join("|").trim();
        try {
          if (!invoiceNumber) throw new Error("明細發票號碼不可空白");
          if (!itemName) throw new Error("品項名稱不可空白");
          const amountCents = parseCents(fields[2]);
          const item = { invoiceNumber, amountCents, itemName, line: index + 1 };
          if (!detailsByNumber.has(invoiceNumber)) detailsByNumber.set(invoiceNumber, []);
          detailsByNumber.get(invoiceNumber).push(item);
          detailCount += 1;
        } catch (error) {
          malformed.push({ line: index + 1, invoiceNumber, message: error.message });
        }
      }
    });

    if (!invoices.length) throw new Error("沒有找到可辨識的 M 表頭資料，請確認使用的是電子發票明細 CSV。");

    const orphanDetails = [];
    detailsByNumber.forEach((items, invoiceNumber) => {
      const invoice = invoiceByNumber.get(invoiceNumber);
      if (!invoice) {
        items.forEach(item => orphanDetails.push(item));
        return;
      }
      invoice.items.push(...items);
    });

    invoices.forEach(invoice => {
      invoice.detailTotalCents = invoice.items.reduce((sum, item) => sum + item.amountCents, 0);
      invoice.differenceCents = invoice.detailTotalCents - invoice.totalCents;
      if (!invoice.items.length) invoice.errors.push("找不到此發票的 D 明細");
      if (invoice.differenceCents !== 0 && invoice.items.length) invoice.errors.push("明細加總與表頭總額不一致");
      invoice.ok = invoice.errors.length === 0;
    });

    const totalCents = invoices.reduce((sum, invoice) => sum + invoice.totalCents, 0);
    const matchedCount = invoices.filter(invoice => invoice.ok).length;
    const issueCount = invoices.length - matchedCount;
    return {
      invoices,
      detailCount,
      malformed,
      orphanDetails,
      duplicateHeaders,
      recognizedHeaderRows,
      totalCents,
      matchedCount,
      issueCount,
      sourceLines: lines.filter(line => line.trim()).length
    };
  }

  function formatMoney(cents) {
    return "NT$ " + money.format(cents / 100);
  }

  function makeKpi(label, value, modifier) {
    const card = make("div", "einvoice-kpi" + (modifier ? " " + modifier : ""));
    card.append(make("span", "einvoice-kpi-label", label), make("strong", "einvoice-kpi-value", value));
    return card;
  }

  function statusText(invoice) {
    if (invoice.duplicate) return "疑似重複";
    if (invoice.ok) return "明細核對一致";
    if (!invoice.items.length) return "缺少明細";
    return "金額／資料待檢查";
  }

  function normalizeSearchTerm(value) {
    return String(value || "").normalize("NFKC").toLocaleLowerCase("zh-TW").replace(/\s+/g, "");
  }

  function invoiceMatchesSearch(invoice, query) {
    const term = normalizeSearchTerm(query);
    if (!term) return true;

    const textValues = [
      invoice.invoiceNumber,
      invoice.merchantName,
      invoice.merchantTaxId,
      invoice.date,
      invoice.date.replace(/-/g, ""),
      invoice.invoiceStatus,
      invoice.carrierType,
      statusText(invoice),
      ...invoice.items.map(item => item.itemName)
    ];
    if (textValues.some(value => normalizeSearchTerm(value).includes(term))) return true;

    const numericTerm = term.replace(/[^\d.-]/g, "");
    if (!/^-?\d+(?:\.\d{1,2})?$/.test(numericTerm)) return false;
    let amountCents;
    try {
      amountCents = parseCents(numericTerm);
    } catch (_) {
      return false;
    }
    const amounts = [invoice.totalCents, ...invoice.items.map(item => item.amountCents)];
    return amounts.some(amount => amount === amountCents);
  }

  function getVisibleInvoices() {
    if (!parsedResult) return [];
    let visible = parsedResult.invoices;
    if (currentSearch) visible = visible.filter(invoice => invoiceMatchesSearch(invoice, currentSearch));
    if (currentFilter === "issues") visible = visible.filter(invoice => !invoice.ok);
    if (currentFilter === "duplicates") visible = visible.filter(invoice => invoice.duplicate);
    if (currentMonth !== "all") visible = visible.filter(invoice => invoice.date.slice(0, 7) === currentMonth);
    return visible;
  }

  function renderPagination(total) {
    const host = document.getElementById("einvoice-csv-pagination");
    if (!host) return;
    host.replaceChildren();
    if (!total) {
      host.classList.add("hidden");
      return;
    }
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    currentPage = Math.min(Math.max(1, currentPage), totalPages);
    const start = (currentPage - 1) * pageSize + 1;
    const end = Math.min(total, currentPage * pageSize);
    host.classList.remove("hidden");

    const info = make("span", "einvoice-page-info", "顯示第 " + start + "–" + end + " 張，共 " + total + " 張 · 第 " + currentPage + "／" + totalPages + " 頁");
    const controls = make("div", "einvoice-page-controls");
    const previous = make("button", "secondary small einvoice-page-button", "上一頁");
    previous.type = "button";
    previous.disabled = currentPage <= 1;
    previous.addEventListener("click", () => { currentPage -= 1; renderInvoices(); });
    const next = make("button", "secondary small einvoice-page-button", "下一頁");
    next.type = "button";
    next.disabled = currentPage >= totalPages;
    next.addEventListener("click", () => { currentPage += 1; renderInvoices(); });

    const pageNumbers = make("div", "einvoice-page-numbers");
    let first = Math.max(1, currentPage - 2);
    let last = Math.min(totalPages, first + 4);
    first = Math.max(1, last - 4);
    if (first > 1) {
      const startButton = make("button", "einvoice-page-number", "1");
      startButton.type = "button";
      startButton.addEventListener("click", () => { currentPage = 1; renderInvoices(); });
      pageNumbers.append(startButton);
      if (first > 2) pageNumbers.append(make("span", "einvoice-page-ellipsis", "…"));
    }
    for (let page = first; page <= last; page += 1) {
      const button = make("button", "einvoice-page-number" + (page === currentPage ? " active" : ""), page);
      button.type = "button";
      button.setAttribute("aria-label", "第 " + page + " 頁");
      if (page === currentPage) button.setAttribute("aria-current", "page");
      button.addEventListener("click", () => { currentPage = page; renderInvoices(); });
      pageNumbers.append(button);
    }
    if (last < totalPages) {
      if (last < totalPages - 1) pageNumbers.append(make("span", "einvoice-page-ellipsis", "…"));
      const endButton = make("button", "einvoice-page-number", totalPages);
      endButton.type = "button";
      endButton.addEventListener("click", () => { currentPage = totalPages; renderInvoices(); });
      pageNumbers.append(endButton);
    }
    controls.append(previous, pageNumbers, next);
    host.append(info, controls);
  }

  function renderInvoices() {
    const host = document.getElementById("einvoice-csv-results");
    const summary = document.getElementById("einvoice-csv-summary");
    const list = document.getElementById("einvoice-csv-list");
    const diagnostics = document.getElementById("einvoice-csv-diagnostics");
    if (!host || !parsedResult) return;

    summary.replaceChildren();
    summary.append(
      makeKpi("發票張數", parsedResult.invoices.length + " 張"),
      makeKpi("發票總額", formatMoney(parsedResult.totalCents)),
      makeKpi("商品／折扣明細", parsedResult.detailCount + " 筆"),
      makeKpi("核對一致", parsedResult.matchedCount + " 張", "is-good"),
      makeKpi("待檢查", parsedResult.issueCount + " 張", parsedResult.issueCount ? "is-warn" : "is-good")
    );

    const visible = getVisibleInvoices();
    const totalPages = Math.max(1, Math.ceil(visible.length / pageSize));
    currentPage = Math.min(Math.max(1, currentPage), totalPages);
    const pageInvoices = visible.slice((currentPage - 1) * pageSize, currentPage * pageSize);
    list.replaceChildren();

    if (!pageInvoices.length) {
      const emptyMessage = currentSearch
        ? "找不到符合「" + currentSearch + "」的發票，請試試發票號碼、店家、商品、統編或金額。"
        : "目前篩選條件沒有發票。";
      list.append(make("p", "einvoice-empty", emptyMessage));
    }

    pageInvoices.forEach(invoice => {
      const card = make("article", "einvoice-card");
      const top = make("div", "einvoice-card-top");
      const main = make("div", "einvoice-card-main");
      main.append(
        make("strong", "einvoice-merchant", invoice.merchantName || "未提供店家"),
        make("span", "einvoice-date", invoice.date + " · " + invoice.invoiceNumber)
      );
      const amount = make("strong", "einvoice-amount", formatMoney(invoice.totalCents));
      top.append(main, amount);
      card.append(top);

      const meta = make("div", "einvoice-card-meta");
      meta.append(
        make("span", "einvoice-carrier", invoice.carrierType || "未提供載具"),
        make("span", "einvoice-item-count", invoice.items.length + " 筆明細"),
        make("span", "einvoice-status" + (invoice.ok ? " is-good" : " is-warn"), statusText(invoice))
      );
      card.append(meta);

      const numbers = make("div", "einvoice-reconcile-line");
      numbers.append(
        make("span", "", "明細合計 " + formatMoney(invoice.detailTotalCents)),
        make("strong", invoice.differenceCents === 0 ? "is-good-text" : "is-warn-text", "差額 " + formatMoney(invoice.differenceCents))
      );
      card.append(numbers);

      if (invoice.errors.length) card.append(make("p", "einvoice-card-warning", invoice.errors.join("；")));

      if (invoice.items.length) {
        const details = make("details", "einvoice-items");
        const summaryNode = make("summary", "", "展開商品與折扣明細（" + invoice.items.length + " 筆）");
        const itemList = make("ul", "einvoice-item-list");
        invoice.items.forEach(item => {
          const li = make("li", "einvoice-item");
          li.append(
            make("span", "einvoice-item-name", item.itemName),
            make("strong", item.amountCents < 0 ? "is-negative" : "", formatMoney(item.amountCents))
          );
          itemList.append(li);
        });
        details.append(summaryNode, itemList);
        card.append(details);
      }
      list.append(card);
    });

    diagnostics.replaceChildren();
    const diagnosticLines = [];
    if (parsedResult.duplicateHeaders) diagnosticLines.push("檔案內重複表頭：" + parsedResult.duplicateHeaders + " 筆");
    if (parsedResult.orphanDetails.length) diagnosticLines.push("找不到對應 M 表頭的 D 明細：" + parsedResult.orphanDetails.length + " 筆");
    if (parsedResult.malformed.length) diagnosticLines.push("格式異常資料列：" + parsedResult.malformed.length + " 筆");
    if (diagnosticLines.length) {
      diagnostics.classList.remove("hidden");
      diagnostics.append(make("strong", "", "需要留意的資料"));
      const ul = make("ul", "einvoice-diagnostic-list");
      diagnosticLines.forEach(line => ul.append(make("li", "", line)));
      diagnostics.append(ul);
      const examples = parsedResult.malformed.slice(0, 10);
      if (examples.length) {
        const pre = make("pre", "einvoice-diagnostic-examples");
        pre.textContent = examples.map(item => "第 " + item.line + " 行：" + item.message).join("\n");
        diagnostics.append(pre);
      }
    } else {
      diagnostics.classList.add("hidden");
    }
    renderPagination(visible.length);
    host.classList.remove("hidden");
  }

  function resetPreview(ask) {
    if (ask && parsedResult) {
      const savedNote = previewSaved
        ? "此批發票已保存到家庭歷史區；清除只會移除本機預覽，不會刪除已保存紀錄。"
        : "此預覽尚未保存到資料庫。";
      if (!window.confirm("清除目前選取的檔案與發票預覽？\n\n" + savedNote)) return;
    }
    parsedResult = null;
    currentFilter = "all";
    currentMonth = "all";
    currentSearch = "";
    currentPage = 1;
    pageSize = 10;
    const file = document.getElementById("einvoice-csv-file");
    const message = document.getElementById("einvoice-csv-message");
    const results = document.getElementById("einvoice-csv-results");
    const filename = document.getElementById("einvoice-csv-filename");
    const filter = document.getElementById("einvoice-csv-filter");
    const month = document.getElementById("einvoice-csv-month");
    const search = document.getElementById("einvoice-csv-search");
    const searchClear = document.getElementById("einvoice-csv-search-clear");
    const size = document.getElementById("einvoice-csv-page-size");
    if (file) file.value = "";
    if (message) { message.className = "einvoice-message"; message.textContent = ""; }
    if (filename) filename.textContent = "尚未選擇檔案";
    if (filter) filter.value = "all";
    if (month) month.replaceChildren(new Option("全部月份", "all"));
    if (search) search.value = "";
    if (searchClear) searchClear.disabled = true;
    if (size) size.value = "10";
    if (results) results.classList.add("hidden");
    const clear = document.getElementById("einvoice-csv-clear");
    if (clear) clear.disabled = true;
    const save = document.getElementById("einvoice-csv-save");
    if (save) { save.disabled = true; save.textContent = "儲存發票紀錄"; }
    previewSaved = false;
    previewFamilyId = null;
  }

  function fillMonthOptions(invoices) {
    const select = document.getElementById("einvoice-csv-month");
    if (!select) return;
    const months = [...new Set(invoices.map(invoice => invoice.date.slice(0, 7)))].sort().reverse();
    select.replaceChildren(new Option("全部月份", "all"));
    months.forEach(month => select.add(new Option(month.replace("-", " 年 ") + " 月", month)));
  }


  function invoiceHistoryStatus(invoice) {
    if (invoice.is_voided) return "已作廢";
    return ({
      matched: "明細核對一致",
      mismatch: "金額不一致",
      missing_details: "缺少商品明細",
      duplicate_in_file: "來源檔重複"
    })[invoice.validation_status] || "待檢查";
  }

  function currencyAmount(value) {
    return "NT$ " + money.format(Number(value || 0));
  }

  function historyStatusMessage(message, type) {
    const node = document.getElementById("einvoice-history-message");
    if (!node) return;
    node.className = "einvoice-message" + (type ? " is-" + type : "");
    node.textContent = message || "";
  }

  function historyPagination(total) {
    const host = document.getElementById("einvoice-history-pagination");
    if (!host) return;
    host.replaceChildren();
    if (!total) {
      host.classList.add("hidden");
      return;
    }
    const pages = Math.max(1, Math.ceil(total / historyPageSize));
    historyPage = Math.min(Math.max(1, historyPage), pages);
    host.classList.remove("hidden");
    const start = (historyPage - 1) * historyPageSize + 1;
    const end = Math.min(total, historyPage * historyPageSize);
    host.append(make("span", "einvoice-page-info",
      "顯示第 " + start + "–" + end + " 張，共 " + total + " 張 · 第 " + historyPage + "／" + pages + " 頁"));
    const controls = make("div", "einvoice-page-controls");
    const previous = make("button", "secondary small einvoice-page-button", "上一頁");
    previous.type = "button";
    previous.disabled = historyPage <= 1;
    previous.addEventListener("click", () => { historyPage -= 1; loadHistory(); });
    const next = make("button", "secondary small einvoice-page-button", "下一頁");
    next.type = "button";
    next.disabled = historyPage >= pages;
    next.addEventListener("click", () => { historyPage += 1; loadHistory(); });
    const label = make("span", "einvoice-page-info", "第 " + historyPage + "／" + pages + " 頁");
    controls.append(previous, label, next);
    host.append(controls);
  }

  async function loadInvoiceHistoryDetail(invoiceId, detailHost, familyId, includeVoided) {
    const bridge = window.FamilyFinanceInvoiceBridge;
    try {
      const params = new URLSearchParams({ family_id: String(familyId) });
      if (includeVoided) params.set("include_voided", "true");
      const result = await bridge.request(
        "/electronic-invoices/" + invoiceId + "?" + params.toString()
      );
      detailHost.replaceChildren();
      const items = result.items || [];
      if (!items.length) {
        detailHost.append(make("p", "tiny muted", "這張發票沒有商品明細。"));
      } else {
        const list = make("ul", "einvoice-item-list");
        items.forEach(item => {
          const row = make("li", "einvoice-item");
          row.append(
            make("span", "einvoice-item-name", item.item_name),
            make("strong", Number(item.amount) < 0 ? "is-negative" : "", currencyAmount(item.amount))
          );
          list.append(row);
        });
        detailHost.append(list);
      }
      if (result.detail_total_amount !== null && result.detail_total_amount !== undefined) {
        detailHost.append(make("div", "einvoice-reconcile-line",
          "商品／折扣合計 " + currencyAmount(result.detail_total_amount)));
        detailHost.append(make("div",
          "einvoice-reconcile-line " + (Number(result.difference_amount) === 0 ? "is-good-text" : "is-warn-text"),
          "與發票總額差異 " + currencyAmount(result.difference_amount)));
      }
      detailHost.dataset.loaded = "1";
    } catch (error) {
      detailHost.replaceChildren(make("p", "einvoice-card-warning", "明細載入失敗：" + error.message));
    }
  }

  function renderHistoryInvoices(invoices, familyId) {
    const list = document.getElementById("einvoice-history-list");
    if (!list) return;
    list.replaceChildren();
    if (!invoices.length) {
      list.append(make("p", "einvoice-empty", "沒有符合條件的已保存發票。可以清除篩選，或先匯入電子發票 CSV。"));
      return;
    }

    invoices.forEach(invoice => {
      const card = make("article", "einvoice-card einvoice-history-card");
      const top = make("div", "einvoice-card-top");
      const main = make("div", "einvoice-card-main");
      main.append(
        make("strong", "einvoice-merchant", invoice.merchant_name || "未提供店家"),
        make("span", "einvoice-date", invoice.invoice_date + " · " + invoice.invoice_number)
      );
      const amount = make("strong", "einvoice-amount", currencyAmount(invoice.total_amount));
      top.append(main, amount);
      card.append(top);

      const meta = make("div", "einvoice-card-meta");
      meta.append(
        make("span", "einvoice-status" + (invoice.validation_status === "matched" && !invoice.is_voided ? " is-good" : " is-warn"),
          invoiceHistoryStatus(invoice)),
        make("span", "einvoice-item-count", invoice.item_count + " 筆明細"),
        make("span", "einvoice-carrier", "匯入批次 #" + invoice.import_batch_id)
      );
      if (invoice.merchant_tax_id) meta.append(make("span", "einvoice-carrier", "統編 " + invoice.merchant_tax_id));
      if (invoice.linked_transaction_id) meta.append(make("span", "einvoice-status is-good", "已連結帳務 #" + invoice.linked_transaction_id));
      card.append(meta);

      const details = make("details", "einvoice-items");
      const summaryNode = make("summary", "", "查看商品與折扣明細（" + invoice.item_count + " 筆）");
      const detailHost = make("div", "einvoice-history-detail");
      details.append(summaryNode, detailHost);
      details.addEventListener("toggle", () => {
        if (details.open && detailHost.dataset.loaded !== "1" && !detailHost.dataset.loading) {
          detailHost.dataset.loading = "1";
          detailHost.append(make("p", "tiny muted", "正在載入明細…"));
          loadInvoiceHistoryDetail(invoice.id, detailHost, familyId, invoice.is_voided).finally(() => {
            delete detailHost.dataset.loading;
          });
        }
      });
      card.append(details);

      const actions = make("div", "einvoice-history-actions");
      if (!invoice.is_voided && window.FamilyFinanceInvoiceBridge?.hasPermission("invoices.void")) {
        const voidButton = make("button", "secondary small", "作廢紀錄");
        voidButton.type = "button";
        voidButton.addEventListener("click", async () => {
          const reason = window.prompt("請輸入作廢原因（可留空）：", "");
          if (reason === null) return;
          voidButton.disabled = true;
          try {
            await window.FamilyFinanceInvoiceBridge.request(
              "/electronic-invoices/" + invoice.id + "?family_id=" + encodeURIComponent(familyId),
              { method: "DELETE", body: JSON.stringify({ reason }) }
            );
            historyStatusMessage("發票紀錄已作廢，歷史資料仍會保留。", "success");
            await loadHistory();
          } catch (error) {
            historyStatusMessage("作廢失敗：" + error.message, "error");
            voidButton.disabled = false;
          }
        });
        actions.append(voidButton);
      }
      card.append(actions);
      list.append(card);
    });
  }

  async function loadHistory() {
    const sequence = ++historyRequestSequence;
    const bridge = window.FamilyFinanceInvoiceBridge;
    const familyId = bridge?.getFamilyId();
    const list = document.getElementById("einvoice-history-list");
    const pagination = document.getElementById("einvoice-history-pagination");
    if (!bridge || !familyId) {
      historyStatusMessage("請先登入並選擇家庭，再查詢已保存的發票。", "error");
      if (list) { list.replaceChildren(); list.removeAttribute("aria-busy"); }
      if (pagination) { pagination.replaceChildren(); pagination.classList.add("hidden"); }
      return;
    }
    if (!bridge.hasPermission("invoices.view")) {
      historyStatusMessage("目前帳號沒有查看家庭發票的權限。", "error");
      if (list) { list.replaceChildren(); list.removeAttribute("aria-busy"); }
      if (pagination) { pagination.replaceChildren(); pagination.classList.add("hidden"); }
      return;
    }
    const query = document.getElementById("einvoice-history-search")?.value.trim() || "";
    const startDate = document.getElementById("einvoice-history-start")?.value || "";
    const endDate = document.getElementById("einvoice-history-end")?.value || "";
    const validation = document.getElementById("einvoice-history-status")?.value || "";
    const includeVoided = Boolean(document.getElementById("einvoice-history-voided")?.checked);
    const params = new URLSearchParams({
      family_id: String(familyId),
      skip: String((historyPage - 1) * historyPageSize),
      limit: String(historyPageSize)
    });
    if (query) params.set("q", query);
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    if (validation) params.set("validation_status", validation);
    if (includeVoided) params.set("include_voided", "true");

    historyStatusMessage("正在搜尋已保存的家庭發票…");
    if (list) list.setAttribute("aria-busy", "true");
    try {
      const result = await bridge.request("/electronic-invoices?" + params.toString());
      if (sequence !== historyRequestSequence) return;
      renderHistoryInvoices(result.invoices || [], familyId);
      historyPagination(result.total || 0);
      historyStatusMessage("共找到 " + (result.total || 0) + " 張已保存發票。這裡查詢的是正式保存紀錄，不是暫存預覽。", "success");
    } catch (error) {
      if (sequence !== historyRequestSequence) return;
      historyStatusMessage("歷史發票查詢失敗：" + error.message, "error");
      if (list) list.replaceChildren(make("p", "einvoice-empty", "暫時無法載入發票紀錄，請稍後重試。"));
      const pagination = document.getElementById("einvoice-history-pagination");
      if (pagination) pagination.classList.add("hidden");
    } finally {
      if (sequence === historyRequestSequence && list) list.removeAttribute("aria-busy");
    }
  }

  async function savePreview() {
    if (!parsedResult || previewSaved) return;
    const bridge = window.FamilyFinanceInvoiceBridge;
    const familyId = bridge?.getFamilyId();
    if (!familyId) {
      const message = document.getElementById("einvoice-csv-message");
      message.className = "einvoice-message is-error";
      message.textContent = "請先登入並選擇家庭，才能保存發票紀錄。";
      return;
    }
    if (!bridge.hasPermission("invoices.import")) {
      const message = document.getElementById("einvoice-csv-message");
      message.className = "einvoice-message is-error";
      message.textContent = "目前帳號沒有保存電子發票的權限。";
      return;
    }
    if (!previewFamilyId || String(familyId) !== String(previewFamilyId)) {
      const message = document.getElementById("einvoice-csv-message");
      message.className = "einvoice-message is-error";
      message.textContent = "家庭已切換，為避免發票存入錯誤家庭，請清除目前預覽並在正確家庭重新選取 CSV。";
      const saveButton = document.getElementById("einvoice-csv-save");
      if (saveButton) saveButton.disabled = true;
      return;
    }
    const file = document.getElementById("einvoice-csv-file");
    const filename = document.getElementById("einvoice-csv-filename")?.textContent || "電子發票匯入.csv";
    const invoiceCount = parsedResult.invoices.length;
    const detailCount = parsedResult.detailCount;
    if (!window.confirm(
      "即將保存 " + invoiceCount + " 張發票及 " + detailCount + " 筆商品／折扣明細至目前家庭。\n\n" +
      "這只會保存發票資料，不會自動新增收入或支出，也不會保存載具號碼或原始 CSV。確定繼續？"
    )) return;

    const button = document.getElementById("einvoice-csv-save");
    const message = document.getElementById("einvoice-csv-message");
    button.disabled = true;
    button.textContent = "正在保存…";
    message.className = "einvoice-message";
    message.textContent = "正在將發票紀錄安全保存至目前家庭…";

    const cents = value => {
      const amount = Math.abs(Number(value || 0));
      return (Number(value) < 0 ? "-" : "") +
        Math.floor(amount / 100) + "." + String(amount % 100).padStart(2, "0");
    };
    const payload = {
      source_filename: filename,
      invoices: parsedResult.invoices.map(invoice => ({
        invoice_date: invoice.date,
        invoice_number: invoice.invoiceNumber,
        merchant_tax_id: invoice.merchantTaxId || null,
        merchant_name: invoice.merchantName || "未提供店家",
        total_amount: cents(invoice.totalCents),
        invoice_status: invoice.invoiceStatus || null,
        carrier_type: invoice.carrierType || null,
        duplicate_in_source: Boolean(invoice.duplicate),
        items: invoice.items.map(item => ({
          item_name: item.itemName,
          amount: cents(item.amountCents)
        }))
      }))
    };

    try {
      const result = await bridge.request(
        "/electronic-invoices/imports?family_id=" + encodeURIComponent(familyId),
        { method: "POST", body: JSON.stringify(payload) }
      );
      previewSaved = true;
      button.textContent = "本批已保存";
      message.className = "einvoice-message is-success";
      message.textContent =
        "已保存 " + result.saved_count + " 張發票；" + result.duplicate_count +
        " 張因家庭既有紀錄或本批重複而略過。發票沒有自動轉成正式支出。";
      await loadHistory();
    } catch (error) {
      button.disabled = false;
      button.textContent = "儲存發票紀錄";
      message.className = "einvoice-message is-error";
      message.textContent = "保存失敗：" + error.message + "。原始預覽仍保留，可以修正後再試。";
    }
  }

  function resetHistoryFilters() {
    historyPage = 1;
    const ids = [
      ["einvoice-history-search", ""],
      ["einvoice-history-start", ""],
      ["einvoice-history-end", ""],
      ["einvoice-history-status", ""]
    ];
    ids.forEach(([id, value]) => {
      const node = document.getElementById(id);
      if (node) node.value = value;
    });
    const includeVoided = document.getElementById("einvoice-history-voided");
    if (includeVoided) includeVoided.checked = false;
    loadHistory();
  }

  async function handleFile(file) {
    const message = document.getElementById("einvoice-csv-message");
    const results = document.getElementById("einvoice-csv-results");
    const clear = document.getElementById("einvoice-csv-clear");
    if (!file) return;
    parsedResult = null;
    previewSaved = false;
    previewFamilyId = window.FamilyFinanceInvoiceBridge?.getFamilyId();
    previewFamilyId = previewFamilyId ? String(previewFamilyId) : null;
    const saveButton = document.getElementById("einvoice-csv-save");
    if (saveButton) { saveButton.disabled = true; saveButton.textContent = "儲存發票紀錄"; }
    results.classList.add("hidden");
    clear.disabled = false;
    message.className = "einvoice-message";
    message.textContent = "";
    document.getElementById("einvoice-csv-filename").textContent = file.name;
    if (file.size > MAX_BYTES) {
      message.classList.add("is-error");
      message.textContent = "檔案不可超過 10 MB，請分月份匯入。";
      return;
    }
    try {
      const text = decodeBytes(await file.arrayBuffer());
      parsedResult = parseText(text);
      currentFilter = "all";
      currentMonth = "all";
      currentSearch = "";
      currentPage = 1;
      pageSize = 10;
      previewSaved = false;
      const activeFamilyId = window.FamilyFinanceInvoiceBridge?.getFamilyId();
      const familyMatches = Boolean(previewFamilyId && activeFamilyId && String(activeFamilyId) === previewFamilyId);
      document.getElementById("einvoice-csv-save").disabled = !familyMatches;
      document.getElementById("einvoice-csv-save").textContent = "儲存發票紀錄";
      document.getElementById("einvoice-csv-filter").value = "all";
      document.getElementById("einvoice-csv-search").value = "";
      document.getElementById("einvoice-csv-search-clear").disabled = true;
      document.getElementById("einvoice-csv-page-size").value = "10";
      fillMonthOptions(parsedResult.invoices);
      document.getElementById("einvoice-csv-filename").textContent = file.name;
      if (familyMatches) {
        message.classList.add("is-success");
        message.textContent = "已在此裝置完成解析。原始 CSV 不會上傳伺服器，也尚未寫入正式帳務。";
      } else {
        message.classList.add("is-error");
        message.textContent = "已完成本機解析，但目前沒有可用的家庭或解析期間已切換家庭。請先確認家庭，再重新選取 CSV 才能保存。";
      }
      renderInvoices();
    } catch (error) {
      parsedResult = null;
      previewFamilyId = null;
      const saveButton = document.getElementById("einvoice-csv-save");
      if (saveButton) saveButton.disabled = true;
      message.classList.add("is-error");
      message.textContent = error.message || "讀取 CSV 失敗，請確認檔案格式。";
    }
  }

  function mount() {
    const workspace = document.getElementById("einvoice-csv-workspace-content");
    if (!workspace || document.getElementById("einvoice-csv-import")) return;
    const section = make("section", "subpanel einvoice-csv-import");
    section.id = "einvoice-csv-import";
    section.innerHTML =
      '<div class="einvoice-history-panel">' +
        '<div class="einvoice-list-heading"><div><h3>家庭歷史發票</h3><p class="tiny muted">搜尋所有已保存批次，可查發票號碼、店家、商品、統編、日期與金額。</p></div>' +
          '<button id="einvoice-history-refresh" class="secondary small" type="button">重新整理</button></div>' +
        '<div class="einvoice-history-filters">' +
          '<label class="einvoice-history-search">快速搜尋<input id="einvoice-history-search" type="search" placeholder="例如：AB12345678、全聯、牛奶、1280、統編" autocomplete="off"></label>' +
          '<label class="einvoice-history-filter">日期（起）<input id="einvoice-history-start" type="date"></label>' +
          '<label class="einvoice-history-filter">日期（迄）<input id="einvoice-history-end" type="date"></label>' +
          '<label class="einvoice-history-filter">核對狀態<select id="einvoice-history-status"><option value="">全部狀態</option><option value="matched">明細核對一致</option><option value="mismatch">金額不一致</option><option value="missing_details">缺少商品明細</option><option value="duplicate_in_file">來源檔重複</option></select></label>' +
          '<label class="einvoice-history-voided"><input id="einvoice-history-voided" type="checkbox"> 顯示已作廢</label>' +
          '<button id="einvoice-history-clear" class="secondary small" type="button">清除條件</button>' +
        '</div>' +
        '<p id="einvoice-history-message" class="einvoice-message" role="status" aria-live="polite">登入並選擇家庭後，即可搜尋已保存發票。</p>' +
        '<div id="einvoice-history-list" class="einvoice-card-list" aria-live="polite"></div>' +
        '<nav id="einvoice-history-pagination" class="einvoice-pagination hidden" aria-label="歷史發票分頁"></nav>' +
        '<p class="einvoice-local-footnote">歷史發票保存的是發票表頭及商品／折扣明細，不保存載具號碼或原始 CSV。作廢只隱藏在一般清單中，歷史仍保留。</p>' +
      '</div>' +
      '<div class="einvoice-upload-box">' +
        '<div class="einvoice-upload-heading"><label class="field">選擇電子發票 CSV 檔案' +
          '<input id="einvoice-csv-file" type="file" accept=".csv,.txt,text/csv,text/plain"></label>' +
          '<div class="einvoice-upload-actions"><button id="einvoice-csv-save" class="primary einvoice-save-button" type="button" disabled>儲存發票紀錄</button>' +
          '<button id="einvoice-csv-clear" class="secondary einvoice-clear-button" type="button" disabled>清除預覽</button></div></div>' +
        '<p class="tiny muted">支援 UTF-8、Big5／CP950；以 | 分隔欄位，單檔上限 10 MB。建議一次匯入一個月份。</p>' +
        '<p id="einvoice-csv-filename" class="einvoice-filename">尚未選擇檔案</p></div>' +
      '<p id="einvoice-csv-message" class="einvoice-message" role="status" aria-live="polite"></p>' +
      '<div id="einvoice-csv-results" class="hidden">' +
        '<div id="einvoice-csv-summary" class="einvoice-kpi-grid"></div>' +
        '<div class="einvoice-list-heading"><div><h3>發票檢查結果</h3><p class="tiny muted">表頭總額與商品／折扣明細逐張核對；負數折扣會保留。</p></div>' +
          '<div class="einvoice-list-toolbar">' +
            '<div class="einvoice-search-row">' +
              '<label class="einvoice-search-label">快速搜尋<input id="einvoice-csv-search" type="search" placeholder="發票號碼、店家、商品、統編或金額" aria-label="搜尋目前匯入的發票" autocomplete="off"></label>' +
              '<button id="einvoice-csv-search-clear" class="secondary small einvoice-search-clear" type="button" disabled>清除搜尋</button>' +
            '</div>' +
            '<div class="einvoice-filter-controls">' +
              '<label class="einvoice-filter-label">月份<select id="einvoice-csv-month"><option value="all">全部月份</option></select></label>' +
              '<label class="einvoice-filter-label">狀態<select id="einvoice-csv-filter"><option value="all">全部發票</option><option value="issues">待檢查</option><option value="duplicates">疑似重複</option></select></label>' +
              '<label class="einvoice-filter-label">每頁<select id="einvoice-csv-page-size"><option value="10">10 張</option><option value="20">20 張</option><option value="50">50 張</option></select></label>' +
            '</div></div></div>' +
        '<div id="einvoice-csv-diagnostics" class="einvoice-diagnostics hidden"></div>' +
        '<div id="einvoice-csv-list" class="einvoice-card-list"></div>' +
        '<nav id="einvoice-csv-pagination" class="einvoice-pagination hidden" aria-label="電子發票分頁"></nav>' +
        '<p class="einvoice-local-footnote">解析階段只在本機執行；按下「儲存發票紀錄」後，才會將發票表頭及商品／折扣明細寫入家庭資料庫。原始 CSV 與載具號碼不會保存，也不會自動建立正式支出。</p>' +
      '</div>';
    workspace.append(section);

    const fileInput = document.getElementById("einvoice-csv-file");
    fileInput.addEventListener("change", event => {
      const file = event.target.files && event.target.files[0];
      event.target.value = "";
      handleFile(file);
    });
    document.getElementById("einvoice-csv-clear").addEventListener("click", () => resetPreview(true));
    document.getElementById("einvoice-csv-save").addEventListener("click", savePreview);
    const historySearch = document.getElementById("einvoice-history-search");
    historySearch.addEventListener("input", () => {
      historyPage = 1;
      if (historySearchTimer) window.clearTimeout(historySearchTimer);
      historySearchTimer = window.setTimeout(loadHistory, 300);
    });
    ["einvoice-history-start", "einvoice-history-end", "einvoice-history-status", "einvoice-history-voided"].forEach(id => {
      document.getElementById(id).addEventListener("change", () => { historyPage = 1; loadHistory(); });
    });
    document.getElementById("einvoice-history-refresh").addEventListener("click", () => loadHistory());
    document.getElementById("einvoice-history-clear").addEventListener("click", resetHistoryFilters);
    window.addEventListener("family-finance-family-changed", () => {
      historyRequestSequence += 1;
      historyPage = 1;
      if (historySearchTimer) window.clearTimeout(historySearchTimer);
      historySearchTimer = null;

      const historyList = document.getElementById("einvoice-history-list");
      const historyPagination = document.getElementById("einvoice-history-pagination");
      if (historyList) { historyList.replaceChildren(); historyList.removeAttribute("aria-busy"); }
      if (historyPagination) { historyPagination.replaceChildren(); historyPagination.classList.add("hidden"); }

      const activeFamilyId = window.FamilyFinanceInvoiceBridge?.getFamilyId();
      const familyMatches = Boolean(previewFamilyId && activeFamilyId && String(activeFamilyId) === String(previewFamilyId));
      const saveButton = document.getElementById("einvoice-csv-save");
      if (parsedResult && !previewSaved && saveButton) saveButton.disabled = !familyMatches;
      if (parsedResult && !previewSaved && !familyMatches) {
        const message = document.getElementById("einvoice-csv-message");
        if (message) {
          message.className = "einvoice-message is-error";
          message.textContent = "家庭已切換；目前 CSV 預覽仍屬於原家庭。請清除預覽並在目前家庭重新選取 CSV，避免存錯家庭。";
        }
      }
      if (!document.getElementById("einvoice-csv-view")?.classList.contains("hidden")) loadHistory();
    });
    const searchInput = document.getElementById("einvoice-csv-search");
    const searchClear = document.getElementById("einvoice-csv-search-clear");
    searchInput.addEventListener("input", event => {
      currentSearch = event.target.value.trim();
      searchClear.disabled = !currentSearch;
      currentPage = 1;
      renderInvoices();
    });
    searchClear.addEventListener("click", () => {
      searchInput.value = "";
      currentSearch = "";
      searchClear.disabled = true;
      currentPage = 1;
      renderInvoices();
      searchInput.focus();
    });
    document.getElementById("einvoice-csv-filter").addEventListener("change", event => {
      currentFilter = event.target.value;
      currentPage = 1;
      renderInvoices();
    });
    document.getElementById("einvoice-csv-month").addEventListener("change", event => {
      currentMonth = event.target.value;
      currentPage = 1;
      renderInvoices();
    });
    document.getElementById("einvoice-csv-page-size").addEventListener("change", event => {
      pageSize = Number(event.target.value) || 10;
      currentPage = 1;
      renderInvoices();
    });
    document.getElementById("open-einvoice-csv")?.addEventListener("click", () => {
      document.getElementById("einvoice-csv-view")?.scrollIntoView({ behavior: "smooth", block: "start" });
      loadHistory();
    });
    document.getElementById("close-einvoice-csv")?.addEventListener("click", () => {
      document.getElementById("einvoice-csv-view")?.classList.add("hidden");
      document.querySelector('[data-nav-key="overview"]')?.click();
    });
  }

  window.EInvoiceCsvPreview = { parseText };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
})();