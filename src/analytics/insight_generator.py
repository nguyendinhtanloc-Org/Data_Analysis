"""Insight Generator - Tự động sinh insight text từ dữ liệu phân tích.

Module này nhận đầu vào là kết quả từ contribution analysis và drill-down,
sau đó sinh ra các insight text có cấu trúc:

  Phát hiện vấn đề → Nguyên nhân → Evidence → Đề xuất

Mỗi insight đều có:
  - severity: 'critical' | 'warning' | 'info'
  - trend: 'up' | 'down' | 'stable'
  - dimension: lĩnh vực tác động
  - root_cause: nguyên nhân gốc rễ
  - evidence: dẫn chứng từ dữ liệu
  - recommendation: đề xuất hành động
  - confidence: độ tin cậy (0-1)
"""
import math
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def generate_revenue_insight(
    kpi_name: str,
    curr_value: float,
    prev_value: float,
    pct_change: float,
    dimension: str = "overall",
    dimension_value: str = "overall",
    contributions: Optional[list] = None,
    drill_down_path: Optional[list] = None,
) -> dict:
    """Sinh insight cho revenue KPI."""
    severity = _classify_severity(abs(pct_change), curr_value, prev_value)
    trend = "up" if pct_change > 0 else "down"

    lines = [f"[{severity.upper()}] {_kpi_label(kpi_name)} {_trend_label(trend)} "
             f"{abs(pct_change):.1f}% ({_fmt_value(curr_value)} vs {_fmt_value(prev_value)} kỳ trước)"]

    if dimension_value and dimension_value != "overall":
        lines[0] += f" ở {dimension}: {dimension_value}"

    if contributions and len(contributions) > 0:
        top_drivers = [c for c in contributions if abs(c.get("contribution_pct", 0)) >= 5]
        if top_drivers:
            lines.append(f"\nNguyên nhân chính:")
            for c in top_drivers[:3]:
                direction = "tăng" if c["pct_change"] > 0 else "giảm"
                lines.append(f"  • {c['dimension_value']}: {direction} {abs(c['pct_change']):.1f}% "
                             f"(đóng góp {c['contribution_pct']:.1f}%)")

    if drill_down_path:
        lines.append(f"\nChuỗi nguyên nhân:")
        for step in drill_down_path[:5]:
            if step.get("is_driver"):
                lines.append(f"  → {step['dimension_value']} ({step['dimension']}): "
                             f"{step['pct_change']:+.1f}%, contrib {step['contribution_pct']:.1f}%")

    root_cause = _identify_root_cause(dimension_value, contributions, drill_down_path)

    recommendation = _generate_recommendation(kpi_name, trend, severity, dimension, root_cause)

    return {
        "kpi_name": kpi_name,
        "dimension": dimension,
        "dimension_value": dimension_value,
        "severity": severity,
        "trend": trend,
        "curr_value": curr_value,
        "prev_value": prev_value,
        "abs_change": curr_value - prev_value,
        "pct_change": round(pct_change, 2),
        "insight_text": "\n".join(lines),
        "root_cause": root_cause,
        "recommendation": recommendation,
        "confidence": _calc_confidence(abs(pct_change), len(contributions or [])),
        "calculated_at": datetime.now(),
    }


def generate_cluster_migration_insight(
    cluster_label: str,
    prev_count: int,
    curr_count: int,
    churned_count: int,
    new_count: int,
    total_customers: int,
) -> dict:
    """Sinh insight cho customer migration."""
    churn_rate = churned_count / max(total_customers, 1) * 100
    severity = "critical" if churn_rate > 10 else ("warning" if churn_rate > 5 else "info")

    lines = [
        f"[{severity.upper()}] Customer Migration - {cluster_label}:",
        f"  • Trước: {prev_count} KH | Sau: {curr_count} KH",
        f"  • Rời đi: {churned_count} KH | Mới đến: {new_count} KH",
        f"  • Tỷ lệ rời bỏ: {churn_rate:.1f}%",
    ]

    if churn_rate > 10:
        recommendation = (f"Cần chiến dịch giữ chân khẩn cấp cho {cluster_label}. "
                          f"Tập trung vào {churned_count} KH có nguy cơ cao.")
    elif churn_rate > 5:
        recommendation = (f"Triển khai chương trình loyalty cho {cluster_label} "
                          f"để giảm tỷ lệ rời bỏ.")
    else:
        recommendation = "Tiếp tục duy trì chính sách hiện tại."

    return {
        "kpi_name": f"customer_migration_{cluster_label.lower().replace(' ', '_')}",
        "dimension": "customer_segment",
        "dimension_value": cluster_label,
        "severity": severity,
        "trend": "down" if churned_count > new_count else "up",
        "curr_value": float(curr_count),
        "prev_value": float(prev_count),
        "abs_change": curr_count - prev_count,
        "pct_change": round((curr_count - prev_count) / max(prev_count, 1) * 100, 2),
        "insight_text": "\n".join(lines),
        "root_cause": "Customer churn do không có engagement strategy phù hợp",
        "recommendation": recommendation,
        "confidence": 0.7,
        "calculated_at": datetime.now(),
    }


