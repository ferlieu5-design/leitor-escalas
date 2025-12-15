import streamlit as st
import easyocr
import re
import numpy as np
from PIL import Image

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Leitor de Escalas", page_icon="🚚", layout="wide")

# --- CARREGAMENTO DA IA (CACHE) ---
# O @st.cache_resource faz a IA carregar só uma vez, para o site ficar rápido
@st.cache_resource
def carregar_ia():
    try:
        return easyocr.Reader(['pt'], gpu=False)
    except Exception as e:
        st.error(f"Erro ao carregar IA: {e}")
        return None

reader = carregar_ia()

# --- FUNÇÕES DE LÓGICA (V17) ---
def formatar_placa(placa):
    if not placa: return ""
    placa = re.sub(r'[^A-Z0-9]', '', placa.upper())
    if len(placa) >= 7:
        return f"{placa[:3]}-{placa[3:]}"
    return placa

def identificar_destino(texto):
    matches = re.findall(r'\b(SP|RJ|MG|BA|PR|SC|RS|GO|MT|MS|ES|PB|DF)\b', texto.upper())
    estado = matches[-1] if matches else "XX"
    num = re.search(r'\b(\d)\b', texto)
    numero = num.group(1) if num else "1"
    return f"{estado} {numero}"

def limpar_sujeira_nome(texto):
    return re.sub(r'[^A-Z\sÁÉÍÓÚÃÕÂÊÎÔÛÇ]', '', texto.upper()).strip()

def agrupar_por_linhas(resultados, tolerancia_y=20):
    if not resultados: return []
    resultados_ordenados = sorted(resultados, key=lambda x: x[0][0][1])
    linhas = []
    linha_atual = [resultados_ordenados[0]]
    y_atual = resultados_ordenados[0][0][0][1]

    for i in range(1, len(resultados_ordenados)):
        item = resultados_ordenados[i]
        y_item = item[0][0][1]
        if abs(y_item - y_atual) <= tolerancia_y:
            linha_atual.append(item)
        else:
            linha_atual.sort(key=lambda x: x[0][0][0])
            linhas.append(linha_atual)
            linha_atual = [item]
            y_atual = y_item
    linha_atual.sort(key=lambda x: x[0][0][0])
    linhas.append(linha_atual)
    return linhas

def processar_imagem(imagem_upload):
    # Converte imagem do Streamlit para formato que o EasyOCR aceita (numpy)
    imagem = Image.open(imagem_upload)
    imagem_np = np.array(imagem)

    dados_brutos = reader.readtext(imagem_np, detail=1, paragraph=False)
    tabela = agrupar_por_linhas(dados_brutos)
    
    saida_formatada = []
    qtd_motoristas = 0

    for linha in tabela:
        tokens = [item[1] for item in linha]
        texto_completo = " ".join(tokens).upper()
        
        if "TERÇA" in texto_completo or "SAÍDA" in texto_completo or "ORIG" in texto_completo:
            continue
        
        # 1. REMOVER PLACAS
        regex_placa = r'[A-Z]{3}\d[A-Z0-9]\d{2}|[A-Z]{3}\d{4}'
        placas_encontradas = re.findall(regex_placa, texto_completo.replace("-", ""))
        
        cavalo = placas_encontradas[0] if len(placas_encontradas) > 0 else "???"
        carreta = placas_encontradas[1] if len(placas_encontradas) > 1 else None
        
        texto_sem_placas = re.sub(regex_placa, '', texto_completo.replace("-", ""))

        # 2. REMOVER NUMEROS
        numeros_encontrados = re.findall(r'\d{5,}', texto_sem_placas)
        cnh = "Desconhecida"
        cpf = "Desconhecido"
        rg = "Desconhecido"
        
        candidatos_cpf = [n for n in numeros_encontrados if len(n) == 11]
        if candidatos_cpf:
            cpf = candidatos_cpf[-1]
            if cpf in numeros_encontrados: numeros_encontrados.remove(cpf)
        
        candidatos_cnh = [n for n in numeros_encontrados if len(n) >= 9]
        if candidatos_cnh:
            cnh = candidatos_cnh[0]
            if cnh in numeros_encontrados: numeros_encontrados.remove(cnh)
            
        if numeros_encontrados:
            rg = numeros_encontrados[0]

        # 3. NOME
        texto_limpo = texto_sem_placas
        for n in [cpf, cnh, rg]:
            if n != "Desconhecido" and n != "Desconhecida":
                texto_limpo = texto_limpo.replace(n, "")
        
        texto_limpo = re.sub(r'\b(SP|RJ|MG|BA|PR|SC|RS|GO|MT|MS|ES|PB|DF|CAJAMAR|PAVUNA|RIBEIRÃO|UBERLÂNDIA)\b', '', texto_limpo)
        texto_limpo = re.sub(r'\d+', '', texto_limpo)
        
        nome_candidato = limpar_sujeira_nome(texto_limpo)
        palavras_nome = nome_candidato.split()
        palavras_nome = [p for p in palavras_nome if len(p) > 1]
        
        nome = "NOME NÃO IDENTIFICADO"
        if palavras_nome:
            if len(palavras_nome) >= 2:
                nome = f"{palavras_nome[0]} {palavras_nome[1]}"
            else:
                nome = palavras_nome[0]

        if nome == "NOME NÃO IDENTIFICADO" and cavalo == "???":
            continue

        destino_code = identificar_destino(texto_completo)

        # MONTAGEM
        bloco = [
            "FSJ",
            destino_code,
            f"MOT: {nome}",
            f"CPF:{cpf}",
            f"CNH:{cnh}",
            f"RG:{rg}"
        ]

        if carreta:
            bloco.append(f"CAVALO:{formatar_placa(cavalo)}")
            bloco.append(f"CARRETA:{formatar_placa(carreta)}")
        else:
            bloco.append(f"TRUCK:{formatar_placa(cavalo)}")

        saida_formatada.append("\n".join(bloco) + "\n\n")
        qtd_motoristas += 1

    return "".join(saida_formatada), qtd_motoristas

# --- INTERFACE DO SITE ---
st.title("Extrator de Escalas 🚚")
st.markdown("**Versão Web Inteligente (V17)**")

col1, col2 = st.columns([1, 2])

with col1:
    st.info("Faça o upload da foto da escala abaixo.")
    arquivo = st.file_uploader("Escolher imagem", type=["png", "jpg", "jpeg"])
    
    if arquivo:
        st.image(arquivo, caption="Imagem Carregada", use_column_width=True)
        
        if st.button("PROCESSAR ESCALA", type="primary"):
            if reader:
                with st.spinner("Lendo com Inteligência Artificial..."):
                    try:
                        texto_final, qtd = processar_imagem(arquivo)
                        if qtd > 0:
                            st.success(f"Sucesso! {qtd} motoristas identificados.")
                            st.session_state['resultado'] = texto_final
                        else:
                            st.warning("Nenhum dado encontrado na imagem.")
                    except Exception as e:
                        st.error(f"Erro ao processar: {e}")

with col2:
    st.subheader("Resultado:")
    if 'resultado' in st.session_state:
        # Área de texto grande para copiar
        st.text_area("Dados Extraídos (Copie daqui):", value=st.session_state['resultado'], height=600)
    else:
        st.text_area("O resultado aparecerá aqui...", height=600, disabled=True)

st.markdown("---")
st.caption("Desenvolvido por **Bruno.R**")