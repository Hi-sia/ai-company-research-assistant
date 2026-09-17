from sec_text import (
    get_filing_url,
    download_html,
    html_to_text,
    extract_mda,
    split_paragraphs,
    EVIDENCE_THEMES,
    score_paragraph,
)


# =========================
# Rank all candidates
# =========================

def rank_candidates(
    mda_text,
    max_per_theme=10,
):
    paragraphs = split_paragraphs(
        mda_text
    )

    results = {}

    for theme, keywords in (
        EVIDENCE_THEMES.items()
    ):
        candidates = []

        for index, paragraph in enumerate(
            paragraphs
        ):
            result = score_paragraph(
                paragraph,
                keywords,
            )

            if result is None:
                continue

            candidates.append(
                {
                    "paragraph_id":
                        f"P{index + 1:03d}",

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

                    "text":
                        paragraph,
                }
            )

        candidates.sort(
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
            candidates[:max_per_theme]
        )

    return results


# =========================
# Print debug results
# =========================

def print_results(results):
    for theme, candidates in (
        results.items()
    ):
        print(
            "\n\n"
            + "=" * 80
        )

        print(
            f"TOP 10 — {theme}"
        )

        print(
            "=" * 80
        )

        if not candidates:
            print(
                "\n❌ No candidates found."
            )
            continue

        for rank, item in enumerate(
            candidates,
            start=1,
        ):
            print(
                f"\n--- Rank {rank} ---"
            )

            print(
                f"Evidence ID: "
                f"{item['paragraph_id']}"
            )

            print(
                f"Score: "
                f"{item['score']}"
            )

            print(
                "Theme matches: "
                + ", ".join(
                    item[
                        "matched_keywords"
                    ]
                )
            )

            if item[
                "matched_causal_terms"
            ]:
                print(
                    "Causal matches: "
                    + ", ".join(
                        item[
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
                + item["text"]
            )


# =========================
# AAPL retrieval debug
# =========================

if __name__ == "__main__":
    ticker = "AAPL"

    print(
        f"\n正在运行 {ticker} "
        "Retrieval Debug..."
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
        "\n正在读取 SEC 10-K..."
    )

    html = download_html(url)

    text = html_to_text(html)

    mda = extract_mda(text)

    if not mda:
        raise ValueError(
            "MD&A 提取失败"
        )

    paragraphs = split_paragraphs(
        mda
    )

    print(
        f"\n✅ MD&A length: "
        f"{len(mda):,} characters"
    )

    print(
        f"✅ Paragraphs: "
        f"{len(paragraphs)}"
    )

    print(
        "\n正在生成每个主题的 "
        "Top 10 Retrieval Candidates..."
    )

    results = rank_candidates(
        mda,
        max_per_theme=10,
    )

    print_results(
        results
    )