#!/usr/bin/env python3
"""
Jogo do Bicho RJ — servidor de resultados.

Raspa a página "Deu no Poste" (www.ojogodobicho.com/deu_no_poste.htm), que publica
a apuração do Rio de Janeiro, e expõe:
  * GET /api/resultados  -> JSON estruturado (resultados de hoje + histórico)
  * GET /                -> site estático (public/)

Sem dependências externas: apenas a biblioteca padrão do Python.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import palpites

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FONTE_URL = "https://www.ojogodobicho.com/deu_no_poste.htm"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}
CACHE_TTL = 90          # segundos entre uma raspagem e outra


def _porta_do_ambiente():
    """Lê a variável PORT quando a plataforma injeta (Render, Railway etc.)."""
    try:
        p = int(os.environ.get("PORT", ""))
        if 1 <= p <= 65535:
            return p
    except (TypeError, ValueError):
        pass
    return None


_porta_env = _porta_do_ambiente()
PORTA = _porta_env if _porta_env else 8000
# Em plataforma (PORT injetada) escuta em todas as interfaces; localmente,
# só em localhost — funciona mesmo sem HOST configurada no painel.
HOST = os.environ.get("HOST", "0.0.0.0" if _porta_env else "127.0.0.1")
PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_PUBLIC = os.path.join(PASTA_BASE, "public")

# ---------------------------------------------------------------- atualização automática
#
# O histórico (dados/historico.json) é incremental: no início o servidor baixa
# os dias que faltam e, depois, roda uma atualização por dia às 23:30 (horário
# de Brasília, após a última apuração do dia, a Coruja das 21:30).

HORA_ATUALIZACAO_HORA, HORA_ATUALIZACAO_MIN = 23, 30


def _rodar_historico(rotulo: str):
    """Executa historico.py (incremental) e invalida o cache de palpites."""
    try:
        res = subprocess.run(
            [sys.executable, "historico.py"], cwd=PASTA_BASE,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60 * 30)
        saida = (res.stdout or "").strip().splitlines()
        ultima = saida[-1] if saida else ""
        if res.returncode != 0 and not ultima:
            ultima = (res.stderr or "").strip()[-300:]
        CACHE_PALPITES.invalidar()
        print(f"[historico] {rotulo}: {ultima}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[historico] {rotulo}: erro: {exc}", flush=True)


def _segundos_ate_proxima_meia_noite_rio() -> float:
    agora = datetime.now(palpites.FUSO_RIO)
    alvo = agora.replace(hour=HORA_ATUALIZACAO_HORA,
                         minute=HORA_ATUALIZACAO_MIN, second=0, microsecond=0)
    if agora >= alvo:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


def _rotina_historico_diario():
    """Thread: catch-up na inicialização + atualização diária automática."""
    _rodar_historico("verificação inicial (dias novos)")
    while True:
        try:
            time.sleep(_segundos_ate_proxima_meia_noite_rio())
        except Exception:  # noqa: BLE001
            time.sleep(3600)
        _rodar_historico("atualização diária automática")

MESES_PT = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4,
    "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8,
    "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12,
}

# grupo, animal, emoji, dezenas
ANIMAIS = [
    (1, "Avestruz", "🐦", "01 a 04"),
    (2, "Águia", "🦅", "05 a 08"),
    (3, "Burro", "🐴", "09 a 12"),
    (4, "Borboleta", "🦋", "13 a 16"),
    (5, "Cachorro", "🐕", "17 a 20"),
    (6, "Cabra", "🐐", "21 a 24"),
    (7, "Carneiro", "🐑", "25 a 28"),
    (8, "Camelo", "🐫", "29 a 32"),
    (9, "Cobra", "🐍", "33 a 36"),
    (10, "Coelho", "🐇", "37 a 40"),
    (11, "Cavalo", "🐎", "41 a 44"),
    (12, "Elefante", "🐘", "45 a 48"),
    (13, "Galo", "🐓", "49 a 52"),
    (14, "Gato", "🐈", "53 a 56"),
    (15, "Jacaré", "🐊", "57 a 60"),
    (16, "Leão", "🦁", "61 a 64"),
    (17, "Macaco", "🐒", "65 a 68"),
    (18, "Porco", "🐷", "69 a 72"),
    (19, "Pavão", "🦚", "73 a 76"),
    (20, "Peru", "🦃", "77 a 80"),
    (21, "Touro", "🐂", "81 a 84"),
    (22, "Tigre", "🐅", "85 a 88"),
    (23, "Urso", "🐻", "89 a 92"),
    (24, "Veado", "🦌", "93 a 96"),
    (25, "Vaca", "🐄", "97 a 00"),
]
ANIMAL_POR_GRUPO = {g: {"animal": a, "emoji": e} for g, a, e, _ in ANIMAIS}

LOTERIAS = {
    "PPT": {"nome": "Para Todos", "horario": "09:30"},
    "PTM": {"nome": "PT Manhã", "horario": "11:30"},
    "PT": {"nome": "PT Tarde", "horario": "14:30"},
    "PTV": {"nome": "PT Vespera", "horario": "16:30"},
    "PTN": {"nome": "PT Noite", "horario": "18:30"},
    "FED": {"nome": "Federal", "horario": "19:00"},
    "COR": {"nome": "Coruja", "horario": "21:30"},
}


def minutos_loteria(codigo: str) -> int:
    """Horário da apuração em minutos desde a meia-noite (para ordenar do
    último resultado para o primeiro)."""
    h = LOTERIAS.get(codigo, {}).get("horario", "")
    try:
        hh, mm = h.split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return 0


def grupo_de_dezena(dezena: int) -> int:
    """Dezena (00-99) -> grupo (1-25). Ex.: 17 -> 5 (Cachorro), 00 -> 25 (Vaca)."""
    if dezena == 0:
        return 25
    return (dezena - 1) // 4 + 1


def detalhes_milhar(numero: str):
    """'6465' -> dict com centena, dezena, grupo, animal e emoji."""
    numero = numero.strip()
    dezena = int(numero[-2:])
    grupo = grupo_de_dezena(dezena)
    info = ANIMAL_POR_GRUPO[grupo]
    return {
        "numero": numero,
        "centena": numero[-3:],
        "dezena": f"{dezena:02d}",
        "grupo": grupo,
        "animal": info["animal"],
        "emoji": info["emoji"],
    }


def baixar_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read()
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


class TabelaParser(HTMLParser):
    """Extrai todas as <table> da página (caption, cabeçalho e células)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tabelas = []
        self._tabela = None
        self._em_caption = False
        self._no_thead = False
        self._linha = None
        self._celula = None

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "table":
            self._tabela = {"caption": "", "header": [], "linhas": []}
            self.tabelas.append(self._tabela)
        elif tag == "caption":
            self._em_caption = True
        elif tag == "thead":
            self._no_thead = True
        elif tag == "tbody":
            self._no_thead = False
        elif tag == "tr":
            self._linha = []
        elif tag in ("td", "th") and self._linha is not None:
            self._celula = {"texto": "", "classe": d.get("class", "")}
            self._linha.append(self._celula)

    def handle_endtag(self, tag):
        if tag == "caption":
            self._em_caption = False
        elif tag == "table":
            self._tabela = None
        elif tag == "tr" and self._linha is not None and self._tabela is not None:
            if self._no_thead:
                self._tabela["header"] = [c["texto"].strip() for c in self._linha]
            else:
                self._tabela["linhas"].append([c for c in self._linha])
            self._linha = None
        elif tag in ("td", "th"):
            self._celula = None

    def handle_data(self, data):
        if self._em_caption and self._tabela is not None:
            self._tabela["caption"] += data
        elif self._celula is not None:
            self._celula["texto"] += data


