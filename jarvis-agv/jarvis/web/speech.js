/* Relógio para a medição. Fora do navegador (testes), cai no Date. */
const agora = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

/* Boca do rosto. Lê o áudio que está tocando e escreve a altura de cada barra
   nas variáveis --m0..--m6 do SVG. Sem áudio para medir (voz do dispositivo ou
   navegador sem Web Audio), o CSS assume com a animação em loop. */
const FaceMouth = {
  bars: 7,
  peso: [.72, .88, 1, 1.12, 1, .88, .72],
  nivel: [0, 0, 0, 0, 0, 0, 0],
  ctx: null, analyser: null, data: null, raf: 0, svg: null,

  alvo() {
    if (!this.svg && typeof document !== 'undefined') this.svg = document.querySelector('.face');
    return this.svg;
  },

  /* Só pode existir um MediaElementSource por elemento, e criá-lo exige um
     gesto do usuário; por isso só é chamado a partir de unlock(). */
  conectar(audio) {
    if (this.analyser) return true;
    const Ctx = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext);
    if (!Ctx || !audio) return false;
    try {
      this.ctx = new Ctx();
      const fonte = this.ctx.createMediaElementSource(audio);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 128;
      this.analyser.smoothingTimeConstant = .7;
      fonte.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
      this.data = new Uint8Array(this.analyser.frequencyBinCount);
      return true;
    } catch (_) {
      this.ctx = null; this.analyser = null;
      return false;
    }
  },

  retomar() {
    if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume().catch(() => {});
  },

  escrever(valores) {
    const face = this.alvo();
    if (!face) return;
    for (let i = 0; i < this.bars; i++) face.style.setProperty('--m' + i, valores[i].toFixed(3));
  },

  simular() {
    this.parar();
    if (typeof document !== 'undefined') document.body.classList.add('mouth-sim');
  },

  iniciar() {
    if (!this.analyser) return this.simular();
    document.body.classList.remove('mouth-sim');
    this.retomar();
    cancelAnimationFrame(this.raf);
    const faixas = Math.min(this.data.length - 1, 28);
    const passo = Math.max(1, Math.floor(faixas / this.bars));
    const quadro = () => {
      this.analyser.getByteFrequencyData(this.data);
      const valores = [];
      for (let i = 0; i < this.bars; i++) {
        let soma = 0;
        for (let j = 0; j < passo; j++) soma += this.data[1 + i * passo + j] || 0;
        const bruto = Math.min(1, (soma / passo / 255) * 2.1) * this.peso[i];
        this.nivel[i] = this.nivel[i] * .45 + bruto * .55;
        valores.push(.16 + this.nivel[i] * 1.25);
      }
      this.escrever(valores);
      this.raf = requestAnimationFrame(quadro);
    };
    this.raf = requestAnimationFrame(quadro);
  },

  parar() {
    if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(this.raf);
    this.raf = 0;
    if (typeof document !== 'undefined') document.body.classList.remove('mouth-sim');
    this.nivel = this.nivel.map(() => 0);
    this.escrever(new Array(this.bars).fill(.16));
  }
};

/* Fila de fala: gera e reproduz uma frase por vez, sem esperar a resposta inteira. */
class SpeechQueue {
  constructor(audio, getOptions, report) {
    this.audio = audio;
    this.getOptions = getOptions;
    this.report = report;
    this.jobs = [];
    this.epoch = 0;
    this.running = false;
    this.controllers = new Set();
    this.finishPlay = null;
    this.measureAt = null;
    this.measured = true;
  }

  /* Marca o instante do envio da pergunta, para medir o tempo até o 1º áudio. */
  startMeasure(label = 'pergunta') {
    this.measureAt = agora();
    this.measureLabel = label;
    this.measured = false;
  }

  noteFirstAudio() {
    if (this.measured || this.measureAt === null) return;
    this.measured = true;
    const ms = Math.round(agora() - this.measureAt);
    console.log(`[Jarvis] primeiro áudio em ${ms} ms (${this.measureLabel})`);
  }

