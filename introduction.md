# Hecate

Tài liệu giới thiệu cho người mới. 

## 1. Hecate là gì

Hecate là một chương trình đọc tài liệu mô tả dữ liệu của ngân hàng, rồi lập
ra một bảng tổng hợp: **mỗi trường dữ liệu trong hệ thống đến từ đâu, đi qua
những chặng nào, và bị biến đổi ra sao trên đường đi.**

Kết quả cuối cùng là một tệp Excel. Bạn mở nó bằng Excel như mọi tệp khác.

---

## 2. Vấn đề nó giải quyết

### Chuyện gì đang xảy ra

Dữ liệu trong ngân hàng không nằm yên một chỗ. Nó chạy qua nhiều hệ thống.
Ví dụ một trường "số dư tài khoản":

```
hệ thống gốc  ->  kho tạm  ->  kho dữ liệu  ->  bản trên cloud
```

Mỗi lần chuyển như vậy gọi là **một chặng**. Ở mỗi chặng, trường đó có thể
bị đổi tên, đổi kiểu dữ liệu, đổi độ dài, hoặc bị tính lại theo một công
thức nào đó.

### Tại sao việc này khó

Tài liệu mô tả các chặng đó **được viết riêng cho từng bảng, không phải cho
từng chặng.** Nghĩa là không có một tệp nào tên kiểu "tài liệu từ hệ thống
gốc sang kho tạm". Thay vào đó có khoảng 90 tệp Excel, mỗi tệp nói về một
bảng.

Muốn biết đường đi đầy đủ của **một** trường, bạn phải:

1. Mở tệp của bảng đích, tìm dòng của trường đó
2. Dòng đó ghi tên bảng nguồn và cột nguồn
3. Đi tìm tệp của bảng nguồn đó trong 90 tệp
4. Mở ra, tìm dòng của cột đó
5. Lặp lại cho đến khi không còn tệp nào nữa

Làm bằng tay, một trường mất vài phút. Có hàng nghìn trường.

Và các tệp này do người viết tay nên rất lộn xộn: có tệp để 13 dòng thông
tin phụ phía trên dòng tiêu đề thật; có cột tên là "Loại biến đổi" nhưng
97% ô để trống, còn quy tắc thật lại nằm ở cột "Ghi chú"; có ô ghi tên bảng
nguồn nhưng lại nằm dưới tiêu đề "bảng đích".

**Hecate làm đúng việc lần theo dấu vết đó, tự động.**

### Một cách hình dung quen thuộc

Trong Excel có chức năng **Trace Precedents**: bạn bấm vào một ô có công
thức, Excel vẽ mũi tên chỉ ra những ô nào đã tạo nên giá trị này.

Hecate làm đúng việc đó, nhưng ở quy mô lớn hơn nhiều: không phải giữa các ô
trong một bảng tính, mà giữa các bảng nằm rải rác trong 90 tệp tài liệu khác
nhau.

---

## 3. Vài từ sẽ gặp

| Từ | Nghĩa đơn giản |
|---|---|
| **Từ điển dữ liệu** | Bảng liệt kê mọi trường dữ liệu và mô tả của chúng |
| **Nguồn gốc dữ liệu** | Đường đi của một trường, từ nơi sinh ra đến nơi hiện tại |
| **Chặng** | Một trạm trên đường đi đó (ví dụ: kho tạm, kho dữ liệu) |
| **Trường đích** | Cột ở cuối đường đi, tức cột mà ta đang muốn giải thích |
| **Trường nguồn** | Cột đã cung cấp dữ liệu cho trường đích |
| **Bản ghi** | Một dòng kết quả, ghi một cặp (trường đích, trường nguồn) |
| **Bộ nhớ đệm** | Nơi chương trình nhớ những tệp đã đọc, để lần sau khỏi đọc lại |

### Một điểm dễ nhầm

**Số bản ghi thường nhiều hơn số trường.** Đó là bình thường, không phải lỗi.

Lý do: một trường đích có thể được ghép từ nhiều trường nguồn. Ví dụ cột
`HO_TEN` được ghép từ `HO` và `TEN`. Khi đó chương trình ghi **hai** bản
ghi, cùng một trường đích, mỗi bản ghi một nguồn.

Cách này giúp bạn nhìn rõ từng nguồn một, thay vì phải đọc mấy tên bị nhét
chung vào một ô. Trên màn hình, những trường như vậy có nhãn màu cam
`n→1`.

---

## 4. Cài đặt

Sau khi cài xong, Hecate nằm trong thư mục **Applications** như mọi ứng dụng
khác trên máy Mac. Bạn mở nó bằng cách bấm đúp, y hệt mở Excel.

