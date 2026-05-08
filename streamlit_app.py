from __future__ import annotations

import csv
import io
import json
import os
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
import streamlit as st


BASE_URL = "https://www.aigorism.com"
ENDPOINT = "/api/data_source/news/incremental"
MAX_DAYS = 31


st.set_page_config(
    page_title="物流新闻获取器",
    page_icon="",
    layout="centered",
)

st.markdown(
    """
    <style>
    :root {
      --ink: #18201c;
      --muted: #68746d;
      --line: #d8ded8;
      --paper: #fbfaf6;
      --field: #ffffff;
      --accent: #176b5b;
    }

    .stApp {
      background:
        linear-gradient(180deg, rgba(255,255,255,.72), rgba(255,255,255,.94)),
        repeating-linear-gradient(90deg, rgba(24,32,28,.035) 0 1px, transparent 1px 64px),
        var(--paper);
      color: var(--ink);
    }

    .block-container {
      max-width: 880px;
      padding-top: 3.4rem;
      padding-bottom: 3rem;
    }

    h1 {
      color: var(--ink);
      font-size: 2.2rem !important;
      letter-spacing: 0 !important;
      margin-bottom: .35rem !important;
    }

    div[data-testid="stMetric"] {
      background: rgba(255,255,255,.75);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: .9rem 1rem;
    }

    div[data-testid="stMetricValue"] {
      color: var(--accent);
    }

    .stButton > button,
    .stDownloadButton > button {
      border-radius: 6px;
      border: 1px solid #0f5548;
      background: #176b5b;
      color: white;
      min-height: 2.75rem;
      font-weight: 650;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
      border-color: #0b3d34;
      background: #0f5548;
      color: white;
    }

    div[data-testid="stDateInput"] input,
    div[data-testid="stTextInput"] input {
      background: var(--field);
      border-radius: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_secret(name: str) -> str:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value or os.getenv(name, "")).strip()


def parse_item_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fetch_one_day(api_key: str, day: date, max_retry: int = 3) -> list[dict[str, Any]]:
    url = f"{BASE_URL}{ENDPOINT}"
    headers = {"Authorization": f"API-Key {api_key}"}
    items: list[dict[str, Any]] = []
    page = 0

    with requests.Session() as session:
        while True:
            page += 1
            params = {
                "since": day.isoformat(),
                "test_mode": "true",
                "page": page,
            }

            last_error: Exception | None = None
            body: dict[str, Any] | None = None
            for attempt in range(max_retry):
                try:
                    response = session.get(url, headers=headers, params=params, timeout=120)
                    response.raise_for_status()
                    body = response.json()
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(2**attempt)
            else:
                raise RuntimeError(f"{day.isoformat()} 第 {page} 页失败：{last_error}")

            if body is None or body.get("code") != 200:
                message = body.get("message") if body else "empty response"
                raise RuntimeError(f"{day.isoformat()} 第 {page} 页返回异常：{message}")

            data = body.get("data") or {}
            page_items = data.get("items") or []
            items.extend(page_items)

            if not data.get("has_more", False) or not page_items:
                break
            if page > 500:
                raise RuntimeError(f"{day.isoformat()} 页数超过 500，已停止")

    return items


def keep_items_for_day(items: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    lower = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    upper = lower + timedelta(days=1)
    kept: list[dict[str, Any]] = []
    for item in items:
        created_at = parse_item_time(item.get("created_at"))
        if created_at is None or lower <= created_at < upper:
            kept.append(item)
    return kept


def build_daily_payload(day: date, items: list[dict[str, Any]], raw_count: int) -> dict[str, Any]:
    lower = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    upper = lower + timedelta(days=1)
    return {
        "date": day.isoformat(),
        "time_range": {
            "since": lower.isoformat(),
            "until_exclusive": upper.isoformat(),
        },
        "count": len(items),
        "raw_count": raw_count,
        "filtered_out": raw_count - len(items),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "; ".join(parts)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_csv(items: list[dict[str, Any]]) -> bytes:
    fields = [
        "date",
        "_id",
        "title",
        "abstract",
        "url",
        "created_at",
        "publish_time",
        "transport_modes",
        "freight_impact_category",
        "event_locations",
        "impact_locations",
        "keywords",
        "application_tags",
    ]
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writeheader()
    for item in items:
        created_at = parse_item_time(item.get("created_at"))
        row = {field: stringify(item.get(field)) for field in fields}
        row["date"] = created_at.date().isoformat() if created_at else ""
        writer.writerow(row)
    return text.getvalue().encode("utf-8-sig")


def build_zip(payloads: list[dict[str, Any]], combined_items: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for payload in payloads:
            archive.writestr(
                f"{payload['date']}.json",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        archive.writestr(
            "combined.json",
            json.dumps(
                {
                    "count": len(combined_items),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "items": combined_items,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        archive.writestr("combined.csv", build_csv(combined_items))
    return buffer.getvalue()


def each_day(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


st.title("物流新闻获取器")

api_key = read_secret("AIGORISM_API_KEY")
if not api_key:
    api_key = st.text_input("AIGORISM_API_KEY", type="password").strip()

today = date.today()
default_start = today - timedelta(days=5)
left, right = st.columns(2)
with left:
    start_date = st.date_input("开始日期", value=default_start)
with right:
    end_date = st.date_input("结束日期", value=today - timedelta(days=1))

submitted = st.button("获取新闻", use_container_width=True)

if submitted:
    if not api_key:
        st.error("缺少 AIGORISM_API_KEY")
        st.stop()
    if end_date < start_date:
        st.error("结束日期不能早于开始日期")
        st.stop()

    day_count = (end_date - start_date).days + 1
    if day_count > MAX_DAYS:
        st.error(f"一次最多获取 {MAX_DAYS} 天")
        st.stop()

    progress = st.progress(0)
    status = st.empty()
    payloads: list[dict[str, Any]] = []
    combined_items: list[dict[str, Any]] = []

    for index, day in enumerate(each_day(start_date, end_date), start=1):
        status.write(f"正在获取 {day.isoformat()} ...")
        raw_items = fetch_one_day(api_key, day)
        kept_items = keep_items_for_day(raw_items, day)
        payloads.append(build_daily_payload(day, kept_items, len(raw_items)))
        combined_items.extend(kept_items)
        progress.progress(index / day_count)

    status.write("完成")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("天数", day_count)
    col_b.metric("新闻条数", len(combined_items))
    col_c.metric("文件数", len(payloads) + 2)

    file_prefix = f"rachelnews_{start_date.isoformat()}_{end_date.isoformat()}"
    zip_bytes = build_zip(payloads, combined_items)
    csv_bytes = build_csv(combined_items)

    st.download_button(
        "下载 ZIP",
        data=zip_bytes,
        file_name=f"{file_prefix}.zip",
        mime="application/zip",
        use_container_width=True,
    )
    st.download_button(
        "下载 CSV",
        data=csv_bytes,
        file_name=f"{file_prefix}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with st.expander("每日条数"):
        for payload in payloads:
            st.write(f"{payload['date']}: {payload['count']} 条")
