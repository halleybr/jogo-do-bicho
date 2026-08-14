"use strict";

const $ = (sel) => document.querySelector(sel);

let DADOS = null;
let busca = "";

const el = {
  status: $("#status"),
  btnAtualizar: $("#btn-atualizar"),
  busca: $("#busca"),
  btnLimpar: $("#btn-limpar"),
  resumoBusca: $("#resumo-busca"),
  erro: $("#erro"),
  secaoHoje: $("#secao-hoje"),
  dataHoje: $("#data-hoje"),
  hoje: $("#hoje"),
  secaoHistorico: $("#secao-historico"),
  corpoHistorico: $("#tabela-historico tbody"),
  secaoBichos: $("#secao-bichos"),
  bichos: $("#bichos"),
  secaoPalpites: $("#secao-palpites"),
  palpites: $("#palpites"),
  palpitesRodape: $("#palpites-rodape"),
  secaoPessoal: $("#secao-pessoal"),
  nascimento: $("#nascimento"),
  pessoalResultado: $("#pessoal-resultado"),
  secaoArquivo: $("#secao-arquivo"),
  arquivoCobertura: $("#arquivo-cobertura"),
  buscaArquivo: $("#busca-arquivo"),
  arquivoStatus: $("#arquivo-status"),
  arquivoLista: $("#arquivo-lista"),
};

