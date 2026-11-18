const API = "";
const TOKEN_KEY = "family_finance_access_token";
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
async function api(path, options={}){const headers={"Content-Type":"application/json",...(options.headers||{})};if(token())headers.Authorization="Bearer "+token();const response=await fetch(API+path,{...options,headers});let data={};try{data=await response.json();}catch{}if(!response.ok){if(response.status===401&&token()){sessionStorage.removeItem(TOKEN_KEY);showAuth();}throw new Error(data.detail||"目前無法完成操作，請稍後再試。");}return data;}
function setMode(next){mode=next;$("login-tab").classList.toggle("active",mode==="login");$("register-tab").classList.toggle("active",mode==="register");$("name-wrap").classList.toggle("hidden",mode!=="register");$("form-title").textContent=mode==="login"?"歡迎回來":"建立家庭帳號";$("form-desc").textContent=mode==="login"?"使用 Email 與密碼登入家庭記帳系統。":"建立帳號後即可建立家庭或加入家人邀請。";$("submit-auth").textContent=mode==="login"?"登入":"建立帳號";$("password").autocomplete=mode==="login"?"current-password":"new-password";clearNotice("notice");}
function showAuth(){currentUser=null;$("auth-view").classList.remove("hidden");$("app-view").classList.add("hidden");}
function showApp(){$("auth-view").classList.add("hidden");$("app-view").classList.remove("hidden");}
async function loadApp(){try{currentUser=await api("/auth/me");}catch(error){showAuth();notice("notice",error.message,"error");return;}$("user-greeting").textContent=currentUser.display_name+"（"+currentUser.email+"）";showApp();try{await loadFamilies();}catch(error){notice("notice-app","已登入，但家庭清單載入失敗："+error.message,"error");}}
async function loadFamilies(){const result=await api("/families/mine");$("family-count").textContent=result.total+" 個家庭";const list=$("family-list");list.replaceChildren();$("empty-family").classList.toggle("hidden",result.total!==0);if(!selectedFamilyId&&result.families.length){selectedFamilyId=result.families[0].family_id;}for(const family of result.families){const card=document.createElement("button");card.type="button";card.className="family-card"+(selectedFamilyId===family.family_id?" selected":"");const title=document.createElement("strong");title.textContent=family.family_name;const meta=document.createElement("span");meta.textContent=family.currency+" · 家庭成員";card.append(title,meta);card.addEventListener("click",async()=>{selectedFamilyId=family.family_id;for(const node of list.children)node.classList.remove("selected");card.classList.add("selected");notice("notice-app","已切換至「"+family.family_name+"」。","success");if(!$("accounts-view").classList.contains("hidden")){await loadAccounts();}if(!$("transactions-view").classList.contains("hidden")){await showTransactions();}if(!$("transfers-view").classList.contains("hidden")){await showTransfers();}if(!$("credit-card-payments-view").classList.contains("hidden")){await showCreditCardPayments();}});list.append(card);}}
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
$("logout-button").addEventListener("click",async()=>{let revoked=false;try{await api("/auth/logout",{method:"POST"});revoked=true;}catch{}sessionStorage.removeItem(TOKEN_KEY);selectedFamilyId=null;accounts=[];accountBalances.clear();$("accounts-view").classList.add("hidden");showAuth();setMode("login");if(revoked){notice("notice","已安全登出。","success");}else{notice("notice","已清除此瀏覽器的登入狀態，但伺服器端 Token 撤銷未確認；請確認網路連線後重新登入。","error");}});
async function init(){if(token()){await loadApp();}else{showAuth();}try{const cfg=await fetch("/app-config").then(r=>r.json());if(cfg.google_client_id){const script=document.createElement("script");script.src="https://accounts.google.com/gsi/client";script.async=true;script.defer=true;script.onload=()=>{google.accounts.id.initialize({client_id:cfg.google_client_id,callback:async(response)=>{try{const result=await api("/auth/google",{method:"POST",body:JSON.stringify({id_token:response.credential})});sessionStorage.setItem(TOKEN_KEY,result.access_token);await loadApp();}catch(error){notice("notice",error.message,"error");}}});google.accounts.id.renderButton($("google-button"),{theme:"outline",size:"large",shape:"rectangular",width:300,text:"continue_with",locale:"zh_TW"});$("google-hint").classList.add("hidden");};document.head.append(script);}}catch{}}
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
