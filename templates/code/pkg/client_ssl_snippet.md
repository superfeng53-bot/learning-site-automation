# HttpClient SSL 校验（Phase 1 client.py + config.py）

部分站点证书链在 **macOS 自带 Python** 下无法通过校验（`CERTIFICATE_VERIFY_FAILED` / `certificate has expired`），浏览器仍可访问。在 `<pkg>/config.py` 增加：

```python
import os

# 默认关闭校验；生产可设环境变量 <PKG>_SSL_VERIFY=1 强制开启
SSL_VERIFY = os.environ.get("<PKG_UPPER>_SSL_VERIFY", "0").strip().lower() in ("1", "true", "yes")
```

在 `<pkg>/client.py` 的 `HttpClient.__init__`：

```python
from .config import SSL_VERIFY

if not SSL_VERIFY:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

self.session = requests.Session()
self.session.verify = SSL_VERIFY
```

**验收**：`client.api_get(...)` 对业务 API 返回 200/401（非 SSL 错误）。

**反模式**：不要全局 `verify=False` 散落在各 `requests.get` — 统一走 `HttpClient.session`。
