from datetime import datetime, timedelta

import pytest


def ago(days=0, hours=0):
    return (datetime.now() - timedelta(days=days, hours=hours)).isoformat()


@pytest.fixture
def structure(client):
    body = {"name": "Diyarbakır Surları", "location": "Diyarbakır", "scenario_intensity": 8}
    return client.post("/api/structures", json=body).json()


@pytest.fixture
def component(client, structure):
    body = {"name": "Yedi Kardeş Burcu", "component_type": "burç", "masonry_typology": "masif_tas"}
    return client.post(f"/api/structures/{structure['id']}/components", json=body).json()


def add_damage(client, component_id, **kw):
    body = {"type_code": "yapisal_catlak", "severity": 4, "observed_at": ago(days=1)}
    body.update(kw)
    return client.post(f"/api/components/{component_id}/damages", json=body)


# ---------------------------------------------------------------- CRUD


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_structure_crud(client, structure):
    sid = structure["id"]
    assert client.get("/api/structures").json()[0]["name"] == "Diyarbakır Surları"
    updated = client.put(f"/api/structures/{sid}", json={"name": "Surlar", "scenario_intensity": 9})
    assert updated.json()["scenario_intensity"] == 9
    assert client.delete(f"/api/structures/{sid}").status_code == 204
    assert client.get(f"/api/structures/{sid}").status_code == 404


def test_component_crud_and_cascade(client, structure, component):
    sid, cid = structure["id"], component["id"]
    assert len(client.get(f"/api/structures/{sid}/components").json()) == 1
    add_damage(client, cid)
    client.delete(f"/api/structures/{sid}")
    assert client.get(f"/api/components/{cid}").status_code == 404
    assert client.get(f"/api/components/{cid}/damages").status_code == 404


def test_meta_endpoints(client):
    assert len(client.get("/api/meta/damage-types").json()) == 6
    assert len(client.get("/api/meta/masonry-typologies").json()) == 3
    params = client.get("/api/meta/parameters").json()
    assert params["version"] == "v1" and params["w_damage"] == 0.5


# ---------------------------------------------------------------- doğrulama (Deney 5)


@pytest.mark.parametrize(
    "path, body",
    [
        ("/api/structures", {"name": ""}),
        ("/api/structures", {}),
        ("/api/structures", {"name": "X", "scenario_intensity": 13}),
        ("/api/structures", {"name": "X", "latitude": 120}),
    ],
)
def test_invalid_structure_rejected(client, path, body):
    assert client.post(path, json=body).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"type_code": "yapisal_catlak", "severity": 0},
        {"type_code": "yapisal_catlak", "severity": 6},
        {"type_code": "yapisal_catlak", "severity": "yüksek"},
        {"type_code": "bilinmeyen", "severity": 3},
        {"type_code": "yapisal_catlak"},
        {"type_code": "yapisal_catlak", "severity": 3, "observed_at": "2999-01-01T00:00:00"},
        {"type_code": "yapisal_catlak", "severity": 3, "data_source": "uydurma"},
    ],
)
def test_invalid_damage_rejected(client, component, body):
    assert client.post(f"/api/components/{component['id']}/damages", json=body).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"humidity_pct": 101},
        {"humidity_pct": -1},
        {"temperature_c": 75},
        {"temperature_c": "sıcak"},
        {"temperature_c": 20, "measured_at": "2999-01-01T00:00:00"},
    ],
)
def test_invalid_measurement_rejected(client, component, body):
    assert client.post(f"/api/components/{component['id']}/measurements", json=body).status_code == 422


def test_invalid_component_typology_rejected(client, structure):
    body = {"name": "Burç", "masonry_typology": "beton"}
    assert client.post(f"/api/structures/{structure['id']}/components", json=body).status_code == 422


def test_records_for_missing_component_rejected(client):
    assert add_damage(client, 999).status_code == 404
    assert client.post("/api/components/999/measurements", json={"temperature_c": 5}).status_code == 404
    assert client.get("/api/components/999/risk").status_code == 404


def test_bulk_rejects_whole_request_on_one_bad_row(client, component):
    cid = component["id"]
    rows = [{"temperature_c": 10, "measured_at": ago(hours=2)}, {"humidity_pct": 500}]
    assert client.post(f"/api/components/{cid}/measurements/bulk", json=rows).status_code == 422
    assert client.get(f"/api/components/{cid}/measurements").json() == []
    assert client.post(f"/api/components/{cid}/measurements/bulk", json=[]).status_code == 422


# ---------------------------------------------------------------- risk akışı


