# BI Dashboard Documentation — Business Performance Overview

## 1. Mục tiêu Dashboard

Dashboard **Business Performance Overview** được xây dựng nhằm cung cấp cái nhìn tổng quan về hiệu quả kinh doanh của dữ liệu AdventureWorks trong Data Warehouse. Dashboard tập trung trả lời các câu hỏi chính:

- Doanh thu và lợi nhuận gộp toàn hệ thống là bao nhiêu?
- Biên lợi nhuận gộp hiện tại có tốt không?
- Doanh thu và lợi nhuận thay đổi thế nào theo thời gian?
- Nhóm sản phẩm nào tạo doanh thu chính?
- Nhóm sản phẩm nào có biên lợi nhuận tốt nhất?
- Khu vực nào đóng góp nhiều doanh thu nhất?
- Sản phẩm nào là sản phẩm chủ lực?

Dashboard này phục vụ chủ yếu cho **Sales Manager** và nhóm quản trị kinh doanh, giúp theo dõi nhanh tình hình tổng thể và nhận diện các điểm cần phân tích sâu hơn.

---

## 2. Nguồn dữ liệu sử dụng

Dashboard lấy dữ liệu từ PostgreSQL Data Warehouse:

- Database: `adventureworks_dw`
- Schema: `dw`
- Bảng chính: `dw.fact_sales`
- Bảng dimension liên quan: `dw.dim_date`, `dw.dim_product`, `dw.dim_territory`

Các chỉ số chính được lấy từ bảng `fact_sales`, sau đó join với các bảng dimension để phân tích theo thời gian, sản phẩm và khu vực.

---

## 3. Ý nghĩa và insight từng biểu đồ

### 3.1. KPI — Total Revenue

**Giá trị hiển thị:** `$109.85M`

**Ý nghĩa:**  
Chỉ số này thể hiện tổng doanh thu bán hàng của toàn bộ dữ liệu đã được load vào Data Warehouse. Đây là chỉ số tổng quan quan trọng nhất để đánh giá quy mô hoạt động kinh doanh.

**Cách tính:**  
Tổng `line_total` trong bảng `dw.fact_sales`.

**Insight:**  
Doanh nghiệp đạt tổng doanh thu khoảng **109.85 triệu USD**, cho thấy dữ liệu bán hàng có quy mô đủ lớn để phân tích theo nhiều chiều như thời gian, danh mục sản phẩm, khu vực và sản phẩm.

---

### 3.2. KPI — Total Gross Profit

**Giá trị hiển thị:** `$9.37M`

**Ý nghĩa:**  
Chỉ số này thể hiện tổng lợi nhuận gộp sau khi trừ giá vốn hàng bán. Gross Profit giúp đánh giá phần giá trị còn lại từ doanh thu trước khi tính các chi phí vận hành khác.

**Cách tính:**  
Tổng `gross_profit` trong bảng `dw.fact_sales`.

**Insight:**  
Tổng lợi nhuận gộp đạt khoảng **9.37 triệu USD**. Khi so với tổng doanh thu 109.85 triệu USD, lợi nhuận gộp chiếm tỷ trọng không quá cao, vì vậy cần xem thêm chỉ số Gross Margin để đánh giá hiệu quả lợi nhuận.

---

### 3.3. KPI — Gross Margin

**Giá trị hiển thị:** `8.53%`

**Ý nghĩa:**  
Gross Margin cho biết cứ 100 USD doanh thu thì doanh nghiệp giữ lại được bao nhiêu USD lợi nhuận gộp. Đây là chỉ số quan trọng để đánh giá chất lượng doanh thu.

**Cách tính:**  
`Gross Margin = Total Gross Profit / Total Revenue × 100`

**Insight:**  
Gross Margin toàn hệ thống đạt **8.53%**, cho thấy biên lợi nhuận chung còn tương đối mỏng. Vì vậy, dashboard cần phân tích sâu theo product category để xác định nhóm sản phẩm nào có biên lợi nhuận tốt hơn.

---

### 3.4. KPI — Sales Line Items

**Giá trị hiển thị:** `121,317`

**Ý nghĩa:**  
Chỉ số này thể hiện tổng số dòng giao dịch bán hàng trong bảng `fact_sales`. Mỗi dòng là một dòng chi tiết sản phẩm trong một đơn hàng, không phải tổng số đơn hàng.

