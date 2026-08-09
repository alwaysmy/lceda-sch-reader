# lceda_reader 文档生成脚本

基于 `../lceda_reader.py`（pinmap 连通域精确方案）生成 markdown 文档的脚本。
依赖：Python 3.8+，仅标准库；lceda_reader.py 在本目录上一级。

## 脚本与产出

| 脚本 | 产出 | 说明 |
| --- | --- | --- |
| `gen_v11_md.py` | `5_docs/V1.1版主控原理图引脚关系.md` | V1.1 主控板各器件引脚→网络→MCU 引脚表（每器件一个二级标题） |
| `gen_adda_md3.py` | `5_docs/V1.1主控与ADDA板对应关系.md` | V1.1 主控 ↔ ADDA 板连接器 40pin 核对 + ADDA 各器件（U26/U27/U3/U4/U18/U2/U28）引脚映射 |
| `gen_audit.py` | `5_docs/ADDA板设计审计.md` | ADDA 板设计审计（板间接线核对、悬空引脚、ADT7310 SPI 接线核对） |

## 用法

```bat
set PYTHONIOENCODING=utf-8
rem 默认输出到 5_docs/（脚本内置默认路径）
python gen_v11_md.py
python gen_adda_md3.py
python gen_audit.py

rem 自定义工程/输出路径
python gen_v11_md.py --eprj <工程.eprj2> --out <输出.md>
```

## 与临时脚本的关系

这些脚本从 `%TEMP%\opencode\lceda_probe\gen_*.py` 迁移而来，已参数化
（`--eprj`/`--out`/`--tool`），不再依赖临时目录。

## 注意

- 输出基于 pinmap **连通域精确方案**，推断网络带 `*` 标记（net_inferred）。
- 重新生成文档前建议核对 lceda_reader.py 的 README 缺陷清单，确认无已知问题影响。
