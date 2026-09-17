# 🔎 公司显微镜 · AI Company Research Assistant



> 输入一家美股公司，快速看懂它最近一个财年发生了什么，并让重要解释尽可能回到 SEC 官方披露。



公司显微镜是一个面向普通个人投资者的 AI 公司研究助手。



它不是让大模型自由分析股票，而是尝试解决一个更具体的问题：



> \*\*如何让 AI 的公司研究既有解释价值，又尽量减少“听起来合理、但没有证据”的分析？\*\*



项目目前支持美国上市公司最新年度 Form 10-K，结合 SEC XBRL 财务事实、10-K MD\&A 管理层文本证据和受约束的 LLM Interpretation，为用户回答：



\- 公司的收入发生了什么？

\- 利润发生了什么？

\- 经营现金流发生了什么？

\- 管理层披露了哪些可能解释这些变化的信息？

\- 有哪些值得注意的经营风险？

\- 这些解释对应的 SEC 原文证据在哪里？



\---



\## 🎯 Problem



普通个人投资者面对公司年报时有两个典型困难。



第一，10-K 很长，财务数字、管理层讨论和风险披露分散在不同位置，阅读成本很高。



第二，直接让通用 AI 回答：



> “为什么这家公司收入增长了？”



虽然可以得到非常流畅的回答，但模型可能混入外部知识、新闻、行业常识或未经当前财报验证的原因。



这会产生一个产品矛盾：



> \*\*如果限制太少，AI 容易 hallucinate；  

> 如果限制太强，只允许 AI 看几个财务数字，回答又会变得正确但没有价值。\*\*



\---



\## 💡 Product Hypothesis



我的产品假设是：



> 与其要求 LLM “更谨慎地回答”，不如改变它能够看到和使用的信息结构。



因此，公司显微镜没有让 LLM 自己寻找财务数字，也没有让它自由决定公司变化的原因。



系统把任务拆成三类：



\### Fact



Revenue、Net Income、Operating Income、Operating Cash Flow 等核心数字来自 SEC XBRL。



同比变化由 Python 确定性计算。



\### Management Explanation



“为什么发生变化”优先从公司最新 10-K 的 MD\&A 中寻找管理层披露。



每条证据保留 Evidence ID 和 SEC 原文。



\### AI Interpretation



LLM 的任务不是创造事实，而是：



> \*\*把已经锁定的 Fact + Evidence 翻译成普通用户容易理解的语言。\*\*



如果证据不足，系统允许 AI 明确说：



> \*\*现有 SEC 证据不足以判断具体原因。\*\*



\---



\## 🧠 Core Product Principle



项目最重要的设计原则是：



> \*\*LLM 负责怎么讲，程序负责怎么算；  

> AI 不只是回答“找到了什么证据”，还要知道“这条证据允许自己说到什么程度”。\*\*



因此系统区分：



\*\*Scope\*\*



\- `company`：公司整体

\- `component`：产品、业务、地区、segment 等局部范围

\- `none`：没有足够证据



\*\*Metric Alignment\*\*



\- `exact`：证据直接讨论目标指标

\- `related`：证据相关，但不是目标指标本身

\- `none`：没有足够证据



\*\*Support\*\*



\- `direct`

\- `partial`

\- `insufficient`



应用层进一步约束：



```text

direct

=

company scope

\+

exact metric alignment

```



这避免了一个常见错误：



> 一条证据即使是“公司级证据”，也不意味着它直接解释了当前目标财务指标。



\---



\## 🏗️ Architecture



```text

User enters ticker

&#x20;       ↓

SEC Company Resolution

&#x20;       ↓

Latest Form 10-K

&#x20;       ↓

┌───────────────────────────────┐

│                               │

│  SEC XBRL Facts               │

│  Revenue / Profit / Cash      │

│                               │

└───────────────┬───────────────┘

&#x20;               ↓

&#x20;    Period Validation

&#x20;               ↓

&#x20;  Deterministic Calculation

&#x20;               ↓

&#x20;   Locked Financial Facts





Latest 10-K HTML

&#x20;       ↓

MD\&A Section Extraction

&#x20;       ↓

Paragraph Candidates

&#x20;       ↓

Python Theme Gate

&#x20;       ↓

LLM Evidence Selector

&#x20;       ↓

Application Validation

&#x20;       ↓

Evidence ID

\+ Scope

\+ Metric Alignment

\+ Support

&#x20;       ↓

Locked Management Evidence





Locked Financial Facts

&#x20;       +

Locked Management Evidence

&#x20;       ↓

Grounded Interpreter

&#x20;       ↓

Fact

→ Management Explanation

→ AI Interpretation

→ SEC Evidence

```



