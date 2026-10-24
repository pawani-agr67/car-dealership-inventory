"""Car inventory API. SQLite transactions keep stock changes atomic."""
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator


def database_path():
    return os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parent.parent / "inventory.sqlite3"))


@contextmanager
def db():
    connection = sqlite3.connect(database_path(), timeout=15, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    try:
        yield connection
    finally:
        connection.close()


def initialize():
    with db() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user'
            );
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY, make TEXT NOT NULL, model TEXT NOT NULL,
                category TEXT NOT NULL, price REAL NOT NULL CHECK(price >= 0),
                quantity INTEGER NOT NULL CHECK(quantity >= 0)
            );
        """)


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="Car Dealership Inventory", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")], allow_methods=["*"], allow_headers=["*"])
bearer = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return value


class LoginCredentials(Credentials):
    password: str = Field(min_length=1)


class VehicleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    price: float = Field(ge=0, allow_inf_nan=False)
    quantity: int = Field(ge=0)


class VehicleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    make: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    quantity: int | None = Field(default=None, ge=0)


class Restock(BaseModel):
    quantity: int = Field(gt=0)


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return f"{salt.hex()}:{digest.hex()}"


def check_password(password, encoded):
    try:
        salt, digest = encoded.split(":")
        calculated = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000)
        return hmac.compare_digest(calculated, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def token_secret():
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("Set JWT_SECRET in your environment before starting the API")
    return secret


def current_user(auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if auth is None:
        raise HTTPException(401, "Authentication required")
    try:
        payload = jwt.decode(auth.credentials, token_secret(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Invalid or expired token")
    with db() as connection:
        user = connection.execute("SELECT id, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(401, "User no longer exists")
    return dict(user)


def admin_only(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def vehicle_or_404(connection, vehicle_id):
    row = connection.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Vehicle not found")
    return dict(row)


@app.post("/api/auth/register", status_code=201)
def register(credentials: Credentials):
    with db() as connection:
        try:
            cursor = connection.execute("INSERT INTO users(email, password_hash) VALUES(?, ?)", (credentials.email, hash_password(credentials.password)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Email already registered")
    return {"id": cursor.lastrowid, "email": credentials.email, "role": "user"}


@app.post("/api/auth/login")
def login(credentials: LoginCredentials):
    with db() as connection:
        user = connection.execute("SELECT * FROM users WHERE email = ?", (credentials.email,)).fetchone()
    if user is None or not check_password(credentials.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = jwt.encode({"sub": str(user["id"]), "exp": datetime.now(timezone.utc) + timedelta(hours=8)}, token_secret(), algorithm="HS256")
    return {"token": token, "token_type": "bearer", "role": user["role"], "email": user["email"]}


@app.get("/api/vehicles")
def list_vehicles(user=Depends(current_user)):
    with db() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM vehicles ORDER BY id DESC")]


@app.get("/api/vehicles/search")
def search_vehicles(make: str | None = None, model: str | None = None, category: str | None = None, min_price: float | None = None, max_price: float | None = None, user=Depends(current_user)):
    if (min_price is not None and min_price < 0) or (max_price is not None and max_price < 0) or (min_price is not None and max_price is not None and min_price > max_price):
        raise HTTPException(422, "Invalid price range")
    clauses, params = [], []
    for column, value in (("make", make), ("model", model), ("category", category)):
        if value:
            clauses.append(f"LOWER({column}) LIKE ?")
            params.append(f"%{value.lower()}%")
    if min_price is not None:
        clauses.append("price >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("price <= ?")
        params.append(max_price)
    query = "SELECT * FROM vehicles" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY id DESC"
    with db() as connection:
        return [dict(row) for row in connection.execute(query, params)]


@app.post("/api/vehicles", status_code=201)
def add_vehicle(vehicle: VehicleInput, user=Depends(admin_only)):
    with db() as connection:
        cursor = connection.execute("INSERT INTO vehicles(make, model, category, price, quantity) VALUES(?,?,?,?,?)", tuple(vehicle.model_dump().values()))
        return vehicle_or_404(connection, cursor.lastrowid)


@app.put("/api/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, changes: VehicleUpdate, user=Depends(admin_only)):
    values = changes.model_dump(exclude_unset=True)
    if not values or any(value is None for value in values.values()):
        raise HTTPException(422, "Provide non-null fields to update")
    with db() as connection:
        vehicle_or_404(connection, vehicle_id)
        connection.execute("UPDATE vehicles SET " + ", ".join(f"{key} = ?" for key in values) + " WHERE id = ?", (*values.values(), vehicle_id))
        return vehicle_or_404(connection, vehicle_id)


@app.delete("/api/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, user=Depends(admin_only)):
    with db() as connection:
        if connection.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,)).rowcount == 0:
            raise HTTPException(404, "Vehicle not found")


@app.post("/api/vehicles/{vehicle_id}/purchase")
def purchase(vehicle_id: int, user=Depends(current_user)):
    with db() as connection:
        updated = connection.execute("UPDATE vehicles SET quantity = quantity - 1 WHERE id = ? AND quantity > 0", (vehicle_id,))
        if updated.rowcount == 0:
            vehicle_or_404(connection, vehicle_id)
            raise HTTPException(409, "Vehicle is out of stock")
        return vehicle_or_404(connection, vehicle_id)


@app.post("/api/vehicles/{vehicle_id}/restock")
def restock(vehicle_id: int, restock: Restock, user=Depends(admin_only)):
    with db() as connection:
        updated = connection.execute("UPDATE vehicles SET quantity = quantity + ? WHERE id = ?", (restock.quantity, vehicle_id))
        if updated.rowcount == 0:
            raise HTTPException(404, "Vehicle not found")
        return vehicle_or_404(connection, vehicle_id)
