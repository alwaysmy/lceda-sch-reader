# project.json 信息文件

`project.json` 是项目的核心信息文件，描述了整个项目的结构性信息，包括器件、符号、封装、原理图、PCB、板子配置等。

## 结构示例

```json
{
  "devices": {
    "device-uuid-1": {
      "title": "DV2005",
      "description": "...",
      "tags": [],
      "images": [],
      "attributes": {
        "symbol_uuid": "symbol-uuid-1",
        "footprint_uuid": "footprint-uuid-2",
        "manufacture": "LCSC",
        "value": "10uF"
      }
    }
  },
  "symbols": {
    "symbol-uuid-1": {
      "title": "symbol1",
      "source": "",
      "version": "",
      "type": 17,
      "desc": "TI Memory",
      "tags": ["Memory"]
    }
  },
  "footprints": {
    "footprint-uuid-1": {
      "title": "0805",
      "source": "",
      "version": "",
      "type": 17,
      "desc": "TI Memory",
      "tags": ["Memory"]
    }
  },
  "schematics": {
    "schematic-uuid-1": {
      "name": "Schematic1",
      "sheets": [
        {"id": 1, "name": "1"},
        {"id": 3, "name": "A"},
        {"id": 8, "name": "3"}
      ]
    }
  },
  "pcbs": {
    "pcb-uuid-1": "PCB Title 1",
    "pcb-uuid-2": "AAbbCCd"
  },
  "boards": {
    "Board1": {
      "schematic": "schematic-uuid-1",
      "pcb": "pcb-uuid-1"
    },
    "Board2": {
      "schematic": "schematic-uuid-2"
    }
  },
  "config": {
    "title": "Project3",
    "defaultSheet": "device-uuid-3",
    "cbbProject": false
  }
}
```

## 字段说明

### devices

- 键为器件 UUID。
- `title`：器件标题。
- `description`：器件说明。
- `tags`：分类标记。
- `images`：图片列表。
- `attributes`：器件属性，可包含 `symbol_uuid`、`footprint_uuid`、`manufacture`、`value` 等。

### symbols

- 键为符号 UUID，与 `SYMBOL` 目录下的文件名对应。
- `title`：Symbol 名称。
- `source`：Symbol 来源。如果是工程库则固定留空。
- `version`：Symbol 来源版本号。如果是工程库则固定留空。
- `type`：Symbol 类型编号。
- `desc`：Symbol 说明，可留空。如果不是工程库则固定留空。
- `tags`：Symbol 分类标记，可留空。如果不是工程库则固定留空。

### footprints

- 键为封装 UUID，与 `FOOTPRINT` 目录下的文件名对应。
- 字段含义与 `symbols` 类似，分别对应 Footprint 名称、来源、版本号、类型编号、说明和分类标记。

### schematics

- 键为原理图 UUID，与 `SHEET` 目录下的文件夹名称一致。
- `name`：原理图名称。
- `sheets`：原理图下所有 Sheet 的信息，顺序应与左侧树显示的顺序一致。
  - `id`：Sheet 编号，与 `SHEET` 目录下对应原理图下对应的文件名一致。
  - `name`：Sheet 显示名称。

### pcbs

- 键为 PCB UUID，值为 PCB 标题。

### boards

- 描述板级映射关系。
- `schematic`：对应的原理图 UUID。
- `pcb`：对应的 PCB UUID（可选）。

### config

- `title`：工程名称。
- `defaultSheet`：默认图框配置（对应 device UUID）。
- `cbbProject`：是否 CBB 工程。如果是 CBB 工程，导入时需要检查 CBB 工程的基本要求。
