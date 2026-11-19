/* G-03-02-06 Responsive bank and credit-card reconciliation workspace */
(function(){
  let reconciliationAccounts=[];
  let reconciliationBatches=[];
  let reconciliationSessions=[];
  let activeReconciliationSession=null;
  let activeReconciliationRows=[];
  let reconciliationSuggestions=new Map();

  const el=id=>document.getElementById(id);
  const statusLabels={draft:"草稿",in_progress:"進行中",completed:"已完成",cancelled:"已取消"};
  const rowStatusLabels={unmatched:"待核對",partially_matched:"部分核對",matched:"已核對",excluded:"已排除"};

  function reconciliationNotice(message,type="success"){
    const node=el("bank-reconciliation-notice");
    node.textContent=message;
    node.className="notice show "+type;
  }
  function clearReconciliationNotice(){
    const node=el("bank-reconciliation-notice");
    node.textContent="";
    node.className="notice";
  }
  function makeButton(label,className,handler){
    const button=document.createElement("button");
    button.type="button";
    button.className=className||"secondary small";
    button.textContent=label;
    button.addEventListener("click",handler);
    return button;
  }
  function makeText(tag,className,value){
    const node=document.createElement(tag);
    if(className)node.className=className;
    node.textContent=value??"";
    return node;
  }
  function dateLabel(value){
    if(!value)return "—";
    const date=new Date(value);
    return Number.isNaN(date.getTime())?String(value):date.toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"});
  }
  function dateShift(value,days){
    const date=new Date(value+"T12:00:00Z");
    date.setUTCDate(date.getUTCDate()+days);
    return date.toISOString().slice(0,10);
  }
  function statusClass(value){
    return "reconciliation-status reconciliation-status-"+String(value||"unknown").replace(/[^a-z_]/g,"");
  }
  function fillBatchOptions(){
    const accountId=Number(el("reconciliation-account").value||0);
    const select=el("reconciliation-batch");
    select.replaceChildren(new Option("選擇已確認的匯入批次",""));
    const matches=reconciliationBatches.filter(item=>item.status==="confirmed"&&Number(item.account_id)===accountId);
    for(const batch of matches){
      const label="#"+batch.id+" · "+(batch.source_filename||"銀行明細")+" · "+(batch.confirmed_at?dateLabel(batch.confirmed_at):"已確認")+" · "+(batch.total_rows||0)+" 筆";
      select.add(new Option(label,String(batch.id)));
    }
    if(!matches.length)select.add(new Option("此帳戶沒有已確認的匯入批次",""));
  }
  async function loadReconciliationSetup(){
    const [accountResult,batchResult]=await Promise.all([
      api("/accounts?family_id="+selectedFamilyId),
      api("/imports/batches?family_id="+selectedFamilyId+"&limit=200")
    ]);
    reconciliationAccounts=(accountResult.accounts||[]).filter(item=>item.is_active!==false);
    reconciliationBatches=batchResult.batches||[];
    const accountSelect=el("reconciliation-account");
    const previous=accountSelect.value;
    accountSelect.replaceChildren(new Option("選擇帳戶",""));
    for(const account of reconciliationAccounts){
      accountSelect.add(new Option(account.name+" · "+accountTypeLabel(account.account_type)+" · "+account.currency_code,String(account.id)));
    }
    if(previous&&reconciliationAccounts.some(item=>String(item.id)===previous))accountSelect.value=previous;
    else if(reconciliationAccounts.length)accountSelect.value=String(reconciliationAccounts[0].id);
    fillBatchOptions();
    el("reconciliation-period-start").value=el("reconciliation-period-start").value||localDateString().slice(0,8)+"01";
    el("reconciliation-period-end").value=el("reconciliation-period-end").value||localDateString();
  }
  async function loadReconciliationSessions(){
    const result=await api("/reconciliations/sessions?family_id="+selectedFamilyId+"&limit=100");
    reconciliationSessions=result.sessions||[];
    const host=el("reconciliation-session-list");
    host.replaceChildren();
    el("reconciliation-session-count").textContent=reconciliationSessions.length+" 個工作階段";
    el("reconciliation-session-empty").classList.toggle("hidden",reconciliationSessions.length>0);
    for(const session of reconciliationSessions){
      const account=reconciliationAccounts.find(item=>item.id===session.account_id);
      const card=document.createElement("article");
      card.className="reconciliation-session-card";
      const info=document.createElement("div");
      info.className="reconciliation-session-info";
      info.append(
        makeText("strong",(null),"#"+session.id+" · "+(account?.name||("帳戶 #"+session.account_id))),
        makeText("p","tiny muted",dateLabel(session.period_start)+" 至 "+dateLabel(session.period_end)+" · "+session.currency_code),
        makeText("p","tiny muted","銀行明細 "+session.statement_row_count+" 筆 · 已核對 "+session.matched_row_count+" · 待處理 "+session.difference_row_count+" · 排除 "+(session.excluded_row_count||0))
      );
      const actions=document.createElement("div");
      actions.className="reconciliation-session-actions";
      actions.append(makeText("span",statusClass(session.status),statusLabels[session.status]||session.status));
      actions.append(makeButton("查看明細","secondary small",()=>loadReconciliationDetail(session.id)));
      card.append(info,actions);
      host.append(card);
    }
  }
  function renderKpis(session,rows){
    const host=el("reconciliation-kpis");
    host.replaceChildren();
    const partial=(rows||[]).filter(item=>item.reconciliation_status==="partially_matched").length;
    const metrics=[
      ["銀行明細",session.statement_row_count||0],
      ["已核對",session.matched_row_count||0],
      ["部分配對",partial],
      ["待核對",Math.max(0,(session.difference_row_count||0)-partial)],
      ["已排除",session.excluded_row_count||0]
    ];
    for(const [label,value] of metrics){
      const card=document.createElement("div");
      card.className="reconciliation-kpi";
      card.append(makeText("span","tiny muted",label),makeText("strong",null,String(value)));
      host.append(card);
    }
  }
  function renderSessionActions(session){
    const host=el("reconciliation-session-actions");
    host.replaceChildren();
    if(session.status==="in_progress"){
      host.append(makeButton("完成對帳","primary small",completeReconciliationSession));
    }else if(session.status==="completed"){
      host.append(makeButton("重新開啟對帳","secondary small",reopenReconciliationSession));
      host.append(makeText("span","tiny muted","已完成於 "+dateLabel(session.completed_at)));
    }
  }
  function renderReconciliationRows(rows){
    const host=el("reconciliation-rows");
    host.replaceChildren();
    el("reconciliation-rows-empty").classList.toggle("hidden",rows.length>0);
    const editable=activeReconciliationSession?.status==="in_progress";
    for(const row of rows){
      const card=document.createElement("article");
      card.className="reconciliation-row-card";
      const top=document.createElement("div");
      top.className="reconciliation-row-top";
      const identity=document.createElement("div");
      identity.className="reconciliation-row-identity";
      identity.append(
        makeText("strong",null,row.description||"（無交易說明）"),
        makeText("p","tiny muted","第 "+row.row_number+" 列 · "+dateLabel(row.transaction_date)+" · "+(row.transaction_type==="expense"?"支出":"收入")+" · "+(row.external_reference||"無銀行序號"))
      );
      const amount=makeText("strong","reconciliation-row-amount",money(row.amount,row.currency_code));
      top.append(identity,amount);
      const meta=document.createElement("div");
      meta.className="reconciliation-row-meta";
      meta.append(
        makeText("span",statusClass(row.reconciliation_status),rowStatusLabels[row.reconciliation_status]||row.reconciliation_status),
        makeText("span","tiny muted","已配對 "+money(row.matched_amount,row.currency_code)),
        makeText("span","tiny muted","剩餘 "+money(row.remaining_amount,row.currency_code))
      );
      card.append(top,meta);
      if(row.exclusion){
        const reason=makeText("p","reconciliation-reason","排除原因："+row.exclusion.reason);
        card.append(reason);
        if(editable)card.append(makeButton("解除排除","secondary small",()=>voidReconciliationExclusion(row.exclusion.id)));
      }
      if(row.matches?.length){
        const matches=document.createElement("div");
        matches.className="reconciliation-match-list";
        for(const match of row.matches){
          const line=document.createElement("div");
          line.className="reconciliation-match-line";
          line.append(makeText("span","tiny","交易 #"+match.transaction_id+" · "+money(match.allocated_amount, row.currency_code)));
          if(editable)line.append(makeButton("解除配對","danger small",()=>voidReconciliationMatch(match.id)));
          matches.append(line);
        }
        card.append(matches);
      }
      if(editable&&row.reconciliation_status!=="excluded"){
        const suggestion=(reconciliationSuggestions.get(row.id)||[]);
        if(suggestion.length){
          const group=document.createElement("div");
          group.className="reconciliation-candidates";
          group.append(makeText("h4",null,"系統比對建議（仍需人工確認）"));
          for(const candidate of suggestion){
            const candidateCard=document.createElement("div");
            candidateCard.className="reconciliation-candidate-card";
            const detail=document.createElement("div");
            detail.className="reconciliation-candidate-info";
            detail.append(
              makeText("strong",null,candidate.description||("交易 #"+candidate.transaction_id)),
              makeText("p","tiny muted",dateLabel(candidate.transaction_date)+" · "+money(candidate.amount,candidate.currency_code)+" · "+candidate.score+" 分 · "+({high:"高信心",medium:"中信心",low:"低信心"}[candidate.confidence]||candidate.confidence))
            );
            detail.append(makeText("p","tiny muted",(candidate.reasons||[]).join("；")));
            if(candidate.ambiguous_across_rows)detail.append(makeText("p","tiny muted","注意：此交易也出現在其他銀行明細的候選清單中。"));
            candidateCard.append(detail,makeButton("確認配對","primary small",()=>createReconciliationMatch(row,candidate.transaction_id,candidate.allocated_amount)));
            group.append(candidateCard);
          }
          card.append(group);
        }else{
          card.append(makeText("p","tiny muted","目前沒有自動比對建議；可搜尋家庭帳務，或先保留待核對。"));
        }
        if(Number(row.remaining_amount)>0){
          const manualHost=document.createElement("div");
          manualHost.className="reconciliation-manual-match";
          const searchButton=makeButton("搜尋其他帳務","secondary small",()=>searchTransactionsForRow(row,manualHost));
          manualHost.append(searchButton);
          card.append(manualHost);
        }
        if(row.reconciliation_status==="unmatched"){
          card.append(makeButton("排除此明細","danger small",()=>excludeReconciliationRow(row.id)));
        }
      }
      host.append(card);
    }
  }
  async function loadReconciliationDetail(sessionId){
    clearReconciliationNotice();
    try{
      const result=await api("/reconciliations/sessions/"+sessionId+"?family_id="+selectedFamilyId+"&limit=500");
      activeReconciliationSession=result.session;
      activeReconciliationRows=result.rows||[];
      reconciliationSuggestions=new Map();
      if(activeReconciliationSession.status==="in_progress"){
        try{
          const suggestions=await api("/reconciliations/sessions/"+sessionId+"/suggestions?family_id="+selectedFamilyId,{method:"POST"});
          for(const item of suggestions.suggestions||[])reconciliationSuggestions.set(item.bank_import_row.id,item.candidates||[]);
        }catch(error){
          reconciliationNotice("明細已載入，但目前帳號沒有產生配對建議的權限："+error.message,"error");
        }
      }
      el("reconciliation-detail-panel").classList.remove("hidden");
      el("reconciliation-detail-title").textContent="對帳工作階段 #"+activeReconciliationSession.id;
      el("reconciliation-detail-subtitle").textContent="帳戶 #"+activeReconciliationSession.account_id+" · "+dateLabel(activeReconciliationSession.period_start)+" 至 "+dateLabel(activeReconciliationSession.period_end)+" · "+activeReconciliationSession.currency_code;
      renderKpis(activeReconciliationSession,activeReconciliationRows);
      renderSessionActions(activeReconciliationSession);
      renderReconciliationRows(activeReconciliationRows);
      el("reconciliation-detail-panel").scrollIntoView({behavior:"smooth",block:"start"});
    }catch(error){
      reconciliationNotice("無法載入對帳明細："+error.message,"error");
    }
  }
  async function createReconciliationMatch(row,transactionId,amount){
    if(!activeReconciliationSession)return;
    try{
      await api("/reconciliations/sessions/"+activeReconciliationSession.id+"/matches?family_id="+selectedFamilyId,{
        method:"POST",
        body:JSON.stringify({bank_import_row_id:row.id,transaction_id:transactionId,allocated_amount:String(amount)})
      });
      reconciliationNotice("配對已建立；正式交易與銀行原始明細均未被修改。");
      await loadReconciliationDetail(activeReconciliationSession.id);
      await loadReconciliationSessions();
    }catch(error){reconciliationNotice("配對失敗："+error.message,"error");}
  }
  async function searchTransactionsForRow(row,host){
    const session=activeReconciliationSession;
    if(!session)return;
    host.querySelectorAll("select,button.reconciliation-search-submit").forEach(node=>node.remove());
    const start=encodeURIComponent(dateShift(session.period_start,-7)+"T00:00:00+08:00");
    const end=encodeURIComponent(dateShift(session.period_end,7)+"T23:59:59+08:00");
    try{
      const result=await api("/transactions?family_id="+selectedFamilyId+"&account_id="+session.account_id+"&transaction_type="+row.transaction_type+"&start_date="+start+"&end_date="+end+"&limit=200");
      const matchedIds=new Set((row.matches||[]).map(item=>item.transaction_id));
      const candidates=(result.transactions||[]).filter(item=>
        item.currency_code===row.currency_code&&Number(item.amount)>0&&
        Number(item.amount)<=Number(row.remaining_amount)&&!matchedIds.has(item.id)
      );
      const select=document.createElement("select");
      select.className="reconciliation-manual-select";
      select.add(new Option(candidates.length?"選擇要配對的正式交易":"沒有符合條件的正式交易",""));
      for(const item of candidates){
        select.add(new Option("#"+item.id+" · "+dateLabel(item.transaction_date)+" · "+money(item.amount,item.currency_code)+" · "+item.description,String(item.id)));
      }
      const submit=makeButton("確認手動配對","primary small",()=>{
        const chosen=candidates.find(item=>String(item.id)===select.value);
        if(chosen)createReconciliationMatch(row,chosen.id,chosen.amount);
      });
      submit.classList.add("reconciliation-search-submit");
      submit.disabled=!candidates.length;
      host.append(select,submit);
      if(!candidates.length)host.append(makeText("p","tiny muted","查詢期間內沒有符合帳戶、幣別、方向及剩餘金額的交易。"));
    }catch(error){reconciliationNotice("搜尋帳務失敗："+error.message,"error");}
  }
  async function voidReconciliationMatch(matchId){
    const reason=window.prompt("請輸入解除配對原因：");
    if(!reason||!reason.trim())return;
    try{
      await api("/reconciliations/sessions/"+activeReconciliationSession.id+"/matches/"+matchId+"/void?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify({reason:reason.trim()})});
      reconciliationNotice("配對已解除，原配對紀錄及原因已保留。");
      await loadReconciliationDetail(activeReconciliationSession.id);
      await loadReconciliationSessions();
    }catch(error){reconciliationNotice("解除配對失敗："+error.message,"error");}
  }
  async function excludeReconciliationRow(rowId){
    const reason=window.prompt("請輸入排除此銀行明細的原因：");
    if(!reason||!reason.trim())return;
    try{
      await api("/reconciliations/sessions/"+activeReconciliationSession.id+"/exclude?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify({bank_import_row_id:rowId,reason:reason.trim()})});
      reconciliationNotice("明細已排除，原始銀行資料仍完整保留。");
      await loadReconciliationDetail(activeReconciliationSession.id);
      await loadReconciliationSessions();
    }catch(error){reconciliationNotice("排除明細失敗："+error.message,"error");}
  }
  async function voidReconciliationExclusion(exclusionId){
    const reason=window.prompt("請輸入解除排除原因：");
    if(!reason||!reason.trim())return;
    try{
      await api("/reconciliations/sessions/"+activeReconciliationSession.id+"/exclusions/"+exclusionId+"/void?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify({reason:reason.trim()})});
      reconciliationNotice("已解除排除，該筆明細可以重新配對。");
      await loadReconciliationDetail(activeReconciliationSession.id);
      await loadReconciliationSessions();
    }catch(error){reconciliationNotice("解除排除失敗："+error.message,"error");}
  }
  async function completeReconciliationSession(){
    if(!activeReconciliationSession)return;
    if(!window.confirm("確認完成此對帳工作階段？所有銀行明細都必須已核對或有理由排除。"))return;
    const reason=window.prompt("請輸入完成對帳的確認說明：");
    if(!reason||!reason.trim())return;
    try{
      await api("/reconciliations/sessions/"+activeReconciliationSession.id+"/complete?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify({reason:reason.trim()})});
      reconciliationNotice("對帳已完成，完成紀錄已寫入稽核歷程。");
      await loadReconciliationDetail(activeReconciliationSession.id);
      await loadReconciliationSessions();
    }catch(error){reconciliationNotice("無法完成對帳："+error.message,"error");}
  }
  async function reopenReconciliationSession(){
    if(!activeReconciliationSession)return;
    if(!window.confirm("重新開啟後，必須再次核對並完成此工作階段。"))return;
    const reason=window.prompt("請輸入重新開啟原因：");
    if(!reason||!reason.trim())return;
    try{
      await api("/reconciliations/sessions/"+activeReconciliationSession.id+"/reopen?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify({reason:reason.trim()})});
      reconciliationNotice("對帳已重新開啟，歷史完成紀錄仍會保留。");
      await loadReconciliationDetail(activeReconciliationSession.id);
      await loadReconciliationSessions();
    }catch(error){reconciliationNotice("重新開啟失敗："+error.message,"error");}
  }
  async function createReconciliationSession(event){
    event.preventDefault();
    const button=el("reconciliation-session-submit");
    button.disabled=true;
    clearReconciliationNotice();
    try{
      const payload={
        account_id:Number(el("reconciliation-account").value),
        source_batch_id:Number(el("reconciliation-batch").value),
        period_start:el("reconciliation-period-start").value,
        period_end:el("reconciliation-period-end").value
      };
      if(!payload.account_id||!payload.source_batch_id)throw new Error("請選擇帳戶及已確認的匯入批次。");
      if(payload.period_end<payload.period_start)throw new Error("對帳結束日期不可早於開始日期。");
      const result=await api("/reconciliations/sessions?family_id="+selectedFamilyId,{method:"POST",body:JSON.stringify(payload)});
      reconciliationNotice("對帳工作階段已建立；尚未改動任何正式交易。");
      await loadReconciliationSessions();
      await loadReconciliationDetail(result.session.id);
    }catch(error){reconciliationNotice("建立對帳失敗："+error.message,"error");}
    finally{button.disabled=false;}
  }
  async function loadBankReconciliationWorkspace(){
    if(!selectedFamilyId)return;
    clearReconciliationNotice();
    try{
      await loadReconciliationSetup();
      await loadReconciliationSessions();
      if(activeReconciliationSession&&activeReconciliationSession.family_id!==selectedFamilyId){
        activeReconciliationSession=null;
        el("reconciliation-detail-panel").classList.add("hidden");
      }
    }catch(error){reconciliationNotice("載入銀行對帳工作區失敗："+error.message,"error");}
  }
  function openBankReconciliation(){
    if(!selectedFamilyId){notice("notice-app","請先建立或選擇家庭，再使用銀行對帳工作區。","error");return;}
    el("bank-reconciliation-view").classList.remove("hidden");
    el("bank-reconciliation-view").scrollIntoView({behavior:"smooth",block:"start"});
    loadBankReconciliationWorkspace();
  }

  el("open-bank-reconciliation").addEventListener("click",openBankReconciliation);
  el("close-bank-reconciliation").addEventListener("click",()=>el("bank-reconciliation-view").classList.add("hidden"));
  el("refresh-bank-reconciliation").addEventListener("click",loadBankReconciliationWorkspace);
  el("reconciliation-account").addEventListener("change",fillBatchOptions);
  el("reconciliation-session-form").addEventListener("submit",createReconciliationSession);
  el("reconciliation-refresh-suggestions").addEventListener("click",()=>activeReconciliationSession&&loadReconciliationDetail(activeReconciliationSession.id));
  el("reconciliation-close-detail").addEventListener("click",()=>el("reconciliation-detail-panel").classList.add("hidden"));
  window.loadBankReconciliationWorkspace=loadBankReconciliationWorkspace;
})();