def test_risk_of_empty_component(client, component):
    risk = client.get(f"/api/components/{component['id']}/risk").json()
    assert risk["d"] == 0 and risk["e"] is None
    assert "cevresel_veri_yok" in risk["flags"]
    assert risk["explanation"].endswith("restorasyon talimatı değildir.")


def test_damage_raises_risk_and_repair_lowers_it(client, component):
    cid = component["id"]
    before = client.get(f"/api/components/{cid}/risk").json()["r"]
    damage = add_damage(client, cid).json()
    during = client.get(f"/api/components/{cid}/risk").json()
    assert during["d"] == pytest.approx(80.0) and during["r"] > before

    client.put(f"/api/damages/{damage['id']}", json={"status": "onarildi"})
    after = client.get(f"/api/components/{cid}/risk").json()
    assert after["d"] == 0


def test_new_observation_changes_severity_and_trend(client, component):
    cid = component["id"]
    damage = add_damage(client, cid, severity=2, observed_at=ago(days=120)).json()
    client.post(f"/api/damages/{damage['id']}/observations", json={"severity": 4, "observed_at": ago(days=5)})
    risk = client.get(f"/api/components/{cid}/risk").json()
    assert risk["d"] == pytest.approx(80.0)
    assert risk["t_parts"]["egilim"] == pytest.approx(100.0)  # 40 -> 80, +40 puan
    assert "egilim_verisi_yetersiz" not in risk["flags"]

    past = client.get(f"/api/components/{cid}/risk", params={"as_of": ago(days=60)}).json()
    assert past["d"] == pytest.approx(40.0)


def test_measurements_feed_environmental_score(client, component):
    cid = component["id"]
    rows = [
        {"measured_at": ago(days=2, hours=10), "temperature_c": 4, "humidity_pct": 85},
        {"measured_at": ago(days=2, hours=1), "temperature_c": 14, "humidity_pct": 60},
    ]
    assert client.post(f"/api/components/{cid}/measurements/bulk", json=rows).json() == {"created": 2}
    risk = client.get(f"/api/components/{cid}/risk").json()
    assert risk["e_parts"]["nem"] == pytest.approx(50.0)
    assert risk["e"] is not None


def test_maintenance_resets_maintenance_score(client, component):
    cid = component["id"]
    assert client.get(f"/api/components/{cid}/risk").json()["t_parts"]["bakim"] == 100
    client.post(f"/api/components/{cid}/maintenance", json={"kind": "denetim", "performed_at": ago(days=3)})
    assert client.get(f"/api/components/{cid}/risk").json()["t_parts"]["bakim"] == 100  # denetim bakım sayılmaz
    client.post(f"/api/components/{cid}/maintenance",
                json={"kind": "bakim", "performed_at": ago(days=3), "materials_used": "kireç harcı"})
    risk = client.get(f"/api/components/{cid}/risk").json()
    assert risk["t_parts"]["bakim"] < 1
    assert "bakim_kaydi_yok" not in risk["flags"]


def test_risk_history_is_ordered_time_series(client, component):
    cid = component["id"]
    damage = add_damage(client, cid, severity=1, observed_at=ago(days=300)).json()
    for days, severity in [(200, 2), (100, 3), (10, 4)]:
        client.post(f"/api/damages/{damage['id']}/observations",
                    json={"severity": severity, "observed_at": ago(days=days)})
    history = client.get(f"/api/components/{cid}/risk/history", params={"step_days": 60}).json()
    assert len(history) == 7
    assert [p["as_of"] for p in history] == sorted(p["as_of"] for p in history)
    d_values = [p["d"] for p in history]
    assert d_values == sorted(d_values) and d_values[-1] == pytest.approx(80.0)


def test_history_rejects_bad_ranges(client, component):
    url = f"/api/components/{component['id']}/risk/history"
    assert client.get(url, params={"start": ago(days=1), "end": ago(days=10)}).status_code == 422
    assert client.get(url, params={"start": "1990-01-01T00:00:00", "step_days": 1}).status_code == 422


# ---------------------------------------------------------------- öncelik ve panel


def test_priorities_rank_components(client, structure):
    sid = structure["id"]
    ids = []
    for name in ("Sağlam Burç", "Hasarlı Burç", "Az Hasarlı Duvar"):
        ids.append(client.post(f"/api/structures/{sid}/components", json={"name": name}).json()["id"])
    add_damage(client, ids[1], severity=5)
    add_damage(client, ids[2], severity=2, type_code="yuzey_asinmasi")

    ranking = client.get(f"/api/structures/{sid}/priorities").json()
    assert [r["component_name"] for r in ranking] == ["Hasarlı Burç", "Az Hasarlı Duvar", "Sağlam Burç"]
    assert [r["rank"] for r in ranking] == [1, 2, 3]
    assert ranking[0]["risk_class"] == "Kritik"
    assert len(client.get("/api/priorities").json()) == 3

    dash = client.get(f"/api/structures/{sid}/dashboard").json()
    assert dash["component_count"] == 3 and dash["active_damage_count"] == 2
    assert sum(dash["class_counts"].values()) == 3


