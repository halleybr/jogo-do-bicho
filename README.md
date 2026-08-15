# Jogo do Bicho RJ — Resultados + Palpites

Site informativo com os resultados do Jogo do Bicho do **Rio de Janeiro**
("Deu no Poste"), busca por milhar/centena/dezena/grupo/bicho, **histórico
completo de 2021 até hoje** e **palpites do dia** gerados com estatísticas
reais — tudo sem dependências externas (Python padrão + HTML/CSS/JS puro).

## Atualização automática diária

- O `server.py` **atualiza o histórico sozinho**: na inicialização baixa os
  dias que faltam e depois roda uma verificação por dia às **23:30 (Brasília)**,
  após a última apuração (Coruja 21:30). Basta deixar o servidor rodando.
- Os palpites são recalculados automaticamente após cada atualização, e o site
  mostra quando o arquivo foi atualizado por último.
- O repositório inclui um **workflow do GitHub Actions**
  (`.github/workflows/atualizar-historico.yml`) que roda diariamente às 23:45
  (Brasília), baixa os dias novos e commita o `dados/historico.json` — assim,
  quando o site estiver publicado (ex.: Render), o deploy sempre nasce com o
  histórico em dia, mesmo se o servidor ficar dormindo.

## Como funciona

- **Resultados de hoje** — raspados de
  [www.ojogodobicho.com/deu_no_poste.htm](https://www.ojogodobicho.com/deu_no_poste.htm),
  que publica as apurações do RJ (PPT, PTM, PT, PTV, PTN, FED, COR) divulgadas
  pela imprensa.
- **Histórico completo (2021 → hoje)** — baixado de
  [resultadojogobicho.com/RJ/dia/](https://resultadojogobicho.com/RJ/dia/2026-08-13)
  (arquivo gratuito mais antigo disponível; 2020 não existe em fonte gratuita
  confiável) e persistido em `dados/historico.json` de forma incremental.
  Cada dia guarda as loterias com os 5 prêmios (milhar + grupo + bicho).
- **Palpites do dia (3 grupos)** — motor estatístico em `palpites.py` que
  analisa apenas o **1º prêmio (a cabeça)** dos **últimos 2 meses**: escolhe um
  grupo **atrasado** (mais dias sem sair na cabeça), um **em alta** (melhor
  frequência no 1º prêmio do período) e um **consistente** (mais cabeças nos
  últimos 2 meses / repetiu ontem), cada um com o motivo explicado.
- **Palpite pessoal (numerologia)** — reproduz a fórmula do popular
  [Palpitômetro do ojogodobicho.com](https://www.ojogodobicho.com/palpite.htm)
  (FNV-1a 32 bits + xorshift32, semente = data de nascimento + próxima
  apuração): informe sua data e veja bicho, dezena, centena e milhar sugeridos.

## Rodando

```bash
python historico.py          # baixa o histórico completo (incremental, ~5 workers)
python server.py             # sobe o site em http://127.0.0.1:8000
```

> No Windows, se o comando `python` não existir, use o caminho do interpretador,
> ex.: `/c/Python314/python server.py`.

## Endpoints

| Rota | Descrição |
|------|-----------|
| `/` | Site (página principal) |
| `/api/resultados` | Resultado de hoje + últimos dias (fonte: ojogodobicho.com) |
| `/api/resultados?forcar=1` | Ignora o cache e raspa de novo |
| `/api/palpites` | 3 grupos sugeridos + estatísticas completas + cobertura do histórico |
| `/api/palpites?nascimento=DD/MM/AAAA` | Inclui o palpite pessoal numerológico |
| `/api/historico?numero=6465&grupo=17&de=&ate=&loteria=&limite=` | Busca no histórico completo |
| `/diario.html` | Página de **resultados diários** (escolha a data, navegue dia a dia, busque no dia) |
| `/api/diario?data=AAAA-MM-DD` | Resultados de um dia específico do arquivo + vizinhos para navegação (sem `data`, retorna o último dia) |

## Estrutura

```
server.py            servidor HTTP + raspador do dia + API (resultados, palpites, histórico, diário)
historico.py         downloader/parser do histórico 2021→hoje (incremental)
palpites.py          motor estatístico + palpite pessoal (fórmula do Palpitômetro)
gerar_estatico.py    gera os JSONs para o modo estático (public/dados/) — usado pelo workflow do Pages
dados/historico.json cache do histórico (gerado pelo historico.py)
public/index.html    página principal (hoje, palpites, busca, tabela dos bichos)
public/diario.html   página de resultados diários
public/estatico.js   modo estático: emula /api/historico e /api/diario no navegador + numerologia local
public/diario.js     lógica da página diária (navegação + busca no dia)
public/style.css     estilos
public/app.js        busca, palpites, histórico, atualização automática
```

> Para testar o modo estático localmente: `python gerar_estatico.py` e depois
> `cd public && python -m http.server 8000` (sem rodar o `server.py`).

## Publicando na internet

O site tem dois modos: **com backend** (Render/Railway/PythonAnywhere/VPS),
com resultados em tempo real raspados do ojogodobicho.com; e **estático**
(GitHub Pages), com os dados gerados uma vez por dia — o frontend detecta a
ausência do backend (`/api/*` devolvendo 404) e usa os JSONs de
`public/dados/` gerados pelo `gerar_estatico.py`.

### GitHub Pages (gratuito, sem servidor)

1. Publique o repositório no GitHub e ative o Pages em **Settings → Pages →
   Source: GitHub Actions** (uma única vez).
2. O workflow `.github/workflows/pages.yml` publica o site a cada push na
   `main` e também todo dia de madrugada: ele roda `historico.py` (baixa os
   dias novos) e `gerar_estatico.py` (gera os JSONs) antes do deploy.
3. O resultado fica em `https://SEU-USUARIO.github.io/jogo-do-bicho/` (ou no
   seu domínio customizado).

No modo estático o site fica **atrasado em até ~1 dia** em relação à última
apuração (os dados são os do último build), o botão "Atualizar" some e o
palpite pessoal (numerologia) é calculado no próprio navegador, com a mesma
fórmula. A busca no histórico completo e a página diária rodam no navegador
sobre o `dados/historico.json` (3,7 MB) incluído no deploy.

### Com backend (resultados em tempo real)

O modo completo **precisa de um servidor que rode Python** (ele raspa os
resultados e serve a API). Opções gratuitas/simples:

1. **Render** ([render.com](https://render.com), free tier) ou **Railway** —
   conecte o repositório Git e o serviço detecta o `server.py`; defina:
   - **Build command:** `python historico.py` (ou pule se você subir o
     `dados/historico.json` — tem só ~3,7 MB)
   - **Start command:** `python server.py`
   - **Health check:** `/api/resultados`
   - O Render já injeta `PORT` e o servidor agora respeita `PORT`/`HOST`
     (rode com `HOST=0.0.0.0` para escutar em todas as interfaces).
2. **PythonAnywhere** — mais manual: envie os arquivos pelo painel, rode
   `historico.py` uma vez e deixe `server.py` sempre ativo (precisa de conta
   paga para manter 24/7; a gratuita dorme).
3. **VPS** (Hetzner ~€4/mês, Oracle Cloud free tier) — `git clone` no servidor,
   `python historico.py`, e rode:
   ```bash
   HOST=0.0.0.0 PORT=8000 python server.py
   ```
   (idealmente com `systemd` ou `screen` para manter no ar; use um proxy
   reverso tipo Caddy/Nginx para HTTPS).

Para testar em qualquer host:

```bash
HOST=0.0.0.0 PORT=8000 python server.py
```

> O arquivo `dados/historico.json` (3,7 MB) já contém 2021→hoje: você pode
> subi-lo junto em vez de rodar o download do zero no servidor.

## Aviso

O jogo do bicho **não é regulamentado no Brasil** (proibido por lei federal
desde 1946). Este projeto é apenas informativo — não faz, intermedia nem
incentiva apostas. Palpites são estatísticos/folclóricos: o sorteio é aleatório
e nenhum palpite garante resultado. Os resultados são os divulgados pela
imprensa e reunidos no ojogodobicho.com e resultadojogobicho.com.
