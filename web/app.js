const $ = id => document.getElementById(id);
const history = [];
let image = null;

function message(role, content) {
  const node = document.createElement('div');
  node.className = `message ${role}`;
  node.textContent = content;
  $('messages').appendChild(node);
  node.scrollIntoView({block:'end'});
  return node;
}

async function refresh() {
  try {
    const [state, health] = await Promise.all([
      fetch('/api/state').then(r => r.json()), fetch('/api/health').then(r => r.json())
    ]);
    $('status').textContent = health.ready ? `API 已設定 · ${health.model}` : '請先設定 OPENAI_API_KEY';
    if (state.status !== 'ok') {
      $('state').textContent = state.message || '尚無遊戲資料';
      return;
    }
    const meta = state.meta;
    $('state').textContent = `回合 ${meta.turn ?? '未知'}\n${meta.leader || '未知領袖'} / ${meta.civilization || '未知文明'}\n城市 ${state.cities.length} · 單位 ${state.units.length} · 可見地塊 ${state.plots.length}\n日誌更新：${new Date(state.updated_at).toLocaleString()}`;
  } catch {
    $('status').textContent = '本機服務無法連線';
  }
}

async function setImage(file) {
  if (!file || !file.type.startsWith('image/')) return;
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1800 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  image = canvas.toDataURL('image/png').split(',')[1];
  $('image-name').textContent = `${file.name || '剪貼簿截圖'}（下次提問附上）`;
}

$('refresh').addEventListener('click', refresh);
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
  $('question').value = button.dataset.question;
  $('question').focus();
}));
$('screenshot').addEventListener('change', event => setImage(event.target.files[0]).catch(() => message('error','無法讀取截圖')));
document.addEventListener('paste', event => {
  const file = [...event.clipboardData.items].find(item => item.type.startsWith('image/'))?.getAsFile();
  if (file) { event.preventDefault(); setImage(file).catch(() => message('error','無法讀取截圖')); }
});
$('form').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (!question) return;
  const submittedImage = image;
  const previous = history.slice(-8);
  message('user', question + (submittedImage ? '\n（附遊戲截圖）' : ''));
  $('send').disabled = true;
  const pending = message('assistant','分析中…');
  try {
    const response = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question, image:submittedImage, history:previous})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '請求失敗');
    pending.textContent = result.answer;
    history.push({role:'user', content:question}, {role:'assistant', content:result.answer});
    $('question').value = '';
    image = null;
    $('screenshot').value = '';
    $('image-name').textContent = '也可直接貼上截圖（Ctrl+V）';
    refresh();
  } catch(error) { pending.className = 'message error'; pending.textContent = error.message; }
  finally { $('send').disabled = false; }
});
refresh();
