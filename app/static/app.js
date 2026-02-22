(function(){
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const messages = document.getElementById('messages');

  function addMsg(text, who){
    const el = document.createElement('div');
    el.className = 'msg ' + who;
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  window.addEventListener('DOMContentLoaded', () => {
    if (typeof WELCOME_MSG !== 'undefined' && WELCOME_MSG && WELCOME_MSG.trim()) {
      addMsg(WELCOME_MSG, 'bot');
    }
  });

  let wsProto = (location.protocol === 'https:') ? 'wss' : 'ws';
  const ws = new WebSocket(wsProto + '://' + location.host + '/ws/chat');

  ws.addEventListener('message', (ev)=>{
    addMsg(ev.data, 'bot');
  });

  sendBtn.addEventListener('click', ()=>{
    const txt = input.value.trim();
    if(!txt) return;
    addMsg(txt, 'user');
    ws.send(txt);
    input.value = '';
    input.focus();
  });

  input.addEventListener('keydown', (e)=>{
    if(e.key === 'Enter') sendBtn.click();
  });
})();
