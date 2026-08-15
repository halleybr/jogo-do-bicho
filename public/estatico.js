"use strict";

/* Modo estático (GitHub Pages): quando o site é servido sem o backend Python
   (as rotas /api/* devolvem 404/HTML), emula as APIs a partir dos JSONs
   gerados por gerar_estatico.py (public/dados/*). Também traz a numerologia
   (palpite pessoal) para o navegador, com a mesma fórmula do Palpitômetro do
   ojogodobicho.com (FNV-1a 32 bits + xorshift32). */

const estatico = {
  ANIMAIS: {
    1: ["Avestruz", "🐦"], 2: ["Águia", "🦅"], 3: ["Burro", "🐴"],
    4: ["Borboleta", "🦋"], 5: ["Cachorro", "🐕"], 6: ["Cabra", "🐐"],
    7: ["Carneiro", "🐑"], 8: ["Camelo", "🐫"], 9: ["Cobra", "🐍"],
    10: ["Coelho", "🐇"], 11: ["Cavalo", "🐎"], 12: ["Elefante", "🐘"],
    13: ["Galo", "🐓"], 14: ["Gato", "🐈"], 15: ["Jacaré", "🐊"],
    16: ["Leão", "🦁"], 17: ["Macaco", "🐒"], 18: ["Porco", "🐷"],
    19: ["Pavão", "🦚"], 20: ["Peru", "🦃"], 21: ["Touro", "🐂"],
    22: ["Tigre", "🐅"], 23: ["Urso", "🐻"], 24: ["Veado", "🦌"],
    25: ["Vaca", "🐄"],
  },
  NOMES_LOTERIAS: {
    PPT: "Para Todos", PTM: "PT Manhã", PT: "PT Tarde", PTV: "PT Vespera",
    PTN: "PT Noite", FED: "Federal", COR: "Coruja",
  },
  HORARIOS: {
    PPT: "09:30", PTM: "11:30", PT: "14:30", PTV: "16:30",
    PTN: "18:20", FED: "20:00", COR: "21:30",
  },
  /* Apurações por dia da semana (0=domingo), em minutos desde a meia-noite —
     mesma grade do Palpitômetro. */
  GRADE_APURACOES: {
    0: [["FED", 690], ["PT", 870], ["PTV", 990]],
    1: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    2: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    3: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["FED", 1200], ["COR", 1290]],
    4: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    5: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    6: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1170], ["COR", 1290]],
  },

  minutosLoteria(codigo) {
    const h = this.HORARIOS[codigo] || "";
    const [hh, mm] = h.split(":");
    const n = Number(hh) * 60 + Number(mm);
    return Number.isFinite(n) ? n : 0;
  },

  ultimoDia(hist) {
    const chaves = Object.keys((hist && hist.dias) || {}).sort();
    return chaves[chaves.length - 1] || null;
  },

  /* Carrega (uma vez por página) o histórico completo para busca/diário. */
  carregarHistorico() {
    if (!this._hist) {
      this._hist = fetch("dados/historico.json").then((r) => {
        if (!r.ok) throw new Error("dados/historico.json não encontrado");
        return r.json();
      });
    }
    return this._hist;
  },

  /* Equivale a GET /api/historico (consulta server.py). */
  consultarHistorico(hist, params) {
    params = params || {};
    const dias = Object.keys(hist.dias || {}).sort().map((k) => hist.dias[k]);
    const de = params.de || "";
    const ate = params.ate || "";
    const grupo = params.grupo !== undefined && params.grupo !== "" ? Number(params.grupo) : null;
    const numero = (params.numero || "").trim();
    const loteria = (params.loteria || "").trim().toUpperCase();
    let limite = parseInt(params.limite, 10);
    if (!Number.isFinite(limite)) limite = 100;
    limite = Math.max(1, Math.min(limite, 500));

    const resultados = [];
    for (const dia of dias) {
      if (de && dia.data < de) continue;
      if (ate && dia.data > ate) continue;
      for (const lot of dia.loterias) {
        if (loteria && lot.codigo !== loteria) continue;
        for (const p of lot.premios) {
          if (grupo && grupo !== p.grupo) continue;
          if (numero && !String(p.numero).includes(numero)) continue;
          const info = this.ANIMAIS[p.grupo] || [p.animal || "?", ""];
          resultados.push({
            data: dia.data,
            loteria: lot.codigo,
            nome_loteria: this.NOMES_LOTERIAS[lot.codigo] || lot.codigo,
            posicao: p.posicao,
            numero: p.numero,
            grupo: p.grupo,
            animal: info[0],
            emoji: info[1],
          });
          if (resultados.length >= 5000) break;
        }
        if (resultados.length >= 5000) break;
      }
      if (resultados.length >= 5000) break;
    }
    // mais recente primeiro: data e, no mesmo dia, apuração mais tardia
    resultados.sort((a, b) => {
      const ka = a.data + "|" + String(this.minutosLoteria(a.loteria)).padStart(5, "0");
      const kb = b.data + "|" + String(this.minutosLoteria(b.loteria)).padStart(5, "0");
      return ka < kb ? 1 : ka > kb ? -1 : 0;
    });
    const truncado = resultados.length > limite;
    return {
      total: truncado ? null : resultados.length,
      resultados: resultados.slice(0, limite),
      truncado,
    };
  },

  /* Equivale a GET /api/diario (consulta server.py). Lança erro
     "fora do arquivo disponível (inicio → fim)" para datas fora do arquivo. */
  consultarDiario(hist, dataStr) {
    const chaves = Object.keys(hist.dias || {}).sort();
    if (!chaves.length) throw new Error("histórico vazio");
    const inicio = chaves[0];
    const fim = chaves[chaves.length - 1];
    if (dataStr < inicio || dataStr > fim) {
      const e = new Error(`fora do arquivo disponível (${inicio} → ${fim})`);
      e.inicio = inicio;
      e.fim = fim;
      throw e;
    }
    const loterias = [];
    if (chaves.includes(dataStr)) {
      const dia = hist.dias[dataStr];
      for (const lot of dia.loterias) {
        const premios = lot.premios.map((p) => {
          const info = this.ANIMAIS[p.grupo] || [p.animal || "?", ""];
          return {
            posicao: p.posicao,
            numero: p.numero,
            grupo: p.grupo,
            animal: info[0],
            emoji: info[1],
          };
        });
        loterias.push({
          codigo: lot.codigo,
          nome: this.NOMES_LOTERIAS[lot.codigo] || lot.codigo,
          horario: this.HORARIOS[lot.codigo] || "",
          premios,
        });
      }
    }
    loterias.sort((a, b) => this.minutosLoteria(b.codigo) - this.minutosLoteria(a.codigo));

    const idx = chaves.indexOf(dataStr);
    let anterior = null;
    let proximo = null;
    if (idx !== -1) {
      anterior = idx > 0 ? chaves[idx - 1] : null;
      proximo = idx < chaves.length - 1 ? chaves[idx + 1] : null;
    } else {
      // buraco no arquivo: vizinhos mais próximos com dados
      const antes = chaves.filter((c) => c < dataStr);
      const depois = chaves.filter((c) => c > dataStr);
      anterior = antes.length ? antes[antes.length - 1] : null;
      proximo = depois.length ? depois[0] : null;
    }
    return {
      data: dataStr,
      tem_dados: loterias.length > 0,
      loterias,
      anterior,
      proximo,
      inicio,
      fim,
    };
  },

  /* ---------- palpite pessoal (numerologia) — igual ao palpites.py ---------- */

  fnv1a32(s) {
    // Math.imul evita overflow de precisão dupla (o produto passa de 2^53)
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) {
      h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0;
    }
    return h >>> 0;
  },

  xorshift32(x) {
    x = (x ^ ((x << 13) & 0xFFFFFFFF)) >>> 0;
    x = (x ^ (x >>> 17)) >>> 0;
    x = (x ^ ((x << 5) & 0xFFFFFFFF)) >>> 0;
    return x >>> 0;
  },

  /* Próxima apuração a sair. 'agora' deve ser um Date com os componentes UTC
     já ajustados para o horário do Rio (UTC-3, sem horário de verão). */
  proximaApuracao(agora) {
    const dow = agora.getUTCDay();
    const minutos = agora.getUTCHours() * 60 + agora.getUTCMinutes();
    const grade = this.GRADE_APURACOES[dow] || this.GRADE_APURACOES[0];
    for (const [sigla, min] of grade) {
      if (minutos < min) return this._regApuracao(sigla, min, agora, false);
    }
    const amanha = new Date(agora.getTime() + 24 * 3600 * 1000);
    const gradeAmanha = this.GRADE_APURACOES[amanha.getUTCDay()] || this.GRADE_APURACOES[0];
    const [sigla, min] = gradeAmanha[0];
    return this._regApuracao(sigla, min, amanha, true);
  },

  _regApuracao(sigla, minutos, data, amanha) {
    const hora = `${String(Math.floor(minutos / 60)).padStart(2, "0")}:${String(minutos % 60).padStart(2, "0")}`;
    const iso = `${data.getUTCFullYear()}-${String(data.getUTCMonth() + 1).padStart(2, "0")}-${String(data.getUTCDate()).padStart(2, "0")}`;
    const chave = `${iso}|${sigla}`;
    return {
      sigla,
      hora,
      data: iso,
      chave,
      rotulo: `${sigla} ${amanha ? "de amanhã" : "de hoje"} (${hora})`,
      nome: this.NOMES_LOTERIAS[sigla] || sigla,
    };
  },

  palpitePessoal(ano, mes, dia, agora) {
    const apuracao = this.proximaApuracao(agora);
    const semente =
      `${String(ano).padStart(4, "0")}-${String(mes).padStart(2, "0")}-${String(dia).padStart(2, "0")}|${apuracao.chave}`;
    let x = this.fnv1a32(semente);
    if (x === 0) x = 0x9E3779B9;
    x = this.xorshift32(x);
    const grupo = 1 + (x % 25);
    x = this.xorshift32(x);
    const idxDez = x % 4;
    x = this.xorshift32(x);
    const cenPre = x % 10;
    x = this.xorshift32(x);
    const milPre = x % 10;

    const base = (grupo - 1) * 4;
    const dezenas = Array.from({ length: 4 }, (_, i) =>
      String((base + i + 1) % 100).padStart(2, "0"));
    const dezena = dezenas[idxDez];
    const centena = String(cenPre * 100 + Number(dezena)).padStart(3, "0");
    const milhar = String(milPre * 1000 + Number(centena)).padStart(4, "0");
    const info = this.ANIMAIS[grupo] || ["?", ""];
    return {
      apuracao,
      grupo,
      animal: info[0],
      emoji: info[1],
      dezenas,
      dezena,
      centena,
      milhar,
      metodo: "FNV-1a 32 bits + xorshift32 (mesma fórmula do Palpitômetro do ojogodobicho.com)",
    };
  },
};