\---



\## 🛡️ Why Not Let the LLM Do Everything?



这个项目刻意没有让 LLM：



\- 自己寻找财务数字

\- 自己计算同比

\- 自己决定数据期间

\- 自由搜索公司变化原因

\- 使用候选池之外的 Evidence

\- 把局部业务证据扩大成全公司结论

\- 在证据不足时强行生成原因

\- 提供买入、卖出、目标价或投资评级



原因是这些任务中，有些更适合确定性程序，有些才适合 LLM。



因此架构原则是：



```text

Deterministic where possible.

Generative where useful.

Grounded where necessary.

```



\---



\## 🔍 Evidence Pipeline



\### 1. SEC XBRL Fact Layer



系统自动：



1\. 根据 ticker 解析公司和 CIK

2\. 获取最新年度 10-K

3\. 获取 SEC Company Facts

4\. 寻找适用的 XBRL concepts

5\. 验证完整财年期间

6\. 提取当前财年和上一财年

7\. 使用 Python 计算 YoY



当前核心指标：



\- Revenue

\- Net Income

\- Operating Income

\- Operating Cash Flow



不同公司可能使用不同 XBRL concept。



例如 NVIDIA Revenue 使用：



```text

Revenues

```



而 Apple 使用：



```text

RevenueFromContractWithCustomerExcludingAssessedTax

```



因此系统包含 concept fallback，而不是假设所有公司使用完全相同的标签。



\---



\### 2. MD\&A Section Extraction



最初版本直接搜索：



```text

Management's Discussion and Analysis

```



但第一次在 NVIDIA 10-K 中命中的是：



> Table of Contents



而不是真正的 MD\&A 正文。



因此后续版本加入候选位置评分和 section-aware extraction，从真正的 Item 7 正文提取管理层讨论。



这是项目中的第一个重要 retrieval failure。



\---



\### 3. Theme Gate



早期 Evidence Retrieval 使用主题关键词和：



```text

driven by

due to

primarily due to

```



等因果表达进行评分。



实际测试发现：



> \*\*包含因果词 ≠ 与当前问题真正相关。\*\*



例如税务相关段落可能因为包含 `due to` 被错误提升到 Cash / Risk 候选中。



因此加入 Python Theme Gate：



> 候选段落必须先满足主题相关性，因果词只能在主题匹配之后增加分数。



\---



\### 4. Evidence Selector



Theme Gate 解决了明显的跨主题误匹配，但又出现新的问题：



> \*\*相关证据 ≠ 足以回答问题的证据。\*\*



因此加入 Evidence Selector。



LLM 不能自由创造分析，只能从候选池选择 Evidence ID，并输出结构化判断：



```json

{

&#x20; "evidence\_id": "P008",

&#x20; "scope": "component",

&#x20; "metric\_alignment": "related",

&#x20; "support": "partial"

}

```



应用层随后验证：



\- Evidence ID 是否真的存在

\- scope 是否合法

\- metric alignment 是否合法

\- support 是否与其他字段一致



LLM 无法通过输出一个不存在的 Evidence ID 绕过候选池。



\---



\### 5. Grounded Interpreter



最终 Interpreter 只能看到：



```text

LOCKED FINANCIAL FACTS

\+

LOCKED MANAGEMENT EVIDENCE

```



它负责区分：



```text

FACT

→ 财务数字发生了什么



MANAGEMENT EXPLANATION

→ 管理层披露了什么



AI INTERPRETATION

→ 这对普通用户意味着什么

```



如果只有 component evidence，AI 必须明确告诉用户它不能完整解释公司整体。



如果：



```text

support = insufficient

```



系统不会继续猜原因。



\---



\## 🧪 Evaluation



为了避免只凭“回答看起来不错”判断系统质量，我建立了一个小型人工 evaluation baseline。



\### Evaluation V0.2



测试公司：



\- Apple (AAPL)

\- Microsoft (MSFT)

\- NVIDIA (NVDA)



