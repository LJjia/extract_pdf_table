import streamlit as st
import tempfile
import camelot
from openai import OpenAI
import os
import logging

logging.basicConfig(

    filename="app.log",

    level=logging.INFO,

    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)

# ========== 页面配置 ==========
st.set_page_config(page_title="循证医学智能体平台 V2", layout="wide")
st.markdown("<br><br>", unsafe_allow_html=True)

st.markdown(
    "<h1 style='text-align: center;'>循证医学智能体平台 V2</h1>",
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

uploaded_files = st.file_uploader(
    "上传医学PDF（支持表格内容分析、表格提取）",
    type="pdf",
    accept_multiple_files=True,  # 允许多文件上传
    help="建议上传带表格的论文，如Baseline Table / Outcome Table"
)
# 显示已上传的文件列表
if uploaded_files:
    st.write(f"已上传 {len(uploaded_files)} 个文件：")
    for file in uploaded_files:
        st.write(f"- {file.name}")


st.markdown("<br><br><br><br>", unsafe_allow_html=True)


question = st.text_input("❓ 输入你感兴趣的问题", placeholder="例如：提取临床试验表格中的关键数据")

# 添加分析模式选择
analysis_mode = st.radio(
    "分析模式",
    ["合并分析所有文件", "分别分析每个文件"],
    help="合并分析：将所有文件内容合并后统一分析；分别分析：对每个文件独立分析"
)

st.markdown("<br>", unsafe_allow_html=True)

# show_prompt = st.checkbox("显示Prompt")
# if show_prompt:
#     st.subheader("Prompt预览")
#     st.code(prompt, language="text")
# with st.expander("查看完整Prompt"):
#     st.code(prompt)

# ========== 工具函数 ==========
def extract_tables_from_pdf(file):
    """从单个PDF文件中提取表格"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file.getvalue())
        tmp_path = tmp_file.name

    try:
        tables = camelot.read_pdf(tmp_path, flavor='stream', pages='all')
        
        tables_text = ""
        for table in tables:
            df = table.df
            # 简单过滤垃圾表
            if df.shape[1] > 2:
                tables_text += df.to_markdown(index=False) + "\n\n"
        
        return tables_text, file.name
    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def extract_tables_from_multiple_pdfs(files):
    """从多个PDF文件中提取表格"""
    all_tables = {}
    total_tables = 0
    
    for file in files:
        with st.spinner(f"正在解析 {file.name}..."):
            tables_text, filename = extract_tables_from_pdf(file)
            all_tables[filename] = tables_text
            
            # 统计表格数量
            table_count = len(tables_text.split('\n\n')) - 1
            total_tables += table_count
            
    return all_tables, total_tables

def build_prompt_for_multiple(question, tables_dict):
    """为多个文件构建prompt"""
    combined_text = ""
    
    for filename, tables_text in tables_dict.items():
        if tables_text.strip():
            combined_text += f"\n\n{tables_text}"
    
    return f"""
你是一个医学分析助手。

请根据以下多个文献的表格数据回答问题。

【问题】
{question}

【文献表格数据】
{combined_text}

请输出：
1. 关键数据总结（按文献分别总结）
2. 与问题直接相关的结论
3. 不同文献数据之间的比较分析（如适用）
4. 如有必要，指出数据不足
"""

def build_prompt_for_single(question, tables_text, filename):
    """为单个文件构建prompt"""
    return f"""
你是一个医学分析助手。

请根据以下文献表格数据回答问题。

【问题】
{question}

【文献来源】
{filename}

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
        base_url = "https://api.hunyuan.cloud.tencent.com/v1"
        model = "hunyuan-turbos-latest"
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    logger.info("调用大模型...")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    
    return resp.choices[0].message.content

def pdf_statistics(file):

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:

        tmp.write(file.getvalue())

        path = tmp.name

    doc = fitz.open(path)

    stats = {
        "pages": len(doc),
        "title": doc.metadata.get("title"),
        "author": doc.metadata.get("author"),
        "producer": doc.metadata.get("producer")
    }

    doc.close()

    os.remove(path)

    return stats


# ========== 主逻辑 ==========
if uploaded_files and question:
    with st.spinner("🔍 正在解析所有PDF的表格..."):
        try:
            # 提取所有文件的表格
            all_tables, total_tables = extract_tables_from_multiple_pdfs(uploaded_files)
            
            # 检查是否有有效表格
            valid_files = {name: text for name, text in all_tables.items() if text.strip()}
            
            if not valid_files:
                st.error("❌ 所有文件均未检测到有效表格（可能是扫描PDF）")
                st.stop()
            
            st.success(f"✅ 成功从 {len(valid_files)} 个文件中提取到表格（共约 {total_tables} 个表格）")

            if analysis_mode == "合并分析所有文件":
                # 合并分析模式
                with st.spinner("🧠 正在调用大模型进行综合分析..."):
                    prompt = build_prompt_for_multiple(question, valid_files)
                    logger.info(f"==============prompt is=========== \n\n\n\n {prompt}")
                    answer = call_llm(api_key, base_url_option, model_option, prompt)
                    
                    st.subheader("📊 综合分析结果")
                    st.write(answer)
                    
                    # 显示所有提取的表格
                    with st.expander("📄 查看所有提取的表格"):
                        for filename, tables_text in valid_files.items():
                            st.markdown(f"### 📄 {filename}")
                            st.markdown(tables_text)
                            st.markdown("---")
            
            else:
                # 分别分析模式
                st.subheader("📊 各文件分析结果")
                
                # 使用tab分别显示每个文件的分析结果
                file_tabs = st.tabs(list(valid_files.keys()))
                
                for tab, (filename, tables_text) in zip(file_tabs, valid_files.items()):
                    with tab:
                        with st.spinner(f"正在分析 {filename}..."):
                            prompt = build_prompt_for_single(question, tables_text, filename)
                            answer = call_llm(api_key, base_url_option, model_option, prompt)
                            st.write(answer)

            if "history" not in st.session_state:
                st.session_state.history = []
            st.session_state.history.append({
                "question": question,
                "answer": answer
            })
    
            # st.sidebar.subheader("历史记录")
            # for item in st.session_state.history[::-1]:
            #     with st.sidebar.expander(item["question"]):
            #         st.write(item["answer"])
    
            # with st.expander(f"📄 查看 {filename} 的原始表格"):
            #     st.markdown(tables_text)

            # st.download_button(
            #         "下载分析结果",
            #         answer,
            #         file_name="analysis.md",
            #         mime="text/markdown"
            #     )
            
            
        except Exception as e:
            st.error(f"❌ 出错了: {e}")
    
elif not uploaded_files:
    st.info("👆 请上传PDF文件开始分析")
elif not question:
    st.info("❓ 请输入您感兴趣的问题")