Bạn **không** cần tài khoản, không cần mật khẩu, không cần nhập mã gì cả.

### Nếu máy không cho mở Hecate

Hecate là ứng dụng nội bộ, không tải từ App Store, nên lần đầu mở macOS có
thể chặn lại. Máy bạn không bị làm sao cả, và đây không phải lỗi của bạn.
Chỉ cần làm một lần duy nhất, từ lần sau bấm đúp là chạy bình thường.

**Bảng thông báo hiện ra sẽ chỉ có hai nút:**

| Nút | Làm gì |
|---|---|
| **Done** (hoặc **Xong**) | Bấm nút này |
| **Move to Trash** (hoặc **Chuyển vào Thùng rác**) | **Tuyệt đối không bấm.** Nút này xoá ứng dụng đi |

Bấm **Done** để đóng bảng đó lại, rồi làm theo 7 bước sau.

1. Bấm vào biểu tượng quả táo ở góc trên cùng bên trái màn hình
2. Chọn **System Settings** (Cài đặt Hệ thống)
3. Ở cột bên trái, kéo xuống và chọn **Privacy & Security**
   (Quyền riêng tư & Bảo mật)
4. Ở khung bên phải, kéo xuống gần cuối tới mục **Security** (Bảo mật)
5. Bạn sẽ thấy một dòng chữ có nhắc tên **Hecate** vừa bị chặn, bên cạnh
   có nút **Open Anyway** (Vẫn mở). Bấm nút đó
6. Máy hỏi vân tay hoặc mật khẩu đăng nhập máy tính. Xác nhận
7. Có thể hiện thêm một bảng nữa hỏi lại cho chắc. Bấm **Open Anyway**
   (Vẫn mở) một lần nữa

Xong. Hecate sẽ mở ra.

> **Không thấy dòng chữ nhắc tên Hecate ở bước 5?**
> Dòng đó chỉ hiện ra ngay sau khi bạn vừa thử mở ứng dụng, và nó tự mất sau
> một lúc. Hãy bấm đúp vào Hecate một lần nữa, rồi quay lại
> **Privacy & Security** ngay. Lúc đó dòng chữ sẽ có ở đó.

---

## 5. Dùng chương trình

Chương trình có đúng 3 bước, hiện ở thanh trên cùng cửa sổ:

```
1 Chọn thư mục      2 Chọn nội dung      3 Kết quả
```

Góc trên bên phải có nút **EN** để đổi sang tiếng Anh nếu bạn muốn.

### Bước 1: Chọn thư mục

Bấm **Chọn thư mục…** rồi trỏ tới thư mục chứa tài liệu nguồn.

Chương trình tự nhận biết đó là thư mục tài liệu Excel hay thư mục chứa các
tệp `.sql`. Bạn không phải chọn loại nào cả.

**Bước này an toàn tuyệt đối.** Chọn thư mục không chạy gì hết, không tốn gì
hết. Chọn nhầm thì bấm **Quay lại** rồi chọn lại.

### Bước 2: Chọn nội dung

Màn hình hiện danh sách những bảng mà chương trình có thể lập từ điển, kèm
một dòng tóm tắt kiểu:

> **7** bảng đích có thể lập từ điển, trong tổng số **89** bảng đã lập chỉ
> mục. Các chặng: **source → staging → dwh → cloud**.

Mặc định tất cả đều được tick. **Lần đầu dùng, hãy bỏ tick hết và chỉ chọn
1 hoặc 2 bảng.**

Lý do rất thực tế: mỗi tệp là một lượt gọi AI. Chọn nhiều thì chạy lâu và
tốn hạn mức. Chọn ít, xem kết quả, hiểu cách đọc đã, rồi hãy chạy nhiều.

Khi chọn quá 8 mục, chương trình sẽ nhắc bạn điều này ngay trên màn hình.

Chọn xong, bấm **Bắt đầu chạy**.

### Bước 3: Chờ và xem kết quả

Màn hình chuyển sang **Đang chạy…** và hiện một khung chữ chạy dần. Khung đó
là nhật ký, ghi lại chương trình đang đọc tệp nào. Bạn không cần hiểu từng
dòng trong đó.

**Lần chạy đầu tiên với một thư mục sẽ chậm**, có thể vài phút, vì mỗi tệp
phải gửi cho AI đọc. Những lần sau nhanh hơn nhiều vì đã có trong bộ nhớ
đệm.

Bạn có thể chuyển sang cửa sổ khác làm việc trong lúc chờ.

#### Nếu muốn dừng giữa chừng

Bấm **Dừng lại**.

