import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from dzh_refresh.db import get_connection

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _format_time(dt: datetime) -> str:
    """Format datetime to yyyyMMdd-HHmmss-SSS."""
    return dt.strftime("%Y%m%d-%H%M%S-") + f"{dt.microsecond // 1000:03d}"


class DzhTokenStore:
    """基于 MySQL 的 token 存取."""

    def __init__(self, app_id: str, table: str = "dzh_token") -> None:
        self.app_id = app_id
        self.table = table
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS `{self.table}` (
                        app_id VARCHAR(64) NOT NULL PRIMARY KEY,
                        token VARCHAR(512) NOT NULL,
                        expire_at DATETIME NOT NULL,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def load(self) -> Optional[Dict[str, Any]]:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT token, expire_at FROM `{self.table}` WHERE app_id=%s LIMIT 1",
                    (self.app_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                token, expire_at = row[0], row[1]
                expire_ts = expire_at.timestamp() if expire_at else 0
                return {"token": token, "expire_ts": expire_ts}
        finally:
            conn.close()

    def save(self, token: str, expire_ts: float) -> None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO `{self.table}` (app_id, token, expire_at)
                    VALUES (%s, %s, FROM_UNIXTIME(%s))
                    ON DUPLICATE KEY UPDATE
                        token = VALUES(token),
                        expire_at = VALUES(expire_at)
                    """,
                    (self.app_id, token, expire_ts),
                )
            conn.commit()
        finally:
            conn.close()


class DzhRestClient:
    """Lightweight client for 大智慧 REST gateway."""

    def __init__(
        self,
        app_id: str,
        secret_key: str,
        base_url: str = "https://gw.yundzh.com",
        timeout: int = 12,
        max_retry: int = 5,
        token_store: Optional[DzhTokenStore] = None,
    ) -> None:
        self.app_id = app_id
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retry = max_retry
        self.session = requests.Session()
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0
        self.token_store = token_store or DzhTokenStore(app_id)

    def get_access_token(self, force: bool = False) -> str:
        """Get token, refresh when missing/expired or force=True."""
        now = time.time()
        if not force:
            # 先看内存缓存
            if self._access_token and now < self._token_expire_at:
                return self._access_token
            # 再看数据库缓存
            stored = self.token_store.load()
            if stored and now < stored.get("expire_ts", 0):
                self._access_token = stored["token"]
                self._token_expire_at = stored["expire_ts"]
                return self._access_token

        params = {"appid": self.app_id, "secret_key": self.secret_key}
        resp = self.session.get(
            f"{self.base_url}/token/access", params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("Err") != 0:
            raise RuntimeError(f"获取token失败: {payload}")
        token_obj = payload["Data"]["RepDataToken"][0]
        token = token_obj["token"]
        duration = token_obj.get("duration", 0)
        expire_ts = time.time() + max(duration - 60, 0)
        self._access_token = token
        self._token_expire_at = expire_ts
        # 持久化到数据库
        self.token_store.save(token, expire_ts)
        logger.info("获取到新token，时长 %ss", duration)
        return self._access_token

    def _is_token_invalid(self, payload: Dict[str, Any]) -> bool:
        """Check whether response indicates token invalid/expired."""
        if payload.get("Err") != -1:
            return False
        data = payload.get("Data") or {}
        desc = str(data.get("desc") or "").lower()
        return "token invalid" in desc or "token expired" in desc

    def _request(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call REST API with retry and token refresh."""
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retry):
            token = self.get_access_token(force=False)
            merged = dict(params)
            merged["token"] = token
            try:
                resp = self.session.get(
                    f"{self.base_url}{path}", params=merged, timeout=self.timeout
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: PERF203  # keep readability
                last_err = exc
                time.sleep(1.5 * (attempt + 1))
                continue

            if payload.get("Err") == 0:
                return payload

            if self._is_token_invalid(payload):
                logger.warning("token失效，刷新后重试")
                self.get_access_token(force=True)
                continue

            desc = ""
            data = payload.get("Data")
            if isinstance(data, dict):
                desc = str(data.get("desc") or "")
            last_err = RuntimeError(f"调用失败 Err={payload.get('Err')} desc={desc}")
            time.sleep(1.5 * (attempt + 1))

        if last_err:
            raise last_err
        raise RuntimeError("大智慧接口调用失败且无错误信息")

    def fetch_kline(
        self,
        obj: str,
        period: str,
        begin_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        count: int = 500,
        split: int = 1,
    ) -> List[Dict[str, Any]]:
        """Fetch K-line bars."""
        params: Dict[str, Any] = {
            "obj": obj,
            "period": period,
            "count": count,
            "split": split,
        }
        if begin_time:
            params["begin_time"] = _format_time(begin_time)
        if end_time:
            params["end_time"] = _format_time(end_time)

        payload = self._request("/quote/kline", params)
        return self._parse_kline(payload)

    @staticmethod
    def _parse_kline(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse JsonTbl structure to a list of dict bars."""
        json_tbl = (payload.get("Data") or {}).get("JsonTbl")
        if not json_tbl:
            return []

        data_rows = json_tbl.get("data") or []
        if not data_rows or not data_rows[0]:
            return []

        first_row = data_rows[0][0]
        row_data = first_row.get("data") or []
        # 结构形如 [[obj, {head:[], data:[...]}]]
        cells = row_data[0] if row_data and isinstance(row_data[0], list) else row_data
        if len(cells) < 2:
            return []

        obj_code = cells[0]
        table = cells[1] or {}
        headers = table.get("head") or []
        rows = table.get("data") or []

        bars: List[Dict[str, Any]] = []
        for row in rows:
            bar = dict(zip(headers, row))
            # 带上对象代码，便于后续写库
            bar["Obj"] = obj_code
            bars.append(bar)
        return bars


def build_default_client() -> DzhRestClient:
    """Helper to init client from env vars."""
    app_id = os.getenv("DZH_APP_ID", "0b93313f68e2b2ff4a581e6bf8e8d1c2")
    secret = os.getenv("DZH_SECRET_KEY", "y3i96fyHK8ZL")
    return DzhRestClient(app_id=app_id, secret_key=secret)

