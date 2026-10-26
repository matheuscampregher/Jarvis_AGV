// Teste da lógica real de preferências com elementos simulados; não é um teste visual.
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'web/app.js'), 'utf8');
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
assert.equal(new Set(ids).size, ids.length, 'IDs da interface devem ser únicos');

// O seletor do HTML não pode trazer nome de pessoa nem voz removida.
const bloco = html.slice(html.indexOf('<select id="voice">'), html.indexOf('</select>', html.indexOf('<select id="voice">')));
assert(bloco.includes('jarvis-pt'), 'o seletor deve oferecer jarvis-pt');
for (const removido of ['antonio', 'francisca', 'jenny', 'guy', 'Antônio', 'Francisca', 'Jenny'])
  assert(!bloco.includes(removido), 'voz removida no HTML: ' + removido);
assert(/id="pitch"[^>]*value="-4"/.test(html), 'o tom padrão no HTML deve ser -4');

const elements = Object.fromEntries(ids.map(id => [id, {
  value: '', disabled: false, textContent: '', options: [],
  classList: { toggle() {} }, setAttribute() {},
  replaceChildren(...options) { this.options = options; }
}]));
for (const match of source.matchAll(/\$\('#([a-z-]+)'\)/g)) assert(elements[match[1]], 'Elemento ausente: ' + match[1]);
Object.assign(elements.rate, {value:'115', min:'85', max:'150'});
Object.assign(elements.pitch, {value:'-4', min:'-10', max:'10'});
Object.assign(elements.volume, {value:'100', min:'50', max:'120'});
elements.language.value = 'pt-BR'; elements['voice-mode'].value = 'natural';
const storage = new Map();
const context = {
  document: { querySelector: selector => elements[selector.slice(1)], body: {classList: {toggle(){}}} },
  Option: function(label, value) { this.label = label; this.value = value; },
  SpeechQueue: class { constructor(){this.running=false;this.stops=0;} stop(){this.stops++;} },
  localStorage: {getItem:key=>storage.get(key)||null, setItem:(key,value)=>storage.set(key,value)}
};
vm.createContext(context);
vm.runInContext(source.slice(0, source.indexOf("$('#chat-form').addEventListener")), context);
const run = code => vm.runInContext(code, context);
const choices = () => elements.voice.options.map(option => option.value);
const labels = () => elements.voice.options.map(option => option.label);
const key = 'jarvis-agv.preferences.v1';

// Preferências salvas pela versão anterior: ids de pessoa são convertidos.
storage.set(key, JSON.stringify({language:'es-ES',voices:{'pt-BR':'francisca','en-US':'guy'},voiceOn:false}));
run('restorePreferences()');
assert.equal(elements.language.value,'pt-BR');
assert.deepEqual(choices(),['jarvis-pt']);
assert.equal(elements.voice.value,'jarvis-pt');
assert.deepEqual(labels(),['Jarvis — voz masculina (Brasil)']);
assert.equal(run('voiceOn'),false);
assert(run('speaker.stops')>0, 'Desativar leitura deve interromper a fila');

// Sem tom salvo, o padrão é o valor mais grave.
assert.equal(Number(elements.pitch.value), -4);
assert.equal(run('DEFAULT_PITCH'), -4);

// Inglês tem uma única voz masculina, e 'guy' salvo passou a apontar para ela.
elements.language.value='en-US';run("updateVoiceChoices(rememberedVoices['en-US'])");
assert.deepEqual(choices(),['jarvis-en']);
assert.equal(elements.voice.value,'jarvis-en');
run('savePreferences()');

// Catálogo do servidor só com ids antigos não reintroduz as vozes removidas.
run("applyCatalog({'pt-BR':{voices:{antonio:'a',francisca:'f'}},'en-US':{voices:{jenny:'j',guy:'g'}}})");
assert.deepEqual(choices(),['jarvis-en']);
assert(labels().every(l => l.startsWith('Jarvis — ')), 'rótulos devem ser do Jarvis');

// Catálogo do servidor com os ids atuais é respeitado.
run("applyCatalog({'pt-BR':{voices:{'jarvis-pt':'Jarvis — voz masculina (Brasil)'}},'en-US':{voices:{'jarvis-en':'Jarvis — voz masculina (inglês)'}}})");
assert.deepEqual(choices(),['jarvis-en']);
assert.equal(elements.voice.value,'jarvis-en');

run('restorePreferences()');
elements.language.value='pt-BR';run("updateVoiceChoices(rememberedVoices['pt-BR'])");
assert.equal(elements.voice.value,'jarvis-pt');
elements['voice-mode'].value='device';run('updateVoiceChoices()');
assert.equal(elements.voice.disabled,true);

storage.set(key,'JSON inválido');run('restorePreferences()');
assert.equal(elements.language.value,'pt-BR');
assert.equal(elements.voice.value,'jarvis-pt');
console.log('Vozes do Jarvis, migração de ids antigos, tom padrão e preferências salvas: OK');
