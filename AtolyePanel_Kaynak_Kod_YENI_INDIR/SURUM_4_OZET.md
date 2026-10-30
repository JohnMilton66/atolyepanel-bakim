# AtölyePanel V4 — Bakım Kartı Takvimi ve Teknisyen Girişi

## Neler yeni?

- Yönetici ve teknisyen, **Takvim ve kartlar** ekranında aynı planlanan geliş takvimini görür.
- Takvim günlerinde planlanan kartların **sayısı** ve masaüstünde ilk **iki kart kodu** görünür.
- Güne basınca **uçak tescili, kart kodu/adı, planlanan saat, lokasyon, mevcut durum** listelenir.
- **Önceki ay, sonraki ay, bugün** seçenekleri ve **ISL1 / ISL2 / IST / SAW** lokasyon filtreleri vardır.
- Yönetici takvimdeki güne basıp **Bu güne kart ekle** ile tarih ve lokasyonu önceden doldurulmuş yeni kart oluşturur.
- Yönetici **Kullanıcılar** ekranında **ad soyad, kullanıcı adı ve ilk şifre** belirleyerek teknisyen hesabı açar.
- Teknisyen bu bilgilerle giriş yapar; kart planı oluşturamaz veya değiştiremez, sorumlusu olduğu ya da boşta duran kartlarda geliş/bitiş/yorum işlemleri yapabilir.
- Başlangıç şifreleri açık metin saklanmaz (PBKDF2-SHA256); yönetici eski şifreyi okuyamaz ama sıfırlayabilir.
- Uçak ve kart işlemlerinde **yalnızca dört bakım lokasyonu** yeni kayıtlarda kabul edilir.
- Lacivert, kırmızı, beyaz THY esintili sade arayüz. Üstteki kuş simgesi **temsili simgedir**, THY'nin resmî logosu değildir. Resmî logo, kurumsal izin ve görsel dosyası edinildiğinde kullanılmalıdır.

## Demo başlatma (Windows)

1. ZIP dosyasını klasöre çıkarın.
2. Python 3.11 veya üzeri kurulu olsun.
3. `baslat_demo.bat` dosyasına çift tıklayın.
4. Tarayıcıdan `http://127.0.0.1:8000` adresini açın.

Demo girişleri:

| Rol | Kullanıcı adı | Şifre |
|---|---|---|
| Yönetici | `admin` | `DemoAdmin123!` |
| Teknisyen | `teknisyen` | `DemoTek123!` |

**ÖNEMLİ:** Bunlar yalnızca yerel demo içindir. Kurumsal yayına alınmamalı, gerçek kullanıcılara verilmemelidir.

## Yönetici yeni teknisyen nasıl ekler?

1. `admin` hesabıyla giriş yapın.
2. Sol menüden **Kullanıcılar** sayfasını açın.
3. **Ad soyad**, benzersiz **kullanıcı adı**, en az 10 karakterlik **başlangıç şifresi** girin.
4. Yetkiyi **Teknisyen** olarak bırakın ve **Hesabı oluştur** düğmesine basın.
5. Kullanıcı adı ve şifreyi teknisyene **güvenli, özel bir kanaldan** iletin.
6. Teknisyen giriş ekranından bu bilgilerle oturum açabilir.

Yöneticinin parolayı unutması durumunda eski parola okunamaz; yönetici panelinden yeni parola atanabilir. Sistemde yalnızca bir yönetici kalır ve kendi hesabına erişimini kaybederse dosya/kurum IT yöneticisiyle güvenli kurtarma prosedürü gerekecektir.

## V3'ten mevcut kayıtları koruyarak geçiş

1. **Önceki uygulamayı kapatın.**
2. Önceki `data/tracker.sqlite3` dosyasını ayrı bir klasöre **yedekleyin**. SQLite WAL dosyaları bulunuyorsa uygulamayı temiz kapatıp tam bir yedek alın.
3. Yeni V4 klasörünü ayrı bir yere çıkarın.
4. Eski veritabanı dosyasını V4 klasöründeki `data/` altına **kopyalayın**.
5. Uygulamayı başlatın. V3'teki kullanıcılar, kartlar, açıklamalar, atamalar ve geçmiş aynı DB dosyasında korunur; gerekli ek alanlar kendiliğinden oluşturulur.
6. V3'te eski serbest metin lokasyonlar (`ISL / NDT` vb.) **silinmez veya otomatik tahminle değiştirilmez**. Yönetici ilgili kartı düzenleyip doğru yeni lokasyonu elle seçmelidir. Bu kartlar `Tümü` takviminde görünür, yeni dört lokasyondan birine filtrelenince doğru lokasyon seçilene kadar gizlenir.

**Not:** Demoyu eski DB üzerinde başlatırsanız örnek kullanıcı veya örnek kart eklenmez, mevcut kullanıcılar ve veriler korunur.

## Testler

`PYTHONPATH=. pytest -q` (macOS/Linux) ile 16 otomatik test başarılı. Kapsam: yetkilendirme, admin kart oluşturma, teknisyen güncellemesi, atama/devir, takvimde gün seçimi, lokasyon filtreleri, adminin kullanıcı adı ve şifre belirlemesi, teknisyen girişi, geçersiz tarih ve lokasyon doğrulaması. Testler kurumsal penetrasyon testi veya gerçek çok kullanıcılı kabul testinin yerini almaz.

## Güvenlik ve kullanım sınırı

Bu paket **yerel prototip** niteliğindedir. Resmî bakım kartları, CRS/Form-1, airworthiness release veya havacılık mevzuatında zorunlu kayıtların yerine geçmez. Kurum içinde çok kullanıcılı sunucuya alınmadan önce kurum IT onayı, VPN/SSO veya kurumsal kimlik doğrulama, HTTPS, yetkilendirme, yedekleme, erişim logları, log yönetimi ve güvenlik testleri gereklidir. Masaüstü girişinin aksine bağlantı adresinin `127.0.0.1` olması, başka cihazlardan erişilemeyeceği anlamına gelir.
