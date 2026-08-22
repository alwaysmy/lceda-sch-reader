# 新版加密 .eprj2 格式逆向与破解 — 完整记录

> 2026-08-22 完成。本文档详细记录逆向过程、算法细节、实现方案，
> 供后续维护和类似问题参考。

## 一、背景

立创EDA专业版从某版本起，`.eprj2` 工程文件改用**分支版本化加密格式**：
- `documents`/`schematics`/`components` 等主表全部为空
- 全部工程内容存储在 `history_data` 表的加密 blob 中
- 工程结构树在 `project_structures.structure`（明文 JSON）
- 分支信息在 `branches` 表 + `project_history_<branch_uuid>` 表

## 二、识别方法

```sql
-- 判断是否新版格式
SELECT COUNT(*) FROM documents;  -- 结果为 0 即新版
SELECT name FROM sqlite_master WHERE type='table'
  AND name LIKE 'project_history_%';
-- 有结果说明存在分支历史表（含解密密钥）
```

`detect_backend` 中已集成此判断：documents 空 + project_structures 存在
→ 自动解密 → 打包临时 .epro2 → Epro2DB 读取。

## 三、逆向过程

### 3.1 排除法确认"加密"

1. 尝试标准解压：gzip/zlib/raw-deflate/lzma/bz2/zstd/lz4 → 全部失败
2. 香农熵分析：8.00 bits/byte → 加密或高效压缩
3. 字节频率分布：均匀 → 排除简单 XOR/替换
4. 搜索文件头魔数：无 gzip(1f8b)/zlib(78xx)/zstd(28b52ffd) 等

### 3.2 定位加密代码

| 步骤 | 方法 | 结果 |
| --- | --- | --- |
| 主进程 app.js | 搜 createDecipheriv/AES | 仅 crypto-browserify 库内部 |
| 渲染层 ui.js/sch-main.js | 同上 | 同上 |
| pro-mgr workers | 搜 history_data 关键词 | 找到 ORM 实体定义 |
| **app.js @2590023** | 提取类定义 | **找到 AES-128-GCM 加密类** |

### 3.3 加密类完整源码（从 app.js 提取）

```javascript
// 类名: j4 (minified)，实际是 AES-128-GCM 加密器
class j4 {
    static AUTH_TAG_LENGTH = 16;
    algorithm = "aes-128-gcm";
    key;  // 16 bytes
    
    constructor(e) {
        this.key = Buffer.isBuffer(e) ? e : Buffer.from(e, "hex");
        if (this.key.length !== 16)
            throw new Error("Key must be 16 bytes for aes-128-gcm");
    }
    
    encrypt(e, r) {
        // e = IV hex string, r = 明文文本
        let i = Buffer.from(e, "hex"),           // IV → bytes
            s = createCipheriv("aes-128-gcm", this.key, i),
            a = gzipSync(Buffer.from(r, "utf8"), {level: 1}),
            n = concat([s.update(a), s.final()]),
            o = s.getAuthTag();
        return concat([n, o]);                   // 密文 + authTag
    }
    
    decrypt(e, r) {
        let i = Buffer.from(e, "hex"),
            s = r.subarray(r.length - 16),       // 最后 16B = authTag
            a = r.subarray(0, r.length - 16),    // 其余 = ciphertext
            n = createDecipheriv(algorithm, this.key, i);
        n.setAuthTag(s);
        let o = concat([n.update(a), n.final()]);
        return gunzipSync(o).toString("utf8");
    }
}
```

### 3.4 写入函数 U4（关键流程）

```javascript
async function U4(t, e, r, i = true) {
    let s;
    if (!i && r.key)
        s = Buffer.from(r.key, "hex");       // 用已有 key（增量保存）
    else if (r.cnt && r.key)
        s = Buffer.from(r.key, "hex");       // 增量保存复用 key
    else
        s = crypto.randomBytes(16);          // 首次保存生成随机 key
    
    let a = await new j4(s).encrypt(r.uuid, r.dataStr);
    await jB(t, e, a, ...);                  // base64 后写入 history_data
    return s.toString("hex");                // 返回 hex key 给调用者
}
```

### 3.5 密钥存储位置

调用链 `yB → U4 → 返回 hex key → INSERT INTO project_histories`。

**但实际表不是 `project_histories`**——而是分支特定表
`project_history_<branch_uuid>`。通过搜索 SQLite 所有表名中含
`project_history_` 的来定位。

## 四、破解算法（Python 实现）

