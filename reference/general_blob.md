# 二进制数据 BLOB

BLOB 用于在工程中保存二进制数据，例如图片、文件等。

## 格式

```json
["DOCTYPE", "BLOB", "1.0"]
["BLOB", "blob-hash-id1", "aaa.png", "data:image/png;base64,xxsasdfawerwerqwer"]
```

## 字段说明

1. `BLOB`：二进制数据标识。
2. `blob-hash-id1`：二进制哈希码。
3. `aaa.png`：文件名，仅用于参考，可留空。
4. `data:image/png;base64,...`：二进制数据，使用类似 Data URLs 的规范。

## 哈希码计算方式

1. 最终二进制数据字符串使用 **UTF-8** 编码。
2. 使用 **SHA-256** 计算哈希值。
3. 将哈希值使用 **HEX** 编码成十六进制字符串，全小写。

## 二进制数据格式

### 一般格式

与 Data URLs 完全兼容：

```text
data:[<mediatype>][;base64],<data>
```

例如：

```text
data:image/png;base64,asdfasdfwer
data:text/html,<html></html>
```

### 扩展格式

扩展了功能性，加上了如 gzip/deflate 等编码转换功能：

```text
data:<mediatype>[pipeline],<data>
```

例如：

```text
data:text/html;gzip;base64,asdfasdf
data:text/css;deflate;aes128;base64,aaaaaaa
```

解析时按照 pipeline 从后往前依次解码。
