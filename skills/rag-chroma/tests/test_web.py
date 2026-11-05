import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rag-mcp'))
import httpx
from starlette.applications import Starlette
from starlette.routing import Route
import web


class Routes:
    def __init__(self):
        self.routes = []
    def custom_route(self, path, methods):
        def register(fn):
            self.routes.append(Route(path, fn, methods=methods))
            return fn
        return register


class WebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.routes = Routes()
        web.register_web(self.routes)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=Starlette(routes=self.routes.routes)), base_url='http://localhost')
    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_tool_validation_and_dispatch(self):
        async def sample(query: str, k: int = 5) -> dict:
            return {'query': query, 'k': k}
        with patch.dict(web.TOOLS, {'sample': sample}, clear=True):
            res = await self.client.post('/api/call', json={'tool': 'sample', 'arguments': {'query': 'test'}})
            self.assertEqual(res.json(), {'query': 'test', 'k': 5})
            res = await self.client.post('/api/call', json={'tool': 'sample', 'arguments': {'query': 'test', 'bogus': True}})
            self.assertEqual(res.status_code, 400)

    async def test_cross_origin_and_form_posts_rejected(self):
        res = await self.client.post('/api/call', json={}, headers={'Origin': 'https://evil.example'})
        self.assertEqual(res.status_code, 403)
        res = await self.client.post('/api/call', content='tool=rag_clear')
        self.assertEqual(res.status_code, 415)

    async def test_clear_requires_explicit_confirmation(self):
        async def clear() -> dict:
            return {'cleared': 10}
        with patch.dict(web.TOOLS, {'rag_clear': clear}, clear=True):
            self.assertEqual((await self.client.post('/api/call', json={'tool': 'rag_clear'})).status_code, 400)
            res = await self.client.post('/api/call', json={'tool': 'rag_clear', 'confirm': 'rag_clear'})
            self.assertEqual(res.json(), {'cleared': 10})

    async def test_unknown_tool_and_internal_error(self):
        self.assertEqual((await self.client.post('/api/call', json={'tool': 'unknown'})).status_code, 404)
        async def broken() -> dict:
            raise RuntimeError('backend unavailable')
        with patch.dict(web.TOOLS, {'broken': broken}, clear=True):
            res = await self.client.post('/api/call', json={'tool': 'broken'})
            self.assertEqual(res.status_code, 500)
            self.assertIn('backend unavailable', res.json()['error'])


if __name__ == '__main__':
    unittest.main()
