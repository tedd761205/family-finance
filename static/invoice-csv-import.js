(() => {
  "use strict";

  const MAX_BYTES = 10 * 1024 * 1024;
  const MAX_LINES = 20000;
  const money = new Intl.NumberFormat("zh-TW", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  let parsedResult = null;
  let currentFilter = "all";
  let currentMonth = "all";
  let currentSearch = "";
  let currentSourceFilename = "";
  let currentSourceSha256 = null;
  let currentPage = 1;
  let historyPage = 1;
  let currentInvoiceMode = "preview";
  let isSavingPreview = false;
  let persistenceAvailable = false;
  let pageSize = 10;
  let cachedInvoiceCategories = null;
  let cachedInvoiceCategoriesFamilyId = null;

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
    if (ask && parsedResult && !window.confirm("清除目前選取的檔案與發票預覽？此預覽尚未存入資料庫。")) return;
    parsedResult = null;
    currentSourceFilename = "";
    currentSourceSha256 = null;
    const saveButton = document.getElementById("einvoice-csv-save");
    if (saveButton) saveButton.disabled = true;
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
  }

  function fillMonthOptions(invoices) {
    const select = document.getElementById("einvoice-csv-month");
    if (!select) return;
    const months = [...new Set(invoices.map(invoice => invoice.date.slice(0, 7)))].sort().reverse();
    select.replaceChildren(new Option("全部月份", "all"));
    months.forEach(month => select.add(new Option(month.replace("-", " 年 ") + " 月", month)));
  }

  async function calculateSha256(buffer) {
    if (!window.crypto?.subtle) return null;
    const digest = await window.crypto.subtle.digest("SHA-256", buffer);
    return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
  }

  async function handleFile(file) {
    const message = document.getElementById("einvoice-csv-message");
    const results = document.getElementById("einvoice-csv-results");
    const clear = document.getElementById("einvoice-csv-clear");
    if (!file) return;
    parsedResult = null;
    const saveButton = document.getElementById("einvoice-csv-save");
    if (saveButton) saveButton.disabled = true;
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
      const buffer = await file.arrayBuffer();
      currentSourceFilename = file.name;
      currentSourceSha256 = await calculateSha256(buffer);
      const text = decodeBytes(buffer);
      parsedResult = parseText(text);
      currentFilter = "all";
      currentMonth = "all";
      currentSearch = "";
      currentPage = 1;
      pageSize = 10;
      document.getElementById("einvoice-csv-filter").value = "all";
      document.getElementById("einvoice-csv-search").value = "";
      document.getElementById("einvoice-csv-search-clear").disabled = true;
      document.getElementById("einvoice-csv-page-size").value = "10";
      fillMonthOptions(parsedResult.invoices);
      document.getElementById("einvoice-csv-filename").textContent = file.name;
      message.classList.add("is-success");
      message.textContent = "已在此裝置完成解析。原始 CSV 不會上傳伺服器；確認保存後只會傳送解析出的發票與商品明細，不會自動建立支出。";
      showInvoiceMode(currentInvoiceMode);
      const saveButton = document.getElementById("einvoice-csv-save");
      if (saveButton) saveButton.disabled = !persistenceAvailable || !getBridge()?.hasPermission?.("imports.create") || !getBridge()?.hasPermission?.("imports.confirm");
      renderInvoices();
    } catch (error) {
      parsedResult = null;
      currentSourceFilename = "";
      currentSourceSha256 = null;
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
      '<div class="einvoice-mode-tabs" role="tablist" aria-label="發票工作區">' +
        '<button id="einvoice-mode-preview" class="einvoice-mode-tab active" type="button" role="tab" aria-selected="true">匯入與檢查</button>' +
        '<button id="einvoice-mode-history" class="einvoice-mode-tab" type="button" role="tab" aria-selected="false">家庭歷史發票</button>' +
      '</div>' +
      '<div class="einvoice-preview-mode">' +
      '<div class="einvoice-upload-box">' +
        '<div class="einvoice-upload-heading"><label class="field">選擇電子發票 CSV 檔案' +
          '<input id="einvoice-csv-file" type="file" accept=".csv,.txt,text/csv,text/plain"></label>' +
          '<button id="einvoice-csv-clear" class="secondary einvoice-clear-button" type="button" disabled>清除預覽</button></div>' +
        '<p class="tiny muted">支援 UTF-8、Big5／CP950；以 | 分隔欄位，單檔上限 10 MB。建議一次匯入一個月份。</p>' +
        '<p id="einvoice-csv-filename" class="einvoice-filename">尚未選擇檔案</p></div>' +
      '<p id="einvoice-csv-message" class="einvoice-message" role="status" aria-live="polite"></p>' +
      '<div id="einvoice-csv-results" class="hidden">' +
        '<div class="einvoice-save-row"><p>確認後將發票與明細保存到家庭發票庫；原始 CSV 與載具號碼不會上傳，也不會建立正式交易。</p><button id="einvoice-csv-save" class="primary small" type="button" disabled>保存到家庭發票庫</button></div>' +
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
        '<p class="einvoice-local-footnote">預覽僅暫存在此裝置。只有按下「保存到家庭發票庫」並確認後，解析出的發票資料才會保存；不會自動新增家庭支出。</p>' +
      '</div></div>' +
      '<div id="einvoice-history-mode" class="hidden">' +
        '<div class="einvoice-history-intro"><h3>家庭歷史發票</h3><p>搜尋已保存的家庭發票，不必重新匯入 CSV。依帳號權限顯示家庭或本人建立的紀錄。</p></div>' +
        '<form id="einvoice-history-filter" class="einvoice-history-filters">' +
          '<label class="einvoice-history-search">關鍵字<input id="einvoice-history-query" type="search" maxlength="120" placeholder="發票號碼、店家、統編、商品或金額"></label>' +
          '<label>月份<input id="einvoice-history-month" type="month"></label>' +
          '<label>核對狀態<select id="einvoice-history-status"><option value="all">全部狀態</option><option value="matched">核對一致</option><option value="mismatch">金額不一致</option><option value="missing_details">缺少明細</option><option value="duplicate">疑似重複</option></select></label>' +
          '<label>最低金額<input id="einvoice-history-min" type="number" min="0" step="0.01" inputmode="decimal" placeholder="不限"></label>' +
          '<label>最高金額<input id="einvoice-history-max" type="number" min="0" step="0.01" inputmode="decimal" placeholder="不限"></label>' +
          '<div class="einvoice-history-actions"><button class="primary small" type="submit">搜尋發票</button><button id="einvoice-history-clear" class="secondary small" type="button">清除條件</button></div>' +
        '</form>' +
        '<p id="einvoice-history-message" class="einvoice-message" role="status" aria-live="polite"></p>' +
        '<div id="einvoice-history-summary" class="einvoice-history-summary"></div>' +
        '<div id="einvoice-history-list" class="einvoice-history-list"></div>' +
        '<nav id="einvoice-history-pagination" class="einvoice-pagination hidden" aria-label="歷史發票分頁"></nav>' +
      '</div>';
    workspace.append(section);
    showInvoiceMode("preview");
    window.addEventListener("family-finance:permissions-updated", async () => {
      await refreshPersistenceAvailability();
      if (currentInvoiceMode === "history" && persistenceAvailable) loadHistoryInvoices();
    });
    refreshPersistenceAvailability();

    const fileInput = document.getElementById("einvoice-csv-file");
    fileInput.addEventListener("change", event => {
      const file = event.target.files && event.target.files[0];
      event.target.value = "";
      handleFile(file);
    });
    document.getElementById("einvoice-csv-clear").addEventListener("click", () => resetPreview(true));
    document.getElementById("einvoice-csv-save").addEventListener("click", saveCurrentPreview);
    document.getElementById("einvoice-mode-preview").addEventListener("click", () => switchInvoiceMode("preview"));
    document.getElementById("einvoice-mode-history").addEventListener("click", () => switchInvoiceMode("history"));
    document.getElementById("einvoice-history-filter").addEventListener("submit", event => {
      event.preventDefault();
      historyPage = 1;
      loadHistoryInvoices();
    });
    document.getElementById("einvoice-history-clear").addEventListener("click", () => {
      document.getElementById("einvoice-history-query").value = "";
      document.getElementById("einvoice-history-month").value = "";
      document.getElementById("einvoice-history-status").value = "all";
      document.getElementById("einvoice-history-min").value = "";
      document.getElementById("einvoice-history-max").value = "";
      historyPage = 1;
      loadHistoryInvoices();
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
    });
    document.getElementById("close-einvoice-csv")?.addEventListener("click", () => {
      document.getElementById("einvoice-csv-view")?.classList.add("hidden");
      document.querySelector('[data-nav-key="overview"]')?.click();
    });
  }


  function getBridge() {
    return window.FamilyFinanceBridge;
  }

  function showInvoiceMode(mode) {
    currentInvoiceMode = mode;
    const preview = document.querySelector(".einvoice-preview-mode");
    const history = document.getElementById("einvoice-history-mode");
    const previewTab = document.getElementById("einvoice-mode-preview");
    const historyTab = document.getElementById("einvoice-mode-history");
    if (!preview || !history || !previewTab || !historyTab) return;
    const showHistory = mode === "history";
    preview.classList.toggle("hidden", showHistory);
    history.classList.toggle("hidden", !showHistory);
    previewTab.classList.toggle("active", !showHistory);
    historyTab.classList.toggle("active", showHistory);
    previewTab.setAttribute("aria-selected", String(!showHistory));
    historyTab.setAttribute("aria-selected", String(showHistory));
    const saveButton = document.getElementById("einvoice-csv-save");
    const bridge = getBridge();
    const canSave = Boolean(persistenceAvailable && bridge?.hasPermission?.("imports.create") && bridge?.hasPermission?.("imports.confirm"));
    if (historyTab) {
      historyTab.disabled = !persistenceAvailable || !bridge?.hasPermission?.("imports.view");
      historyTab.textContent = persistenceAvailable ? "家庭歷史發票" : "家庭歷史發票（待啟用）";
      historyTab.title = persistenceAvailable ? "搜尋已保存的家庭發票" : "正式資料庫遷移完成並核准後開放";
    }
    if (saveButton) {
      saveButton.classList.toggle("hidden", !bridge?.hasPermission?.("imports.create") || !bridge?.hasPermission?.("imports.confirm"));
      saveButton.textContent = persistenceAvailable ? "保存到家庭發票庫" : "家庭發票庫待啟用";
      saveButton.disabled = !canSave || !parsedResult || isSavingPreview;
    }
  }

  function switchInvoiceMode(mode) {
    if (mode === "history" && !persistenceAvailable) {
      setHistoryMessage("家庭歷史發票資料庫尚未啟用；正式資料庫遷移完成並核准後即可使用。", true);
      return;
    }
    showInvoiceMode(mode);
    if (mode === "history") {
      historyPage = 1;
      loadHistoryInvoices();
    }
  }

  async function refreshPersistenceAvailability() {
    const bridge = getBridge();
    if (!bridge?.api) return;
    try {
      const result = await bridge.api("/einvoices/availability");
      persistenceAvailable = result.enabled === true;
    } catch (_) {
      persistenceAvailable = false;
    }
    if (!persistenceAvailable && currentInvoiceMode === "history") {
      currentInvoiceMode = "preview";
    }
    showInvoiceMode(currentInvoiceMode);
  }

  function currentFamilyId() {
    const value = getBridge()?.getSelectedFamilyId?.();
    return Number.isInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
  }

  async function saveCurrentPreview() {
    const bridge = getBridge();
    const familyId = currentFamilyId();
    const button = document.getElementById("einvoice-csv-save");
    const message = document.getElementById("einvoice-csv-message");
    if (!persistenceAvailable) {
      message.className = "einvoice-message is-error";
      message.textContent = "家庭發票資料庫尚未啟用；正式資料庫遷移完成並核准後才能保存。";
      return;
    }
    if (!parsedResult || !familyId || !bridge?.api) {
      message.className = "einvoice-message is-error";
      message.textContent = "請先登入並選擇家庭，再保存發票資料。";
      return;
    }
    if (!bridge.hasPermission?.("imports.create") || !bridge.hasPermission?.("imports.confirm")) {
      message.className = "einvoice-message is-error";
      message.textContent = "目前帳號沒有保存發票的權限。";
      return;
    }
    const count = parsedResult.invoices.length;
    const amount = formatMoney(parsedResult.totalCents);
    const accepted = window.confirm(
      "確認將這次解析的 " + count + " 張發票（總額 " + amount + "）保存到目前家庭的歷史發票庫？\n\n同一家庭已存在的發票號碼會略過，不會建立任何收入或支出交易。原始 CSV 與載具號碼不會上傳。"
    );
    if (!accepted) return;
    isSavingPreview = true;
    button.disabled = true;
    message.className = "einvoice-message";
    message.textContent = "正在保存家庭發票資料…";
    const invoices = parsedResult.invoices.map(invoice => ({
      invoice_number: invoice.invoiceNumber,
      date: invoice.date,
      merchant_tax_id: invoice.merchantTaxId,
      merchant_name: invoice.merchantName,
      total_amount: (invoice.totalCents / 100).toFixed(2),
      invoice_status: invoice.invoiceStatus,
      carrier_type: invoice.carrierType,
      duplicate: invoice.duplicate === true,
      items: invoice.items.map(item => ({
        item_name: item.itemName,
        amount: (item.amountCents / 100).toFixed(2),
        source_line: item.line
      }))
    }));
    try {
      const result = await bridge.api("/einvoices/imports?family_id=" + familyId, {
        method: "POST",
        body: JSON.stringify({
          source_filename: currentSourceFilename,
          source_sha256: currentSourceSha256,
          invoices
        })
      });
      message.className = "einvoice-message is-success";
      message.textContent = result.message + " 匯入批次 #" + result.batch.id + "。原始 CSV、載具號碼均未保存，且尚未建立正式交易。";
      historyLoaded = false;
    } catch (error) {
      message.className = "einvoice-message is-error";
      message.textContent = "保存失敗：" + error.message;
    } finally {
      isSavingPreview = false;
      showInvoiceMode(currentInvoiceMode);
    }
  }

  function setHistoryMessage(message, isError = false) {
    const node = document.getElementById("einvoice-history-message");
    if (!node) return;
    node.textContent = message || "";
    node.className = "einvoice-message" + (message ? (isError ? " is-error" : " is-success") : "");
  }

  function statusLabel(value) {
    return ({
      matched: "核對一致",
      mismatch: "金額不一致",
      missing_details: "缺少明細",
      duplicate: "疑似重複"
    })[value] || "待檢查";
  }

  function formatHistoryMoney(value) {
    const amount = Number(value || 0);
    return "NT$ " + money.format(amount);
  }

  function renderHistoryPagination(total, pageSize) {
    const host = document.getElementById("einvoice-history-pagination");
    if (!host) return;
    host.replaceChildren();
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    historyPage = Math.min(Math.max(1, historyPage), totalPages);
    if (!total) {
      host.classList.add("hidden");
      return;
    }
    host.classList.remove("hidden");
    const start = (historyPage - 1) * pageSize + 1;
    const end = Math.min(total, historyPage * pageSize);
    const info = make("span", "einvoice-page-info", "顯示第 " + start + "–" + end + " 張，共 " + total + " 張 · 第 " + historyPage + "／" + totalPages + " 頁");
    const controls = make("div", "einvoice-page-controls");
    const previous = make("button", "secondary small einvoice-page-button", "上一頁");
    previous.type = "button";
    previous.disabled = historyPage <= 1;
    previous.addEventListener("click", () => { historyPage -= 1; loadHistoryInvoices(); });
    const next = make("button", "secondary small einvoice-page-button", "下一頁");
    next.type = "button";
    next.disabled = historyPage >= totalPages;
    next.addEventListener("click", () => { historyPage += 1; loadHistoryInvoices(); });
    controls.append(previous, next);
    host.append(info, controls);
  }

  function renderHistoryInvoices(result) {
    const list = document.getElementById("einvoice-history-list");
    const summary = document.getElementById("einvoice-history-summary");
    if (!list || !summary) return;
    list.replaceChildren();
    summary.textContent = "找到 " + result.total + " 張已保存發票";
    if (!result.invoices.length) {
      list.append(make("p", "einvoice-empty", "找不到符合條件的歷史發票。試試其他關鍵字或清除篩選條件。"));
      renderHistoryPagination(0, 20);
      return;
    }
    result.invoices.forEach(invoice => {
      const card = make("article", "einvoice-card einvoice-history-card");
      const top = make("div", "einvoice-card-top");
      const main = make("div", "einvoice-card-main");
      main.append(
        make("strong", "einvoice-merchant", invoice.merchant_name || "未提供店家"),
        make("span", "einvoice-date", invoice.invoice_date + " · " + invoice.invoice_number)
      );
      const amount = make("strong", "einvoice-amount", formatHistoryMoney(invoice.total_amount));
      top.append(main, amount);
      card.append(top);
      const meta = make("div", "einvoice-card-meta");
      meta.append(
        make("span", "einvoice-item-count", invoice.merchant_tax_id || "無統編資料"),
        make("span", "einvoice-status" + (invoice.verification_status === "matched" ? " is-good" : " is-warn"), statusLabel(invoice.verification_status)),
        make("span", "einvoice-item-count", invoice.is_duplicate ? "檔案內重複" : "已保存")
      );
      card.append(meta);
      const line = make("div", "einvoice-reconcile-line");
      line.append(
        make("span", "", "明細合計 " + formatHistoryMoney(invoice.detail_total)),
        make("strong", invoice.verification_status === "matched" ? "is-good-text" : "is-warn-text", "差額 " + formatHistoryMoney(invoice.difference_amount))
      );
      card.append(line);
      const actions = make("div", "einvoice-history-card-actions");
      const detailButton = make("button", "secondary small", "查看商品明細");
      detailButton.type = "button";
      detailButton.addEventListener("click", () => toggleHistoryDetails(card, invoice, detailButton));
      const postingButton = make("button", "secondary small", "確認入帳／付款");
      postingButton.type = "button";
      const canViewPosting = getBridge()?.hasPermission?.("transactions.view") === true;
      postingButton.disabled = !canViewPosting;
      postingButton.title = canViewPosting ? "查看入帳狀態或確認付款" : "需要交易查看權限才能查看入帳資料";
      postingButton.addEventListener("click", () => toggleInvoicePosting(card, invoice, postingButton));
      actions.append(detailButton, postingButton);
      card.append(actions);
      list.append(card);
    });
    renderHistoryPagination(result.total, 20);
  }

  async function loadInvoiceCategoryOptions(bridge, familyId) {
    if (cachedInvoiceCategories && cachedInvoiceCategoriesFamilyId === familyId) {
      return cachedInvoiceCategories;
    }
    const result = await bridge.api("/einvoices/categories?family_id=" + familyId);
    cachedInvoiceCategories = Array.isArray(result.categories) ? result.categories : [];
    cachedInvoiceCategoriesFamilyId = familyId;
    return cachedInvoiceCategories;
  }

  function invoicePostingStatusLabel(value) {
    return ({
      unpaid: "尚未付款",
      partially_paid: "部分付款",
      paid: "已全額付款",
      voided: "已沖銷"
    })[value] || "尚未入帳";
  }

  function formatAccountMoney(value, currencyCode) {
    const amount = Number(value || 0);
    const code = String(currencyCode || "TWD").toUpperCase();
    try {
      return new Intl.NumberFormat("zh-TW", {
        style: "currency",
        currency: code,
        minimumFractionDigits: code === "JPY" || code === "KRW" ? 0 : 2,
        maximumFractionDigits: 4
      }).format(amount);
    } catch (_) {
      return code + " " + money.format(amount);
    }
  }

  function localDateTimeValue(dateText) {
    const date = String(dateText || "").slice(0, 10);
    return date ? date + "T12:00" : new Date().toISOString().slice(0, 16);
  }

  function makeInvoicePaymentRow(accounts, invoiceDate) {
    const row = make("div", "einvoice-payment-entry");
    const accountLabel = make("label", "einvoice-payment-field");
    accountLabel.append(make("span", "", "付款帳戶"));
    const accountSelect = document.createElement("select");
    accountSelect.className = "einvoice-payment-account";
    accountSelect.add(new Option("選擇現金／銀行／信用卡／電子支付", ""));
    accounts.forEach(account => {
      accountSelect.add(new Option(
        account.name + " · " + account.currency_code + " · " + account.account_type,
        String(account.id)
      ));
    });
    accountLabel.append(accountSelect);

    const amountLabel = make("label", "einvoice-payment-field");
    amountLabel.append(make("span", "", "本次付款金額（TWD）"));
    const amountInput = document.createElement("input");
    amountInput.className = "einvoice-payment-amount";
    amountInput.type = "number";
    amountInput.min = "0.01";
    amountInput.step = "0.01";
    amountInput.inputMode = "decimal";
    amountInput.placeholder = "例如 120.50";
    amountLabel.append(amountInput);

    const dateLabel = make("label", "einvoice-payment-field");
    dateLabel.append(make("span", "", "實際付款日期"));
    const dateInput = document.createElement("input");
    dateInput.className = "einvoice-payment-date";
    dateInput.type = "datetime-local";
    dateInput.value = localDateTimeValue(invoiceDate);
    dateLabel.append(dateInput);

    const rateLabel = make("label", "einvoice-payment-field einvoice-payment-rate hidden");
    rateLabel.append(make("span", "", "匯率（帳戶幣別／TWD）"));
    const rateInput = document.createElement("input");
    rateInput.className = "einvoice-payment-exchange-rate";
    rateInput.type = "number";
    rateInput.min = "0.0000000001";
    rateInput.step = "0.0000000001";
    rateInput.inputMode = "decimal";
    rateInput.placeholder = "輸入實際成交匯率";
    rateLabel.append(rateInput);

    const remove = make("button", "secondary small einvoice-payment-remove", "移除此筆");
    remove.type = "button";
    remove.addEventListener("click", () => row.remove());
    accountSelect.addEventListener("change", () => {
      const account = accounts.find(item => Number(item.id) === Number(accountSelect.value));
      rateLabel.classList.toggle("hidden", !account || account.currency_code === "TWD");
      rateInput.value = account && account.currency_code !== "TWD" ? "" : "";
    });
    row.append(accountLabel, amountLabel, dateLabel, rateLabel, remove);
    return row;
  }

  async function toggleInvoicePosting(card, invoice, button) {
    const bridge = getBridge();
    const familyId = currentFamilyId();
    if (!bridge?.api || !familyId) return;
    const existing = card.querySelector(".einvoice-posting-panel");
    if (existing) {
      existing.remove();
      button.textContent = "確認入帳／付款";
      return;
    }
    button.disabled = true;
    button.textContent = "載入中…";
    try {
      const postingResult = await bridge.api(
        "/einvoices/" + invoice.id + "/posting?family_id=" + familyId
      );
      const posting = postingResult.posting;
      let accounts = [];
      if (bridge.hasPermission?.("accounts.view") && bridge.hasPermission?.("transactions.create")) {
        try {
          const accountResult = await bridge.api("/accounts?family_id=" + familyId);
          accounts = (accountResult.accounts || []).filter(account => account.is_active !== false);
        } catch (_) {
          accounts = [];
        }
      }
      const panel = make("section", "einvoice-posting-panel");
      const heading = make("div", "einvoice-posting-heading");
      heading.append(
        make("strong", "", "發票支出入帳"),
        make("span", "einvoice-status" + (posting?.status === "paid" ? " is-good" : " is-warn"),
          invoicePostingStatusLabel(posting?.status))
      );
      panel.append(heading);
      panel.append(make("p", "tiny muted", "發票總額 " + formatHistoryMoney(invoice.total_amount) + "。只有實際付款的金額會建立帳戶支出；未付款餘額不會先扣帳戶金額。"));

      if (posting) {
        const paid = make("div", "einvoice-posting-balance");
        paid.append(
          make("span", "", "已付款 " + formatHistoryMoney(posting.paid_amount)),
          make("strong", "", "剩餘 " + formatHistoryMoney(posting.remaining_amount))
        );
        panel.append(paid);
        if (posting.payments?.length) {
          const paymentList = make("ul", "einvoice-payment-history");
          posting.payments.forEach(payment => {
            const item = make("li", "einvoice-payment-history-row");
            const left = make("span", "", payment.account_name + " · " + String(payment.payment_date).slice(0, 10));
            const right = make("strong", "", formatHistoryMoney(payment.amount) + " → " +
              formatAccountMoney(payment.account_amount, payment.account_currency_code));
            item.append(left, right);
            item.append(make("small", "", "對應帳戶交易 #" + payment.transaction_id));
            if (payment.is_voided) {
              item.classList.add("is-voided");
              item.append(make("small", "einvoice-payment-voided-label", "已沖銷" +
                (payment.void_reason ? " · " + payment.void_reason : "")));
            }
            paymentList.append(item);
          });
          panel.append(paymentList);
        }
      }

      const canCreate = bridge.hasPermission?.("imports.confirm") &&
        bridge.hasPermission?.("transactions.view") &&
        bridge.hasPermission?.("transactions.create") &&
        bridge.hasPermission?.("accounts.view");
      const canVoid = posting &&
        bridge.hasPermission?.("imports.void") &&
        bridge.hasPermission?.("transactions.void") &&
        posting.status !== "voided";
      if (!posting && (!canCreate || invoice.verification_status !== "matched" || invoice.is_duplicate)) {
        panel.append(make("p", "einvoice-posting-warning", "入帳前需完成發票核對一致，且帳號必須有發票確認、交易新增及帳戶查看權限。"));
      }
      if (posting && posting.status === "voided") {
        panel.append(make("p", "einvoice-posting-warning", "此入帳已沖銷，原付款交易已一併作廢；原始明細仍保留。"));
      }

      const invoiceEligible = invoice.verification_status === "matched" && !invoice.is_duplicate;
      const isReopen = posting?.status === "voided";
      const allowMorePayment = canCreate && (posting || invoiceEligible) &&
        (!posting || isReopen || posting.status === "unpaid" || posting.status === "partially_paid") &&
        (!posting || isReopen || Number(posting.remaining_amount) > 0);
      if (allowMorePayment && accounts.length) {
        const form = make("div", "einvoice-posting-form");
        form.append(make("strong", "", isReopen ? "重新入帳：新增一筆或多筆付款" : posting ? "新增一筆或多筆付款" : "選擇付款方式"));
        const rows = make("div", "einvoice-payment-entries");
        rows.append(makeInvoicePaymentRow(accounts, invoice.invoice_date));
        const addRow = make("button", "secondary small", "＋新增另一個付款帳戶");
        addRow.type = "button";
        addRow.addEventListener("click", () => rows.append(makeInvoicePaymentRow(accounts, invoice.invoice_date)));
        const preview = make("p", "einvoice-payment-total", "本次付款合計 NT$ 0.00");
        const updatePreview = () => {
          const total = [...rows.querySelectorAll(".einvoice-payment-amount")]
            .reduce((sum, input) => sum + (Number(input.value) || 0), 0);
          preview.textContent = "本次付款合計 " + formatHistoryMoney(total) +
            (posting ? " · 目前剩餘 " + formatHistoryMoney(posting.remaining_amount) : " · 發票總額 " + formatHistoryMoney(invoice.total_amount));
          preview.classList.toggle("is-warn", total > Number(posting?.remaining_amount ?? invoice.total_amount));
        };
        rows.addEventListener("input", updatePreview);
        const actions = make("div", "einvoice-posting-actions");
        const save = make("button", "primary small",
          isReopen ? "重新入帳並保存付款" : posting ? "保存付款並建立支出" : "確認入帳並保存付款");
        save.type = "button";
        save.addEventListener("click", async () => {
          const paymentRows = [...rows.querySelectorAll(".einvoice-payment-entry")];
          const payments = [];
          for (const row of paymentRows) {
            const accountId = row.querySelector(".einvoice-payment-account").value;
            const amount = row.querySelector(".einvoice-payment-amount").value.trim();
            const dateValue = row.querySelector(".einvoice-payment-date").value;
            const rateInput = row.querySelector(".einvoice-payment-exchange-rate");
            if (!accountId && !amount) continue;
            if (!accountId || !amount || !dateValue) {
              setHistoryMessage("每筆付款請完整選擇帳戶、金額及日期。", true);
              return;
            }
            const account = accounts.find(item => Number(item.id) === Number(accountId));
            if (!account) {
              setHistoryMessage("付款帳戶不存在或已停用，請重新選擇。", true);
              return;
            }
            const payment = {
              account_id: Number(accountId),
              amount: Number(amount).toFixed(2),
              payment_date: new Date(dateValue).toISOString(),
              description: "電子發票 " + invoice.invoice_number
            };
            if (account.currency_code !== "TWD") {
              const rate = rateInput.value.trim();
              if (!rate || !(Number(rate) > 0)) {
                setHistoryMessage("外幣帳戶請輸入實際成交匯率。", true);
                return;
              }
              payment.exchange_rate = rate;
            }
            payments.push(payment);
          }
          const total = payments.reduce((sum, item) => sum + Number(item.amount), 0);
          const remaining = Number(posting?.remaining_amount ?? invoice.total_amount);
          if (total > remaining + 0.000001) {
            setHistoryMessage("本次付款超過發票尚未支付金額，請調整付款明細。", true);
            return;
          }
          if (!payments.length && posting && !isReopen) {
            setHistoryMessage("請至少新增一筆付款。", true);
            return;
          }
          const message = payments.length
            ? "將新增 " + payments.length + " 筆帳戶支出，付款合計 " + formatHistoryMoney(total) + "。"
            : isReopen
              ? "只重新建立發票待付款紀錄，不會新增交易或改變帳戶餘額。"
              : "只確認發票及建立待付款紀錄，不會變動任何帳戶餘額。";
          if (!window.confirm(message + "\n\n是否繼續？")) return;
          save.disabled = true;
          try {
            const endpoint = "/einvoices/" + invoice.id + "/posting" +
              (posting && !isReopen ? "/payments" : "") + "?family_id=" + familyId;
            const result = await bridge.api(endpoint, {
              method: "POST",
              body: JSON.stringify({payments})
            });
            setHistoryMessage(result.message);
            panel.remove();
            button.textContent = "查看入帳／付款";
            button.disabled = false;
            await toggleInvoicePosting(card, invoice, button);
          } catch (error) {
            setHistoryMessage("入帳／付款失敗：" + error.message, true);
            save.disabled = false;
          }
        });
        if (!posting || isReopen) {
          const defer = make("button", "secondary small",
            isReopen ? "重新建立未付款入帳" : "先確認發票，稍後付款");
          defer.type = "button";
          defer.addEventListener("click", async () => {
            if (!window.confirm("只建立發票待付款紀錄，不會新增交易或改變帳戶餘額。是否繼續？")) return;
            defer.disabled = true;
            try {
              const result = await bridge.api("/einvoices/" + invoice.id + "/posting?family_id=" + familyId, {
                method: "POST",
                body: JSON.stringify({payments: []})
              });
              setHistoryMessage(result.message);
              panel.remove();
              button.textContent = "查看入帳／付款";
              button.disabled = false;
              await toggleInvoicePosting(card, invoice, button);
            } catch (error) {
              setHistoryMessage("確認發票失敗：" + error.message, true);
              defer.disabled = false;
            }
          });
          actions.append(defer);
        }
        actions.append(save);
        form.append(rows, addRow, preview, actions);
        panel.append(form);
      } else if (allowMorePayment && !accounts.length) {
        panel.append(make("p", "einvoice-posting-warning", "目前家庭沒有可使用的付款帳戶，請先新增帳戶。"));
      }

      if (canVoid) {
        const voidButton = make("button", "secondary small einvoice-posting-void", "沖銷整筆入帳及付款");
        voidButton.type = "button";
        voidButton.addEventListener("click", async () => {
          const reason = window.prompt("請輸入沖銷原因（必填）：", "誤入帳或付款資料有誤");
          if (!reason || !reason.trim()) return;
          if (!window.confirm("沖銷後，這張發票所有對應帳戶支出交易都會作廢，並恢復帳戶餘額。原始紀錄仍會保留。是否繼續？")) return;
          voidButton.disabled = true;
          try {
            await bridge.api(
              "/einvoices/" + invoice.id + "/posting/void?family_id=" + familyId + "&reason=" + encodeURIComponent(reason.trim()),
              {method:"POST"}
            );
            setHistoryMessage("發票入帳及所有付款交易已沖銷。");
            panel.remove();
            button.textContent = "查看入帳／付款";
            button.disabled = false;
            await toggleInvoicePosting(card, invoice, button);
          } catch (error) {
            setHistoryMessage("沖銷失敗：" + error.message, true);
            voidButton.disabled = false;
          }
        });
        panel.append(voidButton);
      }
      card.append(panel);
      button.textContent = "收起入帳／付款";
    } catch (error) {
      setHistoryMessage("載入發票入帳資料失敗：" + error.message, true);
      button.textContent = "重新載入入帳資料";
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  }

  async function toggleHistoryDetails(card, invoice, button) {
    const bridge = getBridge();
    const familyId = currentFamilyId();
    if (!bridge?.api || !familyId) return;
    let details = card.querySelector(".einvoice-items");
    if (details) {
      details.remove();
      button.textContent = "查看商品明細";
      return;
    }
    button.disabled = true;
    button.textContent = "載入中…";
    try {
      const result = await bridge.api("/einvoices/" + invoice.id + "?family_id=" + familyId);
      const detail = make("div", "einvoice-items");
      detail.append(make("p", "tiny muted", "發票狀態：" + (invoice.invoice_status || "未提供") + " · 保存批次 #" + invoice.import_batch_id));

      const canViewCategories = bridge.hasPermission?.("categories.view") === true;
      const canUpdateCategories = bridge.hasPermission?.("categories.update") === true;
      let categories = [];
      if (canViewCategories) {
        try {
          categories = await loadInvoiceCategoryOptions(bridge, familyId);
        } catch (_) {
          categories = [];
        }
      }

      const itemList = make("ul", "einvoice-item-list");
      result.invoice.items.forEach(item => {
        const row = make("li", "einvoice-item");
        const itemMain = make("div", "einvoice-item-main");
        itemMain.append(
          make("span", "einvoice-item-name", item.item_name),
          make("strong", Number(item.amount) < 0 ? "is-negative" : "", formatHistoryMoney(item.amount))
        );
        row.append(itemMain);

        if (canViewCategories && Number(item.amount) > 0) {
          const categoryPanel = make("div", "einvoice-item-category");
          if (item.category_id) {
            categoryPanel.append(make("span", "einvoice-category-state is-assigned", "已分類：" + (item.category_name || "已設定分類")));
          } else if (item.suggested_category_id) {
            categoryPanel.append(make("span", "einvoice-category-state is-suggested", "建議分類：" + item.suggested_category_name));
          } else {
            categoryPanel.append(make("span", "einvoice-category-state", "尚未分類"));
          }

          if (canUpdateCategories && categories.length) {
            const controls = make("div", "einvoice-category-controls");
            const select = document.createElement("select");
            select.className = "einvoice-category-select";
            select.setAttribute("aria-label", item.item_name + "的支出分類");
            select.add(new Option("請選擇分類", ""));
            categories.forEach(category => {
              select.add(new Option((category.icon ? category.icon + " " : "") + category.name, String(category.id)));
            });
            const selectedCategoryId = item.category_id || item.suggested_category_id || "";
            if (selectedCategoryId && !categories.some(category => Number(category.id) === Number(selectedCategoryId)) && item.category_name) {
              select.add(new Option(item.category_name + "（目前分類）", String(selectedCategoryId)));
            }
            select.value = selectedCategoryId ? String(selectedCategoryId) : "";

            const rememberLabel = make("label", "einvoice-category-remember");
            const remember = document.createElement("input");
            remember.type = "checkbox";
            remember.checked = true;
            rememberLabel.append(remember, document.createTextNode("記住此店家與商品，下次自動建議"));

            const saveCategory = make("button", "secondary small einvoice-category-save", "保存分類");
            saveCategory.type = "button";
            saveCategory.addEventListener("click", async () => {
              const categoryId = select.value ? Number(select.value) : null;
              if (!categoryId && remember.checked) {
                setHistoryMessage("請先選擇分類，才能記住下次的分類建議。", true);
                return;
              }
              saveCategory.disabled = true;
              try {
                await bridge.api(
                  "/einvoices/" + invoice.id + "/items/" + item.id + "/category?family_id=" + familyId,
                  {
                    method: "PUT",
                    body: JSON.stringify({
                      category_id: categoryId,
                      remember_rule: remember.checked
                    })
                  }
                );
                setHistoryMessage(
                  "「" + item.item_name + "」分類已保存" +
                  (remember.checked ? "，下次相同店家與商品會自動提供建議。" : "。")
                );
                detail.remove();
                button.textContent = "查看商品明細";
                button.disabled = false;
                await toggleHistoryDetails(card, invoice, button);
              } catch (error) {
                setHistoryMessage("保存商品分類失敗：" + error.message, true);
                saveCategory.disabled = false;
              }
            });

            controls.append(select, saveCategory);
            categoryPanel.append(controls, rememberLabel);
          } else if (canUpdateCategories && !categories.length) {
            categoryPanel.append(make("span", "tiny muted", "目前沒有可使用的支出分類"));
          }
          row.append(categoryPanel);
        } else if (Number(item.amount) <= 0) {
          row.append(make("span", "tiny muted", "折扣／零元品項不另行分類"));
        }
        itemList.append(row);
      });
      if (!result.invoice.items.length) itemList.append(make("li", "tiny muted", "這張發票沒有可用的商品明細。"));
      detail.append(itemList);

      if (getBridge()?.hasPermission?.("imports.void") && !invoice.is_voided) {
        const voidButton = make("button", "secondary small", "作廢這筆發票紀錄");
        voidButton.type = "button";
        voidButton.addEventListener("click", async () => {
          const reason = window.prompt("請輸入作廢原因（必填）：", "重複或匯入錯誤");
          if (!reason || !reason.trim()) return;
          if (!window.confirm("作廢這張發票保存紀錄？商品明細會保留，正式收支交易不會變更。")) return;
          voidButton.disabled = true;
          try {
            await bridge.api("/einvoices/" + invoice.id + "/void?family_id=" + familyId + "&reason=" + encodeURIComponent(reason.trim()), {method:"POST"});
            setHistoryMessage("發票 " + invoice.invoice_number + " 已作廢保存紀錄；帳務交易未受影響。");
            await loadHistoryInvoices();
          } catch (error) {
            setHistoryMessage("作廢失敗：" + error.message, true);
            voidButton.disabled = false;
          }
        });
        detail.append(voidButton);
      }
      card.append(detail);
      button.textContent = "收起商品明細";
    } catch (error) {
      setHistoryMessage("讀取發票明細失敗：" + error.message, true);
      button.textContent = "重新載入明細";
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  }

  async function loadHistoryInvoices() {
    const bridge = getBridge();
    const familyId = currentFamilyId();
    if (!persistenceAvailable) {
      setHistoryMessage("家庭歷史發票資料庫尚未啟用；正式資料庫遷移完成並核准後即可使用。", true);
      return;
    }
    if (!bridge?.api || !familyId) {
      setHistoryMessage("請先登入並選擇家庭，再查詢歷史發票。", true);
      return;
    }
    if (!bridge.hasPermission?.("imports.view")) {
      setHistoryMessage("目前帳號沒有查看家庭歷史發票的權限。", true);
      return;
    }
    setHistoryMessage("正在搜尋家庭歷史發票…");
    const params = new URLSearchParams({
      family_id: String(familyId),
      skip: String((historyPage - 1) * 20),
      limit: "20",
      verification_status: document.getElementById("einvoice-history-status").value
    });
    const query = document.getElementById("einvoice-history-query").value.trim();
    const month = document.getElementById("einvoice-history-month").value;
    const min = document.getElementById("einvoice-history-min").value.trim();
    const max = document.getElementById("einvoice-history-max").value.trim();
    if (query) params.set("q", query);
    if (month) params.set("month", month);
    if (min) params.set("min_amount", min);
    if (max) params.set("max_amount", max);
    try {
      const result = await bridge.api("/einvoices?" + params.toString());
      renderHistoryInvoices(result);
      historyLoaded = true;
      setHistoryMessage("");
    } catch (error) {
      setHistoryMessage("歷史發票查詢失敗：" + error.message, true);
    }
  }

  window.EInvoiceCsvPreview = { parseText };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
})();