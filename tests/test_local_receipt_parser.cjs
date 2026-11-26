const test = require("node:test");
const assert = require("node:assert/strict");
const parser = require("../static/local-receipt-parser.js");

const leftQr = "AB1122334410205239999000001440000015400000000001234567ydXZt4LAN1UHN/j1juVcRA==:**********:3:3:1:乾電池:1:105:";
const rightQr = "**口罩:1:210:牛奶:1:25";

test("parses Taiwan e-invoice QR header, date, total and seller tax ID", () => {
  const result = parser.parseTaiwanInvoiceQr(leftQr, rightQr);
  assert.equal(result.invoiceNumber, "AB11223344");
  assert.equal(result.date, "2013-05-23");
  assert.equal(result.totalAmount, "340");
  assert.equal(result.salesAmount, "324");
  assert.equal(result.sellerTaxId, "01234567");
  assert.deepEqual(result.items.map((item) => item.name), ["乾電池", "口罩", "牛奶"]);
});

test("accepts a valid 77-character left QR even without optional item extension", () => {
  const fixedHeader = leftQr.split(":")[0];
  assert.equal(fixedHeader.length, 77);
  const result = parser.parseTaiwanInvoiceQr(fixedHeader, null);
  assert.ok(result);
  assert.equal(result.invoiceNumber, "AB11223344");
  assert.equal(result.totalAmount, "340");
  assert.deepEqual(result.items, []);
});

test("classifies an electronic invoice and prioritizes verified QR fields", () => {
  const result = parser.parseReceiptData(
    "電子發票證明聯\nAB-11223344\n總計：999\n2013-05-23",
    [
      { format: "QR Code", value: leftQr, side: "left" },
      { format: "QR Code", value: rightQr, side: "right" }
    ]
  );
  assert.equal(result.type, "electronic_invoice");
  assert.equal(result.typeLabel, "電子發票證明聯");
  assert.equal(result.invoiceNumber, "AB11223344");
  assert.equal(result.amount, "340");
  assert.equal(result.date, "2013-05-23");
  assert.equal(result.source, "qr");
  assert.equal(result.items.length, 3);
});

test("extracts traditional two-part invoice merchant, date, amount and seller ID", () => {
  const result = parser.parseReceiptData(
    "松山商店\n二聯式統一發票\n日期：2026/11/25\n總計：1,250\n賣方統編：12345678",
    []
  );
  assert.equal(result.type, "two_part_invoice");
  assert.equal(result.merchant, "松山商店");
  assert.equal(result.date, "2026-11-25");
  assert.equal(result.amount, "1250");
  assert.equal(result.sellerTaxId, "12345678");
});

test("distinguishes three-part invoices and ordinary receipts", () => {
  assert.equal(parser.detectReceiptType("三聯式統一發票", false), "three_part_invoice");
  assert.equal(parser.detectReceiptType("收據", false), "receipt");
  assert.equal(parser.detectReceiptType("手寫收據", false), "handwritten");
  assert.equal(parser.detectReceiptType("一般交易單", false), "unknown");
});
