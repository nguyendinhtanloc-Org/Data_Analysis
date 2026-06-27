# Product & Customer Analytics Dashboard Documentation

## 1. Mục tiêu dashboard

Dashboard **Product & Customer Analytics** được xây dựng nhằm phân tích sâu hơn về sản phẩm và khách hàng sau khi đã có trang tổng quan kinh doanh. Nếu dashboard **Business Performance Overview** trả lời câu hỏi “doanh nghiệp đang hoạt động như thế nào?”, thì dashboard này tập trung trả lời các câu hỏi chi tiết hơn:

- Khách hàng nào đang đóng góp doanh thu lớn nhất?
- Doanh nghiệp đang bán bao nhiêu sản phẩm và cho bao nhiêu khách hàng?
- Nhóm sản phẩm nào là nhóm cốt lõi tạo ra phần lớn doanh thu?
- Các nhóm sản phẩm con nào đóng góp doanh thu cao nhất?
- Giá vốn và giá bán của sản phẩm có quan hệ như thế nào?
- Sản phẩm nào có biên lợi nhuận gộp cao nhất?

Dashboard sử dụng dữ liệu từ Data Warehouse schema `dw`, chủ yếu gồm `dw.fact_sales`, `dw.dim_customer`, `dw.dim_product` và `dw.dim_date`.

---

## 2. Tổng quan bố cục dashboard

Dashboard được sắp xếp theo luồng phân tích từ tổng quan đến chi tiết:

1. Nhóm KPI tổng quan về khách hàng và sản phẩm.
2. Phân tích top khách hàng theo doanh thu.
3. Phân tích sản phẩm theo nhóm ABC Pareto và subcategory.
4. Phân tích mối quan hệ giữa giá vốn và giá bán.
5. Xác định top sản phẩm có biên lợi nhuận cao.

Bố cục này giúp người xem đi từ câu hỏi “quy mô khách hàng và sản phẩm là bao nhiêu?” đến “nhóm khách hàng/sản phẩm nào cần được ưu tiên?”.

---

## 3. KPI Cards

### 3.1. Active Customers

**Giá trị trên dashboard:** 19,119

**Ý nghĩa:**  
Chỉ số này thể hiện số lượng khách hàng thực sự phát sinh giao dịch trong dữ liệu bán hàng. Đây không phải tổng số khách hàng trong hệ thống, mà là số khách hàng có mua hàng trong bảng `fact_sales`.

**Insight:**  
Số lượng khách hàng hoạt động lớn cho thấy doanh nghiệp có nền khách hàng rộng. Đây là cơ sở để phân tích tiếp các nhóm khách hàng đóng góp doanh thu cao nhất và giá trị trung bình trên mỗi khách hàng.

**Hàm ý quản trị:**  
Doanh nghiệp nên tập trung phân nhóm khách hàng theo giá trị doanh thu, tần suất mua hàng hoặc khu vực để có chiến lược chăm sóc phù hợp.

### 3.2. Active Products

**Giá trị trên dashboard:** 266

**Ý nghĩa:**  
Chỉ số này cho biết số lượng sản phẩm đã phát sinh giao dịch bán hàng. Nó phản ánh mức độ đa dạng của danh mục sản phẩm thực sự được thị trường tiêu thụ.

**Insight:**  
Không phải toàn bộ sản phẩm trong danh mục đều có doanh số. Việc chỉ có 266 sản phẩm active giúp nhóm tập trung phân tích các sản phẩm có đóng góp thật sự vào doanh thu.

**Hàm ý quản trị:**  
Có thể tiếp tục phân tích nhóm sản phẩm bán chạy, sản phẩm biên lợi nhuận cao và sản phẩm thuộc nhóm long-tail để tối ưu danh mục.

### 3.3. Units Sold

**Giá trị trên dashboard:** 274,914

**Ý nghĩa:**  
Chỉ số này thể hiện tổng số lượng sản phẩm đã bán, được tính từ tổng `order_qty` trong `fact_sales`.

**Insight:**  
Units Sold cho thấy quy mô tiêu thụ về mặt số lượng. Khi kết hợp với doanh thu và lợi nhuận, chỉ số này giúp phân biệt sản phẩm bán nhiều nhưng giá trị thấp với sản phẩm bán ít nhưng giá trị cao.

**Hàm ý quản trị:**  
Chỉ số này có thể được dùng để hỗ trợ quyết định tồn kho, kế hoạch nhập hàng và đánh giá sản phẩm có nhu cầu cao.

### 3.4. Avg Revenue per Customer

**Giá trị trên dashboard:** $5,745.40

**Ý nghĩa:**  
Chỉ số này thể hiện doanh thu trung bình trên mỗi khách hàng đang hoạt động.

**Insight:**  
Trung bình mỗi khách hàng đóng góp khoảng $5,745.40 doanh thu. Đây là chỉ số hữu ích để đánh giá giá trị khách hàng ở cấp độ tổng quan.