每家公司测试四类任务：



\- Revenue

\- Profit

\- Cash

\- Risk



共：



```text

3 companies × 4 tasks = 12 cases

```



人工 Rubric：



| Dimension | Question |

|---|---|

| Fact Fidelity | 财务数字和方向是否与 Locked Facts 一致？ |

| Evidence Relevance | 选中的 SEC Evidence 是否真正相关？ |

| Scope Accuracy | 是否把 component evidence 扩大成 company-level claim？ |

| Unsupported Claim | 是否出现 Locked Facts / Evidence 之外的事实或因果主张？ |

| Correct Abstention | 证据不足时是否停止猜测？ |

| Interpretation Value | 是否帮助普通用户理解，而不是简单复述数字？ |



\---



\## 🔬 What Evaluation Found



Evaluation 的目标不是证明系统“100% 准确”。



相反，它帮助发现了一个重复出现的 failure mode。



\### MSFT Profit



Evidence 涉及：



```text

Gross Profit / Gross Margin

```



但目标指标是：



```text

Operating Income / Net Income

```



这条证据是 company-level，也与 profitability 相关，但不能因此自动认为它是目标指标的 direct explanation。



\### NVDA Profit



Evidence 涉及：



```text

Operating Expenses

```



但目标同样是：



```text

Operating Income / Net Income

```



再次出现：



```text

Company-level evidence

≠

Direct evidence for target metric

```



因此下一版 Selector 引入：



```text

Metric Alignment

```



把：



```text

Scope

```



和：



```text

Is this actually about the target metric?

```



拆成两个不同判断。



这是 Evaluation 直接推动产品架构变化的一个例子。



\---



\## 🧯 Abstention as a Product Feature



AAPL Operating Cash Flow 是一个重要测试案例。



Locked Facts 显示：



```text

Operating Cash Flow

$118.3B → $111.5B

YoY -5.7%

```



但当前 MD\&A candidate evidence 中没有找到足以解释这一变化的直接原因。



系统因此返回：



```text

evidence\_id = null

scope = none

metric\_alignment = none

support = insufficient

```



Interpreter 不会用收入、利润、关税或其他“听起来合理”的原因补全答案。



它告诉用户：



> \*\*现有 SEC 证据不足以判断具体原因。\*\*



在这个产品里：



> \*\*“不知道”不是模型失败，而是一种受控的系统状态。\*\*



\---



\## 🔄 Product Iteration



项目并不是一次性设计完成的。



实际迭代路径：



```text

V0.1

Static Apple financial demo

&#x20;       ↓

V0.2

DeepSeek Interpretation

&#x20;       ↓

Problem:

AI only sees four numbers.

Safe, but shallow.

&#x20;       ↓

Generic SEC XBRL Pipeline

&#x20;       ↓

AAPL / MSFT / NVDA

&#x20;       ↓

Add 10-K MD\&A

&#x20;       ↓

Problem:

Naive extraction hits Table of Contents

&#x20;       ↓

Section-aware MD\&A Extraction

&#x20;       ↓

Keyword + causal retrieval

&#x20;       ↓

Problem:

Cross-theme false positives

&#x20;       ↓

Python Theme Gate

&#x20;       ↓

Problem:

Relevant evidence is not always sufficient evidence

&#x20;       ↓

Evidence Selector

&#x20;       ↓

Scope + Support

&#x20;       ↓

12-case Manual Evaluation

&#x20;       ↓

Problem:

Company scope ≠ target metric alignment

&#x20;       ↓

Metric Alignment

&#x20;       ↓

Evidence-Grounded Company Research Assistant

```



\---



\## 🖥️ Current Product Experience



用户输入：



```text

AAPL

MSFT

NVDA

```



系统自动获取最新年度 10-K。



首页首先展示：



```text

Revenue

Net Income

Operating Cash Flow

```



这些数字来自 SEC XBRL，不由 AI 生成。



点击：



```text

✨ 生成公司解读

```



系统依次：



```text

读取 SEC 10-K MD\&A

&#x20;       ↓

寻找候选 Evidence

&#x20;       ↓

选择最相关 Evidence

&#x20;       ↓

验证 Evidence ID / Scope / Alignment / Support

&#x20;       ↓

生成 Grounded Interpretation

```



最终用户看到：



