from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import aiohttp
from typing import List, Optional, Dict
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, func, text
import json
import asyncio
import time
from pydantic import BaseModel

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/weather_db")
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

class SearchHistory(Base):
    __tablename__ = "search_history"
    
    id = Column(Integer, primary_key=True)
    city = Column(String, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    search_count = Column(Integer, default=1)

@app.on_event("startup")
async def startup():
    # задержка для активации бд, перед запуском server UVICORN
    for _ in range(30):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                print("БД инициализирована")
                return
        except Exception as e:
            print(f"Ошибка БД: {e}")
            await asyncio.sleep(1)
    raise Exception("30 неудачных подключений к БД")

# создание ручек 
@app.get("/")
async def read_root():
    with open("app/static/index.html") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/weather/{city}")
async def get_weather(city: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=ru") as response:
            if response.status != 200:
                raise HTTPException(status_code=404, detail="Город не найден")
            data = await response.json()
            if not data.get("results"):
                raise HTTPException(status_code=404, detail="Город не найден")
            
            location = data["results"][0]
            lat, lon = location["latitude"], location["longitude"]

            # !!! РУССКОЕ НАЗВАНИЕ ГОРОДОВ !!!!
            russian_city = location["name"]  
            
            # прогноз погоды
            async with session.get(
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
            ) as response:
                weather_data = await response.json()
                
                # Сохраняем историю поиска с русским названием
                async with async_session() as session:
                    history = SearchHistory(city=russian_city)
                    session.add(history)
                    await session.commit()
                
                return {
                    "city": russian_city,
                    "temperature": weather_data["current"]["temperature_2m"],
                    "humidity": weather_data["current"]["relative_humidity_2m"],
                    "wind_speed": weather_data["current"]["wind_speed_10m"]
                }

@app.get("/api/history")
async def get_search_history(session: AsyncSession = Depends(get_db)):
    try:
        result = await session.execute(
            text("""
                SELECT city, COUNT(*) as count, MAX(timestamp) as last_searched
                FROM search_history
                GROUP BY city
                ORDER BY count DESC, last_searched DESC
                LIMIT 10
            """)
        )
        history = result.fetchall()
        return [
            {
                "city": row[0],
                "count": row[1],
                "last_searched": row[2].isoformat() if row[2] else None
            }
            for row in history
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/static", StaticFiles(directory="app/static"), name="static") 