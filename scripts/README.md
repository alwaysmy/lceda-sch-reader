# lceda_reader 文档生成脚本

基于 `../lceda_reader.py`（pinmap 连通域精确方案）生成 markdown 文档的脚本。
依赖：Python 3.8+，仅标准库；lceda_reader.py 在本目录上一级。

## 脚本与产出

| 脚本 | 产出 | 说明 |
| --- | --- | --- |
| `gen_v11_md.py` | V1.1 主控板引脚关系 md | V1.1 主控板各器件引脚→网络→MCU 引脚表（每器件一个二级标题） |
| `gen_adda_md3.py` | V1.1 主控↔ADDA 对应关系 md | 双工程：V1.1 主控 ↔ ADDA 板连接器 40pin 核对 + ADDA 各器件引脚映射 |
| `gen_audit.py` | ADDA 板设计审计 md | 双工程：板间接线核对、悬空引脚、ADT7310 SPI 接线核对 |

## 用法（工程路径必须显式指定）

```bat
set PYTHONIOENCODING=utf-8

rem 单工程脚本：--eprj 指定工程，--out 指定输出
python gen_v11_md.py --eprj <主控工程.eprj2> --out <输出.md>

rem 双工程脚本：--eprj = 第一工程，--eprj2 = 第二工程
python gen_adda_md3.py --eprj <ADDA工程.eprj2> --eprj2 <主控工程.eprj2> --out <输出.md>
python gen_audit.py --eprj <ADDA工程.eprj2> --eprj2 <主控工程.eprj2> --out <输出.md>

rem 可选：--tool 指定 lceda_reader.py 路径（默认脚本上一级自动定位）
```

`--eprj`/`--eprj2`/`--out` 均**必须**提供（无内置默认路径，工具不绑定工程目录结构）。

## 与临时脚本的关系

这些脚本由早期临时探查脚本整理而来，已参数化
（`--eprj`/`--eprj2`/`--out`/`--tool`），不再依赖临时目录。

## 注意

- 输出基于 pinmap **连通域精确方案**，推断网络带 `*` 标记（net_inferred）。
- 重新生成文档前建议核对 lceda_reader.py 的 README 缺陷清单，确认无已知问题影响。
