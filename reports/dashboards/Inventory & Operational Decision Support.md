# Inventory & Operational Decision Support Dashboard Documentation

## 1. Mục tiêu dashboard

Dashboard **Inventory & Operational Decision Support** được xây dựng để phân tích tình hình tồn kho và hỗ trợ ra quyết định vận hành. Khác với hai dashboard trước tập trung vào doanh thu, khách hàng và sản phẩm, dashboard này tập trung trả lời các câu hỏi liên quan đến quản lý kho:

- Tổng số lượng tồn kho hiện tại là bao nhiêu?
- Giá trị tồn kho ước tính theo giá vốn là bao nhiêu?
- Doanh nghiệp đang đặt thêm bao nhiêu hàng?
- Tỷ lệ hàng hỏng/phế phẩm là bao nhiêu?
- Category và subcategory nào đang chiếm nhiều giá trị tồn kho nhất?
- Sản phẩm nào có khả năng cần bổ sung hàng?
- Nhóm sản phẩm nào phát sinh nhiều hàng hỏng/phế phẩm?

Dashboard sử dụng dữ liệu từ Data Warehouse schema `dw`, chủ yếu gồm `dw.fact_inventory`, `dw.fact_sales`, `dw.dim_product` và `dw.dim_date`.

---

## 2. Tổng quan bố cục dashboard

Dashboard được sắp xếp theo luồng phân tích từ tổng quan đến hỗ trợ hành động:

1. Nhóm KPI tổng quan về tồn kho.
2. Phân tích giá trị tồn kho và số lượng đặt hàng theo category.
3. Phân tích mối quan hệ giữa lượng tồn kho và lượng bán.
4. Phân tích subcategory đang chiếm nhiều giá trị tồn kho.
5. Phân tích nhóm sản phẩm có lượng hỏng/phế phẩm cao.
6. Bảng gợi ý sản phẩm cần ưu tiên kiểm tra hoặc bổ sung hàng.

Bố cục này giúp người xem đi từ câu hỏi “tồn kho hiện tại đang ở mức nào?” đến “nhóm sản phẩm nào cần được ưu tiên xử lý?”.

---

## 3. KPI Cards

### 3.1. Inventory Units

**Giá trị trên dashboard:** 49.2M units

**Ý nghĩa:**  
Chỉ số này thể hiện tổng số lượng hàng tồn kho hiện có trong hệ thống. Đây là tổng quantity từ bảng `fact_inventory`.

**Insight:**  
Số lượng tồn kho ở mức 49.2 triệu đơn vị cho thấy quy mô tồn kho lớn. Tuy nhiên, chỉ nhìn số lượng chưa đủ để đánh giá mức độ rủi ro, vì các sản phẩm có giá vốn khác nhau sẽ tạo ra giá trị tồn kho khác nhau.

**Hàm ý quản trị:**  
Doanh nghiệp cần kết hợp chỉ số số lượng tồn kho với giá trị tồn kho và lượng bán để đánh giá liệu tồn kho đang nằm ở nhóm sản phẩm có nhu cầu cao hay đang bị tích tụ ở nhóm bán chậm.

### 3.2. Inventory Value

**Giá trị trên dashboard:** 4.77B

**Ý nghĩa:**  
Chỉ số này ước tính tổng giá trị tồn kho theo giá vốn chuẩn, được tính bằng công thức:

`Inventory Value = Quantity × Standard Cost`

**Insight:**  
Giá trị tồn kho khoảng 4.77 tỷ cho thấy lượng vốn bị giữ trong hàng tồn kho là rất lớn. Đây là chỉ số quan trọng hơn số lượng tồn kho khi đánh giá tác động tài chính.

**Hàm ý quản trị:**  
Những category hoặc subcategory có inventory value cao cần được ưu tiên kiểm soát, vì chúng ảnh hưởng trực tiếp đến vốn lưu động và chi phí lưu kho.

### 3.3. Ordered Units

**Giá trị trên dashboard:** 12.06M units

**Ý nghĩa:**  
Chỉ số này thể hiện tổng số lượng hàng đang được đặt thêm hoặc đang chờ bổ sung, dựa trên `ordered_qty` trong bảng `fact_inventory`.

