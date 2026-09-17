import json
import os

from openai import OpenAI

from sec_text import (
    get_filing_url,
    download_html,
    html_to_text,
    extract_mda,
    build_evidence_candidates,
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
# Build candidate package
# ============================================================

def build_candidate_package(
    evidence_candidates,
):
    package = {}

    for theme, chunks in (
        evidence_candidates.items()
    ):
        package[theme] = []

        for chunk in chunks:
            package[theme].append(
                {
                    "evidence_id":
                        chunk["paragraph_id"],
                    "text":
                        chunk["text"],
                }
            )

    return package


# ============================================================
# Evidence Selector V0.3
# ============================================================

SYSTEM_PROMPT = """
You are an evidence selection component
inside a financial research system.

You are NOT writing financial analysis.

Your job is to determine:

1. Which SEC evidence is most useful?
2. What scope does that evidence cover?
3. How closely does it align with the target metric?
4. How strongly does it support the research question?

You may only use the supplied
CANDIDATE EVIDENCE PACKAGE.

==================================================
STRICT RULES
==================================================

1. Never invent an evidence ID.

2. Never use external knowledge.

3. Never rewrite or summarize the evidence.

4. Select based on meaning and direct relevance,
   not merely keyword overlap.

5. Prefer evidence that directly explains
   the target financial metric.

6. Do not force an answer.

==================================================
SCOPE
==================================================

Scope answers:

"WHO OR WHAT PART OF THE COMPANY
DOES THIS EVIDENCE COVER?"

Allowed values:

"company"
"component"
"none"

Use "company" when the evidence is explicitly
about the company as a whole.

Use "component" when the evidence is limited to:

- a segment
- a product
- a service
- a geography
- a business line
- another subset of the company

Use "none" when no meaningful evidence
is selected.

Never label component evidence as company-level.

==================================================
METRIC ALIGNMENT
==================================================

Metric alignment answers:

"IS THE EVIDENCE ACTUALLY ABOUT
THE TARGET METRIC?"

Allowed values:

"exact"
"related"
"none"

Use "exact" only when the evidence directly
discusses the same target metric or its change.

Use "related" when the evidence discusses
a financially related metric or driver,
but not the target metric itself.

Use "none" when no meaningful evidence
is selected.

--------------------------------------------------
TARGET METRICS
--------------------------------------------------

revenue_driver:

Target metric:
company revenue / net sales.

Examples of exact metric alignment:
- company revenue
- company net sales
- revenue change

Examples of related metric alignment:
- segment revenue
- product sales
- geography sales
- service revenue

--------------------------------------------------

profit_driver:

Target metrics:
company operating income
and company net income.

Examples of exact metric alignment:
- operating income
- net income
- direct explanation of changes
  in operating income or net income

Examples of related metric alignment:
- gross profit
- gross margin
- operating expenses
- segment operating income
- product margin
- service margin

IMPORTANT:

Company-level gross profit,
gross margin,
or operating expenses
are still only "related"
to operating income / net income.

Company scope does NOT make
metric alignment exact.

--------------------------------------------------

cash_driver:

Target metric:
company cash provided by
operating activities /
operating cash flow.

Examples of exact metric alignment:
- operating cash flow
- cash provided by operating activities
- direct explanation of its change

Examples of related metric alignment:
- liquidity
- cash balance
- cash equivalents
- investing cash flow
- financing cash flow

--------------------------------------------------

key_risk:

Target:
a concrete business or operating risk
that could affect future financial performance.

Use "exact" when the evidence itself
is a concrete risk disclosure.

Use "related" when the evidence only
provides background but does not itself
describe a concrete risk.

==================================================
SUPPORT
==================================================

Allowed values:

"direct"
"partial"
"insufficient"

Use "direct" ONLY when:

scope = "company"
AND
metric_alignment = "exact"

Use "partial" when meaningful evidence exists,
but either:

scope = "component"

OR

metric_alignment = "related"

Use "insufficient" when no candidate provides
meaningful support.

==================================================
CONSISTENCY RULES
==================================================

Valid direct evidence:

evidence_id = Pxxx
scope = company
metric_alignment = exact
support = direct

Valid partial evidence examples:

evidence_id = Pxxx
scope = component
metric_alignment = exact
support = partial

OR

evidence_id = Pxxx
scope = company
metric_alignment = related
support = partial

OR

evidence_id = Pxxx
scope = component
metric_alignment = related
support = partial

Valid insufficient evidence:

evidence_id = null
scope = none
metric_alignment = none
support = insufficient

==================================================
OUTPUT
==================================================

Return JSON only.

Required structure:

{
  "revenue_driver": {
    "evidence_id": "P000 or null",
    "scope": "company | component | none",
    "metric_alignment": "exact | related | none",
    "support": "direct | partial | insufficient"
  },

  "profit_driver": {
    "evidence_id": "P000 or null",
    "scope": "company | component | none",
    "metric_alignment": "exact | related | none",
    "support": "direct | partial | insufficient"
  },

  "cash_driver": {
    "evidence_id": "P000 or null",
    "scope": "company | component | none",
    "metric_alignment": "exact | related | none",
    "support": "direct | partial | insufficient"
  },

  "key_risk": {
    "evidence_id": "P000 or null",
    "scope": "company | component | none",
    "metric_alignment": "exact | related | none",
    "support": "direct | partial | insufficient"
  }
}
"""


# ============================================================
# AI selection
# ============================================================

def select_evidence(
    candidate_package,
):
    client = get_ai_client()

    model_name = os.getenv(
        "ARK_MODEL",
        "deepseek-v4-1-flash-260910",
    )

    user_prompt = (
        "CANDIDATE EVIDENCE PACKAGE:\n\n"
        + json.dumps(
            candidate_package,
            ensure_ascii=False,
            indent=2,
        )
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
# Application Validation V0.3
# ============================================================

def validate_selection(
    selections,
    candidate_package,
):
    allowed_ids = set()

    for chunks in candidate_package.values():
        for chunk in chunks:
            allowed_ids.add(
                chunk["evidence_id"]
            )

    required_keys = {
        "revenue_driver",
        "profit_driver",
        "cash_driver",
        "key_risk",
    }

    if set(selections.keys()) != required_keys:
        raise ValueError(
            "AI 返回的 selection schema 不正确"
        )

    allowed_scopes = {
        "company",
        "component",
        "none",
    }

    allowed_alignment = {
        "exact",
        "related",
        "none",
    }

    allowed_support = {
        "direct",
        "partial",
        "insufficient",
    }

    for question, result in (
        selections.items()
    ):
        evidence_id = result.get(
            "evidence_id"
        )

        scope = result.get(
            "scope"
        )

        metric_alignment = result.get(
            "metric_alignment"
        )

        support = result.get(
            "support"
        )

        if scope not in allowed_scopes:
            raise ValueError(
                f"{question}: "
                f"非法 scope={scope}"
            )

        if (
            metric_alignment
            not in allowed_alignment
        ):
            raise ValueError(
                f"{question}: "
                "非法 metric_alignment="
                f"{metric_alignment}"
            )

        if support not in allowed_support:
            raise ValueError(
                f"{question}: "
                f"非法 support={support}"
            )

        if evidence_id is not None:
            if evidence_id not in allowed_ids:
                raise ValueError(
                    f"{question}: "
                    "AI 选择了不存在的 "
                    f"Evidence ID={evidence_id}"
                )

        # ----------------------------------------
        # Insufficient state
        # ----------------------------------------

        if evidence_id is None:
            if not (
                scope == "none"
                and metric_alignment == "none"
                and support == "insufficient"
            ):
                raise ValueError(
                    f"{question}: "
                    "null evidence 必须对应 "
                    "none / none / insufficient"
                )

            continue

        # ----------------------------------------
        # Evidence exists
        # ----------------------------------------

        if scope == "none":
            raise ValueError(
                f"{question}: "
                "有 Evidence ID 时 "
                "scope 不能为 none"
            )

        if metric_alignment == "none":
            raise ValueError(
                f"{question}: "
                "有 Evidence ID 时 "
                "metric_alignment 不能为 none"
            )

        if support == "insufficient":
            raise ValueError(
                f"{question}: "
                "有 Evidence ID 时 "
                "support 不能为 insufficient"
            )

        # ----------------------------------------
        # Direct requires BOTH:
        # company scope + exact metric
        # ----------------------------------------

        if support == "direct":
            if not (
                scope == "company"
                and metric_alignment == "exact"
            ):
                raise ValueError(
                    f"{question}: "
                    "direct support 必须满足 "
                    "scope=company 且 "
                    "metric_alignment=exact"
                )

        # ----------------------------------------
        # Partial means at least one boundary
        # ----------------------------------------

        if support == "partial":
            if (
                scope == "company"
                and metric_alignment == "exact"
            ):
                raise ValueError(
                    f"{question}: "
                    "company + exact "
                    "不应标记为 partial"
                )

    return True


# ============================================================
# Resolve selected evidence
# ============================================================

def resolve_selected_evidence(
    selections,
    candidate_package,
):
    evidence_lookup = {}

    for chunks in candidate_package.values():
        for chunk in chunks:
            evidence_lookup[
                chunk["evidence_id"]
            ] = chunk["text"]

    resolved = {}

    for question, selection in (
        selections.items()
    ):
        evidence_id = selection[
            "evidence_id"
        ]

        resolved[question] = {
            "evidence_id":
                evidence_id,

            "scope":
                selection["scope"],

            "metric_alignment":
                selection[
                    "metric_alignment"
                ],

            "support":
                selection["support"],

            "text":
                (
                    evidence_lookup[
                        evidence_id
                    ]
                    if evidence_id
                    else None
                ),
        }

    return resolved


# ============================================================
# Print result
# ============================================================

def print_result(resolved):
    print(
        "\n"
        + "=" * 70
    )

    print(
        "EVIDENCE SELECTION V0.3"
    )

    print(
        "=" * 70
    )

    for question, result in (
        resolved.items()
    ):
        print(
            f"\n{question}"
        )

        print(
            f"Evidence ID: "
            f"{result['evidence_id']}"
        )

        print(
            f"Scope: "
            f"{result['scope']}"
        )

        print(
            "Metric Alignment: "
            f"{result['metric_alignment']}"
        )

        print(
            f"Support: "
            f"{result['support']}"
        )

        if result["text"]:
            print(
                "\n"
                + result["text"]
            )
        else:
            print(
                "\nNo sufficiently relevant "
                "evidence selected."
            )


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    ticker = "MSFT"

    print(
        f"\n正在构建 {ticker} "
        "Evidence Selector V0.3 Test..."
    )

    company, filing, url = (
        get_filing_url(ticker)
    )

    print(
        f"\nCompany: "
        f"{company['company_name']}"
    )

    print(
        f"Report date: "
        f"{filing['report_date']}"
    )

    print(
        "\n正在读取 SEC MD&A..."
    )

    html = download_html(url)

    text = html_to_text(html)

    mda = extract_mda(text)

    if not mda:
        raise ValueError(
            "MD&A 提取失败"
        )

    candidates = (
        build_evidence_candidates(
            mda,
            max_per_theme=3,
        )
    )

    candidate_package = (
        build_candidate_package(
            candidates
        )
    )

    print(
        "\n正在判断 Evidence ID "
        "+ Scope "
        "+ Metric Alignment "
        "+ Support..."
    )

    selections = select_evidence(
        candidate_package
    )

    validate_selection(
        selections,
        candidate_package,
    )

    resolved = (
        resolve_selected_evidence(
            selections,
            candidate_package,
        )
    )

    print(
        "\n✅ Selection passed "
        "V0.3 application validation"
    )

    print_result(
        resolved
    )