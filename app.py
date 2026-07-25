import streamlit as st
import tempfile
import camelot
from openai import OpenAI
import os
import logging
import time

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

###### unuse func #####
class MedicalTableAnalyzer:
    """医学表格智能分析器"""
    
    def __init__(self):
        self.clinical_patterns = {
            'baseline': r'(baseline|baseline characteristics|demographic)',
            'outcome': r'(outcome|endpoint|efficacy|result)',
            'safety': r'(adverse event|safety|side effect|toxicity)',
            'survival': r'(survival|kaplan|hazard ratio|overall survival)',
            'subgroup': r'(subgroup|stratified|subpopulation)'
        }
    
    def classify_table_type(self, table_text):
        """自动分类表格类型"""
        table_text_lower = table_text.lower()
        scores = {}
        
        for table_type, pattern in self.clinical_patterns.items():
            matches = re.findall(pattern, table_text_lower)
            scores[table_type] = len(matches)
        
        if max(scores.values()) == 0:
            return "unknown"
        
        return max(scores, key=scores.get)
    
    def extract_statistical_measures(self, table_df):
        """提取统计指标"""
        measures = {
            'p_values': [],
            'confidence_intervals': [],
            'odds_ratios': [],
            'hazard_ratios': [],
            'mean_values': [],
            'sd_values': []
        }
        
        # 查找p值
        p_pattern = r'[pP]\s*[<>=]\s*(\d+\.?\d*)'
        for col in table_df.columns:
            for cell in table_df[col].astype(str):
                matches = re.findall(p_pattern, str(cell))
                measures['p_values'].extend([float(m) for m in matches])
        
        # 查找置信区间
        ci_pattern = r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)'
        for col in table_df.columns:
            for cell in table_df[col].astype(str):
                matches = re.findall(ci_pattern, str(cell))
                measures['confidence_intervals'].extend(matches)
        
        return measures
    
    def check_data_consistency(self, tables_data):
        """检查表格数据一致性"""
        consistency_report = {
            'issues': [],
            'warnings': [],
            'suggestions': []
        }
        
        # 检查样本量一致性
        sample_sizes = []
        for table_text in tables_data.values():
            n_pattern = r'[nN]\s*=\s*(\d+)'
            matches = re.findall(n_pattern, table_text)
            if matches:
                sample_sizes.append(int(matches[0]))
        
        if len(set(sample_sizes)) > 1:
            consistency_report['warnings'].append(
                f"检测到不同的样本量: {set(sample_sizes)}，请检查数据一致性"
            )
        
        # 检查百分比总和
        percentage_pattern = r'(\d+\.?\d*)\s*%'
        for table_text in tables_data.values():
            percentages = re.findall(percentage_pattern, table_text)
            if percentages:
                total = sum(float(p) for p in percentages[:10])  # 检查前10个
                if abs(total - 100) > 5:  # 允许5%的误差
                    consistency_report['issues'].append(
                        f"检测到百分比总和异常: {total:.1f}%"
                    )
        
        return consistency_report