**Insight:**  
Ordered Units đạt 12.06 triệu đơn vị, cho thấy doanh nghiệp vẫn đang có nhu cầu bổ sung hàng đáng kể. Khi kết hợp với Inventory Units, chỉ số này giúp đánh giá việc bổ sung hàng có đang tập trung vào đúng nhóm sản phẩm hay không.

**Hàm ý quản trị:**  
Nếu một nhóm sản phẩm đã có tồn kho cao nhưng vẫn tiếp tục được đặt thêm nhiều, doanh nghiệp cần kiểm tra rủi ro dư thừa tồn kho. Ngược lại, sản phẩm bán tốt nhưng tồn thấp và ordered quantity thấp có thể cần được ưu tiên bổ sung.

### 3.4. Scrap Rate

**Giá trị trên dashboard:** 0.06%

**Ý nghĩa:**  
Scrap Rate thể hiện tỷ lệ hàng hỏng/phế phẩm so với tổng lượng hàng liên quan đến tồn kho. Đây là chỉ số phản ánh mức độ hao hụt hoặc lỗi trong quá trình vận hành.

**Insight:**  
Tỷ lệ scrap rate 0.06% là rất thấp ở mức tổng quan. Điều này cho thấy tỷ lệ hỏng/phế phẩm toàn bộ kho không lớn. Tuy nhiên, vẫn cần phân tích theo subcategory để phát hiện nhóm sản phẩm có mức scrapped quantity cao hơn mặt bằng chung.

**Hàm ý quản trị:**  
Không nên chỉ nhìn scrap rate tổng, vì một số nhóm sản phẩm riêng lẻ vẫn có thể phát sinh phế phẩm cao. Cần dùng thêm biểu đồ Scrapped Quantity by Subcategory để xác định nhóm cần kiểm tra chất lượng hoặc bảo quản.

---

## 4. Inventory Value by Product Category

**Loại biểu đồ:** Bar chart

**Ý nghĩa biểu đồ:**  
Biểu đồ này thể hiện giá trị tồn kho theo từng category sản phẩm, đơn vị tính theo tỷ USD. Giá trị tồn kho được tính dựa trên số lượng tồn kho và standard cost của sản phẩm.

**Insight chính:**  
Bikes và Components là hai category chiếm gần như toàn bộ giá trị tồn kho. Bikes có giá trị tồn kho cao do giá vốn mỗi sản phẩm lớn, trong khi Components cũng chiếm tỷ trọng lớn do số lượng tồn kho cao.

**Hàm ý quản trị:**  
Doanh nghiệp cần ưu tiên theo dõi Bikes và Components vì đây là hai nhóm đang giữ nhiều vốn tồn kho nhất. Nếu các nhóm này bán chậm, rủi ro vốn bị tồn đọng sẽ cao hơn các nhóm khác.

---

## 5. Inventory vs Ordered Quantity by Category

**Loại biểu đồ:** Grouped bar chart / cột đôi

**Ý nghĩa biểu đồ:**  
Biểu đồ này so sánh số lượng tồn kho hiện tại và số lượng đang đặt thêm theo từng category.

**Lý do chọn biểu đồ:**  
Inventory Quantity và Ordered Quantity cùng đơn vị là số lượng, nên sử dụng cột đôi giúp so sánh trực tiếp giữa hàng đang tồn và hàng đang đặt.

**Insight chính:**  
Components có lượng tồn kho và lượng đang đặt lớn nhất. Bikes có giá trị tồn kho cao nhưng số lượng tồn thấp hơn Components, cho thấy sự khác biệt giữa “giá trị tồn kho” và “số lượng tồn kho”.

**Hàm ý quản trị:**  
Components cần được kiểm tra kỹ vì vừa có lượng tồn kho lớn vừa có ordered quantity đáng kể. Điều này có thể là hợp lý nếu nhu cầu cao, nhưng cũng có thể tạo rủi ro dư thừa nếu lượng bán không tương ứng.

---

## 6. Inventory vs Sales Matrix

**Loại biểu đồ:** Scatter plot