  unlock() {
    /* Aqui existe um clique do usuário, único momento em que o navegador deixa
       ligar o analisador de áudio que move a boca. */
    FaceMouth.conectar(this.audio);
    FaceMouth.retomar();
    this.audio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
    this.audio.load();
    this.audio.play().catch(() => {});
  }

  stop() {
    this.epoch += 1;
    this.jobs = [];
    this.running = false;
    FaceMouth.parar();
    this.measureAt = null;
    this.measured = true;
    this.controllers.forEach(controller => controller.abort());
    this.controllers.clear();
    this.audio.onended = null;
    this.audio.onerror = null;
    this.audio.pause();
    this.audio.removeAttribute('src');
    this.audio.load();
    if (this.finishPlay) {
      this.finishPlay();
      this.finishPlay = null;
    }
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    this.report('Voz pronta.');
  }

  add(text) {
    text = String(text || '').replace(/[*#`]/g, '').trim();
    if (!text) return;
    while (text.length > 600) {
      let cut = text.lastIndexOf(' ', 600);
      if (cut < 1) cut = 600;
      this.jobs.push({ text: text.slice(0, cut), options: this.getOptions() });
      text = text.slice(cut).trim();
    }
    if (text) this.jobs.push({ text, options: this.getOptions() });
    if (!this.running) this.run(this.epoch);
    else this.preload();
  }

  async requestAudio(job) {
    if (job.options.mode === 'device') return { device: true };
    const controller = new AbortController();
    this.controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), 28000);
    try {
      this.report('Gerando áudio natural...');
      const response = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          texto: job.text,
          idioma: job.options.language,
          voz: job.options.voice,
          velocidade: job.options.rate,
          tom: job.options.pitch,
          volume: job.options.volume
        }),
        signal: controller.signal
      });
      let errorData = null;
      if (!response.ok) {
        try { errorData = await response.json(); } catch (_) {}
        const error = new Error(errorData?.erro || 'A voz natural não conseguiu gerar áudio.');
        error.code = errorData?.codigo || 'voice_error';
        throw error;
      }
      const blob = await response.blob();
      if (!blob.size) throw new Error('O servidor devolveu um áudio vazio.');
      return { blob };
    } catch (error) {
      return { error };
    } finally {
      clearTimeout(timer);
      this.controllers.delete(controller);
    }
  }

  preload() {
    if (this.jobs.length && !this.jobs[0].ready) this.jobs[0].ready = this.requestAudio(this.jobs[0]);
  }

  getDeviceVoice(language) {
    if (!['pt-BR', 'en-US'].includes(language)) return undefined;
    const voices = window.speechSynthesis?.getVoices?.() || [];
    const wanted = language.toLowerCase();
    return voices.find(item => item.lang.toLowerCase() === wanted)
      || voices.find(item => item.lang.toLowerCase().startsWith(wanted.slice(0, 2)));
  }

  waitForDeviceVoice(language) {
    const found = this.getDeviceVoice(language);
    if (found) return Promise.resolve(found);
    return new Promise(resolve => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(this.getDeviceVoice(language)); } };
      window.speechSynthesis?.addEventListener?.('voiceschanged', finish, { once: true });
      setTimeout(finish, 900);
    });
  }

  async play(job, data, epoch) {
    if (epoch !== this.epoch) return;
    if (data.error) throw data.error;
    if (data.device) {
      if (!('speechSynthesis' in window)) throw new Error('Este navegador não oferece voz do dispositivo.');
      const voice = await this.waitForDeviceVoice(job.options.language);
      if (epoch !== this.epoch) return;
      if (!voice) throw new Error('Não encontrei uma voz instalada para este idioma.');
      await new Promise((resolve, reject) => {
        const utterance = new SpeechSynthesisUtterance(job.text);
        utterance.voice = voice;
        utterance.lang = voice.lang;
        utterance.rate = job.options.rate;
        utterance.pitch = Math.max(.1, 1 + job.options.pitch / 20);
        utterance.volume = Math.max(0, Math.min(1, job.options.volume));
        utterance.onstart = () => { this.noteFirstAudio(); FaceMouth.simular(); this.report('Falando...'); };
        utterance.onend = resolve;
        utterance.onerror = () => reject(new Error('O navegador interrompeu a voz do dispositivo.'));
        this.finishPlay = resolve;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
      });
    } else {
      const url = URL.createObjectURL(data.blob);
      try {
        await new Promise((resolve, reject) => {
          this.finishPlay = resolve;
          this.audio.onended = resolve;
          this.audio.onerror = () => reject(new Error('O navegador não conseguiu reproduzir o áudio natural. Clique em Testar voz ou Ouvir última resposta.'));
          this.audio.src = url;
          this.audio.load();
          this.audio.play().then(() => {
            if (epoch !== this.epoch) return;
            this.noteFirstAudio();
            FaceMouth.iniciar();
            this.report('Falando...');
          }).catch(() => reject(new Error('O navegador bloqueou o áudio. Clique em Testar voz uma vez e tente novamente.')));
        });
      } finally {
        URL.revokeObjectURL(url);
      }
    }
    FaceMouth.parar();
    if (epoch === this.epoch) {
      this.finishPlay = null;
      this.report('Voz pronta.');
    }
  }

  async run(epoch) {
    this.running = true;
    try {
      while (this.jobs.length && epoch === this.epoch) {
        const job = this.jobs.shift();
        const data = job.ready ? await job.ready : await this.requestAudio(job);
        if (epoch !== this.epoch) return;
        this.preload();
        await this.play(job, data, epoch);
      }
    } catch (error) {
      if (epoch === this.epoch) {
        this.stop();
        this.report(error.message || 'Não foi possível reproduzir a voz.');
      }
    } finally {
      if (epoch === this.epoch) this.running = false;
    }
  }
}

