from fastapi import Header, HTTPException, status

from app.config import settings


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    """Gate for endpoints called by the Next.js frontend (see plan: Auth & Sharing)."""
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token"
        )
