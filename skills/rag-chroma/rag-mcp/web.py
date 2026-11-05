"""Local inspector routes. Calls the exact audited functions exposed through MCP."""
import inspect
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ConfigDict, ValidationError, create_model
from starlette.responses import FileResponse, JSONResponse
from audit import TOOLS

STATIC = Path(__file__).parent / "static"


def register_web(mcp):
    @mcp.custom_route("/", methods=["GET"])
    async def index(request):
        return FileResponse(STATIC / "index.html", headers={
            "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff"})

    @mcp.custom_route("/app.js", methods=["GET"])
    async def javascript(request):
        return FileResponse(STATIC / "app.js", media_type="text/javascript")

    @mcp.custom_route("/style.css", methods=["GET"])
    async def stylesheet(request):
        return FileResponse(STATIC / "style.css", media_type="text/css")

    @mcp.custom_route("/api/tools", methods=["GET"])
    async def tools(request):
        return JSONResponse({"tools": [{"name": n, "description": inspect.getdoc(f) or ""}
                                      for n, f in TOOLS.items()]})

    @mcp.custom_route("/api/call", methods=["POST"])
    async def call(request):
        # No cross-origin tool execution, including form-based requests.
        origin = request.headers.get("origin")
        if origin and (urlsplit(origin).netloc != request.url.netloc
                       or urlsplit(origin).scheme != request.url.scheme):
            return JSONResponse({"error": "Cross-origin calls are not allowed"}, status_code=403)
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"error": "Use application/json"}, status_code=415)
        try:
            body = await request.json()
            name = body.get("tool")
            if name not in TOOLS:
                return JSONResponse({"error": "Unknown tool"}, status_code=404)
            if name in ("rag_clear", "rag_remove") and body.get("confirm") != name:
                return JSONResponse({"error": f"Confirm {name} before deleting indexed data"}, status_code=400)
            fn = TOOLS[name]
            fields = {n: (p.annotation, ... if p.default is inspect.Parameter.empty else p.default)
                      for n, p in inspect.signature(fn).parameters.items()}
            model = create_model("Arguments", __config__=ConfigDict(extra="forbid"), **fields)
            arguments = model(**body.get("arguments", {})).model_dump()
            return JSONResponse(await fn(**arguments))
        except (ValueError, TypeError, ValidationError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
