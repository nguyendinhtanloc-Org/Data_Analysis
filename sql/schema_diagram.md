# Thiết Kế Sơ Đồ Cấu Trúc Data Warehouse (Star Schema)
**Vai trò: Data Architect (Thành viên A)**

Dưới đây là sơ đồ Star Schema của hệ thống Data Warehouse. Nó bao gồm 2 bảng sự kiện (`Fact_Sales` và `Fact_Inventory`) cùng với các bảng chiều (`Dim_Date`, `Dim_Product`, `Dim_Customer`, `Dim_Territory`, `Dim_Employee`) kết nối xung quanh.

```mermaid
erDiagram
    dim_date {
        int date_key PK
        date date
        int day
        int month
        int quarter
        int year
        boolean is_weekend
    }

    dim_product {
        int product_key PK
        int product_id
        varchar name
        varchar subcategory
        varchar category
        numeric list_price
        numeric standard_cost
        timestamp valid_from
        timestamp valid_to
        boolean is_current
    }

    dim_customer {
        int customer_key PK
        int customer_id
        varchar full_name
        varchar customer_type
        varchar country
        varchar state_province
        int territory_id
    }

    dim_territory {
        int territory_key PK
        int territory_id
        varchar territory_name
        varchar country_region
        varchar group_name
    }

    dim_employee {
        int employee_key PK
        int employee_id
        varchar full_name
        varchar job_title
        varchar department
        date hire_date
    }

    fact_sales {
        int sales_order_detail_id PK
        int date_key FK
        int product_key FK
        int customer_key FK
        int territory_key FK
        int employee_key FK
        int order_qty
        numeric unit_price
        numeric unit_price_discount
        numeric line_total
        numeric standard_cost
        numeric gross_profit
    }

    fact_inventory {
        int inventory_id PK
        int date_key FK
        int product_key FK
        int quantity
        int ordered_qty
        int scrapped_qty
    }

    %% Relationships
    dim_date ||--o{ fact_sales : "sales_date"
    dim_product ||--o{ fact_sales : "product"
    dim_customer ||--o{ fact_sales : "customer"
    dim_territory ||--o{ fact_sales : "territory"
    dim_employee ||--o{ fact_sales : "sales_person"

    dim_date ||--o{ fact_inventory : "inventory_date"
    dim_product ||--o{ fact_inventory : "product"
```

## Các Quyết Định Thiết Kế (Design Decisions)
1. **Sử dụng Surrogate Keys (`_key` tự tăng)** thay cho Business Keys gốc (`_id`) từ OLTP. Điều này cho phép lưu trữ lịch sử thay đổi (SCD) và cô lập hệ thống DW khỏi các thay đổi cấu trúc bảng ở nguồn.
2. **SCD Type 2 áp dụng cho `Dim_Product`**: `list_price` và `standard_cost` có thể thay đổi. Việc dùng SCD Type 2 đảm bảo phân tích lợi nhuận doanh thu (Margin, Profit) trong quá khứ được tham chiếu chính xác đến giá vốn và giá bán tại thời điểm giao dịch xảy ra.
3. **SCD Type 1 áp dụng cho các Dimension còn lại**: Do yêu cầu dự án không đặt nặng việc phân tích lịch sử thay đổi của khách hàng, nhân viên, hoặc khu vực.
