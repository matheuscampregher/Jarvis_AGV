const $ = selector => document.querySelector(selector);
const history = [];
let busy = false;
let voiceOn = true;
let lastAnswer = '';
let speechBuffer = '';
const DEFAULT_CATALOG = {
  'pt-BR': { label: 'Português (Brasil)', sample: 'Olá! Eu sou o Jarvis AGV. Esta é uma amostra da minha voz.', voices: { 'jarvis-pt': 'Jarvis — voz masculina (Brasil)' } },
  'en-US': { label: 'English (United States)', sample: 'Hello! I am Jarvis AGV. This is a sample of my voice.', voices: { 'jarvis-en': 'Jarvis — voz masculina (inglês)' } }
};
const DEFAULT_VOICES = { 'pt-BR': 'jarvis-pt', 'en-US': 'jarvis-en' };
const DEFAULT_PITCH = -4;
/* Preferências salvas por versões anteriores usavam nomes de pessoas. */
const LEGACY_VOICE_IDS = { antonio: 'jarvis-pt', francisca: 'jarvis-pt', jenny: 'jarvis-en', guy: 'jarvis-en' };
function migrateVoiceId(id, language) {
  const voices = (DEFAULT_CATALOG[language] || DEFAULT_CATALOG['pt-BR']).voices;
  if (typeof id === 'string') {
    if (Object.hasOwn(voices, id)) return id;
    const moved = LEGACY_VOICE_IDS[id.trim().toLowerCase()];
    if (moved && Object.hasOwn(voices, moved)) return moved;
  }
  return DEFAULT_VOICES[language] || DEFAULT_VOICES['pt-BR'];
}
const PREFERENCES_KEY = 'jarvis-agv.preferences.v1';
const GREETING = 'Olá! Eu sou o Jarvis AGV. Posso ajudar nos estudos e consultar as aulas da escola. O que você quer saber?';
let catalog = DEFAULT_CATALOG;
let rememberedVoices = {};
const report = value => {
  $('#voice-status').textContent = value;
  document.body.classList.toggle('speaking', value === 'Falando...');
};
const currentOptions = () => ({
  mode: $('#voice-mode').value,
  language: $('#language').value,
  voice: $('#voice').value,
  rate: Number($('#rate').value) / 100,
  pitch: Number($('#pitch').value),
  volume: Number($('#volume').value) / 100
});
const speaker = new SpeechQueue($('#audio'), currentOptions, report);

function bubble(value, who, typing = false) {
  const wrap = document.createElement('div');
  wrap.className = `message ${who}`;
  wrap.innerHTML = `<div class="avatar" aria-hidden="true">${who === 'bot' ? '<img src="/assets/agv-logo.png" alt="" width="30" height="20">' : 'VC'}</div><div class="bubble"></div>`;
  const content = wrap.querySelector('.bubble');
  if (typing) content.innerHTML = '<div class="typing"><i></i><i></i><i></i></div>';
  else { const text = document.createElement('span'); text.textContent = value; content.append(text); }
  const time = document.createElement('small'); time.className = 'message-time'; time.textContent = typing ? 'processando...' : 'agora'; content.append(time);
  $('#messages').append(wrap);
  $('#messages').scrollTop = $('#messages').scrollHeight;
  return { wrap, content };
}

function updateMessage(target, text) {
  target.content.innerHTML = '';
  const value = document.createElement('span'); value.textContent = text; target.content.append(value);
  const time = document.createElement('small'); time.className = 'message-time'; time.textContent = 'agora'; target.content.append(time);
  $('#messages').scrollTop = $('#messages').scrollHeight;
}

/* A primeira frase sai com menos texto, para o Jarvis começar a falar quase
   junto com o que aparece na tela. As seguintes usam o tamanho normal. */
const PRIMEIRA_FRASE = 6;
let primeiraFraseDita = false;

function feedSpeech(text, force = false) {
  speechBuffer += text;
  const result = takeSentences(speechBuffer, force, primeiraFraseDita ? undefined : PRIMEIRA_FRASE);
  speechBuffer = result.rest;
  if (result.sentences.length) primeiraFraseDita = true;
  if (voiceOn) result.sentences.forEach(sentence => speaker.add(sentence));
}

