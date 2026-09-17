import json
import os

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
# DeepSeek client
# ============================================================

def get_ai_client():
    api_key = os.getenv("ARK_API_KEY")
    base_url = os.getenv("ARK_BASE_URL")

    if not api_key:
        raise ValueError(
            "没有检测到 ARK_API_KEY"
        )

    if not base_url:
        raise ValueError(
            "没有检测到 ARK_BASE_URL"
        )

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


# ============================================================
# Locked Financial Facts
# ============================================================

def build_locked_facts(snapshot):
    company = snapshot["company"]
    filing = snapshot["filing"]
    metrics = snapshot["metrics"]

    return {
        "company_name":
            company["company_name"],

        "ticker":
            company["ticker"],

        "report_date":
            filing["report_date"],

        "filing_date":
            filing["filing_date"],

        "revenue": {
            "current":
                metrics[
                    "Revenue"
                ]["current"]["value"],

            "previous":
                metrics[
                    "Revenue"
                ]["previous"]["value"],

            "yoy_percent":
                metrics[
                    "Revenue"
                ]["yoy_percent"],
        },

        "net_income": {
            "current":
                metrics[
                    "Net Income"
                ]["current"]["value"],

            "previous":
                metrics[
                    "Net Income"
                ]["previous"]["value"],

            "yoy_percent":
                metrics[
                    "Net Income"
                ]["yoy_percent"],
        },

        "operating_income": {
            "current":
                metrics[
                    "Operating Income"
                ]["current"]["value"],

            "previous":
                metrics[
                    "Operating Income"
                ]["previous"]["value"],

            "yoy_percent":
                metrics[
                    "Operating Income"
                ]["yoy_percent"],
        },

        "operating_cash_flow": {
            "current":
                metrics[
                    "Operating Cash Flow"
                ]["current"]["value"],

            "previous":
                metrics[
                    "Operating Cash Flow"
                ]["previous"]["value"],

            "yoy_percent":
                metrics[
                    "Operating Cash Flow"
                ]["yoy_percent"],
        },
    }


# ============================================================
# Evidence Package V0.2
# ============================================================

def build_locked_evidence(
    resolved_evidence,
):
    locked = {}

    for question, result in (
        resolved_evidence.items()
    ):
        locked[question] = {
            "evidence_id":
                result["evidence_id"],

            "scope":
                result["scope"],

            "support":
                result["support"],

            "text":
                result["text"],
        }

    return locked


# ============================================================
# Grounded Interpreter V0.2 Prompt
# ============================================================

