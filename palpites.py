#!/usr/bin/env python3
"""
Motor de palpites do Jogo do Bicho RJ.

1. Estatísticas reais do histórico completo (2021 → hoje): frequência geral,
   frequência recente (2 meses), dias "atrasado" sem sair, repetição do dia
   anterior e frequência no 1º prêmio.
2. Três grupos sugeridos com motivos explicados (diversificados: um atrasado,
   um em alta, um consistente).
3. Palpite pessoal numerológico — mesma fórmula do "Palpitômetro" do
   ojogodobicho.com (FNV-1a 32 bits + xorshift32, semente = data de nascimento
   + janela da próxima apuração), que é o palpite popular que circula na web.
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASTA_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
ARQUIVO_HISTORICO = os.path.join(PASTA_DADOS, "historico.json")

ANIMAIS = {
    1: ("Avestruz", "🐦"), 2: ("Águia", "🦅"), 3: ("Burro", "🐴"),
    4: ("Borboleta", "🦋"), 5: ("Cachorro", "🐕"), 6: ("Cabra", "🐐"),
    7: ("Carneiro", "🐑"), 8: ("Camelo", "🐫"), 9: ("Cobra", "🐍"),
    10: ("Coelho", "🐇"), 11: ("Cavalo", "🐎"), 12: ("Elefante", "🐘"),
    13: ("Galo", "🐓"), 14: ("Gato", "🐈"), 15: ("Jacaré", "🐊"),
    16: ("Leão", "🦁"), 17: ("Macaco", "🐒"), 18: ("Porco", "🐷"),
    19: ("Pavão", "🦚"), 20: ("Peru", "🦃"), 21: ("Touro", "🐂"),
    22: ("Tigre", "🐅"), 23: ("Urso", "🐻"), 24: ("Veado", "🦌"),
    25: ("Vaca", "🐄"),
}

# Grade de apurações (minutos desde a meia-noite, fuso do Rio) — mesma do
# Palpitômetro do ojogodobicho.com. 0 = domingo.
GRADE_APURACOES = {
    0: [["FED", 690], ["PT", 870], ["PTV", 990]],
    1: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    2: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    3: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["FED", 1200], ["COR", 1290]],
    4: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    5: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1100], ["COR", 1290]],
    6: [["PPT", 570], ["PTM", 690], ["PT", 870], ["PTV", 990], ["PTN", 1170], ["COR", 1290]],
}
NOMES_LOTERIAS = {
    "PPT": "Para Todos", "PTM": "PT Manhã", "PT": "PT Tarde",
    "PTV": "PT Vespera", "PTN": "PT Noite", "FED": "Federal", "COR": "Coruja",
}
FUSO_RIO = timezone(timedelta(hours=-3))  # Brasil sem horário de verão desde 2019


# ---------------------------------------------------------------- histórico

def _inicio_janela(ref: date, meses: int = 2) -> date:
    """Data de início da janela: 'meses' meses atrás, contando do dia.
    Ex.: 13/08/2026 → 13/06/2026 (clamp para o último dia do mês, ex.: 31/03 → 28/02)."""
    import calendar
    mes_alvo = ref.month - meses
    ano = ref.year
    while mes_alvo <= 0:
        mes_alvo += 12
        ano -= 1
    ultimo_dia = calendar.monthrange(ano, mes_alvo)[1]
    return date(ano, mes_alvo, min(ref.day, ultimo_dia))


def carregar_dias():
    """Lista de dias (ordem cronológica): [{"data", "loterias": [...]}]."""
    if not os.path.isfile(ARQUIVO_HISTORICO):
        return []
    with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
        dados = json.load(f)
    dias = list(dados.get("dias", {}).values())
    dias.sort(key=lambda d: d["data"])
    return dias


def atualizado_em():
    """Data/hora (ISO) da última atualização do arquivo de histórico."""
    try:
        with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
            return json.load(f).get("atualizado_em")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- estatísticas

def calcular_estatisticas(dias, ref: date):
    """Métricas por grupo (1-25) usando APENAS o 1º prêmio (a 'cabeça') da
    janela dos últimos 2 meses. O atraso e a repetição de ontem usam todo o
    histórico (para saber quando saiu por último), as frequências usam a janela."""
    total_cabeca_hist = defaultdict(int)      # todo o histórico (filtro mínimo)
    total_cabecas_janela = 0
    freq_cabeca_janela = defaultdict(int)
    ultima_cabeca = defaultdict(lambda: None)
    cabecas_ontem = set()

    if dias:
        chaves = [d["data"] for d in dias]
        data_ontem = (ref - timedelta(days=1)).isoformat()
        if data_ontem in set(chaves):
            dia_ontem = dias[chaves.index(data_ontem)]
            cabecas_ontem = {
                p["grupo"] for l in dia_ontem["loterias"]
                for p in l["premios"] if p["posicao"] == 1}
        inicio_janela = _inicio_janela(ref).isoformat()

        for dia in dias:
            for loteria in dia["loterias"]:
                for p in loteria["premios"]:
                    if p["posicao"] != 1:
                        continue
                    g = p["grupo"]
                    if not (1 <= g <= 25):
                        continue
                    total_cabeca_hist[g] += 1
                    if ultima_cabeca[g] is None or dia["data"] > ultima_cabeca[g]:
                        ultima_cabeca[g] = dia["data"]
                    if dia["data"] >= inicio_janela:
                        total_cabecas_janela += 1
                        freq_cabeca_janela[g] += 1

    stats = []
    for g in range(1, 26):
        nome, emoji = ANIMAIS[g]
        ult_cab = ultima_cabeca.get(g)
        atraso_cabeca_dias = None
        if ult_cab:
            atraso_cabeca_dias = (ref - date.fromisoformat(ult_cab)).days
        stats.append({
            "grupo": g,
            "animal": nome,
            "emoji": emoji,
            "total_cabeca": total_cabeca_hist[g],
            "total_cabeca_janela": freq_cabeca_janela[g],
            "freq_cabeca_janela": round(freq_cabeca_janela[g] / total_cabecas_janela * 100, 2)
                if total_cabecas_janela else 0,
            "ultima_cabeca": ult_cab,
            "atraso_cabeca_dias": atraso_cabeca_dias,
            "repetiu_cabeca_ontem": g in cabecas_ontem,
        })
    return stats, total_cabecas_janela


# ---------------------------------------------------------------- os 3 grupos

def gerar_palpites(dias, ref: date):
    """Três grupos sugeridos, um por estratégia, com motivos explicados.
    As estatísticas usam APENAS o 1º prêmio dos últimos 2 meses."""
    stats, total_cabecas_janela = calcular_estatisticas(dias, ref)
    por_grupo = {s["grupo"]: s for s in stats}
    inicio_janela = _inicio_janela(ref)

    def sem_os(grupos_escolhidos):
        return [s for s in stats if s["grupo"] not in grupos_escolhidos]

    escolhidos = []
    palpites = []

    def _adicionar(s, estrategia, motivo):
        escolhidos.append(s["grupo"])
        palpites.append({
            "grupo": s["grupo"],
            "animal": s["animal"],
            "emoji": s["emoji"],
            "estrategia": estrategia,
            "motivo": motivo,
            "dezenas": [f"{(s['grupo'] - 1) * 4 + i:02d}" if (s['grupo'] - 1) * 4 + i < 100 else "00"
                        for i in range(1, 5)],
        })

    # 1) Bicho atrasado — maior tempo sem sair NA CABEÇA (1º prêmio), que é
    #    a aposta mais popular e onde o atraso realmente chama atenção
    candidatos_atrasados = sorted(
        [s for s in stats if s["total_cabeca"] >= 8 and s["atraso_cabeca_dias"] is not None],
        key=lambda s: s["atraso_cabeca_dias"], reverse=True)
    if candidatos_atrasados:
        s = candidatos_atrasados[0]
        _adicionar(s, "atrasado",
            f"está há {s['atraso_cabeca_dias']} dias sem sair no 1º prêmio "
            f"(a 'cabeça' — última vez em {_data_curta(s['ultima_cabeca'])}). "
            f"O 'bicho atrasado' é o palpite mais comentado nas bancas: a "
            f"chance de voltar à cabeça cresce a cada dia.")

    # 2) Em alta — melhor frequência no 1º prêmio nos últimos 2 meses
    candidatos_quentes = sorted(
        [s for s in sem_os(escolhidos) if s["total_cabeca_janela"] >= 2],
        key=lambda s: (s["freq_cabeca_janela"], s["total_cabeca_janela"]), reverse=True)
    if candidatos_quentes:
        s = candidatos_quentes[0]
        _adicionar(s, "quente",
            f"saiu no 1º prêmio {s['total_cabeca_janela']} vezes nos últimos "
            f"2 meses ({s['freq_cabeca_janela']:.1f}% das cabeças do período) — "
            f"é a cabeça em melhor fase. Quem acompanha o jogo de perto aposta "
            f"nos 'quentes'.")

    # 3) Consistente — mais 1º prêmios nos últimos 2 meses + repetição de ontem
    candidatos_frios = sorted(
        sem_os(escolhidos),
        key=lambda s: (s["total_cabeca_janela"], s["freq_cabeca_janela"]), reverse=True)
    if candidatos_frios:
        s = candidatos_frios[0]
        extra = ""
        if s["repetiu_cabeca_ontem"]:
            extra = " Repetiu ontem na cabeça, e repetição é um dos jogos mais comuns."
        _adicionar(s, "consistente",
            f"é o grupo com mais 1º prêmios nos últimos 2 meses "
            f"({s['total_cabeca_janela']} cabeças, {s['freq_cabeca_janela']:.1f}% "
            f"do período){extra}")
    return {
        "gerado_em": datetime.now(FUSO_RIO).isoformat(timespec="seconds"),
        "referencia": ref.isoformat(),
        "palpites": palpites,
        "estatisticas": stats,
        "cobertura": {
            "janela": "últimos 2 meses",
            "inicio": inicio_janela.isoformat(),
            "fim": ref.isoformat(),
            "dias": sum(1 for d in dias if d["data"] >= inicio_janela.isoformat()),
            "total_cabecas": total_cabecas_janela,
            "arquivo": {
                "inicio": dias[0]["data"] if dias else None,
                "fim": dias[-1]["data"] if dias else None,
                "dias": len(dias),
                "total_premios": sum(len(p["premios"]) for d in dias for p in d["loterias"]),
            },
        },
    }


def _data_curta(iso: str) -> str:
    if not iso:
        return "?"
    d = date.fromisoformat(iso)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


# ------------------------------------------------- palpite pessoal (numerologia)

def fnv1a32(s: str) -> int:
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def xorshift32(x: int) -> int:
    x = (x ^ ((x << 13) & 0xFFFFFFFF)) & 0xFFFFFFFF
    x ^= x >> 17
    x = (x ^ ((x << 5) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return x & 0xFFFFFFFF


def proxima_apuracao(agora_rio: datetime):
    """Próxima apuração a sair: {"sigla", "hora", "data", "chave", "rotulo"}."""
    dow = agora_rio.weekday()  # segunda=0 ... domingo=6 (igual ao JS: 0=domingo?)
    # JS usa getUTCDay(): 0 = domingo. Python weekday(): 0 = segunda. Ajusta:
    dow_js = (agora_rio.weekday() + 1) % 7
    minutos = agora_rio.hour * 60 + agora_rio.minute
    grade = GRADE_APURACOES[dow_js]
    for sigla, min_apuracao in grade:
        if minutos < min_apuracao:
            return _reg_apuracao(sigla, min_apuracao, agora_rio.date(), False)
    # depois da última do dia → primeira de amanhã
    amanha = agora_rio.date() + timedelta(days=1)
    grade_amanha = GRADE_APURACOES[(amanha.weekday() + 1) % 7]
    sigla, min_apuracao = grade_amanha[0]
    return _reg_apuracao(sigla, min_apuracao, amanha, True)


def _reg_apuracao(sigla, minutos, data, amanha):
    hora = f"{minutos // 60:02d}:{minutos % 60:02d}"
    chave = f"{data.isoformat()}|{sigla}"
    rotulo = f"{sigla} {'de amanhã' if amanha else 'de hoje'} ({hora})"
    return {"sigla": sigla, "hora": hora, "data": data.isoformat(),
            "chave": chave, "rotulo": rotulo, "nome": NOMES_LOTERIAS.get(sigla, sigla)}


def palpite_pessoal(nascimento: date, agora_rio: datetime):
    """Mesma fórmula do Palpitômetro (ojogodobicho.com) para a próxima apuração."""
    apuracao = proxima_apuracao(agora_rio)
    semente = f"{nascimento.year:04d}-{nascimento.month:02d}-{nascimento.day:02d}|{apuracao['chave']}"
    x = fnv1a32(semente)
    if x == 0:
        x = 0x9E3779B9
    x = xorshift32(x)
    grupo = 1 + x % 25
    x = xorshift32(x)
    idx_dez = x % 4
    x = xorshift32(x)
    cen_pre = x % 10
    x = xorshift32(x)
    mil_pre = x % 10

    base = (grupo - 1) * 4
    dezenas = [f"{(base + i) % 100:02d}" for i in range(1, 5)]
    dezena = dezenas[idx_dez]
    centena = f"{cen_pre * 100 + int(dezena):03d}"
    milhar = f"{mil_pre * 1000 + int(centena):04d}"
    nome, emoji = ANIMAIS[grupo]
    return {
        "apuracao": apuracao,
        "grupo": grupo,
        "animal": nome,
        "emoji": emoji,
        "dezenas": dezenas,
        "dezena": dezena,
        "centena": centena,
        "milhar": milhar,
        "metodo": "FNV-1a 32 bits + xorshift32 (mesma fórmula do Palpitômetro do ojogodobicho.com)",
    }


def agora_rio() -> datetime:
    return datetime.now(FUSO_RIO).replace(tzinfo=None)


if __name__ == "__main__":
    dias = carregar_dias()
    print(f"dias carregados: {len(dias)}")
    if dias:
        res = gerar_palpites(dias, date.today())
        for p in res["palpites"]:
            print(f"  {p['emoji']} Grupo {p['grupo']} ({p['animal']}) — {p['motivo']}")
        print("cobertura:", res["cobertura"])
    pp = palpite_pessoal(date(1990, 1, 1), agora_rio())
    print("palpite pessoal:", pp["emoji"], pp["animal"], pp["milhar"], "| próxima:", pp["apuracao"]["rotulo"])
