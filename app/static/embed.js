(function(){
  const fileInput = document.getElementById('file-input');
  const fileInputMore = document.getElementById('file-input-more');
  const btnProcess = document.getElementById('btn-process');
  const btnProcessMore = document.getElementById('btn-process-more');
  const btnFinish = document.getElementById('btn-finish');
  const statusBox = document.getElementById('status');
  const progress = document.getElementById('progress');
  const bar = document.getElementById('bar');
  const pct = document.getElementById('pct');

  let pollTimer = null;
  function stopPolling(){
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  function getAction() {
    const radios = document.querySelectorAll('input[name="action"]');
    for (const r of radios) if (r.checked) return r.value;
    return 'add';
  }

  function setStatus(msg, ok=false, err=false){
    statusBox.style.display = 'block';
    statusBox.textContent = msg;
    statusBox.classList.remove('ok','err');
    if (ok) statusBox.classList.add('ok');
    if (err) statusBox.classList.add('err');
  }

  function resetProgress(){
    progress.style.display = 'none';
    bar.style.width = '0%';
    pct.textContent = '0%';
  }

  function showProgress(){
    progress.style.display = 'block';
    bar.style.width = '0%';
    pct.textContent = '0%';
  }

  function setProgress(val){
    const v = Math.max(0, Math.min(100, Math.floor(val)));
    bar.style.width = v + '%';
    pct.textContent = v + '%';
  }

  function poll(jobId){
    stopPolling();
    pollTimer = setInterval(async ()=>{
      try{
        const res = await fetch('/embeddings/progress/' + jobId);
        const data = await res.json();
        if (data.progress !== undefined){
          setProgress(data.progress);
        }
        if (data.detail){
          setStatus((data.status || 'processing') + ': ' + data.detail);
        } else {
          setStatus((data.status || 'processing'));
        }
        if (data.status === 'completed'){
          stopPolling();
          setStatus('Processing completed!', true, false);
          document.getElementById('post-complete').style.display = 'block';
        }
        if (data.status && data.status.startsWith('error')){
          stopPolling();
          setStatus('Error: ' + (data.status || 'failed'), false, true);
          resetProgress();
        }
      }catch(e){
        stopPolling();
        setStatus('Error polling: ' + e.message, false, true);
        resetProgress();
      }
    }, 1500);
  }

  async function processFiles(inputEl, action) {
    if (!inputEl.files || inputEl.files.length === 0) {
      setStatus('Please select files first.', false, true);
      return;
    }

    const form = new FormData();
    form.append('action', action || 'add');
    for (const f of inputEl.files) form.append('files', f, f.name);

    showProgress();
    setProgress(0);
    setStatus('Uploading files...');

    try {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/embeddings/process', true);

      xhr.upload.onprogress = function (e) {
        if (e.lengthComputable) {
          const percent = (e.loaded / e.total) * 100;
          setProgress(percent * 0.4);
        }
      };

      xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
          try {
            const data = JSON.parse(xhr.responseText || '{}');
            if (xhr.status >= 200 && xhr.status < 300) {
              if (data.job_id){
                setProgress(40);
                setStatus('Embedding job started...');
                poll(data.job_id);
              } else {
                setStatus('Unexpected response: ' + (xhr.responseText || 'no body'), false, true);
                resetProgress();
              }
            } else {
              setStatus('Error: ' + (data.message || xhr.statusText), false, true);
              resetProgress();
            }
          } catch (e) {
            setStatus('Error: ' + e.message, false, true);
            resetProgress();
          }
        }
      };

      xhr.send(form);
    } catch (e) {
      setStatus('Error: ' + e.message, false, true);
      resetProgress();
    }
  }

  if (btnProcess) {
    btnProcess.addEventListener('click', ()=> processFiles(fileInput, getAction()));
  }
  if (btnProcessMore) {
    btnProcessMore.addEventListener('click', ()=> processFiles(fileInputMore, 'add'));
  }
  if (btnFinish) {
    btnFinish.addEventListener('click', ()=> {
      window.location.href = '/admin/logout';
    });
  }
})();