function setStatus(element, value, warning = false) {
  element.textContent = value;
  element.classList.toggle('warn', warning);
}

function updateRangeLabels() {
  $('#rate-value').textContent = `${$('#rate').value}%`;
  $('#pitch-value').textContent = `${Number($('#pitch').value) > 0 ? '+' : ''}${$('#pitch').value}`;
  $('#volume-value').textContent = `${$('#volume').value}%`;
}

function updateVoiceChoices(preferred) {
  let language = $('#language').value;
  if (!Object.hasOwn(DEFAULT_CATALOG, language)) language = $('#language').value = 'pt-BR';
  const data = catalog[language] || DEFAULT_CATALOG[language];
  const select = $('#voice');
  /* Converte um id antigo ('antonio', 'jenny') no atual antes de escolher. */
  const previous = migrateVoiceId(preferred || select.value, language);
  select.replaceChildren(...Object.entries(data.voices).map(([id, label]) => new Option(label, id)));
  select.value = Object.hasOwn(data.voices, previous) ? previous
    : (Object.hasOwn(data.voices, DEFAULT_VOICES[language]) ? DEFAULT_VOICES[language] : Object.keys(data.voices)[0]);
  rememberedVoices[language] = select.value;
  select.disabled = $('#voice-mode').value === 'device';
  if (!speaker.running && !busy) report(voiceOn ? 'Voz pronta.' : 'Respostas por voz desativadas.');
}

function applyCatalog(incoming) {
  if (!incoming || typeof incoming !== 'object') return;
  const selected = $('#voice').value;
  catalog = Object.fromEntries(Object.entries(DEFAULT_CATALOG).map(([language, fallback]) => {
    const available = incoming[language]?.voices;
    const pairs = Object.entries(fallback.voices).filter(([id]) => available && Object.hasOwn(available, id));
    return [language, { ...fallback, voices: pairs.length ? Object.fromEntries(pairs) : fallback.voices }];
  }));
  updateVoiceChoices(selected);
}

function savePreferences() {
  rememberedVoices[$('#language').value] = $('#voice').value;
  try {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ ...currentOptions(), voiceOn, voices: rememberedVoices }));
  } catch (_) { /* A interface continua funcionando se o armazenamento estiver bloqueado. */ }
}

function restorePreferences() {
  let saved = {};
  try {
    const value = JSON.parse(localStorage.getItem(PREFERENCES_KEY) || '{}');
    if (value && typeof value === 'object' && !Array.isArray(value)) saved = value;
  } catch (_) {}
  $('#language').value = Object.hasOwn(DEFAULT_CATALOG, saved.language) ? saved.language : 'pt-BR';
  $('#voice-mode').value = saved.mode === 'device' ? 'device' : 'natural';
  const storedVoices = saved.voices && typeof saved.voices === 'object' && !Array.isArray(saved.voices) ? saved.voices : {};
  rememberedVoices = {};
  for (const language of Object.keys(DEFAULT_CATALOG)) {
    if (Object.hasOwn(storedVoices, language)) rememberedVoices[language] = migrateVoiceId(storedVoices[language], language);
  }
  for (const [id, input, fallback, scale] of [['rate', saved.rate, 115, 100], ['pitch', saved.pitch, DEFAULT_PITCH, 1], ['volume', saved.volume, 100, 100]]) {
    const element = $('#' + id);
    const value = typeof input === 'number' && Number.isFinite(input) ? input * scale : fallback;
    element.value = Math.max(Number(element.min), Math.min(Number(element.max), value));
  }
  setVoiceToggle(saved.voiceOn !== false);
  updateVoiceChoices(rememberedVoices[$('#language').value] || DEFAULT_VOICES[$('#language').value]);
  updateRangeLabels();
  savePreferences();
}

