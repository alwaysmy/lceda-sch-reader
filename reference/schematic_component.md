# COMPONENT 图元

`COMPONENT` 引用了 Symbol，Symbol 支持多 PART，所以带了 子库编号 属性指示具体哪一个，如果是单 PART 则使用默认值 `""`。

## 格式

```json
["COMPONENT", "e176", "1", 300, 200, 15, 0, {}, 0]
```

## 字段说明

1. `COMPONENT`：COMPONENT 标识。
2. 编号：文件内唯一。
3. 子库编号：默认 `""`。
4. 位置 X。
5. 位置 Y。
6. 旋转角度：绕位置旋转。
7. 是否镜像。
8. 纯数据属性：附加信息，用于编辑器内部的一些逻辑。
9. 是否锁定。

## 变换顺序

Component 所引用的 Symbol 图元一定是按照如下顺序执行的变换：

1. 按照旋转角度绕原点 `(0,0)` 逆时针旋转。
2. 如果是否镜像为 `1`，则绕原点 `(0,0)` 所在的 Y 轴进行水平镜像。
3. 根据位置进行平移。

## 属性覆盖

Component 内可以绑定多个 `ATTR`，其属性行为将由工具定义。

### Device 属性

```json
["ATTR", "e187", "e176", "Device", "device-uuid-1", 1, 1, 300, 200, 0, "st002", 1]
```

Device uuid 与 `project.json` 里 `devices` 对应的文件名称一致。

### Symbol 属性

```json
["ATTR", "e188", "e176", "Symbol", "symbol-uuid-1", 1, 1, 300, 200, 0, "st002", 1]
```

COMPONENT 内的 ATTR 会对模板内同名属性覆盖，覆盖 Symbol 后会影响此器件对符号的绑定。

### Footprint 属性

```json
["ATTR", "e188", "e176", "Footprint", "footprint-uuid-1", 1, 1, 300, 200, 0, "st002", 1]
```

COMPONENT 内的 ATTR 会对模板内同名属性覆盖，覆盖 Footprint 后会影响此器件对封装的绑定。

### Designator 属性

```json
["ATTR", "e178", "e176", "Designator", "U1", 1, 1, 300, 200, 0, "st002", 1]
```

### PIN 属性覆盖

```json
["ATTR", "e180", "e176e5", "NUMBER", "1", 1, 1, 108, 804.5, 0, "st002", 1]
```

PIN 属性覆盖的方式关键在 `ATTR` 的隶属编号上。编号分两部分，例如 `e176e5`，其中 `e176` 为 `COMPONENT` 的编号，`e5` 为在模板内的 `PIN` 编号。
