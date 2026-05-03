import streamlit as st
import tempfile
import camelot
from openai import OpenAI

# ========== 页面配置 ==========
st.set_page_config(page_title="循证医学智能体 V2", layout="wide")
st.markdown("<br><br>", unsafe_allow_html=True)

st.markdown(
    "<h1 style='text-align: center;'>循证医学智能体 V2</h1>",
    unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)

# ========== Sidebar ==========
st.sidebar.header("⚙️ 配置")

api_key = st.sidebar.text_input("输入 API Key", type="password")

model_option = st.sidebar.selectbox(
    "选择大模型",
    [
        "hunyuan-free",
        "hunyuan-v1",
        "deepseek-chat",
        "deepseek-reasoner",
        "gpt-4o-mini",
        "gpt-4o",
    ]
)

base_url_option = st.sidebar.selectbox(
    "选择接口",
    [
        "https://api.hunyuan.cloud.tencent.com/v1",
        "https://api.deepseek.com",
        "https://api.openai.com/v1"
    ]
)

# ========== 主界面 ==========
st.markdown("### 📄 文献上传")

uploaded_file = st.file_uploader(
    "上传医学PDF（支持表格内容分析、表格提取）",
    type="pdf",
    help="建议上传带表格的论文，如Baseline Table / Outcome Table"
)

st.markdown("<br><br><br><br>", unsafe_allow_html=True)

question = st.text_input("❓ 输入你感兴趣的问题", placeholder="例如：提取临床试验表格中的关键数据")


# ========== 工具函数 ==========
def extract_tables_from_pdf(file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file.getvalue())
        tmp_path = tmp_file.name

    tables = camelot.read_pdf(tmp_path, flavor='stream', pages='all')

    tables_text = ""

    for table in tables:
        df = table.df

        # 简单过滤垃圾表
        if df.shape[1] > 2:
            tables_text += df.to_markdown(index=False) + "\n\n"

    return tables_text


def build_prompt(question, tables_text):
    return f"""
你是一个医学分析助手。

请根据以下文献表格数据回答问题。

【问题】
{question}

【表格数据】
{tables_text}

请输出：
1. 关键数据总结
2. 与问题直接相关的结论
3. 如有必要，指出数据不足
"""


def call_llm(api_key, base_url, model, prompt):
    if model == 'hunyuan-free':
        api_key = 'sk-xT4H5qIik5ua5jAFMVwSB06vnGT6RzmXxJK8eFP9EDzw13L2'
        base_url="https://api.hunyuan.cloud.tencent.com/v1"
        model = "hunyuan-turbos-latest"
    client = OpenAI(api_key=api_key, base_url=base_url)

    print("")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    return resp.choices[0].message.content


# ========== 主逻辑 ==========
if uploaded_file and question:
    # if not api_key:
        # st.warning("⚠️ 请先输入 API Key")
        # st.stop()

    with st.spinner("🔍 正在解析表格 + 调用大模型..."):
        try:
            tables_text = extract_tables_from_pdf(uploaded_file)

            if not tables_text.strip():
                st.error("❌ 未检测到有效表格（可能是扫描PDF）")
                st.stop()

            prompt = build_prompt(question, tables_text)

            answer = call_llm(api_key, base_url_option, model_option, prompt)

            st.subheader("📊 分析结果")
            st.write(answer)

            with st.expander("📄 查看提取的表格"):
                st.markdown(tables_text)

            # with st.expander("🧠 Prompt（调试用）"):
            #     st.code(prompt)

        except Exception as e:
            st.error(f"❌ 出错了: {e}")