function setVoiceToggle(value) {
  voiceOn = value;
  const toggle = $('#voice-toggle');
  toggle.classList.toggle('on', voiceOn);
  toggle.setAttribute('aria-pressed', String(voiceOn));
  if (!voiceOn) { speaker.stop(); report('Respostas por voz desativadas.'); }
}

async function sendQuestion(question) {
  if (busy || !question.trim()) return;
  const input = $('#message');
  speaker.stop(); speaker.unlock(); speaker.startMeasure('pergunta'); speechBuffer = ''; primeiraFraseDita = false; lastAnswer = ''; $('#replay').disabled = true;
  input.value = '';
  bubble(question, 'user');
  const pending = bubble('', 'bot', true);
  busy = true; $('#chat-form button[type="submit"]').disabled = true;
  $('#language').disabled = true; $('#clear-chat').disabled = true;
  document.body.classList.add('thinking');
  $('#conversation-state').textContent = 'Preparando resposta';
  document.querySelectorAll('.quick').forEach(button => { button.disabled = true; });
  const controller = new AbortController();
  let timer = setTimeout(() => controller.abort(), 90000);
  const refresh = () => { clearTimeout(timer); timer = setTimeout(() => controller.abort(), 90000); };
  let answer = '';
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensagem: question, idioma: $('#language').value, historico: history }), signal: controller.signal
    });
    if (!response.ok) { const error = await response.json(); throw new Error(error.erro || 'O Jarvis encontrou um erro.'); }
    if (response.headers.get('Content-Type')?.includes('application/json')) {
      answer = (await response.json()).resposta || '';
      updateMessage(pending, answer); feedSpeech(answer, true);
    } else {
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let finished = false;
      while (true) {
        const result = await reader.read(); if (result.done) break; refresh(); buffer += decoder.decode(result.value, { stream: true });
        const lines = buffer.split('\n'); buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const packet = JSON.parse(line);
          if (packet.erro) throw new Error(packet.erro);
          if (packet.texto) { answer += packet.texto; updateMessage(pending, answer); feedSpeech(packet.texto); }
          if (packet.fim) { finished = true; if (packet.vazio) throw new Error('A IA não gerou texto. Tente novamente.'); }
        }
      }
      if (!finished) throw new Error('A conexão terminou antes da resposta.');
      feedSpeech('', true);
    }
    lastAnswer = answer; $('#replay').disabled = false;
    history.push({ role: 'user', content: question }, { role: 'assistant', content: answer });
    if (history.length > 16) history.splice(0, 2);
  } catch (error) {
    speaker.stop();
    updateMessage(pending, error.name === 'AbortError' ? 'A resposta demorou demais. Tente uma pergunta curta.' : error.message);
  } finally {
    clearTimeout(timer); busy = false; $('#chat-form button[type="submit"]').disabled = false;
    $('#language').disabled = false; $('#clear-chat').disabled = false;
    document.body.classList.remove('thinking');
    $('#conversation-state').textContent = 'Pode perguntar';
    document.querySelectorAll('.quick').forEach(button => { button.disabled = false; });
    if (!$('#settings-dialog').open) input.focus();
  }
}

$('#chat-form').addEventListener('submit', event => { event.preventDefault(); sendQuestion($('#message').value.trim()); });
document.querySelectorAll('.quick').forEach(button => button.addEventListener('click', () => sendQuestion(button.dataset.question)));
$('#voice-toggle').addEventListener('click', () => { setVoiceToggle(!voiceOn); savePreferences(); });
$('#stop-voice').addEventListener('click', () => { setVoiceToggle(false); savePreferences(); report('Leitura interrompida.'); });
$('#replay').addEventListener('click', () => { if (!lastAnswer) return; setVoiceToggle(true); savePreferences(); speaker.stop(); speaker.unlock(); speaker.startMeasure('ouvir de novo'); takeSentences(lastAnswer, true).sentences.forEach(sentence => speaker.add(sentence)); });
$('#test-voice').addEventListener('click', () => { setVoiceToggle(true); savePreferences(); speaker.stop(); speaker.unlock(); speaker.startMeasure('testar voz'); speaker.add((catalog[$('#language').value] || catalog['pt-BR']).sample); });
$('#language').addEventListener('change', () => { speaker.stop(); updateVoiceChoices(rememberedVoices[$('#language').value]); savePreferences(); });
$('#voice-mode').addEventListener('change', () => { speaker.stop(); updateVoiceChoices(); savePreferences(); });
$('#voice').addEventListener('change', () => { speaker.stop(); savePreferences(); });
['rate', 'pitch', 'volume'].forEach(id => $('#' + id).addEventListener('input', () => { updateRangeLabels(); savePreferences(); }));