class EvidenceQualityAssessor:
    """循证医学证据质量评估"""
    
    def __init__(self):
        self.evidence_levels = {
            '1a': '系统评价/Meta分析（同质RCT）',
            '1b': '单个RCT（可信区间窄）',
            '1c': '全或无病例系列',
            '2a': '同质队列研究的系统评价',
            '2b': '单个队列研究/低质量RCT',
            '2c': '结局研究/生态学研究',
            '3a': '同质病例对照研究的系统评价',
            '3b': '单个病例对照研究',
            '4': '病例系列/低质量队列和病例对照研究',
            '5': '专家意见/基础研究'
        }
        
        self.quality_criteria = {
            'randomization': False,
            'blinding': False,
            'allocation_concealment': False,
            'follow_up_complete': False,
            'intention_to_treat': False,
            'sample_size_adequate': False
        }
    
    def assess_study_design(self, text):
        """评估研究设计类型"""
        design_patterns = {
            'systematic_review': r'(systematic review|meta.analysis|荟萃分析|系统评价)',
            'rct': r'(randomized|RCT|随机对照|randomly assigned)',
            'cohort': r'(cohort|队列|prospective|前瞻性)',
            'case_control': r'(case.control|病例对照|retrospective|回顾性)',
            'cross_sectional': r'(cross.sectional|横断面)',
            'case_series': r'(case series|病例系列|case report|病例报告)'
        }
        
        scores = {}
        text_lower = text.lower()
        
        for design, pattern in design_patterns.items():
            matches = re.findall(pattern, text_lower)
            scores[design] = len(matches)
        
        if max(scores.values()) == 0:
            return 'unknown'
        
        return max(scores, key=scores.get)
    
    def calculate_quality_score(self, text, study_design):
        """计算研究质量评分"""
        score = 0
        max_score = 100
        
        # 研究设计基础分
        design_scores = {
            'systematic_review': 80,
            'rct': 70,
            'cohort': 50,
            'case_control': 30,
            'cross_sectional': 20,
            'case_series': 10
        }
        
        score = design_scores.get(study_design, 0)
        
        # 质量指标加分
        if re.search(r'(randomization|随机分组)', text, re.IGNORECASE):
            score += 10
        if re.search(r'(double.blind|双盲|blinding)', text, re.IGNORECASE):
            score += 5
        if re.search(r'(allocation concealment|分配隐藏)', text, re.IGNORECASE):
            score += 5
        if re.search(r'(intention.to.treat|ITT|意向性分析)', text, re.IGNORECASE):
            score += 5
        if re.search(r'(sample size calculation|样本量计算|power)', text, re.IGNORECASE):
            score += 5
        
        # 确保不超过最大值
        score = min(score, max_score)
        
        return score
    
    def get_recommendation_grade(self, quality_score):
        """根据质量评分给出推荐等级"""
        if quality_score >= 80:
            return 'A', '强烈推荐（高质量证据）'
        elif quality_score >= 60:
            return 'B', '推荐（中等质量证据）'
        elif quality_score >= 40:
            return 'C', '可以考虑（低质量证据）'
        else:
            return 'D', '不推荐（极低质量证据）'