**Insight:**  
Data Warehouse hiện có **121,317 dòng bán hàng**, đảm bảo dữ liệu đủ lớn để phân tích xu hướng, top sản phẩm, khu vực và danh mục sản phẩm.

---

### 3.5. Line Chart — Revenue & Gross Profit by Quarter

**Ý nghĩa:**  
Biểu đồ này thể hiện xu hướng doanh thu và lợi nhuận gộp theo từng quý. Vì dữ liệu có yếu tố thời gian, biểu đồ đường là lựa chọn phù hợp để quan sát xu hướng tăng, giảm và biến động qua các kỳ.

**Trục X:** Quarter  
**Trục Y:** Amount ($M)  
**Chuỗi dữ liệu:** Revenue ($M), Gross Profit ($M)

**Insight chính:**

- Doanh thu có xu hướng tăng mạnh từ giai đoạn 2011-Q2 đến 2014-Q1.
- Một số quý có doanh thu nổi bật như 2013-Q3, 2014-Q1.
- Lợi nhuận gộp nhìn chung thấp hơn nhiều so với doanh thu, phản ánh biên lợi nhuận gộp không quá cao.
- Quý 2012-Q2 có Gross Profit âm, đây là điểm bất thường cần được kiểm tra sâu hơn nếu trình bày phần phân tích chi tiết.
- 2014-Q2 giảm mạnh so với 2014-Q1; cần lưu ý rằng quý cuối trong dữ liệu có thể chưa phản ánh đủ kỳ kinh doanh nếu dữ liệu bị cắt ở giữa giai đoạn.

**Thông điệp khi thuyết trình:**  
Doanh thu tăng theo thời gian nhưng lợi nhuận gộp không tăng tương ứng cùng mức, cho thấy cần theo dõi thêm biên lợi nhuận và cơ cấu sản phẩm để đánh giá chất lượng tăng trưởng.

---

### 3.6. Bar Chart — Revenue by Product Category

**Ý nghĩa:**  
Biểu đồ này so sánh doanh thu giữa các nhóm sản phẩm. Đây là biểu đồ giúp xác định danh mục nào đang đóng góp nhiều nhất vào tổng doanh thu.

**Kết quả chính:**

- Bikes: khoảng `$94.65M`
- Components: khoảng `$11.80M`
- Clothing: khoảng `$2.12M`
- Accessories: khoảng `$1.27M`

**Insight:**  
Doanh thu tập trung rất mạnh vào nhóm **Bikes**. Nhóm này là nguồn doanh thu cốt lõi của doanh nghiệp. Tuy nhiên, sự phụ thuộc lớn vào một category cũng tạo ra rủi ro nếu nhu cầu đối với Bikes giảm.

**Thông điệp khi thuyết trình:**  
Bikes là nhóm sản phẩm chủ lực về doanh thu, nhưng doanh nghiệp cần xem thêm biên lợi nhuận để đánh giá nhóm này có thực sự hiệu quả hay không.

---

### 3.7. Bar Chart — Gross Margin % by Product Category

**Ý nghĩa:**  
Biểu đồ này so sánh biên lợi nhuận gộp giữa các nhóm sản phẩm. Khác với biểu đồ doanh thu, biểu đồ này tập trung vào hiệu quả lợi nhuận.

**Kết quả chính:**

- Accessories: khoảng `50.02%`
- Clothing: khoảng `14.57%`
- Bikes: khoảng `8.38%`
- Components: khoảng `4.15%`

**Insight:**  
Mặc dù **Bikes** tạo doanh thu cao nhất, **Accessories** mới là nhóm có Gross Margin cao nhất. Điều này cho thấy nhóm Accessories tuy doanh thu nhỏ nhưng có hiệu quả lợi nhuận tốt hơn.

**Thông điệp khi thuyết trình:**  
Doanh thu cao chưa chắc đồng nghĩa với biên lợi nhuận cao. Doanh nghiệp có thể cân nhắc chiến lược cross-sell Accessories đi kèm Bikes để cải thiện lợi nhuận gộp.

---

### 3.8. Horizontal Bar Chart — Revenue by Territory

