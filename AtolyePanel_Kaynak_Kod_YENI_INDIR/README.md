# AtölyePanel V4 — Takvim + Yönetici Tarafından Teknisyen Girişi

**Güncel sürüm V4.** Yönetici ve teknisyen ekranlarında aylık bakım kartı takvimi, gün içindeki beklenen kartlar, ISL1/ISL2/IST/SAW filtresi ve yönetici tarafından belirlenen kullanıcı adı/şifreyle teknisyen girişi vardır. Ayrıntılar için **`SURUM_4_OZET.md`** dosyasını okuyun.

- Yönetici: **Takvim ve kartlar** → gün seç → **Bu güne kart ekle**; **Kullanıcılar** → yeni teknisyen hesabı oluştur.
- Teknisyen: Yönetici tarafından verilen bilgilerle giriş yap; takvimden kart aç; geliş, bitiş ve yorum ekle.
- `baslat_demo.bat`: örnek hesaplar **admin / DemoAdmin123!** ve **teknisyen / DemoTek123!** (yalnızca yerel demo).
- **Önceki sürüm verisi**: eski `data/tracker.sqlite3` dosyasını V4 `data/` klasörüne taşıyabilirsin; önce yedek al.
- **Eski lokasyon verileri** değiştirilmez; yönetici bunları kart düzenleme ekranından dört sabit lokasyondan birine taşımalıdır.
- Görsel THY esintili kırmızı/lacivert/beyazdır; simge temsili olup resmî THY logosu değildir. Kurumsal izin gereklidir.

---

# AtölyePanel — Uçak Bakım Kartı Takip Sistemi

Admin tarafından planlanan uçak-bakım kartlarının teknisyenlerce güncellenmesini sağlayan, Türkçe ve mobil uyumlu **çalışan web uygulaması prototipi**.

## Özellikler

- **Yönetici:** Uçak ekler; kart kodu, adı, uçağı, beklenen geliş günü/saati ve atölye bilgisini tanımlar; gerekçeyle planı değiştirir; kullanıcı hesabı oluşturur/pasifleştirir; CSV dışa aktarır.
- **Teknisyen:** Kartları listeler, arar, filtreler; fiilî geliş günü ve saatini kaydeder; kartı planlandı/geldi/işlemde/beklemede/tamamlandı durumlarına geçirir; en yeni açıklamayı paylaşır.
- **Tüm yetkili kullanıcılar:** Kartın son açıklamasını, son güncelleyen kişiyi, işlem tarihini ve silinmeyen güncelleme geçmişini görür.
- **Pano:** Bugün beklenenler, gecikenler, bugün gelenler, toplam kart sayısı.
- **Kayıt:** SQLite veritabanında tutulur (`data/tracker.sqlite3`). Türkiye saat dilimi kullanılır.

## Windows hızlı kurulum — örnekleri denemek için

1. Bilgisayarda Python **3.10+** yüklü olsun (`python.org`, kurarken **Add Python to PATH** seçin).
2. Arşivi bir klasöre çıkarın.
3. `baslat_demo.bat` dosyasını çift tıklayın.
4. `http://127.0.0.1:8000` adresini açın.
5. **Demo admin:** `admin` / `DemoAdmin123!` — **Demo teknisyen:** `teknisyen` / `DemoTek123!`.

Demo uçaklarının/kartlarının **tamamı hayalî örnektir**. Demo kullanıcılarını gerçek iş verileriyle KULLANMAYIN. Örnek veriler, uygulama başlatıldığında yalnızca **boş** veritabanına eklenir; gerçek veri içeren veritabanı korunur.

## Gerçek iş verilerine başlamadan önce (yerel test ortamı)

