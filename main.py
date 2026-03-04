# AmapIsochrone - 高德地图等时圈（到达圈）可视化插件
# 纯 API 调用，无浏览器渲染

import re
from typing import List, Optional, Tuple
from urllib.parse import quote

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# 默认：60 分钟，公交
DEFAULT_TIME = 60
DEFAULT_MODE = "bus"

# 方式 -> 高德到达圈 policy（若 REST 支持）
MODE_TO_POLICY = {
    "公交": "BUS",
    "地铁": "SUBWAY",
    "地铁公交": "SUBWAY,BUS",
    "bus": "BUS",
    "subway": "SUBWAY",
    "walk": "WALK",
    "drive": "DRIVE",
}

# 静态图 paths 样式：线宽,线色,线透明度,填充色,填充透明度
# 半透明蓝 0x0000FF，填充透明度约 0.33
PATHS_STYLE = "3,0x0000FF,1,0x0000FF,0.33"


async def _geocode(address: str, key: str) -> Optional[str]:
    """高德地理编码：地址 -> 经纬度 'lng,lat'。失败返回 None。"""
    if not key or not address or not address.strip():
        return None
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {"key": key, "address": address.strip(), "output": "json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"[AmapIsochrone] Geocode request error: {e}")
            return None
    if data.get("status") != "1" or not data.get("geocodes"):
        logger.warning(f"[AmapIsochrone] Geocode no result: {data.get('info', '')}")
        return None
    loc = data["geocodes"][0].get("location")
    if not loc:
        return None
    return str(loc).strip()


async def _reachcircle(origin: str, time_min: int, policy: str, key: str) -> Optional[List[str]]:
    """
    高德到达圈 API：返回外圈多边形坐标列表。
    每个元素为 "lng,lat"，可拼接成 paths 用的 "lng1,lat1;lng2,lat2;..."。
    若接口不可用则返回 None，调用方可用近似圆兜底。
    """
    if not key or not origin:
        return None
    url = "https://restapi.amap.com/v3/direction/reachcircle"
    params = {
        "key": key,
        "origin": origin,
        "time": time_min,
        "policy": policy,
        "output": "json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning(f"[AmapIsochrone] Reachcircle request error: {e}")
            return None
    if data.get("status") != "1":
        logger.warning(f"[AmapIsochrone] Reachcircle fail: {data.get('info', '')}")
        return None
    # 尝试多种可能的返回结构
    outer = data.get("reach") or data.get("outer") or data.get("bounds")
    if isinstance(outer, str):
        # "lng1,lat1;lng2,lat2;..."
        points = [p.strip() for p in outer.split(";") if p.strip()]
        if points:
            return points
    if isinstance(outer, list):
        if not outer:
            return None
        first = outer[0]
        if isinstance(first, (list, tuple)):
            return [f"{p[0]},{p[1]}" for p in first if len(p) >= 2]
        if isinstance(first, str):
            return [s.strip() for s in first.split(";") if s.strip()]
        if isinstance(first, dict) and "lng" in first and "lat" in first:
            return [f"{first['lng']},{first['lat']}"]
    # 部分文档提到 result.bounds 为多边形数组
    result = data.get("result") or data.get("data") or {}
    bounds = result.get("bounds") if isinstance(result, dict) else None
    if isinstance(bounds, list) and bounds:
        polygon = bounds[0]
        if isinstance(polygon, list):
            return [f"{p[0]},{p[1]}" for p in polygon if len(p) >= 2]
        if isinstance(polygon, str):
            return [p.strip() for p in polygon.split(";") if p.strip()]
    return None


def _approx_circle_polygon(lng: float, lat: float, time_min: int, mode: str) -> List[str]:
    """近似等时圈：按时间与方式给一个粗略半径（公里），生成正多边形。"""
    # 粗略：公交/地铁约 12 km/60min，步行约 4 km/60min，驾车约 30 km/60min
    km_per_hour = 12.0
    if "walk" in mode.lower() or "步行" in mode:
        km_per_hour = 4.0
    elif "drive" in mode.lower() or "驾车" in mode:
        km_per_hour = 30.0
    radius_km = (time_min / 60.0) * km_per_hour
    # 1 度纬度约 111km，经度随纬度变化
    import math
    lat_rad = math.radians(lat)
    dy = radius_km / 111.0
    dx = radius_km / (111.0 * max(0.01, math.cos(lat_rad)))
    n = 24
    points = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        points.append(f"{lng + dx * math.cos(t):.6f},{lat + dy * math.sin(t):.6f}")
    return points


def _build_static_map_url(
    center: str,
    paths_points: List[str],
    key: str,
    zoom: Optional[int] = None,
) -> str:
    """构造高德静态地图 URL，多边形半透明蓝。"""
    if not paths_points or not key:
        return ""
    path_str = ";".join(paths_points)
    # paths 格式: style:point1;point2;...
    paths_value = f"{PATHS_STYLE}:{path_str}"
    params = {
        "key": key,
        "paths": paths_value,
        "size": "600*400",
    }
    if center:
        params["location"] = center
    if zoom is not None and 1 <= zoom <= 17:
        params["zoom"] = str(zoom)
    q = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"https://restapi.amap.com/v3/staticmap?{q}"


def _suggest_zoom(points: List[str]) -> int:
    """根据多边形点集粗略建议 zoom。点集跨度越大 zoom 越小。"""
    if len(points) < 2:
        return 12
    lngs, lats = [], []
    for p in points:
        parts = p.split(",")
        if len(parts) >= 2:
            try:
                lngs.append(float(parts[0]))
                lats.append(float(parts[1]))
            except ValueError:
                pass
    if not lngs or not lats:
        return 12
    span_lng = max(lngs) - min(lngs)
    span_lat = max(lats) - min(lats)
    span = max(span_lng, span_lat)
    if span >= 1.0:
        return 9
    if span >= 0.5:
        return 10
    if span >= 0.2:
        return 11
    if span >= 0.1:
        return 12
    if span >= 0.05:
        return 13
    if span >= 0.02:
        return 14
    return 15


def _short_analysis(place: str, time_min: int, mode: str, is_approx: bool) -> str:
    """生成一两句简短可达性分析（纯规则，无 AI）。"""
    mode_cn = "公交/地铁" if mode in ("BUS", "SUBWAY", "SUBWAY,BUS") else mode
    if is_approx:
        return f"该范围按「{time_min} 分钟 {mode_cn}」的近似速度估算，仅供参考。"
    return f"在 {time_min} 分钟内通过 {mode_cn} 可从「{place}」到达图中蓝色区域内的任意地点。"


def _parse_args(text: str) -> Tuple[str, int, str]:
    """解析 '等时圈 [地点] [时间/可选] [方式/可选]'。"""
    text = (text or "").strip()
    # 去掉首条指令名（可能已由 filter 去掉）
    for prefix in ("等时圈", "等时圈 "):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    parts = re.split(r"\s+", text, maxsplit=2)
    place = (parts[0] or "").strip()
    time_min = DEFAULT_TIME
    mode = "BUS"  # 默认公交
    if len(parts) >= 2 and parts[1]:
        try:
            time_min = int(parts[1])
            time_min = max(1, min(60, time_min))
        except ValueError:
            # 第二段当作文本并入地点
            place = f"{place} {parts[1]}".strip()
    if len(parts) >= 3 and parts[2]:
        raw_mode = parts[2].strip()
        mode = MODE_TO_POLICY.get(raw_mode) or MODE_TO_POLICY.get(raw_mode.lower()) or "BUS"
    return place, time_min, mode


@register(
    "amap_isochrone",
    "AstrBot",
    "高德地图等时圈（到达圈）可视化：输入地点与可选时间/方式，返回静态图与简短说明。",
    "1.0.0",
)
class AmapIsochrone(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self._amap_key: str = str(self.config.get("amap_key", "")).strip()
        logger.info("[AmapIsochrone] Plugin loaded. amap_key configured: %s", bool(self._amap_key))

    @filter.command("等时圈")
    async def cmd_isochrone(self, event: AstrMessageEvent):
        if not self._amap_key:
            yield event.plain_result("请先在插件配置中填写高德 Web 服务 Key（amap_key）哦~")
            return
        raw = getattr(event, "message_str", None) or getattr(event, "get_message_str", lambda: "")()
        if callable(raw):
            raw = raw()
        raw = (raw or "").strip()
        place, time_min, mode = _parse_args(raw)
        if not place:
            yield event.plain_result("用法：等时圈 [地点名称] [时间/可选，1-60分钟] [方式/可选：公交、地铁、地铁公交]")
            return
        # 1) 地理编码
        location = await _geocode(place, self._amap_key)
        if not location:
            yield event.plain_result(f"没有找到「{place}」对应的位置哦，试试写更具体的地址或地标名~")
            return
        # 2) 到达圈
        polygon_points = await _reachcircle(location, time_min, mode, self._amap_key)
        is_approx = False
        if not polygon_points:
            try:
                lng, lat = map(float, location.split(",")[:2])
                polygon_points = _approx_circle_polygon(lng, lat, time_min, mode)
                is_approx = True
            except Exception as e:
                logger.exception("[AmapIsochrone] Fallback circle error: %s", e)
                yield event.plain_result("暂时无法生成该地点的到达圈，请稍后再试或检查 Key 权限。")
                return
        zoom = _suggest_zoom(polygon_points)
        static_url = _build_static_map_url(location, polygon_points, self._amap_key, zoom=zoom)
        if not static_url:
            yield event.plain_result("生成静态地图链接失败，请检查配置。")
            return
        analysis = _short_analysis(place, time_min, mode, is_approx)
        # 图片 + 两个换行 + 文字，便于 splitter 单独发图
        msg = f"![等时圈]({static_url})\n\n\n呐~ 哥哥，这是以 {place} 为中心，{time_min} 分钟的出行等时圈。\n{analysis}"
        yield event.plain_result(msg)