_RE_CAPTION_HOJE = re.compile(
    r"^\s*(?:Segunda|Terça|Quarta|Quinta|Sexta)-Feira|^\s*(?:Sábado|Domingo)"
)
_RE_DATA_CAPTION = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})")
_RE_CELULA_HOJE = re.compile(r"^\s*(\d{3,4})\s*-\s*(\d{1,2})\s*$")


def parsear_data_caption(texto: str):
    m = _RE_DATA_CAPTION.search(texto)
    if not m:
        return None
    dia, mes_nome, ano = int(m.group(1)), m.group(2), int(m.group(3))
    mes = MESES_PT.get(mes_nome)
    if not mes:
        return None
    return {"texto": texto.strip(), "dia": dia, "mes": mes, "ano": ano,
            "iso": f"{ano:04d}-{mes:02d}-{dia:02d}"}


def raspar() -> dict:
    """Baixa a página e devolve o dicionário completo de resultados."""
    html = baixar_html(FONTE_URL)
    parser = TabelaParser()
    parser.feed(html)

    hoje = []
    historico = []
    data = None

    for tab in parser.tabelas:
        caption = tab["caption"].strip()
        if not caption:
            continue

        if _RE_CAPTION_HOJE.match(caption) and tab["header"]:
            data = parsear_data_caption(caption)
            codigos = [h.strip() for h in tab["header"] if h.strip()]
            # a primeira célula do cabeçalho é apenas o rótulo da coluna de posição
            if codigos and codigos[0] not in LOTERIAS:
                codigos = codigos[1:]
            por_coluna = {i: [] for i in range(len(codigos))}
            for linha in tab["linhas"]:
                celulas = [c["texto"].strip() for c in linha]
                if not celulas:
                    continue
                for i, texto in enumerate(celulas[1:]):
                    if i not in por_coluna or not texto:
                        continue
                    por_coluna[i].append(texto)
            for i, codigo in enumerate(codigos):
                info = LOTERIAS.get(codigo, {"nome": codigo, "horario": ""})
                premios = []
                centena = None
                for j, texto in enumerate(por_coluna[i]):
                    m = _RE_CELULA_HOJE.match(texto)
                    if not m:
                        continue
                    numero, grupo_str = m.group(1), int(m.group(2))
                    if not (1 <= grupo_str <= 25):
                        continue
                    if len(numero) == 4:
                        det = detalhes_milhar(numero)
                        premios.append({"posicao": j + 1, "milhar": numero, **det})
                    elif len(numero) == 3:
                        det = detalhes_milhar("0" + numero)  # dezena usa os 2 últimos
                        centena = {**det, "numero": numero}
                if premios or centena:
                    hoje.append({
                        "codigo": codigo,
                        "nome": info["nome"],
                        "horario": info["horario"],
                        "premios": premios,
                        "centena": centena,
                    })
        elif caption.lower() == "resultados anteriores":
            for linha in tab["linhas"]:
                celulas = [c["texto"].strip() for c in linha]
                if len(celulas) < 7:
                    continue
                data_cel, tipo = celulas[0], celulas[1]
                numeros = celulas[2:7]
                if not re.fullmatch(r"\d{1,2}/\d{1,2}", data_cel) or not re.fullmatch(r"[A-Z]{2,4}", tipo):
                    continue
                premios = [detalhes_milhar(n) for n in numeros if re.fullmatch(r"\d{4}", n)]
                if len(premios) != 5:
                    continue
                d, m = data_cel.split("/")
                historico.append({
                    "data": data_cel,
                    "dia": int(d),
                    "mes": int(m),
                    "loteria": tipo,
                    "nome": LOTERIAS.get(tipo, {"nome": tipo})["nome"],
                    "premios": premios,
                })

    # Ordena sempre do último resultado para o primeiro: data mais recente
    # primeiro e, dentro do dia, a apuração mais tardia primeiro.
    hoje.sort(key=lambda l: minutos_loteria(l["codigo"]), reverse=True)
    historico.sort(
        key=lambda r: (r["mes"], r["dia"], minutos_loteria(r["loteria"])),
        reverse=True)

    return {
        "fonte": FONTE_URL,
        "raspado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "data": data,
        "hoje": hoje,
        "historico": historico,
        "animais": [
            {"grupo": g, "animal": a, "emoji": e, "dezenas": dz}
            for g, a, e, dz in ANIMAIS
        ],
    }


