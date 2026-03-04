# AmapIsochrone - 高德地图等时圈（到达圈）可视化

AstrBot 插件：根据任意地点名称生成高德等时圈静态图，纯 API 调用，无浏览器渲染。

## 功能

- **指令**：`等时圈 [地点名称] [时间/可选] [方式/可选]`；**测试**：`高德API测试`
- **默认**：60 分钟、**地铁**（可在配置中修改默认交通方式）
- **流程**：地理编码 → 到达圈多边形 → 高德静态图 URL → 返回 Markdown 图片 + 文案

## AstrBot 相关配置与 JSON 文档

| 文件 | 说明 |
|------|------|
| `metadata.yaml` | 插件元数据（id、name、版本、支持平台、astrbot_version 等），AstrBot 据此识别插件 |
| `_conf_schema.json` | WebUI 配置项定义（amap_key、default_transport 等），管理面板据此渲染配置表单 |
| `config.example.json` | 配置项示例值，仅参考用 |
| `docs/astrbot-config.md` | 配置与 JSON 文档说明 |

## 配置（WebUI）

- **amap_key**：高德 Web 服务 API Key（必填），在高德开放平台申请「Web 服务」类型 Key。
- **default_transport**：默认交通方式，可选「地铁」「公交」「地铁公交」「步行」「驾车」，与高德地图可查询方式一致。

## 依赖

- `httpx`（见 `requirements.txt`）

## 说明

- 若高德到达圈接口（v3/direction/reachcircle）不可用或 Key 无权限，将自动退化为「近似圆形」等时圈并标注为仅供参考。
- 输出为字符串：`![等时圈](静态图URL)` + 两个换行 + 文案，便于 splitter 等插件将图片单独发送。