```text

发生了什么？

&#x20;       ↓

怎么理解？

&#x20;       ↓

管理层怎么说？

&#x20;       ↓

SEC 原文 Evidence

```



\---



\## 📊 Current Scope



当前版本刻意保持较窄范围：



\*\*Supported\*\*



\- U.S.-listed companies

\- Latest annual Form 10-K

\- SEC official disclosures

\- Revenue

\- Net Income

\- Operating Income

\- Operating Cash Flow

\- MD\&A evidence

\- Selected operating risks



\*\*Not included\*\*



\- Real-time stock prices

\- Technical indicators

\- Social sentiment

\- Buy / sell recommendations

\- Target prices

\- Automatic valuation

\- 10-Q / 8-K / news synthesis

\- A-share / HK-listed company filings



这是产品范围选择，而不是试图一次解决所有投资研究问题。



\---



\## 🧰 Tech Stack



```text

Python

Streamlit

SEC EDGAR / data.sec.gov

SEC XBRL Company Facts

10-K HTML / MD\&A

OpenAI-compatible API

DeepSeek via Volcengine Ark

```



\---



\## 🚀 Run Locally



\### 1. Clone the repository



```bash

git clone <YOUR\_REPOSITORY\_URL>

cd ai-company-research-assistant

```



\### 2. Create a virtual environment



```bash

python -m venv .venv

```



\### 3. Activate it



Windows PowerShell:



```powershell

.venv\\Scripts\\Activate.ps1

```



\### 4. Install dependencies



```bash

pip install streamlit openai

```



\### 5. Configure environment variables



The application expects:



```text

ARK\_API\_KEY

ARK\_BASE\_URL

ARK\_MODEL

```



Do not commit API keys to GitHub.



\### 6. Run



```bash

streamlit run app.py

```



\---



\## 📁 Project Structure



```text

app.py

│

├── sec\_data.py

│   └── SEC company resolution

│       + latest 10-K

│       + XBRL financial facts

│

├── sec\_text.py

│   └── 10-K HTML

│       + MD\&A extraction

│       + candidate retrieval

│

├── evidence\_selector.py

│   └── Evidence ID

│       + Scope

│       + Metric Alignment

│       + Support

│

├── grounded\_interpreter.py

│   └── Grounded interpretation experiments

│

├── retrieval\_debug.py

│   └── Evidence retrieval debugging

│

└── evaluation\_v0.2.csv

&#x20;   └── Manual evaluation baseline

```



\---



\## ⚠️ Limitations



This is an experimental research assistant, not a production investment product.



Current limitations include:



1\. SEC filing structures vary across companies.

2\. XBRL concepts are not perfectly standardized.

3\. MD\&A retrieval can miss useful evidence.

4\. Evidence selection still depends partly on an LLM.

5\. A relevant disclosure may explain only one part of a financial change.

6\. The current manual evaluation contains only 12 cases across 3 companies.

7\. The system should not be interpreted as providing investment recommendations.



The evaluation results therefore should not be interpreted as a general accuracy estimate.



\---



\## 🧭 What I Learned



这个项目最重要的产品学习不是“如何调用一个 LLM API”。



而是：



\### 1. Hallucination is partly a product architecture problem



仅仅告诉模型：



> “不要 hallucinate”



是不够的。



更有效的方式是限制：



```text

模型能看到什么

模型能选择什么

程序允许模型输出什么

```



\### 2. Reliability and usefulness can conflict



只给 AI 四个确定性财务数字，可以减少 unsupported claims，但输出会非常浅。



增加 MD\&A 后，解释能力增强，但 retrieval、scope 和 evidence quality 又成为新的问题。



因此目标不是：



> 最大化 AI 自由度



也不是：



> 最大化 AI 限制



而是找到：



> \*\*usefulness × groundedness\*\*



之间合理的产品边界。



\### 3. Evaluation should change the product



Evaluation 不应该只是项目最后的一张“准确率成绩单”。



这个项目中的 manual evaluation 实际发现了：



```text

Company Scope

≠

Metric Alignment

```



并直接推动了 Evidence Selector schema 的变化。



\---



\## 📌 Disclaimer



This project is designed to help users understand publicly disclosed company information.



It does not provide investment advice, investment ratings, price targets, or predictions of future stock performance.



Financial information should always be verified against the original SEC filing.

