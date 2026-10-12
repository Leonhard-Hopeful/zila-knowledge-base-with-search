from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

# Gives Swagger UI a single "Authorize" button for the x-api-key header.
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def require_api_key(key: str | None = Security(api_key_header)):
    if not key or key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