def generate_hhi_insight(
    kpi_name: str,
    curr_value: float,
    prev_value: float,
    pct_change: float,
) -> dict:
    # Với 3 categories (Bikes, Clothing, Accessories), HHI tối thiểu = 0.333.
    # Threshold được điều chỉnh cho phù hợp với scale này.
    severity = "critical" if curr_value > 0.6 else ("warning" if curr_value > 0.4 else "info")
    hhi_change = curr_value - prev_value
    trend = "up" if hhi_change > 0 else "down"

    if curr_value > 0.6:
        risk_level = "cao (HHI > 0.6) — doanh thu phụ thuộc quá nhiều vào một danh mục"
        recommendation = ("Cần đa dạng hóa danh mục sản phẩm để giảm rủi ro tập trung. "
                          "Nếu danh mục chính gặp biến động, tổng doanh thu sẽ giảm mạnh.")
    elif curr_value > 0.4:
        risk_level = "trung bình (HHI 0.4–0.6) — cần theo dõi"
        recommendation = "Theo dõi xu hướng tập trung doanh thu, xem xét kế hoạch mở rộng danh mục."
    else:
        risk_level = "thấp (HHI < 0.4) — danh mục tương đối đa dạng"
        recommendation = "Duy trì chiến lược đa dạng hóa hiện tại."

    lines = [
        f"[{severity.upper()}] Mức độ tập trung doanh thu (HHI): {curr_value:.3f}",
        f"  • Đánh giá: {risk_level}",
        f"  • Kỳ trước: {prev_value:.3f} | Biến động: {hhi_change:+.3f}",
        f"  • Gợi ý: {recommendation}",
    ]

    return {
        "kpi_name": kpi_name,
        "dimension": "overall",
        "dimension_value": "overall",
        "severity": severity,
        "trend": trend,
        "curr_value": curr_value,
        "prev_value": prev_value,
        "abs_change": hhi_change,
        "pct_change": round(pct_change, 2),
        "insight_text": "\n".join(lines),
        "root_cause": f"HHI = {curr_value:.3f}, doanh thu tập trung ở một số ít danh mục",
        "recommendation": recommendation,
        "confidence": 0.9 if severity == "critical" else 0.7,
        "calculated_at": datetime.now(),
    }


def generate_inventory_turnover_insight(
    kpi_name: str,
    curr_value: float,
    prev_value: float,
    pct_change: float,
    category_breakdown: Optional[list] = None,
) -> dict:
    severity = "critical" if curr_value < 2 else ("warning" if curr_value < 4 else "info")
    trend = "up" if pct_change > 0 else "down"
    change_label = "cải thiện" if trend == "up" else "suy giảm"
    turnover_label = f"{curr_value:.2f} lần/kỳ"

    lines = [
        f"[{severity.upper()}] Vòng quay hàng tồn kho {change_label}: {turnover_label}",
        f"  • Kỳ trước: {prev_value:.2f} | Thay đổi: {pct_change:+.1f}%",
    ]

    if curr_value < 2:
        recommendation = ("Vòng quay tồn kho rất thấp, vốn đang bị chôn trong hàng tồn. "
                          "Cần thanh lý hàng chậm luân chuyển và giảm reorder quantity.")
        lines[-1] += " -- Cảnh báo: vốn bị chôn quá nhiều"
    elif curr_value < 4:
        recommendation = "Vòng quay tồn kho ở mức trung bình. Rà soát từng category để tối ưu."
    else:
        recommendation = "Vòng quay tồn kho tốt. Duy trì chính sách quản lý tồn kho hiện tại."

    if category_breakdown:
        worst = sorted(category_breakdown, key=lambda c: c.get("value", 0))[:2]
        lines.append(f"  • Danh mục luân chuyển chậm nhất:")
        for c in worst:
            lines.append(f"    - {c.get('dimension_value', '?')}: {c.get('value', 0):.2f} lần")

    lines.append(f"  • Gợi ý: {recommendation}")

    return {
        "kpi_name": kpi_name,
        "dimension": "overall",
        "dimension_value": "overall",
        "severity": severity,
        "trend": trend,
        "curr_value": curr_value,
        "prev_value": prev_value,
        "abs_change": curr_value - prev_value,
        "pct_change": round(pct_change, 2),
        "insight_text": "\n".join(lines),
        "root_cause": f"Vòng quay tồn kho {turnover_label} — {'kém' if severity == 'critical' else 'cần cải thiện'}",
        "recommendation": recommendation,
        "confidence": 0.85,
        "calculated_at": datetime.now(),
    }