const settingsDialog = $('#settings-dialog');
$('#open-settings').addEventListener('click', () => settingsDialog.showModal());
$('#close-settings').addEventListener('click', () => settingsDialog.close());
settingsDialog.addEventListener('click', event => {
  const bounds = settingsDialog.getBoundingClientRect();
  if (event.target === settingsDialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) settingsDialog.close();
});
$('#clear-chat').addEventListener('click', () => {
  if (busy) return;
  speaker.stop(); history.length = 0; lastAnswer = ''; speechBuffer = ''; primeiraFraseDita = false;
  $('#replay').disabled = true; $('#messages').replaceChildren();
  bubble(GREETING, 'bot'); $('#message').focus();
});
restorePreferences();

fetch('/api/status').then(response => {
  if (!response.ok) throw new Error('Servidor indisponível.');
  return response.json();
}).then(status => {
  applyCatalog(status.languages);
  $('#system-dot').classList.add('connected'); $('#system-label').textContent = 'Conectado';
  setStatus($('#server-status'), 'online');
  updateSheetStatus(status.database);
  setStatus($('#natural-status'), status.natural_voice ? 'instalada' : 'não instalada', !status.natural_voice);
  updateVoiceChoices();
  if (!status.natural_voice && $('#voice-mode').value === 'natural') report('Voz natural indisponível. Use a voz do dispositivo em Configurações.');
}).catch(() => {
  $('#system-dot').classList.add('disconnected'); $('#system-label').textContent = 'Sem conexão';
  setStatus($('#server-status'), 'offline', true); report('Não foi possível conectar ao Jarvis. Tente recarregar a página.');
});

function updateSheetStatus(db) {
  const data = db || {};
  setStatus($('#db-status'), data.label || 'Não configurada', data.state === 'error' || data.state === 'not_configured');
}

// Só lê o estado do servidor. Este polling não faz consultas extras ao Google.
setInterval(() => {
  if (document.hidden) return;
  fetch('/api/status').then(response => response.ok ? response.json() : null)
    .then(status => { if (status) updateSheetStatus(status.database); })
    .catch(() => {});
}, 15000);

// Atualiza o seletor com as vozes reais quando o servidor consegue consultá-las.
fetch('/api/voices').then(response => response.ok ? response.json() : null).then(voices => {
  if (voices) applyCatalog(voices);
}).catch(() => {});

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!Recognition) { $('#mic').disabled = true; $('#mic').title = 'Microfone indisponível neste navegador. Use o campo de texto.'; }
else {
  const recognition = new Recognition(); recognition.lang = 'pt-BR'; recognition.interimResults = false;
  let microphoneError = false;
  recognition.onstart = () => { microphoneError = false; document.body.classList.add('listening'); $('#mic').classList.add('active'); report('Ouvindo pelo microfone...'); };
  recognition.onend = () => { document.body.classList.remove('listening'); $('#mic').classList.remove('active'); if (!microphoneError && !busy && !speaker.running) report('Microfone encerrado.'); };
  recognition.onerror = event => { microphoneError = true; report('Microfone: ' + event.error + '. Verifique a permissão.'); };
  recognition.onresult = event => { const phrase = event.results[0][0].transcript.trim(); if (phrase) sendQuestion(phrase); };
  $('#mic').addEventListener('click', () => { if (busy) return report('Aguarde a resposta atual.'); speaker.stop(); try { recognition.lang = $('#language').value; recognition.start(); } catch (_) { report('Aguarde o microfone terminar.'); } });
}
updateRangeLabels();
