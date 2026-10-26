"""API tests in PERSONAL mode (FACEAPI_AUTH_ENABLED=false — no key required)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _file(data: bytes, name: str = "face.jpg", mime: str = "image/jpeg"):
    return {"image": (name, data, mime)}


# ------------------------------------------------------------------ metadata
def test_service_info(personal_client: TestClient):
    response = personal_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_mode"] == "personal"
    assert body["models"]["detector"].endswith(".onnx")
    assert any(plan["name"] == "personal" for plan in body["plans"])


def test_health_endpoints(personal_client: TestClient):
    assert personal_client.get("/healthz").json()["status"] == "ok"
    ready = personal_client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["checks"] == {"models": "ok", "database": "ok"}


def test_openapi_and_docs_available(personal_client: TestClient):
    assert personal_client.get("/docs").status_code == 200
    schema = personal_client.get("/openapi.json").json()
    for path in ("/v1/detect", "/v1/embed", "/v1/verify", "/v1/identify", "/admin/keys"):
        assert path in schema["paths"]


def test_request_id_header(personal_client: TestClient, assets):
    response = personal_client.post("/v1/detect", files=_file(assets["person_a_1"]))
    assert response.headers["X-Request-ID"]
    assert float(response.headers["X-Processing-Time-Ms"]) >= 0


def test_metrics_exposes_prometheus_text(personal_client: TestClient, assets):
    personal_client.post("/v1/detect", files=_file(assets["person_a_1"]))
    text = personal_client.get("/metrics").text
    assert "faceapi_requests_total" in text
    assert "faceapi_faces_detected_total" in text


# -------------------------------------------------------------------- detect
def test_detect_returns_box_landmarks_and_usage(personal_client: TestClient, assets):
    response = personal_client.post("/v1/detect", files=_file(assets["person_a_1"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["face_count"] == 1
    face = body["faces"][0]
    assert face["index"] == 0
    assert face["score"] > 0.8
    assert len(face["landmarks"]) == 5
    assert 0 < face["box_normalized"]["width"] <= 1
    assert body["image"]["format"] == "jpeg"
    assert body["usage"]["plan"] == "personal"
    assert body["usage"]["request_id"] == response.headers["X-Request-ID"]


def test_detect_can_omit_landmarks(personal_client: TestClient, assets):
    response = personal_client.post(
        "/v1/detect", files=_file(assets["person_a_1"]), params={"include_landmarks": False}
    )
    assert response.json()["faces"][0]["landmarks"] is None


def test_detect_returns_zero_faces_for_a_photo_without_people(personal_client: TestClient, assets):
    response = personal_client.post("/v1/detect", files=_file(assets["no_face"], "x.png", "image/png"))
    assert response.status_code == 200
    assert response.json()["face_count"] == 0


def test_detect_rejects_a_non_image(personal_client: TestClient):
    response = personal_client.post("/v1/detect", files=_file(b"not an image at all", "x.txt", "text/plain"))
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_image"
    assert body["error"]["request_id"]


def test_detect_requires_a_file(personal_client: TestClient):
    response = personal_client.post("/v1/detect")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------------- embed
def test_embed_returns_normalised_vector_and_optional_crop(personal_client: TestClient, assets):
    response = personal_client.post(
        "/v1/embed", files=_file(assets["person_a_1"]), params={"include_crop": True}
    )
    assert response.status_code == 200, response.text
    face = response.json()["faces"][0]
    assert face["dim"] == 128
    assert len(face["embedding"]) == 128
    assert face["aligned_face_base64"]

    import math

    norm = math.sqrt(sum(value * value for value in face["embedding"]))
    assert abs(norm - 1.0) < 1e-4


def test_embed_face_index_out_of_range(personal_client: TestClient, assets):
    response = personal_client.post(
        "/v1/embed", files=_file(assets["person_a_1"]), params={"mode": "index", "face_index": 7}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "face_index_out_of_range"


def test_embed_raises_no_face_found(personal_client: TestClient, assets):
    response = personal_client.post("/v1/embed", files=_file(assets["no_face"], "x.png", "image/png"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_face_found"


# -------------------------------------------------------------------- verify
def test_verify_matches_same_person_across_photos(personal_client: TestClient, assets):
    response = personal_client.post(
        "/v1/verify",
        files={
            "image1": ("a1.jpg", assets["person_a_1"], "image/jpeg"),
            "image2": ("a2.jpg", assets["person_a_2"], "image/jpeg"),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["match"] is True
    assert body["similarity"] > body["threshold"]
    assert body["faces_in_image1"] == 1 and body["faces_in_image2"] == 1


def test_verify_rejects_different_people(personal_client: TestClient, assets):
    body = personal_client.post(
        "/v1/verify",
        files={
            "image1": ("a1.jpg", assets["person_a_1"], "image/jpeg"),
            "image2": ("b1.jpg", assets["person_b_1"], "image/jpeg"),
        },
    ).json()
    assert body["match"] is False
    assert body["similarity"] < body["threshold"]


def test_verify_reports_missing_face_in_second_image(personal_client: TestClient, assets):
    response = personal_client.post(
        "/v1/verify",
        files={
            "image1": ("a1.jpg", assets["person_a_1"], "image/jpeg"),
            "image2": ("none.png", assets["no_face"], "image/png"),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_face_found"


def test_verify_honours_a_custom_threshold(personal_client: TestClient, assets):
    body = personal_client.post(
        "/v1/verify",
        files={
            "image1": ("a1.jpg", assets["person_a_1"], "image/jpeg"),
            "image2": ("b1.jpg", assets["person_b_1"], "image/jpeg"),
        },
        params={"threshold": -1.0},
    ).json()
    assert body["match"] is True  # everything matches at -1.0
    assert body["threshold"] == -1.0


# ------------------------------------------------------------------- compare
def test_compare_round_trip(personal_client: TestClient, assets):
    embedding = personal_client.post("/v1/embed", files=_file(assets["person_a_1"])).json()["faces"][0][
        "embedding"
    ]
    response = personal_client.post(
        "/v1/compare", json={"embedding1": embedding, "embedding2": embedding}
    )
    assert response.status_code == 200
    assert response.json()["match"] is True
    assert response.json()["similarity"] == 1.0


def test_compare_validates_embedding_size(personal_client: TestClient):
    response = personal_client.post("/v1/compare", json={"embedding1": [0.1] * 10, "embedding2": [0.1] * 10})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------- collections
def test_collection_lifecycle_and_identify(personal_client: TestClient, assets):
    created = personal_client.post("/v1/collections", json={"name": "employees", "description": "staff"})
    assert created.status_code == 200, created.text
    assert created.json()["face_count"] == 0

    duplicate = personal_client.post("/v1/collections", json={"name": "employees"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"

    listed = personal_client.get("/v1/collections").json()
    assert any(item["name"] == "employees" for item in listed["collections"])

    enrolled = personal_client.post(
        "/v1/collections/employees/faces",
        files=_file(assets["person_a_1"]),
        data={"external_id": "emp-001", "metadata": json.dumps({"dept": "engineering"})},
    )
    assert enrolled.status_code == 200, enrolled.text
    face_id = enrolled.json()["face_id"]
    assert enrolled.json()["external_id"] == "emp-001"
    assert enrolled.json()["metadata"] == {"dept": "engineering"}

    detail = personal_client.get("/v1/collections/employees").json()
    assert detail["face_count"] == 1

    enrolled_again = personal_client.post(
        "/v1/collections/employees/faces",
        files=_file(assets["person_a_2"]),
        data={"external_id": "emp-002"},
    )
    assert enrolled_again.status_code == 200

    listed_faces = personal_client.get("/v1/collections/employees/faces").json()
    assert listed_faces["count"] == 2
    assert {face["external_id"] for face in listed_faces["faces"]} == {"emp-001", "emp-002"}

    # Probe with the same person: must identify the enrolled record.
    identified = personal_client.post(
        "/v1/identify", files=_file(assets["person_a_2"]), params={"collection": "employees"}
    )
    assert identified.status_code == 200, identified.text
    body = identified.json()
    assert body["match"] is True
    assert body["best_match"]["external_id"] in {"emp-001", "emp-002"}
    assert body["gallery_size"] == 2
    assert body["candidates"][0]["similarity"] > 0.36

    # Probe with a stranger: must NOT match.
    stranger = personal_client.post(
        "/v1/identify", files=_file(assets["person_b_1"]), params={"collection": "employees"}
    ).json()
    assert stranger["match"] is False
    assert stranger["best_match"] is None
    assert stranger["candidates"]  # near-misses are still reported

    removed = personal_client.delete(f"/v1/collections/employees/faces/{face_id}")
    assert removed.status_code == 200
    assert personal_client.get("/v1/collections/employees").json()["face_count"] == 1

    assert personal_client.delete("/v1/collections/employees").status_code == 200
    assert personal_client.get("/v1/collections/employees").status_code == 404


def test_identify_unknown_collection_returns_404(personal_client: TestClient, assets):
    response = personal_client.post(
        "/v1/identify", files=_file(assets["person_a_1"]), params={"collection": "does-not-exist"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_collection_name_is_validated(personal_client: TestClient):
    response = personal_client.post("/v1/collections", json={"name": "bad name!"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_enrol_rejects_invalid_metadata(personal_client: TestClient, assets):
    personal_client.post("/v1/collections", json={"name": "meta-test"})
    response = personal_client.post(
        "/v1/collections/meta-test/faces",
        files=_file(assets["person_a_1"]),
        data={"metadata": "{not json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_metadata"


# ------------------------------------------------------------------ account
def test_me_reports_plan_and_usage(personal_client: TestClient, assets):
    personal_client.post("/v1/detect", files=_file(assets["person_a_1"]))
    body = personal_client.get("/v1/me").json()
    assert body["key"]["personal_mode"] is True
    assert body["key"]["plan"] == "personal"
    assert body["usage"]["requests"] >= 1
    assert any(row["endpoint"] == "/v1/detect" for row in body["usage"]["by_endpoint"])


def test_usage_is_only_recorded_for_billed_paths(personal_client: TestClient):
    before = personal_client.get("/v1/me").json()["usage"]["requests"]
    personal_client.get("/healthz")
    personal_client.get("/metrics")
    after = personal_client.get("/v1/me").json()["usage"]["requests"]
    assert after == before + 1  # only the /v1/me call itself