/* Fim de frase para a fala. Dois pontos entram porque o modelo costuma usar
   "Resumindo:" antes de uma lista, e ali já cabe uma pausa natural. */
const SENTENCE_END = '.!?:';
const MIN_SENTENCE = 15;
const MAX_SENTENCE = 240;

/* Separa o que já dá para falar do que ainda está chegando.
   Só devolve uma frase com SENTENCE_END (ou quebra de linha) e pelo menos
   MIN_SENTENCE caracteres. Nunca corta uma palavra: sem pontuação, o corte de
   segurança cai no último espaço. Com force (fim do stream), o resto sai como
   está, mesmo sem pontuação final. */
function takeSentences(text, force = false, min = MIN_SENTENCE) {
  const sentences = [];
  const minimo = Math.max(1, Number(min) || MIN_SENTENCE);
  while (text.length) {
    let cut = 0;
    for (let i = minimo - 1; i < text.length; i++) {
      const char = text[i];
      if (char === '\n') { cut = i + 1; break; }
      if (!SENTENCE_END.includes(char)) continue;
      const next = text[i + 1];
      /* Sem o caractere seguinte não se sabe se a palavra ou o número continua
         (1.500, Dr., 10:30). Espera o próximo pedaço; no fim, o force resolve. */
      if (next === undefined) break;
      if (!/\s/.test(next)) continue;
      cut = i + 1;
      break;
    }
    if (!cut && text.length > MAX_SENTENCE) {
      cut = text.lastIndexOf(' ', MAX_SENTENCE);
      if (cut < 1) cut = MAX_SENTENCE;
    }
    if (!cut) break;
    const piece = text.slice(0, cut).trim();
    if (piece) sentences.push(piece);
    text = text.slice(cut).trimStart();
  }
  if (force && text.trim()) {
    sentences.push(text.trim());
    text = '';
  }
  return { sentences, rest: text };
}