Chương trình sẽ dừng **sau khi đọc xong tệp đang đọc dở**, chứ không dừng
tức khắc. Tệp đã gửi cho AI thì vẫn phải chờ nhận trả lời. Nút sẽ đổi thành
**Đang dừng…** trong lúc đó.

**Dừng lại không làm mất công.** Những tệp đã đọc xong vẫn nằm trong bộ nhớ
đệm, nên lần chạy sau sẽ không phải đọc lại chúng. Chỉ có điều lần chạy bị
dừng thì không tạo ra tệp kết quả nào.

---

## 6. Đọc kết quả

Khi chạy xong, màn hình **Kết quả** hiện ra. Có 4 phần.

### 6.1. Bốn con số ở trên cùng

| Con số | Nghĩa |
|---|---|
| **bản ghi** | Tổng số dòng kết quả |
| **trường đích riêng biệt** | Có bao nhiêu cột thật sự được giải thích |
| **chuỗi đầy đủ** | Bao nhiêu phần trăm trường lần được về tận chặng gốc |
| **tệp đã đọc** | Chương trình đã mở bao nhiêu tệp tài liệu |

Nhắc lại: **bản ghi** nhiều hơn **trường đích riêng biệt** là bình thường.

### 6.2. Các kiểm tra tự động

Đây là phần quan trọng nhất để đánh giá độ tin cậy. Mỗi dòng có dấu tick
xanh nếu đạt, dấu chấm than cam nếu không.

**Mọi tên bảng và cột đều khớp nguyên văn với tài liệu**

Đây là kiểm tra mạnh nhất của chương trình. Nó đối chiếu **từng ký tự** mọi
tên bảng và tên cột trong kết quả với đúng tệp tài liệu đã sinh ra chúng.
Nếu AI bịa ra một cái tên không có trong tài liệu, dòng này sẽ báo lỗi ngay.

Nếu dòng này xanh, bạn có thể yên tâm rằng **không có tên nào bị bịa**.

**Số trường đích khớp với số dòng của tệp**

Tệp tài liệu có bao nhiêu dòng dữ liệu thì phải ra bấy nhiêu trường đích.
Nếu lệch, nghĩa là có trường bị bỏ sót khi đọc. Dòng này báo cam là một tín
hiệu đáng chú ý, đáng báo lại.

**Mọi bản ghi đúng cấu trúc quy định**

Kiểm tra kỹ thuật, xem mỗi dòng kết quả có đủ các ô cần thiết không.

**Tệp không đọc được**

Nếu có tệp nào lỗi khi đọc (thường do mạng hoặc do hết hạn mức AI), số lượng
hiện ở đây, và danh sách cụ thể nằm ở khung **Tệp gặp sự cố** bên dưới.

Lần chạy vẫn tiếp tục với các tệp còn lại. Chạy lại lần nữa thì chương trình
chỉ thử lại đúng những tệp đã lỗi.

### 6.3. Mức độ điền đủ

Các thanh ngang cho biết bao nhiêu phần trăm bản ghi có thông tin ở từng
chặng, từng loại.

**Ô trống ở đây không có nghĩa là lỗi.** Rất nhiều khi tài liệu gốc vốn
không ghi thông tin đó. Chương trình chỉ đếm và báo lại, nó không tự phán
xét, và cũng không tự bịa ra cho đủ.

Thanh màu xám là mức trung bình, xanh là cao, cam là thấp.

### 6.4. Xem từng trường

Bảng ở dưới cùng liệt kê từng bản ghi. Có ô tìm kiếm ở góc phải để lọc theo
tên bảng hoặc tên cột.

**Bấm vào một dòng bất kỳ**, một khung sẽ trượt ra từ bên phải, hiện toàn bộ
đường đi của trường đó: từng chặng một, tên bảng và cột ở mỗi chặng, kiểu dữ
liệu, công thức biến đổi, và quan trọng nhất:

> **Tệp đã nêu điều này:** *tên tệp tài liệu*

Dòng đó chính là bằng chứng. Bấm vào tên tệp, Finder sẽ mở ra và trỏ đúng
vào tệp gốc.

### Hai nút cuối màn hình

- **Mở tệp Excel** mở kết quả bằng Excel. Đây là thứ bạn sẽ làm việc nhiều nhất.
- **Mở thư mục kết quả** mở thư mục chứa cả 3 tệp kết quả.

Kết quả được lưu ở **Documents → Hecate**, mỗi lần chạy một thư mục riêng có
ghi ngày giờ, nên các lần chạy không đè lên nhau.

---

## 7. Kiểm chứng
Chương trình tự kiểm tra được rằng nó **không bịa tên**. Nhưng nó không tự
kiểm tra được rằng nó **hiểu đúng ý tài liệu**. Việc đó cần một người biết
đọc tài liệu ngân hàng.