def generate_retention_insight(
    kpi_name: str,
    curr_value: float,
    prev_value: float,
    pct_change: float,
    breakdown: Optional[list] = None,
) -> dict:
    severity = "critical" if curr_value < 30 else ("warning" if curr_value < 50 else "info")
    trend = "up" if pct_change > 0 else "down"
    change_label = "tăng" if trend == "up" else "giảm"

    lines = [
        f"[{severity.upper()}] Tỷ lệ khách hàng quay lại: {curr_value:.1f}%",
        f"  • Kỳ trước: {prev_value:.1f}% | {change_label} {abs(pct_change):.1f}%",
    ]

    if curr_value < 30:
        recommendation = ("Tỷ lệ quay lại rất thấp — phần lớn khách hàng chỉ mua 1 lần rồi biến mất. "
                          "Cần chiến dịch loyalty và email marketing để tăng tương tác sau mua.")
        lines[-1] += " -- Khách hàng mới không quay lại"
    elif curr_value < 50:
        recommendation = ("Chỉ khoảng một nửa khách hàng quay lại. "
                          "Triển khai chương trình khách hàng thân thiết, tập trung vào nhóm có nguy cơ cao.")
    else:
        recommendation = "Tỷ lệ quay lại tốt. Tiếp tục duy trì chính sách chăm sóc khách hàng hiện tại."

    if breakdown:
        worst = sorted(breakdown, key=lambda b: b.get("value", 100))[:2]
        lines.append(f"  • Nhóm khách hàng có tỷ lệ quay lại thấp nhất:")
        for b in worst:
            lines.append(f"    - {b.get('dimension_value', '?')}: {b.get('value', 0):.1f}%")

    return {
        "kpi_name": kpi_name,
        "dimension": "overall",
        "dimension_value": "overall",
        "severity": severity,
        "trend": trend,
        "curr_value": curr_value,
        "prev_value": prev_value,
        "abs_change": curr_value - prev_value,
        "pct_change": round(pct_change, 2),
        "insight_text": "\n".join(lines),
        "root_cause": f"Tỷ lệ quay lại {curr_value:.1f}% — {'thấp' if curr_value < 50 else 'ổn'}",
        "recommendation": recommendation,
        "confidence": 0.8,
        "calculated_at": datetime.now(),
    }


def generate_anomaly_insight(
    product_name: str,
    category: str,
    dio: float,
    inventory_value: float,
    anomaly_score: float,
) -> dict:
    """Sinh insight cho inventory anomaly."""
    severity = "critical" if dio > 180 else ("warning" if dio > 90 else "info")

    lines = [
        f"[{severity.upper()}] Tồn kho bất thường - {product_name}:",
        f"  • Category: {category}",
        f"  • Số ngày tồn kho (DIO): {dio:.0f} ngày",
        f"  • Giá trị tồn: ${inventory_value:,.0f}",
        f"  • Anomaly score: {anomaly_score:.4f}",
    ]

    if dio > 180:
        recommendation = (f"Thanh lý {product_name} hoặc giảm 50% reorder quantity. "
                          f"Giá trị tồn ${inventory_value:,.0f} đang bị chôn vốn quá lâu.")
    elif dio > 90:
        recommendation = f"Rà soát lại forecast cho {product_name}, cân nhắc giảm safety stock."
    else:
        recommendation = f"Theo dõi {product_name}, có thể điều chỉnh nhẹ reorder point."

    return {
        "kpi_name": "inventory_anomaly",
        "dimension": "product",
        "dimension_value": product_name,
        "severity": severity,
        "trend": "down",
        "curr_value": dio,
        "prev_value": 0,
        "abs_change": dio,
        "pct_change": 0,
        "insight_text": "\n".join(lines),
        "root_cause": f"Hàng tồn kho lưu kho >{dio:.0f} ngày, vốn bị chôn",
        "recommendation": recommendation,
        "confidence": 0.8 if severity == "critical" else 0.6,
        "calculated_at": datetime.now(),
    }