class MedicalDataVisualizer:
    """医学数据可视化"""
    
    def create_forest_plot(self, data_dict):
        """创建森林图"""
        studies = data_dict.get('studies', [])
        or_values = data_dict.get('or_values', [])
        ci_lower = data_dict.get('ci_lower', [])
        ci_upper = data_dict.get('ci_upper', [])
        
        fig = go.Figure()
        
        # 添加效应量和置信区间
        fig.add_trace(go.Scatter(
            x=or_values,
            y=studies,
            mode='markers',
            marker=dict(size=12, color='blue'),
            name='OR/HR',
            error_x=dict(
                type='data',
                symmetric=False,
                array=[u - o for u, o in zip(ci_upper, or_values)],
                arrayminus=[o - l for o, l in zip(or_values, ci_lower)]
            )
        ))
        
        # 添加无效线
        fig.add_vline(x=1, line_dash="dash", line_color="red", annotation_text="无效线")
        
        fig.update_layout(
            title="森林图 (Forest Plot)",
            xaxis_title="效应量 (OR/HR)",
            yaxis_title="研究",
            height=400,
            showlegend=False
        )
        
        return fig
    
    def create_survival_curve(self, time_points, survival_probs, groups):
        """创建生存曲线"""
        fig = go.Figure()
        
        for group, probs in zip(groups, survival_probs):
            fig.add_trace(go.Scatter(
                x=time_points,
                y=probs,
                mode='lines+markers',
                name=group,
                line=dict(width=2)
            ))
        
        fig.update_layout(
            title="生存曲线 (Kaplan-Meier)",
            xaxis_title="时间 (月)",
            yaxis_title="生存率",
            yaxis_range=[0, 1],
            height=400
        )
        
        return fig
    
    def create_risk_of_bias_chart(self, bias_data):
        """创建偏倚风险图"""
        domains = list(bias_data.keys())
        judgments = list(bias_data.values())
        
        # 创建交通灯图
        colors = {
            'low': 'green',
            'unclear': 'yellow',
            'high': 'red'
        }
        
        fig = go.Figure()
        
        for i, (domain, judgment) in enumerate(zip(domains, judgments)):
            fig.add_trace(go.Bar(
                x=[1],
                y=[domain],
                orientation='h',
                marker_color=colors.get(judgment, 'gray'),
                name=domain,
                text=judgment.upper(),
                textposition='inside'
            ))
        
        fig.update_layout(
            title="偏倚风险评估 (Risk of Bias)",
            xaxis_visible=False,
            height=300,
            showlegend=False
        )
        
        return fig
    
    def create_network_meta_plot(self, treatments, comparisons):
        """创建网状Meta分析图"""
        # 创建节点位置（圆形布局）
        n = len(treatments)
        angles = np.linspace(0, 2*np.pi, n, endpoint=False)
        x = np.cos(angles)
        y = np.sin(angles)
        
        fig = go.Figure()
        
        # 添加节点
        for i, (treatment, xi, yi) in enumerate(zip(treatments, x, y)):
            fig.add_trace(go.Scatter(
                x=[xi],
                y=[yi],
                mode='markers+text',
                marker=dict(size=20 + comparisons[i]*5, color='lightblue'),
                text=treatment,
                textposition='top center',
                name=treatment
            ))
        
        # 添加连接线
        for i in range(n):
            for j in range(i+1, n):
                if comparisons[i] > 0 and comparisons[j] > 0:
                    fig.add_trace(go.Scatter(
                        x=[x[i], x[j]],
                        y=[y[i], y[j]],
                        mode='lines',
                        line=dict(width=min(comparisons[i], comparisons[j]), color='gray'),
                        showlegend=False
                    ))
        
        fig.update_layout(
            title="网状Meta分析图 (Network Meta-Analysis)",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=500
        )
        
        return fig


def extract_text_from_pdf(file):
    """提取PDF文本内容（非表格部分）"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file.getvalue())
        tmp_path = tmp_file.name
    
    try:
        doc = fitz.open(tmp_path)
        text_content = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text_content.append({
                'page': page_num + 1,
                'content': text
            })
        
        doc.close()
        return text_content, tmp_path
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def extract_images_from_pdf(file):
    """提取PDF中的图片（可用于图表分析）"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file.getvalue())
        tmp_path = tmp_file.name
    
    try:
        doc = fitz.open(tmp_path)
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                images.append({
                    'page': page_num + 1,
                    'index': img_index,
                    'image': Image.open(io.BytesIO(image_bytes))
                })
        
        doc.close()
        return images
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def init_session_state():
    """初始化会话状态"""
    if 'analysis_history' not in st.session_state:
        st.session_state.analysis_history = []
    
    if 'favorite_analyses' not in st.session_state:
        st.session_state.favorite_analyses = []
    
    if 'current_analysis_id' not in st.session_state:
        st.session_state.current_analysis_id = None

def save_analysis_record(question, answer, files_info, mode, model):
    """保存分析记录"""
    record = {
        'id': datetime.now().strftime("%Y%m%d_%H%M%S"),
        'timestamp': datetime.now().isoformat(),
        'question': question,
        'answer': answer,
        'files': [f['name'] for f in files_info],
        'mode': mode,
        'model': model,
        'is_favorite': False
    }
    st.session_state.analysis_history.append(record)
    return record['id']

def export_history_to_json():
    """导出历史记录为JSON"""
    if not st.session_state.analysis_history:
        return None
    
    export_data = {
        'export_date': datetime.now().isoformat(),
        'total_records': len(st.session_state.analysis_history),
        'records': st.session_state.analysis_history
    }
    
    return json.dumps(export_data, ensure_ascii=False, indent=2)

