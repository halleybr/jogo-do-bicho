#!/usr/bin/env python3
"""
Histórico completo do Jogo do Bicho RJ (2021 → hoje).

Baixa as páginas diárias de https://resultadojogobicho.com/RJ/dia/YYYY-MM-DD
(arquivo gratuito mais antigo disponível: 2021-01-02), converte para JSON e
persiste em dados/historico.json de forma incremental (retomável).

Uso:
  python historico.py            # baixa o que falta (incremental)
  python historico.py --status   # mostra cobertura atual
  python historico.py --teste    # baixa só 1 dia e imprime o JSON
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASTA_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
ARQUIVO = os.path.join(PASTA_DADOS, "historico.json")
FONTE = "https://resultadojogobicho.com/RJ/dia/{data}"
INICIO = date(2021, 1, 2)
ATRASO_ENTRE_REQUISICOES = 0.12  # segundos, para não sobrecarregar a fonte

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_ANIMAIS = {
    1: "Avestruz", 2: "Águia", 3: "Burro", 4: "Borboleta", 5: "Cachorro",
    6: "Cabra", 7: "Carneiro", 8: "Camelo", 9: "Cobra", 10: "Coelho",
    11: "Cavalo", 12: "Elefante", 13: "Galo", 14: "Gato", 15: "Jacaré",
    16: "Leão", 17: "Macaco", 18: "Porco", 19: "Pavão", 20: "Peru",
    21: "Touro", 22: "Tigre", 23: "Urso", 24: "Veado", 25: "Vaca",
}
_CODIGOS = {
    "CORUJA": "COR", "PARA TODOS": "PPT", "FEDERAL": "FED",
    "PTT": "PTV", "PTT16HS": "PTV", "PTVESPERA": "PTV",
    "PTTARDE": "PT", "PTN": "PTN", "PTM": "PTM",
}

# Grade de apurações por dia da semana (minutos desde a meia-noite), usada
# para mapear o horário do bloco quando o código não vem no cabeçalho.
# 0 = domingo … 6 = sábado (mesma grade do Palpitômetro do ojogodobicho.com).
_GRADE = {
    0: [("FED", 690), ("PT", 870), ("PTV", 990)],
    1: [("PPT", 570), ("PTM", 690), ("PT", 870), ("PTV", 990), ("PTN", 1100), ("COR", 1290)],
    2: [("PPT", 570), ("PTM", 690), ("PT", 870), ("PTV", 990), ("PTN", 1100), ("COR", 1290)],
    3: [("PPT", 570), ("PTM", 690), ("PT", 870), ("PTV", 990), ("FED", 1200), ("COR", 1290)],
    4: [("PPT", 570), ("PTM", 690), ("PT", 870), ("PTV", 990), ("PTN", 1100), ("COR", 1290)],
    5: [("PPT", 570), ("PTM", 690), ("PT", 870), ("PTV", 990), ("PTN", 1100), ("COR", 1290)],
    6: [("PPT", 570), ("PTM", 690), ("PT", 870), ("PTV", 990), ("PTN", 1170), ("COR", 1290)],
}


def _codigo_do_bloco(bloco: str, data) -> str | None:
    m = re.search(r"RJ,\s*(\d{1,2}):(\d{2}),?\s*([^<]*?)\s*(?:1º|de hoje|</h3>)", bloco)
    if not m:
        return None
    minutos = int(m.group(1)) * 60 + int(m.group(2))
    sufixo = m.group(3).strip()
    if sufixo:
        codigo = _normalizar_codigo(sufixo)
        if codigo:
            return codigo
    # sem código no cabeçalho: horário → apuração mais próxima da grade do dia
    dow = (data.weekday() + 1) % 7  # 0 = domingo
    melhor, melhor_dist = None, 10**9
    for sigla, min_grade in _GRADE[dow]:
        dist = abs(minutos - min_grade)
        if dist < melhor_dist:
            melhor, melhor_dist = sigla, dist
    return melhor


def grupo_de_dezena(dezena: int) -> int:
    if dezena == 0:
        return 25
    return (dezena - 1) // 4 + 1


def _normalizar_codigo(s: str) -> str:
    s = s.strip()
    primeira = s.split()[0] if s else ""
    chave = re.sub(r"[^A-Z]", "", primeira.upper())
    return _CODIGOS.get(chave, chave)


def baixar_pagina(data: date) -> str:
    req = urllib.request.Request(FONTE.format(data=data.isoformat()), headers=HEADERS)
    raw = urllib.request.urlopen(req, timeout=25).read()
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parsear_dia(html: str, data: date):
    """Devolve {"data": iso, "loterias": [...]} ou None (página caiu no fallback)."""
    if f"do dia {data.isoformat()}" not in html:
        return None  # página de fallback (resultado de outro dia)
    loterias = []
    # cada bloco de loteria começa em um 'result-column'
    blocos = re.split(r'class="col-sm-12 col-md-6 col-lg-6 result-column', html)
    por_codigo = {}
    for bloco in blocos[1:]:
        codigo = _codigo_do_bloco(bloco, data)
        if not codigo or len(codigo) > 4:
            continue
        premios = []
        for rm in re.finditer(
            r'class="rs-posicao"[^>]*>\s*<span>(.*?)</span>.*?'
            r'class="rs-numero"[^>]*>\s*<span>(.*?)</span>.*?'
            r'class="rs-grupo"[^>]*>\s*<span>\s*(.*?)\s*</span>.*?'
            r'class="rs-animal"[^>]*>(.*?)</div>',
            bloco, re.S,
        ):
            pos_texto, numero, grupo_texto, _animal = (rm.group(1), rm.group(2),
                                                       rm.group(3), rm.group(4))
            pm = re.search(r"\d+", pos_texto)
            if not pm:
                continue
            pos = int(pm.group())
            if pos > 5:  # 6º [soma] e 7º [mult] não são prêmios
                continue
            if not re.fullmatch(r"\d{4}", numero.strip()):
                continue
            gm = re.search(r"\d+", grupo_texto)
            if not gm:
                continue
            grupo = int(gm.group())
            if not (1 <= grupo <= 25):
                continue
            premios.append({
                "posicao": pos,
                "numero": numero.strip(),
                "grupo": grupo,
                "animal": _ANIMAIS.get(grupo, grupo_texto.strip()),
            })
        if premios:
            atual = por_codigo.get(codigo)
            # mesma loteria pode aparecer em vários blocos (ex.: 1º ao 5º e
            # 1º ao 10º) — fica o bloco com mais prêmios reais
            if atual is None or len(premios) > len(atual["premios"]):
                por_codigo[codigo] = {"codigo": codigo, "premios": premios}
    if not por_codigo:
        return None
    return {"data": data.isoformat(), "loterias": list(por_codigo.values())}


def carregar():
    if not os.path.isfile(ARQUIVO):
        return {"fonte": FONTE, "dias": {}}
    with open(ARQUIVO, "r", encoding="utf-8") as f:
        dados = json.load(f)
    dados.setdefault("dias", {})
    dados.setdefault("sem_dados", [])  # datas confirmadas sem apuração na fonte
    return dados


def salvar(dados):
    os.makedirs(PASTA_DADOS, exist_ok=True)
    tmp = ARQUIVO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, ARQUIVO)


def _processar_dia(dia):
    """Baixa e parseia um dia; devolve (dia, parsed|None)."""
    time.sleep(ATRASO_ENTRE_REQUISICOES * 2)
    html = baixar_pagina(dia)
    return dia, parsear_dia(html, dia)


def baixar_incremental(workers=5):
    dados = carregar()
    dias = dados["dias"]
    sem_dados = set(dados.get("sem_dados", []))
    hoje = date.today()
    # Buracos confirmados (sem apuração na fonte) só são tentados de novo se
    # forem recentes (≤3 dias) — evita rebaixar centenas de dias a cada rodada.
    limite_retry = hoje - timedelta(days=3)
    pendentes = []
    d = INICIO
    while d <= hoje:
        chave = d.isoformat()
        if chave not in dias and (chave not in sem_dados or d >= limite_retry):
            pendentes.append(d)
        d += timedelta(days=1)
    print(f"pendentes: {len(pendentes)} dias ({INICIO} → {hoje})")
    ok = falhas = 0
    lock = threading.Lock()
    ultimo_salvamento = time.time()
    contador = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futuras = {ex.submit(_processar_dia, dia): dia for dia in pendentes}
        for fut in as_completed(futuras):
            dia = futuras[fut]
            contador += 1
            try:
                _dia, parsed = fut.result()
                if parsed is None:
                    falhas += 1
                    with lock:
                        sem_dados.add(dia.isoformat())
                    print(f"  [{contador}/{len(pendentes)}] {dia} sem dados")
                else:
                    with lock:
                        dias[dia.isoformat()] = parsed
                        sem_dados.discard(dia.isoformat())
                    ok += 1
            except Exception as exc:  # noqa: BLE001
                falhas += 1
                print(f"  [{contador}/{len(pendentes)}] {dia} ERRO: {exc}")
            if contador % 50 == 0 or time.time() - ultimo_salvamento > 45:
                with lock:
                    dados["sem_dados"] = sorted(sem_dados)
                    dados["atualizado_em"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    salvar(dados)
                ultimo_salvamento = time.time()
                print(f"  ...{contador} processados ({ok} ok, {falhas} falhas) | último salvo: {sorted(dias)[-1] if dias else '-'}")
    dados["sem_dados"] = sorted(sem_dados)
    dados["atualizado_em"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    salvar(dados)
    print(f"concluído: {ok} dias ok, {falhas} sem dados → {ARQUIVO}")


def status():
    dados = carregar()
    dias = dados["dias"]
    if not dias:
        print("histórico vazio — rode: python historico.py")
        return
    chaves = sorted(dias)
    total_premios = sum(
        len(p["premios"]) for d in dias.values() for p in d["loterias"])
    print(f"dias: {len(dias)} ({chaves[0]} → {chaves[-1]})")
    print(f"prêmios: {total_premios}")
    print("loterias:", sorted({p["codigo"] for d in dias.values() for p in d["loterias"]}))


def teste():
    dia = date(2021, 1, 2)
    html = baixar_pagina(dia)
    print(json.dumps(parsear_dia(html, dia), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--status":
        status()
    elif arg == "--teste":
        teste()
    elif arg.isdigit():
        baixar_incremental(workers=int(arg))
    else:
        baixar_incremental()
