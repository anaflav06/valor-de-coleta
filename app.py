import base64
import json
import math
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

st.set_page_config(
    page_title="Valor da Coleta | GDS Logística",
    page_icon="🚚",
    layout="centered",
)

# =========================================================
# PARÂMETROS INTERNOS — NÃO EXIBIDOS AO USUÁRIO OPERACIONAL
# =========================================================
PRECO_GASOLINA = 7.00
KM_POR_LITRO = 10.0
MANUTENCAO_POR_KM = 0.20
PNEUS_DEPRECIACAO_POR_KM = 0.15
MOTORISTA_POR_COLETA = 15.00
LUCRO = 0.20
PERCENTUAL_RECEBIDO = 0.75
VALOR_MAX_NF = 80000.00
TIPOS_PERMITIDOS = ["Moto", "Carro de passeio"]

LOCAL_DB_PATH = Path("database_cotacoes.json")


def segredo(nome, padrao=None):
    try:
        return st.secrets.get(nome, padrao)
    except Exception:
        return padrao


GITHUB_TOKEN = segredo("GITHUB_TOKEN")
GITHUB_REPO = segredo("GITHUB_REPO", "anaflav06/valor-de-coleta")
GITHUB_DATA_BRANCH = segredo("GITHUB_DATA_BRANCH", "main")
GITHUB_COTACOES_DB_PATH = segredo(
    "GITHUB_COTACOES_DB_PATH", "database_cotacoes.json"
)


def github_ativo():
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_url():
    return (
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/"
        f"{GITHUB_COTACOES_DB_PATH}"
    )


def ler_github():
    r = requests.get(
        github_url(),
        headers=github_headers(),
        params={"ref": GITHUB_DATA_BRANCH},
        timeout=20,
    )

    if r.status_code == 404:
        return [], None

    r.raise_for_status()
    payload = r.json()
    conteudo = base64.b64decode(payload["content"]).decode("utf-8")
    dados = json.loads(conteudo) if conteudo.strip() else []
    return (dados if isinstance(dados, list) else []), payload.get("sha")


