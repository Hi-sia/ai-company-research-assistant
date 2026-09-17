import json
import os

import streamlit as st
from openai import OpenAI

from sec_data import build_company_snapshot
from sec_text import (
    get_filing_url,
    download_html,
    html_to_text,
    extract_mda,
    build_evidence_candidates,
)
from evidence_selector import (
    build_candidate_package,
    select_evidence,
    validate_selection,
    resolve_selected_evidence,
)


# ============================================================
# Page
# ============================================================

st.set_page_config(
    page_title="公司显微镜 · AI 公司研究助手",
    page_icon="🔎",
    layout="wide",
)


# ============================================================
# Basic helpers
# ============================================================

def format_billions(value):
    if value is None:
        return "N/A"

    return f"${value / 1_000_000_000:,.1f}B"


def format_yoy(value):
    if value is None:
        return "N/A"

    return f"{value:+.1f}% YoY"


def short_company_name(name):
    replacements = [
        " Inc.",
        " INC",
        " Corp.",
        " CORP",
        " Corporation",
        " CORPORATION",
    ]

    result = name

    for text in replacements:
        result = result.replace(text, "")

    return result.strip()


def metric_available(comparison):
    return (
        comparison is not None
        and comparison.get("current") is not None
    )


# ============================================================
# SEC financial facts
# ============================================================

@st.cache_data(ttl=3600)
def load_company_snapshot(ticker):
    return build_company_snapshot(ticker)


def build_fact_package(snapshot):
    company = snapshot["company"]
    filing = snapshot["filing"]
    metrics = snapshot["metrics"]

    package = {
        "company": company["company_name"],
        "ticker": company["ticker"],
        "source": "SEC Form 10-K",
        "report_date": filing["report_date"],
        "filing_date": filing["filing_date"],
        "metrics": {},
    }

    for metric_name, comparison in metrics.items():
        if not metric_available(comparison):
            continue

        current = comparison["current"]
        previous = comparison["previous"]

        metric_fact = {
            "current_value_usd": current["value"],
            "current_period_start": current["start"],
            "current_period_end": current["end"],
            "xbrl_concept": current["concept"],
            "yoy_percent": comparison["yoy_percent"],
        }

        if previous is not None:
            metric_fact["previous_value_usd"] = (
                previous["value"]
            )

            metric_fact["previous_period_start"] = (
                previous["start"]
            )

            metric_fact["previous_period_end"] = (
                previous["end"]
            )

        package["metrics"][metric_name] = metric_fact

    return package


# ============================================================
# SEC filing URL
# ============================================================

def build_filing_url(snapshot):
    company = snapshot["company"]
    filing = snapshot["filing"]

    cik_number = str(int(company["cik"]))

    accession_no_dashes = (
        filing["accession_number"].replace("-", "")
    )

    primary_document = filing["primary_document"]

    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_number}/"
        f"{accession_no_dashes}/"
        f"{primary_document}"
    )


# ============================================================
# MD&A evidence pipeline
# ============================================================

@st.cache_data(ttl=3600)
def load_evidence_package(ticker):
    company, filing, url = get_filing_url(ticker)

    html = download_html(url)
    text = html_to_text(html)
    mda = extract_mda(text)

    if not mda:
        raise ValueError("未能从最新 10-K 中提取 MD&A。")

    candidates = build_evidence_candidates(
        mda,
        max_per_theme=3,
    )

    candidate_package = build_candidate_package(
        candidates
    )

    return candidate_package


def run_evidence_selector(candidate_package):
    selections = select_evidence(
        candidate_package
    )

    validate_selection(
        selections,
        candidate_package,
    )

    return resolve_selected_evidence(
        selections,
        candidate_package,
    )


# ============================================================
# Grounded Interpretation
# ============================================================

