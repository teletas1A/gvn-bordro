# GVN Bordro

Windows'ta aylık toplu bordro PDF'sini personele göre ayıran ve WhatsApp üzerinden gönderen masaüstü uygulamasıdır.

## Özellikler

- Çok sayfalı bordro PDF'sini okur; her sayfayı ayrı personele bağlar.
- `Adı`, `Soyadı`, `Bordro Tarihi` ve Türkiye cep telefonu numarasını algılar.
- PDF içinde telefon bulunmazsa daha önce kaydedilen personel rehberinden getirir.
- Eksik telefonu uygulama içinden düzenleyip sonraki aylar için hatırlar.
- Her personel için yalnızca kendi sayfasını ayrı PDF olarak oluşturur.
- Tam otomatik resmi WhatsApp Business Cloud API gönderimi yapar.
- Alternatif olarak WhatsApp Web sohbetini hazır mesajla açar.
- Gönderim sonucunu yerel veritabanına kaydeder.

## Windows'ta çalıştırma

Bilgisayarda Python 3.11 veya daha yenisi kurulu olmalıdır. İlk kullanımda `run_windows.bat` dosyasına çift tıklayın.

Tek dosyalık Windows uygulaması üretmek için `build_windows.bat` dosyasına çift tıklayın. Çıktı `dist/GVN Bordro.exe` olur.

## Bordrodaki telefon numarası

Her personelin sayfasına aşağıdaki gibi bir alan eklenmesi önerilir:

`Telefon: 0532 123 45 67`

Uygulama `Telefon`, `GSM`, `Cep`, `WhatsApp` veya `Tel` etiketlerini ve Türkiye cep telefonu biçimlerini algılar.

## Tam otomatik WhatsApp gönderimi

Meta WhatsApp Business Cloud API içinde:

1. Bir işletme telefon numarası tanımlayın.
2. Belge başlığı olan `gvn_bordro` adlı Türkçe şablon oluşturup onaya gönderin.
3. Uygulamadaki Ayarlar ekranına Telefon Numarası Kimliği ve kalıcı erişim anahtarını girin.
4. Onaylı şablon adını ve dilini girin.

Kişisel WhatsApp hesabını ekrana tıklayarak yöneten otomasyon kullanılmaz. Yardımlı mod sohbeti ve mesajı açar; PDF'yi kullanıcı ekler. Tam otomatik PDF eki için resmi Cloud API modu kullanılır.

## Gizlilik

Bordrolar `%APPDATA%/GVNBordro/Bordrolar` klasöründe tutulur. Telefon rehberi, ayarlar ve gönderim kayıtları yalnızca aynı bilgisayardaki `%APPDATA%/GVNBordro` klasöründedir. Bu klasöre yalnızca yetkili kişilerin erişmesi gerekir.
