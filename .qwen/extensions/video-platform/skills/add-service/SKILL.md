---
name: add-service
description: Add a new external service wrapper (LLM, TTS, video generation, etc.) to the video platform. Use when integrating a new API or model provider.
---

This skill adds a service wrapper that agents use to interact with external APIs.

## When to Use

- Integrating a new LLM provider (OpenAI, Anthropic, local models)
- Adding a TTS service (ElevenLabs, OpenAI TTS, Coqui)
- Adding a video generation service (Runway, Kling, Pika)
- Wrapping any external API the pipeline depends on

## Steps

### 1. Create the Service File

Create `app/services/<service_name>.py`:

```python
import os
from typing import Optional
import httpx

class <ServiceName>Client:
    """Client for <service> API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("<SERVICE>_API_KEY")
        if not self.api_key:
            raise ValueError(f"<SERVICE>_API_KEY environment variable not set")
        self.base_url = os.getenv("<SERVICE>_BASE_URL", "<default_url>")
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def <primary_method>(self, **kwargs) -> dict:
        """<What this method does>."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {<build payload from kwargs>}
        
        response = await self.client.post(
            f"{self.base_url}/<endpoint>",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        await self.client.aclose()
```

### 2. Add Config to app/config.py

```python
class Settings(BaseSettings):
    # ... existing settings
    
    <SERVICE>_API_KEY: str = ""
    <SERVICE>_BASE_URL: str = "<default>"
    <SERVICE>_MODEL: str = "<default_model>"
```

### 3. Update .env.example

```bash
# <Service> Configuration
<SERVICE>_API_KEY=your_api_key_here
<SERVICE>_BASE_URL=https://api.example.com/v1
<SERVICE>_MODEL=default-model-name
```

### 4. Add Tests

Create `tests/test_services/test_<service_name>.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.<service_name> import <ServiceName>Client

class Test<ServiceName>Client:
    @pytest.fixture
    def client(self):
        with patch.dict(os.environ, {"<SERVICE>_API_KEY": "test-key"}):
            return <ServiceName>Client()
    
    async def test_primary_method(self, client):
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json.return_value = {"result": "data"}
            result = await client.<primary_method>(input="test")
            assert result == {"result": "data"}
            mock_post.assert_called_once()
```

## Best Practices

- **Timeouts**: Set appropriate timeouts (60s for LLM, 120s+ for video gen)
- **Retries**: Use `tenacity` for retry logic with exponential backoff
- **Rate Limits**: Respect rate limits; add `asyncio.sleep()` between calls if needed
- **Error Handling**: Raise typed exceptions that the agent can catch and handle
- **Mocking**: Always provide a way to mock the service in tests

## Checklist

- [ ] Service class takes `api_key` in constructor (with env var fallback)
- [ ] Uses `httpx.AsyncClient` for async HTTP
- [ ] Timeouts are configured
- [ ] Error responses raise appropriate exceptions
- [ ] Config added to `app/config.py`
- [ ] `.env.example` updated with new variables
- [ ] Unit tests mock the HTTP layer