SYSTEM_PROMPT = """
You are the Grounded Interpretation Layer
inside an AI company research product.

Your audience is an ordinary individual investor
who wants to understand a company's annual report.

You are NOT an investment adviser.

You receive two locked inputs:

1. LOCKED FINANCIAL FACTS
2. LOCKED SEC EVIDENCE

You must use ONLY these inputs.

You must not use external knowledge.

==================================================
CORE PRINCIPLE
==================================================

Separate:

FACT
What the deterministic financial data says.

MANAGEMENT EXPLANATION
What management says in the selected SEC evidence.

AI INTERPRETATION
What the supplied facts and evidence mean
when explained in plain language.

Never blur these three layers.

==================================================
EVIDENCE SCOPE
==================================================

Each selected evidence item contains:

evidence_id
scope
support
text

Possible scope values:

company
component
none

Possible support values:

direct
partial
insufficient

You MUST obey these fields.

--------------------------------------------------
CASE 1
scope = company
support = direct
--------------------------------------------------

The evidence directly supports the
company-level research question.

You may explain the management reason
as a direct company-level explanation,
but only to the extent stated in the evidence.

Do not add other causes.

--------------------------------------------------
CASE 2
scope = component
support = partial
--------------------------------------------------

The evidence only covers part of the company,
such as:

a segment
a product
a service
a geography
a business line
a margin category
or another subset.

You MUST NOT present it as the complete
company-level explanation.

The management_explanation should clearly
identify the component being discussed.

The interpretation should explain why
this component-level evidence is useful,
while explicitly stating that it does not
fully explain the company-level financial change.

--------------------------------------------------
CASE 3
scope = none
support = insufficient
--------------------------------------------------

There is no sufficiently relevant
selected SEC evidence.

You MUST NOT guess a cause.

management_explanation must clearly say
that the selected SEC evidence does not
provide a sufficient explanation.

interpretation may explain the financial
fact itself, but must not invent a reason.

evidence_id must be null.

==================================================
STRICT FACT RULES
==================================================

1. Never invent financial numbers.

2. Never modify supplied financial numbers.

3. Never recalculate the supplied numbers.

4. Never introduce financial metrics
   that are not in the locked inputs.

5. Never introduce external events,
   competitors, customers, market share,
   industry trends, stock prices,
   valuation, analyst opinions,
   or news.

6. A statement from management must be
   supported by the selected evidence text.

7. Never convert component evidence
   into a company-wide cause.

8. If evidence is incomplete,
   explicitly preserve that uncertainty.

9. Historical facts and forward-looking risks
   must remain clearly distinguished.

10. Never make buy, sell, hold,
    target-price, valuation,
    or investment recommendations.

==================================================
INTERPRETATION VALUE
==================================================

Do not merely repeat the numbers.

Help the user understand:

- what changed,
- what management actually explained,
- how far that explanation can be trusted,
- what remains unknown.

Use plain Simplified Chinese.

Avoid unnecessary technical language.

Do not mention internal system terms such as:

"prompt"
"LLM"
"RAG"
"validator"
"candidate pool"

It is acceptable to refer to:

"财务数据"
"管理层披露"
"SEC 证据"
"现有证据"

==================================================
RISK SECTION
==================================================

The risk section is different from
historical financial-driver sections.

If selected risk evidence is:

company + direct

you may describe it as a company-level
management risk disclosure.

If it is:

component + partial

clearly state which component or activity
the risk relates to.

Do not say that a risk will happen.

Do not assign probability.

Do not quantify future financial impact
unless the locked evidence explicitly does so.

==================================================
OUTPUT
==================================================

Return JSON only.

Required structure:

{
  "revenue": {
    "fact": "...",
    "management_explanation": "...",
    "interpretation": "...",
    "evidence_id": "P000 or null"
  },

  "profit": {
    "fact": "...",
    "management_explanation": "...",
    "interpretation": "...",
    "evidence_id": "P000 or null"
  },

  "cash": {
    "fact": "...",
    "management_explanation": "...",
    "interpretation": "...",
    "evidence_id": "P000 or null"
  },

  "risk": {
    "fact": "...",
    "management_explanation": "...",
    "interpretation": "...",
    "evidence_id": "P000 or null"
  }
}
"""


# ============================================================
# Generate Interpretation
# ============================================================

def generate_interpretation(
    locked_facts,
    locked_evidence,
):
    client = get_ai_client()

    model_name = os.getenv(
        "ARK_MODEL",
        "deepseek-v4-1-flash-260910",
    )

    input_package = {
        "LOCKED_FINANCIAL_FACTS":
            locked_facts,

        "LOCKED_SEC_EVIDENCE":
            locked_evidence,
    }

    user_prompt = json.dumps(
        input_package,
        ensure_ascii=False,
        indent=2,
    )

    response = (
        client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content":
                        SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content":
                        user_prompt,
                },
            ],
            temperature=0,
        )
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

    return json.loads(
        content.strip()
    )


# ============================================================
# Application Validation V0.2
# ============================================================

def validate_interpretation(
    interpretation,
    locked_evidence,
):
    required_sections = {
        "revenue",
        "profit",
        "cash",
        "risk",
    }

    if set(
        interpretation.keys()
    ) != required_sections:
        raise ValueError(
            "Interpretation 顶层结构不正确"
        )

    required_fields = {
        "fact",
        "management_explanation",
        "interpretation",
        "evidence_id",
    }

    mapping = {
        "revenue":
            "revenue_driver",

        "profit":
            "profit_driver",

        "cash":
            "cash_driver",

        "risk":
            "key_risk",
    }

    for section, evidence_key in (
        mapping.items()
    ):
        result = interpretation[
            section
        ]

        if set(
            result.keys()
        ) != required_fields:
            raise ValueError(
                f"{section} 输出字段不正确"
            )

        selected = locked_evidence[
            evidence_key
        ]

        expected_id = selected[
            "evidence_id"
        ]

        actual_id = result[
            "evidence_id"
        ]

        # Interpreter cannot switch evidence.
        if actual_id != expected_id:
            raise ValueError(
                f"{section}: "
                "Interpreter 使用了错误的 "
                "Evidence ID。"
                f"Expected={expected_id}, "
                f"Actual={actual_id}"
            )

        # Insufficient evidence must remain null.
        if (
            selected["support"]
            == "insufficient"
            and actual_id is not None
        ):
            raise ValueError(
                f"{section}: "
                "insufficient evidence "
                "不能产生 Evidence ID"
            )

    return True