def gravar_github(dados, sha=None):
    conteudo = json.dumps(
        dados, ensure_ascii=False, indent=2
    ).encode("utf-8")

    payload = {
        "message": "Atualiza histórico de cotações",
        "content": base64.b64encode(conteudo).decode("ascii"),
        "branch": GITHUB_DATA_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(
        github_url(),
        headers=github_headers(),
        json=payload,
        timeout=20,
    )
    r.raise_for_status()


def carregar_historico():
    if github_ativo():
        dados, _ = ler_github()
        return dados

    if not LOCAL_DB_PATH.exists():
        return []

    try:
        dados = json.loads(LOCAL_DB_PATH.read_text(encoding="utf-8"))
        return dados if isinstance(dados, list) else []
    except Exception:
        return []


def salvar_historico(historico):
    if github_ativo():
        # Lê o SHA mais recente imediatamente antes da gravação.
        _, sha = ler_github()
        gravar_github(historico, sha)
        return

    LOCAL_DB_PATH.write_text(
        json.dumps(historico, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def arredondar_faixa_30(valor):
    """
    Valores comerciais em faixas de R$ 30,00.
    Há tolerância de até R$ 2,00 acima da faixa anterior:
    30,01 até 32,00 -> 30,00
    acima de 32,00 -> 60,00
    60,01 até 62,00 -> 60,00, etc.
    """
    if valor <= 30.0:
        return 30.0

    faixa_inferior = math.floor(valor / 30.0) * 30.0

    # Se o valor for múltiplo exato de 30, mantém o próprio valor.
    if math.isclose(valor, faixa_inferior, abs_tol=1e-9):
        return faixa_inferior

    # Até R$ 2,00 acima da faixa, mantém a faixa anterior.
    if valor <= faixa_inferior + 2.0:
        return faixa_inferior

    return faixa_inferior + 30.0


def calcular_adicional_peso(peso_total):
    """
    Até 10 kg: sem adicional.
    A partir de 11 kg: R$ 0,70 por kg inteiro excedente.
    Frações de kg são desconsideradas.
    """
    kg_inteiros = math.floor(float(peso_total))
    kg_excedentes = max(0, kg_inteiros - 10)
    return kg_excedentes, kg_excedentes * 0.70


def calcular_valor_coleta(km_ida):
    # A distância informada é automaticamente considerada em ida + volta.
    km_total = float(km_ida) * 2
    gasolina_por_km = PRECO_GASOLINA / KM_POR_LITRO

    custo_total = (
        km_total * gasolina_por_km
        + km_total * MANUTENCAO_POR_KM
        + km_total * PNEUS_DEPRECIACAO_POR_KM
        + MOTORISTA_POR_COLETA
    )

    liquido_necessario = custo_total * (1 + LUCRO)
    valor_calculado = liquido_necessario / PERCENTUAL_RECEBIDO
    valor_base = arredondar_faixa_30(valor_calculado)

    return {
        "km_total": km_total,
        "custo_total": custo_total,
        "valor_calculado": valor_calculado,
        "valor_base": valor_base,
    }


def registrar_cotacao(cep, km, peso_total, valor_nf, tipo_veiculo, calculo, kg_excedentes, adicional_peso, valor_final):
    # Recarrega o banco antes de incluir para reduzir risco de sobrescrever
    # registros feitos por outro usuário.
    historico = carregar_historico()
    agora = datetime.now()

    registro = {
        "id": agora.strftime("%Y%m%d%H%M%S%f"),
        "data_hora": agora.strftime("%d/%m/%Y %H:%M:%S"),
        "timestamp": agora.isoformat(timespec="seconds"),
        "cep_coleta": cep.strip(),
        "km_informado": round(float(km), 2),
        "km_total_interno": round(float(calculo["km_total"]), 2),
        "peso_total": round(float(peso_total), 2),
        "kg_excedentes": int(kg_excedentes),
        "adicional_peso": round(float(adicional_peso), 2),
        "valor_nf": round(float(valor_nf), 2),
        "tipo_veiculo": tipo_veiculo,
        "valor_base": round(float(calculo["valor_base"]), 2),
        "valor_cotacao": round(float(valor_final), 2),
    }

    historico.append(registro)
    salvar_historico(historico)


st.markdown(
    """
<style>
:root {
    --orange: #f47c20;
    --black: #111111;
    --dark: #242424;
    --gray: #6c6c6c;
    --light: #f3f3f3;
    --white: #ffffff;
}
.stApp {
    background:
        radial-gradient(circle at top right, rgba(244,124,32,.09), transparent 30%),
        linear-gradient(180deg, #f8f8f8 0%, #ededed 100%);
}
.block-container {
    max-width: 860px;
    padding-top: 1.8rem;
    padding-bottom: 3rem;
}
.gds-header {
    background: linear-gradient(135deg, #0e0e0e 0%, #2c2c2c 72%, #593116 120%);
    border-radius: 22px;
    padding: 28px 30px;
    margin-bottom: 22px;
    border-bottom: 4px solid #f47c20;
    box-shadow: 0 12px 30px rgba(0,0,0,.13);
}
.gds-brand {
    color: #f47c20;
    font-size: .82rem;
    font-weight: 900;
    letter-spacing: .16em;
}
.gds-title {
    color: white;
    font-size: 2rem;
    font-weight: 850;
    margin-top: 4px;
}
.gds-sub {
    color: #d6d6d6;
    margin-top: 6px;
}
div[data-testid="stForm"] {
    background: linear-gradient(145deg, #ffffff 0%, #f4f4f4 100%);
    border: 1px solid #dedede;
    border-radius: 20px;
    padding: 22px 22px 8px 22px;
    box-shadow: 0 8px 24px rgba(0,0,0,.07);
}
div[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(90deg, #f47c20 0%, #ff963f 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    min-height: 48px;
    font-weight: 850 !important;
    box-shadow: 0 6px 16px rgba(244,124,32,.25);
}
.resultado {
    background: linear-gradient(135deg, #111111 0%, #2c2c2c 70%, #4b2a13 100%);
    border-left: 6px solid #f47c20;
    border-radius: 20px;
    padding: 27px;
    text-align: center;
    margin-top: 20px;
    box-shadow: 0 12px 28px rgba(0,0,0,.16);
}
.resultado-label {
    color: #d9d9d9;
    font-size: .88rem;
    font-weight: 800;
    letter-spacing: .08em;
}
.resultado-valor {
    color: white;
    font-size: 2.65rem;
    font-weight: 900;
}
.hist-card {
    background: linear-gradient(145deg, #ffffff, #f1f1f1);
    border: 1px solid #dddddd;
    border-left: 5px solid #f47c20;
    border-radius: 15px;
    padding: 16px 18px;
    margin-bottom: 12px;
    box-shadow: 0 5px 16px rgba(0,0,0,.06);
}
.hist-date {
    color: #666;
    font-size: .83rem;
    font-weight: 700;
}
.hist-value {
    font-size: 1.35rem;
    font-weight: 900;
    color: #111;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #111111 0%, #292929 100%);
}
[data-testid="stSidebar"] * {
    color: white;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="gds-header">
    <div class="gds-brand">GDS LOGÍSTICA</div>
    <div class="gds-title">🚚 Valor da Coleta</div>
    <div class="gds-sub">Cotação rápida e padronizada para a operação.</div>
</div>
""",
    unsafe_allow_html=True,
)

pagina = st.sidebar.radio(
    "MENU",
    ["🚚 Nova Cotação", "📋 Histórico de Cotações"],
)

if pagina == "🚚 Nova Cotação":
    with st.form("form_coleta"):
        cep_coleta = st.text_input(
            "CEP da coleta",
            placeholder="Ex.: 04150-010",
            max_chars=9,
        )

        km = st.number_input(
            "Quilometragem até o local da coleta (km)",
            min_value=0.0,
            step=0.1,
            format="%.1f",
        )

        peso_total = st.number_input(
            "Peso total (kg)",
            min_value=0.0,
            step=0.1,
            format="%.1f",
        )

        valor_nf = st.number_input(
            "Valor da Nota Fiscal (NF)",
            min_value=0.0,
            step=100.0,
            format="%.2f",
        )

        tipo_veiculo = st.selectbox(
            "Tipo de veículo",
            ["Selecione...", "Moto", "Carro de passeio", "Outro"],
        )

        calcular = st.form_submit_button(
            "CALCULAR VALOR DA COLETA",
            use_container_width=True,
            type="primary",
        )

    if calcular:
        erros = []

        if not cep_coleta.strip():
            erros.append("Informe o CEP da coleta.")
        if km <= 0:
            erros.append("Informe a quilometragem da coleta.")
        if peso_total <= 0:
            erros.append("Informe o peso total da carga.")
        if valor_nf <= 0:
            erros.append("Informe o valor da Nota Fiscal.")
        if tipo_veiculo == "Selecione...":
            erros.append("Selecione o tipo de veículo.")

        if erros:
            for erro in erros:
                st.error(erro)
        else:
            exige_supervisao = False

            if valor_nf > VALOR_MAX_NF:
                exige_supervisao = True
                st.warning(
                    "⚠️ VALOR DA NF ACIMA DE R$ 80.000,00.\n\n"
                    "Consulte a supervisão antes de informar ou confirmar o valor da coleta."
                )

            if tipo_veiculo not in TIPOS_PERMITIDOS:
                exige_supervisao = True
                st.warning(
                    "⚠️ TIPO DE VEÍCULO FORA DO PADRÃO.\n\n"
                    "Para veículos acima de moto ou carro de passeio, consulte a supervisão."
                )

            if exige_supervisao:
                st.info(
                    "Esta cotação precisa de validação da supervisão. "
                    "O valor automático não será exibido."
                )
            else:
                calculo = calcular_valor_coleta(km)
                kg_excedentes, adicional_peso = calcular_adicional_peso(peso_total)
                valor_final = calculo["valor_base"] + adicional_peso

                try:
                    registrar_cotacao(
                        cep_coleta,
                        km,
                        peso_total,
                        valor_nf,
                        tipo_veiculo,
                        calculo,
                        kg_excedentes,
                        adicional_peso,
                        valor_final,
                    )
                    st.success("Cotação calculada e salva no histórico.")
                except Exception:
                    st.error(
                        "O valor foi calculado, mas não foi possível salvar "
                        "o histórico. Verifique a configuração do banco."
                    )

                st.markdown(
                    f"""
                    <div class="resultado">
                        <div class="resultado-label">VALOR DA COLETA</div>
                        <div class="resultado-valor">{moeda(valor_final)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.caption(
                    f"CEP {cep_coleta} • {km:.1f} km • {peso_total:.1f} kg • "
                    f"{tipo_veiculo} • NF {moeda(valor_nf)}"
                )

else:
    st.subheader("📋 Histórico de Cotações")

    try:
        historico = carregar_historico()
    except Exception:
        historico = []
        st.error(
            "Não foi possível carregar o histórico. "
            "Verifique os Secrets e o acesso ao GitHub."
        )

    if not historico:
        st.info("Ainda não há cotações salvas.")
    else:
        historico = sorted(
            historico,
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )

        busca = st.text_input(
            "🔎 Buscar no histórico",
            placeholder="Digite CEP, tipo de veículo ou data",
        ).strip().lower()

        if busca:
            historico = [
                item for item in historico
                if busca in item.get("cep_coleta", "").lower()
                or busca in item.get("tipo_veiculo", "").lower()
                or busca in item.get("data_hora", "").lower()
            ]

        st.caption(f"{len(historico)} cotação(ões) encontrada(s).")

        for item in historico:
            st.markdown(
                f"""
                <div class="hist-card">
                    <div class="hist-date">🕒 {item.get("data_hora", "-")}</div>
                    <div class="hist-value">{moeda(item.get("valor_cotacao", 0))}</div>
                    <div>
                        📍 CEP {item.get("cep_coleta", "-")}
                        &nbsp;&nbsp;•&nbsp;&nbsp;
                        🚗 {item.get("tipo_veiculo", "-")}
                        &nbsp;&nbsp;•&nbsp;&nbsp;
                        📏 {float(item.get("km_informado", 0)):.1f} km
                        &nbsp;&nbsp;•&nbsp;&nbsp;
                        ⚖️ {float(item.get("peso_total", 0)):.1f} kg
                    </div>
                    <div style="margin-top:5px;color:#666;">
                        NF: {moeda(item.get("valor_nf", 0))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.divider()
st.caption(
    "Uso interno GDS Logística. Situações fora dos limites do sistema "
    "devem ser validadas pela supervisão."
)