def render_history_sidebar():
    """在侧边栏显示分析历史"""
    st.sidebar.header("📚 分析历史")
    
    if not st.session_state.analysis_history:
        st.sidebar.info("暂无分析记录")
        return
    
    # 搜索和过滤历史记录
    search_term = st.sidebar.text_input("🔍 搜索历史记录", key="history_search")
    
    filtered_history = st.session_state.analysis_history[::-1]
    if search_term:
        filtered_history = [
            h for h in filtered_history 
            if search_term.lower() in h['question'].lower() 
            or search_term.lower() in h['answer'].lower()
        ]
    
    # 显示历史记录数量
    st.sidebar.markdown(f"**共 {len(filtered_history)} 条记录**")
    
    # 导出按钮
    if st.sidebar.button("📥 导出历史记录"):
        json_data = export_history_to_json()
        if json_data:
            st.sidebar.download_button(
                "下载JSON文件",
                json_data,
                file_name=f"analysis_history_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
    
    st.sidebar.markdown("---")
    
    # 显示每条历史记录
    for item in filtered_history[:5]:  # 只显示最近5条
        with st.sidebar.expander(f"📝 {item['question'][:30]}..."):
            st.markdown(f"**时间:** {item['timestamp']}")
            st.markdown(f"**文件:** {', '.join(item['files'])}")
            st.markdown(f"**模式:** {item['mode']}")
            st.markdown(f"**模型:** {item['model']}")
            
            if st.button(f"⭐ {'取消收藏' if item['is_favorite'] else '收藏'}", key=f"fav_{item['id']}"):
                item['is_favorite'] = not item['is_favorite']
                if item['is_favorite']:
                    st.session_state.favorite_analyses.append(item)
                else:
                    st.session_state.favorite_analyses = [
                        f for f in st.session_state.favorite_analyses 
                        if f['id'] != item['id']
                    ]
                st.rerun()

def compare_model_responses(api_key, base_url, question, tables_data, models_to_test):
    """对比不同模型的回答"""
    results = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, model in enumerate(models_to_test):
        status_text.text(f"正在测试模型: {model}")
        
        start_time = time.time()
        try:
            prompt = build_prompt_for_multiple(question, tables_data)
            answer = call_llm(api_key, base_url, model, prompt)
            elapsed_time = time.time() - start_time
            
            results[model] = {
                'answer': answer,
                'time': elapsed_time,
                'success': True,
                'error': None
            }
        except Exception as e:
            results[model] = {
                'answer': None,
                'time': time.time() - start_time,
                'success': False,
                'error': str(e)
            }
        
        progress_bar.progress((i + 1) / len(models_to_test))
    
    status_text.empty()
    progress_bar.empty()
    
    return results

def render_model_comparison(results):
    """渲染模型对比结果"""
    if not results:
        return
    
    st.subheader("🤖 模型对比结果")
    
    # 性能对比表
    comparison_data = []
    for model, result in results.items():
        comparison_data.append({
            '模型': model,
            '响应时间': f"{result['time']:.2f}秒",
            '状态': '✅ 成功' if result['success'] else '❌ 失败',
            '回答长度': len(result['answer']) if result['answer'] else 0
        })
    
    if comparison_data:
        df_comparison = pd.DataFrame(comparison_data)
        st.dataframe(df_comparison, use_container_width=True)
        
        # 可视化对比
        col1, col2 = st.columns(2)
        
        with col1:
            # 响应时间柱状图
            time_data = {
                '模型': [r['模型'] for r in comparison_data],
                '响应时间(秒)': [float(r['响应时间'].replace('秒', '')) for r in comparison_data]
            }
            df_time = pd.DataFrame(time_data)
            st.bar_chart(df_time.set_index('模型'))
        
        with col2:
            # 回答长度柱状图
            length_data = {
                '模型': [r['模型'] for r in comparison_data],
                '回答长度(字符)': [r['回答长度'] for r in comparison_data]
            }
            df_length = pd.DataFrame(length_data)
            st.bar_chart(df_length.set_index('模型'))
    
    # 显示每个模型的详细回答
    st.markdown("---")
    st.subheader("📝 详细回答对比")
    
    model_tabs = st.tabs(list(results.keys()))
    for tab, (model, result) in zip(model_tabs, results.items()):
        with tab:
            if result['success']:
                st.markdown(f"**响应时间:** {result['time']:.2f}秒")
                st.markdown("**回答:**")
                st.markdown(result['answer'])
            else:
                st.error(f"**错误:** {result['error']}")

def export_results(results, format_type="markdown"):
    """支持多种格式导出结果"""
    if format_type == "markdown":
        return results
    
    elif format_type == "json":
        data = {
            "analysis_date": datetime.now().isoformat(),
            "results": results
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    elif format_type == "csv":
        # 简单CSV导出
        lines = ["Question,Answer"]
        lines.append(f'"{results.get("question", "")}","{results.get("answer", "")}"')
        return "\n".join(lines)
    
    elif format_type == "html":
        # 转换为HTML格式
        html_content = f"""
        <html>
        <head><meta charset="utf-8"><title>分析结果</title></head>
        <body>
            <h1>分析结果</h1>
            <p><strong>时间：</strong>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <div>{markdown.markdown(results)}</div>
        </body>
        </html>
        """
        return html_content

def generate_analysis_report(question, all_results, metadata_list, model_info):
    """生成综合PDF报告"""
    
    class AnalysisReport(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 12)
            self.cell(0, 10, '循证医学分析报告', 0, 1, 'C')
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(10)
        
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')
    
    pdf = AnalysisReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 添加中文字体支持（需要中文字体文件）
    # pdf.add_font('SimSun', '', 'simsun.ttf', uni=True)
    # pdf.set_font('SimSun', '', 12)
    
    # 报告头部信息
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Analysis Report', 0, 1, 'C')
    pdf.ln(10)
    
    # 基本信息
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 10, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1)
    pdf.cell(0, 10, f'Model: {model_info}', 0, 1)
    pdf.cell(0, 10, f'Question: {question}', 0, 1)
    pdf.ln(10)
    
    # 文献元数据
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Literature Metadata', 0, 1)
    pdf.set_font('Arial', '', 10)
    
    for meta in metadata_list:
        pdf.cell(0, 10, f"File: {meta.get('file_name', 'N/A')}", 0, 1)
        pdf.cell(0, 10, f"Pages: {meta.get('pages', 'N/A')}", 0, 1)
        pdf.cell(0, 10, f"Author: {meta.get('author', 'N/A')}", 0, 1)
        pdf.ln(5)
    
    # 分析结果
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Analysis Results', 0, 1)
    pdf.set_font('Arial', '', 10)
    
    for result in all_results:
        pdf.multi_cell(0, 10, result)
        pdf.ln(5)
    
    # 保存到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        tmp_path = tmp_file.name
    
    return tmp_path

def analyze_pdf_metadata(file):
    """分析PDF元数据和质量"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file.getvalue())
        tmp_path = tmp_file.name
    
    try:
        doc = fitz.open(tmp_path)
        metadata = {
            'file_name': file.name,
            'file_size': f"{file.size / 1024:.2f} KB",
            'pages': len(doc),
            'title': doc.metadata.get('title', 'N/A'),
            'author': doc.metadata.get('author', 'N/A'),
            'subject': doc.metadata.get('subject', 'N/A'),
            'keywords': doc.metadata.get('keywords', 'N/A'),
            'creation_date': doc.metadata.get('creationDate', 'N/A'),
            'has_text_layer': False,
            'has_tables': False,
            'table_count': 0
        }
        
        # 检查是否有文本层
        for page in doc:
            if page.get_text().strip():
                metadata['has_text_layer'] = True
                break
        
        doc.close()
        return metadata
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

####### used func #######
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
