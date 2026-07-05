"""Analytics Runner — Chạy toàn bộ phân tích và sinh báo cáo thống nhất.

Kết nối tất cả module analytics thành một pipeline duy nhất:
  KPI Snapshot → Contribution → Drill-down → Causal
  → Insight → Decision Support → Báo cáo Markdown

Usage:
  from src.analytics.runner import AnalyticsRunner

  runner = AnalyticsRunner(engine, period_key="2014Q2")
  report_path = runner.run()
  # => reports/analytics_report_2014Q2.md
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.analytics.kpi_calculator import (
    calculate_kpi,
    calculate_all_kpis,
    get_quarter_boundaries,
    get_period_key,
    KPI_DEFINITIONS,
    DIMENSION_KPIS,
)
from src.analytics.contribution import contribution_breakdown, save_period_comparison
from src.analytics.drill_down import drill_down
from src.analytics.insight_generator import (
    generate_revenue_insight,
    generate_hhi_insight,
    generate_inventory_turnover_insight,
    generate_retention_insight,
    _kpi_label,
    _fmt_value,
)
from src.analytics.causal import price_elasticity
from src.analytics.hypothesis_tester import (
    two_sample_ttest,
    chi_square_cluster_test,
    trend_significance_test,
)
from src.ml.decision_support import run_decision_support

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"


class AnalyticsRunner:
    """Orchestrator chạy toàn bộ phân tích và sinh báo cáo tổng hợp."""

    def __init__(
        self,
        engine: Engine,
        period_key: Optional[str] = None,
        output_dir: Path = REPORTS_DIR,
    ):
        self.engine = engine
        self.period_key = period_key
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.curr_start = ""
        self.curr_end = ""
        self.prev_start = ""
        self.prev_end = ""
        self.prev_period_key = ""

        self.kpi_data: dict[str, dict] = {}
        self.dim_kpi_data: dict[str, list[dict]] = {}
        self.insights: list[dict] = []
        self.contributions: list[dict] = []
        self.drill_steps: list[dict] = []
        self.causal_results: list[dict] = []
        self.anomalies: list[dict] = []
        self.decisions: list[dict] = []
        self.hypothesis_results: list[dict] = []

    def _resolve_period(self) -> None:
        if self.period_key:
            pk = self.period_key
        else:
            try:
                with open(CONFIG_PATH) as f:
                    cfg = json.load(f)
                pk = cfg.get("snapshot_watermark", "2014Q2")
            except (FileNotFoundError, json.JSONDecodeError):
                pk = "2014Q2"

        year = int(pk[:4])
        quarter = int(pk[5])
        self.curr_start, self.curr_end = get_quarter_boundaries(year, quarter)
        self.period_key = pk

        if quarter == 1:
            py, pq = year - 1, 4
        else:
            py, pq = year, quarter - 1
        self.prev_start, self.prev_end = get_quarter_boundaries(py, pq)
        self.prev_period_key = get_period_key("Q", py, pq)

        logger.info(
            "Kỳ: %s (%s → %s) | So sánh: %s (%s → %s)",
            self.period_key, self.curr_start, self.curr_end,
            self.prev_period_key, self.prev_start, self.prev_end,
        )

    def _load_kpi_data(self) -> None:
        query = """
            SELECT kpi_name, period_key, value, dimension, dimension_value
            FROM mart.kpi_snapshot
            WHERE period_key IN (:curr_pk, :prev_pk)
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(
                text(query),
                conn,
                params={"curr_pk": self.period_key, "prev_pk": self.prev_period_key},
            )

        if df.empty:
            logger.info("Snapshot rỗng — tính live...")
            curr = calculate_all_kpis(self.engine, self.curr_start, self.curr_end)
            prev = calculate_all_kpis(self.engine, self.prev_start, self.prev_end)
            df = pd.DataFrame(curr + prev)

        all_kpi_names = set(KPI_DEFINITIONS) | set(DIMENSION_KPIS)

        for kpi_name in all_kpi_names:
            kdf = df[df["kpi_name"] == kpi_name]
            if kdf.empty:
                continue
            if kpi_name in DIMENSION_KPIS:
                rows = []
                for _, r in kdf.iterrows():
                    rows.append({
                        "dimension_value": r.get("dimension_value", "overall"),
                        "value": float(r["value"]) if r["value"] is not None else 0,
                        "period_key": r["period_key"],
                    })
                self.dim_kpi_data[kpi_name] = rows
            else:
                curr_row = kdf[kdf["period_key"] == self.period_key]
                prev_row = kdf[kdf["period_key"] == self.prev_period_key]
                cv = float(curr_row.iloc[0]["value"]) if not curr_row.empty else 0
                pv = float(prev_row.iloc[0]["value"]) if not prev_row.empty else 0
                ch = cv - pv
                pct = (ch / pv * 100) if pv != 0 else 0
                self.kpi_data[kpi_name] = {
                    "curr": cv,
                    "prev": pv,
                    "change": ch,
                    "pct_change": round(pct, 2),
                }
        logger.info("KPI data: %d overall + %d dimension", len(self.kpi_data), len(self.dim_kpi_data))

    def _generate_insights(self) -> None:
        revenue_kpis = {
            "revenue", "gross_profit", "gross_margin_pct",
            "order_count", "total_customers", "avg_order_value",
            "revenue_per_customer",
        }
        for name, d in self.kpi_data.items():
            if name in revenue_kpis:
                related_contrib = [c for c in self.contributions if c["kpi_name"] == name]
                ins = generate_revenue_insight(
                    kpi_name=name, curr_value=d["curr"],
                    prev_value=d["prev"], pct_change=d["pct_change"],
                    contributions=related_contrib if related_contrib else None,
                    drill_down_path=self.drill_steps if self.drill_steps else None,
                )
            elif name == "hhi_revenue_concentration":
                ins = generate_hhi_insight(
                    kpi_name=name, curr_value=d["curr"],
                    prev_value=d["prev"], pct_change=d["pct_change"],
                )
            elif name == "inventory_turnover":
                cat_data = self.dim_kpi_data.get("inventory_turnover_by_category", [])
                ins = generate_inventory_turnover_insight(
                    kpi_name=name, curr_value=d["curr"],
                    prev_value=d["prev"], pct_change=d["pct_change"],
                    category_breakdown=cat_data,
                )
            elif name == "repeat_customer_rate":
                brk = self.dim_kpi_data.get("repeat_rate_by_customer_type", [])
                ins = generate_retention_insight(
                    kpi_name=name, curr_value=d["curr"],
                    prev_value=d["prev"], pct_change=d["pct_change"],
                    breakdown=brk,
                )
            else:
                continue
            self.insights.append(ins)

        self.insights.sort(key=lambda x: (
            {"critical": 0, "warning": 1, "info": 2}.get(x["severity"], 3),
            abs(x.get("pct_change", 0)),
        ), reverse=True)
        logger.info("Insights generated: %d", len(self.insights))

    def _run_contribution(self) -> None:
        for kpi in ["revenue", "gross_margin_pct"]:
            for dim in ["category", "territory", "customer_type"]:
                try:
                    res = contribution_breakdown(
                        self.engine, kpi,
                        self.curr_start, self.curr_end,
                        self.prev_start, self.prev_end,
                        dimension=dim,
                    )
                    self.contributions.extend(res)
                    save_period_comparison(self.engine, res)
                except Exception as e:
                    logger.debug("Contribution %s/%s: %s", kpi, dim, e)
        logger.info("Contribution: %d rows", len(self.contributions))

    def _run_drill_down(self) -> None:
        try:
            self.drill_steps = drill_down(
                self.engine, "revenue",
                self.curr_start, self.curr_end,
                self.prev_start, self.prev_end,
            )
        except Exception as e:
            logger.debug("Drill-down: %s", e)
        logger.info("Drill-down: %d steps", len(self.drill_steps))

    def _run_causal(self) -> None:
        for cat in ["Bikes", "Clothing", "Accessories"]:
            try:
                res = price_elasticity(self.engine, category=cat, period="quarterly")
                if "error" not in res:
                    self.causal_results.append(res)
            except Exception as e:
                logger.debug("Causal %s: %s", cat, e)
        logger.info("Causal: %d results", len(self.causal_results))

    def _run_hypothesis_tests(self) -> None:
        """Chạy các kiểm định thống kê cho các giả thuyết kinh doanh."""
        try:
            h1 = two_sample_ttest(
                self.engine, "line_total",
                "Bikes", "p.category = 'Bikes'",
                "Accessories", "p.category = 'Accessories'",
                self.curr_start, self.curr_end,
            )
            h1["hypothesis"] = "H1: Bikes có giá trị đơn hàng cao hơn Accessories"
            self.hypothesis_results.append(h1)
        except Exception as e:
            logger.debug(f"H1 failed: {e}")

        try:
            h2 = two_sample_ttest(
                self.engine, "line_total",
                "Store", "c.customer_type = 'Store'",
                "Individual", "c.customer_type = 'Individual'",
                self.curr_start, self.curr_end,
            )
            h2["hypothesis"] = "H2: Store customers có giá trị cao hơn Individual"
            self.hypothesis_results.append(h2)
        except Exception as e:
            logger.debug(f"H2 failed: {e}")

        try:
            h3 = trend_significance_test(self.engine, "revenue")
            h3["hypothesis"] = "H3: Doanh thu có xu hướng tăng theo quý"
            self.hypothesis_results.append(h3)
        except Exception as e:
            logger.debug(f"H3 failed: {e}")

        try:
            h4 = chi_square_cluster_test(
                self.engine, self.prev_period_key, self.period_key,
            )
            h4["hypothesis"] = "H4: Phân phối cluster thay đổi có ý nghĩa giữa 2 kỳ"
            self.hypothesis_results.append(h4)
        except Exception as e:
            logger.debug(f"H4 failed: {e}")

        logger.info("Hypothesis tests: %d results", len(self.hypothesis_results))

    def _load_anomalies(self) -> None:
        try:
            q = """
                SELECT product_name, category,
                       days_inventory_outstanding, inventory_value, anomaly_score
                FROM dw.ml_inventory_anomaly
                WHERE anomaly_flag = true
                ORDER BY days_inventory_outstanding DESC LIMIT 10
            """
            with self.engine.connect() as conn:
                df = pd.read_sql(text(q), conn)
            self.anomalies = df.to_dict("records")
        except Exception as e:
            logger.debug("Anomalies: %s", e)
        logger.info("Anomalies: %d products", len(self.anomalies))

    def _run_decision_support(self) -> None:
        try:
            run_decision_support(self.engine)
            q = """
                SELECT signal_type, priority, recommended_action, reason
                FROM dw.decision_support
                WHERE priority IN ('HIGH', 'MEDIUM')
                ORDER BY CASE priority WHEN 'HIGH' THEN 0 ELSE 1 END
                LIMIT 15
            """
            with self.engine.connect() as conn:
                df = pd.read_sql(text(q), conn)
            self.decisions = df.to_dict("records")
        except Exception as e:
            logger.debug("Decision support: %s", e)
        logger.info("Decision support: %d items", len(self.decisions))

    def _build_report(self) -> str:
        L = []

        def w(s=""):
            L.append(s)

        w(f"# Báo cáo Phân tích Kinh doanh — Kỳ {self.period_key}")
        w()
        w(f"- **Ngày tạo:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w(f"- **Kỳ phân tích:** {self.curr_start} → {self.curr_end}")
        w(f"- **Kỳ so sánh:** {self.prev_start} → {self.prev_end}")
        w()
        w("---")
        w()

        # ── 1. KPI Overview ──
        w("## 1. Tổng quan KPI")
        w()
        w("| KPI | Kỳ này | Kỳ trước | Thay đổi | % |")
        w("|---|---|---|---|---|")
        order = [
            "revenue", "gross_profit", "gross_margin_pct",
            "order_count", "total_customers", "avg_order_value",
            "revenue_per_customer", "inventory_turnover",
            "repeat_customer_rate", "hhi_revenue_concentration",
        ]
        for name in order:
            if name not in self.kpi_data:
                continue
            d = self.kpi_data[name]
            cv = d["curr"]
            pv = d["prev"]
            ch = d["change"]
            pc = d["pct_change"]
            arrow = "(+)" if pc > 0 else ("(-)" if pc < 0 else "(=)")
            w(
                f"| {_kpi_label(name)} "
                f"| {_fmt_value(cv, name)} "
                f"| {_fmt_value(pv, name)} "
                f"| {_fmt_value(abs(ch), name)} "
                f"| {arrow} {pc:+.1f}% |"
            )
        w()

        # ── 2. Critical Insights ──
        critical = [i for i in self.insights if i["severity"] == "critical"]
        warnings = [i for i in self.insights if i["severity"] == "warning"]
        if critical or warnings:
            w("## 2. Phát hiện chính")
            w()
            for ins in critical + warnings:
                first, *rest = ins["insight_text"].split("\n")
                w(f"### {first}")
                w()
                for line in rest:
                    w(f"  {line}")
                w()

        # ── 3. HHI ──
        if "hhi_revenue_concentration" in self.kpi_data:
            w("## 3. Rủi ro chiến lược — Mức độ tập trung doanh thu")
            w()
            d = self.kpi_data["hhi_revenue_concentration"]
            hhi = d["curr"]
            if hhi > 0.6:
                w(f"> **Cảnh báo**: HHI = {hhi:.3f} (> 0.6). Doanh thu phụ thuộc quá nhiều vào một danh mục sản phẩm.")
            elif hhi > 0.4:
                w(f"> **Theo dõi**: HHI = {hhi:.3f} (0.4–0.6). Cần theo dõi xu hướng tập trung.")
            else:
                w(f"> HHI = {hhi:.3f} (< 0.4). Danh mục sản phẩm tương đối đa dạng.")
            w()
            cat_data = self.dim_kpi_data.get("revenue_by_category", [])
            curr_cats = [c for c in cat_data if c["period_key"] == self.period_key]
            if curr_cats:
                total = sum(c["value"] for c in curr_cats)
                w("**Phân bố doanh thu theo danh mục:**")
                w()
                w("| Danh mục | Doanh thu | Tỷ trọng |")
                w("|---|---|---|")
                for c in sorted(curr_cats, key=lambda x: x["value"], reverse=True):
                    share = c["value"] / total * 100 if total > 0 else 0
                    w(f"| {c['dimension_value']} | {_fmt_value(c['value'], 'revenue')} | {share:.1f}% |")
                w()

        # ── 4. Inventory ──
        if "inventory_turnover" in self.kpi_data:
            w("## 4. Hiệu quả vận hành — Vòng quay hàng tồn kho")
            w()
            d = self.kpi_data["inventory_turnover"]
            w(f"> Vòng quay: **{d['curr']:.2f}** lần/kỳ (kỳ trước: {d['prev']:.2f}, {d['pct_change']:+.1f}%)")
            w()
            cat_turn = self.dim_kpi_data.get("inventory_turnover_by_category", [])
            curr_turn = [c for c in cat_turn if c["period_key"] == self.period_key]
            if curr_turn:
                w("**Vòng quay theo danh mục:**")
                w()
                w("| Danh mục | Vòng quay | Đánh giá |")
                w("|---|---|---|")
                for c in sorted(curr_turn, key=lambda x: x["value"]):
                    val = c["value"]
                    rating = "Chậm" if val < 2 else ("Trung bình" if val < 4 else "Tốt")
                    w(f"| {c['dimension_value']} | {val:.2f} | {rating} |")
                w()

        # ── 5. Retention ──
        if "repeat_customer_rate" in self.kpi_data:
            w("## 5. Khách hàng — Tỷ lệ quay lại")
            w()
            d = self.kpi_data["repeat_customer_rate"]
            ret = d["curr"]
            if ret < 30:
                w(f"> **Cảnh báo**: Chỉ {ret:.1f}% khách hàng quay lại mua tiếp.")
            elif ret < 50:
                w(f"> {ret:.1f}% khách hàng quay lại. Cần cải thiện.")
            else:
                w(f"> {ret:.1f}% khách hàng quay lại. Ổn định.")
            w()
            ret_type = self.dim_kpi_data.get("repeat_rate_by_customer_type", [])
            curr_ret = [r for r in ret_type if r["period_key"] == self.period_key]
            if curr_ret:
                w("**Tỷ lệ quay lại theo loại khách hàng:**")
                w()
                w("| Loại KH | Tỷ lệ quay lại |")
                w("|---|---|")
                for r in sorted(curr_ret, key=lambda x: x["value"], reverse=True):
                    w(f"| {r['dimension_value']} | {r['value']:.1f}% |")
                w()

        # ── 6. Contribution ──
        w("## 6. Phân tích đóng góp")
        w()
        rev_contrib = [c for c in self.contributions if c["kpi_name"] == "revenue"]
        if rev_contrib:
            by_dim: dict[str, list] = {}
            for c in rev_contrib:
                by_dim.setdefault(c["dimension"], []).append(c)
            for dim, items in by_dim.items():
                top = sorted(items, key=lambda x: abs(x["contribution_pct"]), reverse=True)[:5]
                total_ch = top[0]["total_change_pct"]
                arrow = "(+)" if total_ch >= 0 else "(-)"
                w(f"### Phân rã theo {_dim_label(dim)}")
                w()
                w(f"> Doanh thu thay đổi: {arrow} {total_ch:+.1f}%")
                w()
                w("| Giá trị | Đóng góp | Biến động |")
                w("|---|---|---|")
                for t in top:
                    w(f"| {t['dimension_value']} | {t['contribution_pct']:+.1f}% | {t['pct_change']:+.1f}% |")
                w()

        # ── 7. Drill-down ──
        drivers = [s for s in self.drill_steps if s.get("is_driver")]
        if drivers:
            w("## 7. Chuỗi nguyên nhân (Drill-down)")
            w()
            w("```")
            for s in drivers:
                indent = "  " * s["level"]
                sign = "+" if s["pct_change"] >= 0 else ""
                w(
                    f"{indent}→ {s['dimension_value']} ({s['dimension']}): "
                    f"{sign}{s['pct_change']:.1f}%, "
                    f"đóng góp {s['contribution_pct']:.1f}%"
                )
            w("```")
            w()

        # ── 8. Causal ──
        if self.causal_results:
            w("## 8. Suy luận nhân quả — Độ co giãn theo giá")
            w()
            w("| Danh mục | PED | Loại | R² | p-value | Độ tin cậy |")
            w("|---|---|---|---|---|---|")
            for r in self.causal_results:
                sig = "(Co)" if r.get("is_significant") else "(Khong)"
                rel = r.get("reliability", "?")
                w(f"| {r['category']} | {r['elasticity']:.4f} | {r['elasticity_type']} | {r['r_squared']:.3f} | {sig} {r['p_value']:.4f} | {rel} |")
            w()
            low_reliability = [r for r in self.causal_results if "thấp" in r.get("reliability", "")]
            if low_reliability:
                w("> **Lưu ý**: Dữ liệu AdventureWorks có ít biến động giá theo thời gian,")
                w("> nên ước lượng PED có độ tin cậy thấp. Kết quả chỉ mang tính tham khảo.")
                w()
            sig_results = [r for r in self.causal_results if r.get("is_significant")]
            if sig_results:
                w("**Giải thích:**")
                w()
                for r in sig_results:
                    w(f"- {r['interpretation']}")
                w()

        # ── 9. Hypothesis Tests ──
        if self.hypothesis_results:
            w("## 9. Kiểm định thống kê (Hypothesis Testing)")
            w()
            for hr in self.hypothesis_results:
                first, *rest = hr.get("interpretation", hr.get("error", "?")).split("\n")
                w(f"### {hr.get('hypothesis', '?')}")
                w()
                w(f"> {first}")
                w()
                for line in rest:
                    w(f"  {line}")
                w()
                if "p_value" in hr:
                    sig = "CÓ ý nghĩa" if hr.get("is_significant") else "KHÔNG có ý nghĩa"
                    w(f"- p-value: {hr['p_value']:.4f} — {sig} (α=0.05)")
                if "cohens_d" in hr:
                    w(f"- Effect size (Cohen's d): {hr['cohens_d']:.3f} ({hr.get('effect_size_label', '?')})")
                if "cramers_v" in hr:
                    w(f"- Cramer's V: {hr['cramers_v']:.3f}")
                if "mann_kendall_tau" in hr:
                    w(f"- Mann-Kendall τ: {hr['mann_kendall_tau']:.3f}")
                w()

        # ── 10. Anomalies ──
        if self.anomalies:
            w("## 10. Cảnh báo tồn kho bất thường")
            w()
            w("| Sản phẩm | Danh mục | DIO (ngày) | Giá trị tồn | Anomaly Score |")
            w("|---|---|---|---|---|")
            for a in self.anomalies[:7]:
                dio = a.get("days_inventory_outstanding", 0)
                w(
                    f"| {a['product_name']} "
                    f"| {a.get('category', '?')} "
                    f"| {dio:.0f} "
                    f"| ${a.get('inventory_value', 0):,.0f} "
                    f"| {a.get('anomaly_score', 0):.4f} |"
                )
            w()

        # ── 11. Recommendations ──
        w("## 11. Đề xuất hành động")
        w()
        if critical:
            w("### Khẩn cấp")
            w()
            for c in critical:
                w(f"- **{_kpi_label(c['kpi_name'])}**: {c['recommendation']}")
            w()
        if warnings:
            w("### Cần theo dõi")
            w()
            for w_ in warnings:
                w(f"- **{_kpi_label(w_['kpi_name'])}**: {w_['recommendation']}")
            w()
        if self.decisions:
            w("### Từ hệ thống hỗ trợ quyết định")
            w()
            for d_ in self.decisions[:7]:
                icon = "[HIGH]" if d_["priority"] == "HIGH" else "[MEDIUM]"
                w(f"- {icon} **{d_['signal_type']}**: {d_['recommended_action']}")
            w()

        # ── Disclaimer ──
        w("## ⚠️ Lưu ý khi đọc báo cáo")
        w()
        w("- **Phân tích đóng góp và chuỗi nguyên nhân (Drill-down) dựa trên tương quan, không phải causality.**")
        w("  'Nguyên nhân' ở đây chỉ dimension có đóng góp lớn nhất vào biến động — không khẳng định quan hệ nhân quả.")
        w("  Mọi quyết định kinh doanh cần được đánh giá thêm bằng thực nghiệm (A/B test) hoặc domain expertise.")
        w("- **Dữ liệu AdventureWorks (2010–2014) có thể không đại diện cho thị trường hiện tại.**")
        w("  Phân tích xu hướng, hành vi khách hàng, và độ co giãn theo giá chỉ mang tính tham khảo.")
        w("- **Các ngưỡng cảnh báo (HHI, turnover, churn risk) là heuristic, cần được hiệu chỉnh theo business context thực tế.**")
        w()
        w("---")
        w()
        w(f"*Báo cáo được tạo tự động bởi Analytics Engine — {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        w()

        return "\n".join(L)

    def run(self) -> Path:
        logger.info("=" * 50)
        logger.info("Analytics Runner — bắt đầu")
        logger.info("=" * 50)

        self._resolve_period()
        self._load_kpi_data()
        self._run_contribution()
        self._run_drill_down()
        self._generate_insights()
        # Causal inference được comment mặc định do dữ liệu AdventureWorks
        # không đủ biến động giá để ước lượng PED tin cậy.
        # Bỏ comment nếu dùng dữ liệu thật có price variation.
        # self._run_causal()
        self._run_hypothesis_tests()
        self._load_anomalies()
        self._run_decision_support()

        report = self._build_report()
        fname = f"analytics_report_{self.period_key}.md"
        path = self.output_dir / fname
        path.write_text(report, encoding="utf-8")

        logger.info("Báo cáo đã lưu: %s", path)
        logger.info("=" * 50)
        logger.info("Analytics Runner — hoàn tất (%d insights, %d contributions, %d decisions)",
                     len(self.insights), len(self.contributions), len(self.decisions))
        logger.info("=" * 50)
        return path


def _dim_label(dim: str) -> str:
    return {
        "category": "danh mục sản phẩm",
        "territory": "khu vực",
        "customer_type": "loại khách hàng",
        "overall": "tổng thể",
    }.get(dim, dim)


def main():
    """Entry point khi chạy trực tiếp python src/analytics/runner.py --period 2014Q2"""
    import argparse
    from sqlalchemy import create_engine
    from src.config import load_postgres_settings

    parser = argparse.ArgumentParser(description="Analytics Runner — Báo cáo tổng hợp")
    parser.add_argument("--period", default=None, help="Kỳ phân tích (vd: 2014Q2)")
    parser.add_argument("--output", default=None, help="Thư mục lưu báo cáo")
    args = parser.parse_args()

    settings = load_postgres_settings()
    engine = create_engine(settings.connection_string())

    runner = AnalyticsRunner(
        engine=engine,
        period_key=args.period,
        output_dir=Path(args.output) if args.output else REPORTS_DIR,
    )
    report_path = runner.run()
    print(f"\nBáo cáo đã được tạo: {report_path}")


if __name__ == "__main__":
    main()