# ============================================================
# Pretty Print
# ============================================================

def print_section(
    number,
    title,
    result,
    evidence_meta,
):
    print(
        "\n"
        + "=" * 70
    )

    print(
        f"{number} {title}"
    )

    print(
        "=" * 70
    )

    print(
        "\n【Fact】"
    )

    print(
        result["fact"]
    )

    print(
        "\n【Management Explanation】"
    )

    print(
        result[
            "management_explanation"
        ]
    )

    print(
        "\n【AI Interpretation】"
    )

    print(
        result["interpretation"]
    )

    print(
        "\n【Evidence】"
    )

    print(
        result["evidence_id"]
    )

    print(
        "\n【Evidence Scope】"
    )

    print(
        evidence_meta["scope"]
    )

    print(
        "\n【Support Level】"
    )

    print(
        evidence_meta["support"]
    )


# ============================================================
# End-to-End Test
# ============================================================

if __name__ == "__main__":
    ticker = "NVDA"

    print(
        f"\n正在构建 {ticker} "
        "Grounded Interpreter V0.2 Test..."
    )

    # --------------------------------------------------------
    # Step 1
    # --------------------------------------------------------

    print(
        "\nStep 1/3 "
        "读取 SEC 财务事实..."
    )

    snapshot = (
        build_company_snapshot(
            ticker
        )
    )

    locked_facts = (
        build_locked_facts(
            snapshot
        )
    )

    print(
        "✅ Locked Financial Facts"
    )

    # --------------------------------------------------------
    # Step 2
    # --------------------------------------------------------

    print(
        "\nStep 2/3 "
        "提取并选择 SEC Evidence..."
    )

    company, filing, url = (
        get_filing_url(
            ticker
        )
    )

    html = download_html(
        url
    )

    text = html_to_text(
        html
    )

    mda = extract_mda(
        text
    )

    if not mda:
        raise ValueError(
            "MD&A 提取失败"
        )

    evidence_candidates = (
        build_evidence_candidates(
            mda,
            max_per_theme=3,
        )
    )

    candidate_package = (
        build_candidate_package(
            evidence_candidates
        )
    )

    selections = (
        select_evidence(
            candidate_package
        )
    )

    validate_selection(
        selections,
        candidate_package,
    )

    resolved_evidence = (
        resolve_selected_evidence(
            selections,
            candidate_package,
        )
    )

    locked_evidence = (
        build_locked_evidence(
            resolved_evidence
        )
    )

    print(
        "✅ Selected SEC Evidence"
    )

    for key, result in (
        locked_evidence.items()
    ):
        print(
            f"  {key}: "
            f"{result['evidence_id']} "
            f"| scope={result['scope']} "
            f"| support={result['support']}"
        )

    # --------------------------------------------------------
    # Step 3
    # --------------------------------------------------------

    print(
        "\nStep 3/3 "
        "生成 Grounded Interpretation..."
    )

    interpretation = (
        generate_interpretation(
            locked_facts,
            locked_evidence,
        )
    )

    validate_interpretation(
        interpretation,
        locked_evidence,
    )

    print(
        "✅ Interpretation passed "
        "Evidence ID validation"
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    print_section(
        "01",
        "生意为什么变化？",
        interpretation["revenue"],
        locked_evidence[
            "revenue_driver"
        ],
    )

    print_section(
        "02",
        "利润怎么看？",
        interpretation["profit"],
        locked_evidence[
            "profit_driver"
        ],
    )

    print_section(
        "03",
        "现金怎么样？",
        interpretation["cash"],
        locked_evidence[
            "cash_driver"
        ],
    )

    print_section(
        "04",
        "要注意什么？",
        interpretation["risk"],
        locked_evidence[
            "key_risk"
        ],
    )