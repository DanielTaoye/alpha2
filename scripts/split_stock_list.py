import pandas as pd
from pathlib import Path


def main():
    src = Path("stock_list.csv")
    if not src.exists():
        raise SystemExit("stock_list.csv 不存在")

    # 尝试多种编码读取（文件原始编码可能为 GBK）
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            df = pd.read_csv(src, encoding=enc)
            print(f"Loaded with encoding={enc}, shape={df.shape}")
            break
        except Exception as e:
            last_err = e
            df = None
    else:
        raise SystemExit(f"读取失败: {last_err}")

    if "nature" not in df.columns:
        raise SystemExit("文件缺少列: nature")

    # 按出现次数排序的类别，用出现次数最高的依次映射为 短线/波段/中长线
    nature_order = df["nature"].value_counts().index.tolist()
    if not nature_order:
        raise SystemExit("nature 列没有可用值")

    mapping_targets = ["short", "swing", "mid"]
    mapping = {}
    for raw, target in zip(nature_order, mapping_targets):
        mapping[raw] = target

    print("类别映射(按出现频次):", mapping)

    for raw, suffix in mapping.items():
        subset = df[df["nature"] == raw]
        out = src.with_name(f"stock_list_{suffix}.csv")
        subset.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"write {out} rows={len(subset)} (raw nature: {raw!r})")


if __name__ == "__main__":
    main()

