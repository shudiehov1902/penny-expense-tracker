"use strict";
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="penny-token"]').content;
const money = (cents) => new Intl.NumberFormat("en-IE", {style: "currency", currency: "EUR"}).format(cents / 100);
const colors = ["#91ab73", "#bdcb9f", "#cdb58b", "#8eaca1", "#b5b58d", "#a5b8bf"];
let overview = null, editingId = null, deletingId = null, requestNumber = 0, toastTimer;
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; };
const node = (tag, className, text) => { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; };
const monthName = (month) => new Date(`${month}-01T12:00:00`).toLocaleDateString("en-GB", {month:"long",year:"numeric"});
function toast(text) { $("toast").textContent = text; $("toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").hidden = true, 3500); }
async function api(path, method = "GET", body) {
  const response = await fetch(path, {method, headers: {"Content-Type":"application/json", "X-Penny-Token":token}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  let data; try { data = await response.json(); } catch { throw new Error("The server could not complete the request. Please try again."); }
  if (!response.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}
function categorySymbol(category) {
  const c = category.toLowerCase();
  if (/food|drink|еда|grocer/.test(c)) return "◒";
  if (/transport|транспорт|travel/.test(c)) return "↗";
  if (/home|rent/.test(c)) return "⌂";
  if (/shop/.test(c)) return "▱";
  if (/health/.test(c)) return "+";
  return "◇";
}
async function loadOverview() {
  const number = ++requestNumber, month = $("month").value;
  $("month-title").textContent = monthName(month);
  $("export").href = `/api/export?month=${encodeURIComponent(month)}`;
  try {
    const data = await api(`/api/overview?month=${encodeURIComponent(month)}`);
    if (number !== requestNumber) return;
    overview = data; $("load-error").hidden = true; render();
  } catch (error) {
    if (number !== requestNumber) return;
    $("load-error").textContent = error.message; $("load-error").hidden = false;
  }
}
function render() {
  const {total_cents:total, budget_cents:budget, expenses} = overview;
  $("total-spent").textContent = money(total);
  $("spent-detail").textContent = `Across ${expenses.length} transaction${expenses.length === 1 ? "" : "s"} this month`;
  $("budget-value").textContent = budget === null ? "Not set" : money(budget);
  $("edit-budget").textContent = budget === null ? "Set budget ↗" : "Edit budget ↗";
  $("budget-progress").style.width = budget === null ? "0%" : `${Math.min(100, total / budget * 100)}%`;
  $("budget-progress").parentElement.classList.toggle("over", budget !== null && total > budget);
  $("budget-detail").textContent = budget === null ? "Give your spending a little direction." : `${Math.round(total / budget * 100)}% of your monthly budget used`;
  const remaining = budget === null ? null : budget - total;
  $("remaining-value").textContent = remaining === null ? "—" : money(Math.abs(remaining));
  $("remaining-value").closest("article").classList.toggle("over", remaining !== null && remaining < 0);
  $("remaining-label").replaceChildren(node("span", "", remaining !== null && remaining < 0 ? "Over budget" : "Left to spend"), node("span", "", "↙"));
  $("remaining-detail").textContent = remaining === null ? "Set a monthly budget to see your balance." : remaining < 0 ? "A good moment to check your spending." : "A little breathing room for the month.";
  $("transaction-count").textContent = expenses.length;
  const selectedCategory = $("category-filter").value;
  $("category-filter").replaceChildren(new Option("All categories", ""));
  [...new Set(expenses.map(e => e.category))].sort((a,b)=>a.localeCompare(b)).forEach(c => $("category-filter").add(new Option(c,c)));
  $("category-filter").value = [...$("category-filter").options].some(o => o.value === selectedCategory) ? selectedCategory : "";
  $("categories").replaceChildren(...overview.categories.map(c => new Option(c,c)));
  renderChart(); renderCategories(); renderRows();
}
function renderChart() {
  const chart = $("activity-chart"); chart.replaceChildren();
  const month = overview.month, [year, mon] = month.split("-").map(Number);
  const last = new Date(year, mon, 0).getDate();
  const daily = new Map(overview.daily.map(d => [d.date, d.amount_cents]));
  const highest = Math.max(1, ...daily.values());
  $("axis-last").textContent = last; $("axis-middle").textContent = Math.ceil(last/2);
  for (let day=1;day<=last;day++) {
    const date = `${month}-${String(day).padStart(2,"0")}`, cents = daily.get(date) || 0;
    const bar = node("div", `chart-bar${date === today() ? " current" : ""}`);
    bar.style.height = `${Math.max(1.5,cents/highest*100)}%`;
    bar.append(node("span","tooltip",`${day} ${monthName(month).split(" ")[0]} · ${money(cents)}`));
    chart.append(bar);
  }
  chart.setAttribute("aria-label", `Daily spending for ${monthName(month)}. Total ${money(overview.total_cents)}.`);
  if (!overview.expenses.length) chart.append(node("div","chart-empty","Your spending story starts with the first expense."));
}
function renderCategories() {
  const box = $("category-breakdown"); box.replaceChildren();
  if (!overview.breakdown.length) { box.append(node("p","category-empty","Add an expense to see your categories.")); return; }
  const list = overview.breakdown.slice(0,5);
  list.forEach((item,index) => {
    const row=node("div","category-item"); row.style.setProperty("--category-color",colors[index%colors.length]);
    const info=node("div","category-info"), name=node("span","category-name"); name.append(node("i"),node("span","",item.category));
    info.append(name,node("span","category-total",money(item.amount_cents)));
    const track=node("div","category-track"), fill=node("span"); fill.style.width=`${item.amount_cents/overview.total_cents*100}%`;track.append(fill);
    row.append(info,track);box.append(row);
  });
  if (overview.breakdown.length>5) box.append(node("p","category-more",`+ ${overview.breakdown.length-5} more categories in your transactions`));
}
function renderRows() {
  if (!overview) return;
  const search=$("search").value.trim().toLocaleLowerCase(), category=$("category-filter").value;
  const rows=overview.expenses.filter(e => (!category || e.category===category) && `${e.category} ${e.note}`.toLocaleLowerCase().includes(search));
  const sort=$("sort").value;
  rows.sort((a,b) => sort==="highest" ? b.amount_cents-a.amount_cents : sort==="lowest" ? a.amount_cents-b.amount_cents : sort==="oldest" ? a.spent_on.localeCompare(b.spent_on)||a.id-b.id : b.spent_on.localeCompare(a.spent_on)||b.id-a.id);
  const tbody=$("expense-rows");tbody.replaceChildren();
  rows.forEach(expense => {
    const tr=node("tr"), main=node("td"), cell=node("div","expense-cell"), detail=node("div");
    detail.append(node("span","expense-name",expense.note || expense.category));
    detail.append(node("span","expense-note",expense.note ? expense.category : "Everyday expense"));
    cell.append(node("span","category-icon",categorySymbol(expense.category)),detail);main.append(cell);
    const categoryCell=node("td");categoryCell.append(node("span","category-pill",expense.category));
    const dateCell=node("td","date-cell",new Date(`${expense.spent_on}T12:00:00`).toLocaleDateString("en-GB",{day:"2-digit",month:"short",year:"numeric"}));
    const amount=node("td","amount-cell",money(expense.amount_cents));
    const actionCell=node("td"), actions=node("div","actions");
    const edit=node("button","row-action","✎");edit.type="button";edit.setAttribute("aria-label",`Edit ${expense.category} expense of ${money(expense.amount_cents)}`);edit.addEventListener("click",()=>openExpense(expense));
    const remove=node("button","row-action delete","×");remove.type="button";remove.setAttribute("aria-label",`Delete ${expense.category} expense of ${money(expense.amount_cents)}`);remove.addEventListener("click",()=>openDelete(expense));
    actions.append(edit,remove);actionCell.append(actions);tr.append(main,categoryCell,dateCell,amount,actionCell);tbody.append(tr);
  });
  $("empty-state").hidden=rows.length>0;
  const filtered=Boolean(search||category);
  $("empty-state").querySelector("h3").textContent=filtered?"No matching expenses":"No expenses yet";
  $("empty-state").querySelector("p").textContent=filtered?"Try another search or choose a different category.":"Add your first expense to start seeing the bigger picture.";
  $("empty-add").hidden=filtered;
  $("table-count").textContent=`Showing ${rows.length} of ${overview.expenses.length} transactions`;
}
function openExpense(expense=null) {
  editingId=expense?.id ?? null;
  $("expense-form").reset();$("expense-error").textContent="";
  $("expense-title").textContent=expense?"Edit expense":"Add expense";
  $("save-expense").textContent=expense?"Save changes":"Save expense";
  $("amount").value=expense?(expense.amount_cents/100).toFixed(2):"";
  $("expense-category").value=expense?.category??"";
  $("expense-note").value=expense?.note??"";
  $("expense-date").value=expense?.spent_on??( $("month").value===today().slice(0,7)?today():`${$("month").value}-01` );
  $("expense-dialog").showModal();$("amount").focus();
}
function openBudget() {
  if (!overview) return;
  $("budget-month-label").textContent=monthName(overview.month).toUpperCase();
  $("budget-amount").value=overview.budget_cents===null?"":(overview.budget_cents/100).toFixed(2);
  $("budget-error").textContent="";$("remove-budget").hidden=overview.budget_cents===null;
  $("budget-dialog").showModal();$("budget-amount").focus();
}
function openDelete(expense) {
  deletingId=expense.id;$("delete-error").textContent="";
  $("delete-description").textContent=`${expense.category} · ${money(expense.amount_cents)} · ${expense.spent_on}. This will remove the record from your tracker.`;
  $("delete-dialog").showModal();
}
async function submitForm(event, errorId, action) {
  event.preventDefault(); const form=event.currentTarget;
  if(form.dataset.busy) return;
  form.dataset.busy="true";const buttons=[...form.querySelectorAll("button")];buttons.forEach(b=>b.disabled=true);$(errorId).textContent="";
  try { await action(); } catch(error) { $(errorId).textContent=error.message; }
  finally { delete form.dataset.busy;buttons.forEach(b=>b.disabled=false); }
}
$("expense-form").addEventListener("submit", event=>submitForm(event,"expense-error",async()=>{
  const data={amount:$("amount").value,category:$("expense-category").value,spent_on:$("expense-date").value,note:$("expense-note").value};
  await api(editingId===null?"/api/expenses":`/api/expenses/${editingId}`,editingId===null?"POST":"PUT",data);
  $("expense-dialog").close();$("month").value=data.spent_on.slice(0,7);await loadOverview();toast(editingId===null?"Expense added":"Expense updated");
}));
$("budget-form").addEventListener("submit",event=>submitForm(event,"budget-error",async()=>{
  await api("/api/budget","PUT",{month:overview.month,amount:$("budget-amount").value});$("budget-dialog").close();await loadOverview();toast("Budget updated");
}));
$("remove-budget").addEventListener("click",async()=>{
  $("remove-budget").disabled=true;
  try {await api("/api/budget","PUT",{month:overview.month,amount:null});$("budget-dialog").close();await loadOverview();toast("Budget removed");}
  catch(error){$("budget-error").textContent=error.message;}
  finally{$("remove-budget").disabled=false;}
});
$("delete-form").addEventListener("submit",event=>submitForm(event,"delete-error",async()=>{
  await api(`/api/expenses/${deletingId}`,"DELETE");$("delete-dialog").close();await loadOverview();toast("Expense deleted");
}));
["add-expense","empty-add"].forEach(id=>$(id).addEventListener("click",()=>openExpense()));
["sidebar-budget","edit-budget"].forEach(id=>$(id).addEventListener("click",openBudget));
document.querySelectorAll(".close-dialog").forEach(button=>button.addEventListener("click",()=>button.closest("dialog").close()));
$("search").addEventListener("input",renderRows);$("category-filter").addEventListener("change",renderRows);$("sort").addEventListener("change",renderRows);
$("month").value=today().slice(0,7);$("month").addEventListener("change",()=>{if($("month").value)loadOverview();});
function changeMonth(offset){const date=new Date(`${$("month").value}-01T12:00:00`);date.setMonth(date.getMonth()+offset);$("month").value=`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}`;loadOverview();}
$("previous-month").addEventListener("click",()=>changeMonth(-1));$("next-month").addEventListener("click",()=>changeMonth(1));
loadOverview();
