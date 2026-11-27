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
    return String(value || "").normalize("NFKC").toLocaleLowerCase("zh-TW").replace(/\\s+/g, "");
  }

  function invoiceMatchesSearch(invoice, query) {
    const term = normalizeSearchTerm(query);
    if (!term) return true;

    const textValues = [
      invoice.invoiceNumber,
      invoice.merchantName,
      invoice.merchantTaxId,
      invoice.date,
      invoice.invoiceStatus,
      invoice.carrierType,
      statusText(invoice),
      ...invoice.items.map(item => item.itemName)
    ];
    if (textValues.some(value => normalizeSearchTerm(value).includes(term))) return true;

    const numericTerm = term.replace(/[^\\d.-]/g, "");
    if (!numericTerm) return false;
    const amounts = [
      formatMoney(invoice.totalCents),
      String(invoice.totalCents / 100),
      ...invoice.items.map(item => formatMoney(item.amountCents)),
      ...invoice.items.map(item => String(item.amountCents / 100))
    ];
    return amounts.some(value => normalizeSearchTerm(value).replace(/[^\\d.-]/g, "").includes(numericTerm));
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

  async function handleFile(file) {
    const message = document.getElementById("einvoice-csv-message");
    const results = document.getElementById("einvoice-csv-results");
    const clear = document.getElementById("einvoice-csv-clear");
    if (!file) return;
    parsedResult = null;
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
      document.getElementById("einvoice-csv-filter").value = "all";
      document.getElementById("einvoice-csv-search").value = "";
      document.getElementById("einvoice-csv-search-clear").disabled = true;
      document.getElementById("einvoice-csv-page-size").value = "10";
      fillMonthOptions(parsedResult.invoices);
      document.getElementById("einvoice-csv-filename").textContent = file.name;
      message.classList.add("is-success");
      message.textContent = "已在此裝置完成解析。原始 CSV 不會上傳伺服器，也尚未寫入正式帳務。";
      renderInvoices();
    } catch (error) {
      parsedResult = null;
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
      '<div class="einvoice-upload-box">' +
        '<div class="einvoice-upload-heading"><label class="field">選擇電子發票 CSV 檔案' +
          '<input id="einvoice-csv-file" type="file" accept=".csv,.txt,text/csv,text/plain"></label>' +
          '<button id="einvoice-csv-clear" class="secondary einvoice-clear-button" type="button" disabled>清除預覽</button></div>' +
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
        '<p class="einvoice-local-footnote">目前為本機檢查預覽：不會寫入資料庫、不會新增正式交易，也不會與銀行／信用卡 CSV 匯入混用。清除預覽或重新整理頁面後，請重新選取檔案。</p>' +
      '</div>';
    workspace.append(section);

    const fileInput = document.getElementById("einvoice-csv-file");
    fileInput.addEventListener("change", event => {
      const file = event.target.files && event.target.files[0];
      event.target.value = "";
      handleFile(file);
    });
    document.getElementById("einvoice-csv-clear").addEventListener("click", () => resetPreview(true));
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

  window.EInvoiceCsvPreview = { parseText };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
})();