SYSTEM_PROMPT = """
你是“公司显微镜”的 Grounded Financial Interpreter。

你的任务不是自由分析公司。
你的任务是把已经锁定的金融事实和已经选中的 SEC 管理层证据，
解释成普通个人投资者容易理解的中文。

你会收到两个数据源：

1. LOCKED FINANCIAL FACTS
   来自 SEC XBRL，由程序抽取和计算。

2. LOCKED MANAGEMENT EVIDENCE
   来自公司最新 10-K 的 MD&A。
   每条证据已经包含：
   - evidence_id
   - scope
   - metric_alignment
   - support
   - text

严格遵守：

1. 只能使用提供给你的两个 Locked 数据源。
2. 不得使用外部知识。
3. 不得补充新闻、竞争对手、市场份额、客户、
   行业趋势、股价、估值或其他外部事件。
4. 不得发明任何数字。
5. 不得重新计算财务指标。
6. 不得创造 Evidence ID。
7. 不得把 component 证据扩大成全公司原因。
8. support=partial 时，必须明确告诉用户：
   这只是部分证据，不能完整解释公司整体变化。
9. support=insufficient 时，不得猜原因。
   必须明确告诉用户：
   “现有 SEC 证据不足以判断具体原因。”
10. metric_alignment=related 时，
    必须说明该证据与目标指标有关，
    但不是对目标指标变化的完整直接解释。
11. 风险披露是前瞻性风险，不代表一定会发生。
12. 不得提供买入、卖出、持有、目标价或投资评级。
13. 不预测股价。
14. 使用简体中文。
15. 面向没有专业财务背景的普通用户。
16. 每部分尽量控制在 2 到 4 句话。

请只返回 JSON，不使用 Markdown 代码块。

必须严格包含：

{
  "revenue": {
    "interpretation": "...",
    "management_explanation": "...",
    "evidence_id": "P000 or null"
  },
  "profit": {
    "interpretation": "...",
    "management_explanation": "...",
    "evidence_id": "P000 or null"
  },
  "cash": {
    "interpretation": "...",
    "management_explanation": "...",
    "evidence_id": "P000 or null"
  },
  "risk": {
    "interpretation": "...",
    "management_explanation": "...",
    "evidence_id": "P000 or null"
  }
}

Revenue 对应 Revenue。

Profit 同时观察 Net Income 和 Operating Income。

Cash 对应 Operating Cash Flow。

Risk 只根据选中的 SEC 风险证据解释。

management_explanation 是“管理层披露了什么”。

interpretation 是“这对普通用户意味着什么”。

不要把 AI Interpretation 写成管理层原话。
"""


def get_ai_client():
    api_key = os.getenv("ARK_API_KEY")
    base_url = os.getenv("ARK_BASE_URL")

    if not api_key:
        raise ValueError("没有检测到 ARK_API_KEY")

    if not base_url:
        raise ValueError("没有检测到 ARK_BASE_URL")

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def generate_grounded_interpretation(
    fact_package,
    evidence_package,
):
    client = get_ai_client()

    model_name = os.getenv(
        "ARK_MODEL",
        "deepseek-v4-1-flash-260910",
    )

    locked_input = {
        "LOCKED_FINANCIAL_FACTS":
            fact_package,
        "LOCKED_MANAGEMENT_EVIDENCE":
            evidence_package,
    }

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    locked_input,
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
        temperature=0,
    )

    content = (
        response
        .choices[0]
        .message
        .content
        .strip()
    )

    if content.startswith("```json"):
        content = content[7:]

    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    result = json.loads(content.strip())

    required_keys = {
        "revenue",
        "profit",
        "cash",
        "risk",
    }

    if set(result.keys()) != required_keys:
        raise ValueError(
            "AI 返回的 Grounded Interpretation "
            "结构不正确"
        )

    evidence_map = {
        "revenue":
            evidence_package["revenue_driver"],
        "profit":
            evidence_package["profit_driver"],
        "cash":
            evidence_package["cash_driver"],
        "risk":
            evidence_package["key_risk"],
    }

    for section, evidence in evidence_map.items():
        expected_id = evidence["evidence_id"]
        returned_id = result[section].get(
            "evidence_id"
        )

        if returned_id != expected_id:
            raise ValueError(
                f"{section}: AI 返回的 Evidence ID "
                "与 Selector 不一致"
            )

    return result


# ============================================================
# Session state
# ============================================================

