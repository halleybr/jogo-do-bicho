#!/usr/bin/env python3
"""
Gera os arquivos JSON que permitem publicar o site como estático
(GitHub Pages), sem o backend Python:

  public/dados/resultados.json  -> o que /api/resultados devolveria (hoje +
                                   últimos dias + tabela dos bichos)
  public/dados/palpites.json    -> o que /api/palpites devolveria
  public/dados/historico.json   -> cópia do dados/historico.json (busca no
                                   histórico e página diária rodam no navegador)

Rode depois do historico.py — o workflow .github/workflows/pages.yml faz os
dois passos na ordem certa. O frontend (public/app.js, public/diario.js)
detecta a ausência do backend e usa esses arquivos.
"""
import json
import os
from datetime import date, datetime, timedelta, timezone

import palpites

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_DADOS = os.path.join(PASTA_BASE, "dados")
PASTA_SAIDA = os.path.join(PASTA_BASE, "public", "dados")
ARQUIVO_HISTORICO = os.path.join(PASTA_DADOS, "historico.json")

# grupo -> (animal, emoji)
ANIMAIS = palpites.ANIMAIS

# codigo -> (nome, horário)
LOTERIAS = {
    "PPT": ("Para Todos", "09:30"),
    "PTM": ("PT Manhã", "11:30"),
    "PT": ("PT Tarde", "14:30"),
    "PTV": ("PT Vespera", "16:30"),
    "PTN": ("PT Noite", "18:30"),
    "FED": ("Federal", "19:00"),
    "COR": ("Coruja", "21:30"),
}

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

FUSO_RIO = timezone(timedelta(hours=-3))


def grupo_de_dezena(dezena: int) -> int:
    """Dezena (00-99) -> grupo (1-25). Ex.: 17 -> 5 (Cachorro), 00 -> 25 (Vaca)."""
    if dezena == 0:
        return 25
    return (dezena - 1) // 4 + 1


def detalhes_milhar(numero: str) -> dict:
    """'6465' -> dict com centena, dezena, grupo, animal e emoji."""
    numero = numero.strip()
    dezena = int(numero[-2:])
    grupo = grupo_de_dezena(dezena)
    animal, emoji = ANIMAIS[grupo]
    return {
        "numero": numero,
        "centena": numero[-3:],
        "dezena": f"{dezena:02d}",
        "grupo": grupo,
        "animal": animal,
        "emoji": emoji,
    }


def dezenas_do_grupo(grupo: int) -> str:
    """'01 a 04' para o grupo 1 ... '97 a 00' para o grupo 25."""
    ini = (grupo - 1) * 4 + 1
    fim = ini + 3
    if grupo == 25:
        ini, fim = 97, 0
    return f"{ini:02d} a {fim:02d}"


def minutos_loteria(codigo: str) -> int:
    """Horário da apuração em minutos desde a meia-noite (ordenação)."""
    _, horario = LOTERIAS.get(codigo, ("", ""))
    try:
        hh, mm = horario.split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return 0


def data_long_pt(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def dia_para_hoje(dia: dict) -> list:
    """Formata um dia do arquivo como a seção 'hoje' de /api/resultados."""
    hoje = []
    for lot in dia["loterias"]:
        nome, horario = LOTERIAS.get(lot["codigo"], (lot["codigo"], ""))
        premios = [{"posicao": p["posicao"], **detalhes_milhar(p["numero"])}
                   for p in lot["premios"]]
        hoje.append({
            "codigo": lot["codigo"],
            "nome": nome,
            "horario": horario,
            "premios": premios,
            "centena": None,  # o arquivo guarda só os 5 prêmios (sem centena)
        })
    # apuração mais tardia primeiro
    hoje.sort(key=lambda l: minutos_loteria(l["codigo"]), reverse=True)
    return hoje


def gerar_resultados(dias: list) -> dict:
    ultimo = dias[-1]
    hoje = dia_para_hoje(ultimo)

    historico = []
    for dia in dias[-8:-1]:  # os 7 dias anteriores ao último
        for lot in dia["loterias"]:
            nome = LOTERIAS.get(lot["codigo"], (lot["codigo"], ""))[0]
            a, m, d = dia["data"].split("-")  # ISO é AAAA-MM-DD
            historico.append({
                "data": f"{d}/{m}",
                "dia": int(d),
                "mes": int(m),
                "loteria": lot["codigo"],
                "nome": nome,
                "premios": [detalhes_milhar(p["numero"]) for p in lot["premios"]],
            })
    # mais recente primeiro (como a página raspada)
    historico.sort(key=lambda r: (r["mes"], r["dia"], minutos_loteria(r["loteria"])),
                   reverse=True)

    return {
        "fonte": "arquivo local (dados/historico.json)",
        "raspado_em": datetime.now(FUSO_RIO).isoformat(timespec="seconds"),
        "data": {
            "texto": "Última apuração disponível: " + data_long_pt(ultimo["data"]),
            "iso": ultimo["data"],
        },
        "hoje": hoje,
        "historico": historico,
        "animais": [
            {"grupo": g, "animal": a, "emoji": e, "dezenas": dezenas_do_grupo(g)}
            for g, (a, e) in sorted(ANIMAIS.items())
        ],
    }


def gerar_palpites(dias: list) -> dict:
    payload = palpites.gerar_palpites(dias, date.today())
    payload["cobertura"]["arquivo"]["atualizado_em"] = palpites.atualizado_em()
    payload["pessoal"] = None  # numerologia roda no navegador (public/estatico.js)
    return payload


def escrever(nome: str, obj) -> str:
    caminho = os.path.join(PASTA_SAIDA, nome)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return caminho


def main():
    if not os.path.isfile(ARQUIVO_HISTORICO):
        raise SystemExit(
            "dados/historico.json não encontrado — rode 'python historico.py' antes.")
    dias = palpites.carregar_dias()
    if not dias:
        raise SystemExit("dados/historico.json está vazio — rode 'python historico.py'.")

    os.makedirs(PASTA_SAIDA, exist_ok=True)

    caminho = escrever("resultados.json", gerar_resultados(dias))
    print(f"gerado: {caminho}")

    caminho = escrever("palpites.json", gerar_palpites(dias))
    print(f"gerado: {caminho}")

    caminho = os.path.join(PASTA_SAIDA, "historico.json")
    with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as origem, \
            open(caminho, "w", encoding="utf-8") as destino:
        destino.write(origem.read())
    print(f"copiado: {caminho}")

    print(f"dias no arquivo: {len(dias)} ({dias[0]['data']} → {dias[-1]['data']})")


if __name__ == "__main__":
    main()
