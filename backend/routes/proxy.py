import json
import re
import logging
from urllib.parse import urlparse
import httpx
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import Response, HTMLResponse

logger = logging.getLogger("formpilot-backend")
router = APIRouter()

@router.api_route("/proxy", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_page(request: Request, url: str = Query(..., description="Target URL to proxy")):
    """
    Fetches the target URL, strips X-Frame-Options / CSP headers that block
    iframe embedding, and injects a <base> tag so relative URLs still resolve
    against the original domain.  This makes the form fully interactive inside
    our frontend's iframe (same-origin = full DOM access for autofill).
    """
    parsed_input = urlparse(url)
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    hostname = (parsed_input.hostname or "").lower()
    if parsed_input.scheme not in {"http", "https"} or not hostname:
        raise HTTPException(status_code=400, detail="Only absolute http(s) URLs can be embedded.")
    if hostname in blocked_hosts or hostname.endswith(".local"):
        raise HTTPException(status_code=400, detail="Local/private URLs cannot be proxied.")

    method = request.method
    body = await request.body()

    # Forward headers, avoiding host/connection conflicts
    forward_headers = {}
    excluded_headers = {"host", "connection", "accept-encoding", "content-length"}
    for k, v in request.headers.items():
        if k.lower() not in excluded_headers:
            forward_headers[k] = v

    # Add browser-like User-Agent and headers if not set
    if "user-agent" not in {k.lower() for k in forward_headers.keys()}:
        forward_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    if "accept" not in {k.lower() for k in forward_headers.keys()}:
        forward_headers["Accept"] = "*/*"
    if "accept-language" not in {k.lower() for k in forward_headers.keys()}:
        forward_headers["Accept-Language"] = "en-US,en;q=0.9"

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=forward_headers,
                content=body
            )
    except Exception as e:
        logger.error(f"Proxy fetch failed for {url}: {e}")
        accept_header = request.headers.get("accept", "")
        headers = {"Access-Control-Allow-Origin": "*"}
        if "text/html" not in accept_header:
            return Response(
                content=json.dumps({"error": "Proxy fetch failed", "details": str(e)}),
                media_type="application/json",
                status_code=502,
                headers=headers
            )
        return HTMLResponse(
            content=f"<html><body><h2>Failed to load form</h2><p>{str(e)}</p></body></html>",
            status_code=502,
            headers=headers
        )

    content_type = resp.headers.get("content-type", "")

    # Only process HTML responses
    if "text/html" not in content_type:
        response_headers = {}
        for k, v in resp.headers.items():
            if k.lower() not in {"content-length", "content-encoding", "transfer-encoding", "connection", "access-control-allow-origin"}:
                response_headers[k] = v
        response_headers["Access-Control-Allow-Origin"] = "*"
        return Response(content=resp.content, status_code=resp.status_code, headers=response_headers, media_type=content_type)

    html = resp.text

    # Inject <base href> so relative URLs (CSS, JS, images, form actions)
    # resolve against the original domain instead of localhost.
    parsed = urlparse(str(resp.url))  # use final URL after redirects
    # Build base from the directory of the current path
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = path.rsplit("/", 1)[0] + "/"
    base_href = f"{parsed.scheme}://{parsed.netloc}{path}"

    base_tag = f'<base href="{base_href}">'
    history_script = (
        "<script>\n"
        "  // 1. Rewrite history pathname to match target URL path for client routers\n"
        "  try {\n"
        "    const urlParams = new URLSearchParams(window.location.search);\n"
        "    const targetUrlStr = urlParams.get('url');\n"
        "    if (targetUrlStr) {\n"
        "      const targetUrl = new URL(targetUrlStr);\n"
        "      const cleanPath = targetUrl.pathname + targetUrl.search + targetUrl.hash;\n"
        "      const absolutePath = window.location.origin + cleanPath;\n"
        "      window.history.replaceState(null, '', absolutePath);\n"
        "    }\n"
        "  } catch (e) {\n"
        "    console.error('Failed to rewrite history path:', e);\n"
        "  }\n"
        "\n"
        "  // 2. Intercept fetch & XHR to proxy relative and cross-origin requests to avoid CORS block\n"
        "  try {\n"
        "    let baseOrigin = 'https://job-boards.greenhouse.io';\n"
        "    const baseTag = document.querySelector('base');\n"
        "    if (baseTag && baseTag.href) {\n"
        "      baseOrigin = new URL(baseTag.href).origin;\n"
        "    }\n"
        "\n"
        "    function proxyUrl(url) {\n"
        "      if (!url) return url;\n"
        "      if (url.startsWith('/proxy') || url.includes('localhost') || url.includes('127.0.0.1')) {\n"
        "        return url;\n"
        "      }\n"
        "      // Only proxy external http(s) URLs or relative API paths, leave inline assets (data:, blob:) alone\n"
        "      if (url.startsWith('data:') || url.startsWith('blob:') || url.startsWith('javascript:')) {\n"
        "        return url;\n"
        "      }\n"
        "      let absoluteUrl = url;\n"
        "      if (!url.startsWith('http')) {\n"
        "        absoluteUrl = baseOrigin + (url.startsWith('/') ? '' : '/') + url;\n"
        "      }\n"
        "      // Only proxy requests targeted to external domains to avoid loops\n"
        "      if (absoluteUrl.includes(window.location.host)) {\n"
        "        return url;\n"
        "      }\n"
        "      return window.location.origin + '/proxy?url=' + encodeURIComponent(absoluteUrl);\n"
        "    }\n"
        "\n"
        "    const originalFetch = window.fetch;\n"
        "    window.fetch = function(input, init) {\n"
        "      if (!input) return originalFetch(input, init);\n"
        "      let url = typeof input === 'string' ? input : input.url;\n"
        "      let newUrl = proxyUrl(url);\n"
        "      if (newUrl !== url) {\n"
        "        if (typeof input === 'string') {\n"
        "          input = newUrl;\n"
        "        } else {\n"
        "          input = new Request(newUrl, input);\n"
        "        }\n"
        "      }\n"
        "      return originalFetch(input, init);\n"
        "    };\n"
        "\n"
        "    const originalOpen = XMLHttpRequest.prototype.open;\n"
        "    XMLHttpRequest.prototype.open = function(method, url, ...args) {\n"
        "      let newUrl = proxyUrl(url);\n"
        "      return originalOpen.call(this, method, newUrl, ...args);\n"
        "    };\n"
        "  } catch (e) {\n"
        "    console.error('Failed to initialize fetch interceptors:', e);\n"
        "  }\n"
        "</script>"
    )
    injection = base_tag + "\n" + history_script

    if '<head>' in html.lower():
        html = re.sub(r'(<head[^>]*>)', lambda m: m.group(1) + injection, html, count=1, flags=re.IGNORECASE)
    elif '<html' in html.lower():
        html = re.sub(r'(<html[^>]*>)', lambda m: m.group(1) + '<head>' + injection + '</head>', html, count=1, flags=re.IGNORECASE)
    else:
        html = injection + html

    headers = {"Access-Control-Allow-Origin": "*"}
    return HTMLResponse(content=html, headers=headers)
