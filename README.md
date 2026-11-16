# SmartHeritage

Dijital İkiz Tabanlı Akıllı Kültürel Miras İzleme ve Bakım Sistemi.

Tarihî yapıların bileşenlerini, hasarlarını, çevresel ölçümlerini ve bakım geçmişini
kaydeden; bu verilerden açıklanabilir bir risk puanı ve bakım önceliği üreten web
tabanlı bir karar destek prototipi.

> Bu yazılım bir karar destek aracıdır. Restorasyon talimatı vermez ve bir yapının
> mühendislik açısından güvenli olduğunu kanıtlamaz. Depodaki örnek veriler aksi
> belirtilmedikçe sentetiktir.

## Durum

- [x] Risk motoru (D, E, T, sismik S, toplam R, sınıflandırma, açıklama)
- [x] Veritabanı ve API (FastAPI + SQLite)
- [ ] Arayüz ve izleme paneli
- [ ] Simülatör ve deneyler

## Kurulum

```
python -m venv .venv
.venv\Scripts\activate        (Windows)
pip install -r requirements.txt
```

## Çalıştırma

```
uvicorn app.main:app --reload
```

Etkileşimli API belgeleri: http://127.0.0.1:8000/docs

Veritabanı ilk çalıştırmada `data/smartheritage.db` olarak oluşturulur. Farklı bir dosya
için `SMARTHERITAGE_DB` ortam değişkeni kullanılabilir (ör. `sqlite:///data/deneme.db`).

## Testler

```
pytest
```

## Yapı

```
app/config.py                 Sürümlü risk parametreleri
app/services/risk_engine.py   D, E, T, R hesapları (veritabanından bağımsız)
app/services/seismic.py       Makrosismik hasar modeli, denetim sırası
app/services/explain.py       Risk açıklama metni
app/services/ahp.py           Ağırlık gerekçesi için AHP hesabı
app/services/assessment.py    Veritabanı kayıtlarını risk motoruna bağlar
app/database.py, models.py    SQLite bağlantısı ve tablolar
app/schemas.py                Giriş doğrulama ve çıkış şemaları
app/routers/                  API uçları (yapılar, kayıtlar, deprem, risk)
app/main.py                   FastAPI uygulaması
tests/                        Birim ve API testleri
```

## Dayandığı ana makale

Cinquepalmi, F., & Tiburcio, V. A. (2023). Sustainable Restoration of Cultural Heritage
in the digital era. *VITRUVIO*, 8(2), 76–87. https://doi.org/10.4995/vitruvio-ijats.2023.20545