def test_export_json_and_csv(client, structure, component):
    add_damage(client, component["id"])
    sid = structure["id"]
    data = client.get(f"/api/structures/{sid}/export").json()
    assert data["components"][0]["damages"][0]["type_code"] == "yapisal_catlak"
    csv_response = client.get(f"/api/structures/{sid}/export", params={"format": "csv"})
    assert csv_response.headers["content-type"].startswith("text/csv")
    text = csv_response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("rank,component_name,risk_class")
    assert "Yedi Kardeş Burcu" in text


# ---------------------------------------------------------------- deprem akışı


def make_wall(client, sid, name, typology):
    body = {"name": name, "masonry_typology": typology}
    return client.post(f"/api/structures/{sid}/components", json=body).json()["id"]


def test_strong_earthquake_creates_inspection_queue(client, structure):
    sid = structure["id"]
    robust = make_wall(client, sid, "Masif Burç", "masif_tas")
    weak = make_wall(client, sid, "Moloz Duvar", "moloz_tas")

    result = client.post(f"/api/structures/{sid}/seismic-events",
                         json={"intensity": 8, "magnitude": 7.7, "occurred_at": ago(hours=1)}).json()
    queue = result["inspection_queue"]
    assert [f["component_id"] for f in queue] == [weak, robust]
    assert all(f["status"] == "bekliyor" for f in queue)
    assert queue[0]["expected_mu_d"] == pytest.approx(2.88, abs=0.01)

    ranking = client.get(f"/api/structures/{sid}/priorities").json()
    assert all(r["pending_seismic_inspection"] for r in ranking)


def test_weak_earthquake_does_not_flag_robust_component(client, structure):
    sid = structure["id"]
    make_wall(client, sid, "Masif Burç", "masif_tas")
    queue = client.post(f"/api/structures/{sid}/seismic-events", json={"intensity": 6}).json()["inspection_queue"]
    assert queue[0]["status"] == "gerekmiyor"
    assert client.get(f"/api/structures/{sid}/dashboard").json()["pending_seismic_inspections"] == 0


def test_post_earthquake_inspection_flow(client, structure):
    """Göçen bileşen D üzerinden Kritik olur; hasarsız bileşende hiçbir şey değişmez."""
    sid = structure["id"]
    collapsed = make_wall(client, sid, "Göçen Duvar", "moloz_tas")
    intact = make_wall(client, sid, "Sağlam Duvar", "moloz_tas")
    before = client.get(f"/api/components/{intact}/risk").json()["r"]

    result = client.post(f"/api/structures/{sid}/seismic-events", json={"intensity": 9}).json()
    event_id = result["event"]["id"]
    flags = {f["component_id"]: f["id"] for f in result["inspection_queue"]}

    assert add_damage(client, collapsed, severity=5, seismic_event_id=event_id,
                      observed_at=ago(hours=0)).status_code == 201
    for flag_id in flags.values():
        assert client.post(f"/api/seismic-flags/{flag_id}/resolve", json={"note": "denetlendi"}).status_code == 200
    assert client.post(f"/api/seismic-flags/{flags[intact]}/resolve", json={}).status_code == 409

    collapsed_risk = client.get(f"/api/components/{collapsed}/risk").json()
    assert collapsed_risk["d"] == pytest.approx(100.0) and collapsed_risk["risk_class"] == "Kritik"
    assert client.get(f"/api/components/{intact}/risk").json()["r"] == pytest.approx(before, abs=0.01)

    queue = client.get(f"/api/seismic-events/{event_id}/inspection-queue").json()
    assert all(f["status"] == "denetlendi" for f in queue)


def test_damage_cannot_reference_event_of_other_structure(client, structure, component):
    other = client.post("/api/structures", json={"name": "Başka Yapı"}).json()
    event = client.post(f"/api/structures/{other['id']}/seismic-events", json={"intensity": 7}).json()["event"]
    assert add_damage(client, component["id"], seismic_event_id=event["id"]).status_code == 422
    assert add_damage(client, component["id"], seismic_event_id=999).status_code == 404