class CacheResultados:
    def __init__(self):
        self._lock = threading.Lock()
        self._payload = None
        self._quando = 0.0
        self._erro = None

    def obter(self, forcar=False):
        with self._lock:
            idade = time.time() - self._quando
            if self._payload is not None and not forcar and idade < CACHE_TTL:
                return self._payload, self._erro, False
        try:
            payload = raspar()
        except Exception as exc:  # noqa: BLE001 — mantém o último dado bom
            with self._lock:
                if self._payload is not None:
                    return self._payload, f"falha ao atualizar: {exc}", True
                raise
        with self._lock:
            self._payload = payload
            self._quando = time.time()
            self._erro = None
        return payload, None, False


CACHE = CacheResultados()


class CachePalpites:
    """Resultado do motor de palpites, recalculado quando o histórico muda."""

    def __init__(self):
        self._lock = threading.Lock()
        self._payload = None
        self._quando = 0.0

    def obter(self):
        with self._lock:
            if self._payload is not None and time.time() - self._quando < 600:
                return self._payload
        dias = palpites.carregar_dias()
        if not dias:
            raise RuntimeError("histórico ainda não foi baixado (rode: python historico.py)")
        payload = palpites.gerar_palpites(dias, date.today())
        payload["cobertura"]["arquivo"]["atualizado_em"] = palpites.atualizado_em()
        payload["pessoal"] = None
        with self._lock:
            self._payload = payload
            self._quando = time.time()
        return payload

    def invalidar(self):
        """Força o próximo obter() a recalcular (usado após atualizar o histórico)."""
        with self._lock:
            self._quando = 0.0