**Hàm ý quản trị:**  
Có thể dùng chỉ số này làm mốc tham chiếu để xác định nhóm khách hàng giá trị cao, nhóm khách hàng trung bình và nhóm khách hàng cần kích hoạt thêm doanh thu.

---

## 4. Top 10 Customers by Revenue

**Loại biểu đồ:** Row chart / horizontal bar chart

**Ý nghĩa biểu đồ:**  
Biểu đồ này hiển thị 10 khách hàng có doanh thu cao nhất. Mỗi thanh biểu diễn tổng doanh thu của một khách hàng, đơn vị tính theo triệu USD.

**Lý do chọn biểu đồ:**  
Tên khách hàng thường dài, nên biểu đồ cột ngang giúp dễ đọc hơn biểu đồ cột dọc. Đồng thời, biểu đồ xếp hạng giúp người xem nhanh chóng nhận ra khách hàng nào có đóng góp lớn nhất.

**Insight chính:**  
Các khách hàng top đầu có mức doanh thu khá sát nhau, dao động khoảng $0.73M đến $0.88M. Điều này cho thấy doanh thu không chỉ phụ thuộc vào một khách hàng duy nhất mà được phân bổ cho nhiều khách hàng lớn.

**Hàm ý quản trị:**  
Nhóm khách hàng top 10 nên được ưu tiên trong các chính sách chăm sóc, giữ chân và khuyến mãi cá nhân hóa. Đây là nhóm có ảnh hưởng trực tiếp đến doanh thu, nên cần duy trì mối quan hệ tốt để giảm rủi ro mất khách hàng quan trọng.

---

## 5. Revenue Share by ABC Product Class

**Loại biểu đồ:** Donut chart / pie chart

**Giá trị thể hiện:**

- A - Core Products: khoảng 79.87% doanh thu
- B - Support Products: khoảng 15.05% doanh thu
- C - Long Tail: khoảng 5.08% doanh thu

**Ý nghĩa biểu đồ:**  
Biểu đồ ABC Pareto phân loại sản phẩm theo mức độ đóng góp doanh thu. Nhóm A gồm các sản phẩm cốt lõi tạo ra phần lớn doanh thu, nhóm B là nhóm hỗ trợ, còn nhóm C là nhóm long-tail có đóng góp nhỏ hơn.

**Lý do chọn biểu đồ:**  
Vì chỉ có 3 nhóm A/B/C và mục tiêu là thể hiện tỷ trọng đóng góp trong tổng doanh thu, donut chart là lựa chọn phù hợp. Nó giúp người xem nhanh chóng thấy nhóm A chiếm tỷ trọng áp đảo.

**Insight chính:**  
Nhóm A đóng góp gần 80% doanh thu, cho thấy doanh thu phụ thuộc chủ yếu vào một nhóm sản phẩm cốt lõi. Nhóm C chỉ chiếm khoảng 5% doanh thu, dù có thể gồm nhiều sản phẩm hơn.

**Hàm ý quản trị:**  
Doanh nghiệp cần ưu tiên quản lý nhóm A về tồn kho, nguồn cung, chất lượng và chiến dịch bán hàng. Nhóm B có thể được phát triển để tăng trưởng thêm, còn nhóm C cần xem xét tối ưu danh mục hoặc hạn chế tồn kho quá mức.

---

## 6. Top 10 Product Subcategories by Revenue

**Loại biểu đồ:** Row chart / horizontal bar chart

**Ý nghĩa biểu đồ:**  
Biểu đồ này hiển thị 10 nhóm sản phẩm con có doanh thu cao nhất. Nó giúp phân tích sâu hơn so với cấp category tổng quát.

**Insight chính:**  
Các subcategory như Road Bikes, Mountain Bikes và Touring Bikes đóng góp doanh thu lớn nhất. Điều này cho thấy nhóm xe đạp vẫn là nguồn doanh thu chủ lực của doanh nghiệp.

**Hàm ý quản trị:**  
Doanh nghiệp nên tập trung chiến lược bán hàng và tồn kho vào các subcategory có doanh thu cao. Các nhóm sản phẩm con có doanh thu thấp hơn cần được đánh giá thêm về vai trò hỗ trợ, tiềm năng tăng trưởng hoặc khả năng tối ưu danh mục.

**Giá trị phân tích:**  
Biểu đồ này bổ sung cho dashboard tổng quan, vì thay vì chỉ biết category “Bikes” có doanh thu cao, người xem biết cụ thể subcategory nào trong Bikes đang tạo doanh thu lớn nhất.

---

## 7. Average Cost vs Selling Price by Product

**Loại biểu đồ:** Scatter plot

**Ý nghĩa biểu đồ:**  
Biểu đồ phân tán thể hiện mối quan hệ giữa giá vốn trung bình và giá bán trung bình của từng sản phẩm. Trục X là Average Cost, trục Y là Average Selling Price.

**Lý do chọn biểu đồ:**  
Scatter plot phù hợp khi cần phân tích mối quan hệ giữa hai đại lượng định lượng. Trong trường hợp này, biểu đồ giúp đánh giá giá vốn và giá bán có biến động cùng chiều hay không.