1. Demo başlattıysanız ve örneklere ihtiyacınız kalmadıysa uygulamayı durdurun, **yalnızca kendi demo test veritabanınızı** yedekleyip `data/tracker.sqlite3` ve `data/tracker.sqlite3-wal`, `data/tracker.sqlite3-shm` dosyalarını silin.
2. `baslat_gercek.bat` dosyasını çalıştırın. İlk açılışta yönetici kullanıcı adını, adını ve **güçlü şifresini** sorar. Bu işlem boş DB'de yalnızca bir kere olur.
3. Yönetici ile giriş yapıp **Uçaklar** bölümünden uçakları, **Kullanıcılar** bölümünden teknisyenleri, **Yeni kart** bölümünden iş kartlarını ekleyin.
4. Teknisyenler kendi kullanıcı adlarıyla oturum açıp kart sayfasında **Yeni durum bildir** formunu doldurur.

> Bu paket varsayılan olarak **yalnızca çalıştırılan bilgisayarda (127.0.0.1)** erişilebilir. Teknisyenlerin farklı bilgisayarlardan ulaşması için sunucu/kurum içi ağ kurulumu, HTTPS, erişim yönetimi, günlükleme ve IT onayı gerekir. `--host 0.0.0.0` ile internete doğrudan açmayın.

## Terminal ile başlatma

```bash
python -m pip install -r requirements.txt
python app.py demo           # yalnızca ilk, boş demo DB için
python app.py serve          # http://127.0.0.1:8000
```

Demo yerine yönetici hesabı oluşturmak için: `python app.py init-admin`.

## Rol-yetki özeti

| İşlem | Yönetici | Teknisyen |
| --- | --- | --- |
| Kart listele / arama | Evet | Evet |
| Uçak / plan / kart oluşturma-düzenleme | Evet | Hayır |
| Kartın durumu / açıklaması / ilk geliş zamanı | Evet | Evet |
| Daha önce girilen geliş zamanını düzeltme (açıklamayla) | Evet | Hayır |
| Kullanıcı oluşturma / pasifleştirme | Evet | Hayır |
| CSV dışa aktarma | Evet | Hayır |

## Veri modeli

- `aircraft`: Uçak tanımlayıcı, model
- `users`: Kullanıcı, parola özeti, rol ve aktiflik
- `cards`: Uçak, kart kodu ve adı, beklenen geliş, fiilî geliş, son durum ve son not
- `card_events`: Her güncellemenin kullanıcı/zaman/durum/not geçmişi

## Güncelleme kuralları

- Planlanan geliş günü zorunludur; saat isteğe bağlıdır.
- Kartın gelişi kaydedilmemiş ve plan günü geçmişse **geciken** sayılır; bu bir uyarıdır, bakım uygunluğu / release kararı değildir.
- İlk geliş saati teknisyen tarafından girilebilir; kaydedilmiş zaman yalnızca yönetici tarafından açıklama yazılarak değiştirilebilir.
- Her durum değişimi ve yeni bilgi notu geçmişe kaydedilir. Son bilgi sahası, en son girilen **boş olmayan** açıklamayı korur.
- Kartı bitirmek, NDT sonucunu onaylamak, resmî iş kartını kapatmak veya CRS/Form 1 işlemi yapmak anlamına **gelmez**.

## Kurumsal yayına çıkmadan önce zorunlu değerlendirmeler

Bu **MVP / pilot prototiptir**, havacılık otoritesi onaylı kayıt sistemi, e-imza altyapısı veya üretim seviyesi bakım yönetimi değildir. Kurum IT / bilgi güvenliği / kalite birimlerince doğrulanmadan operasyonel birincil kayıt olarak kullanılmamalıdır.

- Kurumsal SSO/MFA, parolaları kullanıcıların değiştirebilmesi ve admin parola sıfırlama.
- HTTPS, reverse proxy, erişim kontrolleri, kapalı kurumsal ağ/VPN, yetkilendirilmiş barındırma.
- Düzenli veritabanı yedekleri, geri dönüş denemeleri, silinmez/harici log saklama, audit tamlığı.
- Çok kullanıcılı yoğun iş yükünde PostgreSQL, eşzamanlı güncelleme çakışma yönetimi.
- Kişisel veri politikası, kurumsal veri sınıflandırması ve ilgili prosedürlerin onayı.
- Onay akışları, kart sahipliği / atanmış teknisyen, dosya ekleri, gecikme bildirimleri ve tercihe göre bakım sistemi entegrasyonu.

## Test