defaults = {
    "analysis": None,
    "analysis_ticker": None,
    "selected_evidence": None,
    "analysis_status": "尚未生成",
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_analysis():
    st.session_state.analysis = None
    st.session_state.selected_evidence = None
    st.session_state.analysis_status = (
        "尚未生成"
    )


# ============================================================
# UI helpers
# ============================================================

def show_metric(
    label,
    comparison,
):
    if not metric_available(comparison):
        st.warning("SEC 中暂未找到该指标。")
        return

    current = comparison["current"]
    previous = comparison["previous"]

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "当前财年",
            format_billions(
                current["value"]
            ),
            format_yoy(
                comparison["yoy_percent"]
            ),
        )

    with col2:
        if previous is None:
            st.metric(
                "上一财年",
                "N/A",
            )
        else:
            st.metric(
                "上一财年",
                format_billions(
                    previous["value"]
                ),
            )

    st.caption(
        "SEC XBRL · "
        f"{current['concept']} · "
        f"{current['start']} → "
        f"{current['end']}"
    )


def evidence_badge(evidence):
    support = evidence.get("support")
    scope = evidence.get("scope")
    alignment = evidence.get(
        "metric_alignment"
    )

    if support == "insufficient":
        return "证据不足"

    if support == "direct":
        return "公司级直接证据"

    if scope == "component":
        return "局部证据"

    if alignment == "related":
        return "相关证据"

    return "部分证据"


def render_story_section(
    number,
    title,
    question,
    metrics_to_show,
    analysis_key,
    evidence_key,
):
    st.divider()

    st.header(
        f"{number}｜{title}"
    )

    st.caption(question)

    for metric_label, comparison in (
        metrics_to_show
    ):
        st.markdown(
            f"**{metric_label}**"
        )

        show_metric(
            metric_label,
            comparison,
        )

    analysis = st.session_state.analysis
    evidence_package = (
        st.session_state.selected_evidence
    )

    if (
        analysis is None
        or evidence_package is None
    ):
        st.info(
            "点击上方「生成公司解读」，"
            "系统会先从 10-K 中寻找管理层证据，"
            "再生成有证据约束的 AI 解读。"
        )
        return

    section = analysis[analysis_key]
    evidence = evidence_package[
        evidence_key
    ]

    st.markdown("### 💬 怎么理解？")

    st.write(
        section["interpretation"]
    )

    st.markdown(
        "### 🏢 管理层怎么说？"
    )

    if evidence["support"] == "insufficient":
        st.warning(
            "现有 SEC 证据不足以判断具体原因。"
            "AI 不继续猜测。"
        )

    else:
        st.write(
            section["management_explanation"]
        )

        st.caption(
            "Evidence "
            f"{evidence['evidence_id']} · "
            f"{evidence_badge(evidence)}"
        )

        with st.expander(
            "📄 查看 SEC 原文证据"
        ):
            st.write(
                evidence["text"]
            )

            st.caption(
                "Scope: "
                f"{evidence['scope']} · "
                "Metric alignment: "
                f"{evidence['metric_alignment']} · "
                "Support: "
                f"{evidence['support']}"
            )


def render_risk_section():
    st.divider()

    st.header(
        "04｜⚠️ 有什么值得注意的风险？"
    )

    st.caption(
        "只展示最新 10-K 中能够找到的"
        "管理层风险证据。"
    )

    analysis = st.session_state.analysis
    evidence_package = (
        st.session_state.selected_evidence
    )

    if (
        analysis is None
        or evidence_package is None
    ):
        st.info(
            "生成公司解读后，这里会显示"
            "与公司经营相关的 SEC 风险证据。"
        )
        return

    evidence = evidence_package["key_risk"]
    section = analysis["risk"]

    if evidence["support"] == "insufficient":
        st.warning(
            "当前候选证据中没有找到"
            "足够明确的风险披露。"
        )
        return

    st.markdown("### 💬 怎么理解？")

    st.write(
        section["interpretation"]
    )

    st.markdown(
        "### 🏢 管理层风险披露"
    )

    st.write(
        section["management_explanation"]
    )

    st.caption(
        "Evidence "
        f"{evidence['evidence_id']} · "
        f"{evidence_badge(evidence)}"
    )

    with st.expander(
        "📄 查看 SEC 原文证据"
    ):
        st.write(
            evidence["text"]
        )

        st.caption(
            "Scope: "
            f"{evidence['scope']} · "
            "Support: "
            f"{evidence['support']}"
        )


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.header("🔎 公司显微镜")

    st.write(
        "AI Company Research Assistant"
    )

    st.divider()

    st.markdown("### 当前范围")

    st.write("🇺🇸 美国上市公司")
    st.write("📄 最新年度 10-K")
    st.write("🏛️ SEC 官方披露")
    st.write("🧾 XBRL + MD&A")

    st.divider()

    st.markdown("### 产品原则")

    st.write("✓ 数字由程序确定")
    st.write("✓ 原因必须有 SEC 证据")
    st.write("✓ 区分事实与 AI 解读")
    st.write("✓ 局部证据不扩大")
    st.write("✓ 证据不足就不猜")
    st.write("✓ 不提供投资建议")


