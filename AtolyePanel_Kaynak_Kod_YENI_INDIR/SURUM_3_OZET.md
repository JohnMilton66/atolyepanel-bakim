# AtölyePanel v3 — kısa rehber

**Güncelleme:** 30 Ekim 2026

## Sorumlu atama
- Yönetici: **Yeni kart** ekranında veya **Kart ayrıntısı → Görev sorumluluğu** alanında teknisyen seçer.
- Teknisyen: Henüz kimseye atanmadıysa **Bu kartın sorumluluğunu üstlen** seçeneğine basar. İlk kart güncellemesi de otomatik üstlenir.

## Görevlerim ve iş yükü
- Teknisyen: **Görevlerim** menüsünde yalnızca kendisine atananları görür.
- Herkes: **Görev dağılımı** menüsünde kimde kaç kart olduğunu, atanmamış kartları ve son vardiya devirlerini görür.
- Yönetici: Genel pano filtrelerinden tek teknisyeni seçebilir ve CSV raporunu dışa aktarabilir.

## Vardiya devri
1. Kart sahibi kartı açar (veya yönetici açar).
2. **Vardiya devri → Görevi devret** alanında yeni teknisyeni seçer.
3. **Sabah / Akşam / Gece / Diğer** seçilir, işin mevcut durumu ve bekleyen adımlar açıkça yazılır.
4. İşlem kaydedildiğinde sorumlu değişir, eski sahibin düzenleme yetkisi kalkar, devir kart geçmişine işlenir.

## V2 verilerini korumak
Uygulamayı kapatın → V2 `data/` klasörünü yedekleyin → V3'ü yeni klasöre çıkartın → veritabanını V3 `data/` altına taşıyın → çalıştırın. Otomatik şema güncellemesi mevcut kartları korur.

**Sistem bir operasyonel izleme prototipidir; resmî bakım kaydı değildir.**