```bash
python -m pip install -r requirements.txt pytest httpx
pytest -q
```

## Proje dosyaları

- `app.py`: Sunucu, oturum, yetkilendirme, veri modeli ve iş akışları
- `templates/`: HTML sayfaları
- `static/`: CSS/JS
- `baslat_demo.bat`: Windows örnek veriyle açma
- `baslat_gercek.bat`: Windows yeni yönetici hesabı açma
- `tests/`: İşlevsel testler

Örnek veriler / kullanıcılar gerçek ortama aktarılmamalıdır.

## Sürüm 2 güncellemeleri

- Teknisyenler bakım kartının **geliş tarihini/saatini**, **bitiş tarihini/saatini**, **durumunu** ve **açıklamasını** kart ayrıntı ekranından kaydedebilir.
- Tamamlandı durumu seçilip bitiş saati girilmezse sistem mevcut Türkiye saatini bitiş olarak kaydeder. Bitiş, gelişten önce olamaz; tamamlandı bilgisi için geliş zamanı zorunludur.
- Geliş ve bitiş zamanını ilk kez teknisyen girebilir. Mevcut zamanların düzeltilmesi yalnızca yönetici tarafından gerekçeli notla yapılır.
- Yönetici, kullanıcılar ekranından **yönetici/teknisyen hesabı oluşturabilir**, hesapları pasifleştirebilir veya **şifre sıfırlayabilir**.
- Kart panosunda tamamlanan kart sayısı ve bitiş zamanı görünür; CSV dışa aktarımına bitiş saati eklendi.
- Var olan SQLite dosyası uygulama açıldığında **bitiş tarihi sütunu eklenerek otomatik genişletilir**. Veritabanını silmeyin; sürüm yükseltmeden önce yedek alın.
- Uygulamada geciken kartlar için pano uyarısı vardır; **e-posta / SMS / anlık push bildirimleri henüz yoktur**. Rapor CSV formatındadır; Excel'de açılabilir.
- `PYTHONPATH=. pytest -q` ile 6 otomatik test çalıştırıldı.

## Sürüm 3 — Sorumlu teknisyen, kişisel görevler ve vardiya devri (30 Ekim 2026)

### Yeni özellikler

- **Kart sorumlusu:** Yönetici kart oluştururken veya kart ayrıntısından aktif bir teknisyeni sorumlu atayabilir. İlk atamada gerekçe isteğe bağlıdır, mevcut bir sorumluyu değiştirirken gerekçe **zorunludur**.
- **Görevlerim:** Teknisyen kendi kartlarını ayrı bir listede görür. Genel listede kullanıcıya göre, **atanmamış kartlara göre**, uçak ve duruma göre filtreleme vardır.
- **Boştaki kartı üstlen:** Atanmamış bir kartı teknisyen kendisi üstlenebilir. Atanmamış kart üzerinde ilk güncelleme yapan teknisyen, otomatik olarak kart sorumlusu olur. Çakışan atamalar SQLite işlem kilidiyle sıraya alınır.
- **Kartı güncelleme yetkisi:** Başka bir teknisyene atanmış kartlar diğer teknisyenler için salt okunurdur. Sorumlu teknisyen ve yönetici güncelleme yapabilir. Bu, V2'ye göre **yetki değişikliğidir**.
- **Vardiya devri:** Kart sorumlusu veya yönetici, tamamlanmamış kartı başka bir aktif teknisyene devredebilir. Hedef teknisyen, vardiya (sabah/akşam/gece/diğer) ve en az 8 karakterlik devir notu zorunludur. Yeni sorumlu otomatik güncellenir.
- **Görev dağılımı:** Kullanıcı başına açık, işlemde, beklemede ve toplam atanmış kart sayısı; atanmamış kartlar listesi; son 30 vardiya devri.
- **Denetim izi:** Kimin, ne zaman, kimden kime atama/devir yaptığı hem olay geçmişine hem de ayrı alanlara işlenir. Son yorumun yazarı, sonraki sorumlu atamalarından bağımsız korunur.
- **Rapor:** CSV'ye sorumlu teknisyen ve sorumlu atama zamanı eklendi.

