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
# Moto / carro
PRECO_GASOLINA = 7.00
CARRO_KM_POR_LITRO = 10.0
MANUTENCAO_POR_KM = 0.20
PNEUS_DEPRECIACAO_POR_KM = 0.15
MOTORISTA_CARRO = 15.00

# Caminhão
PRECO_DIESEL = 8.00
CAMINHAO_KM_POR_LITRO = 3.5
PRECO_ARLA = 3.50
ARLA_POR_LITROS_DIESEL = 1 / 20
MOTORISTA_CAMINHAO = 150.00
RASTREAMENTO_CAMINHAO = 80.00
SEGURO_CAMINHAO = 50.00

# Regras gerais
LUCRO = 0.20
PERCENTUAL_RECEBIDO = 0.75
VALOR_MAX_NF = 80000.00
PESO_INCLUSO_KG = 10
VALOR_KG_EXCEDENTE = 0.70
FATOR_CUBAGEM = 6000.0

SERVICOS = ["Premium", "Expresso", "Ecommerce", "Standard", "Econômico"]
SERVICOS_DOBRAM_CARRO = {"Ecommerce", "Standard", "Econômico"}

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
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
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
        _, sha = ler_github()
        gravar_github(historico, sha)
    else:
        LOCAL_DB_PATH.write_text(
            json.dumps(historico, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def moeda(valor):
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def arredondar_dezena_para_cima(valor):
    return math.ceil(float(valor) / 10.0) * 10.0


def calcular_peso(peso_real, altura, largura, comprimento):
    peso_cubado = (float(altura) * float(largura) * float(comprimento)) / FATOR_CUBAGEM
    peso_considerado = max(float(peso_real), peso_cubado)

    # Regra aprovada: somente kg inteiro excedente.
    # Ex.: 11,7 kg => 11 kg para cobrança => 1 kg excedente.
    kg_inteiros = math.floor(peso_considerado)
    kg_excedentes = max(0, kg_inteiros - PESO_INCLUSO_KG)
    adicional = kg_excedentes * VALOR_KG_EXCEDENTE

    return peso_cubado, peso_considerado, kg_excedentes, adicional


def calcular_carro_moto(km_ida, servico):
    km_total = float(km_ida) * 2

    gasolina_por_km = PRECO_GASOLINA / CARRO_KM_POR_LITRO
    custo_total = (
        km_total * gasolina_por_km
        + km_total * MANUTENCAO_POR_KM
        + km_total * PNEUS_DEPRECIACAO_POR_KM
        + MOTORISTA_CARRO
    )

    liquido_com_lucro = custo_total * (1 + LUCRO)
    valor_antes_arredondamento = liquido_com_lucro / PERCENTUAL_RECEBIDO
    valor_base = arredondar_dezena_para_cima(valor_antes_arredondamento)

    if servico in SERVICOS_DOBRAM_CARRO:
        valor_servico = valor_base * 2
    else:
        valor_servico = valor_base

    return {
        "regra": "Moto/Carro",
        "km_total": km_total,
        "custo_total": custo_total,
        "valor_calculado": valor_antes_arredondamento,
        "valor_base": valor_base,
        "valor_servico": valor_servico,
    }


def calcular_caminhao(km_ida):
    km_total = float(km_ida) * 2

    litros_diesel = km_total / CAMINHAO_KM_POR_LITRO
    custo_diesel = litros_diesel * PRECO_DIESEL

    litros_arla = litros_diesel * ARLA_POR_LITROS_DIESEL
    custo_arla = litros_arla * PRECO_ARLA

    custo_total = (
        custo_diesel
        + custo_arla
        + km_total * MANUTENCAO_POR_KM
        + km_total * PNEUS_DEPRECIACAO_POR_KM
        + RASTREAMENTO_CAMINHAO
        + MOTORISTA_CAMINHAO
        + SEGURO_CAMINHAO
    )

    liquido_com_lucro = custo_total * (1 + LUCRO)
    # Caminhão não usa arredondamento por dezena e serviço não dobra o valor.
    valor_servico = liquido_com_lucro / PERCENTUAL_RECEBIDO

    return {
        "regra": "Caminhão",
        "km_total": km_total,
        "custo_total": custo_total,
        "valor_calculado": valor_servico,
        "valor_base": valor_servico,
        "valor_servico": valor_servico,
    }


def registrar_cotacao(
    cep, km, servico, peso_real, altura, largura, comprimento,
    peso_cubado, peso_considerado, kg_excedentes, adicional_peso,
    valor_nf, tipo_veiculo, calculo, valor_final
):
    historico = carregar_historico()
    agora = datetime.now()

    registro = {
        "id": agora.strftime("%Y%m%d%H%M%S%f"),
        "data_hora": agora.strftime("%d/%m/%Y %H:%M:%S"),
        "timestamp": agora.isoformat(timespec="seconds"),
        "cep_coleta": cep.strip(),
        "km_informado": round(float(km), 2),
        "km_total_interno": round(float(calculo["km_total"]), 2),
        "servico": servico,
        "peso_total": round(float(peso_real), 2),
        "altura_cm": round(float(altura), 2),
        "largura_cm": round(float(largura), 2),
        "comprimento_cm": round(float(comprimento), 2),
        "peso_cubado": round(float(peso_cubado), 2),
        "peso_considerado": round(float(peso_considerado), 2),
        "kg_excedentes": int(kg_excedentes),
        "adicional_peso": round(float(adicional_peso), 2),
        "valor_nf": round(float(valor_nf), 2),
        "tipo_veiculo": tipo_veiculo,
        "regra_calculo": calculo["regra"],
        "valor_base": round(float(calculo["valor_base"]), 2),
        "valor_servico": round(float(calculo["valor_servico"]), 2),
        "valor_cotacao": round(float(valor_final), 2),
    }

    historico.append(registro)
    salvar_historico(historico)


st.markdown(
    """
<style>
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

        st.markdown("**Serviço da coleta**")
        servico = st.radio(
            "Selecione o serviço",
            SERVICOS,
            horizontal=True,
            label_visibility="collapsed",
        )

        peso_total = st.number_input(
            "Peso total (kg)",
            min_value=0.0,
            step=0.1,
            format="%.1f",
        )

        st.markdown("**Medidas da carga (cm)**")
        col1, col2, col3 = st.columns(3)
        with col1:
            altura = st.number_input(
                "Altura",
                min_value=0.0,
                step=1.0,
                format="%.1f",
            )
        with col2:
            largura = st.number_input(
                "Largura",
                min_value=0.0,
                step=1.0,
                format="%.1f",
            )
        with col3:
            comprimento = st.number_input(
                "Comprimento",
                min_value=0.0,
                step=1.0,
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
            ["Selecione...", "Moto", "Carro de passeio", "Caminhão", "Outro"],
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
        if altura <= 0 or largura <= 0 or comprimento <= 0:
            erros.append("Informe altura, largura e comprimento da carga.")
        if valor_nf <= 0:
            erros.append("Informe o valor da Nota Fiscal.")
        if tipo_veiculo == "Selecione...":
            erros.append("Selecione o tipo de veículo.")

        if erros:
            for erro in erros:
                st.error(erro)
        else:
            if tipo_veiculo == "Outro":
                st.warning(
                    "⚠️ TIPO DE VEÍCULO FORA DO PADRÃO.\n\n"
                    "Consulte a supervisão para esta cotação."
                )
            else:
                peso_cubado, peso_considerado, kg_excedentes, adicional_peso = calcular_peso(
                    peso_total, altura, largura, comprimento
                )

                # NF acima de 80 mil exige os parâmetros de caminhão/rastreamento,
                # mesmo que outro veículo tenha sido selecionado.
                operacao_caminhao = (
                    tipo_veiculo == "Caminhão" or valor_nf > VALOR_MAX_NF
                )

                if operacao_caminhao:
                    calculo = calcular_caminhao(km)
                else:
                    calculo = calcular_carro_moto(km, servico)

                valor_final = calculo["valor_servico"] + adicional_peso

                try:
                    registrar_cotacao(
                        cep_coleta,
                        km,
                        servico,
                        peso_total,
                        altura,
                        largura,
                        comprimento,
                        peso_cubado,
                        peso_considerado,
                        kg_excedentes,
                        adicional_peso,
                        valor_nf,
                        tipo_veiculo,
                        calculo,
                        valor_final,
                    )
                    st.success("Cotação calculada e salva no histórico.")
                except Exception:
                    st.error(
                        "O valor foi calculado, mas não foi possível salvar o histórico. "
                        "Verifique a configuração do banco."
                    )

                if valor_nf > VALOR_MAX_NF and tipo_veiculo != "Caminhão":
                    st.info(
                        "ℹ️ NF acima de R$ 80.000,00: foram aplicados automaticamente "
                        "os parâmetros de caminhão e rastreamento."
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
                    f"CEP {cep_coleta} • {km:.1f} km • {servico} • "
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
            placeholder="Digite CEP, serviço, veículo ou data",
        ).strip().lower()

        if busca:
            historico = [
                item for item in historico
                if busca in item.get("cep_coleta", "").lower()
                or busca in item.get("servico", "").lower()
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
                        &nbsp;•&nbsp;
                        🚗 {item.get("tipo_veiculo", "-")}
                        &nbsp;•&nbsp;
                        📦 {item.get("servico", "-")}
                        &nbsp;•&nbsp;
                        📏 {float(item.get("km_informado", 0)):.1f} km
                    </div>
                    <div style="margin-top:6px;color:#666;">
                        Peso real: {float(item.get("peso_total", 0)):.1f} kg
                        &nbsp;•&nbsp;
                        Peso cubado: {float(item.get("peso_cubado", 0)):.2f} kg
                        &nbsp;•&nbsp;
                        Peso considerado: {float(item.get("peso_considerado", item.get("peso_total", 0))):.2f} kg
                        <br>
                        Medidas: {float(item.get("altura_cm", 0)):.1f} ×
                        {float(item.get("largura_cm", 0)):.1f} ×
                        {float(item.get("comprimento_cm", 0)):.1f} cm
                        <br>
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
