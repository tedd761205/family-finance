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
async function loadFamilies(){const result=await api("/families/mine");$("family-count").textContent=result.total+" 個家庭";const list=$("family-list");list.replaceChildren();$("empty-family").classList.toggle("hidden",result.total!==0);if(!selectedFamilyId&&result.families.length){selectedFamilyId=result.families[0].family_id;}for(const family of result.families){const card=document.createElement("button");card.type="button";card.className="family-card"+(selectedFamilyId===family.family_id?" selected":"");const title=document.createElement("strong");title.textContent=family.family_name;const meta=document.createElement("span");meta.textContent=family.currency+" · 家庭成員";card.append(title,meta);card.addEventListener("click",async()=>{selectedFamilyId=family.family_id;for(const node of list.children)node.classList.remove("selected");card.classList.add("selected");notice("notice-app","已切換至「"+family.family_name+"」。","success");if(!$("accounts-view").classList.contains("hidden")){await loadAccounts();}if(!$("transactions-view").classList.contains("hidden")){await showTransactions();}});list.append(card);}}
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
  } catch(error) {
    notice("transaction-notice","收支紀錄載入失敗："+error.message,"error");
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
    await loadTransactions();
    await loadAccounts();
    notice("transaction-notice",wasEditing?"收支紀錄已更新。":"收支紀錄已新增。","success");
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
    await loadTransactions();
    await loadAccounts();
    notice("transaction-notice","收支紀錄已作廢，歷史資料仍會保留。","success");
  } catch(error) {
    notice("transaction-notice",error.message,"error");
  }
}