def _classify_severity(pct_change_abs: float, curr: float, prev: float) -> str:
    if pct_change_abs is None or math.isnan(pct_change_abs):
        return "info"
    mean = (curr + prev) / 2
    if mean == 0:
        return "info"
    # Dùng coefficient of variation để scale threshold
    # Với seasonal business (bike retailer), QoQ change > 30% là bình thường
    # Dùng z-score tương đối: |change| / mean
    relative_magnitude = abs(curr - prev) / mean
    if relative_magnitude > 0.5:
        return "critical"
    elif relative_magnitude > 0.25:
        return "warning"
    return "info"


def _kpi_label(kpi_name: str) -> str:
    labels = {
        "revenue": "Doanh thu",
        "gross_profit": "Lợi nhuận gộp",
        "gross_margin_pct": "Biên lợi nhuận gộp",
        "order_count": "Số lượng dòng bán hàng",
        "total_customers": "Tổng số khách hàng",
        "avg_order_value": "Giá trị đơn hàng trung bình",
        "revenue_per_customer": "Doanh thu trên mỗi khách hàng",
        "inventory_turnover": "Vòng quay hàng tồn kho",
        "inventory_turnover_by_category": "Vòng quay hàng tồn kho theo danh mục",
        "repeat_customer_rate": "Tỷ lệ khách hàng quay lại",
        "repeat_rate_by_customer_type": "Tỷ lệ quay lại theo loại khách hàng",
        "hhi_revenue_concentration": "Mức độ tập trung doanh thu (HHI)",
    }
    return labels.get(kpi_name, kpi_name)


def _trend_label(trend: str) -> str:
    return "tăng" if trend == "up" else "giảm"


def _fmt_value(v, kpi_name: str = "") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    _pct_kpis = {"gross_margin_pct", "margin_by_category", "repeat_customer_rate",
                 "repeat_rate_by_customer_type", "hhi_revenue_concentration"}
    if kpi_name in _pct_kpis:
        return f"{v:.1f}%"
    if kpi_name == "inventory_turnover":
        return f"{v:.2f}"
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    elif abs(v) >= 1_000:
        return f"${v:,.0f}"
    elif 0 < abs(v) < 1:
        return f"{v:.3f}"
    return f"${v:.2f}"


def _identify_root_cause(
    dimension_value: str,
    contributions: Optional[list],
    drill_down_path: Optional[list],
) -> str:
    if drill_down_path:
        drivers = [s for s in drill_down_path if s.get("is_driver")]
        if drivers:
            deepest = drivers[-1]
            return (f"Nguyên nhân gốc: {deepest['dimension_value']} "
                    f"({deepest['dimension']}) thay đổi {deepest['pct_change']:+.1f}%, "
                    f"đóng góp {deepest['contribution_pct']:.1f}% vào biến động tổng thể")

    if contributions:
        top = max(contributions, key=lambda c: abs(c.get("contribution_pct", 0)))
        return (f"Yếu tố ảnh hưởng chính: {top.get('dimension_value', 'unknown')} "
                f"với {top.get('contribution_pct', 0):.1f}% đóng góp")

    return "Không xác định được nguyên nhân cụ thể"


def _generate_recommendation(
    kpi_name: str,
    trend: str,
    severity: str,
    dimension: str,
    root_cause: str,
) -> str:
    if severity == "critical" and trend == "down":
        return (f"Cần can thiệp ngay: {root_cause}. "
                f"Triệu tập họp khẩn với bộ phận liên quan đến {dimension}.")
    elif trend == "down":
        return (f"Phân tích thêm và xây dựng kế hoạch cải thiện cho {dimension}. "
                f"Tham khảo: {root_cause}")
    elif trend == "up":
        return f"Duy trì đà tăng trưởng, nghiên cứu nhân rộng thành công ở {dimension}."
    return "Theo dõi định kỳ."


def _calc_confidence(pct_change_abs: float, n_contributions: int) -> float:
    base = 0.5
    if pct_change_abs > 50:
        base += 0.3
    elif pct_change_abs > 25:
        base += 0.2
    elif pct_change_abs > 10:
        base += 0.1
    base += min(n_contributions * 0.05, 0.2)
    return min(base, 0.99)
