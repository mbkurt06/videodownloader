# Video Downloader — Chrome eklentisi

YouTube'da indirme hakkınız bulunan videoları farklı çözünürlüklerde MP4/WebM/MKV olarak veya MP3/M4A ses dosyası olarak kaydetmeye yönelik **yerel prototip**.

## Kurulum (macOS)

1. Python 3.10+ ve FFmpeg kurun: `brew install python ffmpeg`.
2. Repoyu klonlayın: `git clone https://github.com/mbkurt06/videodownloader.git`
3. `cd videodownloader/server`
4. `python3 -m venv .venv && source .venv/bin/activate`
5. `pip install -r requirements.txt`
6. `python app.py` (terminal açık kalmalı).
7. Chrome'da `chrome://extensions` açın, **Developer mode** etkinleştirin, **Load unpacked** ile `extension` klasörünü seçin.
8. YouTube videosunu açın, eklenti simgesine tıklayın, **Formatları getir** ve **İndir** seçeneklerini kullanın.

Dosyalar: `~/Downloads/VideoDownloader`.

## Notlar

- Chrome eklentileri tek başına FFmpeg ve yt-dlp çalıştıramadığı için yerel Python yardımcı servisi gerekir.
- Bazı formatlar kaynağa göre mevcut olmayabilir. 320 kbps MP3 seçeneği kaynak ses kalitesini artırmaz.
- YouTube arayüzü/erişim politikaları değiştiğinde yt-dlp güncellemesi gerekebilir: `pip install -U yt-dlp`.
- Bu sürüm yalnızca yerel geliştirme amaçlıdır; Chrome Web Store yayınına uygunluk garanti edilmez.
- Sadece hak sahibi olduğunuz veya indirme izniniz bulunan içerikleri indirin.
- Servis yalnızca 127.0.0.1 üzerinde çalışır. Çok kullanıcılı sistemlerde ek güvenlik ve kimlik doğrulama gerekir.
