import re
import urllib.request
from html import unescape

from sec_data import (
    ticker_to_company,
    get_latest_10k,
)


# =========================
# SEC configuration
# =========================

HEADERS = {
    "User-Agent": (
        "AI-Company-Research-Assistant "
        "demo@example.com"
    ),
}


# =========================
# Filing URL
# =========================

def get_filing_url(ticker):
    company = ticker_to_company(ticker)

    filing = get_latest_10k(
        company["cik"]
    )

    cik_number = str(
        int(company["cik"])
    )

    accession = (
        filing["accession_number"]
        .replace("-", "")
    )

    document = filing["primary_document"]

    url = (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_number}/"
        f"{accession}/"
        f"{document}"
    )

    return company, filing, url


# =========================
# Download HTML
# =========================

def download_html(url):
    request = urllib.request.Request(
        url,
        headers=HEADERS,
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        )


# =========================
# HTML → text
# =========================

def html_to_text(html):
    text = re.sub(
        r"<script.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<style.*?</style>",
        " ",
        text,
        flags=re.I | re.S,
    )

    block_endings = [
        r"<br\s*/?>",
        r"</p>",
        r"</div>",
        r"</tr>",
        r"</li>",
        r"</h[1-6]>",
    ]

    for pattern in block_endings:
        text = re.sub(
            pattern,
            "\n",
            text,
            flags=re.I,
        )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = unescape(text)

    text = text.replace(
        "\xa0",
        " ",
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r" *\n *",
        "\n",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# =========================
# Search normalization
# =========================

def normalize_for_search(text):
    return (
        text
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )


# =========================
# Find MD&A candidates
# =========================

def find_mda_candidates(text):
    searchable = normalize_for_search(
        text
    )

    pattern = (
        r"Item\s+7[\.\s]+"
        r"Management['’]s\s+Discussion"
        r"\s+and\s+Analysis"
    )

    return [
        match.start()
        for match in re.finditer(
            pattern,
            searchable,
            flags=re.I,
        )
    ]


# =========================
# Score MD&A candidates
# =========================

def score_mda_candidate(
    text,
    position,
):
    sample = text[
        position:
        position + 15000
    ]

    sample_lower = (
        normalize_for_search(sample)
        .lower()
    )

    score = 0

    positive_terms = [
        "results of operations",
        "revenue",
        "net income",
        "operating income",
        "fiscal year",
        "financial condition",
    ]

    for term in positive_terms:
        if term in sample_lower:
            score += 2

    early_sample = sample_lower[:2500]

    toc_terms = [
        "item 7a",
        "item 8",
        "item 9",
        "item 10",
        "item 11",
        "item 12",
        "item 15",
    ]

    toc_hits = sum(
        1
        for term in toc_terms
        if term in early_sample
    )

    if toc_hits >= 3:
        score -= 10

    return score


# =========================
# Extract real MD&A
# =========================

def extract_mda(text):
    candidates = find_mda_candidates(
        text
    )

    if not candidates:
        return None

    scored = []

    for position in candidates:
        scored.append(
            (
                score_mda_candidate(
                    text,
                    position,
                ),
                position,
            )
        )

    scored.sort(
        reverse=True
    )

    start = scored[0][1]

    searchable = normalize_for_search(
        text
    )

    after_start = searchable[
        start + 1000:
    ]

    end_match = re.search(
        r"\bItem\s+7A[\.\s]",
        after_start,
        flags=re.I,
    )

    if end_match:
        end = (
            start
            + 1000
            + end_match.start()
        )
    else:
        end = min(
            len(text),
            start + 100000,
        )

    return text[
        start:end
    ].strip()


# =========================
# Paragraph splitting
# =========================

def split_paragraphs(text):
    raw_parts = re.split(
        r"\n+",
        text,
    )

    paragraphs = []

    for part in raw_parts:
        cleaned = re.sub(
            r"\s+",
            " ",
            part,
        ).strip()

        if len(cleaned) < 80:
            continue

        paragraphs.append(
            cleaned
        )

    return paragraphs


# =========================
# Evidence themes
# =========================

EVIDENCE_THEMES = {
    "Revenue / Growth": [
        "revenue",
        "revenue growth",
        "year-on-year growth",
        "year over year",
        "sales",
    ],

    "Profitability": [
        "operating income",
        "net income",
        "gross margin",
        "operating expenses",
        "profit",
        "profitability",
    ],

    "Cash / Liquidity": [
        "cash flow",
        "cash flows",
        "cash provided by",
        "cash used in",
        "operating activities",
        "liquidity",
        "cash and cash equivalents",
        "cash equivalents",
    ],

    "Risks / Challenges": [
        "risk",
        "risks",
        "could impact",
        "may impact",
        "could adversely",
        "may adversely",
        "shortage",
        "delay",
        "delays",
        "volatility",
        "tariff",
        "tariffs",
        "export",
        "supply chain",
        "uncertainty",
        "challenges",
    ],
}


# =========================
# Causal language
# =========================

CAUSAL_TERMS = [
    "driven by",
    "due to",
    "primarily due to",
    "resulting from",
    "as a result",
    "attributable to",
]


# =========================
# Evidence scoring
# =========================

def score_paragraph(
    paragraph,
    keywords,
):
    """
    Important retrieval rule:

    A paragraph must FIRST match the
    evidence theme.

    Only after it passes that relevance
    gate can causal language increase
    its score.

    This prevents a paragraph from
    entering Cash or Risk merely because
    it contains phrases such as
    "driven by" or "due to".
    """

    lower = (
        normalize_for_search(
            paragraph
        )
        .lower()
    )

    matched_keywords = []

    for keyword in keywords:
        if keyword in lower:
            matched_keywords.append(
                keyword
            )

    # Theme Gate:
    # no theme match = not a candidate.
    if not matched_keywords:
        return None

    # Base relevance score.
    score = len(
        matched_keywords
    ) * 2

    matched_causal_terms = []

    for term in CAUSAL_TERMS:
        if term in lower:
            matched_causal_terms.append(
                term
            )

    # Causal language is useful only
    # AFTER theme relevance is proven.
    score += (
        len(matched_causal_terms) * 2
    )

    return {
        "score": score,
        "matched_keywords":
            matched_keywords,
        "matched_causal_terms":
            matched_causal_terms,
    }


# =========================
# Build evidence candidates
# =========================

def build_evidence_candidates(
    mda_text,
    max_per_theme=3,
):
    paragraphs = split_paragraphs(
        mda_text
    )

    results = {}

    for theme, keywords in (
        EVIDENCE_THEMES.items()
    ):
        scored = []

        for index, paragraph in enumerate(
            paragraphs
        ):
            result = score_paragraph(
                paragraph,
                keywords,
            )

            if result is None:
                continue

            scored.append(
                {
                    "paragraph_id": (
                        f"P{index + 1:03d}"
                    ),
                    "score":
                        result["score"],
                    "matched_keywords":
                        result[
                            "matched_keywords"
                        ],
                    "matched_causal_terms":
                        result[
                            "matched_causal_terms"
                        ],
                    "text": paragraph,
                }
            )

        scored.sort(
            key=lambda item: (
                item["score"],
                len(
                    item[
                        "matched_keywords"
                    ]
                ),
                len(item["text"]),
            ),
            reverse=True,
        )

        results[theme] = (
            scored[:max_per_theme]
        )

    return results


# =========================
# Print evidence
# =========================

def print_evidence(
    evidence,
):
    for theme, chunks in (
        evidence.items()
    ):
        print(
            "\n"
            + "=" * 70
        )

        print(
            f"EVIDENCE THEME: {theme}"
        )

        print(
            "=" * 70
        )

        if not chunks:
            print(
                "❌ 没有找到候选 Evidence"
            )
            continue

        for chunk in chunks:
            print(
                f"\n[{chunk['paragraph_id']}] "
                f"score={chunk['score']}"
            )

            print(
                "Theme matches: "
                + ", ".join(
                    chunk[
                        "matched_keywords"
                    ]
                )
            )

            if chunk[
                "matched_causal_terms"
            ]:
                print(
                    "Causal matches: "
                    + ", ".join(
                        chunk[
                            "matched_causal_terms"
                        ]
                    )
                )
            else:
                print(
                    "Causal matches: none"
                )

            print(
                "\n"
                + chunk["text"]
            )


# =========================
# Test
# =========================

if __name__ == "__main__":
    ticker = "NVDA"

    print(
        f"\n正在构建 {ticker} "
        "MD&A Evidence Candidates..."
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
        f"Filing date: "
        f"{filing['filing_date']}"
    )

    print(
        "\n正在下载 SEC 10-K..."
    )

    html = download_html(url)

    text = html_to_text(html)

    mda = extract_mda(text)

    if not mda:
        print(
            "\n❌ MD&A 提取失败"
        )
        raise SystemExit

    print(
        f"\n✅ MD&A length: "
        f"{len(mda):,} characters"
    )

    paragraphs = split_paragraphs(
        mda
    )

    print(
        f"✅ Paragraphs: "
        f"{len(paragraphs)}"
    )

    evidence = (
        build_evidence_candidates(
            mda,
            max_per_theme=3,
        )
    )

    print_evidence(
        evidence
    )