# ============================================================
# Header
# ============================================================

st.title("🔎 公司显微镜")

st.markdown(
    "### 输入一家美股公司，"
    "3 分钟看懂它最近一个财年发生了什么"
)

st.caption(
    "发生了什么 → 管理层怎么解释 → "
    "AI 怎么理解 → 原文证据在哪里"
)


# ============================================================
# Search
# ============================================================

ticker_input = st.text_input(
    "输入股票代码",
    value="AAPL",
    placeholder="例如：AAPL / MSFT / NVDA",
)

ticker = (
    ticker_input
    .strip()
    .upper()
)

if not ticker:
    st.info(
        "请输入一个美股股票代码。"
    )
    st.stop()


# ============================================================
# Load SEC facts
# ============================================================

try:
    with st.spinner(
        f"正在从 SEC 获取 {ticker} 官方数据..."
    ):
        snapshot = load_company_snapshot(
            ticker
        )

except Exception as error:
    st.error(
        f"无法获取 {ticker} 的 SEC 数据。"
    )

    with st.expander("查看错误信息"):
        st.code(str(error))

    st.stop()


company = snapshot["company"]
filing = snapshot["filing"]
metrics = snapshot["metrics"]

company_name = company["company_name"]

display_name = short_company_name(
    company_name
)

fact_package = build_fact_package(
    snapshot
)

filing_url = build_filing_url(
    snapshot
)


# ============================================================
# Prevent stale cross-company analysis
# ============================================================

if (
    st.session_state.analysis_ticker
    is not None
    and st.session_state.analysis_ticker
    != ticker
):
    reset_analysis()
    st.session_state.analysis_ticker = None


# ============================================================
# Company hero
# ============================================================

st.divider()

st.header(
    f"🏢 {display_name} ({ticker})"
)

st.caption(
    f"最新 10-K 报告期："
    f"{filing['report_date']} · "
    f"提交日期：{filing['filing_date']}"
)

hero1, hero2, hero3 = st.columns(3)

with hero1:
    revenue = metrics.get("Revenue")

    if metric_available(revenue):
        st.metric(
            "Revenue",
            format_billions(
                revenue["current"]["value"]
            ),
            format_yoy(
                revenue["yoy_percent"]
            ),
        )

with hero2:
    net_income = metrics.get("Net Income")

    if metric_available(net_income):
        st.metric(
            "Net Income",
            format_billions(
                net_income["current"]["value"]
            ),
            format_yoy(
                net_income["yoy_percent"]
            ),
        )

with hero3:
    cash = metrics.get(
        "Operating Cash Flow"
    )

    if metric_available(cash):
        st.metric(
            "Operating Cash Flow",
            format_billions(
                cash["current"]["value"]
            ),
            format_yoy(
                cash["yoy_percent"]
            ),
        )

st.caption(
    "以上数字来自 SEC XBRL，"
    "不是由 AI 生成。"
)

st.warning(
    "本产品用于帮助理解公司公开披露信息，"
    "不构成投资建议。"
)


# ============================================================
# Generate analysis
# ============================================================

st.divider()

button_col, text_col = st.columns(
    [1, 3]
)

with button_col:
    generate_clicked = st.button(
        "✨ 生成公司解读",
        type="primary",
        use_container_width=True,
    )

with text_col:
    st.caption(
        "系统会先读取最新 10-K 的 MD&A，"
        "选择可验证证据，再让 AI 解释。"
        "没有证据时不会强行给原因。"
    )


