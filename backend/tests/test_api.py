def test_registration_login_and_protection(client):
    assert client.get("/api/vehicles").status_code == 401
    response = client.post("/api/auth/register", json={"email": "a@example.com", "password": "securepass123"})
    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert client.post("/api/auth/register", json={"email": "a@example.com", "password": "securepass123"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "securepass123"}).json()["token"]
    assert client.get("/api/vehicles", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_vehicle_crud_search_and_roles(client, admin, buyer, vehicle):
    assert client.post("/api/vehicles", json=vehicle, headers=buyer).status_code == 403
    created = client.post("/api/vehicles", json=vehicle, headers=admin)
    assert created.status_code == 201
    vid = created.json()["id"]
    assert client.get("/api/vehicles", headers=buyer).json()[0]["id"] == vid
    assert len(client.get("/api/vehicles/search?make=toy&model=roll&category=sed&min_price=14000&max_price=15000", headers=buyer).json()) == 1
    assert client.get("/api/vehicles/search?min_price=16000", headers=buyer).json() == []
    assert client.get("/api/vehicles/search?min_price=200&max_price=100", headers=buyer).status_code == 422
    assert client.put(f"/api/vehicles/{vid}", json={"price": 13500}, headers=buyer).status_code == 403
    assert client.put(f"/api/vehicles/{vid}", json={"price": 13500}, headers=admin).json()["price"] == 13500
    assert client.delete(f"/api/vehicles/{vid}", headers=buyer).status_code == 403
    assert client.delete(f"/api/vehicles/{vid}", headers=admin).status_code == 204
    assert client.delete(f"/api/vehicles/{vid}", headers=admin).status_code == 404


def test_purchase_restock_and_validation(client, admin, buyer, vehicle):
    assert client.post("/api/vehicles", json={**vehicle, "price": -1}, headers=admin).status_code == 422
    vid = client.post("/api/vehicles", json={**vehicle, "quantity": 1}, headers=admin).json()["id"]
    assert client.post(f"/api/vehicles/{vid}/purchase", headers=buyer).json()["quantity"] == 0
    assert client.post(f"/api/vehicles/{vid}/purchase", headers=buyer).status_code == 409
    assert client.post(f"/api/vehicles/{vid}/restock", json={"quantity": 2}, headers=buyer).status_code == 403
    assert client.post(f"/api/vehicles/{vid}/restock", json={"quantity": 0}, headers=admin).status_code == 422
    assert client.post(f"/api/vehicles/{vid}/restock", json={"quantity": 3}, headers=admin).json()["quantity"] == 3
    assert client.post("/api/vehicles/9999/purchase", headers=buyer).status_code == 404