CACHE_PALPITES = CachePalpites()


def consultar_diario(data_str):
    """Resultados de um dia específico do arquivo (2021→hoje) + navegação."""
    try:
        data_alvo = date.fromisoformat(data_str)
    except ValueError:
        raise ValueError("data inválida (use AAAA-MM-DD)")
    dias = palpites.carregar_dias()
    if not dias:
        raise RuntimeError("histórico ainda não foi baixado (rode: python historico.py)")
    chaves = [d["data"] for d in dias]
    inicio, fim = chaves[0], chaves[-1]
    if data_alvo < date.fromisoformat(inicio) or data_alvo > date.fromisoformat(fim):
        raise ValueError(f"fora do arquivo disponível ({inicio} → {fim})")

    loterias = []
    if data_str in chaves:
        dia = dias[chaves.index(data_str)]
        for lot in dia["loterias"]:
            premios = []
            for p in lot["premios"]:
                info = palpites.ANIMAIS.get(p["grupo"], (p.get("animal", "?"), ""))
                premios.append({
                    "posicao": p["posicao"],
                    "numero": p["numero"],
                    "grupo": p["grupo"],
                    "animal": info[0],
                    "emoji": info[1],
                })
            loterias.append({
                "codigo": lot["codigo"],
                "nome": palpites.NOMES_LOTERIAS.get(lot["codigo"], lot["codigo"]),
                "horario": LOTERIAS.get(lot["codigo"], {}).get("horario", ""),
                "premios": premios,
            })
    # último resultado primeiro (apuração mais tardia no topo)
    loterias.sort(key=lambda l: minutos_loteria(l["codigo"]), reverse=True)

    idx = chaves.index(data_str) if data_str in chaves else None
    if idx is not None:
        anterior = chaves[idx - 1] if idx > 0 else None
        proximo = chaves[idx + 1] if idx < len(chaves) - 1 else None
    else:
        # buraco no arquivo: vizinhos mais próximos com dados
        anterior = next((ch for ch in reversed(chaves) if ch < data_str), None)
        proximo = next((ch for ch in chaves if ch > data_str), None)
    return {
        "data": data_str,
        "tem_dados": bool(loterias),
        "loterias": loterias,
        "anterior": anterior,
        "proximo": proximo,
        "inicio": inicio,
        "fim": fim,
    }


