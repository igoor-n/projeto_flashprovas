import streamlit as st
import google.generativeai as genai
import os
from dotenv import load_dotenv
import json
import io
import re
import random
import time

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak
import PyPDF2
from docx import Document

# Carregar variáveis de ambiente
load_dotenv()

# Configurar API do Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key and api_key != "your_api_key_here":
    genai.configure(api_key=api_key)

st.set_page_config(page_title="FlashProvas", page_icon="🎓", layout="wide")

# Ocultar o branding do Streamlit na interface pública
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def extract_text_from_file(uploaded_file):
    text = ""
    try:
        if uploaded_file.name.endswith('.pdf'):
            reader = PyPDF2.PdfReader(uploaded_file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif uploaded_file.name.endswith('.docx'):
            doc = Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif uploaded_file.name.endswith('.txt'):
            text = uploaded_file.getvalue().decode("utf-8")
    except Exception as e:
        st.error(f"Erro ao ler arquivo {uploaded_file.name}: {e}")
    return text

def generate_questions(theme, q_easy, v_easy, q_medium, v_medium, q_hard, v_hard):
    prompt = f"""
    Atue como um professor especialista na criação de questões para provas de múltipla escolha.
    O tema ou texto base é:
    {theme}
    
    Você deve gerar exatamente o seguinte número de questões:
    - {q_easy} questões de nível Fácil (cada uma valendo {v_easy} pontos)
    - {q_medium} questões de nível Médio (cada uma valendo {v_medium} pontos)
    - {q_hard} questões de nível Difícil (cada uma valendo {v_hard} pontos)
    
    Cada questão deve ter exatas 5 alternativas de A a E.
    
    ATENÇÃO: Retorne APENAS um JSON estrito obedecendo a estrutura abaixo. Não adicione crases, blocos markdown, textos antes ou depois. Se não houver questões solicitadas para um nível, basta não incluí-las.
    EXEMPLO DO JSON DE SAÍDA:
    {{
      "questions": [
        {{
          "level": "Fácil",
          "value": 1.0,
          "text": "Texto da questão",
          "options": ["A) Opção", "B) Opção", "C) Opção", "D) Opção", "E) Opção"],
          "answer": "A) Opção"
        }}
      ]
    }}
    """
    
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Tentativa de extrair apenas o objeto JSON caso a IA inclua marcação markdown
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
            
        data = json.loads(response_text)
        return data.get("questions", [])
    except json.JSONDecodeError as e:
        st.error(f"Erro ao decodificar o JSON gerado pela IA. Detalhes: {e}\n\nResposta bruta da IA:\n{response.text}")
        return None
    except Exception as e:
        st.error(f"Erro ao processar a resposta da IA (verifique se o conteúdo base não é muito longo ou se a API retornou erro). Detalhes: {str(e)}")
        return None

def create_pdf(questions, school_name="", teacher_name="", subject_name="", include_answers=True):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = styles["Heading1"]
    title_style.alignment = 1 # Centro
    
    header_style = ParagraphStyle('Header', parent=styles['Normal'], spaceAfter=12)
    question_style = ParagraphStyle('Question', parent=styles['Normal'], spaceAfter=6, fontName='Helvetica-Bold')
    option_style = ParagraphStyle('Option', parent=styles['Normal'], leftIndent=20, spaceAfter=4)
    answer_style = ParagraphStyle('Answer', parent=styles['Normal'], spaceAfter=4, fontName='Helvetica-Bold')
    
    story = []
    
    # Cabeçalho
    title = school_name if school_name.strip() else "Avaliação"
    story.append(Paragraph(f"<b>{title}</b>", title_style))
    story.append(Spacer(1, 0.5*cm))
    
    teacher_str = f"<b>Professor(a):</b> {teacher_name}" if teacher_name else "<b>Professor(a):</b> _________________"
    subject_str = f"<b>Disciplina:</b> {subject_name}" if subject_name else "<b>Disciplina:</b> ___________________"
    
    story.append(Paragraph(f"{teacher_str} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {subject_str}", header_style))
    story.append(Paragraph("<b>Nome do Aluno:</b> ____________________________________________________", header_style))
    story.append(Paragraph("<b>Data:</b> ___/___/_______   <b>Turma:</b> __________   <b>Nota Final:</b> _______", header_style))
    story.append(Spacer(1, 1*cm))
    
    if not questions:
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    # Questões
    for i, q in enumerate(questions):
        q_text = f"{i+1}. [{q.get('value', 0.0)} ponto(s)] - {q.get('text', '')}"
        story.append(Paragraph(q_text, question_style))
        
        for opt in q.get('options', []):
            story.append(Paragraph(opt, option_style))
            
        story.append(Spacer(1, 0.5*cm))
        
    # Gabarito
    if include_answers:
        story.append(PageBreak())
        
        story.append(Paragraph("<b>Gabarito</b>", title_style))
        story.append(Spacer(1, 0.5*cm))
        
        for i, q in enumerate(questions):
            ans_text = f"Questão {i+1}: {q.get('answer', '')}"
            story.append(Paragraph(ans_text, answer_style))
            
    doc.build(story)
    buffer.seek(0)
    return buffer

def main():
    st.title("🎓 FlashProvas")
    st.markdown("Crie simulados e provas personalizadas com a ajuda da IA.")
    
    if not api_key or api_key == "your_api_key_here":
        st.error("⚠️ Chave da API do Gemini não configurada corretamente no seu .env.")
        st.stop()
        
    st.header("1. Informações do Cabeçalho")
    col_cab1, col_cab2, col_cab3 = st.columns(3)
    with col_cab1:
        school_name = st.text_input("Instituição de Ensino *", placeholder="Ex: Escola FlashProvas")
    with col_cab2:
        teacher_name = st.text_input("Professor(a) *", placeholder="Seu nome")
    with col_cab3:
        subject_name = st.text_input("Disciplina *", placeholder="Ex: História")
        
    st.header("2. Conteúdo Base do Professor")
    st.markdown("Você pode colar o texto da prova OU enviar arquivos base (PDF, DOCX, TXT):")
    
    # File Uploader
    uploaded_files = st.file_uploader("📥 Envie arquivos base para gerar as questões (Opcional)", type=['pdf', 'docx', 'txt'], accept_multiple_files=True)
    
    # Extract text from files if any
    file_content = ""
    if uploaded_files:
        for file in uploaded_files:
            extracted = extract_text_from_file(file)
            if extracted:
                file_content += f"\n\n--- Conteúdo do arquivo {file.name} ---\n{extracted}\n"
    
    # Text input
    typed_theme = st.text_area("✍️ Insira o assunto ou texto base da prova:", height=150)
    
    # Combine texts
    theme = f"{file_content}\n\n{typed_theme}".strip()
    
    st.header("3. Configuração de Questões")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("🟢 Fácil")
        q_easy = st.number_input("Quantidade (Fácil)", min_value=0, value=2, step=1)
        v_easy = st.number_input("Valor (Fácil)", min_value=0.0, value=1.0, step=0.5, format="%.1f")
        
    with col2:
        st.subheader("🟡 Nível Médio")
        q_medium = st.number_input("Quantidade (Médio)", min_value=0, value=2, step=1)
        v_medium = st.number_input("Valor (Médio)", min_value=0.0, value=1.5, step=0.5, format="%.1f")
        
    with col3:
        st.subheader("🔴 Difícil")
        q_hard = st.number_input("Quantidade (Difícil)", min_value=0, value=1, step=1)
        v_hard = st.number_input("Valor (Difícil)", min_value=0.0, value=2.0, step=0.5, format="%.1f")
        
    total_questions = q_easy + q_medium + q_hard
    total_score = (q_easy * v_easy) + (q_medium * v_medium) + (q_hard * v_hard)
    
    st.subheader("📊 Resumo da Avaliação")
    metric_col1, metric_col2 = st.columns(2)
    with metric_col1:
        st.metric(label="Total de Questões", value=total_questions)
    with metric_col2:
        st.metric(label="Total de Pontos da Prova", value=f"{total_score:.1f}")
    
    if st.button("🚀 Gerar Questões", type="primary", disabled=(total_questions == 0)):
        if not school_name.strip() or not teacher_name.strip() or not subject_name.strip():
            st.warning("⚠️ Por favor, preencha todas as informações obrigatórias do Cabeçalho (Instituição, Professor e Disciplina).")
            return
            
        if not theme:
            st.warning("⚠️ Por favor, insira o tema, texto base ou envie um arquivo para a prova.")
            return
            
        with st.spinner(f"Processando {total_questions} questões com IA... Isso pode levar alguns segundos."):
            questions = generate_questions(theme, q_easy, v_easy, q_medium, v_medium, q_hard, v_hard)
            
            if questions:
                random.shuffle(questions)
                st.session_state['questions'] = questions
                
                msg = st.empty()
                msg.success("🎉 Questões geradas com sucesso!")
                time.sleep(4)
                msg.empty()
                
    if 'questions' in st.session_state and st.session_state['questions']:
        st.header("4. Revisar e Editar Questões")
        st.markdown("Você pode editar os textos das questões e alternativas abaixo antes de gerar o PDF.")
        
        for i, q in enumerate(st.session_state['questions']):
            with st.expander(f"✏️ Questão {i+1} ({q.get('level', '')}) - {q.get('value', 0.0)} ponto(s)"):
                q['text'] = st.text_area("Enunciado", value=q.get('text', ''), key=f"q_{i}_text", height=100)
                q['value'] = st.number_input("Valor da Questão", value=float(q.get('value', 0.0)), key=f"q_{i}_val", step=0.5)
                
                st.markdown("**Alternativas:**")
                options = q.get('options', [])
                if len(options) < 5:
                    options.extend([""] * (5 - len(options)))
                    
                for j in range(5):
                    # Forçar prefixo se não existir para ficar bonito no PDF
                    prefix = f"{chr(65+j)}) "
                    opt_val = options[j].strip()
                    if not opt_val.startswith(prefix):
                        opt_val = prefix + opt_val.lstrip('ABCDE) .')
                    options[j] = st.text_input(f"Alternativa {chr(65+j)}", value=opt_val, key=f"q_{i}_opt_{j}")
                q['options'] = options
                
                # Selecionar Gabarito (Letra)
                valid_options = ["A", "B", "C", "D", "E"]
                current_ans = str(q.get('answer', 'A')).strip().upper()
                current_letter = current_ans[0] if current_ans and current_ans[0] in valid_options else "A"
                ans_idx = valid_options.index(current_letter)
                
                sel_ans = st.selectbox("Gabarito Correto", valid_options, index=ans_idx, key=f"q_{i}_ans_sel")
                q['answer'] = sel_ans
                
        st.header("5. Exportação")
        st.markdown("Escolha a versão que deseja baixar:")
            
        pdf_prova = create_pdf(st.session_state['questions'], school_name, teacher_name, subject_name, include_answers=False)
        pdf_gabarito = create_pdf(st.session_state['questions'], school_name, teacher_name, subject_name, include_answers=True)
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.download_button(
                label="📄 Baixar APENAS A PROVA",
                data=pdf_prova,
                file_name="flashprovas_alunos.pdf",
                mime="application/pdf"
            )
        with col_btn2:
            st.download_button(
                label="📝 Baixar PROVA + GABARITO",
                data=pdf_gabarito,
                file_name="flashprovas_professor.pdf",
                mime="application/pdf"
            )
            
    # Rodapé de Suporte
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; margin-top: 40px; color: gray; font-size: 14px;'>"
        "Suporte exclusivo via área de membros Kiwify"
        "</div>", 
        unsafe_allow_html=True
    )
        
if __name__ == "__main__":
    main()
