# AmapIsochrone 的 AstrBot 配置说明

## 配置文件一览

| 文件 | 用途 |
|------|------|
| `metadata.yaml` | 插件元数据，AstrBot 据此识别与加载插件（必填） |
| `_conf_schema.json` | Web 管理面板中的配置项定义（类型、描述、默认值、选项） |
| `config.example.json` | 配置项示例值，仅作参考，不参与加载 |

## metadata.yaml

插件根目录下的 **metadata.yaml** 为 AstrBot 必读文件，用于：

- 插件 ID、名称、展示名、作者、版本、描述
- 支持平台（如 aiocqhttp、kook、telegram）
- AstrBot 版本要求（如 `>=4.16,<5`）
- 仓库地址（发布到插件市场时填写）

修改后需在 WebUI 中「重载插件」生效。

## _conf_schema.json

定义在 WebUI「插件配置」中显示的字段，用户在此填写后由 AstrBot 注入到插件的 `config` 中。

### 当前字段

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `amap_key` | string | `""` | 高德 Web 服务 API Key，必填 |
| `default_transport` | string | `"地铁"` | 默认交通方式，可选：地铁、公交、地铁公交、步行、驾车 |

### 字段说明（与高德一致）

- **amap_key**：在 [高德开放平台](https://console.amap.com/dev/key/app) 创建应用，添加「Web 服务」类型 Key，用于地理编码、到达圈、静态图接口。
- **default_transport**：用户发送「等时圈 北京西站」且未写交通方式时使用；取值与高德地图可查询方式一致。

## config.example.json

仅作示例，展示配置项键与推荐取值格式，**不会被 AstrBot 自动加载**。实际配置以 WebUI 中保存的为准（对应 `_conf_schema.json` 中定义的项）。

## 依赖

- **requirements.txt**：声明第三方依赖（如 `httpx`），安装/更新插件时由 AstrBot 自动安装。
