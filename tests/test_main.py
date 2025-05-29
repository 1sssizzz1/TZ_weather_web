import pytest
from fastapi.testclient import TestClient
from app.main import app, Base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

# тест БД
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/test_weather_db"
engine = create_async_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture
async def test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
def client(test_db):
    return TestClient(app)

def test_read_main(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Прогноз погоды" in response.text

def test_get_weather(client):
    response = client.get("/api/weather/Moscow")
    assert response.status_code == 200
    data = response.json()
    assert "city" in data
    assert "temperature" in data
    assert "humidity" in data
    assert "wind_speed" in data

def test_get_weather_invalid_city(client):
    response = client.get("/api/weather/InvalidCity123")
    assert response.status_code == 404

def test_get_history(client):

    client.get("/api/weather/Moscow")
    
    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "city" in data[0]
    assert "count" in data[0] 