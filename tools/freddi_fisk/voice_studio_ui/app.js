const form = document.querySelector('#studio');
const text = document.querySelector('#text');
const button = document.querySelector('#generate');
const error = document.querySelector('#error');
const progress = document.querySelector('#progress');
const playback = document.querySelector('.playback');
const audio = document.querySelector('#audio');
let busy = false;
let voices = {};
const engine = document.querySelector('#engine');

function selection() { return new FormData(form).get('speaker'); }
function update() {
  const chatterbox = Boolean(voices[selection()]?.chatterbox_available);
  engine.querySelector('[value=chatterbox]').disabled = !chatterbox;
  if (engine.value === 'chatterbox' && !chatterbox) engine.value = 'alva';
  document.querySelector('#exaggeration').disabled = engine.value !== 'chatterbox';
  document.querySelector('#count').textContent = `${text.value.length} / 400`;
  button.disabled = busy || !text.value.trim() || !voices[selection()]?.available;
}
function showError(message) { error.textContent = message; error.hidden = false; }
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Något gick fel. Försök igen.');
  return data;
}
async function poll(identifier) {
  let failures = 0;
  while (true) {
    let job;
    try { job = await request(`/api/jobs/${identifier}`); failures = 0; }
    catch (e) {
      if (++failures >= 3) throw new Error('Kontakten med röststudion bröts. Kontrollera att den fortfarande körs.');
      await new Promise(resolve => setTimeout(resolve, 1500)); continue;
    }
    if (job.state === 'error') throw new Error(job.error);
    if (job.state === 'done') return job;
    progress.textContent = {queued:'Väntar på sin tur…', synthesizing:job.engine === 'chatterbox' ? 'Skapar naturligt svenskt tal… Det kan ta en stund.' : 'Läser din svenska replik…', converting:`Formar ${job.speaker === 'freddi' ? 'Freddis' : 'Linus'} röst…`}[job.state] || 'Skapar din replik…';
    await new Promise(resolve => setTimeout(resolve, 750));
  }
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (button.disabled) return;
  busy = true; error.hidden = true; playback.classList.add('busy'); update();
  progress.textContent = 'Förbereder din replik…';
  try {
    const job = await request('/api/jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      text:text.value.trim(), speaker:selection(), rate:Number(document.querySelector('#rate').value), pitch:Number(document.querySelector('#pitch').value),
      engine:engine.value, exaggeration:Number(document.querySelector('#exaggeration').value)
    })});
    const result = await poll(job.id);
    const name = result.speaker === 'freddi' ? 'Freddi' : 'Linus';
    document.querySelector('#playback-title').textContent = `${name} har något att säga`;
    document.querySelector('#spoken-text').textContent = result.text;
    document.querySelector('#result').hidden = false;
    audio.src = result.audio_url;
    const download = document.querySelector('#download');
    download.href = result.audio_url; download.download = `${result.speaker}-svenska.wav`; download.hidden = false;
    progress.textContent = `Klart att lyssna · ${result.duration.toFixed(1).replace('.', ',')} sekunder`;
    audio.play().catch(() => {});
  } catch (e) { showError(e.message); progress.textContent = 'Repliken kunde inte skapas.'; }
  finally { busy = false; playback.classList.remove('busy'); update(); }
});
text.addEventListener('input', update);
form.addEventListener('change', update);
document.querySelectorAll('[data-text]').forEach(preset => preset.addEventListener('click', () => { text.value = preset.dataset.text; update(); text.focus(); }));
document.querySelector('#pitch').addEventListener('input', event => { const value = Number(event.target.value); document.querySelector('#pitch-value').textContent = value > 0 ? `+${value}` : String(value); });
document.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); form.requestSubmit(); } });
request('/api/status').then(status => {
  voices = status.voices;
  document.querySelectorAll('[name=speaker]').forEach(radio => { radio.disabled = !voices[radio.value]?.available; });
  if (!voices[selection()]?.available) {
    const first = document.querySelector('[name=speaker]:not(:disabled)');
    if (first) first.checked = true; else showError('Inga röstmodeller hittades. Se startinstruktionerna för röststudion.');
  }
  if (status.default_engine === 'chatterbox' && voices[selection()]?.chatterbox_available) {
    engine.value = 'chatterbox';
  }
  if (Object.values(voices).every(voice => voice.available && voice.kind === 'trained')) {
    document.querySelector('#prototype p').textContent = 'Experimentella röster, tränade på svenska repliker från originalspelet. Röstlikhet och uttal kan variera.';
  }
  update();
}).catch(() => { showError('Röststudion svarar inte. Starta den lokala servern och ladda om sidan.'); });
update();
