import math
import streamlit as st

st.set_page_config(
    page_title="Valor da Coleta",
    page_icon="🚚",
    layout="centered"
)

# =========================================================
# PARÂMETROS INTERNOS
# Não exibir estas métricas para o usuário operacional.
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

def moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def arredondar_dezena_para_cima(valor):
    return math.ceil(valor / 10.0) * 10.0

def calcular_valor_coleta(km_ida):
    # A quilometragem digitada é a distância de ida.
    # A volta é sempre incluída automaticamente e não é opcional.
    km_total = km_ida * 2

    gasolina_por_km = PRECO_GASOLINA / KM_POR_LITRO
    gasolina = km_total * gasolina_por_km
    manutencao = km_total * MANUTENCAO_POR_KM
    pneus_depreciacao = km_total * PNEUS_DEPRECIACAO_POR_KM

    custo_total = (
        gasolina
        + manutencao
        + pneus_depreciacao
        + MOTORISTA_POR_COLETA
    )

    liquido_com_lucro = custo_total * (1 + LUCRO)
    valor_bruto = liquido_com_lucro / PERCENTUAL_RECEBIDO
    valor_final = arredondar_dezena_para_cima(valor_bruto)

    return valor_final

st.markdown("""
<style>
    :root {
        --gds-orange: #f47c20;
        --gds-black: #111111;
        --gds-dark: #1d1d1f;
        --gds-gray: #6b6b6b;
        --gds-light: #f4f4f4;
        --gds-white: #ffffff;
    }

    .stApp {
        background:
            radial-gradient(circle at top right, rgba(244,124,32,0.08), transparent 30%),
            linear-gradient(180deg, #f8f8f8 0%, #eeeeee 100%);
    }

    .block-container {
        max-width: 820px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    .gds-header {
        background: linear-gradient(135deg, #111111 0%, #303030 72%, #f47c20 160%);
        border-radius: 22px;
        padding: 28px 30px;
        margin-bottom: 24px;
        box-shadow: 0 12px 30px rgba(0,0,0,.12);
        border-bottom: 4px solid #f47c20;
    }

    .gds-brand {
        color: #f47c20;
        font-size: .82rem;
        font-weight: 800;
        letter-spacing: .16em;
        margin-bottom: 5px;
    }

    .titulo {
        color: #ffffff;
        font-size: 2.05rem;
        font-weight: 800;
        margin: 0;
        line-height: 1.15;
    }

    .subtitulo {
        color: #d5d5d5;
        font-size: .98rem;
        margin-top: 8px;
    }

    div[data-testid="stForm"] {
        background: linear-gradient(145deg, #ffffff 0%, #f5f5f5 100%);
        border: 1px solid #dedede;
        border-radius: 20px;
        padding: 22px 22px 8px 22px;
        box-shadow: 0 8px 24px rgba(0,0,0,.07);
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input {
        border-radius: 10px;
    }

    div[data-baseweb="select"] > div {
        border-radius: 10px;
    }

    div.stButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(90deg, #f47c20 0%, #ff963f 100%) !important;
        color: #ffffff !important;
        border: 0 !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        min-height: 48px;
        box-shadow: 0 6px 16px rgba(244,124,32,.25);
    }

    div[data-testid="stFormSubmitButton"] > button:hover {
        filter: brightness(.96);
        transform: translateY(-1px);
    }

    .resultado {
        background: linear-gradient(135deg, #111111 0%, #2c2c2c 70%, #4a2a13 100%);
        border: 1px solid #3b3b3b;
        border-left: 6px solid #f47c20;
        border-radius: 20px;
        padding: 26px;
        text-align: center;
        margin-top: 20px;
        box-shadow: 0 12px 28px rgba(0,0,0,.16);
    }

    .resultado-label {
        color: #d9d9d9;
        font-size: .9rem;
        font-weight: 700;
        letter-spacing: .08em;
        margin-bottom: 5px;
    }

    .resultado-valor {
        color: #ffffff;
        font-size: 2.65rem;
        font-weight: 900;
        line-height: 1.15;
    }

    .resultado-valor::first-letter {
        color: #f47c20;
    }

    hr {
        border-color: #d4d4d4 !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown(
    """
    <div class="gds-header">
        <div class="gds-brand">GDS LOGÍSTICA</div>
        <div class="titulo">🚚 Valor da Coleta</div>
        <div class="subtitulo">Preencha os dados abaixo para calcular o valor a ser cobrado.</div>
    </div>
    """,
    unsafe_allow_html=True
)

with st.form("form_coleta"):
    nome = st.text_input(
        "Nome",
        placeholder="Digite o nome do cliente ou solicitante"
    )

    numero_coleta = st.text_input(
        "Número da coleta",
        placeholder="Ex.: 12345"
    )

    cep_coleta = st.text_input(
        "CEP da coleta",
        placeholder="Ex.: 04150-010",
        max_chars=9
    )

    km = st.number_input(
        "Quilometragem até o local da coleta (km)",
        min_value=0.0,
        step=0.1,
        format="%.1f",
    )

    valor_nf = st.number_input(
        "Valor da Nota Fiscal (NF)",
        min_value=0.0,
        step=100.0,
        format="%.2f"
    )

    tipo_veiculo = st.selectbox(
        "Tipo de veículo",
        ["Selecione...", "Moto", "Carro de passeio", "Outro"]
    )

    calcular = st.form_submit_button(
        "CALCULAR VALOR DA COLETA",
        use_container_width=True,
        type="primary"
    )

if calcular:
    erros = []

    if not nome.strip():
        erros.append("Informe o nome.")
    if not numero_coleta.strip():
        erros.append("Informe o número da coleta.")
    if not cep_coleta.strip():
        erros.append("Informe o CEP da coleta.")
    if km <= 0:
        erros.append("Informe a quilometragem da coleta.")
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
                "A cotação precisa de validação da supervisão. "
                "O valor automático não será exibido."
            )
        else:
            valor_final = calcular_valor_coleta(km)

            st.success("Cálculo realizado com sucesso.")
            st.markdown(
                f"""
                <div class="resultado">
                    <div class="resultado-label">VALOR DA COLETA</div>
                    <div class="resultado-valor">{moeda(valor_final)}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.caption(
                f"Coleta nº {numero_coleta} • {nome} • "
                f"{cep_coleta} • {km:.1f} km informados • {tipo_veiculo}"
            )

st.divider()
st.caption(
    "Uso interno. Em situações fora dos limites apresentados pelo sistema, consulte a supervisão."
)
