import json
import urllib.request
from datetime import date


# =========================
# SEC configuration
# =========================

HEADERS = {
    "User-Agent": "AI-Company-Research-Assistant demo@example.com",
}


# =========================
# HTTP helper
# =========================

def get_json(url):
    request = urllib.request.Request(
        url,
        headers=HEADERS,
    )

    with urllib.request.urlopen(
        request,
        timeout=20,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


# =========================
# Ticker → CIK
# =========================

def ticker_to_company(ticker):
    ticker = ticker.strip().upper()

    url = (
        "https://www.sec.gov/files/"
        "company_tickers.json"
    )

    companies = get_json(url)

    for company in companies.values():
        if company["ticker"].upper() == ticker:
            return {
                "ticker": ticker,
                "cik": str(
                    company["cik_str"]
                ).zfill(10),
                "company_name": company["title"],
            }

    raise ValueError(
        f"SEC 中没有找到股票代码：{ticker}"
    )


# =========================
# Latest 10-K
# =========================

def get_latest_10k(cik):
    url = (
        "https://data.sec.gov/submissions/"
        f"CIK{cik}.json"
    )

    submissions = get_json(url)

    recent = submissions["filings"]["recent"]

    for index, form in enumerate(recent["form"]):
        if form == "10-K":
            return {
                "company_name": submissions["name"],
                "form": form,
                "filing_date":
                    recent["filingDate"][index],
                "report_date":
                    recent["reportDate"][index],
                "accession_number":
                    recent["accessionNumber"][index],
                "primary_document":
                    recent["primaryDocument"][index],
            }

    raise ValueError(
        "没有在 SEC recent filings 中找到 10-K"
    )


# =========================
# SEC Company Facts
# =========================

def get_company_facts(cik):
    url = (
        "https://data.sec.gov/api/xbrl/"
        f"companyfacts/CIK{cik}.json"
    )

    return get_json(url)


# =========================
# Candidate concepts
# =========================

METRIC_CONCEPTS = {
    "Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],

    "Net Income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],

    "Operating Income": [
        "OperatingIncomeLoss",
    ],

    "Operating Cash Flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
}


# =========================
# Period validation
# =========================

def period_days(start, end):
    if not start or not end:
        return None

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    return (end_date - start_date).days


def is_full_year_fact(fact):
    """
    防止把季度或九个月数据误当成年报。

    大多数完整财年大约 365 天。
    52/53 周财年也会落在这个范围附近。
    """

    days = period_days(
        fact.get("start"),
        fact.get("end"),
    )

    if days is None:
        return False

    return 330 <= days <= 380


# =========================
# Select fact for one year
# =========================

def find_fact_for_period(
    company_facts,
    concept_candidates,
    target_end_date,
):
    us_gaap = (
        company_facts
        .get("facts", {})
        .get("us-gaap", {})
    )

    for concept_name in concept_candidates:

        concept = us_gaap.get(concept_name)

        if not concept:
            continue

        usd_facts = (
            concept
            .get("units", {})
            .get("USD", [])
        )

        matches = []

        for fact in usd_facts:

            if fact.get("form") != "10-K":
                continue

            if fact.get("end") != target_end_date:
                continue

            if fact.get("fp") not in ("FY", None):
                continue

            if "val" not in fact:
                continue

            if not is_full_year_fact(fact):
                continue

            matches.append(fact)

        if not matches:
            continue

        # Prefer a fact actually filed as part of the
        # 10-K for that fiscal period.
        matches.sort(
            key=lambda item: item.get("filed", ""),
            reverse=True,
        )

        selected = matches[0]

        return {
            "concept": concept_name,
            "label": concept.get(
                "label",
                concept_name,
            ),
            "value": selected["val"],
            "unit": "USD",
            "start": selected.get("start"),
            "end": selected.get("end"),
            "filed": selected.get("filed"),
            "form": selected.get("form"),
            "fp": selected.get("fp"),
            "accession_number":
                selected.get("accn"),
            "period_days": period_days(
                selected.get("start"),
                selected.get("end"),
            ),
        }

    return None


# =========================
# Discover annual periods
# =========================

def get_annual_periods(
    company_facts,
    concept_candidates,
):
    us_gaap = (
        company_facts
        .get("facts", {})
        .get("us-gaap", {})
    )

    periods = set()

    for concept_name in concept_candidates:

        concept = us_gaap.get(concept_name)

        if not concept:
            continue

        usd_facts = (
            concept
            .get("units", {})
            .get("USD", [])
        )

        for fact in usd_facts:

            if fact.get("form") != "10-K":
                continue

            if fact.get("fp") not in ("FY", None):
                continue

            if not is_full_year_fact(fact):
                continue

            end_date = fact.get("end")

            if end_date:
                periods.add(end_date)

    return sorted(
        periods,
        reverse=True,
    )


# =========================
# YoY calculation
# =========================

def calculate_yoy(current, previous):
    if current is None or previous is None:
        return None

    if previous == 0:
        return None

    return (
        (current - previous)
        / abs(previous)
        * 100
    )


# =========================
# Extract current + previous
# =========================

def extract_metric_comparison(
    company_facts,
    concept_candidates,
    current_report_date,
):
    current = find_fact_for_period(
        company_facts,
        concept_candidates,
        current_report_date,
    )

    if current is None:
        return {
            "current": None,
            "previous": None,
            "yoy_percent": None,
        }

    annual_periods = get_annual_periods(
        company_facts,
        concept_candidates,
    )

    previous_periods = [
        period
        for period in annual_periods
        if period < current_report_date
    ]

    previous = None

    for previous_end_date in previous_periods:

        candidate = find_fact_for_period(
            company_facts,
            concept_candidates,
            previous_end_date,
        )

        if candidate is None:
            continue

        # Previous fiscal year should normally end
        # roughly one year before the current one.
        gap = (
            date.fromisoformat(current["end"])
            - date.fromisoformat(candidate["end"])
        ).days

        if 330 <= gap <= 400:
            previous = candidate
            break

    yoy = None

    if previous is not None:
        yoy = calculate_yoy(
            current["value"],
            previous["value"],
        )

    return {
        "current": current,
        "previous": previous,
        "yoy_percent": yoy,
    }


# =========================
# Four core metrics
# =========================

def extract_core_metrics(
    company_facts,
    report_date,
):
    results = {}

    for metric_name, candidates in (
        METRIC_CONCEPTS.items()
    ):
        results[metric_name] = (
            extract_metric_comparison(
                company_facts,
                candidates,
                report_date,
            )
        )

    return results


# =========================
# Company snapshot
# =========================

def build_company_snapshot(ticker):
    company = ticker_to_company(ticker)

    filing = get_latest_10k(
        company["cik"]
    )

    facts = get_company_facts(
        company["cik"]
    )

    metrics = extract_core_metrics(
        facts,
        filing["report_date"],
    )

    return {
        "company": company,
        "filing": filing,
        "metrics": metrics,
    }


# =========================
# Formatting
# =========================

def format_usd(value):
    if value is None:
        return "N/A"

    return (
        f"${value / 1_000_000_000:,.2f}B"
    )


def format_yoy(value):
    if value is None:
        return "N/A"

    return f"{value:+.1f}%"


# =========================
# Print test result
# =========================

def print_snapshot(snapshot):
    company = snapshot["company"]
    filing = snapshot["filing"]
    metrics = snapshot["metrics"]

    print("\n" + "=" * 64)

    print(
        f"{company['company_name']} "
        f"({company['ticker']})"
    )

    print("=" * 64)

    print(
        f"Latest 10-K report date: "
        f"{filing['report_date']}"
    )

    print(
        f"Filed: {filing['filing_date']}"
    )

    print("\n核心财务指标：")

    for metric_name, comparison in metrics.items():

        print("\n" + metric_name)

        current = comparison["current"]
        previous = comparison["previous"]
        yoy = comparison["yoy_percent"]

        if current is None:
            print("  ❌ 当前财年数据未找到")
            continue

        print(
            f"  Current: "
            f"{format_usd(current['value'])}"
        )

        print(
            f"  Current period: "
            f"{current['start']} → "
            f"{current['end']} "
            f"({current['period_days']} days)"
        )

        if previous is None:
            print(
                "  Previous: ❌ 未找到"
            )
        else:
            print(
                f"  Previous: "
                f"{format_usd(previous['value'])}"
            )

            print(
                f"  Previous period: "
                f"{previous['start']} → "
                f"{previous['end']} "
                f"({previous['period_days']} days)"
            )

        print(
            f"  YoY: {format_yoy(yoy)}"
        )

        print(
            f"  XBRL concept: "
            f"{current['concept']}"
        )


# =========================
# Cross-company test
# =========================

if __name__ == "__main__":

    test_tickers = [
        "AAPL",
        "MSFT",
        "NVDA",
    ]

    for ticker in test_tickers:

        try:
            print(
                f"\n正在从 SEC 查询 {ticker}..."
            )

            snapshot = (
                build_company_snapshot(ticker)
            )

            print_snapshot(snapshot)

        except Exception as error:

            print(
                f"\n❌ {ticker} 查询失败："
            )

            print(error)