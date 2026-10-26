const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(require('path').join(__dirname,'../web/speech.js'),'utf8'),context);
let first=context.takeSentences('Esta é a primeira frase. A segunda ainda');
assert.strictEqual(first.sentences[0],'Esta é a primeira frase.');assert.strictEqual(first.rest,'A segunda ainda');
let final=context.takeSentences(first.rest+' está chegando.',true);
assert.strictEqual(final.sentences[0],'A segunda ainda está chegando.');
let decimal=context.takeSentences('O valor é 2.5 reais. Ainda escrevendo');assert.strictEqual(decimal.sentences[0],'O valor é 2.5 reais.');
const long='palavra '.repeat(200);const split=context.takeSentences(long,true);assert.ok(split.sentences.every(s=>s.length<=241));assert.strictEqual(split.sentences.join(' '),long.trim());
console.log('Frases iniciam antes do fim, sem truncar o texto: OK');

// Mínimo de 15 caracteres: frases curtas se juntam em vez de virar áudio picado.
assert.deepEqual(Array.from(context.takeSentences('Sim. Ok. Agora vai a frase inteira. resto').sentences),
  ['Sim. Ok. Agora vai a frase inteira.']);
assert.deepEqual(Array.from(context.takeSentences('Sim. Ok. Nao. ').sentences), []);
assert.deepEqual(Array.from(context.takeSentences('Sim. Ok. Nao. ', true).sentences), ['Sim. Ok. Nao.']);

// Dois pontos e quebra de linha também fecham frase.
assert.strictEqual(context.takeSentences('Resumindo os pontos: o resto vem depois').sentences[0],
  'Resumindo os pontos:');
assert.strictEqual(context.takeSentences('Primeira linha aqui\nsegunda').sentences[0], 'Primeira linha aqui');

// Nunca corta no meio de número nem de hora: espera o pedaço seguinte.
assert.deepEqual(Array.from(context.takeSentences('A aula comeca as 10:30 e termina').sentences), []);
assert.strictEqual(context.takeSentences('A aula comeca as 10:30 e termina depois. ').sentences[0],
  'A aula comeca as 10:30 e termina depois.');

// Streaming em pedaços: ordem preservada, nada perdido e nenhuma palavra cortada.
const texto = 'A fotossintese transforma luz em energia. Ela ocorre no cloroplasto, onde fica a clorofila. '
  + 'Resumindo: entra luz, saem acucar e oxigenio. A planta cresce com isso.';
const palavras = texto.match(/\S+\s*/g);
let buffer = '', faladas = [];
palavras.forEach((pedaco, indice) => {
  buffer += pedaco;
  const resultado = context.takeSentences(buffer, indice === palavras.length - 1);
  buffer = resultado.rest;
  faladas = faladas.concat(resultado.sentences);
});
assert.strictEqual(buffer, '', 'o buffer deve terminar vazio');
assert.strictEqual(faladas.join(' ').replace(/\s+/g, ' '), texto.replace(/\s+/g, ' '));
assert.ok(faladas.length >= 3, 'deve falar em partes, nao de uma vez: ' + faladas.length);
faladas.slice(0, -1).forEach(frase => assert.ok(frase.length >= 15, 'frase curta: ' + frase));
faladas.forEach(frase => assert.ok(texto.includes(frase), 'palavra cortada em: ' + frase));
console.log('Minimo de 15 caracteres, dois pontos, horas e streaming em pedacos: OK');

// A medição do primeiro áudio funciona e só registra uma vez por pergunta.
{
  const registros = [];
  const SpeechQueueMedida = vm.runInContext('SpeechQueue', context);
  context.console = { log: texto => registros.push(texto) };
  context.window = { speechSynthesis: { cancel() {} } };
  const fila = new SpeechQueueMedida({pause(){},load(){},removeAttribute(){}}, ()=>({}), ()=>{});
  fila.noteFirstAudio();
  assert.strictEqual(registros.length, 0, 'sem startMeasure nao registra');
  fila.startMeasure('pergunta');
  fila.noteFirstAudio();
  fila.noteFirstAudio();
  assert.strictEqual(registros.length, 1, 'registra uma vez por pergunta');
  assert.ok(/primeiro áudio em \d+ ms \(pergunta\)/.test(registros[0]), registros[0]);
  fila.stop();
  fila.noteFirstAudio();
  assert.strictEqual(registros.length, 1, 'parar cancela a medicao pendente');
}
console.log('Medicao do tempo ate o primeiro audio: OK');

// Uma preferência em inglês nunca deve escolher uma voz em português/espanhol.
context.window={speechSynthesis:{getVoices:()=>[{lang:'pt-BR',name:'Português'},{lang:'es-ES',name:'Espanhol'}],cancel:()=>{}}};
const SpeechQueue=vm.runInContext('SpeechQueue',context);
const audio={pause(){},load(){},removeAttribute(){}};
const queue=new SpeechQueue(audio,()=>({}),()=>{});
assert.strictEqual(queue.getDeviceVoice('en-US'),undefined);
assert.strictEqual(queue.getDeviceVoice('es-ES'),undefined);
assert.strictEqual(queue.getDeviceVoice('pt-BR').name,'Português');

(async()=>{
  // Parar durante a espera pelas vozes não pode iniciar uma fala atrasada.
  let release,spoken=0;
  queue.waitForDeviceVoice=()=>new Promise(resolve=>{release=resolve;});
  context.window.speechSynthesis.speak=()=>{spoken++;};
  const playing=queue.play({text:'Teste',options:{language:'pt-BR'}},{device:true},queue.epoch);
  queue.stop();release({lang:'pt-BR'});await playing;
  assert.strictEqual(spoken,0);
  // A Web Speech API aceita volume de 0 a 1, mesmo com ganho natural em 120%.
  queue.waitForDeviceVoice=async()=>({lang:'en-US'});
  context.SpeechSynthesisUtterance=function(text){this.text=text;};
  context.window.speechSynthesis.speak=utterance=>{
    assert.strictEqual(utterance.volume,1);
    assert.strictEqual(utterance.lang,'en-US');
    utterance.onstart();utterance.onend();
  };
  await queue.play({text:'Hello',options:{language:'en-US',rate:1.15,pitch:0,volume:1.2}},{device:true},queue.epoch);
  console.log('Idioma, cancelamento e volume da voz do dispositivo: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