**Insight chính:**  
Các điểm dữ liệu có xu hướng đi lên từ trái sang phải, cho thấy sản phẩm có giá vốn cao thường có giá bán cao hơn. Các sản phẩm nằm ở vùng giá cao có khả năng thuộc nhóm xe đạp giá trị lớn.

**Hàm ý quản trị:**  
Nếu có sản phẩm có giá vốn cao nhưng giá bán không tương ứng, sản phẩm đó cần được kiểm tra lại về chiến lược giá hoặc biên lợi nhuận. Ngược lại, các sản phẩm có giá bán cao và gross margin tốt có thể là nhóm sản phẩm chiến lược.

---

## 8. Top 10 Products by Gross Margin %

**Loại biểu đồ:** Row chart / horizontal bar chart

**Ý nghĩa biểu đồ:**  
Biểu đồ này hiển thị 10 sản phẩm có tỷ lệ biên lợi nhuận gộp cao nhất. Khác với biểu đồ top sản phẩm theo doanh thu, biểu đồ này tập trung vào hiệu quả lợi nhuận.

**Insight chính:**  
Các sản phẩm như Sport-100 Helmet và Hydration Pack có Gross Margin % cao, trên 40%. Đây là các sản phẩm có hiệu quả lợi nhuận tốt dù có thể không phải nhóm tạo doanh thu lớn nhất.

**Hàm ý quản trị:**  
Doanh nghiệp nên xem xét đẩy mạnh bán chéo hoặc khuyến mãi kết hợp các sản phẩm có biên lợi nhuận cao. Các sản phẩm này có thể giúp cải thiện gross margin tổng thể nếu được khai thác tốt.

**Lưu ý phân tích:**  
Một sản phẩm có gross margin cao chưa chắc đóng góp doanh thu lớn. Vì vậy nên xem biểu đồ này kết hợp với biểu đồ doanh thu theo sản phẩm hoặc subcategory để đánh giá toàn diện.

---

## 9. Câu chuyện tổng thể của dashboard

Dashboard **Product & Customer Analytics** cho thấy doanh nghiệp có nền khách hàng và danh mục sản phẩm khá rộng, với 19,119 khách hàng hoạt động và 266 sản phẩm có phát sinh giao dịch. Tuy nhiên, doanh thu có xu hướng tập trung vào một nhóm sản phẩm cốt lõi. Phân tích ABC cho thấy nhóm A đóng góp gần 80% doanh thu, khẳng định vai trò quan trọng của nhóm sản phẩm chủ lực.

Ở góc độ khách hàng, top 10 khách hàng có doanh thu khá cao và tương đối sát nhau, cho thấy doanh nghiệp không phụ thuộc hoàn toàn vào một khách hàng duy nhất. Điều này giúp giảm rủi ro tập trung doanh thu, nhưng cũng đặt ra yêu cầu cần chăm sóc tốt nhóm khách hàng giá trị cao.

Ở góc độ sản phẩm, các subcategory thuộc nhóm xe đạp như Road Bikes và Mountain Bikes là nguồn doanh thu chính. Trong khi đó, các sản phẩm có gross margin cao như helmet hoặc hydration pack cho thấy cơ hội cải thiện lợi nhuận thông qua chiến lược bán kèm và tối ưu danh mục.

Biểu đồ scatter giữa giá vốn và giá bán cho thấy mối quan hệ tương đối cùng chiều, phản ánh cấu trúc giá hợp lý ở mức tổng quan. Tuy nhiên, các điểm lệch khỏi xu hướng chung cần được phân tích sâu hơn để phát hiện sản phẩm có khả năng định giá chưa tối ưu.

---

## 10. Kết luận

Dashboard này giúp bổ sung góc nhìn chi tiết cho dashboard tổng quan kinh doanh. Nếu dashboard đầu tiên trả lời “doanh nghiệp đang bán được bao nhiêu và hiệu quả ra sao”, thì dashboard này trả lời “khách hàng nào và sản phẩm nào đang tạo ra giá trị đó”.

Các insight chính gồm:

1. Nhóm sản phẩm A là nhóm cốt lõi, đóng góp gần 80% doanh thu.
2. Các subcategory thuộc nhóm xe đạp là nguồn doanh thu chủ lực.
3. Top khách hàng đóng góp doanh thu cao nhưng không quá lệ thuộc vào một cá nhân duy nhất.
4. Một số sản phẩm có biên lợi nhuận cao có thể được dùng để cải thiện hiệu quả lợi nhuận.
5. Giá vốn và giá bán có xu hướng tăng cùng nhau, cho thấy cấu trúc định giá tổng thể tương đối hợp lý.

Từ các kết quả này, doanh nghiệp có thể ưu tiên quản lý nhóm sản phẩm cốt lõi, chăm sóc nhóm khách hàng giá trị cao, đồng thời khai thác thêm các sản phẩm có biên lợi nhuận tốt để cải thiện hiệu quả kinh doanh.
