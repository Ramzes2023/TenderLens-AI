"""Small dashboard enhancement. Only the public bot username reaches the browser."""

TELEGRAM_SCRIPT = r"""
const telegram = {connected:false,busy:false,timer:null,deadline:0,controller:null,closed:false};
function stopTelegramRefresh(){
  clearTimeout(telegram.timer); telegram.timer=null;
  if(telegram.controller)telegram.controller.abort();
  telegram.controller=null;
}
function renderTelegram(account){
  telegram.connected=account.telegram_connected===true;
  const button=document.getElementById('connectTelegram');
  button.hidden=telegram.connected;
  button.disabled=telegram.busy||telegram.connected;
  document.getElementById('telegramStatus').textContent=telegram.connected?'✓ Telegram connected':'Not connected';
  document.getElementById('telegramStatus').className=telegram.connected?'chip good':'chip';
  if(telegram.connected){
    stopTelegramRefresh();
    document.getElementById('telegramOpen').removeAttribute('href');
    document.getElementById('telegramOpen').hidden=true;
    document.getElementById('telegramMessage').textContent='The bot and web now use the same workspace.';
  }
}
async function telegramRequest(path,options={}){
  const controller=new AbortController();
  telegram.controller=controller;
  const timeout=setTimeout(()=>controller.abort(),10000);
  try{
    const response=await fetch(path,{...options,credentials:'same-origin',cache:'no-store',signal:controller.signal});
    if(response.status===401){stopTelegramRefresh();location.replace('/login');throw new Error('Please sign in again.')}
    if(!response.ok){
      const error=new Error(response.status===409?'Telegram is already connected or linking is unavailable.':'Unable to connect Telegram. Please try again.');
      error.status=response.status;throw error;
    }
    return await response.json();
  }finally{clearTimeout(timeout);if(telegram.controller===controller)telegram.controller=null}
}
async function refreshTelegramStatus(){
  if(telegram.closed||telegram.connected)return;
  if(Date.now()>=telegram.deadline){
    stopTelegramRefresh();
    document.getElementById('telegramOpen').hidden=true;
    document.getElementById('telegramOpen').removeAttribute('href');
    document.getElementById('telegramMessage').textContent='Automatic checking finished. Use Refresh to check your account, or connect again.';
    return;
  }
  try{
    const account=await telegramRequest('/api/v1/auth/me');
    state.ownerId=account.owner_user_id;
    renderTelegram(account);
    if(telegram.connected){
      await Promise.all([loadCompanies(),loadMonitoring(),loadTenders()]);
      return;
    }
  }catch(error){
    if(telegram.closed)return;
    stopTelegramRefresh();
    document.getElementById('telegramMessage').textContent='Status check failed. Use Refresh to retry.';
    return;
  }
  if(!telegram.closed&&!telegram.connected)telegram.timer=setTimeout(refreshTelegramStatus,2500);
}
async function connectTelegram(){
  if(telegram.busy||telegram.connected||telegram.closed)return;
  stopTelegramRefresh();
  telegram.busy=true;
  const button=document.getElementById('connectTelegram'),message=document.getElementById('telegramMessage');
  button.disabled=true;
  document.getElementById('telegramOpen').hidden=true;
  document.getElementById('telegramOpen').removeAttribute('href');
  message.textContent='Preparing Telegram…';
  // Open synchronously to avoid popup blockers after the async request.
  const popup=window.open('about:blank','_blank');
  if(popup)popup.opener=null;
  try{
    const ticket=await telegramRequest('/api/v1/auth/telegram-link',{method:'POST'});
    if(telegram.closed){if(popup)popup.close();return}
    if(!/^link_[A-Za-z0-9_-]{1,59}$/.test(ticket.start_parameter))throw new Error('Invalid connection link. Please try again.');
    const url='https://t.me/TenderLensAI_bot?start='+encodeURIComponent(ticket.start_parameter);
    const link=document.getElementById('telegramOpen');
    link.href=url;link.hidden=false;
    if(popup)popup.location.replace(url);
    message.textContent='Press START in Telegram. This page will check the connection for up to 2 minutes.';
    telegram.deadline=Date.now()+120000;
    telegram.timer=setTimeout(refreshTelegramStatus,2500);
  }catch(error){
    if(popup)popup.close();
    if(telegram.closed)return;
    if(error.status===409){
      try{const account=await telegramRequest('/api/v1/auth/me');state.ownerId=account.owner_user_id;renderTelegram(account)}catch(_){}
    }
    if(!telegram.connected)message.textContent=error.message;
  }finally{telegram.busy=false;button.disabled=telegram.connected}
}
window.addEventListener('pagehide',()=>{telegram.closed=true;stopTelegramRefresh()});
window.addEventListener('pageshow',()=>{telegram.closed=false});
"""