```python
import sqlite3, base64, gzip
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def decrypt_eprj2(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    
    # Step 1: 找分支历史表获取密钥
    branch_tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name LIKE 'project_history_%'")]
    key_map = {}
    for tbl in branch_tables:
        for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
            if row[1]:
                key_map[row[0]] = row[1]
    
    # Step 2: 解密全部 blob
    all_text = []
    for buuid_full, bdata in conn.execute(
            "SELECT uuid, dataStr FROM history_data ORDER BY id"):
        buuid = buuid_full.split("-")[0]     # 去掉分片后缀
        key_hex = key_map.get(buuid)
        
        blob = base64.b64decode(bdata)
        iv = bytes.fromhex(buuid[:32])       # uuid 前 32 hex → 16B IV
        key = bytes.fromhex(key_hex)         # hex → 16B key
        
        aesgcm = AESGCM(key)
        compressed = aesgcm.decrypt(iv, blob, None)
        plaintext = gzip.decompress(compressed).decode("utf-8")
        all_text.append(plaintext)
    
    return all_text  # 每个 element 是一个 epru 日志段
```

### 关键参数映射

| 参数 | 来源 | 说明 |
| --- | --- | --- |
| **key** (16B) | `project_history_<branch>.key` 列 | hex 字符串 → bytes |
| **IV** (16B) | `history_data.uuid` 列前 32 个 hex 字符 | hex → bytes |
| **authTag** | blob 最后 16 字节 | GCM 认证标签 |
| **ciphertext** | blob 其余部分 | AES-GCM 密文 |
| **压缩** | gzip level=1 | 解密后需 gunzip |

### 注意事项

1. **uuid 分片后缀**：同一逻辑 blob 可能拆成多行存储，uuid 带 `-1`/`-2`
   后缀。解密时用去掉后缀的基础 uuid 做 IV。
2. **多个 blob 合并**：全部 blob 的明文拼接即为完整工程日志。
   实测 Piezo_Driver 有 4 个 blob 合并后 63M chars。
3. **增量追加**：用户修改后再保存会追加新的小 blob（几百字节到几 KB），
   而非重写大 blob。工具需合并全部 blob 的解密结果。
4. **依赖库**：Python 需要 `cryptography` 包（AESGCM）。

## 五、验证结果

Piezo_Driver.eprj2（10.9MB）：

| 指标 | 值 |
| --- | ---|
| 解密后明文 | 63.0M chars |
| DOCHEAD 数 | 2154 |
| 文档类型 | FOOTPRINT×440, DEVICE×532, SYMBOL×828, SCH_PAGE×236... |
| 打包 .epro2 后 Epro2DB 读取 | 73 页 / 16 板 / 3575 元件 ✓ |
| netlist | 267 网 ✓ |
| CBB 展开 | 15 实例 ✓ |

## 六、CBB 位号映射（INSTANCE 文档）

### 数据来源

解密后的 epru 中包含 INSTANCE 类型的 DOCHEAD 段，内含 INSTANCE_ATTR
记录。这些记录了 CBB 放置到母图时 LCEDA 自动分配的母图位号。

### 格式

INSTANCE uuid 编码 = `<sch_uuid>_$<母图页uuid>~<实例cid>_$<模板页uuid>`

INSTANCE_ATTR 记录 = `{Designator: "母图位号"}`

### 工具行为

- `.epro2` 导出：INSTANCE 段完整保留 → CBB 展开条目使用母图位号 ✓
- 新版 .eprj2 解密：INSTANCE 段在 history_data 中 → 同样可用 ✓
- 展开条目格式：`CBBn.成员位号`，net 为"内部网络∪父网络"并集

### 注意

LCEDA 的 INSTANCE_ATTR 只记录**被改过位号的成员**的母图位号。
未被改过的成员沿用模板原始位号。因此展开条目可能同时包含
模板位号和母图位号（这是正确行为——增量日志保留了变更轨迹）。

## 七、经验总结（避免下次踩坑）

1. **不要过早下"加密"结论**：先穷举所有标准压缩格式（包括 zstd/lz4/
   brotli），再用熵分析和字节频率排除。本项目最终确实是 AES-GCM 加密。
2. **从写入路径反推**：找 INSERT INTO 目标表的代码，回溯数据来源。
   本项目通过 U4 函数的 `new j4(s).encrypt(...)` 定位了加密类。
3. **密钥可能存在非显而易见的位置**：不在 `project_histories` 通用表，
   而在分支特定的 `project_history_<branch_uuid>` 表。搜表名模式而非固定表名。
4. **IV 可能就是行标识符**：`history_data.uuid` 兼作 IV，一列两用。
5. **minified 代码的括号配平提取**：需要处理嵌套字符串中的 `{}`，
   简单计数会提前终止。建议打印大段上下文人工分析。
6. **CDP 动态分析的限制**：worker 线程不可 evaluate；渲染层 hook 无法
   捕获主进程/worker 内的调用。静态分析 + 运行时验证结合最有效。
7. **官方文档是第一手资料**：easyeda/easyeda-pro-file-format-v2 等官方
   GitHub 仓库提供了 BLOB pipeline 编码（gzip/aes128/base64）的关键线索，
   应优先查阅而非盲目逆向。
8. **增量日志的合并语义容易出错**：ticket 每段独立计数不能全局比较；
   同 (type,id) 以 (段序,ticket) 双键取最新；未合并则历史轨迹叠加导致
   连通域爆炸。改动合并逻辑务必双场景回归。
