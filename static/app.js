const API = "";
const TOKEN_KEY = "family_finance_access_token";
const INVITE_TOKEN_KEY = "family_finance_pending_invite";
let mode = "login";
let currentUser = null;
let selectedFamilyId = null;
let accounts = [];
let accountBalances = new Map();
let editingAccountId = null;
let openingBalanceAccount = null;
const $ = (id) => document.getElementById(id);
const token = () => sessionStorage.getItem(TOKEN_KEY);
function notice(target, message, type="success"){const el=$(target);el.textContent=message;el.className="notice show "+type;}
function clearNotice(target){const el=$(target);el.textContent="";el.className="notice";}
async function api(path, options={}){const headers={"Content-Type":"application/json",...(options.headers||{})};if(token())headers.Authorization="Bearer "+token();const response=await fetch(API+path,{...options,headers});let data={};try{data=await response.json();}catch{}if(!response.ok){if(response.status===401&&token()){sessionStorage.removeItem(TOKEN_KEY);showAuth();}const error=new Error(data.detail||"目前無法完成操作，請稍後再試。");error.status=response.status;throw error;}return data;}
function setMode(next){mode=next;$("login-tab").classList.toggle("active",mode==="login");$("register-tab").classList.toggle("active",mode==="register");$("name-wrap").classList.toggle("hidden",mode!=="register");$("form-title").textContent=mode==="login"?"歡迎回來":"建立家庭帳號";$("form-desc").textContent=mode==="login"?"使用 Email 與密碼登入家庭記帳系統。":"建立帳號後即可建立家庭或加入家人邀請。";$("submit-auth").textContent=mode==="login"?"登入":"建立帳號";$("password").autocomplete=mode==="login"?"current-password":"new-password";clearNotice("notice");}
function showAuth(){currentUser=null;$("auth-view").classList.remove("hidden");$("app-view").classList.add("hidden");}
function showApp(){$("auth-view").classList.add("hidden");$("app-view").classList.remove("hidden");}
async function loadApp(){try{currentUser=await api("/auth/me");}catch(error){showAuth();notice("notice",error.message,"error");return;}$("user-greeting").textContent=currentUser.display_name+"（"+currentUser.email+"）";showApp();try{await loadFamilies();await handlePendingFamilyInvitation();}catch(error){notice("notice-app","已登入，但家庭清單載入失敗："+error.message,"error");}}
async function loadFamilies(){const result=await api("/families/mine");$("family-count").textContent=result.total+" 個家庭";const list=$("family-list");list.replaceChildren();$("empty-family").classList.toggle("hidden",result.total!==0);if(!selectedFamilyId&&result.families.length){selectedFamilyId=result.families[0].family_id;}for(const family of result.families){const card=document.createElement("button");card.type="button";card.className="family-card"+(selectedFamilyId===family.family_id?" selected":"");const title=document.createElement("strong");title.textContent=family.family_name;const meta=document.createElement("span");meta.textContent=family.currency+" · 家庭成員";card.append(title,meta);card.addEventListener("click",async()=>{selectedFamilyId=family.family_id;for(const node of list.children)node.classList.remove("selected");card.classList.add("selected");notice("notice-app","已切換至「"+family.family_name+"」。","success");if(!$("accounts-view").classList.contains("hidden")){await loadAccounts();}if(!$("transactions-view").classList.contains("hidden")){await showTransactions();}if(!$("transfers-view").classList.contains("hidden")){await showTransfers();}if(!$("credit-card-payments-view").classList.contains("hidden")){await showCreditCardPayments();}if(!$("bills-view").classList.contains("hidden")){await showBills();}if(!$("bill-payments-view").classList.contains("hidden")){$("bill-payments-view").classList.add("hidden");activeBillForPayments=null;}if(!$("recurring-bills-view").classList.contains("hidden")){await showRecurringBills();}if(!$("reports-view").classList.contains("hidden")){await loadFinancialReports();}if(!$("family-members-view").classList.contains("hidden")){await loadFamilyMembers();}if(!$("family-roles-view").classList.contains("hidden")){await loadFamilyRoles();}if(!$("audit-logs-view").classList.contains("hidden")){await loadAuditLogs();}if(!$("bank-reconciliation-view").classList.contains("hidden")&&window.loadBankReconciliationWorkspace){await window.loadBankReconciliationWorkspace();}});list.append(card);}}
function accountTypeLabel(type){return({bank:"銀行帳戶",time_deposit:"定期存款",cash:"現金",credit_card:"信用卡",e_wallet:"電子支付",other:"其他"})[type]||type;}
function money(value,currency){const amount=Number(value||0);try{return new Intl.NumberFormat("zh-TW",{style:"currency",currency:currency||"TWD",minimumFractionDigits:2,maximumFractionDigits:2}).format(amount);}catch{return amount.toFixed(2)+" "+(currency||"");}}
function toggleCreditFields(){const isCard=$("account-type").value==="credit_card";$("credit-fields").classList.toggle("hidden",!isCard);}
function resetAccountForm(){editingAccountId=null;$("account-form").reset();$("account-form-title").textContent="新增帳戶";$("account-submit").textContent="新增帳戶";$("account-form-panel").classList.add("hidden");$("account-number-last4").value="";toggleCreditFields();}
function accountPayload(){const isCard=$("account-type").value==="credit_card";return{name:$("account-name").value.trim(),account_type:$("account-type").value,currency_code:$("account-currency").value.trim().toUpperCase(),institution_name:$("account-institution").value.trim()||null,account_number_last4:$("account-number-last4").value.trim()||null,credit_limit:isCard&&$("credit-limit").value?$("credit-limit").value:null,statement_day:isCard&&$("statement-day").value?Number($("statement-day").value):null,payment_due_day:isCard&&$("payment-due-day").value?Number($("payment-due-day").value):null,note:$("account-note").value.trim()||null};}
function startEditAccount(account){editingAccountId=account.id;$("account-form-title").textContent="修改帳戶";$("account-submit").textContent="儲存修改";$("account-name").value=account.name;$("account-type").value=account.account_type;$("account-currency").value=account.currency_code;$("account-institution").value=account.institution_name||"";$("account-number-last4").value=account.account_number_last4||"";$("credit-limit").value=account.credit_limit??"";$("statement-day").value=account.statement_day??"";$("payment-due-day").value=account.payment_due_day??"";$("account-note").value=account.note||"";toggleCreditFields();$("account-form-panel").classList.remove("hidden");$("account-form-panel").scrollIntoView({behavior:"smooth",block:"start"});}
function renderAccounts(){const list=$("accounts-list");list.replaceChildren();$("accounts-count").textContent=accounts.length+" 個帳戶";if(!accounts.length){$("accounts-empty").classList.remove("hidden");return;}$("accounts-empty").classList.add("hidden");for(const account of accounts){const balance=accountBalances.get(account.id);const card=document.createElement("article");card.className="account-card";const top=document.createElement("div");top.className="account-card-top";const titleWrap=document.createElement("div");const title=document.createElement("h3");title.textContent=account.name;const meta=document.createElement("p");meta.className="muted";meta.textContent=accountTypeLabel(account.account_type)+" · "+account.currency_code+(account.institution_name?" · "+account.institution_name:"");titleWrap.append(title,meta);const amount=document.createElement("strong");amount.className="account-balance";amount.textContent=balance?money(balance.balance,account.currency_code):"餘額暫不可用";const amountLabel=document.createElement("span");amountLabel.className="tiny muted balance-label";amountLabel.textContent=account.account_type==="credit_card"?"目前欠款":"目前餘額";const amountWrap=document.createElement("div");amountWrap.className="balance-wrap";amountWrap.append(amountLabel,amount);top.append(titleWrap,amountWrap);card.append(top);if(account.account_number_last4){const last4=document.createElement("p");last4.className="account-detail";last4.textContent="帳號末四碼：•••• "+account.account_number_last4;card.append(last4);}if(account.account_type==="credit_card"&&(account.credit_limit!==null||account.statement_day||account.payment_due_day)){const extra=document.createElement("p");extra.className="account-detail";extra.textContent=["額度 "+(account.credit_limit?money(account.credit_limit,account.currency_code):"未設定"),account.statement_day?"結帳日 "+account.statement_day+" 日":"",account.payment_due_day?"繳款日 "+account.payment_due_day+" 日":""].filter(Boolean).join(" · ");card.append(extra);}const actions=document.createElement("div");actions.className="account-actions";const edit=document.createElement("button");edit.type="button";edit.className="secondary small";edit.textContent="修改";edit.addEventListener("click",()=>startEditAccount(account));const opening=document.createElement("button");opening.type="button";opening.className="secondary small";opening.textContent="設定期初餘額";opening.addEventListener("click",()=>openOpeningBalance(account));const voidButton=document.createElement("button");voidButton.type="button";voidButton.className="danger small";voidButton.textContent="作廢";voidButton.addEventListener("click",()=>voidAccount(account));actions.append(edit,opening,voidButton);card.append(actions);list.append(card);}}
async function loadAccounts(){if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理帳戶。","error");return;}clearNotice("account-notice");$("accounts-list").replaceChildren();$("accounts-loading").classList.remove("hidden");try{const [accountResult,balanceResult]=await Promise.all([api("/accounts?family_id="+selectedFamilyId),api("/accounts/balances?family_id="+selectedFamilyId).catch(error=>({__error:error}))]);accounts=accountResult.accounts||[];accountBalances=new Map();if(balanceResult.__error){notice("account-notice","帳戶清單已載入，但餘額讀取失敗："+balanceResult.__error.message,"error");}else{for(const item of balanceResult.balances||[]){accountBalances.set(item.account_id,item);}}renderAccounts();}catch(error){notice("account-notice","帳戶清單載入失敗："+error.message,"error");}finally{$("accounts-loading").classList.add("hidden");}}
function showAccounts(){if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理帳戶。","error");return;}$("accounts-view").classList.remove("hidden");$("accounts-view").scrollIntoView({behavior:"smooth",block:"start"});loadAccounts();}
$("open-accounts").addEventListener("click",showAccounts);
$("close-accounts").addEventListener("click",()=>{$("accounts-view").classList.add("hidden");resetAccountForm();$("opening-form-panel").classList.add("hidden");});
$("account-type").addEventListener("change",toggleCreditFields);
$("add-account-button").addEventListener("click",()=>{resetAccountForm();$("account-form-panel").classList.remove("hidden");$("account-form-panel").scrollIntoView({behavior:"smooth",block:"start"});});
$("account-cancel").addEventListener("click",resetAccountForm);
$("account-form").addEventListener("submit",async(event)=>{event.preventDefault();const button=$("account-submit");button.disabled=true;clearNotice("account-notice");try{const payload=accountPayload();const isEditing=Boolean(editingAccountId);const successMessage=isEditing?"帳戶資料已更新。":"帳戶已新增。";if(isEditing){await api("/accounts/"+editingAccountId+"?family_id="+selectedFamilyId,{method:"PATCH",body:JSON.stringify(payload)});}else{await api("/accounts?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});}resetAccountForm();await loadAccounts();notice("account-notice",successMessage,"success");}catch(error){notice("account-notice",error.message,"error");}finally{button.disabled=false;}});
async function voidAccount(account){if(!window.confirm("確定要作廢「"+account.name+"」？作廢後不會刪除歷史紀錄。"))return;try{await api("/accounts/"+account.id+"?family_id="+selectedFamilyId,{method:"DELETE"});await loadAccounts();notice("account-notice","帳戶已作廢，歷史資料仍會保留。","success");}catch(error){notice("account-notice",error.message,"error");}}
function localDateString(){const now=new Date();return now.getFullYear()+"-"+String(now.getMonth()+1).padStart(2,"0")+"-"+String(now.getDate()).padStart(2,"0");}
async function openOpeningBalance(account){openingBalanceAccount=account;$("opening-account-name").textContent=account.name;$("opening-amount-label").textContent=account.account_type==="credit_card"?"期初欠款金額":"期初餘額";$("opening-amount").value="";$("opening-date").value=localDateString();$("opening-form-panel").classList.remove("hidden");$("opening-status").textContent="正在確認是否已有有效期初餘額…";$("opening-form").classList.add("hidden");$("opening-form-panel").scrollIntoView({behavior:"smooth",block:"start"});try{const result=await api("/transactions?family_id="+selectedFamilyId+"&account_id="+account.id+"&transaction_type=opening_balance&include_voided=true&limit=200");const active=(result.transactions||[]).filter(item=>!item.is_voided);if(active.length){$("opening-status").textContent="此帳戶已有有效期初餘額："+money(active[0].amount,account.currency_code)+"。依系統規則，每個帳戶只能有一筆有效期初餘額。";}else{$("opening-status").textContent=(result.transactions||[]).length?"先前期初餘額已作廢，可重新設定一筆有效期初餘額。":"尚未設定期初餘額。";$("opening-form").classList.remove("hidden");}}catch(error){$("opening-status").textContent="無法確認期初餘額狀態："+error.message;}}
$("opening-cancel").addEventListener("click",()=>{$("opening-form-panel").classList.add("hidden");openingBalanceAccount=null;});
$("opening-form").addEventListener("submit",async(event)=>{event.preventDefault();if(!openingBalanceAccount)return;const button=$("opening-submit");button.disabled=true;try{const amount=$("opening-amount").value;if(!(Number(amount)>0))throw new Error("金額必須大於 0。");await api("/transactions?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify({account_id:openingBalanceAccount.id,transaction_type:"opening_balance",amount:amount,currency_code:openingBalanceAccount.currency_code,transaction_date:$("opening-date").value+"T00:00:00+08:00",description:"期初餘額"})});$("opening-form-panel").classList.add("hidden");openingBalanceAccount=null;await loadAccounts();notice("account-notice","期初餘額已設定。","success");}catch(error){$("opening-status").textContent=error.message;}finally{button.disabled=false;}});
$("login-tab").addEventListener("click",()=>setMode("login"));$("register-tab").addEventListener("click",()=>setMode("register"));
$("auth-form").addEventListener("submit",async(event)=>{event.preventDefault();clearNotice("notice");const button=$("submit-auth");button.disabled=true;try{const payload={email:$("email").value.trim(),password:$("password").value};let result;if(mode==="login"){result=await api("/auth/login",{method:"POST",body:JSON.stringify(payload)});}else{payload.display_name=$("display-name").value.trim();await api("/auth/register",{method:"POST",body:JSON.stringify(payload)});result=await api("/auth/login",{method:"POST",body:JSON.stringify({email:payload.email,password:payload.password})});}sessionStorage.setItem(TOKEN_KEY,result.access_token);$("auth-form").reset();await loadApp();}catch(error){notice("notice",error.message,"error");}finally{button.disabled=false;}});
$("create-family-form").addEventListener("submit",async(event)=>{event.preventDefault();clearNotice("notice-app");const button=event.submitter;button.disabled=true;try{const result=await api("/families",{method:"POST",body:JSON.stringify({name:$("family-name").value.trim(),currency:$("family-currency").value})});$("family-name").value="";selectedFamilyId=result.family_id;await loadFamilies();notice("notice-app","家庭「"+result.family_name+"」已建立，建立者已設定為家庭管理員。","success");}catch(error){notice("notice-app",error.message,"error");}finally{button.disabled=false;}});
$("logout-button").addEventListener("click",async()=>{let revoked=false;try{await api("/auth/logout",{method:"POST"});revoked=true;}catch{}sessionStorage.removeItem(TOKEN_KEY);sessionStorage.removeItem(INVITE_TOKEN_KEY);selectedFamilyId=null;accounts=[];accountBalances.clear();$("accounts-view").classList.add("hidden");showAuth();setMode("login");if(revoked){notice("notice","已安全登出。","success");}else{notice("notice","已清除此瀏覽器的登入狀態，但伺服器端 Token 撤銷未確認；請確認網路連線後重新登入。","error");}});
async function init(){captureFamilyInvitationToken();if(token()){await loadApp();}else{showAuth();}try{const cfg=await fetch("/app-config").then(r=>r.json());if(cfg.google_client_id){const script=document.createElement("script");script.src="https://accounts.google.com/gsi/client";script.async=true;script.defer=true;script.onload=()=>{google.accounts.id.initialize({client_id:cfg.google_client_id,callback:async(response)=>{try{let result;try{result=await api("/auth/google",{method:"POST",body:JSON.stringify({id_token:response.credential})});}catch(error){if(error.status!==409)throw error;const accepted=window.confirm("這個 Google Email 已有家庭記帳系統帳號。是否使用 Google 已驗證的相同 Email，將 Google 安全綁定到既有帳號並登入？\n\n此操作不會建立新帳號，也不會更動原有家庭與帳務資料。");if(!accepted)return;result=await api("/auth/google/recover",{method:"POST",body:JSON.stringify({id_token:response.credential})});}sessionStorage.setItem(TOKEN_KEY,result.access_token);await loadApp();}catch(error){notice("notice",error.message,"error");}}});google.accounts.id.renderButton($("google-button"),{theme:"outline",size:"large",shape:"rectangular",width:300,text:"continue_with",locale:"zh_TW"});$("google-hint").classList.add("hidden");};document.head.append(script);}}catch{}}
init();

// --------------------------------------------------
// G-02-03：收入與支出交易管理
// --------------------------------------------------
let editingTransactionId = null;
let transactionRows = [];
let transactionAccounts = [];
let transactionCategories = [];

function transactionTypeLabel(type) {
  return ({income:"收入",expense:"支出",opening_balance:"期初餘額"})[type] || type;
}

function transactionDateInput(value) {
  if (!value) return localDateString();
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return localDateString();
  return date.getFullYear()+"-"+String(date.getMonth()+1).padStart(2,"0")+"-"+String(date.getDate()).padStart(2,"0");
}

function transactionDateTime(value, endOfDay=false) {
  return value ? value+(endOfDay ? "T23:59:59+08:00" : "T00:00:00+08:00") : "";
}

function populateTransactionAccountSelects() {
  const formSelect=$("transaction-account");
  const filterSelect=$("transaction-filter-account");
  formSelect.replaceChildren();
  filterSelect.replaceChildren(new Option("全部帳戶",""));
  for (const account of transactionAccounts) {
    const label=account.name+" · "+account.currency_code;
    formSelect.add(new Option(label,String(account.id)));
    filterSelect.add(new Option(label,String(account.id)));
  }
}

function populateTransactionCategories(type, selectedId=null) {
  const select=$("transaction-category");
  select.replaceChildren(new Option("未指定分類",""));
  for (const category of transactionCategories.filter(item=>item.category_type===type)) {
    select.add(new Option(category.name,String(category.id)));
  }
  if (selectedId!==null && selectedId!==undefined) {
    if (!transactionCategories.some(item=>item.id===Number(selectedId))) select.add(new Option("既有分類 #"+selectedId,String(selectedId)));
    select.value=String(selectedId);
  }
}

async function loadTransactionSupportData() {
  const [accountResult,categoryResult]=await Promise.all([
    api("/accounts?family_id="+selectedFamilyId),
    api("/categories?family_id="+selectedFamilyId).catch(()=>({categories:[]}))
  ]);
  transactionAccounts=accountResult.accounts||[];
  transactionCategories=categoryResult.categories||[];
  populateTransactionAccountSelects();
  populateTransactionCategories($("transaction-type").value);
}

function transactionQuery() {
  const params=new URLSearchParams({family_id:String(selectedFamilyId),limit:"200"});
  const type=$("transaction-filter-type").value;
  const accountId=$("transaction-filter-account").value;
  const start=$("transaction-filter-start").value;
  const end=$("transaction-filter-end").value;
  if(type)params.set("transaction_type",type);
  if(accountId)params.set("account_id",accountId);
  if(start)params.set("start_date",transactionDateTime(start));
  if(end)params.set("end_date",transactionDateTime(end,true));
  if($("transaction-include-voided").checked)params.set("include_voided","true");
  return params.toString();
}

function renderTransactions() {
  const list=$("transactions-list");
  list.replaceChildren();
  $("transactions-count").textContent=transactionRows.length+" 筆紀錄";
  $("transactions-empty").classList.toggle("hidden",transactionRows.length!==0);
  for(const item of transactionRows) {
    const account=transactionAccounts.find(row=>row.id===item.account_id);
    const category=transactionCategories.find(row=>row.id===item.category_id);
    const card=document.createElement("article");
    card.className="transaction-card"+(item.is_voided?" transaction-voided":"");
    const top=document.createElement("div");
    top.className="transaction-card-top";
    const main=document.createElement("div");
    const title=document.createElement("strong");
    title.textContent=item.description||transactionTypeLabel(item.transaction_type);
    const meta=document.createElement("p");
    meta.className="muted tiny";
    meta.textContent=[transactionTypeLabel(item.transaction_type),transactionDateInput(item.transaction_date),account?account.name:"帳戶 #"+item.account_id,category?category.name:"未分類"].join(" · ");
    main.append(title,meta);
    const amount=document.createElement("strong");
    amount.className="transaction-amount "+(item.transaction_type==="income"?"income":"expense");
    amount.textContent=(item.transaction_type==="expense"?"−":item.transaction_type==="income"?"+":"")+money(item.amount,item.currency_code);
    top.append(main,amount);
    card.append(top);
    if(item.is_voided) {
      const status=document.createElement("span");
      status.className="transaction-status";
      status.textContent="已作廢";
      card.append(status);
    }
    const managed=item.transfer_id!==null||item.credit_card_payment_id!==null||item.bill_payment_id!==null;
    if(!item.is_voided&&!managed) {
      const actions=document.createElement("div");
      actions.className="account-actions";
      const edit=document.createElement("button");
      edit.type="button";edit.className="secondary small";edit.textContent="修改";
      edit.addEventListener("click",()=>startEditTransaction(item));
      const voidButton=document.createElement("button");
      voidButton.type="button";voidButton.className="danger small";voidButton.textContent="作廢";
      voidButton.addEventListener("click",()=>voidTransaction(item));
      actions.append(edit,voidButton);
      card.append(actions);
    } else if(managed&&!item.is_voided) {
      const hint=document.createElement("p");
      hint.className="tiny muted";
      hint.textContent="此筆紀錄由轉帳／繳款功能管理，請至對應功能修改或作廢。";
      card.append(hint);
    }
    list.append(card);
  }
}

async function loadTransactions() {
  if(!selectedFamilyId)return;
  clearNotice("transaction-notice");
  $("transactions-loading").classList.remove("hidden");
  try {
    const result=await api("/transactions?"+transactionQuery());
    transactionRows=result.transactions||[];
    renderTransactions();
    return true;
  } catch(error) {
    notice("transaction-notice","收支紀錄載入失敗："+error.message,"error");
    return false;
  } finally {
    $("transactions-loading").classList.add("hidden");
  }
}

async function showTransactions() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理收支紀錄。","error");return;}
  $("transactions-view").classList.remove("hidden");
  $("transactions-view").scrollIntoView({behavior:"smooth",block:"start"});
  try {
    await loadTransactionSupportData();
    await loadTransactions();
  } catch(error) {
    notice("transaction-notice","收支管理初始化失敗："+error.message,"error");
  }
}

function resetTransactionForm() {
  editingTransactionId=null;
  $("transaction-form").reset();
  $("transaction-form-title").textContent="新增收支";
  $("transaction-submit").textContent="新增紀錄";
  $("transaction-type").disabled=false;
  $("transaction-account").disabled=false;
  $("transaction-date").value=localDateString();
  $("transaction-form-panel").classList.add("hidden");
  populateTransactionCategories($("transaction-type").value);
}

function startEditTransaction(item) {
  editingTransactionId=item.id;
  $("transaction-form-title").textContent="修改收支";
  $("transaction-submit").textContent="儲存修改";
  $("transaction-type").value=item.transaction_type;
  $("transaction-type").disabled=item.transaction_type==="opening_balance";
  $("transaction-account").value=String(item.account_id);
  $("transaction-account").disabled=true;
  $("transaction-amount").value=item.amount;
  $("transaction-date").value=transactionDateInput(item.transaction_date);
  $("transaction-description").value=item.description||"";
  $("transaction-reference").value=item.external_reference||"";
  $("transaction-note").value=item.note||"";
  populateTransactionCategories(item.transaction_type,item.category_id);
  $("transaction-form-panel").classList.remove("hidden");
  $("transaction-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
}

$("open-transactions").addEventListener("click",showTransactions);
$("close-transactions").addEventListener("click",()=>{
  $("transactions-view").classList.add("hidden");
  resetTransactionForm();
});
$("add-transaction-button").addEventListener("click",()=>{
  resetTransactionForm();
  if(!transactionAccounts.length){notice("transaction-notice","請先建立至少一個啟用中的帳戶。","error");return;}
  $("transaction-form-panel").classList.remove("hidden");
  $("transaction-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
});
$("transaction-cancel").addEventListener("click",resetTransactionForm);
$("transaction-type").addEventListener("change",()=>{
  populateTransactionCategories($("transaction-type").value);
});
$("apply-transaction-filters").addEventListener("click",loadTransactions);
$("transaction-filter-type").addEventListener("change",loadTransactions);
$("transaction-filter-account").addEventListener("change",loadTransactions);
$("transaction-include-voided").addEventListener("change",loadTransactions);
$("transaction-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const button=$("transaction-submit");
  button.disabled=true;
  clearNotice("transaction-notice");
  try {
    const account=transactionAccounts.find(row=>row.id===Number($("transaction-account").value));
    if(!account)throw new Error("請選擇有效帳戶。");
    const type=$("transaction-type").value;
    const categoryId=$("transaction-category").value;
    const wasEditing=Boolean(editingTransactionId);
    const payload={
      transaction_type:type,
      amount:$("transaction-amount").value,
      currency_code:account.currency_code,
      transaction_date:new Date($("transaction-date").value+"T12:00:00").toISOString(),
      description:$("transaction-description").value.trim()||null,
      category_id:categoryId?Number(categoryId):null,
      external_reference:$("transaction-reference").value.trim()||null,
      note:$("transaction-note").value.trim()||null
    };
    if(wasEditing) {
      delete payload.currency_code;
      await api("/transactions/"+editingTransactionId+"?family_id="+selectedFamilyId,{method:"PATCH",body:JSON.stringify(payload)});
    } else {
      payload.account_id=account.id;
      await api("/transactions?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
    }
    resetTransactionForm();
    const refreshed=await loadTransactions();
    await loadAccounts();
    notice("transaction-notice",refreshed?(wasEditing?"收支紀錄已更新。":"收支紀錄已新增。"):"資料已儲存，但收支清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("transaction-notice",error.message,"error");
  } finally {
    button.disabled=false;
  }
});

async function voidTransaction(item) {
  if(!window.confirm("確定要作廢這筆"+transactionTypeLabel(item.transaction_type)+"紀錄？作廢後不會刪除歷史資料。"))return;
  try {
    await api("/transactions/"+item.id+"?family_id="+selectedFamilyId,{method:"DELETE"});
    const refreshed=await loadTransactions();
    await loadAccounts();
    notice("transaction-notice",refreshed?"收支紀錄已作廢，歷史資料仍會保留。":"已完成作廢，但收支清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("transaction-notice",error.message,"error");
  }
}


// --------------------------------------------------
// G-02-04：帳戶轉帳管理
// --------------------------------------------------
let editingTransferId = null;
let transferRows = [];
let transferAccounts = [];

function transferDateInput(value) {
  if (!value) return localDateString();
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return localDateString();
  return date.getFullYear()+"-"+String(date.getMonth()+1).padStart(2,"0")+"-"+String(date.getDate()).padStart(2,"0");
}

function transferDateTime(value) {
  return value ? value+"T12:00:00+08:00" : "";
}

function transferFilterDateTime(value, endOfDay=false) {
  return value ? value+(endOfDay?"T23:59:59+08:00":"T00:00:00+08:00") : "";
}

function transferAccountLabel(account) {
  return account.name+" · "+account.currency_code;
}

function transferEligibleAccounts() {
  return transferAccounts.filter(account=>account.is_active!==false);
}

function populateTransferAccountSelects(preferred={}) {
  const eligible=transferEligibleAccounts();
  const from=$("transfer-from-account");
  const to=$("transfer-to-account");
  const fee=$("transfer-fee-account");
  const filter=$("transfer-filter-account");
  const previous={from:preferred.from??from.value,to:preferred.to??to.value,fee:preferred.fee??fee.value,filter:filter.value};
  from.replaceChildren();
  to.replaceChildren();
  fee.replaceChildren(new Option("不指定（無手續費時）",""));
  filter.replaceChildren(new Option("全部帳戶",""));
  for(const account of eligible) {
    const label=transferAccountLabel(account);
    from.add(new Option(label,String(account.id)));
    filter.add(new Option(label,String(account.id)));
  }
  const source=eligible.find(account=>account.id===Number(previous.from))||eligible[0]||null;
  if(source)from.value=String(source.id);
  const currency=source?.currency_code;
  for(const account of eligible.filter(item=>item.currency_code===currency)) {
    to.add(new Option(transferAccountLabel(account),String(account.id)));
    fee.add(new Option(transferAccountLabel(account),String(account.id)));
  }
  if(previous.to && [...to.options].some(option=>option.value===String(previous.to)))to.value=String(previous.to);
  if(previous.fee && [...fee.options].some(option=>option.value===String(previous.fee)))fee.value=String(previous.fee);
  if(previous.filter && [...filter.options].some(option=>option.value===String(previous.filter)))filter.value=String(previous.filter);
  updateTransferCurrencyHint();
}

function updateTransferCurrencyHint() {
  const source=transferAccounts.find(account=>account.id===Number($("transfer-from-account").value));
  $("transfer-currency-hint").textContent=source
    ?"轉帳幣別："+source.currency_code+"。轉入帳戶與手續費扣款帳戶必須使用相同幣別。"
    :"請先建立至少兩個啟用中的同幣別帳戶。";
}

async function loadTransferSupportData() {
  const result=await api("/accounts?family_id="+selectedFamilyId);
  transferAccounts=result.accounts||[];
  populateTransferAccountSelects();
}

function transferQuery() {
  const params=new URLSearchParams({family_id:String(selectedFamilyId),limit:"200"});
  const account=$("transfer-filter-account").value;
  const start=$("transfer-filter-start").value;
  const end=$("transfer-filter-end").value;
  if(account)params.set("account_id",account);
  if(start)params.set("start_date",transferFilterDateTime(start));
  if(end)params.set("end_date",transferFilterDateTime(end,true));
  if($("transfer-include-voided").checked)params.set("include_voided","true");
  return params.toString();
}

function renderTransfers() {
  const list=$("transfers-list");
  list.replaceChildren();
  $("transfers-count").textContent=transferRows.length+" 筆轉帳";
  $("transfers-empty").classList.toggle("hidden",transferRows.length!==0);
  for(const item of transferRows) {
    const from=transferAccounts.find(account=>account.id===item.from_account_id);
    const to=transferAccounts.find(account=>account.id===item.to_account_id);
    const feeAccount=transferAccounts.find(account=>account.id===item.fee_account_id);
    const card=document.createElement("article");
    card.className="transaction-card"+(item.is_voided?" transaction-voided":"");
    const top=document.createElement("div");
    top.className="transaction-card-top";
    const main=document.createElement("div");
    const title=document.createElement("strong");
    title.textContent=item.description||"帳戶轉帳";
    const meta=document.createElement("p");
    meta.className="muted tiny";
    meta.textContent=[transferDateInput(item.transfer_date),(from?.name||"帳戶 #"+item.from_account_id)+" → "+(to?.name||"帳戶 #"+item.to_account_id)].join(" · ");
    main.append(title,meta);
    const amount=document.createElement("strong");
    amount.className="transaction-amount";
    amount.textContent=money(item.amount,item.currency_code);
    top.append(main,amount);
    card.append(top);
    const details=document.createElement("p");
    details.className="tiny muted";
    details.textContent="手續費："+money(item.fee_amount||0,item.currency_code)+(Number(item.fee_amount||0)>0?" · 扣款帳戶："+(feeAccount?.name||"帳戶 #"+item.fee_account_id):"");
    card.append(details);
    if(item.is_voided) {
      const status=document.createElement("span");
      status.className="transaction-status";
      status.textContent="已作廢";
      card.append(status);
    } else {
      const actions=document.createElement("div");
      actions.className="account-actions";
      const edit=document.createElement("button");
      edit.type="button";edit.className="secondary small";edit.textContent="修改";
      edit.addEventListener("click",()=>startEditTransfer(item));
      const voidButton=document.createElement("button");
      voidButton.type="button";voidButton.className="danger small";voidButton.textContent="作廢";
      voidButton.addEventListener("click",()=>voidTransfer(item));
      actions.append(edit,voidButton);
      card.append(actions);
    }
    list.append(card);
  }
}

async function loadTransfers() {
  if(!selectedFamilyId)return false;
  clearNotice("transfer-notice");
  $("transfers-loading").classList.remove("hidden");
  try {
    const result=await api("/transfers?"+transferQuery());
    transferRows=result.transfers||[];
    renderTransfers();
    return true;
  } catch(error) {
    notice("transfer-notice","轉帳紀錄載入失敗："+error.message,"error");
    return false;
  } finally {
    $("transfers-loading").classList.add("hidden");
  }
}

async function showTransfers() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理轉帳。","error");return;}
  $("transfers-view").classList.remove("hidden");
  $("transfers-view").scrollIntoView({behavior:"smooth",block:"start"});
  try {
    await loadTransferSupportData();
    await loadTransfers();
  } catch(error) {
    notice("transfer-notice","轉帳管理初始化失敗："+error.message,"error");
  }
}

function resetTransferForm() {
  editingTransferId=null;
  $("transfer-form").reset();
  $("transfer-form-title").textContent="新增轉帳";
  $("transfer-submit").textContent="新增轉帳";
  $("transfer-date").value=localDateString();
  $("transfer-fee-amount").value="0";
  $("transfer-form-panel").classList.add("hidden");
  populateTransferAccountSelects();
}

function startEditTransfer(item) {
  editingTransferId=item.id;
  $("transfer-form-title").textContent="修改轉帳";
  $("transfer-submit").textContent="儲存修改";
  populateTransferAccountSelects({from:item.from_account_id,to:item.to_account_id,fee:item.fee_account_id});
  $("transfer-from-account").value=String(item.from_account_id);
  populateTransferAccountSelects({from:item.from_account_id,to:item.to_account_id,fee:item.fee_account_id});
  $("transfer-to-account").value=String(item.to_account_id);
  $("transfer-amount").value=item.amount;
  $("transfer-date").value=transferDateInput(item.transfer_date);
  $("transfer-fee-amount").value=item.fee_amount||0;
  $("transfer-fee-account").value=item.fee_account_id?String(item.fee_account_id):"";
  $("transfer-description").value=item.description||"";
  $("transfer-note").value=item.note||"";
  $("transfer-form-panel").classList.remove("hidden");
  $("transfer-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
}

$("open-transfers").addEventListener("click",showTransfers);
$("close-transfers").addEventListener("click",()=>{
  $("transfers-view").classList.add("hidden");
  resetTransferForm();
});
$("add-transfer-button").addEventListener("click",()=>{
  resetTransferForm();
  if(transferEligibleAccounts().length<2){notice("transfer-notice","請先建立至少兩個啟用中的同幣別帳戶。","error");return;}
  $("transfer-form-panel").classList.remove("hidden");
  $("transfer-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
});
$("transfer-cancel").addEventListener("click",resetTransferForm);
$("transfer-from-account").addEventListener("change",()=>{
  const from=$("transfer-from-account").value;
  populateTransferAccountSelects({from,to:"",fee:""});
});
$("transfer-fee-amount").addEventListener("input",()=>{
  if(Number($("transfer-fee-amount").value||0)<=0)$("transfer-fee-account").value="";
});
$("apply-transfer-filters").addEventListener("click",loadTransfers);
$("transfer-filter-account").addEventListener("change",loadTransfers);
$("transfer-include-voided").addEventListener("change",loadTransfers);
$("transfer-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const button=$("transfer-submit");
  button.disabled=true;
  clearNotice("transfer-notice");
  try {
    const from=transferAccounts.find(account=>account.id===Number($("transfer-from-account").value));
    const to=transferAccounts.find(account=>account.id===Number($("transfer-to-account").value));
    const fee=Number($("transfer-fee-amount").value||0);
    const feeAccountId=$("transfer-fee-account").value;
    if(!from||!to)throw new Error("請選擇有效的轉出與轉入帳戶。");
    if(from.id===to.id)throw new Error("轉出帳戶與轉入帳戶不可相同。");
    if(from.currency_code!==to.currency_code)throw new Error("轉出與轉入帳戶幣別必須相同。");
    if(fee>0&&!feeAccountId)throw new Error("有手續費時必須指定扣款帳戶。");
    const feeAccount=feeAccountId?transferAccounts.find(account=>account.id===Number(feeAccountId)):null;
    if(fee>0&&(!feeAccount||feeAccount.currency_code!==from.currency_code))throw new Error("手續費扣款帳戶幣別必須與轉帳一致。");
    const payload={
      from_account_id:from.id,
      to_account_id:to.id,
      amount:$("transfer-amount").value,
      currency_code:from.currency_code,
      transfer_date:transferDateTime($("transfer-date").value),
      description:$("transfer-description").value.trim(),
      fee_amount:String(fee),
      fee_account_id:fee>0?Number(feeAccountId):null,
      note:$("transfer-note").value.trim()||null
    };
    const wasEditing=Boolean(editingTransferId);
    if(wasEditing)await api("/transfers/"+editingTransferId+"?family_id="+selectedFamilyId,{method:"PATCH",body:JSON.stringify(payload)});
    else await api("/transfers?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
    resetTransferForm();
    const refreshed=await loadTransfers();
    await loadAccounts();
    notice("transfer-notice",refreshed?(wasEditing?"轉帳紀錄已更新，兩端交易明細已同步。":"轉帳已新增，兩端交易明細已建立。"):"資料已儲存，但轉帳清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("transfer-notice",error.message,"error");
  } finally {
    button.disabled=false;
  }
});

async function voidTransfer(item) {
  if(!window.confirm("確定要作廢這筆帳戶轉帳？系統會一併作廢轉出、轉入及手續費交易，並保留歷史資料。"))return;
  try {
    await api("/transfers/"+item.id+"?family_id="+selectedFamilyId,{method:"DELETE"});
    const refreshed=await loadTransfers();
    await loadAccounts();
    notice("transfer-notice",refreshed?"轉帳及相關交易已作廢，歷史資料仍會保留。":"已完成作廢，但轉帳清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("transfer-notice",error.message,"error");
  }
}


// --------------------------------------------------
// G-02-05：信用卡繳款管理
// --------------------------------------------------
let editingCreditCardPaymentId = null;
let creditCardPaymentRows = [];
let creditCardPaymentAccounts = [];

function paymentDateInput(value) {
  if (!value) return localDateString();
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return localDateString();
  return date.getFullYear()+"-"+String(date.getMonth()+1).padStart(2,"0")+"-"+String(date.getDate()).padStart(2,"0");
}

function paymentDateTime(value, endOfDay=false) {
  return value ? value+(endOfDay ? "T23:59:59+08:00" : "T12:00:00+08:00") : "";
}

function paymentAccountLabel(account) {
  return account.name+" · "+account.currency_code;
}

function paymentSourceAccounts() {
  return creditCardPaymentAccounts.filter(account=>["bank","cash","e_wallet"].includes(account.account_type)&&account.is_active!==false);
}

function paymentCardAccounts() {
  return creditCardPaymentAccounts.filter(account=>account.account_type==="credit_card"&&account.is_active!==false);
}

function populateCreditCardPaymentAccounts(preferred={}) {
  const source=$("credit-payment-source");
  const card=$("credit-payment-card");
  const filter=$("credit-payment-filter-account");
  const previous={source:preferred.source??source.value,card:preferred.card??card.value,filter:filter.value};
  source.replaceChildren();
  card.replaceChildren();
  filter.replaceChildren(new Option("全部帳戶",""));
  for(const account of creditCardPaymentAccounts) filter.add(new Option(paymentAccountLabel(account),String(account.id)));
  for(const account of paymentSourceAccounts()) source.add(new Option(paymentAccountLabel(account),String(account.id)));
  for(const account of paymentCardAccounts()) card.add(new Option(paymentAccountLabel(account),String(account.id)));
  if(previous.source&&[...source.options].some(option=>option.value===String(previous.source)))source.value=String(previous.source);
  if(previous.card&&[...card.options].some(option=>option.value===String(previous.card)))card.value=String(previous.card);
  if(previous.filter&&[...filter.options].some(option=>option.value===String(previous.filter)))filter.value=String(previous.filter);
  updateCreditPaymentCurrencyHint();
}

function updateCreditPaymentCurrencyHint() {
  const source=creditCardPaymentAccounts.find(account=>account.id===Number($("credit-payment-source").value));
  const card=creditCardPaymentAccounts.find(account=>account.id===Number($("credit-payment-card").value));
  $("credit-payment-currency-hint").textContent=source&&card
    ? "繳款幣別："+source.currency_code+"。來源帳戶與信用卡帳戶必須使用相同幣別。"
    : "請先建立可扣款的銀行／現金／電子支付帳戶，以及信用卡帳戶。";
}

async function loadCreditCardPaymentSupportData() {
  const result=await api("/accounts?family_id="+selectedFamilyId);
  creditCardPaymentAccounts=result.accounts||[];
  populateCreditCardPaymentAccounts();
}

function creditCardPaymentQuery() {
  const params=new URLSearchParams({family_id:String(selectedFamilyId),limit:"200"});
  const account=$("credit-payment-filter-account").value;
  const start=$("credit-payment-filter-start").value;
  const end=$("credit-payment-filter-end").value;
  if(account)params.set("account_id",account);
  if(start)params.set("start_date",paymentDateTime(start));
  if(end)params.set("end_date",paymentDateTime(end,true));
  if($("credit-payment-include-voided").checked)params.set("include_voided","true");
  return params.toString();
}

function renderCreditCardPayments() {
  const list=$("credit-card-payments-list");
  list.replaceChildren();
  $("credit-card-payments-count").textContent=creditCardPaymentRows.length+" 筆繳款";
  $("credit-card-payments-empty").classList.toggle("hidden",creditCardPaymentRows.length!==0);
  for(const item of creditCardPaymentRows) {
    const source=creditCardPaymentAccounts.find(account=>account.id===item.from_account_id);
    const cardAccount=creditCardPaymentAccounts.find(account=>account.id===item.credit_card_account_id);
    const card=document.createElement("article");
    card.className="transaction-card"+(item.is_voided?" transaction-voided":"");
    const top=document.createElement("div");
    top.className="transaction-card-top";
    const main=document.createElement("div");
    const title=document.createElement("strong");
    title.textContent=item.description||"信用卡繳款";
    const meta=document.createElement("p");
    meta.className="muted tiny";
    meta.textContent=[paymentDateInput(item.payment_date),(source?.name||"來源帳戶 #"+item.from_account_id)+" → "+(cardAccount?.name||"信用卡 #"+item.credit_card_account_id)].join(" · ");
    main.append(title,meta);
    const amount=document.createElement("strong");
    amount.className="transaction-amount expense";
    amount.textContent=money(item.amount,item.currency_code);
    top.append(main,amount);
    card.append(top);
    if(item.note) {
      const note=document.createElement("p");
      note.className="tiny muted transfer-card-details";
      note.textContent="備註："+item.note;
      card.append(note);
    }
    if(item.is_voided) {
      const status=document.createElement("span");
      status.className="transaction-status";
      status.textContent="已作廢";
      card.append(status);
    } else {
      const actions=document.createElement("div");
      actions.className="account-actions";
      const edit=document.createElement("button");
      edit.type="button";edit.className="secondary small";edit.textContent="修改";
      edit.addEventListener("click",()=>startEditCreditCardPayment(item));
      const voidButton=document.createElement("button");
      voidButton.type="button";voidButton.className="danger small";voidButton.textContent="作廢";
      voidButton.addEventListener("click",()=>voidCreditCardPayment(item));
      actions.append(edit,voidButton);
      card.append(actions);
    }
    list.append(card);
  }
}

async function loadCreditCardPayments() {
  if(!selectedFamilyId)return false;
  clearNotice("credit-payment-notice");
  $("credit-card-payments-loading").classList.remove("hidden");
  try {
    const result=await api("/credit-card-payments?"+creditCardPaymentQuery());
    creditCardPaymentRows=result.payments||[];
    renderCreditCardPayments();
    return true;
  } catch(error) {
    notice("credit-payment-notice","信用卡繳款清單載入失敗："+error.message,"error");
    return false;
  } finally {
    $("credit-card-payments-loading").classList.add("hidden");
  }
}

async function showCreditCardPayments() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理信用卡繳款。","error");return;}
  $("credit-card-payments-view").classList.remove("hidden");
  $("credit-card-payments-view").scrollIntoView({behavior:"smooth",block:"start"});
  try {
    await loadCreditCardPaymentSupportData();
    await loadCreditCardPayments();
  } catch(error) {
    notice("credit-payment-notice","信用卡繳款管理初始化失敗："+error.message,"error");
  }
}

function resetCreditCardPaymentForm() {
  editingCreditCardPaymentId=null;
  $("credit-payment-form").reset();
  $("credit-payment-form-title").textContent="新增信用卡繳款";
  $("credit-payment-submit").textContent="新增繳款";
  $("credit-payment-source").disabled=false;
  $("credit-payment-card").disabled=false;
  $("credit-payment-date").value=localDateString();
  $("credit-payment-form-panel").classList.add("hidden");
  populateCreditCardPaymentAccounts();
}

function startEditCreditCardPayment(item) {
  editingCreditCardPaymentId=item.id;
  $("credit-payment-form-title").textContent="修改信用卡繳款";
  $("credit-payment-submit").textContent="儲存修改";
  populateCreditCardPaymentAccounts({source:item.from_account_id,card:item.credit_card_account_id});
  $("credit-payment-source").value=String(item.from_account_id);
  $("credit-payment-card").value=String(item.credit_card_account_id);
  $("credit-payment-source").disabled=true;
  $("credit-payment-card").disabled=true;
  $("credit-payment-amount").value=item.amount;
  $("credit-payment-date").value=paymentDateInput(item.payment_date);
  $("credit-payment-description").value=item.description||"";
  $("credit-payment-note").value=item.note||"";
  $("credit-payment-form-panel").classList.remove("hidden");
  $("credit-payment-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
}

$("open-credit-card-payments").addEventListener("click",showCreditCardPayments);
$("close-credit-card-payments").addEventListener("click",()=>{
  $("credit-card-payments-view").classList.add("hidden");
  resetCreditCardPaymentForm();
});
$("add-credit-payment-button").addEventListener("click",()=>{
  resetCreditCardPaymentForm();
  if(!paymentSourceAccounts().length||!paymentCardAccounts().length) {
    notice("credit-payment-notice","請先建立至少一個銀行／現金／電子支付帳戶及一個信用卡帳戶。","error");
    return;
  }
  $("credit-payment-form-panel").classList.remove("hidden");
  $("credit-payment-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
});
$("credit-payment-cancel").addEventListener("click",resetCreditCardPaymentForm);
$("credit-payment-source").addEventListener("change",updateCreditPaymentCurrencyHint);
$("credit-payment-card").addEventListener("change",updateCreditPaymentCurrencyHint);
$("apply-credit-payment-filters").addEventListener("click",loadCreditCardPayments);
$("credit-payment-filter-account").addEventListener("change",loadCreditCardPayments);
$("credit-payment-include-voided").addEventListener("change",loadCreditCardPayments);
$("credit-payment-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const button=$("credit-payment-submit");
  button.disabled=true;
  clearNotice("credit-payment-notice");
  try {
    const source=creditCardPaymentAccounts.find(account=>account.id===Number($("credit-payment-source").value));
    const card=creditCardPaymentAccounts.find(account=>account.id===Number($("credit-payment-card").value));
    if(!source||!card)throw new Error("請選擇有效的扣款帳戶及信用卡帳戶。");
    if(source.id===card.id)throw new Error("扣款帳戶不可與信用卡帳戶相同。");
    if(source.currency_code!==card.currency_code)throw new Error("扣款帳戶與信用卡帳戶幣別必須相同。");
    const wasEditing=Boolean(editingCreditCardPaymentId);
    const payload={
      amount:$("credit-payment-amount").value,
      payment_date:paymentDateTime($("credit-payment-date").value),
      description:$("credit-payment-description").value.trim()||null,
      note:$("credit-payment-note").value.trim()||null
    };
    if(wasEditing) {
      await api("/credit-card-payments/"+editingCreditCardPaymentId+"?family_id="+selectedFamilyId,{method:"PATCH",body:JSON.stringify(payload)});
    } else {
      payload.from_account_id=source.id;
      payload.credit_card_account_id=card.id;
      payload.currency_code=source.currency_code;
      await api("/credit-card-payments?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
    }
    resetCreditCardPaymentForm();
    const refreshed=await loadCreditCardPayments();
    await loadAccounts();
    notice("credit-payment-notice",refreshed?(wasEditing?"信用卡繳款已更新，來源帳戶與信用卡交易明細已同步。":"信用卡繳款已新增，系統已同步兩端帳戶交易。"):"資料已儲存，但清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("credit-payment-notice",error.message,"error");
  } finally {
    button.disabled=false;
  }
});

async function voidCreditCardPayment(item) {
  if(!window.confirm("確定要作廢這筆信用卡繳款？系統會一併作廢來源帳戶及信用卡交易，並保留歷史紀錄。"))return;
  try {
    await api("/credit-card-payments/"+item.id+"?family_id="+selectedFamilyId,{method:"DELETE"});
    const refreshed=await loadCreditCardPayments();
    await loadAccounts();
    notice("credit-payment-notice",refreshed?"信用卡繳款及相關交易已作廢，歷史資料仍會保留。":"已完成作廢，但清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("credit-payment-notice",error.message,"error");
  }
}


// --------------------------------------------------
// G-02-06：家庭帳單管理
// --------------------------------------------------
let billRows=[];
let billCategories=[];
let editingBillId=null;
let editingBillPaymentHistory=false;

function billDateInput(value) {
  if(!value)return "";
  return String(value).slice(0,10);
}

function billStatusLabel(status) {
  return ({unpaid:"未繳",partially_paid:"部分付款",paid:"已繳清",overdue:"已逾期",voided:"已作廢"})[status]||status;
}

function billStatusClass(status) {
  return status==="paid"?"bill-status-paid":status==="overdue"?"bill-status-overdue":status==="voided"?"bill-status-voided":"bill-status-open";
}

function billTotalValue(item) {
  return Number(item.original_amount||0)+Number(item.tax_amount||0)-Number(item.discount_amount||0);
}

function populateBillCategories(selectedId=null) {
  const select=$("bill-category");
  select.replaceChildren(new Option("未指定分類",""));
  for(const category of billCategories)select.add(new Option(category.name,String(category.id)));
  if(selectedId!==null&&selectedId!==undefined) {
    if(!billCategories.some(item=>item.id===Number(selectedId)))select.add(new Option("既有分類 #"+selectedId,String(selectedId)));
    select.value=String(selectedId);
  }
}

async function loadBillSupportData() {
  const result=await api("/categories?family_id="+selectedFamilyId+"&category_type=expense").catch(()=>({categories:[]}));
  billCategories=(result.categories||[]).filter(item=>item.is_active!==false);
  populateBillCategories();
}

function billQuery() {
  const params=new URLSearchParams({family_id:String(selectedFamilyId),limit:"200"});
  const start=$("bill-filter-start").value;
  const end=$("bill-filter-end").value;
  if(start)params.set("start_date",start);
  if(end)params.set("end_date",end);
  if($("bill-include-voided").checked)params.set("include_voided","true");
  return params.toString();
}

function renderBills() {
  const list=$("bills-list");
  list.replaceChildren();
  $("bills-count").textContent=billRows.length+" 張帳單";
  $("bills-empty").classList.toggle("hidden",billRows.length!==0);
  for(const item of billRows) {
    const category=billCategories.find(row=>row.id===item.category_id);
    const card=document.createElement("article");
    card.className="bill-card"+(item.is_voided?" bill-card-voided":"");
    const top=document.createElement("div");
    top.className="bill-card-top";
    const main=document.createElement("div");
    const title=document.createElement("strong");
    title.textContent=item.title;
    const meta=document.createElement("p");
    meta.className="muted tiny";
    meta.textContent=[item.bill_number?"帳單編號 "+item.bill_number:null,"帳單日 "+billDateInput(item.bill_date),item.due_date?"到期 "+billDateInput(item.due_date):null,category?.name||"未分類"].filter(Boolean).join(" · ");
    main.append(title,meta);
    const amountWrap=document.createElement("div");
    amountWrap.className="bill-amount-wrap";
    const total=document.createElement("strong");
    total.className="bill-total";
    total.textContent=money(item.total_amount,item.currency_code);
    const remaining=document.createElement("span");
    remaining.className="tiny muted";
    remaining.textContent=item.status==="voided"?"已作廢":"未付 "+money(item.remaining_amount,item.currency_code);
    amountWrap.append(total,remaining);
    top.append(main,amountWrap);
    card.append(top);
    const detail=document.createElement("div");
    detail.className="bill-card-details";
    const paid=document.createElement("span");
    paid.textContent="已付 "+money(item.paid_amount,item.currency_code);
    const status=document.createElement("span");
    status.className="bill-status "+billStatusClass(item.status);
    status.textContent=billStatusLabel(item.status);
    detail.append(paid,status);
    card.append(detail);
    if(item.note) {
      const note=document.createElement("p");
      note.className="tiny muted";
      note.textContent="備註："+item.note;
      card.append(note);
    }
    if(item.is_voided) {
      if(item.void_reason) {
        const reason=document.createElement("p");
        reason.className="tiny muted";
        reason.textContent="作廢原因："+item.void_reason;
        card.append(reason);
      }
    } else {
      const actions=document.createElement("div");
      actions.className="account-actions";
      const payments=document.createElement("button");
      payments.type="button";payments.className="secondary small";payments.textContent="付款／退款";
      payments.addEventListener("click",()=>showBillPayments(item));
      const edit=document.createElement("button");
      edit.type="button";edit.className="secondary small";edit.textContent="修改";
      edit.addEventListener("click",()=>startEditBill(item));
      const voidButton=document.createElement("button");
      voidButton.type="button";voidButton.className="danger small";voidButton.textContent="作廢";
      voidButton.addEventListener("click",()=>voidBill(item));
      actions.append(payments,edit,voidButton);
      card.append(actions);
    }
    list.append(card);
  }
}

async function loadBills() {
  if(!selectedFamilyId)return false;
  clearNotice("bill-notice");
  $("bills-loading").classList.remove("hidden");
  try {
    const result=await api("/bills?"+billQuery());
    billRows=result.bills||[];
    renderBills();
    return true;
  } catch(error) {
    notice("bill-notice","帳單清單載入失敗："+error.message,"error");
    return false;
  } finally {
    $("bills-loading").classList.add("hidden");
  }
}

async function showBills() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理帳單。","error");return;}
  $("bills-view").classList.remove("hidden");
  $("bills-view").scrollIntoView({behavior:"smooth",block:"start"});
  try {
    await loadBillSupportData();
    await loadBills();
  } catch(error) {
    notice("bill-notice","帳單管理初始化失敗："+error.message,"error");
  }
}

function resetBillForm() {
  editingBillId=null;
  editingBillPaymentHistory=false;
  $("bill-form").reset();
  $("bill-form-title").textContent="新增帳單";
  $("bill-submit").textContent="新增帳單";
  $("bill-currency").disabled=false;
  $("bill-date").value=localDateString();
  $("bill-period-start").value="";
  $("bill-period-end").value="";
  $("bill-due-date").value="";
  $("bill-tax").value="0";
  $("bill-discount").value="0";
  $("bill-form-panel").classList.add("hidden");
  $("bill-currency-hint").textContent="若帳單已有付款／退款紀錄，幣別將無法變更。";
  populateBillCategories();
}

async function startEditBill(item) {
  editingBillId=item.id;
  editingBillPaymentHistory=true;
  $("bill-form-title").textContent="修改帳單";
  $("bill-submit").textContent="儲存修改";
  $("bill-number").value=item.bill_number||"";
  $("bill-title").value=item.title;
  $("bill-category").value=item.category_id?String(item.category_id):"";
  $("bill-date").value=billDateInput(item.bill_date);
  $("bill-period-start").value=billDateInput(item.billing_period_start);
  $("bill-period-end").value=billDateInput(item.billing_period_end);
  $("bill-due-date").value=billDateInput(item.due_date);
  $("bill-original-amount").value=item.original_amount;
  $("bill-tax").value=item.tax_amount||0;
  $("bill-discount").value=item.discount_amount||0;
  $("bill-currency").value=item.currency_code;
  $("bill-currency").disabled=editingBillPaymentHistory;
  $("bill-note").value=item.note||"";
  populateBillCategories(item.category_id);
  $("bill-currency-hint").textContent="正在確認付款／退款歷史…";
  $("bill-form-panel").classList.remove("hidden");
  $("bill-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
  try {
    const history=await api("/bill-payments?family_id="+selectedFamilyId+"&bill_id="+item.id+"&include_voided=true&limit=200");
    editingBillPaymentHistory=(history.payments||[]).length>0;
    $("bill-currency").disabled=editingBillPaymentHistory;
    $("bill-currency-hint").textContent=editingBillPaymentHistory?"此帳單已有付款／退款歷史，為避免幣別與歷史交易不一致，幣別已鎖定。":"目前沒有付款／退款歷史，可修改帳單幣別。";
  } catch(error) {
    editingBillPaymentHistory=true;
    $("bill-currency").disabled=true;
    $("bill-currency-hint").textContent="無法確認付款／退款歷史，為避免幣別與既有交易不一致，暫時鎖定幣別。";
  }
}

$("open-bills").addEventListener("click",showBills);
$("close-bills").addEventListener("click",()=>{
  $("bills-view").classList.add("hidden");
  resetBillForm();
});
$("add-bill-button").addEventListener("click",()=>{
  resetBillForm();
  $("bill-form-panel").classList.remove("hidden");
  $("bill-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
});
$("bill-cancel").addEventListener("click",resetBillForm);
$("apply-bill-filters").addEventListener("click",loadBills);
$("bill-include-voided").addEventListener("change",loadBills);
$("bill-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const button=$("bill-submit");
  button.disabled=true;
  clearNotice("bill-notice");
  try {
    const original=Number($("bill-original-amount").value);
    const tax=Number($("bill-tax").value||0);
    const discount=Number($("bill-discount").value||0);
    if(!(original>0)||tax<0||discount<0)throw new Error("金額格式不正確，原始金額必須大於 0，稅額與折扣不可小於 0。");
    if(original+tax-discount<0)throw new Error("折扣金額不可大於原始金額加稅額。");
    const periodStart=$("bill-period-start").value;
    const periodEnd=$("bill-period-end").value;
    if(Boolean(periodStart)!==Boolean(periodEnd))throw new Error("帳單期間起日與迄日必須同時填寫。");
    if(periodStart&&periodEnd&&periodStart>periodEnd)throw new Error("帳單期間起日不可晚於迄日。");
    const payload={
      bill_number:$("bill-number").value.trim()||null,
      title:$("bill-title").value.trim(),
      category_id:$("bill-category").value?Number($("bill-category").value):null,
      bill_date:$("bill-date").value,
      billing_period_start:periodStart||null,
      billing_period_end:periodEnd||null,
      due_date:$("bill-due-date").value||null,
      original_amount:$("bill-original-amount").value,
      tax_amount:$("bill-tax").value||"0",
      discount_amount:$("bill-discount").value||"0",
      currency_code:$("bill-currency").value.trim().toUpperCase(),
      note:$("bill-note").value.trim()||null
    };
    const wasEditing=Boolean(editingBillId);
    if(wasEditing) {
      await api("/bills/"+editingBillId+"?family_id="+selectedFamilyId,{method:"PATCH",body:JSON.stringify(payload)});
    } else {
      await api("/bills?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
    }
    resetBillForm();
    const refreshed=await loadBills();
    notice("bill-notice",refreshed?(wasEditing?"帳單已更新。":"帳單已新增。"):"帳單已儲存，但清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("bill-notice",error.message,"error");
  } finally {
    button.disabled=false;
  }
});

async function voidBill(item) {
  const reason=window.prompt("請輸入作廢原因（可留空）：","");
  if(reason===null)return;
  if(!window.confirm("確定作廢「"+item.title+"」？若仍有有效付款／退款紀錄，系統會拒絕作廢，需先處理付款紀錄。"))return;
  try {
    const params=new URLSearchParams({family_id:String(selectedFamilyId)});
    if(reason.trim())params.set("reason",reason.trim());
    await api("/bills/"+item.id+"?"+params.toString(),{method:"DELETE"});
    const refreshed=await loadBills();
    notice("bill-notice",refreshed?"帳單已作廢，歷史資料已保留。":"帳單已作廢，但清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("bill-notice",error.message,"error");
  }
}


// --------------------------------------------------
// G-02-07：帳單付款與退款管理
// --------------------------------------------------
let activeBillForPayments=null;
let billPaymentRows=[];
let billPaymentAccounts=[];
let billPaymentMode="payment";
let billPaymentOriginalId=null;

function billPaymentAccountLabel(account) {
  return account.name+" · "+account.currency_code;
}

function populateBillPaymentAccounts(preferredId=null) {
  const select=$("bill-payment-account");
  select.replaceChildren();
  const active=billPaymentAccounts.filter(account=>account.is_active!==false);
  for(const account of active)select.add(new Option(billPaymentAccountLabel(account),String(account.id)));
  if(preferredId&&active.some(account=>account.id===Number(preferredId)))select.value=String(preferredId);
}

async function loadBillPaymentSupportData(preferredId=null) {
  const result=await api("/accounts?family_id="+selectedFamilyId);
  billPaymentAccounts=result.accounts||[];
  populateBillPaymentAccounts(preferredId);
}

function billPaymentRefundable(payment) {
  const refunded=billPaymentRows.filter(row=>row.payment_type==="refund"&&row.original_payment_id===payment.id&&!row.is_voided)
    .reduce((sum,row)=>sum+Number(row.amount||0),0);
  return Math.max(Number(payment.amount||0)-refunded,0);
}

function hasActiveBillPaymentRefund(payment) {
  return billPaymentRows.some(row=>row.payment_type==="refund"&&row.original_payment_id===payment.id&&!row.is_voided);
}

function renderBillPayments() {
  const list=$("bill-payments-list");
  list.replaceChildren();
  $("bill-payments-count").textContent=billPaymentRows.length+" 筆付款／退款";
  $("bill-payments-empty").classList.toggle("hidden",billPaymentRows.length!==0);
  for(const item of billPaymentRows) {
    const account=billPaymentAccounts.find(row=>row.id===item.account_id);
    const isRefund=item.payment_type==="refund";
    const card=document.createElement("article");
    card.className="bill-payment-card"+(item.is_voided?" bill-payment-voided":"");
    const top=document.createElement("div");
    top.className="bill-payment-top";
    const main=document.createElement("div");
    const title=document.createElement("strong");
    title.textContent=isRefund?"帳單退款":"帳單付款";
    const meta=document.createElement("p");
    meta.className="muted tiny";
    meta.textContent=[billDateInput(item.payment_date),account?.name||"帳戶 #"+item.account_id,isRefund?"原付款 #"+item.original_payment_id:null].filter(Boolean).join(" · ");
    main.append(title,meta);
    const amount=document.createElement("strong");
    amount.className="bill-payment-amount "+(isRefund?"income":"expense");
    amount.textContent=(isRefund?"+":"−")+money(item.amount,item.currency_code);
    top.append(main,amount);
    card.append(top);
    if(item.description) {
      const description=document.createElement("p");
      description.className="tiny muted";
      description.textContent=item.description;
      card.append(description);
    }
    if(item.note) {
      const note=document.createElement("p");
      note.className="tiny muted";
      note.textContent="備註："+item.note;
      card.append(note);
    }
    if(item.is_voided) {
      const status=document.createElement("span");
      status.className="bill-status bill-status-voided";
      status.textContent="已作廢";
      card.append(status);
      if(item.void_reason) {
        const reason=document.createElement("p");
        reason.className="tiny muted";
        reason.textContent="作廢原因："+item.void_reason;
        card.append(reason);
      }
    } else {
      const actions=document.createElement("div");
      actions.className="account-actions";
      if(!isRefund&&billPaymentRefundable(item)>0) {
        const refund=document.createElement("button");
        refund.type="button";refund.className="secondary small";
        refund.textContent="建立退款（可退 "+money(billPaymentRefundable(item),item.currency_code)+"）";
        refund.addEventListener("click",()=>startBillRefund(item));
        actions.append(refund);
      }
      const voidButton=document.createElement("button");
      voidButton.type="button";voidButton.className="danger small";voidButton.textContent="作廢";
      const blocked=!isRefund&&hasActiveBillPaymentRefund(item);
      voidButton.disabled=blocked;
      if(blocked)voidButton.title="此付款已有有效退款，請先作廢退款紀錄";
      voidButton.addEventListener("click",()=>voidBillPayment(item));
      actions.append(voidButton);
      card.append(actions);
    }
    list.append(card);
  }
}

async function loadBillPayments() {
  if(!activeBillForPayments)return false;
  clearNotice("bill-payment-notice");
  $("bill-payments-loading").classList.remove("hidden");
  try {
    const params=new URLSearchParams({family_id:String(selectedFamilyId),bill_id:String(activeBillForPayments.id),limit:"200"});
    if($("bill-payment-include-voided").checked)params.set("include_voided","true");
    const result=await api("/bill-payments?"+params.toString());
    billPaymentRows=result.payments||[];
    renderBillPayments();
    return true;
  } catch(error) {
    notice("bill-payment-notice","付款／退款紀錄載入失敗："+error.message,"error");
    return false;
  } finally {
    $("bill-payments-loading").classList.add("hidden");
  }
}

async function showBillPayments(item) {
  if(!selectedFamilyId||!item)return;
  activeBillForPayments=item;
  $("bill-payments-view").classList.remove("hidden");
  $("bill-payments-title").textContent="帳單付款／退款："+item.title;
  $("bill-payments-summary").textContent="應繳 "+money(item.total_amount,item.currency_code)+" · 已付 "+money(item.paid_amount,item.currency_code)+" · 未付 "+money(item.remaining_amount,item.currency_code);
  $("bill-payments-view").scrollIntoView({behavior:"smooth",block:"start"});
  try {
    await loadBillPaymentSupportData();
    await loadBillPayments();
  } catch(error) {
    notice("bill-payment-notice","付款／退款管理初始化失敗："+error.message,"error");
  }
}

function resetBillPaymentForm() {
  billPaymentMode="payment";
  billPaymentOriginalId=null;
  $("bill-payment-form").reset();
  $("bill-payment-date").value=localDateString();
  $("bill-payment-form-title").textContent="新增帳單付款";
  $("bill-payment-submit").textContent="確認付款";
  $("bill-payment-form-panel").classList.add("hidden");
  populateBillPaymentAccounts();
}

function startBillPaymentCreate() {
  if(!billPaymentAccounts.filter(account=>account.is_active!==false).length) {
    notice("bill-payment-notice","請先建立至少一個有效帳戶，才能記錄付款。","error");
    return;
  }
  if(!activeBillForPayments||activeBillForPayments.is_voided) {
    notice("bill-payment-notice","已作廢帳單不可新增付款。","error");
    return;
  }
  if(Number(activeBillForPayments.remaining_amount)<=0) {
    notice("bill-payment-notice","此帳單已繳清，若需退費請從原付款紀錄建立退款。","error");
    return;
  }
  billPaymentMode="payment";
  billPaymentOriginalId=null;
  $("bill-payment-form-title").textContent="新增帳單付款";
  $("bill-payment-submit").textContent="確認付款";
  $("bill-payment-amount").value="";
  $("bill-payment-date").value=localDateString();
  $("bill-payment-description").value="";
  $("bill-payment-note").value="";
  populateBillPaymentAccounts();
  $("bill-payment-form-panel").classList.remove("hidden");
  $("bill-payment-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
}

function startBillRefund(original) {
  const refundable=billPaymentRefundable(original);
  if(refundable<=0) {
    notice("bill-payment-notice","此筆付款已無可退款餘額。","error");
    return;
  }
  billPaymentMode="refund";
  billPaymentOriginalId=original.id;
  $("bill-payment-form-title").textContent="建立帳單退款（原付款 #"+original.id+"）";
  $("bill-payment-submit").textContent="確認退款";
  $("bill-payment-amount").value="";
  $("bill-payment-date").value=localDateString();
  $("bill-payment-description").value="帳單退款："+activeBillForPayments.title;
  $("bill-payment-note").value="";
  populateBillPaymentAccounts(original.account_id);
  $("bill-payment-form-panel").classList.remove("hidden");
  $("bill-payment-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
}

$("close-bill-payments").addEventListener("click",()=>{
  $("bill-payments-view").classList.add("hidden");
  resetBillPaymentForm();
  $("bills-view").scrollIntoView({behavior:"smooth",block:"start"});
});
$("add-bill-payment-button").addEventListener("click",startBillPaymentCreate);
$("bill-payment-cancel").addEventListener("click",resetBillPaymentForm);
$("bill-payment-include-voided").addEventListener("change",loadBillPayments);
$("bill-payment-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const button=$("bill-payment-submit");
  button.disabled=true;
  clearNotice("bill-payment-notice");
  try {
    if(!activeBillForPayments)throw new Error("請先選擇帳單。");
    const account=billPaymentAccounts.find(row=>row.id===Number($("bill-payment-account").value));
    if(!account||account.is_active===false)throw new Error("請選擇有效的付款帳戶。");
    if(account.currency_code!==activeBillForPayments.currency_code)throw new Error("付款帳戶幣別必須與帳單幣別一致。");
    const amount=Number($("bill-payment-amount").value);
    if(!(amount>0))throw new Error("付款／退款金額必須大於 0。");
    const payload={
      account_id:account.id,
      amount:$("bill-payment-amount").value,
      currency_code:activeBillForPayments.currency_code,
      payment_date:paymentDateTime($("bill-payment-date").value),
      description:$("bill-payment-description").value.trim()||null,
      note:$("bill-payment-note").value.trim()||null
    };
    const wasRefund=billPaymentMode==="refund";
    if(wasRefund) {
      const original=billPaymentRows.find(row=>row.id===billPaymentOriginalId&&row.payment_type==="payment");
      if(!original||original.is_voided)throw new Error("找不到有效的原始付款紀錄。");
      const refundable=billPaymentRefundable(original);
      if(amount>refundable)throw new Error("退款金額超過可退餘額："+money(refundable,original.currency_code));
      await api("/bill-payments/"+billPaymentOriginalId+"/refund?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
    } else {
      const remaining=Number(activeBillForPayments.remaining_amount||0);
      if(amount>remaining)throw new Error("付款金額超過帳單未付餘額："+money(remaining,activeBillForPayments.currency_code));
      payload.bill_id=activeBillForPayments.id;
      await api("/bill-payments?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
    }
    resetBillPaymentForm();
    const paymentsRefreshed=await loadBillPayments();
    const billsRefreshed=await loadBills();
    const updated=billsRefreshed?billRows.find(row=>row.id===activeBillForPayments.id):null;
    if(updated) {
      activeBillForPayments=updated;
      $("bill-payments-summary").textContent="應繳 "+money(updated.total_amount,updated.currency_code)+" · 已付 "+money(updated.paid_amount,updated.currency_code)+" · 未付 "+money(updated.remaining_amount,updated.currency_code);
    }
    const actionMessage=wasRefund?"退款已建立，已同步產生帳戶收入交易。":"付款已建立，已同步產生帳戶支出交易。";
    notice("bill-payment-notice",paymentsRefreshed&&billsRefreshed?actionMessage:actionMessage+" 但部分清單更新失敗，請重新整理。",paymentsRefreshed&&billsRefreshed?"success":"error");
  } catch(error) {
    notice("bill-payment-notice",error.message,"error");
  } finally {
    button.disabled=false;
  }
});

async function voidBillPayment(item) {
  if(item.payment_type==="payment"&&hasActiveBillPaymentRefund(item)) {
    notice("bill-payment-notice","此付款已有有效退款，請先作廢退款紀錄。","error");
    return;
  }
  const reason=window.prompt("請輸入作廢原因（可留空）：","");
  if(reason===null)return;
  if(!window.confirm("確定作廢這筆"+(item.payment_type==="refund"?"退款":"付款")+"？系統會一併作廢對應帳戶交易並保留歷史紀錄。"))return;
  try {
    const params=new URLSearchParams({family_id:String(selectedFamilyId)});
    if(reason.trim())params.set("reason",reason.trim());
    await api("/bill-payments/"+item.id+"?"+params.toString(),{method:"DELETE"});
    const paymentsRefreshed=await loadBillPayments();
    const billsRefreshed=await loadBills();
    const updated=billsRefreshed?billRows.find(row=>row.id===activeBillForPayments.id):null;
    if(updated) {
      activeBillForPayments=updated;
      $("bill-payments-summary").textContent="應繳 "+money(updated.total_amount,updated.currency_code)+" · 已付 "+money(updated.paid_amount,updated.currency_code)+" · 未付 "+money(updated.remaining_amount,updated.currency_code);
    }
    notice("bill-payment-notice",paymentsRefreshed&&billsRefreshed?"付款／退款紀錄及對應交易已作廢，歷史資料已保留。":"已完成作廢，但部分清單更新失敗，請重新整理。",paymentsRefreshed&&billsRefreshed?"success":"error");
  } catch(error) {
    notice("bill-payment-notice",error.message,"error");
  }
}


// --------------------------------------------------
// G-02-08：定期帳單管理
// --------------------------------------------------
let recurringBillRows=[];
let recurringBillCategories=[];
let editingRecurringBillId=null;

function recurringFrequencyLabel(frequency) {
  return ({weekly:"每週",monthly:"每月",yearly:"每年"})[frequency]||frequency;
}

function recurringBillDate(value) {
  return value?String(value).slice(0,10):"";
}

function populateRecurringBillCategories(selectedId=null) {
  const select=$("recurring-bill-category");
  select.replaceChildren(new Option("未指定分類",""));
  for(const category of recurringBillCategories)select.add(new Option(category.name,String(category.id)));
  if(selectedId!==null&&selectedId!==undefined) {
    if(!recurringBillCategories.some(item=>item.id===Number(selectedId)))select.add(new Option("既有分類 #"+selectedId,String(selectedId)));
    select.value=String(selectedId);
  }
}

async function loadRecurringBillSupportData() {
  const result=await api("/categories?family_id="+selectedFamilyId+"&category_type=expense").catch(()=>({categories:[]}));
  recurringBillCategories=(result.categories||[]).filter(item=>item.is_active!==false);
  populateRecurringBillCategories();
}

function recurringBillQuery() {
  const params=new URLSearchParams({family_id:String(selectedFamilyId)});
  if($("recurring-bill-include-inactive").checked)params.set("include_inactive","true");
  return params.toString();
}

function renderRecurringBills() {
  const list=$("recurring-bills-list");
  list.replaceChildren();
  $("recurring-bills-count").textContent=recurringBillRows.length+" 個定期規則";
  $("recurring-bills-empty").classList.toggle("hidden",recurringBillRows.length!==0);
  for(const item of recurringBillRows) {
    const category=recurringBillCategories.find(row=>row.id===item.category_id);
    const card=document.createElement("article");
    card.className="recurring-bill-card"+(!item.is_active?" recurring-bill-inactive":"");
    const top=document.createElement("div");
    top.className="recurring-bill-top";
    const main=document.createElement("div");
    const title=document.createElement("strong");
    title.textContent=item.title;
    const meta=document.createElement("p");
    meta.className="muted tiny";
    meta.textContent=[recurringFrequencyLabel(item.frequency)+(item.interval_count>1?" · 每 "+item.interval_count+" 個週期":""),category?.name||"未分類","起始 "+recurringBillDate(item.start_date),item.end_date?"結束 "+recurringBillDate(item.end_date):"無結束日"].join(" · ");
    main.append(title,meta);
    const amount=document.createElement("div");
    amount.className="recurring-bill-amount";
    const total=document.createElement("strong");
    total.textContent=money(Number(item.original_amount||0)+Number(item.tax_amount||0)-Number(item.discount_amount||0),item.currency_code);
    const next=document.createElement("span");
    next.className="tiny muted";
    next.textContent=item.is_active?"下次產生 "+recurringBillDate(item.next_run_date):"已停用";
    amount.append(total,next);
    top.append(main,amount);
    card.append(top);
    const detail=document.createElement("p");
    detail.className="tiny muted";
    detail.textContent="產生帳單後 "+item.due_days_after+" 天到期"+(item.note?" · "+item.note:"");
    card.append(detail);
    if(!item.is_active) {
      const status=document.createElement("span");
      status.className="bill-status bill-status-voided";
      status.textContent="已停用";
      card.append(status);
    } else {
      const actions=document.createElement("div");
      actions.className="account-actions";
      const generate=document.createElement("button");
      generate.type="button";generate.className="primary small";generate.textContent="立即產生帳單";
      generate.addEventListener("click",()=>generateRecurringBills(item));
      const edit=document.createElement("button");
      edit.type="button";edit.className="secondary small";edit.textContent="修改";
      edit.addEventListener("click",()=>startEditRecurringBill(item));
      const deactivate=document.createElement("button");
      deactivate.type="button";deactivate.className="danger small";deactivate.textContent="停用";
      deactivate.addEventListener("click",()=>deactivateRecurringBill(item));
      actions.append(generate,edit,deactivate);
      card.append(actions);
    }
    list.append(card);
  }
}

async function loadRecurringBills() {
  if(!selectedFamilyId)return false;
  clearNotice("recurring-bill-notice");
  $("recurring-bills-loading").classList.remove("hidden");
  try {
    const result=await api("/recurring-bills?"+recurringBillQuery());
    recurringBillRows=result.recurring_bills||[];
    renderRecurringBills();
    return true;
  } catch(error) {
    notice("recurring-bill-notice","定期帳單清單載入失敗："+error.message,"error");
    return false;
  } finally {
    $("recurring-bills-loading").classList.add("hidden");
  }
}

async function showRecurringBills() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理定期帳單。","error");return;}
  $("recurring-bills-view").classList.remove("hidden");
  $("recurring-bills-view").scrollIntoView({behavior:"smooth",block:"start"});
  try {
    await loadRecurringBillSupportData();
    await loadRecurringBills();
  } catch(error) {
    notice("recurring-bill-notice","定期帳單管理初始化失敗："+error.message,"error");
  }
}

function resetRecurringBillForm() {
  editingRecurringBillId=null;
  $("recurring-bill-form").reset();
  $("recurring-bill-form-title").textContent="新增定期帳單";
  $("recurring-bill-submit").textContent="新增定期帳單";
  $("recurring-bill-start").value=localDateString();
  $("recurring-bill-next").value=localDateString();
  $("recurring-bill-end").value="";
  $("recurring-bill-interval").value="1";
  $("recurring-bill-due-days").value="0";
  $("recurring-bill-tax").value="0";
  $("recurring-bill-discount").value="0";
  $("recurring-bill-currency").value="TWD";
  $("recurring-bill-form-panel").classList.add("hidden");
  populateRecurringBillCategories();
}

function startEditRecurringBill(item) {
  editingRecurringBillId=item.id;
  $("recurring-bill-form-title").textContent="修改定期帳單";
  $("recurring-bill-submit").textContent="儲存修改";
  $("recurring-bill-title").value=item.title;
  $("recurring-bill-category").value=item.category_id?String(item.category_id):"";
  $("recurring-bill-frequency").value=item.frequency;
  $("recurring-bill-interval").value=item.interval_count;
  $("recurring-bill-start").value=recurringBillDate(item.start_date);
  $("recurring-bill-end").value=recurringBillDate(item.end_date);
  $("recurring-bill-next").value=recurringBillDate(item.next_run_date);
  $("recurring-bill-due-days").value=item.due_days_after;
  $("recurring-bill-original").value=item.original_amount;
  $("recurring-bill-tax").value=item.tax_amount||0;
  $("recurring-bill-discount").value=item.discount_amount||0;
  $("recurring-bill-currency").value=item.currency_code;
  $("recurring-bill-note").value=item.note||"";
  populateRecurringBillCategories(item.category_id);
  $("recurring-bill-form-panel").classList.remove("hidden");
  $("recurring-bill-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
}

$("open-recurring-bills").addEventListener("click",showRecurringBills);
$("close-recurring-bills").addEventListener("click",()=>{
  $("recurring-bills-view").classList.add("hidden");
  resetRecurringBillForm();
});
$("add-recurring-bill-button").addEventListener("click",()=>{
  resetRecurringBillForm();
  $("recurring-bill-form-panel").classList.remove("hidden");
  $("recurring-bill-form-panel").scrollIntoView({behavior:"smooth",block:"start"});
});
$("recurring-bill-cancel").addEventListener("click",resetRecurringBillForm);
$("recurring-bill-include-inactive").addEventListener("change",loadRecurringBills);
$("recurring-bill-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const button=$("recurring-bill-submit");
  button.disabled=true;
  clearNotice("recurring-bill-notice");
  try {
    const original=Number($("recurring-bill-original").value);
    const tax=Number($("recurring-bill-tax").value||0);
    const discount=Number($("recurring-bill-discount").value||0);
    if(!(original>0)||tax<0||discount<0)throw new Error("原始金額必須大於 0，稅額與折扣不可小於 0。");
    if(original+tax-discount<0)throw new Error("折扣金額不可大於原始金額加稅額。");
    const start=$("recurring-bill-start").value;
    const end=$("recurring-bill-end").value;
    const next=$("recurring-bill-next").value;
    if(end&&end<start)throw new Error("結束日期不可早於開始日期。");
    if(next&&next<start)throw new Error("下次產生日期不可早於開始日期。");
    const payload={
      title:$("recurring-bill-title").value.trim(),
      category_id:$("recurring-bill-category").value?Number($("recurring-bill-category").value):null,
      frequency:$("recurring-bill-frequency").value,
      interval_count:Number($("recurring-bill-interval").value),
      start_date:start,
      end_date:end||null,
      next_run_date:next||null,
      due_days_after:Number($("recurring-bill-due-days").value||0),
      original_amount:$("recurring-bill-original").value,
      tax_amount:$("recurring-bill-tax").value||"0",
      discount_amount:$("recurring-bill-discount").value||"0",
      currency_code:$("recurring-bill-currency").value.trim().toUpperCase(),
      note:$("recurring-bill-note").value.trim()||null
    };
    const wasEditing=Boolean(editingRecurringBillId);
    if(wasEditing) {
      await api("/recurring-bills/"+editingRecurringBillId+"?family_id="+selectedFamilyId,{method:"PATCH",body:JSON.stringify(payload)});
    } else {
      await api("/recurring-bills?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
    }
    resetRecurringBillForm();
    const refreshed=await loadRecurringBills();
    notice("recurring-bill-notice",refreshed?(wasEditing?"定期帳單規則已更新。":"定期帳單規則已新增。"):"規則已儲存，但清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("recurring-bill-notice",error.message,"error");
  } finally {
    button.disabled=false;
  }
});

async function generateRecurringBills(item) {
  const through=window.prompt("請輸入要產生帳單至哪一天（YYYY-MM-DD）：",localDateString());
  if(through===null)return;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(through)) {
    notice("recurring-bill-notice","日期格式請使用 YYYY-MM-DD。","error");
    return;
  }
  if(through<recurringBillDate(item.next_run_date)) {
    notice("recurring-bill-notice","產生截止日不可早於下次產生日期。","error");
    return;
  }
  try {
    const result=await api("/recurring-bills/"+item.id+"/generate?family_id="+selectedFamilyId+"&through_date="+encodeURIComponent(through),{method:"POST"});
    const refreshed=await loadRecurringBills();
    if(!$("bills-view").classList.contains("hidden"))await loadBills();
    notice("recurring-bill-notice","已產生 "+result.generated_count+" 張帳單。"+(result.next_run_date?"下次產生日期："+recurringBillDate(result.next_run_date):"此規則已到期或停用。"),refreshed?"success":"error");
  } catch(error) {
    notice("recurring-bill-notice",error.message,"error");
  }
}

async function deactivateRecurringBill(item) {
  if(!window.confirm("確定停用「"+item.title+"」？已產生的帳單不會刪除，只有未來期數停止自動產生。"))return;
  try {
    await api("/recurring-bills/"+item.id+"?family_id="+selectedFamilyId,{method:"DELETE"});
    const refreshed=await loadRecurringBills();
    notice("recurring-bill-notice",refreshed?"定期帳單已停用，既有帳單保留。":"已停用，但清單重新載入失敗，請重新整理。",refreshed?"success":"error");
  } catch(error) {
    notice("recurring-bill-notice",error.message,"error");
  }
}


// --------------------------------------------------
// G-02-09：家庭財務報表
// --------------------------------------------------
let monthlyReportData=null;
let yearlyReportData=null;
let categoryReportData=null;

function reportAmountMap(rows) {
  return new Map((rows||[]).map(row=>[row.currency_code,Number(row.amount||0)]));
}

function reportCurrencies(...groups) {
  return [...new Set(groups.flatMap(rows=>(rows||[]).map(row=>row.currency_code)))].sort();
}

function renderMonthlyReport(data) {
  const host=$("monthly-report-summary");
  host.replaceChildren();
  $("monthly-report-period").textContent=data.year+" 年 "+data.month+" 月";
  $("monthly-report-count").textContent=data.transaction_count+" 筆交易";
  const currencies=reportCurrencies(data.total_income,data.total_expense,data.net_amount);
  $("monthly-report-empty").classList.toggle("hidden",currencies.length!==0);
  const income=reportAmountMap(data.total_income),expense=reportAmountMap(data.total_expense),net=reportAmountMap(data.net_amount);
  for(const currency of currencies) {
    const card=document.createElement("article");
    card.className="report-currency-card";
    const title=document.createElement("h4");title.textContent=currency;
    card.append(title);
    for(const [label,value,kind] of [["總收入",income.get(currency)||0,"income"],["總支出",expense.get(currency)||0,"expense"],["淨收支",net.get(currency)||0,"net"]]) {
      const row=document.createElement("div");row.className="report-metric "+kind;
      const name=document.createElement("span");name.textContent=label;
      const amount=document.createElement("strong");amount.textContent=money(value,currency);
      row.append(name,amount);card.append(row);
    }
    host.append(card);
  }
}

function renderYearlyReport(data) {
  const host=$("yearly-report-list");host.replaceChildren();
  const currencies=reportCurrencies(data.total_income,data.total_expense,data.net_amount);
  $("yearly-report-empty").classList.toggle("hidden",currencies.length!==0);
  const monthly=data.monthly_reports||[];
  for(const currency of currencies) {
    const block=document.createElement("article");block.className="yearly-currency-block";
    const title=document.createElement("h4");title.textContent=currency+" · "+data.year+" 年";
    block.append(title);
    const maxAmount=Math.max(1,...monthly.flatMap(item=>[reportAmountMap(item.total_income).get(currency)||0,reportAmountMap(item.total_expense).get(currency)||0]));
    for(const item of monthly) {
      const income=reportAmountMap(item.total_income).get(currency)||0;
      const expense=reportAmountMap(item.total_expense).get(currency)||0;
      const net=reportAmountMap(item.net_amount).get(currency)||0;
      const row=document.createElement("div");row.className="yearly-month-row";
      const month=document.createElement("strong");month.textContent=item.month+" 月";
      const bars=document.createElement("div");bars.className="yearly-bars";
      const incomeTrack=document.createElement("div");incomeTrack.className="yearly-bar-track";
      const incomeFill=document.createElement("div");incomeFill.className="yearly-bar-fill";incomeFill.style.width=(income/maxAmount*100)+"%";incomeTrack.append(incomeFill);
      const expenseTrack=document.createElement("div");expenseTrack.className="yearly-bar-track";
      const expenseFill=document.createElement("div");expenseFill.className="yearly-bar-fill expense";expenseFill.style.width=(expense/maxAmount*100)+"%";expenseTrack.append(expenseFill);
      bars.append(incomeTrack,expenseTrack);
      const netLabel=document.createElement("span");netLabel.className="yearly-month-net";netLabel.textContent="淨額 "+money(net,currency);
      row.append(month,bars,netLabel);block.append(row);
    }
    const legend=document.createElement("p");legend.className="tiny muted";legend.textContent="上方綠色：收入；下方橘色：支出。每個幣別使用自己的比例尺。";
    block.append(legend);host.append(block);
  }
}

function renderCategoryReport(data) {
  const host=$("category-report-list");host.replaceChildren();
  $("category-report-period").textContent=(data.start_date||"不限開始日")+" 至 "+(data.end_date||"不限結束日");
  const rows=data.categories||[];
  $("category-report-empty").classList.toggle("hidden",rows.length===0);
  for(const item of rows) {
    const card=document.createElement("article");card.className="category-report-item";
    const top=document.createElement("div");top.className="category-report-item-top";
    const name=document.createElement("strong");name.textContent=(item.category_type==="income"?"收入 · ":"支出 · ")+item.category_name;
    const amount=document.createElement("strong");amount.textContent=money(item.total_amount,item.currency_code);
    top.append(name,amount);
    const track=document.createElement("div");track.className="category-report-track";
    const fill=document.createElement("div");fill.className="category-report-fill";fill.style.width=Math.max(0,Math.min(100,Number(item.percentage||0)))+"%";track.append(fill);
    const meta=document.createElement("div");meta.className="category-report-meta tiny muted";
    const count=document.createElement("span");count.textContent=item.transaction_count+" 筆 · "+Number(item.percentage||0).toFixed(2)+"%";
    const currency=document.createElement("span");currency.textContent=item.currency_code;
    meta.append(count,currency);card.append(top,track,meta);host.append(card);
  }
}

async function loadFinancialReports() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再查看財務報表。","error");return false;}
  const year=Number($("report-year").value),month=Number($("report-month").value);
  const start=$("report-start-date").value,end=$("report-end-date").value;
  if(!Number.isInteger(year)||year<2000||year>2100){notice("reports-notice","報表年份必須介於 2000 至 2100。","error");return false;}
  if(start&&end&&start>end){notice("reports-notice","分類開始日期不可晚於結束日期。","error");return false;}
  $("reports-loading").classList.remove("hidden");clearNotice("reports-notice");
  try {
    const categoryParams=new URLSearchParams({family_id:String(selectedFamilyId)});
    if(start)categoryParams.set("start_date",start);
    if(end)categoryParams.set("end_date",end);
    if($("report-category-type").value)categoryParams.set("transaction_type",$("report-category-type").value);
    const [monthly,yearly,categories]=await Promise.all([
      api("/reports/monthly-summary?family_id="+selectedFamilyId+"&year="+year+"&month="+month),
      api("/reports/yearly-summary?family_id="+selectedFamilyId+"&year="+year),
      api("/reports/category-summary?"+categoryParams.toString())
    ]);
    monthlyReportData=monthly;yearlyReportData=yearly;categoryReportData=categories;
    renderMonthlyReport(monthly);renderYearlyReport(yearly);renderCategoryReport(categories);
    notice("reports-notice","財務報表已更新。","success");
    return true;
  } catch(error) {
    notice("reports-notice","報表載入失敗："+error.message,"error");
    return false;
  } finally {
    $("reports-loading").classList.add("hidden");
  }
}

function openFinancialReports() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再查看財務報表。","error");return;}
  const now=new Date(),year=now.getFullYear(),month=now.getMonth()+1;
  $("report-year").value=String(year);
  $("report-month").value=String(month);
  const first=new Date(year,month-1,1);
  const last=new Date(year,month,0);
  const iso=date=>date.getFullYear()+"-"+String(date.getMonth()+1).padStart(2,"0")+"-"+String(date.getDate()).padStart(2,"0");
  $("report-start-date").value=iso(first);$("report-end-date").value=iso(last);
  $("reports-view").classList.remove("hidden");
  $("reports-view").scrollIntoView({behavior:"smooth",block:"start"});
  loadFinancialReports();
}

$("open-reports").addEventListener("click",openFinancialReports);
$("close-reports").addEventListener("click",()=>{$("reports-view").classList.add("hidden");});
$("refresh-reports").addEventListener("click",loadFinancialReports);
$("apply-reports").addEventListener("click",loadFinancialReports);


// --------------------------------------------------
// G-02-10：家庭成員名單與邀請
// --------------------------------------------------
function renderFamilyMembers(members) {
  const host = $("family-members-list");
  host.replaceChildren();
  $("family-members-count").textContent = members.length + " 位成員";
  $("family-members-empty").classList.toggle("hidden", members.length > 0);
  for (const member of members) {
    const card = document.createElement("article");
    card.className = "family-member-card";
    const identity = document.createElement("div");
    identity.className = "family-member-identity";
    const name = document.createElement("strong");
    name.textContent = (member.display_name || "未設定名稱") + (member.is_me ? "（我）" : "");
    const email = document.createElement("span");
    email.className = "tiny muted";
    email.textContent = member.email;
    identity.append(name, email);
    const roles = document.createElement("div");
    roles.className = "family-member-roles";
    for (const role of (member.roles || [])) {
      const tag = document.createElement("span");
      tag.className = "member-role-tag";
      tag.textContent = role;
      roles.append(tag);
    }
    if (!member.roles || member.roles.length === 0) {
      const none = document.createElement("span");
      none.className = "tiny muted";
      none.textContent = "尚未指派角色";
      roles.append(none);
    }
    card.append(identity, roles);
    host.append(card);
  }
}

async function loadFamilyMembers() {
  if (!selectedFamilyId) {
    notice("notice-app", "請先建立或選擇家庭，再管理家庭成員。", "error");
    return;
  }
  $("family-members-loading").classList.remove("hidden");
  clearNotice("family-members-notice");
  try {
    const result = await api("/families/" + selectedFamilyId + "/members");
    renderFamilyMembers(result.members || []);
  } catch (error) {
    notice("family-members-notice", "家庭成員載入失敗：" + error.message, "error");
    $("family-members-list").replaceChildren();
    $("family-members-count").textContent = "—";
  } finally {
    $("family-members-loading").classList.add("hidden");
  }
}

function openFamilyMembers() {
  if (!selectedFamilyId) {
    notice("notice-app", "請先建立或選擇家庭，再管理家庭成員。", "error");
    return;
  }
  $("family-members-view").classList.remove("hidden");
  $("family-members-view").scrollIntoView({behavior: "smooth", block: "start"});
  loadFamilyMembers();
  loadFamilyInvitations();
}

$("open-family-members").addEventListener("click", openFamilyMembers);
$("close-family-members").addEventListener("click", () => {
  $("family-members-view").classList.add("hidden");
});
$("refresh-family-members").addEventListener("click", async () => { await loadFamilyMembers(); await loadFamilyInvitations(); });
$("copy-family-invite-link").addEventListener("click", async () => { const value = $("family-invite-url").value; if (!value) return; try { await navigator.clipboard.writeText(value); notice("family-members-notice", "邀請連結已複製。", "success"); } catch { $("family-invite-url").select(); notice("family-members-notice", "瀏覽器無法自動複製，已選取連結，請手動複製。", "error"); } });
$("family-member-invite-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFamilyId) return;
  const button = $("family-member-invite-submit");
  button.disabled = true;
  clearNotice("family-members-notice");
  try {
    const email = $("family-member-email").value.trim();
    const result = await api("/families/" + selectedFamilyId + "/invitations", {
      method: "POST",
      body: JSON.stringify({email})
    });
    $("family-member-email").value = "";
    $("family-invite-url").value = result.invite_url;
    $("family-invite-link-panel").classList.remove("hidden");
    await loadFamilyInvitations();
    notice("family-members-notice", "邀請已建立。請複製邀請連結傳給家人；家人須使用此 Email 的 Google 帳號登入並接受邀請。", "success");
  } catch (error) {
    notice("family-members-notice", "邀請失敗：" + error.message, "error");
  } finally {
    button.disabled = false;
  }
});



async function loadFamilyInvitations() {
  if (!selectedFamilyId) return;
  const host = $("family-invitations-list");
  if (!host) return;
  host.replaceChildren();
  try {
    const result = await api("/families/" + selectedFamilyId + "/invitations");
    for (const invitation of (result.invitations || [])) {
      const row = document.createElement("article");
      row.className = "family-invitation-row";
      const info = document.createElement("div");
      const email = document.createElement("strong");
      email.textContent = invitation.email;
      const expiry = document.createElement("p");
      expiry.className = "tiny muted";
      expiry.textContent = "邀請人：" + invitation.invited_by + " · 到期：" + new Date(invitation.expires_at).toLocaleString("zh-TW");
      info.append(email, expiry);
      const revoke = document.createElement("button");
      revoke.type = "button";
      revoke.className = "danger small";
      revoke.textContent = "撤銷邀請";
      revoke.addEventListener("click", async () => {
        if (!window.confirm("確定撤銷寄給 " + invitation.email + " 的邀請？")) return;
        try {
          await api("/families/" + selectedFamilyId + "/invitations/" + invitation.invitation_id, {method:"DELETE"});
          await loadFamilyInvitations();
          notice("family-members-notice", "邀請已撤銷。", "success");
        } catch (error) {
          notice("family-members-notice", error.message, "error");
        }
      });
      row.append(info, revoke);
      host.append(row);
    }
    $("family-invitations-empty").classList.toggle("hidden", (result.invitations || []).length > 0);
  } catch (error) {
    $("family-invitations-empty").classList.remove("hidden");
    $("family-invitations-empty").textContent = "待接受邀請載入失敗：" + error.message;
  }
}

function captureFamilyInvitationToken() {
  const params = new URLSearchParams(window.location.search);
  const inviteToken = params.get("invite");
  if (inviteToken) {
    sessionStorage.setItem(INVITE_TOKEN_KEY, inviteToken);
    window.history.replaceState({}, document.title, window.location.pathname + window.location.hash);
  }
}

async function handlePendingFamilyInvitation() {
  const inviteToken = sessionStorage.getItem(INVITE_TOKEN_KEY);
  if (!inviteToken) return;
  try {
    const result = await api("/families/invitations/accept", {
      method: "POST",
      body: JSON.stringify({token: inviteToken})
    });
    sessionStorage.removeItem(INVITE_TOKEN_KEY);
    selectedFamilyId = result.family_id;
    await loadFamilies();
    notice("notice-app", "已成功加入家庭！系統已先指派「一般成員」角色，家庭管理員可再調整權限。", "success");
  } catch (error) {
    notice("notice-app", error.message + "。請確認使用受邀 Email 的 Google 帳號登入；若仍無法加入，請向邀請人索取新連結。", "error");
  }
}

// --------------------------------------------------
// G-02-11：角色、細項權限及成員角色指派
// --------------------------------------------------
let familyRoles = [];
let familyMembersForRoles = [];
let familyPermissionCatalog = [];
let editingFamilyRoleId = null;

const ROLE_CATEGORY_NAMES = {
  dashboard:"儀表板", transactions:"帳務紀錄", accounts:"帳戶管理",
  categories:"收支分類", bills:"帳單管理", recurring_bills:"定期帳單",
  payments:"帳單付款", reconciliation:"帳務對帳", reports:"財務報表",
  notifications:"通知", exports:"匯出管理", imports:"資料匯入",
  attachments:"附件", ocr:"文字辨識", family:"家庭設定",
  members:"家庭成員", roles:"角色權限", audit_logs:"稽核紀錄",
  backups:"備份管理", exchange_rates:"匯率管理"
};

function renderFamilyRoles() {
  const host = $("family-roles-list");
  host.replaceChildren();
  if (!familyRoles.length) {
    const empty = document.createElement("p");
    empty.className = "muted tiny";
    empty.textContent = "目前沒有可顯示的角色，或目前帳號沒有查看角色的權限。";
    host.append(empty);
  }
  for (const role of familyRoles) {
    const card = document.createElement("article");
    card.className = "family-role-card";
    const top = document.createElement("div");
    top.className = "family-role-card-top";
    const info = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = role.name + (role.is_system ? "（系統預設）" : "");
    const desc = document.createElement("p");
    desc.className = "tiny muted";
    desc.textContent = role.description || "未設定說明";
    const meta = document.createElement("span");
    meta.className = "tiny muted";
    meta.textContent = role.permission_codes.length + " 項權限 · " + role.assigned_member_count + " 位成員";
    info.append(name, desc, meta);
    top.append(info);
    const actions = document.createElement("div");
    actions.className = "form-actions";
    if (!role.is_system) {
      const edit = document.createElement("button");
      edit.type = "button"; edit.className = "secondary small"; edit.textContent = "編輯";
      edit.addEventListener("click", () => openFamilyRoleEditor(role));
      const remove = document.createElement("button");
      remove.type = "button"; remove.className = "danger small"; remove.textContent = "作廢";
      remove.addEventListener("click", () => voidFamilyRole(role));
      actions.append(edit, remove);
    } else {
      const locked = document.createElement("span");
      locked.className = "member-role-tag"; locked.textContent = "受保護";
      actions.append(locked);
    }
    card.append(top, actions);
    host.append(card);
  }
}

function renderRolePermissionEditor(selectedCodes = [], selectedScopes = {}) {
  const host = $("family-role-permissions");
  host.replaceChildren();
  const grouped = new Map();
  for (const permission of familyPermissionCatalog) {
    if (!grouped.has(permission.category)) grouped.set(permission.category, []);
    grouped.get(permission.category).push(permission);
  }
  for (const [category, permissions] of grouped) {
    const group = document.createElement("section");
    group.className = "role-permission-group";
    const heading = document.createElement("h4");
    heading.textContent = ROLE_CATEGORY_NAMES[category] || category;
    group.append(heading);
    for (const permission of permissions) {
      const label = document.createElement("label");
      label.className = "role-permission-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.dataset.permissionCode = permission.code;
      checkbox.checked = selectedCodes.includes(permission.code);
      checkbox.disabled = !permission.grantable && !checkbox.checked;
      const textWrap = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = permission.name;
      const code = document.createElement("small");
      code.textContent = permission.code;
      textWrap.append(title, code);
      label.append(checkbox, textWrap);
      group.append(label);
    }
    host.append(group);
  }
  renderRoleScopeEditor(selectedScopes);
}

function renderRoleScopeEditor(selectedScopes = {}) {
  const host = $("family-role-scopes");
  host.replaceChildren();
  const categories = new Set(
    [...$("family-role-permissions").querySelectorAll("input:checked")]
      .map(input => input.dataset.permissionCode.split(".")[0])
  );
  for (const category of [...categories].sort()) {
    const label = document.createElement("label");
    label.className = "field role-scope-field";
    const title = document.createElement("span");
    title.textContent = (ROLE_CATEGORY_NAMES[category] || category) + "資料範圍";
    const select = document.createElement("select");
    select.dataset.scopeResource = category;
    for (const [value, text] of [["own","僅自己建立（own）"],["family","整個家庭（family）"]]) {
      const option = document.createElement("option");
      option.value = value; option.textContent = text;
      select.append(option);
    }
    select.value = selectedScopes[category] || "own";
    label.append(title, select);
    host.append(label);
  }
}

function openFamilyRoleEditor(role = null) {
  editingFamilyRoleId = role ? role.id : null;
  $("family-role-form-title").textContent = role ? "編輯自訂角色" : "建立自訂角色";
  $("family-role-name").value = role ? role.name : "";
  $("family-role-description").value = role ? (role.description || "") : "";
  renderRolePermissionEditor(role ? role.permission_codes : [], role ? role.data_scopes : {});
  $("family-role-form").classList.remove("hidden");
  $("family-role-form").scrollIntoView({behavior:"smooth", block:"start"});
}

function renderRoleMembers() {
  const host = $("family-role-members");
  host.replaceChildren();
  for (const member of familyMembersForRoles) {
    const card = document.createElement("article");
    card.className = "family-role-member-card";
    const identity = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = (member.display_name || "未設定名稱") + (member.is_me ? "（我）" : "");
    const email = document.createElement("span");
    email.className = "tiny muted"; email.textContent = member.email;
    identity.append(name, email);
    const controls = document.createElement("div");
    controls.className = "family-role-member-controls";
    const select = document.createElement("select");
    select.multiple = true;
    select.size = Math.min(Math.max(familyRoles.length, 2), 5);
    select.setAttribute("aria-label", "選擇" + (member.display_name || member.email) + "的角色");
    for (const role of familyRoles) {
      const option = document.createElement("option");
      option.value = String(role.id); option.textContent = role.name;
      option.selected = (member.role_ids || []).includes(role.id);
      select.append(option);
    }
    const save = document.createElement("button");
    save.type = "button"; save.className = "primary small"; save.textContent = "儲存指派";
    save.addEventListener("click", async () => {
      const roleIds = [...select.selectedOptions].map(option => Number(option.value));
      if (!roleIds.length) {
        notice("family-roles-notice", "每位有效成員至少必須保留一個角色。", "error");
        return;
      }
      save.disabled = true;
      try {
        await api("/families/" + selectedFamilyId + "/members/" + member.family_member_id + "/roles", {
          method:"PUT", body:JSON.stringify({role_ids:roleIds})
        });
        notice("family-roles-notice", "已更新 " + (member.display_name || member.email) + " 的角色。", "success");
        await loadFamilyRoles();
      } catch (error) {
        notice("family-roles-notice", "角色指派失敗：" + error.message, "error");
      } finally { save.disabled = false; }
    });
    controls.append(select, save);
    card.append(identity, controls);
    host.append(card);
  }
}

async function loadFamilyRoles() {
  if (!selectedFamilyId) return;
  clearNotice("family-roles-notice");
  try {
    const [roleResult, permissionResult, memberResult] = await Promise.all([
      api("/families/" + selectedFamilyId + "/roles"),
      api("/families/" + selectedFamilyId + "/permissions"),
      api("/families/" + selectedFamilyId + "/members")
    ]);
    familyRoles = roleResult.roles || [];
    familyPermissionCatalog = permissionResult.permissions || [];
    familyMembersForRoles = memberResult.members || [];
    renderFamilyRoles();
    renderRoleMembers();
  } catch (error) {
    notice("family-roles-notice", "角色資料載入失敗：" + error.message, "error");
    $("family-roles-list").replaceChildren();
    $("family-role-members").replaceChildren();
  }
}

async function openFamilyRoles() {
  if (!selectedFamilyId) {
    notice("notice-app", "請先建立或選擇家庭，再管理角色與權限。", "error");
    return;
  }
  $("family-roles-view").classList.remove("hidden");
  $("family-roles-view").scrollIntoView({behavior:"smooth", block:"start"});
  await loadFamilyRoles();
}

$("open-family-roles").addEventListener("click", openFamilyRoles);
$("close-family-roles").addEventListener("click", () => $("family-roles-view").classList.add("hidden"));
$("refresh-family-roles").addEventListener("click", loadFamilyRoles);
$("new-family-role").addEventListener("click", () => openFamilyRoleEditor());
$("cancel-family-role").addEventListener("click", () => {
  $("family-role-form").classList.add("hidden");
  editingFamilyRoleId = null;
});
$("family-role-permissions").addEventListener("change", event => {
  if (event.target.matches("input[data-permission-code]")) renderRoleScopeEditor();
});
$("family-role-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("save-family-role");
  button.disabled = true;
  try {
    const permissionCodes = [...$("family-role-permissions").querySelectorAll("input:checked")]
      .map(input => input.dataset.permissionCode);
    const dataScopes = {};
    for (const select of $("family-role-scopes").querySelectorAll("select[data-scope-resource]")) {
      dataScopes[select.dataset.scopeResource] = select.value;
    }
    const payload = {
      name:$("family-role-name").value.trim(),
      description:$("family-role-description").value.trim() || null,
      permission_codes:permissionCodes,
      data_scopes:dataScopes
    };
    const path = "/families/" + selectedFamilyId + "/roles" + (editingFamilyRoleId ? "/" + editingFamilyRoleId : "");
    await api(path, {method:editingFamilyRoleId ? "PATCH" : "POST", body:JSON.stringify(payload)});
    $("family-role-form").classList.add("hidden");
    editingFamilyRoleId = null;
    notice("family-roles-notice", "角色設定已儲存。", "success");
    await loadFamilyRoles();
  } catch (error) {
    notice("family-roles-notice", "儲存角色失敗：" + error.message, "error");
  } finally { button.disabled = false; }
});

async function voidFamilyRole(role) {
  if (!window.confirm("確定作廢自訂角色「" + role.name + "」？此操作不會刪除歷史資料。")) return;
  try {
    await api("/families/" + selectedFamilyId + "/roles/" + role.id, {method:"DELETE"});
    notice("family-roles-notice", "自訂角色已作廢。", "success");
    await loadFamilyRoles();
  } catch (error) {
    notice("family-roles-notice", "作廢角色失敗：" + error.message, "error");
  }
}


// --------------------------------------------------
// G-02-12：家庭稽核紀錄查詢
// --------------------------------------------------
let auditLogOffset = 0;
const AUDIT_LOG_LIMIT = 50;
const AUDIT_ACTION_LABELS = {
  "role.create":"建立角色", "role.update":"修改角色權限",
  "role.void":"作廢角色", "member.roles.update":"調整成員角色",
  "transaction.create":"新增帳務", "transaction.update":"修改帳務",
  "transaction.void":"作廢帳務", "account.create":"新增帳戶",
  "account.update":"修改帳戶", "account.void":"作廢帳戶"
};

function renderAuditLogs(records) {
  const host = $("audit-logs-list");
  host.replaceChildren();
  $("audit-logs-empty").classList.toggle("hidden", records.length > 0);
  for (const record of records) {
    const card = document.createElement("article");
    card.className = "audit-log-card";
    const top = document.createElement("div");
    top.className = "audit-log-card-top";
    const summary = document.createElement("div");
    const action = document.createElement("strong");
    action.textContent = AUDIT_ACTION_LABELS[record.action] || record.action;
    const details = document.createElement("p");
    details.className = "tiny muted";
    details.textContent = (record.actor_name || "未知操作者") + " · " + (record.actor_email || "系統操作");
    const entity = document.createElement("span");
    entity.className = "member-role-tag";
    entity.textContent = record.entity_type + (record.entity_id ? " #" + record.entity_id : "");
    summary.append(action, details, entity);
    const time = document.createElement("time");
    time.className = "tiny muted audit-log-time";
    time.textContent = record.created_at ? new Date(record.created_at).toLocaleString("zh-TW", {hour12:false}) : "時間未知";
    top.append(summary, time);
    card.append(top);
    if (record.description) {
      const description = document.createElement("p");
      description.className = "audit-log-description";
      description.textContent = record.description;
      card.append(description);
    }
    if (record.old_values || record.new_values) {
      const disclosure = document.createElement("details");
      disclosure.className = "audit-log-values";
      const label = document.createElement("summary");
      label.textContent = "查看異動內容";
      const values = document.createElement("div");
      values.className = "audit-log-value-grid";
      if (record.old_values) {
        const old = document.createElement("div");
        const oldTitle = document.createElement("strong");
        oldTitle.textContent = "異動前";
        const oldPre = document.createElement("pre");
        oldPre.textContent = JSON.stringify(record.old_values, null, 2);
        old.append(oldTitle, oldPre);
        values.append(old);
      }
      if (record.new_values) {
        const next = document.createElement("div");
        const nextTitle = document.createElement("strong");
        nextTitle.textContent = "異動後";
        const nextPre = document.createElement("pre");
        nextPre.textContent = JSON.stringify(record.new_values, null, 2);
        next.append(nextTitle, nextPre);
        values.append(next);
      }
      disclosure.append(label, values);
      card.append(disclosure);
    }
    host.append(card);
  }
}

async function loadAuditLogs() {
  if (!selectedFamilyId) return;
  $("audit-logs-loading").classList.remove("hidden");
  clearNotice("audit-logs-notice");
  try {
    const params = new URLSearchParams({limit:String(AUDIT_LOG_LIMIT), offset:String(auditLogOffset)});
    const start = $("audit-log-start-date").value;
    const end = $("audit-log-end-date").value;
    const action = $("audit-log-action").value.trim();
    const entity = $("audit-log-entity").value.trim();
    if (start) params.set("start_date", start);
    if (end) params.set("end_date", end);
    if (action) params.set("action", action);
    if (entity) params.set("entity_type", entity);
    const result = await api("/families/" + selectedFamilyId + "/audit-logs?" + params.toString());
    renderAuditLogs(result.records || []);
    $("audit-logs-count").textContent = result.total + " 筆紀錄";
    $("audit-logs-scope").textContent = result.scope === "family" ? "目前可查看全家庭紀錄" : "目前僅顯示自己執行的紀錄";
    const page = Math.floor(auditLogOffset / AUDIT_LOG_LIMIT) + 1;
    $("audit-log-page-label").textContent = "第 " + page + " 頁";
    $("audit-log-prev").disabled = auditLogOffset === 0;
    $("audit-log-next").disabled = auditLogOffset + AUDIT_LOG_LIMIT >= result.total;
  } catch (error) {
    notice("audit-logs-notice", "稽核紀錄載入失敗：" + error.message, "error");
    $("audit-logs-list").replaceChildren();
    $("audit-logs-count").textContent = "—";
    $("audit-logs-scope").textContent = "無法取得資料範圍";
  } finally {
    $("audit-logs-loading").classList.add("hidden");
  }
}

async function openAuditLogs() {
  if (!selectedFamilyId) {
    notice("notice-app", "請先建立或選擇家庭，再查看稽核紀錄。", "error");
    return;
  }
  $("audit-logs-view").classList.remove("hidden");
  $("audit-logs-view").scrollIntoView({behavior:"smooth", block:"start"});
  auditLogOffset = 0;
  await loadAuditLogs();
}

$("open-audit-logs").addEventListener("click", openAuditLogs);
$("close-audit-logs").addEventListener("click", () => $("audit-logs-view").classList.add("hidden"));
$("refresh-audit-logs").addEventListener("click", loadAuditLogs);
$("audit-log-filter-form").addEventListener("submit", event => {
  event.preventDefault();
  auditLogOffset = 0;
  loadAuditLogs();
});
$("clear-audit-log-filters").addEventListener("click", () => {
  $("audit-log-filter-form").reset();
  auditLogOffset = 0;
  loadAuditLogs();
});
$("audit-log-prev").addEventListener("click", () => {
  auditLogOffset = Math.max(0, auditLogOffset - AUDIT_LOG_LIMIT);
  loadAuditLogs();
});
$("audit-log-next").addEventListener("click", () => {
  auditLogOffset += AUDIT_LOG_LIMIT;
  loadAuditLogs();
});

/* G-02-13: family category management */
let categoryRows = [], editingCategoryId = null;
function renderCategories(){
 const host=$("categories-list");host.replaceChildren();$("categories-empty").classList.toggle("hidden",categoryRows.length>0);$("categories-count").textContent=categoryRows.length+" 個分類";
 for(const row of categoryRows){
  const card=document.createElement("article");card.className="category-admin-card";
  const info=document.createElement("div");info.className="category-admin-info";
  const name=document.createElement("strong");name.textContent=(row.icon?row.icon+" ":"")+row.name;
  const parent=categoryRows.find(item=>item.id===row.parent_id);
  const meta=document.createElement("p");meta.className="tiny muted";meta.textContent=(row.category_type==="income"?"收入":"支出")+(parent?" · 上層："+parent.name:" · 頂層")+" · 排序 "+row.sort_order+(row.is_system?" · 系統分類":" · 家庭自訂")+(row.is_active?"":" · 已停用");
  info.append(name,meta);card.append(info);const actions=document.createElement("div");actions.className="category-admin-actions";
  if(!row.is_system&&row.family_id===selectedFamilyId&&row.is_active){
   const edit=document.createElement("button");edit.type="button";edit.className="secondary small";edit.textContent="編輯";edit.addEventListener("click",()=>openCategoryForm(row));
   const disable=document.createElement("button");disable.type="button";disable.className="secondary small";disable.textContent="停用";disable.addEventListener("click",async()=>{if(!window.confirm("確定停用「"+row.name+"」？歷史資料會保留。"))return;try{await api("/categories/"+row.id+"?family_id="+selectedFamilyId,{method:"DELETE"});notice("categories-notice","分類已停用。");await loadCategories();}catch(error){notice("categories-notice",error.message,"error");}});
   actions.append(edit,disable);
  }else{const tag=document.createElement("span");tag.className="tiny muted";tag.textContent=row.is_system?"唯讀":"已停用（保留紀錄）";actions.append(tag);}
  card.append(actions);host.append(card);
 }
}
function populateCategoryParents(type,id=null){const select=$("category-parent");select.replaceChildren(new Option("無（頂層分類）",""));for(const row of categoryRows.filter(x=>x.is_active&&x.category_type===type&&x.id!==id))select.add(new Option((row.is_system?"系統 · ":"")+row.name,String(row.id)));}
async function loadCategories(){if(!selectedFamilyId)return;$("categories-loading").classList.remove("hidden");clearNotice("categories-notice");try{const params=new URLSearchParams({family_id:String(selectedFamilyId),include_inactive:String($("category-include-inactive").checked)});if($("category-filter-type").value)params.set("category_type",$("category-filter-type").value);const result=await api("/categories?"+params.toString());categoryRows=result.categories||[];renderCategories();}catch(error){categoryRows=[];renderCategories();notice("categories-notice","分類載入失敗："+error.message,"error");}finally{$("categories-loading").classList.add("hidden");}}
function openCategoryForm(row=null){editingCategoryId=row?row.id:null;$("category-form").reset();$("category-form-title").textContent=row?"編輯分類":"新增分類";$("category-submit").textContent=row?"儲存修改":"新增分類";$("category-type").disabled=Boolean(row);$("category-type").value=row?row.category_type:($("category-filter-type").value||"expense");populateCategoryParents($("category-type").value,row?row.id:null);$("category-parent").value=row&&row.parent_id?String(row.parent_id):"";$("category-name").value=row?row.name:"";$("category-sort-order").value=row?String(row.sort_order):"0";$("category-icon").value=row&&row.icon?row.icon:"";$("category-color").value=row&&row.color?row.color:"";$("category-note").value=row&&row.note?row.note:"";$("category-form-panel").classList.remove("hidden");$("category-form-panel").scrollIntoView({behavior:"smooth",block:"center"});}
async function openCategories(){if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理收支分類。","error");return;}$("categories-view").classList.remove("hidden");$("categories-view").scrollIntoView({behavior:"smooth",block:"start"});await loadCategories();}
$("open-categories").addEventListener("click",openCategories);$("close-categories").addEventListener("click",()=>$("categories-view").classList.add("hidden"));$("add-category-button").addEventListener("click",()=>openCategoryForm());$("category-cancel").addEventListener("click",()=>{$("category-form-panel").classList.add("hidden");editingCategoryId=null;});$("refresh-categories").addEventListener("click",loadCategories);$("category-filter-type").addEventListener("change",loadCategories);$("category-include-inactive").addEventListener("change",loadCategories);$("category-type").addEventListener("change",()=>populateCategoryParents($("category-type").value,editingCategoryId));
$("category-form").addEventListener("submit",async event=>{event.preventDefault();const payload={category_type:$("category-type").value,name:$("category-name").value.trim(),parent_id:$("category-parent").value?Number($("category-parent").value):null,sort_order:Number($("category-sort-order").value),icon:$("category-icon").value.trim()||null,color:$("category-color").value.trim()||null,note:$("category-note").value.trim()||null};try{const path="/categories"+(editingCategoryId?"/"+editingCategoryId:"")+"?family_id="+selectedFamilyId;await api(path,{method:editingCategoryId?"PATCH":"POST",body:JSON.stringify(payload)});$("category-form-panel").classList.add("hidden");editingCategoryId=null;notice("categories-notice","分類已成功儲存。");await loadCategories();}catch(error){notice("categories-notice","儲存分類失敗："+error.message,"error");}});

/* G-02-14: secure attachments and OCR review */
let attachmentRecords = [], selectedAttachment = null, currentOcrTask = null;
function selectedAttachmentTarget() {
  const id = Number($("attachment-target-record").value);
  return attachmentRecords.find(row => row.id === id) || null;
}
function renderAttachmentRows(rows) {
  const host=$("attachments-list");host.replaceChildren();$("attachments-empty").classList.toggle("hidden",rows.length>0);$("attachments-count").textContent=rows.length+" 個附件";
  for(const row of rows) {
    const card=document.createElement("article");card.className="attachment-admin-card";
    const info=document.createElement("div");info.className="attachment-admin-info";
    const name=document.createElement("strong");name.textContent=row.original_filename;
    const meta=document.createElement("p");meta.className="tiny muted";meta.textContent=(row.content_type||"圖片")+" · "+Math.ceil((row.file_size||0)/1024)+" KB · "+(row.created_at?new Date(row.created_at).toLocaleString("zh-TW",{hour12:false}):"時間未知")+(row.is_voided?" · 已作廢":"");
    info.append(name,meta);card.append(info);
    const actions=document.createElement("div");actions.className="attachment-admin-actions";
    if(!row.is_voided) {
      const view=document.createElement("button");view.type="button";view.className="secondary small";view.textContent="查看圖片";view.addEventListener("click",()=>viewAttachment(row));
      const ocr=document.createElement("button");ocr.type="button";ocr.className="secondary small";ocr.textContent="OCR 辨識";ocr.addEventListener("click",()=>startAttachmentOcr(row));
      const voidButton=document.createElement("button");voidButton.type="button";voidButton.className="secondary small";voidButton.textContent="作廢附件";voidButton.addEventListener("click",async()=>{if(!window.confirm("確定作廢附件「"+row.original_filename+"」？原始檔案會保留。"))return;try{await api("/attachments/"+row.id+"?family_id="+selectedFamilyId,{method:"DELETE"});notice("attachments-notice","附件已作廢，檔案本體仍保留。");await loadAttachments();}catch(error){notice("attachments-notice",error.message,"error");}});
      actions.append(view,ocr,voidButton);
    } else {const tag=document.createElement("span");tag.className="tiny muted";tag.textContent="已作廢（保留原始檔案）";actions.append(tag);}
    card.append(actions);host.append(card);
  }
}
async function loadAttachmentTargets() {
  const type=$("attachment-target-type").value,select=$("attachment-target-record"),previous=select.value;
  select.replaceChildren(new Option("請選擇資料",""));
  try {
    const result=await api(type==="bill"?"/bills?family_id="+selectedFamilyId+"&limit=200":"/transactions?family_id="+selectedFamilyId+"&limit=200");
    attachmentRecords=type==="bill"?(result.bills||[]):(result.transactions||[]);
    for(const row of attachmentRecords) {
      const label=type==="bill"?(row.bill_date+" · "+row.title+" · "+row.total_amount+" "+row.currency_code):(String(row.transaction_date||"").slice(0,10)+" · "+(row.description||row.transaction_type)+" · "+row.amount+" "+row.currency_code);
      select.add(new Option(label,String(row.id)));
    }
    if(previous&&attachmentRecords.some(row=>String(row.id)===previous))select.value=previous;
    $("attachment-upload-panel").classList.toggle("hidden",!select.value);
  } catch(error) { attachmentRecords=[];$("attachment-upload-panel").classList.add("hidden");notice("attachments-notice","帳單／交易清單載入失敗："+error.message,"error"); }
}
async function loadAttachments() {
  const target=selectedAttachmentTarget();
  if(!target){$("attachments-list").replaceChildren();$("attachments-empty").classList.add("hidden");$("attachments-count").textContent="0 個附件";$("attachment-upload-panel").classList.add("hidden");return;}
  $("attachment-upload-panel").classList.remove("hidden");$("attachments-loading").classList.remove("hidden");clearNotice("attachments-notice");
  const type=$("attachment-target-type").value,params=new URLSearchParams({family_id:String(selectedFamilyId)});
  params.set(type==="bill"?"bill_id":"transaction_id",String(target.id));
  try {const result=await api("/attachments?"+params.toString());renderAttachmentRows(result.attachments||[]);}
  catch(error){renderAttachmentRows([]);notice("attachments-notice","附件載入失敗："+error.message,"error");}
  finally{$("attachments-loading").classList.add("hidden");}
}
async function viewAttachment(row) {
  try {const response=await fetch("/attachments/"+row.id+"/content?family_id="+selectedFamilyId,{headers:token()?{Authorization:"Bearer "+token()}:{}});
    let data={};if(!response.ok){try{data=await response.json();}catch{}throw new Error(data.detail||"無法讀取附件");}
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.target="_blank";link.rel="noopener";link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
  } catch(error){notice("attachments-notice","附件讀取失敗："+error.message,"error");}
}
function renderOcrTask(task) {
  currentOcrTask=task;$("ocr-result-panel").classList.remove("hidden");
  const labels={queued:"排隊中",processing:"辨識中",succeeded:"辨識成功",failed:"辨識失敗",confirmed:"已人工確認"};
  $("ocr-result-status").textContent=(labels[task.status]||task.status)+" · 嘗試 "+task.attempts+"/5"+(task.error_message?" · "+task.error_message:"");
  $("ocr-extracted-text").textContent=task.extracted_text||"目前沒有辨識文字。";
  const host=$("ocr-suggested-fields");host.replaceChildren();
  if(task.suggested_fields){const pre=document.createElement("pre");pre.textContent=JSON.stringify(task.suggested_fields,null,2);host.append(pre);}
  if(task.status==="succeeded") {
    const confirm=document.createElement("button");confirm.type="button";confirm.className="primary small";confirm.textContent="我已核對，確認辨識結果";confirm.addEventListener("click",async()=>{try{const result=await api("/ocr/tasks/"+task.id+"/confirm?family_id="+selectedFamilyId,{method:"POST"});renderOcrTask(result.task);notice("attachments-notice","OCR 結果已確認；正式帳單與交易未被修改。");}catch(error){notice("attachments-notice",error.message,"error");}});
    host.append(confirm);
  } else if(task.status==="failed"&&task.attempts<5) {
    const retry=document.createElement("button");retry.type="button";retry.className="secondary small";retry.textContent="重新排入辨識";retry.addEventListener("click",async()=>{try{const result=await api("/ocr/tasks/"+task.id+"/retry?family_id="+selectedFamilyId,{method:"POST"});await processOcrTask(result.task);}catch(error){notice("attachments-notice",error.message,"error");}});
    host.append(retry);
  }
}
async function processOcrTask(task) {
  try {const result=await api("/ocr/tasks/"+task.id+"/process?family_id="+selectedFamilyId,{method:"POST"});renderOcrTask(result.task);notice("attachments-notice",result.message||"OCR 作業已完成。");}
  catch(error){notice("attachments-notice","OCR 執行失敗："+error.message,"error");try{const latest=await api("/ocr/tasks/"+task.id+"?family_id="+selectedFamilyId);renderOcrTask(latest);}catch{}}
}
async function startAttachmentOcr(row) {
  selectedAttachment=row;$("ocr-result-panel").classList.remove("hidden");$("ocr-result-status").textContent="正在建立或讀取 OCR 任務…";$("ocr-extracted-text").textContent="";$("ocr-suggested-fields").replaceChildren();
  try {
    const result=await api("/ocr/tasks?attachment_id="+row.id+"&family_id="+selectedFamilyId,{method:"POST"});
    const task=result.task;renderOcrTask(task);
    if(task.status==="queued")await processOcrTask(task);
  } catch(error){notice("attachments-notice","無法建立 OCR 任務："+error.message,"error");}
}
async function openAttachments() {
  if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再管理附件。","error");return;}
  $("attachments-view").classList.remove("hidden");$("attachments-view").scrollIntoView({behavior:"smooth",block:"start"});await loadAttachmentTargets();await loadAttachments();
}
$("open-attachments").addEventListener("click",openAttachments);
$("close-attachments").addEventListener("click",()=>$("attachments-view").classList.add("hidden"));
$("refresh-attachments").addEventListener("click",async()=>{await loadAttachmentTargets();await loadAttachments();});
$("attachment-target-type").addEventListener("change",async()=>{await loadAttachmentTargets();await loadAttachments();});
$("attachment-target-record").addEventListener("change",loadAttachments);
$("attachment-upload-form").addEventListener("submit",async event=>{
  event.preventDefault();const target=selectedAttachmentTarget(),file=$("attachment-file").files[0];if(!target||!file)return;
  if(file.size>10*1024*1024){notice("attachments-notice","圖片大小不可超過 10 MB。","error");return;}
  const formData=new FormData();formData.append("file",file);
  const type=$("attachment-target-type").value,params=new URLSearchParams({family_id:String(selectedFamilyId)});params.set(type==="bill"?"bill_id":"transaction_id",String(target.id));
  $("attachment-upload-submit").disabled=true;
  try {
    const response=await fetch("/attachments?"+params.toString(),{method:"POST",headers:token()?{Authorization:"Bearer "+token()}: {},body:formData});
    let data={};try{data=await response.json();}catch{}if(!response.ok)throw new Error(data.detail||"上傳附件失敗");
    $("attachment-upload-form").reset();notice("attachments-notice","附件已成功上傳。");await loadAttachments();
  } catch(error){notice("attachments-notice","上傳附件失敗："+error.message,"error");}
  finally{$("attachment-upload-submit").disabled=false;}
});

/* G-02-15: notifications and export management */
const exportColumns={
 transactions:[["id","交易編號"],["occurred_on","日期"],["type","類型"],["amount","金額"],["currency_code","幣別"],["description","說明"],["category_id","分類 ID"],["account_id","帳戶 ID"],["created_by","建立者 ID"]],
 bills:[["id","帳單編號"],["bill_number","帳單號碼"],["title","帳單名稱"],["bill_date","帳單日期"],["due_date","到期日"],["original_amount","金額"],["currency_code","幣別"],["status","狀態"],["created_by","建立者 ID"]]
};
let exportTemplates=[],exportSchedules=[],exportRuns=[],editingExportTemplate=null;
const exportStatusLabel={draft:"草稿",published:"已發布",disabled:"已停用",queued:"排隊中",running:"執行中",succeeded:"成功",failed:"失敗",revoked:"已撤銷"};
function renderExportColumnChoices(selected=[]){
 const host=$("export-template-columns");host.replaceChildren();
 for(const [value,label] of exportColumns[$("export-template-dataset").value]){
  const wrap=document.createElement("label");wrap.className="export-column-option";
  const input=document.createElement("input");input.type="checkbox";input.value=value;input.checked=selected.includes(value);
  const text=document.createElement("span");text.textContent=label+"（"+value+"）";wrap.append(input,text);host.append(wrap);
 }
}
function renderExportTemplates(){
 const host=$("export-templates-list");host.replaceChildren();$("export-templates-empty").classList.toggle("hidden",exportTemplates.length>0);
 for(const item of exportTemplates){
  const card=document.createElement("article");card.className="export-admin-card";
  const info=document.createElement("div");const title=document.createElement("strong");title.textContent=item.name;
  const meta=document.createElement("p");meta.className="tiny muted";meta.textContent=(item.config.dataset==="transactions"?"交易資料":"帳單資料")+" · v"+item.version+" · "+(exportStatusLabel[item.status]||item.status)+" · "+(item.config.columns||[]).length+" 欄";
  info.append(title,meta);if(item.description){const desc=document.createElement("p");desc.className="tiny muted";desc.textContent=item.description;info.append(desc);}card.append(info);
  const actions=document.createElement("div");actions.className="export-admin-actions";
  const edit=document.createElement("button");edit.type="button";edit.className="secondary small";edit.textContent="編輯";edit.disabled=item.status==="disabled";edit.addEventListener("click",()=>openExportTemplateForm(item));actions.append(edit);
  if(item.status==="draft"){
   const publish=document.createElement("button");publish.type="button";publish.className="primary small";publish.textContent="發布";publish.addEventListener("click",async()=>{if(!window.confirm("發布範本「"+item.name+"」第 "+item.version+" 版？"))return;try{await api("/exports/templates/"+item.id+"/publish?family_id="+selectedFamilyId+"&expected_version="+item.version,{method:"POST"});notice("notifications-exports-notice","匯出範本已發布。");await loadExportWorkspace();}catch(error){notice("notifications-exports-notice",error.message,"error");}});actions.append(publish);
  }
  if(item.status==="published"){
   const run=document.createElement("button");run.type="button";run.className="primary small";run.textContent="立即匯出";run.addEventListener("click",async()=>{if(!window.confirm("立即執行「"+item.name+"」並產生 CSV 檔案？"))return;try{await api("/exports/templates/"+item.id+"/run?family_id="+selectedFamilyId,{method:"POST"});notice("notifications-exports-notice","匯出已完成，請至執行紀錄下載。");await loadExportWorkspace();}catch(error){notice("notifications-exports-notice","匯出失敗："+error.message,"error");}});actions.append(run);
   const disable=document.createElement("button");disable.type="button";disable.className="secondary small";disable.textContent="停用";disable.addEventListener("click",async()=>{if(!window.confirm("停用範本後，相關定期排程也會停止。確定繼續？"))return;try{await api("/exports/templates/"+item.id+"/disable?family_id="+selectedFamilyId+"&expected_version="+item.version,{method:"POST"});notice("notifications-exports-notice","範本已停用。");await loadExportWorkspace();}catch(error){notice("notifications-exports-notice",error.message,"error");}});actions.append(disable);
  }
  card.append(actions);host.append(card);
 }
 const select=$("export-schedule-template"),previous=select.value;select.replaceChildren(new Option("請選擇已發布範本",""));
 for(const item of exportTemplates.filter(x=>x.status==="published"))select.add(new Option(item.name+"（v"+item.version+"）",String(item.id)));
 if(previous&&Array.from(select.options).some(x=>x.value===previous))select.value=previous;
}
function openExportTemplateForm(item=null){
 editingExportTemplate=item; $("export-template-form").reset();$("export-template-form-title").textContent=item?"編輯範本草稿":"新增匯出範本";
 $("export-template-submit").textContent=item?"儲存新版本草稿":"建立草稿";
 $("export-template-name").value=item?item.name:"";$("export-template-description").value=item?(item.description||""):"";
 $("export-template-dataset").disabled=Boolean(item);$("export-template-dataset").value=item?item.config.dataset:"transactions";
 renderExportColumnChoices(item?item.config.columns:[]);$("export-template-form-panel").classList.remove("hidden");
}
async function loadNotificationItems(){
 const result=await api("/notifications?family_id="+selectedFamilyId+"&limit=100");
 $("notification-unread-count").textContent="未讀 "+result.unread+" 則";
 const host=$("notifications-list");host.replaceChildren();$("notifications-empty").classList.toggle("hidden",(result.notifications||[]).length>0);
 for(const item of result.notifications||[]){
  const card=document.createElement("article");card.className="notification-admin-card"+(item.read_at?"":" notification-unread");
  const body=document.createElement("div");const title=document.createElement("strong");title.textContent=item.title;
  const desc=document.createElement("p");desc.className="tiny muted";desc.textContent=item.body||"";
  const meta=document.createElement("span");meta.className="tiny muted";meta.textContent=(item.created_at?new Date(item.created_at).toLocaleString("zh-TW",{hour12:false}):"時間未知")+" · "+item.notification_type;
  body.append(title,desc,meta);card.append(body);
  if(!item.read_at){const read=document.createElement("button");read.type="button";read.className="secondary small";read.textContent="標記已讀";read.addEventListener("click",async()=>{try{await api("/notifications/"+item.id+"/read?family_id="+selectedFamilyId,{method:"POST"});await loadNotificationItems();}catch(error){notice("notifications-exports-notice",error.message,"error");}});card.append(read);}
  host.append(card);
 }
}
async function loadExportTemplates(){
 const result=await api("/exports/templates?family_id="+selectedFamilyId);exportTemplates=result.templates||[];renderExportTemplates();
}
async function loadExportSchedules(){
 const result=await api("/exports/schedules?family_id="+selectedFamilyId);exportSchedules=result.schedules||[];
 const host=$("export-schedules-list");host.replaceChildren();$("export-schedules-empty").classList.toggle("hidden",exportSchedules.length>0);
 for(const item of exportSchedules){
  const card=document.createElement("article");card.className="export-admin-card";const info=document.createElement("div");
  const title=document.createElement("strong");title.textContent=item.name;const meta=document.createElement("p");meta.className="tiny muted";
  const frequency={daily:"每日",weekly:"每週",monthly:"每月"}[item.frequency]||item.frequency;
  meta.textContent=frequency+" · "+String(item.local_hour).padStart(2,"0")+":"+String(item.local_minute).padStart(2,"0")+"（台灣時間） · 下次："+new Date(item.next_run_at).toLocaleString("zh-TW",{hour12:false})+" · "+(item.enabled?"啟用":"已停用");
  info.append(title,meta);card.append(info);
  if(item.enabled){const disable=document.createElement("button");disable.type="button";disable.className="secondary small";disable.textContent="停用排程";disable.addEventListener("click",async()=>{if(!window.confirm("確定停用此排程？"))return;try{await api("/exports/schedules/"+item.id+"/disable?family_id="+selectedFamilyId,{method:"POST"});await loadExportSchedules();}catch(error){notice("notifications-exports-notice",error.message,"error");}});card.append(disable);}
  host.append(card);
 }
}
async function loadExportRuns(){
 const [result,dashboard]=await Promise.all([api("/exports/runs?family_id="+selectedFamilyId+"&limit=100"),api("/exports/dashboard?family_id="+selectedFamilyId)]);
 exportRuns=result.runs||[];$("export-runs-summary").textContent="共 "+result.total+" 筆 · 失敗 "+(dashboard.alert_count||0)+" 筆";
 const host=$("export-runs-list");host.replaceChildren();$("export-runs-empty").classList.toggle("hidden",exportRuns.length>0);
 for(const item of exportRuns){
  const card=document.createElement("article");card.className="export-admin-card";const info=document.createElement("div");
  const title=document.createElement("strong");title.textContent="匯出 #"+item.id+" · "+(exportStatusLabel[item.status]||item.status);
  const meta=document.createElement("p");meta.className="tiny muted";meta.textContent="範本 #"+item.template_id+" · v"+item.template_version+" · "+new Date(item.created_at).toLocaleString("zh-TW",{hour12:false})+(item.file_size?" · "+Math.ceil(item.file_size/1024)+" KB":"")+(item.error_code?" · "+item.error_code:"");
  info.append(title,meta);card.append(info);
  if(item.status==="succeeded"){const download=document.createElement("button");download.type="button";download.className="primary small";download.textContent="下載 CSV";download.addEventListener("click",()=>downloadExportRun(item.id));card.append(download);}
  host.append(card);
 }
}
async function downloadExportRun(id){
 try{const response=await fetch("/exports/runs/"+id+"/download?family_id="+selectedFamilyId,{headers:token()?{Authorization:"Bearer "+token()}:{}});
  if(!response.ok){let data={};try{data=await response.json();}catch{}throw new Error(data.detail||"下載失敗");}
  const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="family-export-"+id+".csv";a.click();URL.revokeObjectURL(url);
 }catch(error){notice("notifications-exports-notice","下載失敗："+error.message,"error");}
}
async function loadExportWorkspace(){await Promise.all([loadNotificationItems(),loadExportTemplates(),loadExportSchedules(),loadExportRuns()]);}
async function openNotificationsExports(){if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭。","error");return;}$("notifications-exports-view").classList.remove("hidden");$("notifications-exports-view").scrollIntoView({behavior:"smooth",block:"start"});try{await loadExportWorkspace();}catch(error){notice("notifications-exports-notice","載入通知或匯出資料失敗："+error.message,"error");}}
$("open-notifications-exports").addEventListener("click",openNotificationsExports);
$("close-notifications-exports").addEventListener("click",()=>$("notifications-exports-view").classList.add("hidden"));
$("refresh-notifications-exports").addEventListener("click",openNotificationsExports);
$("new-export-template").addEventListener("click",()=>openExportTemplateForm());
$("export-template-cancel").addEventListener("click",()=>{$("export-template-form-panel").classList.add("hidden");editingExportTemplate=null;});
$("export-template-dataset").addEventListener("change",()=>renderExportColumnChoices());
$("export-template-form").addEventListener("submit",async event=>{
 event.preventDefault();const columns=Array.from($("export-template-columns").querySelectorAll("input:checked")).map(x=>x.value);
 if(!columns.length){notice("notifications-exports-notice","請至少選擇一個匯出欄位。","error");return;}
 const body={name:$("export-template-name").value.trim(),description:$("export-template-description").value.trim()||null,config:{dataset:$("export-template-dataset").value,columns}};
 try{const path="/exports/templates"+(editingExportTemplate?"/"+editingExportTemplate.id:"")+"?family_id="+selectedFamilyId;
  if(editingExportTemplate)body.expected_version=editingExportTemplate.version;
  await api(path,{method:editingExportTemplate?"PUT":"POST",body:JSON.stringify(body)});
  $("export-template-form-panel").classList.add("hidden");editingExportTemplate=null;notice("notifications-exports-notice","匯出範本草稿已儲存。");await loadExportWorkspace();
 }catch(error){notice("notifications-exports-notice","儲存範本失敗："+error.message,"error");}
});
$("export-schedule-frequency").addEventListener("change",()=>{$("export-schedule-weekday-wrap").classList.toggle("hidden",$("export-schedule-frequency").value!=="weekly");$("export-schedule-monthday-wrap").classList.toggle("hidden",$("export-schedule-frequency").value!=="monthly");});
$("export-schedule-form").addEventListener("submit",async event=>{
 event.preventDefault();const frequency=$("export-schedule-frequency").value,body={template_id:Number($("export-schedule-template").value),name:$("export-schedule-name").value.trim(),frequency,local_hour:Number($("export-schedule-hour").value),local_minute:Number($("export-schedule-minute").value),enabled:true};
 if(frequency==="weekly")body.weekday=Number($("export-schedule-weekday").value);if(frequency==="monthly")body.monthday=Number($("export-schedule-monthday").value);
 try{await api("/exports/schedules?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(body)});$("export-schedule-form").reset();notice("notifications-exports-notice","定期匯出排程已建立。");await loadExportSchedules();}
 catch(error){notice("notifications-exports-notice","建立排程失敗："+error.message,"error");}
});

/* G-03-01: staged bank statement CSV import */
let importCsvFile=null,importCsvHeaders=[],importCsvSamples=[],selectedImportBatchId=null;
const importFields=[["date","交易日期",true],["amount","金額",true],["description","交易說明",true],["type","交易類型",false],["currency_code","幣別",false],["external_reference","銀行交易序號",false]];
function renderImportMapping(){
 const host=$("bank-import-mapping");host.replaceChildren();
 for(const [key,label,required] of importFields){
  const wrap=document.createElement("label");wrap.className="field";wrap.textContent=label+(required?"（必填）":"（選填）");
  const select=document.createElement("select");select.dataset.importField=key;select.required=required;select.add(new Option(required?"請選擇欄位":"不使用",""));
  for(const header of importCsvHeaders)select.add(new Option(header,header));
  const guesses={date:/date|日期|交易日|時間/i,amount:/amount|金額|交易金額|支出金額/i,description:/description|memo|摘要|說明|交易內容/i,type:/type|類型|收支|借貸/i,currency_code:/currency|幣別/i,external_reference:/reference|序號|交易序號|交易編號/i};
  const guess=importCsvHeaders.find(x=>guesses[key].test(x));if(guess)select.value=guess;
  wrap.append(select);host.append(wrap);
 }
 const sample=$("bank-import-sample");sample.replaceChildren();
 const title=document.createElement("p");title.className="tiny muted";title.textContent="檔案："+(importCsvFile?importCsvFile.name:"")+" · 共 "+importCsvSamples.length+" 筆樣本預覽";sample.append(title);
 const pre=document.createElement("pre");pre.className="import-sample-data";pre.textContent=JSON.stringify(importCsvSamples.slice(0,3),null,2);sample.append(pre);
 $("bank-import-mapping-panel").classList.remove("hidden");
}
async function loadBankImportAccounts(){
 const result=await api("/accounts?family_id="+selectedFamilyId);const select=$("bank-import-account");select.replaceChildren(new Option("請選擇帳戶",""));
 for(const account of result.accounts||[])select.add(new Option(account.name+"（"+account.currency_code+"）",String(account.id)));
}
async function loadBankImportBatches(){
 const result=await api("/imports/batches?family_id="+selectedFamilyId+"&limit=100");
 const host=$("bank-import-batches");host.replaceChildren();$("bank-import-batches-empty").classList.toggle("hidden",(result.batches||[]).length>0);
 const labels={previewed:"待確認",confirmed:"已確認匯入",cancelled:"已取消"};
 for(const item of result.batches||[]){
  const card=document.createElement("article");card.className="import-batch-card";
  const info=document.createElement("div");const title=document.createElement("strong");title.textContent=item.source_filename;
  const meta=document.createElement("p");meta.className="tiny muted";meta.textContent="批次 #"+item.id+" · "+(labels[item.status]||item.status)+" · 總計 "+item.total_rows+" 筆 · 待確認 "+item.ready_rows+" · 重複 "+item.duplicate_rows+" · 錯誤 "+item.invalid_rows+" · 已匯入對帳 "+item.imported_rows;
  info.append(title,meta);card.append(info);
  const view=document.createElement("button");view.type="button";view.className="secondary small";view.textContent="查看明細";view.addEventListener("click",()=>loadBankImportBatch(item.id));card.append(view);host.append(card);
 }
}
async function loadBankImportBatch(id){
 try{const result=await api("/imports/batches/"+id+"?family_id="+selectedFamilyId+"&limit=500");const batch=result.batch;selectedImportBatchId=id;
  $("bank-import-detail-title").textContent="匯入批次 #"+id+" · "+batch.source_filename;
  $("bank-import-counts").textContent="狀態："+batch.status+" · 總計 "+batch.total_rows+" · 待確認 "+batch.ready_rows+" · 重複 "+batch.duplicate_rows+" · 錯誤 "+batch.invalid_rows+" · 已匯入對帳 "+batch.imported_rows;
  const body=$("bank-import-rows");body.replaceChildren();
  const statusLabels={ready:"待確認",duplicate:"疑似重複，仍保留對帳",invalid:"格式錯誤",imported:"已匯入對帳",skipped:"已略過"};
  for(const row of result.rows||[]){
   const tr=document.createElement("tr");
   for(const value of [row.row_number,row.transaction_date?new Date(row.transaction_date).toLocaleDateString("zh-TW"):"—",row.transaction_type==="income"?"收入":row.transaction_type==="expense"?"支出":"—",row.amount?(row.amount+" "+(row.currency_code||"")):"—",row.description||"—",(statusLabels[row.status]||row.status)+(row.error_message?" · "+row.error_message:"")]){
    const td=document.createElement("td");td.textContent=String(value);tr.append(td);
   }body.append(tr);
  }
  $("bank-import-confirm").disabled=batch.status!=="previewed"||(batch.ready_rows+batch.duplicate_rows)===0;
  $("bank-import-void").disabled=batch.status!=="previewed";
  $("bank-import-detail-panel").classList.remove("hidden");$("bank-import-detail-panel").scrollIntoView({behavior:"smooth",block:"start"});
 }catch(error){notice("bank-imports-notice","載入匯入明細失敗："+error.message,"error");}
}
async function openBankImports(){
 if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭。","error");return;}
 $("bank-imports-view").classList.remove("hidden");$("bank-imports-view").scrollIntoView({behavior:"smooth",block:"start"});
 try{await Promise.all([loadBankImportAccounts(),loadBankImportBatches()]);}catch(error){notice("bank-imports-notice","載入匯入功能失敗："+error.message,"error");}
}
$("open-bank-imports").addEventListener("click",openBankImports);
$("close-bank-imports").addEventListener("click",()=>$("bank-imports-view").classList.add("hidden"));
$("refresh-bank-imports").addEventListener("click",async()=>{await loadBankImportAccounts();await loadBankImportBatches();});
$("bank-import-inspect-form").addEventListener("submit",async event=>{
 event.preventDefault();importCsvFile=$("bank-import-file").files[0];if(!importCsvFile)return;
 if(importCsvFile.size>10*1024*1024){notice("bank-imports-notice","CSV 檔案不可超過 10 MB。","error");return;}
 const form=new FormData();form.append("file",importCsvFile);
 try{const response=await fetch("/imports/inspect?family_id="+selectedFamilyId,{method:"POST",headers:token()?{Authorization:"Bearer "+token()}: {},body:form});
  let data={};try{data=await response.json();}catch{}if(!response.ok)throw new Error(data.detail||"讀取 CSV 失敗");
  importCsvHeaders=data.headers||[];importCsvSamples=data.sample_rows||[];renderImportMapping();notice("bank-imports-notice","已讀取 CSV 欄位，請確認欄位對應。");
 }catch(error){notice("bank-imports-notice","讀取 CSV 失敗："+error.message,"error");}
});
$("bank-import-upload").addEventListener("click",async()=>{
 if(!importCsvFile||!$("bank-import-account").value){notice("bank-imports-notice","請先選擇帳戶及 CSV 檔案。","error");return;}
 const mapping={};for(const select of $("bank-import-mapping").querySelectorAll("select"))if(select.value)mapping[select.dataset.importField]=select.value;
 for(const key of ["date","amount","description"])if(!mapping[key]){notice("bank-imports-notice","日期、金額及交易說明欄位皆須指定。","error");return;}
 const form=new FormData();form.append("file",importCsvFile);form.append("mapping",JSON.stringify(mapping));
 $("bank-import-upload").disabled=true;
 try{const response=await fetch("/imports/batches?family_id="+selectedFamilyId+"&account_id="+$("bank-import-account").value,{method:"POST",headers:token()?{Authorization:"Bearer "+token()}: {},body:form});
  let data={};try{data=await response.json();}catch{}if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:(data.detail?.message||"建立匯入預覽失敗"));
  notice("bank-imports-notice","匯入預覽已建立；尚未新增正式交易。");$("bank-import-mapping-panel").classList.add("hidden");$("bank-import-inspect-form").reset();importCsvFile=null;await loadBankImportBatches();await loadBankImportBatch(data.batch.id);
 }catch(error){notice("bank-imports-notice","建立匯入預覽失敗："+error.message,"error");}
 finally{$("bank-import-upload").disabled=false;}
});
$("bank-import-confirm").addEventListener("click",async()=>{
 const createTransactions=$("bank-import-create-transactions").checked;
 const prompt=createTransactions
  ?"確認匯入銀行明細，並將所有有效且非重複的資料建立為正式交易？疑似重複資料仍會保留供對帳。"
  :"確認只匯入銀行對帳明細，不自動新增正式交易？這是避免重複記帳的建議方式。";
 if(!selectedImportBatchId||!window.confirm(prompt))return;
 try{
  const result=await api("/imports/batches/"+selectedImportBatchId+"/confirm?family_id="+selectedFamilyId+"&create_transactions="+(createTransactions?"true":"false"),{method:"POST"});
  notice("bank-imports-notice",result.message||"銀行明細已確認。");
  $("bank-import-create-transactions").checked=false;
  await loadBankImportBatches();await loadBankImportBatch(selectedImportBatchId);
 }catch(error){notice("bank-imports-notice","確認匯入失敗："+error.message,"error");}
});
$("bank-import-void").addEventListener("click",async()=>{
 if(!selectedImportBatchId||!window.confirm("取消此匯入批次？這只會取消暫存預覽，不會修改正式交易。"))return;
 try{await api("/imports/batches/"+selectedImportBatchId+"/void?family_id="+selectedFamilyId,{method:"POST"});notice("bank-imports-notice","匯入批次已取消。");await loadBankImportBatches();await loadBankImportBatch(selectedImportBatchId);}
 catch(error){notice("bank-imports-notice","取消批次失敗："+error.message,"error");}
});
