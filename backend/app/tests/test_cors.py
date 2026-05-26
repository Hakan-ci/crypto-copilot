import asyncio

import httpx

from app.main import create_app


def test_cors_allows_local_frontend_origin():
    async def preflight() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

    response = asyncio.run(preflight())

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
