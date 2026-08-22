# INSTANCE 实例属性类型文档

实例属性覆盖为块级图元，与 `PART` 类似。

## 文件头

```json
["DOCTYPE", "INSTANCE", "1.0"]
```

## OVERRIDE 实例属性覆盖

### 格式

```json
['OVERRIDE', ['Schematic ID', '$5e100', '$1e55', '$6e15', '$8'], { 'e176': { 'Designator': 'U15', 'ASDF': '1234' }, '': { 'Author': 'abc' }, 'e176e5': { 'NUMBER': 2 } }]
```

### 字段说明

1. `OVERRIDE`：实例属性覆盖标识。
2. 实例路径：
   - `Schematic ID` 为顶层原理图，与导出格式里 `project.json` 里的 `schemtaics` 下的名字要对应上。
   - 最后一个只到 Sheet 编号。
   - 中间所有的都是使用编号组合语法定位的 Block Symbol，如 `$1e2`，其中 `1` 为 sheetid，`e2` 为 Block Symbol 编号。
3. 属性覆盖，数据签名为 `{ [parentId: string]: { [key: string]: string } }`。

### 非层次图实例

```json
['OVERRIDE', ['Schematic ID', '$5'], { 'e176': { 'Designator': 'U15', 'ASDF': '1234' }, '': { 'Author': 'abc' }, 'e176e5': { 'NUMBER': 2 } }]
```

这种写法就是针对非层次图实例的属性覆盖。