if generate_clicked:
    try:
        with st.spinner(
            "① 正在读取 SEC 10-K MD&A..."
        ):
            candidate_package = (
                load_evidence_package(
                    ticker
                )
            )

        with st.spinner(
            "② 正在选择最相关的官方证据..."
        ):
            selected_evidence = (
                run_evidence_selector(
                    candidate_package
                )
            )

        with st.spinner(
            "③ 正在生成有证据约束的解读..."
        ):
            analysis = (
                generate_grounded_interpretation(
                    fact_package,
                    selected_evidence,
                )
            )

        st.session_state.selected_evidence = (
            selected_evidence
        )

        st.session_state.analysis = analysis
        st.session_state.analysis_ticker = ticker
        st.session_state.analysis_status = (
            "Grounded"
        )

        st.success(
            "公司解读生成完成。"
            "财务数字来自 SEC XBRL；"
            "原因解释受到 SEC 原文证据约束。"
        )

    except Exception as error:
        reset_analysis()

        st.error(
            "公司解读生成失败。"
            "SEC 财务数字仍可正常查看。"
        )

        with st.expander(
            "查看错误信息"
        ):
            st.code(str(error))


# ============================================================
# Main story
# ============================================================

render_story_section(
    "01",
    "📈 生意怎么样？",
    "公司这一年的收入发生了什么？"
    "管理层披露了哪些可能解释变化的信息？",
    [
        (
            "Revenue",
            metrics.get("Revenue"),
        ),
    ],
    "revenue",
    "revenue_driver",
)


render_story_section(
    "02",
    "💰 赚得怎么样？",
    "利润增长还是下降？"
    "现有 SEC 证据能够解释到什么程度？",
    [
        (
            "Net Income",
            metrics.get("Net Income"),
        ),
        (
            "Operating Income",
            metrics.get(
                "Operating Income"
            ),
        ),
    ],
    "profit",
    "profit_driver",
)


render_story_section(
    "03",
    "💵 现金怎么样？",
    "经营活动真正带回了多少现金？"
    "财报有没有解释变化原因？",
    [
        (
            "Operating Cash Flow",
            metrics.get(
                "Operating Cash Flow"
            ),
        ),
    ],
    "cash",
    "cash_driver",
)


render_risk_section()


# ============================================================
# Source
# ============================================================

st.divider()

st.header(
    "📄 原始来源"
)

st.write(
    "核心财务数字来自 SEC XBRL；"
    "管理层解释来自最新 10-K 的 MD&A。"
    "每条 AI 原因解释都必须对应"
    "选中的 Evidence ID。"
)

st.link_button(
    "🔗 查看这家公司的最新 SEC 10-K",
    filing_url,
)


# ============================================================
# Architecture
# ============================================================

st.divider()

st.header(
    "🛡️ AI 为什么不能随便解释？"
)

st.markdown(
    """
**SEC XBRL FACTS**  
程序读取 Revenue、Net Income、Operating Income 和 Operating Cash Flow。

↓

**DETERMINISTIC CALCULATION**  
Python 验证财年并计算同比变化。

↓

**SEC 10-K MD&A**  
程序从管理层讨论与分析中寻找文本证据。

↓

**THEME GATE**  
先按 Revenue / Profit / Cash / Risk 筛选候选证据。

↓

**EVIDENCE SELECTOR**  
AI 只能从候选池中选择 Evidence ID，并判断 Scope、Metric Alignment 和 Support。

↓

**APPLICATION VALIDATION**  
程序检查 Evidence ID 和结构是否合法。

↓

**GROUNDED INTERPRETER**  
DeepSeek 只能根据锁定的金融事实和选中的 SEC Evidence 做通俗解释。

↓

**ABSTENTION**  
如果证据不足，系统明确说“不知道”，而不是补一个听起来合理的原因。
"""
)


# ============================================================
# PM / Debug
# ============================================================

with st.expander(
    "🔒 查看 Locked Financial Facts"
):
    st.json(fact_package)


if (
    st.session_state.selected_evidence
    is not None
):
    with st.expander(
        "🧾 查看 Selected SEC Evidence"
    ):
        st.json(
            st.session_state.selected_evidence
        )


with st.expander(
    "🧪 查看 SEC 自动抽取结果"
):
    st.json(snapshot)


# ============================================================
# Footer
# ============================================================

st.divider()

st.caption(
    "Company Microscope · "
    "Evidence-Grounded AI Company Research · "
    "SEC 10-K + XBRL + MD&A + "
    "Evidence Selection + Grounded Interpretation"
)