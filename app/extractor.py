"""Extrai a localização escrita na foto (carimbo de app de câmera com GPS).

Usa a API do Gemini via REST (httpx, Python puro): sem SDK, sem arquivos
compilados que o Controle de Aplicativo do Windows possa bloquear.
"""
import base64
import json
import re

import httpx

from . import config

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """Esta é uma foto de serviço de sinalização viária com um carimbo de localização
(texto sobreposto na imagem, geralmente com endereço e coordenadas).
Leia SOMENTE o que está escrito na imagem. Não invente nada.
Responda apenas com JSON neste formato:
{"rua": str|null, "bairro": str|null, "cidade": str|null,
 "latitude": float|null, "longitude": float|null,
 "data_hora": str|null, "confianca": "alta"|"media"|"baixa"}
Use null para o que não estiver legível."""

VAZIO = {"rua": None, "bairro": None, "cidade": None, "latitude": None,
         "longitude": None, "data_hora": None, "confianca": "baixa"}


def extrair_localizacao(imagem: bytes, mime: str) -> dict:
    try:
        resp = httpx.post(
            API_URL.format(model=config.GEMINI_MODEL),
            headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [
                    {"inline_data": {"mime_type": mime, "data": base64.b64encode(imagem).decode()}},
                    {"text": PROMPT},
                ]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
            },
            timeout=60,
        )
        resp.raise_for_status()
        partes = resp.json()["candidates"][0]["content"]["parts"]
        texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
        texto = re.sub(r"```json|```", "", texto).strip()
        return {**VAZIO, **json.loads(texto)}
    except Exception as e:  # noqa: BLE001 - se falhar, o bot pergunta ao usuário
        print("falha na extração:", repr(e))
        return dict(VAZIO)