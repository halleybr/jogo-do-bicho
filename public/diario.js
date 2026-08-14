/* Resultados diários — carrega /api/diario, navega dia a dia e busca no dia. */
"use strict";

const el = {
  data: document.getElementById("data"),
  btnAnterior: document.getElementById("btn-anterior"),
  btnHoje: document.getElementById("btn-hoje"),
  btnProximo: document.getElementById("btn-proximo"),
  busca: document.getElementById("busca-dia"),
  resumo: document.getElementById("resumo-dia"),
  erro: document.getElementById("erro"),
  titulo: document.getElementById("dia-titulo"),
  sub: document.getElementById("dia-sub"),
  grades: document.getElementById("dia-grades"),
  semDados: document.getElementById("sem-dados"),
};

let estado = null; // resposta atual de /api/diario
let analise = null; // busca atual

function escapeHtml(t) {
  return String(t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function normalizar(s) {
  return String(s).toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function formatarData(iso) {
  if (!iso) return "";
  const [a, m, d] = iso.split("-").map(Number);
  const dt = new Date(a, m - 1, d);
  const cap = dt.toLocaleDateString("pt-BR", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  return cap.charAt(0).toUpperCase() + cap.slice(1);
}

function formatarCurta(iso) {
  if (!iso) return "";
  return iso.split("-").reverse().join("/");
}

function analisarBusca(q) {
  q = q.trim();
  if (!q) return null;
  const n = normalizar(q);
  const soDigitos = n.replace(/\D/g, "");
  if (/^\d+$/.test(n) && soDigitos.length >= 2) {
    const g = Number(soDigitos);
    return { tipo: "numero", q: soDigitos, grupo: g >= 1 && g <= 25 ? g : null };
  }
  return { tipo: "animal", q: n };
}

function premioCombina(a, p) {
  if (!a) return true;
  if (a.tipo === "numero") {
    if (p.numero.includes(a.q)) return true;
    return a.grupo !== null && p.grupo === a.grupo;
  }
  return normalizar(p.animal).includes(a.q);
}

function renderPremio(p) {
  const combina = premioCombina(analise, p);
  const destaque = analise && analise.tipo === "animal" && normalizar(p.animal).includes(analise.q);
  const nomeBicho = destaque
    ? `<span class="premio-bicho"><span class="emoji">${p.emoji}</span> <mark>${p.animal}</mark></span>`
    : `<span class="premio-bicho"><span class="emoji">${p.emoji}</span> ${p.animal}</span>`;
  return `
    <div class="premio ${p.posicao === 1 ? "pos-1" : ""} ${combina ? "" : "apagado"}">
      <span class="premio-pos">${p.posicao}º</span>
      <span class="premio-num">${escapeHtml(p.numero)}</span>
      ${nomeBicho} <span class="premio-grupo">G${p.grupo}</span>
    </div>`;
}

function renderLoterias(loterias) {
  if (!loterias.length) return "";
  return loterias.map((l) => {
    const premios = l.premios.map(renderPremio).join("");
    return `
      <article class="cartao">
        <header class="cartao-cab">
          <div class="cartao-titulo">
            <span class="cartao-codigo">${escapeHtml(l.codigo)}</span>
            <span class="cartao-nome">${escapeHtml(l.nome)}</span>
          </div>
          ${l.horario ? `<span class="cartao-horario">🕐 ${l.horario}</span>` : ""}
        </header>
        <div class="cartao-corpo">
          <div class="premios">${premios}</div>
        </div>
      </article>`;
  }).join("");
}

function aplicarBusca() {
  const dados = estado || {};
  const loterias = dados.loterias || [];
  if (!loterias.length) return;
  const lista = loterias
    .map((l) => ({ l, premios: l.premios.filter((p) => premioCombina(analise, p)) }))
    .filter((x) => x.premios.length);
  el.grades.innerHTML = lista.map((x) => renderLoterias([{ ...x.l, premios: x.premios }])).join("");
  el.resumo.hidden = false;
  const total = lista.reduce((s, x) => s + x.premios.length, 0);
  el.resumo.innerHTML = analise
    ? `${total} prêmio(s) encontrado(s) em ${lista.length} apuração(ões) para <b>${escapeHtml(analise.q)}</b> no dia ${formatarCurta(dados.data)}.`
    : `${loterias.length} apurações em ${formatarCurta(dados.data)}.`;
}

function semDados(dados, erroFora) {
  el.grades.innerHTML = "";
  el.semDados.hidden = false;
  if (erroFora && dados) {
    el.semDados.innerHTML =
      `<b>Sem resultados para ${formatarCurta(dados.data)}</b> — o arquivo cobre de ${formatarCurta(dados.inicio)} a ${formatarCurta(dados.fim)}.` +
      `<br><br><button id="ir-ultimo" class="btn">Ver o último dia disponível (${formatarCurta(dados.fim)})</button>`;
  } else {
    let nav = "";
    if (dados.anterior && dados.proximo) {
      nav = `<br><br><button id="ir-ant" class="btn">◀ ${formatarCurta(dados.anterior)}</button> <button id="ir-prox" class="btn">${formatarCurta(dados.proximo)} ▶</button>`;
    }
    el.semDados.innerHTML =
      `<b>Sem resultados para este dia</b> — não há apurações registradas nessa data no arquivo.` + nav;
  }
  const ir = document.getElementById("ir-ultimo");
  if (ir) ir.addEventListener("click", () => carregarDia(dados.fim));
  const ant = document.getElementById("ir-ant");
  if (ant) ant.addEventListener("click", () => carregarDia(dados.anterior));
  const prox = document.getElementById("ir-prox");
  if (prox) prox.addEventListener("click", () => carregarDia(dados.proximo));
}

function mostrarErro(msg) {
  el.erro.hidden = false;
  el.erro.textContent = msg;
}

let seqDia = 0;

async function carregarDia(data) {
  const meu = ++seqDia;
  const url = data ? `/api/diario?data=${encodeURIComponent(data)}` : "/api/diario";
  el.erro.hidden = true;
  el.grades.innerHTML = "";
  el.titulo.textContent = "Carregando…";
  try {
    const resp = await fetch(url);
    const dados = await resp.json();
    if (!resp.ok) throw new Error(dados.erro || "HTTP " + resp.status);
    if (meu !== seqDia) return; // resposta antiga
    estado = dados;
    el.data.value = dados.data;
    el.btnAnterior.disabled = !dados.anterior;
    el.btnProximo.disabled = !dados.proximo;
    el.titulo.innerHTML = `📅 <b>${formatarData(dados.data)}</b>`;
    el.sub.textContent = `Arquivo: ${formatarCurta(dados.inicio)} → ${formatarCurta(dados.fim)}`;
    if (dados.tem_dados) {
      el.semDados.hidden = true;
      aplicarBusca();
    } else {
      semDados(dados, false);
    }
  } catch (e) {
    if (e.message.includes("fora do arquivo") && estado) {
      mostrarErro(e.message);
      semDados({ data, inicio: estado.inicio, fim: estado.fim }, true);
    } else {
      mostrarErro("Não foi possível carregar o dia: " + e.message);
    }
  }
}

el.data.addEventListener("change", () => carregarDia(el.data.value));
el.btnAnterior.addEventListener("click", () => { if (estado && estado.anterior) carregarDia(estado.anterior); });
el.btnProximo.addEventListener("click", () => { if (estado && estado.proximo) carregarDia(estado.proximo); });
el.btnHoje.addEventListener("click", () => {
  const hoje = new Date();
  const iso = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}-${String(hoje.getDate()).padStart(2, "0")}`;
  carregarDia(iso);
});

let tBusca = null;
el.busca.addEventListener("input", () => {
  clearTimeout(tBusca);
  tBusca = setTimeout(() => {
    analise = analisarBusca(el.busca.value);
    if (estado && estado.tem_dados) aplicarBusca();
  }, 120);
});

// data vinda da URL (?data=AAAA-MM-DD) ou último dia disponível
const q = new URLSearchParams(location.search).get("data");
carregarDia(q);