**Ý nghĩa:**  
Biểu đồ này cho biết khu vực nào đóng góp doanh thu nhiều nhất. Do tên territory tương đối dài và có nhiều hạng mục, biểu đồ cột ngang giúp người xem dễ đọc hơn.

**Kết quả nổi bật:**

- Southwest: khoảng `$24.18M`
- Canada: khoảng `$16.36M`
- Northwest: khoảng `$16.08M`
- Germany: khoảng `$4.92M`

**Insight:**  
Southwest là khu vực có doanh thu cao nhất, vượt khá xa các khu vực còn lại. Canada và Northwest cũng là hai thị trường quan trọng. Germany là khu vực có doanh thu thấp nhất trong nhóm hiển thị.

**Thông điệp khi thuyết trình:**  
Doanh thu có sự chênh lệch rõ giữa các khu vực. Nhóm quản trị có thể ưu tiên duy trì các thị trường mạnh như Southwest, Canada, Northwest và phân tích nguyên nhân doanh thu thấp ở các khu vực như Germany.

---

### 3.9. Horizontal Bar Chart — Top 10 Products by Revenue

**Ý nghĩa:**  
Biểu đồ này hiển thị 10 sản phẩm tạo doanh thu cao nhất. Vì tên sản phẩm dài, biểu đồ cột ngang là lựa chọn phù hợp để tăng khả năng đọc.

**Insight:**  
Các sản phẩm đứng đầu chủ yếu thuộc nhóm **Mountain Bikes** và **Road Bikes**, trong đó `Mountain-200 Black, 38` là sản phẩm có doanh thu cao nhất. Điều này củng cố nhận định rằng nhóm Bikes là nguồn doanh thu chủ lực.

**Thông điệp khi thuyết trình:**  
Một số dòng xe cụ thể đang đóng góp lớn vào doanh thu. Doanh nghiệp nên ưu tiên quản lý tồn kho, chiến dịch bán hàng và chính sách giá cho các sản phẩm top đầu này.

---

## 4. Câu chuyện tổng thể của Dashboard

Dashboard cho thấy doanh nghiệp có quy mô doanh thu lớn, đạt khoảng **109.85 triệu USD**, nhưng Gross Margin toàn hệ thống chỉ khoảng **8.53%**. Doanh thu chủ yếu đến từ nhóm **Bikes**, đặc biệt là các dòng Mountain Bikes và Road Bikes. Tuy nhiên, khi xét theo biên lợi nhuận, **Accessories** lại là nhóm có Gross Margin cao nhất.

Điều này tạo ra một insight quan trọng: **Bikes là động lực doanh thu, còn Accessories là cơ hội cải thiện lợi nhuận.** Về mặt khu vực, Southwest là thị trường đóng góp doanh thu cao nhất, trong khi Germany có doanh thu thấp hơn đáng kể so với các khu vực còn lại.

---

## 5. Hàm ý quản trị

Từ dashboard, có thể đề xuất một số hướng hành động:

1. **Duy trì và tối ưu nhóm Bikes** vì đây là nguồn doanh thu chính.
2. **Tăng bán kèm Accessories** vì nhóm này có biên lợi nhuận cao nhất.
3. **Tập trung vào các sản phẩm top doanh thu** như Mountain-200 và Road-250 để đảm bảo tồn kho và chiến lược giá phù hợp.
4. **Ưu tiên thị trường Southwest, Canada, Northwest** vì đây là các khu vực đóng góp doanh thu lớn.
5. **Phân tích sâu các khu vực doanh thu thấp** để tìm nguyên nhân: nhu cầu thấp, kênh bán yếu, thiếu sản phẩm phù hợp hoặc vấn đề phân phối.

---

## 6. Lưu ý khi trình bày

- `Sales Line Items` là số dòng chi tiết bán hàng, không phải số đơn hàng duy nhất.
- Biểu đồ Revenue & Gross Profit dùng chung đơn vị `$M`, nhưng Revenue lớn hơn Gross Profit khá nhiều nên cần giải thích rằng mục tiêu chính của biểu đồ là xem xu hướng tổng thể.
- Dashboard này tập trung vào phân tích tổng quan. Các phân tích sâu hơn về khách hàng, Pareto ABC, tồn kho hoặc ML nên được trình bày ở các dashboard tiếp theo.