### Cách kiểm chứng một trường
1. Trong màn hình **Xem từng trường**, chọn một dòng bất kỳ
2. Đọc khung bên phải: chương trình nói trường này đến từ bảng nào, cột nào,
   biến đổi ra sao
3. Bấm vào tên tệp ở dòng **Tệp đã nêu điều này**
4. Mở tệp Excel đó lên, tìm đúng dòng của cột đó
5. **So sánh: tài liệu có đúng nói như vậy không?**



### Nên kiểm chứng những trường nào

Đừng kiểm tra ngẫu nhiên đều tay. Hãy nhắm vào chỗ dễ sai nhất:

- **Trường có nhãn cam `n→1`.** Đây là trường ghép từ nhiều nguồn, phần khó
  nhất. Kiểm tra xem có đủ nguồn không, có thừa nguồn nào không.
- **Trường có công thức biến đổi dài.** Câu chữ trong ô "Ghi chú" của tài
  liệu thường viết theo văn nói, dễ bị hiểu sai.
- **Trường có ô Mô tả trống.** Xem thử tài liệu gốc có mô tả thật không. Nếu
  tài liệu có mà kết quả trống, đó là một lỗi đáng báo.
- **Trường mà cột Chuỗi hiện ít chặng hơn các trường khác.** Có thể đường đi
  bị đứt giữa chừng.
- **Trường có nhãn `có khoảng trắng thừa`.** Nhãn này báo rằng tên trong tài
  liệu gốc có dấu cách thừa ở đầu hoặc cuối. Chương trình cố ý giữ nguyên,
  không tự cắt bỏ, vì nhiệm vụ của nó là ghi lại đúng những gì tài liệu viết.

---

## 8. Những điều bình thường, không phải lỗi

Liệt kê ở đây để bạn khỏi mất công báo nhầm.

| Hiện tượng | Giải thích |
|---|---|
| Số bản ghi nhiều hơn số trường | Một trường nhiều nguồn thì thành nhiều bản ghi |
| Cột Mô tả trống ở nhiều dòng | Tài liệu gốc vốn không ghi mô tả cho trường đó |
| Chuỗi đầy đủ chỉ đạt 60-70% | Nhiều trường thật sự chỉ tồn tại ở vài chặng cuối |
| Lần chạy đầu rất chậm | Mỗi tệp là một lượt gọi AI. Lần sau sẽ nhanh |
| Có 1-2 tệp lỗi | Thường do hạn mức AI. Chạy lại là được |
| Tên bảng ở chặng cloud khác chặng trước | Hệ thống cloud lược bỏ tiền tố tên bảng |

---

## 10. Câu hỏi thường gặp

**Tôi có làm hỏng gì được không?**
Không. Chương trình chỉ đọc tài liệu, không bao giờ ghi đè lên chúng. Kết
quả luôn ghi vào thư mục mới trong Documents → Hecate.

**Chạy lại có bị mất kết quả cũ không?**
Không. Mỗi lần chạy tạo một thư mục riêng có ngày giờ.

**Tôi lỡ chọn 90 bảng rồi bấm chạy thì sao?**
Bấm **Dừng lại**. Phần đã đọc vẫn được giữ trong bộ nhớ đệm.

**Tôi có cần internet không?**
Có, cho những tệp chưa từng đọc. Tệp đã có trong bộ nhớ đệm thì không cần.

**Tôi có phải nhập mã API hay mật khẩu gì không?**
Không. Mọi thứ đã nằm sẵn trong ứng dụng.

**Kết quả có 3 tệp, tôi mở tệp nào?**
Mở `output.xlsx`. Hai tệp còn lại (`output.json`, `report.json`) dành cho
người phát triển.

**Chương trình có tự nghĩ ra mô tả cho trường không?**
Không, và đây là điều cần biết rõ. Chương trình chỉ **chép** mô tả từ tài
liệu. Chỗ nào tài liệu không ghi thì để trống. Nó không bao giờ tự đoán.

---

## 11. Tóm lại

Chương trình này chép, chứ không sáng tác. Mọi tên bảng và tên cột trong kết
quả đều được đối chiếu từng ký tự với đúng một tệp tài liệu, và tệp đó luôn
được ghi kèm ngay bên cạnh.

Nghĩa là mọi con số bạn thấy đều kiểm chứng được bằng tay, bằng Excel, bằng
đúng kỹ năng bạn đã có.

Nếu có chỗ nào trong tài liệu này khó hiểu, đó là lỗi của tài liệu chứ không
phải của bạn. Hỏi lại là được.
