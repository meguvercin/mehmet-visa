# visa-radar

Schengen vize randevusu açıldığında Telegram'dan haber veren, **tamamen ücretsiz** ve **salt okunur** küçük bir radar.

- GitHub Actions üzerinde 5 dakikada bir çalışır → sunucu, VPS, kart bilgisi gerekmez.
- VFS/iDATA sitelerine **girmez**, login olmaz, captcha çözmez, randevu **almaz**.
  Sadece halka açık bir agregatör API'sini okur ve "şurada randevu açıldı" der.
- Randevuyu bildirim gelince **resmi siteden kendin** alırsın.

## Kurulum (10 dakika)

### 1. Telegram botu
1. Telegram'da **@BotFather** → `/newbot` → isim ve kullanıcı adı ver → sana bir **token** verir.
2. Bota bir mesaj at (ör. "merhaba").
3. Tarayıcıda aç: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   `"chat":{"id":123456789 ...}` içindeki sayı senin **chat id**'n.
   (Kanal/grup kullanacaksan botu ekle, yönetici yap; id `-100...` ile başlar.)

### 2. GitHub deposu
1. Bu klasörü yeni bir **private** repo olarak GitHub'a yükle.
2. **Settings → Secrets and variables → Actions**
   - *Secrets* sekmesi: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - *Variables* sekmesi (isteğe bağlı, varsayılanlar `che,nld,aut,svk`):
     - `MISSION_COUNTRIES` → takip edilecek ülkeler, ISO3, virgülle: `che,nld,aut,svk,esp`
     - `CITIES` → boş = hepsi; ör. `Istanbul,Ankara`
     - `VISA_KEYWORDS` → vize tipinde aranacak kelimeler; boş = hepsi
     - `VISA_API_URLS` → agregatör adresi değişirse buradan güncelle
3. **Actions** sekmesine gir, workflow'u etkinleştir.

### 3. Test
- Actions → **visa-radar** → **Run workflow** → mode: `test` → Telegram'a test mesajı gelmeli.
- mode: `dump` → API'nin döndürdüğü ilk 3 kaydı loga basar. Alan adları farklıysa
  `check.py` içindeki `normalize_record` fonksiyonunu ona göre düzelt.
- Sonra kendi kendine 5 dakikada bir çalışır. Bir randevu **kapalıdan açığa** geçtiğinde
  ya da en erken tarih değiştiğinde mesaj atar; aynı durumu tekrar tekrar bildirmez.

## Lokal çalıştırma (isteğe bağlı)
```bash
cp .env.example .env   # doldur
set -a; . ./.env; set +a
python3 check.py --dump   # API'yi gör
python3 check.py --test   # Telegram'ı test et
python3 check.py          # normal kontrol
```
Python 3.8+ yeter, ek paket yok.

## Bilinmesi gerekenler
- **API'ler oynak.** Bu radarlar VFS'in engelleyip durduğu üçüncü taraf agregatörlere dayanır;
  adres değişir ya da servis çöker. `dump` modu boş dönüyorsa GitHub'da güncel bir
  agregatör adresi bulup `VISA_API_URLS` değişkenine yaz. Script birden fazla adresi sırayla dener.
- **GitHub cron dakik değil.** Yoğun saatlerde 5 dk yerine 10-20 dk gecikebilir.
  Repo 60 gün hareketsiz kalırsa GitHub zamanlanmış çalışmayı kapatır; küçük bir commit yeter.
- **Bildirim ≠ randevu.** Mesaj gelince VFS'e giriş yapıp randevuyu kendin al.
  Otomatik rezervasyon botları VFS kullanım şartlarına aykırıdır ve hesabı kapattırır; bu proje o işi yapmaz.
- Agregatörün kendi kullanım koşulları olabilir; kişisel, düşük frekanslı, salt okunur kullanım için tasarlandı.

## Lisans
MIT
