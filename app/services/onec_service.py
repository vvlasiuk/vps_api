import time

import httpx
from fastapi import HTTPException

from ..runtime import ONEC_TOKEN, error_logger


def call_onec_save(url: str, payload: dict) -> dict:
    payload = {**payload, "token": ONEC_TOKEN}
    t0 = time.time()
    try:
        response = httpx.post(url, json=payload, timeout=30)
    except httpx.RequestError as exc:
        error_logger.log_error(f"1С недоступний: {exc}", responsibility="vps_api")
        raise HTTPException(status_code=503, detail="1С сервіс недоступний")

    print(f"[1c call] save {url} - {int((time.time() - t0) * 1000)} ms")

    if response.status_code == 401:
        raise HTTPException(status_code=502, detail="Помилка авторизації до 1С")

    if response.status_code == 409:
        try:
            data = response.json()
            detail = data.get("error", "Документ змінено іншим користувачем")
        except Exception:
            detail = "Документ змінено іншим користувачем"
        raise HTTPException(status_code=409, detail=detail)

    if response.status_code != 200:
        try:
            data = response.json()
            detail = data.get("error", "Помилка 1С")
        except Exception:
            detail = f"1С повернула HTTP {response.status_code}: {response.text[:300]}"
        error_logger.log_error(f"1С помилка: {detail}", responsibility="vps_api")
        raise HTTPException(status_code=502, detail=detail)

    return response.json()

def call_onec_read(url: str, payload: dict, label: str = "read") -> dict:
    payload = {**payload, "token": ONEC_TOKEN}
    t0 = time.time()
    try:
        response = httpx.post(url, json=payload, timeout=30)
    except httpx.RequestError as exc:
        error_logger.log_error(f"1С недоступний: {exc}", responsibility="vps_api")
        raise HTTPException(status_code=503, detail="1С сервіс недоступний")

    print(f"[1c call] {label} {url} - {int((time.time() - t0) * 1000)} ms")

    if response.status_code == 401:
        raise HTTPException(status_code=502, detail="Помилка авторизації до 1С")

    if response.status_code != 200:
        try:
            data = response.json()
            detail = data.get("error", "Помилка 1С")
        except Exception:
            detail = f"1С повернула HTTP {response.status_code}: {response.text[:300]}"
        error_logger.log_error(f"1С помилка: {detail}", responsibility="vps_api")
        raise HTTPException(status_code=502, detail=detail)

    return response.json()