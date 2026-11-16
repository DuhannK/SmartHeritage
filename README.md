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
- [ ] Veritabanı ve API
- [ ] Arayüz ve izleme paneli
- [ ] Simülatör ve deneyler

## Kurulum

```
python -m venv .venv
.venv\Scripts\activate        (Windows)
pip install -r requirements.txt
```

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
tests/                        Birim testleri
```

## Dayandığı ana makale

Cinquepalmi, F., & Tiburcio, V. A. (2023). Sustainable Restoration of Cultural Heritage
in the digital era. *VITRUVIO*, 8(2), 76–87. https://doi.org/10.4995/vitruvio-ijats.2023.20545
