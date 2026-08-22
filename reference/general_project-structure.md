# 项目打包结构

## 概述

项目打包结构选用 **zip 压缩格式**，主要因为可采用以下几点优势：

1. 良好的通用性。
2. 借助其所支持的目录结构，实现信息的分类。
3. 借助其信息压缩算法，实现项目信息的高效存储和交换。

由于 zip 压缩格式有一定的限制（例如文件名非法字符的限制等），有时不方便直接以文件原始的名称命名。此时需要采用 **无实际含义的编号** 为其命名，只要和 `project.json` 的信息能对应上即可。

## .zip 文件组织方式

整个项目将使用如下目录结构打包：

```text
ROOT
├── project.json              // 项目信息文件，具有整个项目的结构性信息
├── SYMBOL/                   // 符号模板及 Block Symbol 数据格式文件夹
│   ├── symbol-uuid-1         // SYMBOL 原理图库类型文档数据，文件名用于和 project.json 内 symbols 一节对应
│   ├── symbol-uuid-2
│   └── symbol-uuid-3
├── FOOTPRINT/                // 封装模板数据格式文件夹
│   ├── footprint-uuid-1      // FOOTPRINT PCB库类型文档数据，文件名用于和 project.json 内 footprints 一节对应
│   ├── footprint-uuid-2
│   └── footprint-uuid-3
├── INSTANCE/                 // 实例属性类型文档
│   ├── instance-part-1
│   └── instance-part-2
├── BLOB/                     // 二进制数据文件夹
│   ├── blob-hash1            // BLOB 类型文档内容
│   └── blob-hash2
├── SHEET/                    // 原理图信息文件夹
│   ├── schematic-uuid-1      // 用于和 project.json 内 schematics 一节对应的原理图编号
│   │   ├── 1                 // SCH 原理图类型文档数据，文件名为 Sheet 编号
│   │   ├── 3
│   │   └── 8
│   └── schematic-uuid-2
│       ├── 1
│       └── 2
├── PCB/                      // PCB 类型文档数据
│   ├── pcb-uuid-1
│   └── pcb-uuid-2
└── POUR/                     // PCB 覆铜结果类型文档数据
    ├── pcb-uuid-1_eid1
    └── pcb-uuid-2_eid2
```

### 说明

- `INSTANCE` 内是依照 **INSTANCE 实例属性类型文档** 撰写的实例属性信息。推荐按照层次图底层图的 Sheet 进行分组，但其它分组方式亦可。文件名是自由的，不假设其具有任何关键逻辑含义。
- `SHEET` 目录下的文件名（如 `1`、`3`、`8`）为 Sheet 编号，例如 DX 里 `$8I5` 中的 `8`。