**Ý nghĩa biểu đồ:**  
Biểu đồ này so sánh lượng bán và lượng tồn kho của từng sản phẩm. Trục X là Units Sold, trục Y là Inventory Units. Đơn vị đã được quy đổi sang nghìn đơn vị để biểu đồ dễ đọc hơn.

**Lý do chọn biểu đồ:**  
Scatter plot phù hợp để phân tích mối quan hệ giữa hai đại lượng định lượng. Trong trường hợp này, biểu đồ giúp nhận diện sản phẩm có thể bị tồn kho cao hoặc có nguy cơ thiếu hàng.

**Insight chính:**  
Các điểm nằm phía trên bên trái là sản phẩm có tồn kho cao nhưng lượng bán thấp. Đây là nhóm có thể có rủi ro overstock. Ngược lại, các điểm nằm phía dưới bên phải là sản phẩm có lượng bán cao nhưng tồn kho thấp, có thể cần kiểm tra khả năng bổ sung hàng.

**Hàm ý quản trị:**  
Biểu đồ này giúp quản lý kho xác định nhanh các nhóm sản phẩm cần chú ý:

- Bán nhiều nhưng tồn thấp: ưu tiên kiểm tra reorder.
- Tồn cao nhưng bán ít: kiểm tra rủi ro tồn kho chậm luân chuyển.
- Bán nhiều và tồn cao: nhóm sản phẩm chủ lực cần đảm bảo nguồn cung ổn định.

---

## 7. Top 10 Product Subcategories by Inventory Value

**Loại biểu đồ:** Row chart / horizontal bar chart

**Ý nghĩa biểu đồ:**  
Biểu đồ này thể hiện 10 subcategory có giá trị tồn kho cao nhất. Nó giúp phân tích sâu hơn so với cấp category.

**Insight chính:**  
Road Bikes có giá trị tồn kho cao nhất, tiếp theo là Mountain Bikes, Wheels và Mountain Frames. Điều này cho thấy phần lớn vốn tồn kho đang tập trung ở các subcategory liên quan đến xe đạp và linh kiện có giá trị cao.

**Hàm ý quản trị:**  
Các subcategory giữ nhiều inventory value cần được ưu tiên kiểm soát về vòng quay tồn kho, kế hoạch bổ sung và chiến lược bán hàng. Nếu các nhóm này bán chậm, tác động đến vốn lưu động sẽ lớn.

---

## 8. Scrapped Quantity by Subcategory

**Loại biểu đồ:** Row chart / horizontal bar chart

**Ý nghĩa biểu đồ:**  
Biểu đồ này hiển thị lượng hàng hỏng/phế phẩm theo từng subcategory. Đây là chỉ số vận hành quan trọng, giúp phát hiện nhóm sản phẩm có hao hụt cao.

**Insight chính:**  
Wheels là subcategory có lượng scrapped cao nhất, tiếp theo là Derailleurs, Cranksets và Headsets. Các nhóm này cần được chú ý vì có thể liên quan đến lỗi sản xuất, hư hỏng trong lưu kho hoặc vấn đề bảo quản.

**Hàm ý quản trị:**  
Doanh nghiệp nên kiểm tra quy trình bảo quản, vận chuyển, kiểm định chất lượng hoặc nhà cung cấp của các subcategory có scrapped quantity cao. Việc giảm scrapped quantity có thể giúp giảm chi phí vận hành và cải thiện hiệu quả tồn kho.

---

## 9. Reorder Priority Products

**Loại biểu đồ:** Table

**Ý nghĩa bảng:**  
Bảng này liệt kê các sản phẩm cần ưu tiên kiểm tra hoặc bổ sung hàng dựa trên lượng bán, lượng tồn kho, lượng đang đặt và tỷ lệ Inventory-to-Sales Ratio.

**Cách hiểu các cột chính:**

- **Units Sold:** tổng số lượng sản phẩm đã bán.
- **Inventory Units:** số lượng tồn kho hiện tại.
- **Ordered Units:** số lượng đang đặt thêm.
- **Revenue ($M):** doanh thu của sản phẩm.
- **Inventory-to-Sales Ratio:** tỷ lệ tồn kho so với lượng bán.
- **Recommendation:** gợi ý hành động dựa trên rule nghiệp vụ.

