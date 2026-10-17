/* Company billing: read-only verified usage, NEVER invented money or checkout. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
if(!$('billingWorkspace'))return;
let serial=0;
const identity=()=>String(state.organizationId)+':'+String(state.uiEpoch||0);
function reset(){
 $('billingPlan').textContent='Not enabled';
 $('billingNextCharge').textContent='No scheduled charge';
 for(const id of ['billingSearches','billingSaved','billingSeats'])$(id).textContent='—';
 $('billingPayments').textContent='No verified transactions available';
 $('billingInvoices').textContent='Not available until a merchant and invoicing integration is verified';
 $('upgradeBilling').disabled=true;
}
async function load(){
 const ticket=++serial,scope=identity();
 reset();
 if(!usingSharedOrganization()){
  $('billingMessage').textContent='Choose a shared organization in Team. Personal workspaces cannot own company subscriptions.';
  return;
 }
 $('billingMessage').textContent='Loading recorded usage…';
 try{
  const r=await fetch('/api/v1/organizations/'+encodeURIComponent(state.organizationId)+'/billing',
   {credentials:'same-origin',cache:'no-store'});
  if(ticket!==serial||scope!==identity())return;
  if(r.status===401){location.replace('/login');return;}
  if(r.status===403){
   $('billingMessage').textContent='Only organization owners and administrators can view billing.';
   return;
  }
  if(!r.ok){
   $('billingMessage').textContent='Billing overview unavailable; retry.';
   return;
  }
  const data=await r.json();
  if(ticket!==serial||scope!==identity())return;
  if(data.billing_status!=='not_enabled'||data.upgrade_available!==false){
   $('billingMessage').textContent='Unexpected billing state. Contact support.';
   return;
  }
  const usage=data.usage||{};
  const safeInt=x=>Number.isSafeInteger(x)&&x>=0?String(x):'Unavailable';
  $('billingSearches').textContent=safeInt(usage.recorded_searches);
  $('billingSaved').textContent=safeInt(usage.saved_opportunities);
  $('billingSeats').textContent=safeInt(usage.team_seats);
  $('billingMessage').textContent='This account is in non-billing pilot mode. No payment has been requested.';
 }catch(e){
  if(ticket===serial&&scope===identity())
   $('billingMessage').textContent='Network unavailable. No billing changes were made.';
 }
}
$('refreshBilling').onclick=load;
window.addEventListener('workspace-context',()=>{
 serial++;
 reset();
 if((location.hash.slice(1)||'overview')==='billing')load();
});
if((location.hash.slice(1)||'overview')==='billing')load();
})();
