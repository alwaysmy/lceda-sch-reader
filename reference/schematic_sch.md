# SCH 原理图类型文档

`SCH` 文档描述原理图页面的内容。

## 文件头

```json
["DOCTYPE", "SCH", "1.0"]
["HEAD", {"ORIGIN_X": 0, "ORIGIN_Y": 0, "editorVersion": "4.7.8", "importFlag": 0}]
```

## HEAD 字段说明

1. `HEAD`：文档头标识。
2. 内部参数 Key-Value：
   - `ORIGIN_X`、`ORIGIN_Y`：预留为画布原点偏移，可选。
   - 其它为编辑器附加信息，用于数据分析等功能，可选。

## 原理图主体示例

```json
["FONTSTYLE", "st001", "#880000", "Consolas", 7, 1, 0, 0, 0, 0, 0]
["FONTSTYLE", "st002", "#880000", "Consolas", 7, 1, 0, 0, 0, 0, 2]
["FONTSTYLE", "st003", "#880000", "Consolas", 7, 1, 0, 0, 0, 0, 2]
["LINESTYLE", "st004", "#880000", 0, "#664400", 1]
["LINESTYLE", "st005", "#880000", 1, "", 1]
["LINESTYLE", "st006", "#880000", 0, "#664400", 5]
["WIRE", "e112", [455, 265, 455, 485, 720, 485], "st005", 0]
["ATTR", "e111", "e112", "NET", "+5V", 1, 1, 108, 804.5, 0, "st002", 1]
["BUS", "e106", [455, 265, 455, 485, 720, 485], "st005", 0]
["ATTR", "e111", "e106", "NET", "+5V", 1, 1, 108, 804.5, 0, "st002", 1]
```

原理图主体由多个基础图元组成，例如 `FONTSTYLE`、`LINESTYLE`、`WIRE`、`BUS`、`COMPONENT` 等。