**Insight chính:**  
Một số sản phẩm như Half-Finger Gloves, Hitch Rack - 4-Bike, Short-Sleeve Classic Jersey có lượng bán phát sinh nhưng tồn kho bằng 0. Các sản phẩm này được đánh dấu là Critical - Stockout risk.

**Hàm ý quản trị:**  
Bảng này hỗ trợ ra quyết định vận hành bằng cách xác định sản phẩm có nguy cơ thiếu hàng. Các sản phẩm có Recommendation là Critical hoặc High Priority cần được kiểm tra sớm về tồn kho thực tế, kế hoạch đặt hàng và nhu cầu bán hàng.

**Lưu ý phân tích:**  
Đây là bảng decision support dựa trên quy tắc đơn giản, chưa phải mô hình tối ưu tồn kho hoàn chỉnh. Để ra quyết định chính xác hơn, cần thêm dữ liệu về lead time, safety stock, forecast demand và mức tồn kho tối thiểu.

---

## 10. Câu chuyện tổng thể của dashboard

Dashboard **Inventory & Operational Decision Support** cho thấy doanh nghiệp đang có lượng tồn kho lớn, với 49.2 triệu đơn vị hàng tồn và giá trị tồn kho ước tính khoảng 4.77B. Dù scrap rate tổng thể chỉ ở mức 0.06%, vẫn có một số subcategory phát sinh lượng hỏng/phế phẩm cao, đặc biệt là Wheels và các nhóm linh kiện như Derailleurs, Cranksets.

Ở góc độ category, Bikes và Components là hai nhóm chiếm phần lớn giá trị tồn kho. Components có số lượng tồn kho và ordered quantity cao nhất, trong khi Bikes tuy có số lượng ít hơn nhưng vẫn giữ giá trị tồn kho lớn do giá vốn cao. Điều này cho thấy cần phân tích đồng thời cả số lượng và giá trị, không nên chỉ nhìn một chỉ số riêng lẻ.

Biểu đồ Inventory vs Sales Matrix giúp phát hiện các nhóm sản phẩm có dấu hiệu rủi ro vận hành. Sản phẩm bán nhiều nhưng tồn kho thấp có thể cần bổ sung hàng, trong khi sản phẩm tồn cao nhưng bán ít có thể cần kiểm tra rủi ro tồn kho chậm luân chuyển.

Bảng Reorder Priority Products đóng vai trò như phần hỗ trợ hành động, giúp xác định các sản phẩm cần kiểm tra sớm. Những sản phẩm có tồn kho bằng 0 nhưng vẫn có lượng bán được xếp vào nhóm Critical - Stockout risk.

---

## 11. Kết luận

Dashboard này bổ sung góc nhìn vận hành cho hệ thống BI. Nếu hai dashboard trước tập trung vào doanh thu, khách hàng và sản phẩm, thì dashboard này tập trung vào quản lý tồn kho và hỗ trợ ra quyết định.

Các insight chính gồm:

1. Tồn kho hiện tại đạt 49.2 triệu đơn vị, với giá trị ước tính khoảng 4.77B.
2. Bikes và Components là hai category chiếm phần lớn giá trị tồn kho.
3. Components có lượng tồn và lượng đang đặt cao nhất, cần được kiểm tra rủi ro dư thừa.
4. Road Bikes, Mountain Bikes và Wheels là các subcategory giữ nhiều vốn tồn kho nhất.
5. Wheels và một số nhóm linh kiện có lượng scrapped cao, cần kiểm tra quy trình bảo quản hoặc chất lượng.
6. Một số sản phẩm có tồn kho bằng 0 nhưng vẫn có lượng bán, cần được ưu tiên kiểm tra bổ sung hàng.

Từ các kết quả này, doanh nghiệp có thể ưu tiên kiểm soát nhóm sản phẩm có giá trị tồn kho cao, giảm rủi ro thiếu hàng cho sản phẩm bán tốt, đồng thời theo dõi các nhóm có scrapped quantity cao để cải thiện hiệu quả vận hành.
