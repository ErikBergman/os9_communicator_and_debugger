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
const castVoice = document.querySelector('#cast-voice');

function selection() { return castVoice.value || new FormData(form).get('speaker'); }
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
    progress.textContent = {queued:'Väntar på sin tur…', synthesizing:job.engine === 'chatterbox' ? 'Skapar naturligt svenskt tal… Det kan ta en stund.' : 'Läser din svenska replik…', converting:`Formar rösten för ${voices[job.speaker]?.name || job.speaker}…`}[job.state] || 'Skapar din replik…';
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
    const name = voices[result.speaker]?.name || result.speaker;
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
document.querySelectorAll('[name=speaker]').forEach(radio => radio.addEventListener('change', () => {
  castVoice.value = ''; update();
}));
castVoice.addEventListener('change', () => {
  const radios = [...document.querySelectorAll('[name=speaker]')];
  if (castVoice.value) radios.forEach(radio => { radio.checked = false; });
  else if (!radios.some(radio => radio.checked)) {
    const first = radios.find(radio => !radio.disabled);
    if (first) first.checked = true;
  }
  update();
});
document.querySelectorAll('[data-text]').forEach(preset => preset.addEventListener('click', () => { text.value = preset.dataset.text; update(); text.focus(); }));
document.querySelector('#pitch').addEventListener('input', event => { const value = Number(event.target.value); document.querySelector('#pitch-value').textContent = value > 0 ? `+${value}` : String(value); });
document.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); form.requestSubmit(); } });
request('/api/status').then(status => {
  voices = status.voices;
  const cards = new Set([...document.querySelectorAll('[name=speaker]')].map(radio => radio.value));
  for (const [identifier, voice] of Object.entries(voices)) {
    if (cards.has(identifier) || !voice.available) continue;
    const option = document.createElement('option');
    option.value = identifier; option.textContent = `${voice.name} · ${voice.description}`;
    castVoice.append(option);
    document.querySelector('#cast-picker').hidden = false;
  }
  document.querySelectorAll('[name=speaker]').forEach(radio => {
    const voice = voices[radio.value];
    radio.disabled = !voice?.available;
    radio.closest('.voice-card').querySelector('small').textContent = voice?.available ? voice.description : 'Röstmodellen är inte klar ännu';
  });
  if (!voices[selection()]?.available) {
    const first = document.querySelector('[name=speaker]:not(:disabled)');
    if (first) first.checked = true;
    else if (castVoice.options.length > 1) castVoice.value = castVoice.options[1].value;
    else showError('Inga röstmodeller hittades. Se startinstruktionerna för röststudion.');
  }
  if (status.default_engine === 'chatterbox' && voices[selection()]?.chatterbox_available) {
    engine.value = 'chatterbox';
  }
  if (Object.values(voices).filter(voice => voice.available).every(voice => voice.kind === 'trained')) {
    document.querySelector('#prototype p').textContent = 'Experimentella röster, tränade på svenska repliker från originalspelet. Röstlikhet och uttal kan variera.';
  }
  update();
}).catch(() => { showError('Röststudion svarar inte. Starta den lokala servern och ladda om sidan.'); });
update();
