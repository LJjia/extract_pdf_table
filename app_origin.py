import streamlit as st
import tempfile
from openai import OpenAI
import camelot

# 这里填入你自己的 OpenAI API key
client = OpenAI(
    api_key='sk-xT4H5qIik5ua5jAFMVwSB06vnGT6RzmXxJK8eFP9EDzw13L2',
    base_url="https://api.hunyuan.cloud.tencent.com/v1",  # 混元 endpoint
    )

st.title("📄循证医学智能体V2")

uploaded_file = st.file_uploader("上传 PDF", type="pdf")
question = st.text_input("输入你的问题，例如：提取临床数据中的表格信息")

if uploaded_file and question:
    # 尝试提取所有表格，使用 lattice 模式（适合有框线的表格，常见于论文）
    # 使用临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name
    tables = camelot.read_pdf(tmp_path, flavor='stream', pages='all')
    print(f"read table num {len(tables)}")
    # 将所有表格数据转换为文本格式，供LLM使用
    tables_text = ""
    for i, table in enumerate(tables):
        # # 获取表格的DataFrame
        df = table.df
        # # fliter text info
        if(len(df.shape) >= 2 and df.shape[1] > 2):
            # print(f"table {i} table {df.to_string(index=False, header=True)}")
            # tables_text += df.to_string(index=False, header=True)
            tables_text += df.to_markdown(index=False)
    # print(tables_text)
    # 调用 LLM 提取答案
    prompt = f"""
    {question}，参考以下文献：
    {tables_text}
    """
    print(f"token len {len(prompt)}")
    # 新的API调用方式
    resp = client.chat.completions.create(
        model="hunyuan-turbos-latest",
        messages=[{"role":"user", "content": prompt}]
    )
    st.subheader("📊 答案：")

    st.write(resp.choices[0].message.content)