function normalizar(s) {
  return (s || "").toString().toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

/* ---------- busca ---------- */

function analisarBusca(q) {
  q = (q || "").trim();
  if (!q) return null;
  if (/^\d+$/.test(q)) {
    const grupo = parseInt(q, 10);
    return {
      tipo: "numero",
      q,
      grupo: grupo >= 1 && grupo <= 25 ? grupo : null,
      soSubstring: q.length >= 2,
    };
  }
  return { tipo: "animal", q: normalizar(q) };
}

function premioCombina(analise, premio) {
  if (analise.tipo === "animal") {
    return normalizar(premio.animal).includes(analise.q);
  }
  if (analise.soSubstring && premio.numero.includes(analise.q)) return true;
  if (analise.grupo !== null && premio.grupo === analise.grupo) return true;
  return false;
}

function marcar(texto, analise) {
  if (!analise) return texto;
  if (analise.tipo === "animal") return texto; // marca só no nome do bicho
  const idx = texto.indexOf(analise.q);
  if (analise.soSubstring && idx !== -1) {
    return texto.slice(0, idx) + "<mark>" + texto.slice(idx, idx + analise.q.length) + "</mark>" + texto.slice(idx + analise.q.length);
  }
  return texto;
}

/* ---------- render ---------- */

function tempoAtualizado(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function renderPremio(premio, analise) {
  const combina = !analise || premioCombina(analise, premio);
  const destaque = analise && analise.tipo === "animal" && normalizar(premio.animal).includes(analise.q);
  const nomeBicho = destaque
    ? `<span class="premio-bicho"><span class="emoji">${premio.emoji}</span> <mark>${premio.animal}</mark></span>`
    : `<span class="premio-bicho"><span class="emoji">${premio.emoji}</span> ${premio.animal}</span>`;
  return `
    <div class="premio ${premio.posicao === 1 ? "pos-1" : ""} ${combina ? "" : "apagado"}">
      <span class="premio-pos">${premio.posicao}º</span>
      <span class="premio-num">${marcar(premio.numero, analise)}</span>
      <span class="premio-bicho">${nomeBicho} <span class="premio-grupo">G${premio.grupo}</span></span>
    </div>`;
}

function renderCartao(loteria, analise) {
  const premios = loteria.premios.map((p) => renderPremio(p, analise)).join("");
  const centena = loteria.centena ? `
    <div class="centena-linha ${!analise || premioCombina(analise, loteria.centena) ? "" : "apagado"}">
      <span class="rotulo">Centena</span>
      <span class="premio-num">${marcar(loteria.centena.numero, analise)}</span>
      <span class="premio-bicho"><span class="emoji">${loteria.centena.emoji}</span> ${loteria.centena.animal}</span>
    </div>` : "";
  return `
    <article class="cartao">
      <header class="cartao-cab">
        <div class="cartao-titulo">
          <span class="cartao-codigo">${loteria.codigo}</span>
          <span class="cartao-nome">${loteria.nome}</span>
        </div>
        ${loteria.horario ? `<span class="cartao-horario">🕐 ${loteria.horario}</span>` : ""}
      </header>
      <div class="cartao-corpo">
        <div class="premios">${premios}</div>
        ${centena}
      </div>
    </article>`;
}

function renderHoje(analise) {
  if (!DADOS.hoje.length) {
    el.secaoHoje.hidden = true;
    return;
  }
  el.secaoHoje.hidden = false;
  el.dataHoje.textContent = DADOS.data ? DADOS.data.texto : "";
  let html = DADOS.hoje.map((l) => renderCartao(l, analise)).join("");
  if (analise && !DADOS.hoje.some((l) =>
    l.premios.some((p) => premioCombina(analise, p)) ||
    (l.centena && premioCombina(analise, l.centena)))) {
    html = `<div class="sem-resultado">Nenhum prêmio de hoje corresponde a <b>${escapeHtml(analise.q)}</b>.</div>`;
  }
  el.hoje.innerHTML = html;
}

function renderHistorico(analise) {
  if (!DADOS.historico.length) {
    el.secaoHistorico.hidden = true;
    return;
  }
  el.secaoHistorico.hidden = false;
  let linhas = DADOS.historico;
  if (analise) {
    linhas = linhas.filter((r) => r.premios.some((p) => premioCombina(analise, p)));
  }
  if (!linhas.length) {
    el.corpoHistorico.innerHTML =
      `<tr><td colspan="7" class="sem-resultado">Nenhum resultado dos últimos dias corresponde a <b>${escapeHtml(analise.q)}</b>.</td></tr>`;
    return;
  }
  el.corpoHistorico.innerHTML = linhas.map((r) => `
    <tr>
      <td class="data-cell">${r.data}</td>
      <td><span class="tipo">${r.loteria}</span> <span style="color:var(--texto-2);font-size:12px">${r.nome}</span></td>
      ${r.premios.map((p) => {
        const destaque = analise && analise.tipo === "animal" && normalizar(p.animal).includes(analise.q);
        return `<td><span class="num">${marcar(p.numero, analise)}</span>
          <span class="bicho-cell">${p.emoji} ${destaque ? `<mark>${p.animal}</mark>` : p.animal} G${p.grupo}</span></td>`;
      }).join("")}
    </tr>`).join("");
}

function renderBichos(analise) {
  el.secaoBichos.hidden = false;
  el.bichos.innerHTML = DADOS.animais.map((b) => {
    const destaque = analise && (
      (analise.tipo === "animal" && normalizar(b.animal).includes(analise.q)) ||
      (analise.tipo === "numero" && analise.grupo === b.grupo)
    );
    return `
      <button class="bicho ${destaque ? "bicho-destaque" : ""}" data-grupo="${b.grupo}" title="Buscar ${b.animal}">
        <span class="emoji">${b.emoji}</span>
        <span><span class="bicho-nome">${destaque ? `<mark>${b.animal}</mark>` : b.animal}</span><br>
        <span class="bicho-meta">G${b.grupo} · dezenas ${b.dezenas}</span></span>
      </button>`;
  }).join("");
  el.bichos.querySelectorAll(".bicho").forEach((btn) => {
    btn.addEventListener("click", () => {
      const animal = DADOS.animais.find((a) => a.grupo === Number(btn.dataset.grupo)).animal;
      el.busca.value = animal;
      aplicarBusca();
      el.busca.focus();
    });
  });
}

function renderResumo(analise) {
  if (!analise) { el.resumoBusca.hidden = true; return; }
  let total = 0;
  if (DADOS.hoje.length) total += DADOS.hoje.reduce((s, l) =>
    s + l.premios.filter((p) => premioCombina(analise, p)).length, 0);
  total += DADOS.historico.reduce((s, r) => s + r.premios.filter((p) => premioCombina(analise, p)).length, 0);
  const desc = analise.tipo === "animal" ? `bicho <b>${escapeHtml(analise.q)}</b>` : `número <b>${escapeHtml(analise.q)}</b>`;
  el.resumoBusca.innerHTML = `${total} prêmio(s) encontrado(s) para ${desc} (destaque em amarelo).`;
  el.resumoBusca.hidden = false;
}

function aplicarBusca() {
  const analise = analisarBusca(el.busca.value);
  busca = analise ? analise.q : "";
  el.btnLimpar.hidden = !analise;
  if (!DADOS) return;
  renderHoje(analise);
  renderHistorico(analise);
  renderBichos(analise);
  renderResumo(analise);
}

function escapeHtml(s) {
  return (s || "").toString().replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function mostrarErro(msg) {
  el.erro.textContent = msg;
  el.erro.hidden = false;
  el.status.textContent = "erro";
  el.status.className = "status erro";
}

/* ---------- palpites ---------- */

const ROTULO_ESTRATEGIA = {
  atrasado: "🕐 Bicho atrasado",
  quente: "🔥 Em alta (2 meses)",
  consistente: "📊 Consistente",
};

async function carregarPalpites() {
  try {
    const resp = await fetch("/api/palpites");
    const dados = await resp.json();
    if (!resp.ok) throw new Error(dados.erro || "HTTP " + resp.status);
    el.secaoPalpites.hidden = false;
    el.palpites.innerHTML = dados.palpites.map((p) => `
      <article class="palpite estr-${escapeHtml(p.estrategia)}">
        <div class="palpite-cab">
          <span class="palpite-emoji">${p.emoji}</span>
          <span>
            <span class="palpite-nome">${p.animal}</span><br>
            <span class="palpite-grupo">Grupo ${p.grupo} · dezenas ${p.dezenas.join(" ")}</span>
          </span>
        </div>
        <span class="estrategia">${ROTULO_ESTRATEGIA[p.estrategia] || p.estrategia}</span>
        <p class="palpite-motivo">${p.motivo}</p>
        <div class="dezenas-chip">${p.dezenas.map((d) => `<span class="dezena-chip">${d}</span>`).join("")}</div>
      </article>`).join("");
    const cob = dados.cobertura;
    const arq = cob.arquivo || {};
    const atrasados = (dados.estatisticas || [])
      .filter((s) => s.atraso_cabeca_dias !== null && s.total_cabeca >= 8)
      .sort((a, b) => b.atraso_cabeca_dias - a.atraso_cabeca_dias)
      .slice(0, 3)
      .map((s) => `${s.animal} (${s.atraso_cabeca_dias} dias)`)
      .join(", ");
    el.palpitesRodape.innerHTML =
      `<b>Base do palpite:</b> 1º prêmio (cabeça) dos últimos 2 meses ` +
      `(${cob.inicio} → ${cob.fim}): ${(cob.total_cabecas || 0).toLocaleString("pt-BR")} cabeças ` +
      `analisadas, sobre arquivo de ${arq.dias || cob.dias} dias ` +
      `(${arq.inicio || cob.inicio} → ${arq.fim || cob.fim}). ` +
      (atrasados ? `Mais atrasados na cabeça (1º prêmio): ${atrasados}. ` : "") +
      `O sorteio é aleatório — o palpite é estatístico e não garante resultado. Jogo do bicho não é regulamentado no Brasil.`;
    el.arquivoCobertura.textContent =
      `Cobrindo ${arq.inicio || cob.inicio} → ${arq.fim || cob.fim} ` +
      `(${arq.dias || cob.dias} dias, ${(arq.total_premios || 0).toLocaleString("pt-BR")} prêmios)` +
      (arq.atualizado_em ? ` · atualizado em ${new Date(arq.atualizado_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}` : "") +
      `.`;
  } catch (e) {
    el.secaoPalpites.hidden = false;
    el.palpites.innerHTML =
      `<div class="sem-resultado">Palpites indisponíveis: ${escapeHtml(e.message)}</div>`;
    el.palpitesRodape.textContent = "O histórico completo ainda está sendo baixado — tente de novo em alguns minutos.";
  }
}

/* ---------- palpite pessoal ---------- */

let seqPessoal = 0;

async function renderPessoal() {
  const v = el.nascimento.value;
  const minha = ++seqPessoal;
  if (!v) { el.pessoalResultado.innerHTML = ""; return; }
  const [ano, mes, dia] = v.split("-");
  el.pessoalResultado.innerHTML = `<div class="sem-resultado">Calculando…</div>`;
  try {
    const resp = await fetch(`/api/palpites?nascimento=${dia}/${mes}/${ano}`);
    const dados = await resp.json();
    if (minha !== seqPessoal) return; // resposta antiga — ignora
    if (!resp.ok) throw new Error(dados.erro || "HTTP " + resp.status);
    const p = dados.pessoal;
    if (!p || p.erro) throw new Error(p ? p.erro : "sem dados");
    el.pessoalResultado.innerHTML = `
      <div class="pessoal-card">
        <span class="pessoal-emoji">${p.emoji}</span>
        <div class="pessoal-info">
          <div class="pessoal-bicho">${p.animal} <span style="color:var(--texto-2);font-size:14px">· Grupo ${p.grupo}</span></div>
          <div class="pessoal-numeros">
            <span class="num-pill">Milhar ${p.milhar}</span>
            <span class="num-pill">Centena ${p.centena}</span>
            <span class="num-pill">Dezena ${p.dezena}</span>
          </div>
          <div class="pessoal-apuracao">Para a próxima apuração: <b>${p.apuracao.rotulo}</b> (${p.apuracao.nome})</div>
          <div class="pessoal-metodo">${p.metodo}</div>
        </div>
      </div>`;
  } catch (e) {
    if (minha !== seqPessoal) return;
    el.pessoalResultado.innerHTML = `<div class="sem-resultado">${escapeHtml(e.message)}</div>`;
  }
}

/* ---------- histórico completo ---------- */

function grupoDeAnimal(nome) {
  if (!DADOS || !DADOS.animais) return null;
  const alvo = normalizar(nome);
  const a = DADOS.animais.find((b) => normalizar(b.animal) === alvo);
  return a ? a.grupo : null;
}

async function carregarArquivo() {
  const q = el.buscaArquivo.value.trim();
  if (!q) {
    el.arquivoStatus.hidden = true;
    el.arquivoLista.innerHTML = "";
    return;
  }
  const analise = analisarBusca(q);
  if (!analise) {
    el.arquivoStatus.hidden = true;
    el.arquivoLista.innerHTML = "";
    return;
  }
  let url = "/api/historico?limite=200";
  if (analise.tipo === "animal") {
    const g = grupoDeAnimal(analise.q);
    if (!g) {
      el.arquivoStatus.hidden = false;
      el.arquivoStatus.innerHTML = `Bicho <b>${escapeHtml(analise.q)}</b> não encontrado.`;
      el.arquivoLista.innerHTML = "";
      return;
    }
    url += `&grupo=${g}`;
  } else {
    url += `&numero=${encodeURIComponent(analise.q)}`;
    if (analise.grupo !== null) url += `&grupo=${analise.grupo}`;
  }
  try {
    const resp = await fetch(url);
    const dados = await resp.json();
    if (!resp.ok) throw new Error(dados.erro || "HTTP " + resp.status);
    const itens = dados.resultados || [];
    el.arquivoStatus.hidden = false;
    el.arquivoStatus.innerHTML = itens.length
      ? `${itens.length} resultado(s) no histórico completo ${dados.truncado ? "(mostrando os primeiros 200)" : ""} para <b>${escapeHtml(q)}</b>.`
      : `Nenhum resultado para <b>${escapeHtml(q)}</b> no histórico completo.`;
    el.arquivoLista.innerHTML = itens.map((r) => `
      <div class="arquivo-item">
        <span class="data"><a href="/diario.html?data=${r.data}" title="Ver o dia completo">${r.data.split("-").reverse().join("/")}</a></span>
        <span class="tipo">${r.loteria}</span>
        <span class="pos">${r.posicao}º</span>
        <span><span class="num">${escapeHtml(r.numero)}</span> <span class="bicho">${r.emoji} ${r.animal} · G${r.grupo}</span></span>
      </div>`).join("");
  } catch (e) {
    el.arquivoStatus.hidden = false;
    el.arquivoStatus.innerHTML = `Erro na busca: ${escapeHtml(e.message)}`;
  }
}

async function carregar(forcar = false) {
  el.btnAtualizar.disabled = true;
  try {
    const resp = await fetch("/api/resultados" + (forcar ? "?forcar=1" : ""));
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const dados = await resp.json();
    if (dados.erro) throw new Error(dados.erro);
    DADOS = dados;
    el.erro.hidden = true;
    if (dados.aviso) {
      el.status.textContent = "⚠ " + dados.aviso;
      el.status.className = "status erro";
    } else {
      el.status.textContent = "✓ atualizado às " + tempoAtualizado(dados.raspado_em);
      el.status.className = "status ok";
    }
    aplicarBusca();
  } catch (e) {
    mostrarErro("Não foi possível carregar os resultados: " + e.message);
  } finally {
    el.btnAtualizar.disabled = false;
  }
}

/* ---------- eventos ---------- */

let debounceTimer;
el.busca.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(aplicarBusca, 120);
});
el.busca.addEventListener("keydown", (e) => {
  if (e.key === "Enter") aplicarBusca();
});
el.btnLimpar.addEventListener("click", () => {
  el.busca.value = "";
  aplicarBusca();
  el.busca.focus();
});
el.btnAtualizar.addEventListener("click", () => carregar(true));

let debouncePessoal;
el.nascimento.addEventListener("input", () => {
  clearTimeout(debouncePessoal);
  debouncePessoal = setTimeout(renderPessoal, 180);
});
el.nascimento.addEventListener("change", renderPessoal);

let debounceArquivo;
el.buscaArquivo.addEventListener("input", () => {
  clearTimeout(debounceArquivo);
  debounceArquivo = setTimeout(carregarArquivo, 200);
});
el.buscaArquivo.addEventListener("keydown", (e) => {
  if (e.key === "Enter") carregarArquivo();
});

async function iniciar() {
  await carregar(false);
  el.secaoPessoal.hidden = false;
  el.secaoArquivo.hidden = false;
  carregarPalpites();
}

iniciar();
setInterval(() => carregar(false), 5 * 60 * 1000);
setInterval(carregarPalpites, 10 * 60 * 1000);
