"""One-off generator for the TechCon abstract Word document.

Not part of the dq-platform package; run manually when the abstract needs to
be regenerated:

    .\\.venv\\Scripts\\python.exe scripts\\generate_techcon_paper.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "reports" / "TechCon_Abstract_Data_Quality_Platform.docx"
ARCHITECTURE_DIAGRAM_PATH = Path(__file__).resolve().parent.parent / "reports" / "architecture_diagram.png"

HPE_GREEN = RGBColor(0x01, 0xA9, 0x82)
DARK = RGBColor(0x1A, 0x1A, 0x1A)

AUTHOR = "Shreya Das"
BUSINESS_UNIT = "DT&A Growth Insights \u2013 Business Insights"
EMAIL = "shreya.das@hpe.com"
TITLE = "A Registry-Driven Data Quality and Revenue Validation Platform for S/4HANA Renewal Data"


def add_page_break(doc: Document) -> None:
    doc.add_page_break()


def set_heading_style(paragraph, size=16, bold=True, color=DARK, align=WD_ALIGN_PARAGRAPH.LEFT, space_after=6):
    paragraph.alignment = align
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = color
    paragraph.paragraph_format.space_after = Pt(space_after)


def add_section_heading(doc: Document, text: str):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(13)
    run.font.color.rgb = HPE_GREEN
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    return p


def add_body(doc: Document, text: str, space_after=8):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(space_after)
    for run in p.runs:
        run.font.size = Pt(10.5)
    return p


def add_bullets(doc: Document, items: list[str]):
    for item in items:
        p = doc.add_paragraph(item, style="List Bullet")
        p.paragraph_format.space_after = Pt(3)
        for run in p.runs:
            run.font.size = Pt(10.5)


def set_default_font(doc: Document):
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), "Calibri")


def build_cover_page(doc: Document):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(160)
    run = p.add_run(TITLE)
    run.bold = True
    run.font.size = Pt(20)
    run.font.color.rgb = DARK

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_before = Pt(30)
    run2 = p2.add_run(AUTHOR)
    run2.font.size = Pt(14)

    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run3 = p3.add_run(BUSINESS_UNIT)
    run3.font.size = Pt(12)

    p4 = doc.add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run4 = p4.add_run(EMAIL)
    run4.font.size = Pt(12)
    run4.font.color.rgb = RGBColor(0x05, 0x63, 0xC1)


def build_technical_pages(doc: Document):
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title_p.add_run(TITLE)
    run.bold = True
    run.font.size = Pt(16)
    title_p.paragraph_format.space_after = Pt(14)

    add_section_heading(doc, "Abstract")
    add_body(
        doc,
        "This paper presents a registry-driven data quality and revenue-validation platform built to "
        "check S/4HANA renewal and contract data against HPE's business rules before it reaches "
        "downstream reporting. The key innovation is a single rule registry that drives the notebook "
        "UI, the preset bundles and the execution engine from one source of truth, so a new check "
        "becomes available everywhere the moment it is registered \u2014 no UI code, no duplicated lists. "
        "On top of this engine sits a dedicated Revenue Validation flow that compares old-vs-new "
        "renewal extracts for channel-profile, document-type and renewal-completeness rules, and a "
        "combined-report mode that merges Data Quality and Revenue Validation results, with charts and "
        "a decision-tree root cause analysis that explains why checks failed, into one Excel workbook "
        "and one HTML dashboard. The platform already validates live S/4HANA renewal data for the Growth Insights "
        "team and is built so any tabular source \u2014 Excel today, SQL Server now, UDP/IBSV/Delta next \u2014 "
        "can be plugged in without touching the rule logic.",
    )

    add_section_heading(doc, "Problem statement")
    add_body(
        doc,
        "Renewal and revenue data drawn from S/4HANA passes through several hand-offs \u2014 extraction, "
        "transformation, and reconciliation between old and new sources \u2014 before it is trusted for "
        "business reporting. Today that trust is established manually: an analyst opens a workbook in "
        "Excel, eyeballs columns for blanks, duplicates and formatting errors, and manually diffs old "
        "versus new renewal totals and renewal-document completeness. This is slow, inconsistent "
        "between analysts, and does not scale as the number of checks or the number of data sources "
        "grows. It also means every new validation requirement (e.g. \u201cTier 2 reseller must be set "
        "when channel profile is indirect\u201d) turns into another one-off spreadsheet formula or macro "
        "that nobody else can reuse or audit.",
    )
    add_body(
        doc,
        "This matters to HPE because revenue and renewal numbers feed directly into business "
        "reporting and decision-making. Undetected data-quality defects \u2014 missing renewal quote "
        "numbers, mismatched document types, revenue deltas beyond tolerance \u2014 propagate into "
        "downstream dashboards and can misstate renewal health. A repeatable, auditable, low-effort "
        "way to catch these issues before they reach reporting reduces rework for the Growth Insights "
        "team and increases confidence in the numbers leadership consumes.",
    )

    add_section_heading(doc, "Our solution")
    add_body(
        doc,
        "The platform's core innovation is treating every data-quality check as a declarative entry in "
        "a rule registry (id, label, quality dimension, required column count, and parameters) rather "
        "than as bespoke code wired into a UI. The notebook UI, the named preset bundles, and the "
        "execution engine all read from this one registry, so authoring a new rule automatically makes "
        "it selectable in the UI, usable in presets, and runnable headlessly \u2014 there is no second "
        "place to update. Twenty-five rule runners are implemented today across six quality dimensions "
        "(completeness, uniqueness, validity, consistency, hygiene and distribution), each isolated so "
        "that one failing or erroring rule cannot stop the rest of the run from completing.",
    )
    add_body(
        doc,
        "On top of the generic engine, we built a Revenue Validation flow specific to the renewal "
        "use case: it loads an \u2018old\u2019 and a \u2018new\u2019 extract (from Excel or SQL Server), filters by a "
        "configurable document-type value, compares old-vs-new revenue totals against a configurable "
        "percentage threshold, and separately checks renewal completeness (renewal quote number and "
        "renewal contract document number must both be populated wherever the renewal status matches "
        "a configured value), flagging either source when missing-data percentage exceeds threshold. "
        "A hybrid mode runs Data Quality and Revenue Validation together and emits one combined Excel "
        "workbook and one combined HTML dashboard, ordered as summary \u2192 charts \u2192 details, so a "
        "reviewer gets a single artifact instead of stitching two reports together.",
    )
    add_body(
        doc,
        "A further innovation is decision-tree root cause analysis in the dashboard's AI Insights "
        "section, which explains why checks failed rather than only that they failed, with no external "
        "AI service. Two trees work together. A rule-based tree walks each failing finding through "
        "fixed branches to a root-cause hypothesis \u2014 for example, a revenue delta over threshold is "
        "tested for unreadable revenue values, then for a matching change in record volume, before "
        "being attributed to a per-record value change such as pricing or column mapping. A learned "
        "CART tree (scikit-learn DecisionTreeClassifier [4][5]) is trained per failing check on the "
        "row-level data and surfaces the segments where failures concentrate, e.g. \u201cmost failures "
        "fall in Region = APJ AND Channel = Indirect, at several times the overall failure rate\u201d. "
        "Every finding shows its evidence and the decision path taken, so the output is deterministic "
        "and auditable, and it is worded as association rather than proven cause.",
    )
    add_body(
        doc,
        "The architecture was deliberately layered (presentation \u2192 configuration \u2192 execution \u2192 data "
        "access \u2192 output) with dependencies flowing one way, so the engine, rules, presets and report "
        "writers never import from the UI layer. This is what lets the whole platform run headlessly "
        "as a plain script, and it is also what makes the proposed Databricks migration (see Next "
        "Steps) a connector swap rather than a rewrite: only io_utils.py currently knows what \u2018Excel\u2019 "
        "means, and the SQL Server connector added for live S/4HANA use already proves the same "
        "registry pattern extends cleanly to a second data source. Figure 1 shows the five layers and "
        "how a check flows from the notebook UI down to the Excel and HTML outputs.",
    )

    if ARCHITECTURE_DIAGRAM_PATH.exists():
        img_p = doc.add_paragraph()
        img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img_p.paragraph_format.space_before = Pt(6)
        img_p.paragraph_format.space_after = Pt(4)
        run = img_p.add_run()
        run.add_picture(str(ARCHITECTURE_DIAGRAM_PATH), width=Inches(6.3))

    add_section_heading(doc, "Evidence the solution works")
    add_body(
        doc,
        "The platform is in active use validating real S/4HANA renewal data for business use cases in "
        "the Growth Insights team, with two analysts (Prakash and Madhan) as the primary users running "
        "it against live extracts rather than synthetic samples. Its rule-registry design was "
        "specifically validated by extension in practice: the renewal-completeness and revenue-delta "
        "checks, the SQL Server connector, and the combined-report/AI-Insights layer were all added "
        "after the original single-source Data Quality tool was working, and each was added without "
        "modifying the core engine, registry contract or existing rule runners \u2014 direct evidence that "
        "the one-way layered architecture achieves its goal of isolating change. A companion script "
        "generates a sample workbook with one planted defect per check, which is used as a regression "
        "fixture together with an automated pytest suite to confirm every rule still fires correctly "
        "after a change, before it is pointed at real data.",
    )

    add_section_heading(doc, "Competitive approaches")
    add_body(
        doc,
        "Generic data-quality tooling exists at both ends of the market. Great Expectations (now "
        "stewarded as \u201cGX Core\u201d) is the closest open-source analogue: like this platform it expresses "
        "checks declaratively and integrates with Python pipelines, but it is detect-only, requires "
        "engineers to write/maintain YAML or Python \u2018expectations\u2019 per dataset, and has no built-in "
        "business-user UI or Excel/HTML reporting \u2014 it is a library, not a point-and-click tool for "
        "an analyst [1]. "
        "Commercial suites such as Informatica Data Quality and Talend Data Quality offer GUI-based "
        "profiling, cleansing and enterprise governance at a scale and cost (Informatica is "
        "subscription-priced for enterprise deployments) that is disproportionate to a focused "
        "renewal-validation need, and neither ships the renewal/revenue-comparison logic this platform "
        "was built for out of the box [2][3].",
    )
    add_body(
        doc,
        "This platform's advantage over the open-source option is usability \u2014 a non-engineer analyst "
        "configures checks through the notebook widget UI with no code \u2014 and over the commercial "
        "options is cost and specificity \u2014 it needed no procurement cycle and encodes HPE-specific "
        "renewal rules (channel-profile/Tier-2-reseller, document-type filtering, renewal-document "
        "completeness) that a generic tool does not provide. Its disadvantage against both is maturity "
        "and scale: it currently handles Excel and SQL Server sources and runs per-analyst from a "
        "notebook, whereas the commercial tools (and GX at larger shops) support broader source "
        "catalogs, scheduled/orchestrated runs, and multi-team governance out of the box \u2014 gaps the "
        "Databricks migration in Next Steps is designed to close.",
    )

    add_section_heading(doc, "Current status")
    add_body(
        doc,
        "The platform is deployed and in day-to-day use validating live S/4HANA renewal data within the "
        "Growth Insights team, run from a local Python virtual environment through a Jupyter notebook "
        "UI, with both the single-source Data Quality flow and the dual-source Revenue Validation flow "
        "available, plus the hybrid combined-report mode and decision-tree root cause analysis. SQL "
        "Server connectivity is implemented alongside the original Excel path, so the same checks can "
        "be run directly against source tables as they can against exported workbooks. By the time "
        "TechCon takes place, we expect to have extended real-world usage to additional renewal "
        "datasets and use cases within the team and to have made measurable progress on the Databricks "
        "connector design described below.",
    )

    add_section_heading(doc, "Next steps")
    add_body(
        doc,
        "The architecture was built so that generalizing beyond Excel/SQL Server is a connector "
        "addition, not a redesign: a planned pluggable DataSource interface (mirroring the existing "
        "RuleDefinition registry pattern) will let UDP, IBSV and Delta tables be selected from the "
        "same dropdown as Excel and SQL Server today, with the engine, registry, rules and report "
        "writers unchanged. Moving execution onto Databricks is the natural next step for running "
        "checks at the scale and schedule the business needs, rather than per-analyst from a notebook, "
        "and would let the same checks run as a scheduled job against production tables with results "
        "pushed to a shared location instead of a local reports folder.",
    )
    add_body(
        doc,
        "Beyond infrastructure, there is real business value in widening adoption: onboarding more "
        "analysts and teams onto the existing notebook tool immediately, growing the preset catalog "
        "as new renewal/revenue edge cases are discovered, and using the refresh history "
        "(dq_history.json) to surface quality drift over time rather than only point-in-time results. "
        "Further work is still required on automated scheduling/alerting so that failures are pushed "
        "to owners rather than discovered on the next manual run, and on broadening the Revenue "
        "Validation rule set to additional business cases beyond channel-profile/Tier-2 and "
        "renewal-completeness as new requirements surface.",
    )

    add_section_heading(doc, "Acknowledgements")
    add_body(
        doc,
        "Thanks to Prakash and Madhan for using the platform against real renewal data and surfacing "
        "the business rules (channel-profile/Tier-2 reseller, renewal-completeness thresholds) that "
        "shaped the Revenue Validation flow. GitHub Copilot (Copilot SDK in VS Code) was used as an "
        "AI coding assistant to help implement portions of the codebase and documentation, and to help "
        "draft and edit this abstract; all technical claims and figures were reviewed by the author "
        "against the actual codebase and real usage before submission.",
    )

    add_section_heading(doc, "References")
    add_bullets(
        doc,
        [
            "[1] Great Expectations / GX Core \u2014 open-source data validation framework for Python pipelines. "
            "https://greatexpectations.io/",
            "[2] Informatica Data Quality \u2014 commercial enterprise data quality platform (profiling, "
            "cleansing, governance). https://www.informatica.com/products/data-quality.html",
            "[3] Talend Data Quality \u2014 commercial/legacy-open-source data profiling and cleansing tool. "
            "https://www.talend.com/products/data-quality/",
            "[4] L. Breiman, J. Friedman, R. Olshen, C. Stone, Classification and Regression Trees, "
            "Wadsworth, 1984.",
            "[5] F. Pedregosa et al., \u201cScikit-learn: Machine Learning in Python\u201d, Journal of Machine "
            "Learning Research 12, pp. 2825\u20132830, 2011. https://jmlr.org/papers/v12/pedregosa11a.html",
        ],
    )


def main():
    doc = Document()
    set_default_font(doc)

    section = doc.sections[0]
    section.left_margin = Pt(62)
    section.right_margin = Pt(62)
    section.top_margin = Pt(54)
    section.bottom_margin = Pt(54)

    build_cover_page(doc)
    add_page_break(doc)
    build_technical_pages(doc)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT_PATH)
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
