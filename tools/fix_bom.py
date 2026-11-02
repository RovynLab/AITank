"""检测并去掉 AITank 仓库所有 .py 文件的 UTF-8 BOM"""
import os

LOCAL = r"e:\work\AITank"
fixed = 0
bom_files = []

for root, dirs, files in os.walk(LOCAL):
    # 跳过这些目录
    dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "tools", ".venv"}]
    for fn in files:
        if not fn.endswith(".py"):
            continue
        fp = os.path.join(root, fn)
        try:
            with open(fp, "rb") as f:
                data = f.read()
            if data.startswith(b"\xef\xbb\xbf"):
                bom_files.append(os.path.relpath(fp, LOCAL))
                # 去 BOM 重写
                with open(fp, "wb") as f:
                    f.write(data[3:])
                fixed += 1
        except Exception as e:
            print(f"ERR {fp}: {e}")

print(f"检测到 {len(bom_files)} 个 BOM 文件, 修复了 {fixed} 个:")
for f in bom_files:
    print(f"  🟢 {f}")