### V2'den V3'e veri kaybetmeden geçiş

1. Uygulamayı **kapatın**. Önceki sürümün `data/tracker.sqlite3` dosyasını ve aynı dizindeki `tracker.sqlite3-wal` ve `tracker.sqlite3-shm` dosyalarını (varlarsa) birlikte **yedekleyin**. Bu işlemi uygulama tamamen durduğunda yapın.
2. V3 ZIP dosyasını **yeni bir klasöre** çıkarın. V2 dosyalarının üstüne doğrudan çıkarmayın.
3. Eski sürümün `data` klasöründeki `tracker.sqlite3` dosyasını yeni sürümün `data/` klasörüne kopyalayın. Uygulama kapanmışsa WAL normal olarak veritabanına işlenmiş olmalıdır; tereddüt halinde tam `data` klasörünü kopyalayın. `session.key` dosyasını da eski oturumların korunmasını istiyorsanız taşıyabilirsiniz.
4. İlk açılışta `assigned_to`, `assigned_at`, `assigned_by` ve olay geçmişi sütunları otomatik eklenir. **Eski kartlar atanmamış olarak açılır; mevcut giriş/yorum geçmişi korunur.**
5. Yönetici hesabınızla giriş yaparak `Kullanıcılar` sayfasından teknisyen profillerini oluşturun veya mevcut profilleri kullanın. Kart ayrıntılarından sorumlu ataması yapın.
6. Kontrol edin: kart sayısı, geliş/bitiş saatleri, notlar ve işlem geçmişi değişmemiş olmalı. Yedeği ilk birkaç çalışma günü saklayın.

**Önemli:** ZIP paketi **kullanıcı kayıtlarını/veritabanını içermez**. Bu sayede yeni sürümü kurarken eski kayıtlarınıza zarar vermez. Test verileriyle denemek için `baslat_demo.bat`, sıfırdan gerçek kurulum için `baslat_gercek.bat` kullanın.

### Örnek iş akışı

1. Admin `Kullanıcılar` menüsünden `Tecrübe 1` ve `Tecrübe 2` adlı iki test teknisyeni hesabı açar.
2. `Yeni kart` ekranından `TC-XXX` için kart oluşturur ve ilk sorumluyu `Tecrübe 1` olarak seçer.
3. `Tecrübe 1`, `Görevlerim` menüsünden kartı açıp gelişini, durumunu ve yorumunu kaydeder.
4. Vardiya sonunda aynı karttaki **Görevi devret** bölümünde `Tecrübe 2` seçilir, vardiya ve devir notu eklenir.
5. Kart artık `Tecrübe 2` hesabının `Görevlerim` listesinde görünür, eski teknisyen kartı düzenleyemez; önceki notlar ve devir kaydı silinmez.
6. Yönetici `Görev dağılımı` sayfasından iş yükünü ve devirleri takip eder; CSV raporunu alır.

### Ek uyarılar

- Vardiya devri ve **Tamamlandı** durumları operasyonel iç takip kayıtlarıdır; resmî bakım yetki/sertifikasyon işlemlerinin yerine geçmez.
- Bu sürümde **otomatik e-posta, SMS veya anlık bildirim** bulunmaz. Vardiya devrinin görünmesi için kullanıcı paneli yenilemelidir.
- Pasifleştirilen teknisyenin üzerinde açık kartlar kalabilir; yönetici kart detayından bu işleri aktif bir teknisyene tekrar atamalıdır.
- Birden çok kullanıcı, kurum içi ağ veya internet üzerinde canlı operasyonlar için kurumsal kimlik sistemi, güvenli barındırma, yedekleme ve bağımsız güvenlik incelemesi gerekir.
- Terminalde otomatik test: `PYTHONPATH=. pytest -q` (Windows: `python -m pytest -q`).

### V3 ekran görselleri

`ornek_ekranlar/` klasöründe, çalışan uygulamanın şablonlarından alınmış örnek pano, kart ayrıntısı, iş yükü ve mobil görev listesi ekran görüntüleri bulunur. Görseller **hayalî demo verileriyle** hazırlanmıştır; canlı veriler içermez.