def consultar_historico(params):
    """Busca no histórico completo (2021→hoje) por grupo, número, intervalo de datas."""
    dias = palpites.carregar_dias()
    de = params.get("de")
    ate = params.get("ate")
    grupo = params.get("grupo")
    numero = params.get("numero", "").strip()
    loteria = params.get("loteria", "").strip().upper()
    limite = 100
    try:
        limite = int(params.get("limite", "100"))
    except ValueError:
        pass
    limite = max(1, min(limite, 500))

    resultados = []
    for dia in dias:
        if de and dia["data"] < de:
            continue
        if ate and dia["data"] > ate:
            continue
        for lot in dia["loterias"]:
            if loteria and lot["codigo"] != loteria:
                continue
            for p in lot["premios"]:
                if grupo:
                    try:
                        if int(grupo) != p["grupo"]:
                            continue
                    except ValueError:
                        pass
                if numero and numero not in p["numero"]:
                    continue
                nome, emoji = palpites.ANIMAIS.get(p["grupo"], (p.get("animal"), ""))
                resultados.append({
                    "data": dia["data"],
                    "loteria": lot["codigo"],
                    "nome_loteria": palpites.NOMES_LOTERIAS.get(lot["codigo"], lot["codigo"]),
                    "posicao": p["posicao"],
                    "numero": p["numero"],
                    "grupo": p["grupo"],
                    "animal": nome,
                    "emoji": emoji,
                })
                if len(resultados) >= 5000:
                    break
            if len(resultados) >= 5000:
                break
        if len(resultados) >= 5000:
            break
    # último resultado primeiro: data mais recente e, no mesmo dia, a apuração
    # mais tardia primeiro (posições do mesmo sorteio permanecem 1º→5º)
    resultados.sort(
        key=lambda r: (r["data"], minutos_loteria(r["loteria"])),
        reverse=True)
    truncado = len(resultados) > limite
    return {"total": None if truncado else len(resultados),
            "resultados": resultados[:limite], "truncado": truncado}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "JogoDoBichoRJ/1.0"

    def _enviar(self, codigo, corpo: bytes, ctype: str, extra=None):
        self.send_response(codigo)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        caminho = self.path.split("?", 1)[0]
        if caminho == "/api/resultados":
            forcar = self.path.split("?", 1)[-1] == "forcar=1"
            try:
                payload, erro, stale = CACHE.obter(forcar=forcar)
            except Exception as exc:  # noqa: BLE001
                corpo = json.dumps({"erro": f"não foi possível buscar os resultados: {exc}"},
                                   ensure_ascii=False).encode("utf-8")
                self._enviar(502, corpo, "application/json; charset=utf-8")
                return
            if erro:
                payload["aviso"] = erro
            corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            extra = {"X-Stale": "1"} if stale else None
            self._enviar(200, corpo, "application/json; charset=utf-8", extra)
            return

        if caminho == "/api/palpites":
            try:
                payload = CACHE_PALPITES.obter()
            except Exception as exc:  # noqa: BLE001
                corpo = json.dumps({"erro": str(exc)},
                                   ensure_ascii=False).encode("utf-8")
                self._enviar(503, corpo, "application/json; charset=utf-8")
                return
            nasc = self.path.split("?", 1)[-1]
            if nasc.startswith("nascimento="):
                try:
                    dia, mes, ano = [int(x) for x in nasc.split("=", 1)[1].split("/")]
                    if not (1900 <= ano <= 2100):
                        raise ValueError("ano fora do intervalo")
                    payload["pessoal"] = palpites.palpite_pessoal(
                        date(ano, mes, dia), palpites.agora_rio())
                except (ValueError, IndexError):
                    payload["pessoal"] = {"erro": "data inválida (use DD/MM/AAAA entre 1900 e 2100)"}
            corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._enviar(200, corpo, "application/json; charset=utf-8")
            return

        if caminho == "/api/historico":
            import urllib.parse
            params = {k: v[0] for k, v in urllib.parse.parse_qs(self.path.split("?", 1)[-1]).items()}
            corpo = json.dumps(consultar_historico(params), ensure_ascii=False).encode("utf-8")
            self._enviar(200, corpo, "application/json; charset=utf-8")
            return

        if caminho == "/api/diario":
            import urllib.parse
            params = {k: v[0] for k, v in urllib.parse.parse_qs(self.path.split("?", 1)[-1]).items()}
            data_str = params.get("data", "").strip()
            if not data_str:  # sem data → último dia do arquivo
                dias = palpites.carregar_dias()
                if not dias:
                    data_str = ""
                else:
                    data_str = dias[-1]["data"]
            try:
                corpo = json.dumps(consultar_diario(data_str), ensure_ascii=False).encode("utf-8")
                self._enviar(200, corpo, "application/json; charset=utf-8")
            except (ValueError, RuntimeError) as exc:
                corpo = json.dumps({"erro": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._enviar(400 if isinstance(exc, ValueError) else 503, corpo, "application/json; charset=utf-8")
            return

        if caminho == "/":
            caminho = "/index.html"
        caminho = caminho.lstrip("/")
        arquivo = os.path.normpath(os.path.join(PASTA_PUBLIC, caminho))
        if not arquivo.startswith(PASTA_PUBLIC) or not os.path.isfile(arquivo):
            self._enviar(404, b"nao encontrado", "text/plain; charset=utf-8")
            return
        ext = os.path.splitext(arquivo)[1].lower()
        with open(arquivo, "rb") as f:
            corpo = f.read()
        self._enviar(200, corpo, MIME.get(ext, "application/octet-stream"))

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    porta = PORTA
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        porta = int(sys.argv[1])
    # atualização diária automática do histórico em segundo plano
    threading.Thread(target=_rotina_historico_diario,
                     name="historico-diario", daemon=True).start()
    servidor = ThreadingHTTPServer((HOST, porta), Handler)
    print(f"Jogo do Bicho RJ rodando em http://{HOST}:{porta}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando.")
        servidor.shutdown()


if __name__ == "__main__":
    main()
