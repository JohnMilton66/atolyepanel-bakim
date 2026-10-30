# AtölyePanel — Vercel yayın rehberi (30 Ekim 2026)

> **Durum:** Bu pakette Vercel uyumlu FastAPI uygulaması ve PostgreSQL adaptörü hazırlandı. Bu paket **yayınlandığı veya Vercel hesabınıza bağlandığı anlamına gelmez**. İnternet adresi yalnızca gerçek deploy başarılı olduktan sonra kesinleşir.
>
> **Kapsam:** Kişisel, hayalî verilerle teknik değerlendirme. Gerçek THY/kurum bakım kartları, personel hesapları, tesciller veya operasyonel bilgiler kurumsal IT/bilgi güvenliği onayı olmadan **kişisel bulut ortamına aktarılmamalıdır**. Hobby planı kişisel/ticari olmayan kullanım içindir.

## Dosyalarda neler hazır?

- FastAPI uygulaması (`app.py`) ve dört lokasyonlu ISL1, ISL2, IST, SAW takvimi.
- `db_backend.py`: `DATABASE_URL` tanımlanırsa PostgreSQL; yerel ortamda SQLite.
- `public/static/`: Vercel statik dosya yolu (Flask/FastAPI dışında doğrudan servis edilebilir).
- `.python-version`: Python 3.12.
- `.env.example`: gerekli Vercel ortam değişkenlerinin iskeleti, **gerçek sır içermez**.
- Güvenliğe yönelik korumalar: bulutta `DATABASE_URL` ve `TRACKER_SESSION_SECRET` zorunluluğu, HTTPS-only cookie; demoyu uzak DB'ye yanlışlıkla seed etme engeli.

## Hesap / veritabanı kurulumu

1. https://vercel.com/signup üzerinden Vercel hesabına giriş yap veya hesap oluştur. Hobby planı için ödeme yapmak gerekmez, fakat **kurumsal/ticari kullanım plan kapsamı dışıdır**.
2. GitHub'da **private** (özel) `atolyepanel-bakim` adlı yeni repository oluştur. Paketteki `AtolyePanel/` içeriğini repoya yükle. `data/`, `.env` ve `session.key` **asla yüklenmemeli**. Bu pakette gerçek DB veya gerçek şifre yoktur.
3. PostgreSQL (ör. Neon) hizmetinde yeni **ayrı bir test veritabanı** oluştur. Verilen bağlantı URI'sini gizli tut; URL'yi ChatGPT mesajına veya kaynak koduna yazma.
4. Vercel > Add New > Project > Import Git Repository > `atolyepanel-bakim` > Deploy.
5. Vercel Project > Settings > Environment Variables alanında şunları ekle:
   - `DATABASE_URL` — harici PostgreSQL bağlantısı; Production ortamına.
   - `TRACKER_SESSION_SECRET` — 32+ karakterlik sabit, rastgele oturum sırrı (ör. bilgisayarda `python -c "import secrets;print(secrets.token_urlsafe(48))"`).
   - `SECURE_COOKIES` — `1`.
6. Ortam değişkenleri kaydedildikten sonra **Redeploy** yap. `app.py` FastAPI entrypoint olarak algılanmalıdır. Vercel'in FastAPI Python Runtime otomatik yapılandırması kullanılacak. Çalışmazsa deployment build/runtime loglarını kontrol et.
7. PostgreSQL şemasını ve ilk yöneticiyi bilgisayarında, **yalnızca güvenilir bir ağdan** (DB'ye izin verilen IP/erişim gerekebilir), aynı `DATABASE_URL` ve `TRACKER_SESSION_SECRET` değişkenleriyle oluştur:
   - macOS/Linux: `export DATABASE_URL='...'; export TRACKER_SESSION_SECRET='...'`
   - Windows PowerShell: `$env:DATABASE_URL='...'; $env:TRACKER_SESSION_SECRET='...'`
   - `python -m pip install -r requirements.txt`
   - `python app.py init-admin` (güçlü ve tekil parola belirle)
   - **Varsayılan demo hesabı oluşturma.** `python app.py demo` yalnızca gerçek veritabanından bağımsız yerel test için.
8. Vercel projesinde Settings > Domains: `atolyepanel-bakim.vercel.app` adını dene; alınmışsa `atolyepanel-bakim-takip.vercel.app` gibi alternatif kullan. `vercel.app` alan adları ilk gelen alır; **bu dosya onların uygunluğunu garanti etmez**.
9. Sadece hayalî kartlarla test et: giriş, kart planlama, teknisyen oluşturma, teknisyen girişi, not, vardiya devri, takvim, rapor, farklı cihaz oturumu. Gerçek kullanım için ek güvenlik ve veri işleme onayı gerekir.

## Kısıtlar ve zorunlu üretim önlemleri

- **Hobby personal/noncommercial only.** THY bakım süreçleri ve çalışan bilgileri için kurumun yetkili altyapısını veya uygun lisanslı kurumsal barındırmayı kullanın.
- **İnternetten erişilebilir olması üretime hazır olduğu anlamına gelmez.** Kurum SSO/MFA, kullanıcı self-service şifre değişikliği, kalıcı dağıtık login rate limit, denetim loglarının korunması, veritabanı yedekleri/geri yükleme denemeleri, erişim sınırlandırmaları, hassas verilerin sınıflandırılması ve güvenlik testi eksiktir.
- PostgreSQL adaptörüyle yerel SQLite testleri 16 + adaptör testleri çalıştırılabilir; **gerçek PostgreSQL entegrasyon testi yapılmadan production kullanmayın.**
- SQLite içeriği otomatik PostgreSQL'e taşınmaz; gerçek bir migration projesi ayrıca gerektirir. Kişisel buluta gerçek THY verisi yüklenmemelidir.
- Orijinal V4 sürümü, yetkili kişilerce gerçek uçak bakımı onayı/CRS/airworthiness release amacıyla kullanılmamalıdır.

## Kod testi

`PYTHONPATH=. pytest -q` (veya Windows `python -m pytest -q`)

## Resmî kaynaklar

- https://vercel.com/docs/plans/hobby
- https://vercel.com/docs/limits
- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/kb/guide/is-sqlite-supported-in-vercel
