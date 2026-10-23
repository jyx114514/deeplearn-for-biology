# 可迁移的章节数据下载工具

## 一键下载、续传并验证

在本目录打开 PowerShell，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\download_datasets.ps1
```

默认下载第 3、4、6 章全部 43 个文件，到脚本所在目录，按章节归类。第 7 章没有独立数据集。重复执行会跳过大小正确的已完成文件，续传未完成的分段，最后验证数据并生成 COMPLETE.txt。

run_download_and_verify.ps1 是同一功能的兼容入口，也可使用上述命令，只需替换脚本名。

## 迁移到另一文件夹或电脑

1. 复制工具包内的脚本、download_manifest.json 和 source_urls.txt。不要把旧 COMPLETE.txt 或日志当作新目录的完成证明。
2. 如需保留已有数据/续传进度，一起复制 chapter_03_dna、chapter_04_graphs、chapter_06_localization 整个文件夹。复制前停止旧下载进程。
3. 在新位置运行相同命令。目录名称可修改，清单使用相对路径，不依赖原盘符。
4. Python 会从脚本目录向上查找 .venv\Scripts\python.exe；找不到时按项目约定尝试 D:\Python3.11\python.exe。找到的解释器无法启动会直接报错，不切换或安装环境。在其他电脑建议显式传 -PythonExe。

不要直接复制 Windows 虚拟环境到另一台电脑；指定目标电脑上已有的可用解释器。工具只要求 Python 3.10+，下载仅用标准库；第 6 章内容验证还需要 NumPy。脚本不会安装任何包。ogb 保留供后续训练代码使用，下载器本身不依赖它。

## 可选参数

```powershell
# 指定现有解释器和另一个数据存储目录（示例路径请替换）
.\download_datasets.ps1 -PythonExe 'C:\myenv\Scripts\python.exe' -Destination 'E:\biology_data'

# 只处理第 3、4 章；PowerShell 中多章使用逗号
.\download_datasets.ps1 -Chapters 3,4

# 下载全部，不进行内容验证；无需 NumPy，不生成 COMPLETE.txt
.\download_datasets.ps1 -DownloadOnly

# 只验证现有数据，不请求网络
.\download_datasets.ps1 -VerifyOnly

# 修改并行连接数和每段重试次数
.\download_datasets.ps1 -Workers 4 -Retries 10
```

也可直接通过现有 Python 解释器运行 dataset_tools.py，使用 --destination、--manifest、--chapters 3 4、--workers、--retries、--verify-only、--download-only 等参数；适用于 Windows、Linux 和 macOS。Python 参数 --chapters 后的章节用空格分隔。

## 文件作用

- download_datasets.ps1：统一 Windows 入口，定位 Python、传递参数。
- run_download_and_verify.ps1：统一入口的兼容别名，参数相同。
- dataset_tools.py：下载、断点续传、加锁和验证的核心。
- download_images_parallel.py：旧入口，默认只下载/续传第 6 章（包括标签），不验证。
- verify_datasets.py：旧入口，默认只验证全部数据。
- download_manifest.json：固定的 43 文件下载清单，路径相对于数据目录；也兼容旧的绝对路径清单。
- source_urls.txt：取自作者服务器的完整原始清单；只有 manifest 中选定的数据会下载，不下载模型。
- test_transfer.py：离线回归测试，通过本机 HTTP 服务验证新下载、迁移路径、两种续传、重复执行和文件锁。

## 断点续传

发生中断后重新运行同一命令。完成的分段不会重下；中断时尚未记为完成的分段会重新下载。旧的 .part 顺序下载文件和原第 6 章 prefix/done 分段记录均兼容。

必须一起保留对应的 `.parallel.part` 和 `.ranges.json`；不要依据预分配的 `.parallel.part` 文件大小判断进度。分段大小固定为 32 MiB；进度文件会记录 URL、总字节数及分段大小，新下载器会检查是否匹配。

同一数据目录只允许一个新下载/验证进程运行。`.download.lock` 文件可以保留，系统锁在进程退出后自动释放。不要同时运行旧脚本副本。

## 数据和校验

- chapter_03_dna：30 个 CSV，约 80.16 MB。核对清单大小、字段、200bp ACGT 序列和二值标签。
- chapter_04_graphs：ogbl_ddi 完整目录，约 102.15 MB。核对全部文件大小及 gzip CRC；ogb 的 root 应指向 chapter_04_graphs。
- chapter_06_localization：images.npy + labels.npy，约 45.42 GB。核对文件大小、图像/标签数量和抽样像素有限性。

第 6 章 images.npy 实际是 float32 原始内存映射，形状 (-1, 100, 100, 1)，用 numpy.memmap 读取。labels.npy 是作者提供的含对象数组的 NumPy 文件，按原实现使用 allow_pickle=True，包含 7 列元数据。

这些校验不等同于逐字节密码学哈希校验；作者清单未提供 SHA256。完整验证覆盖所需全部章节时才写入 COMPLETE.txt，失败或只下载时不写完成标记。运行会移除旧完成标记，防止旧标记掩盖本次失败。

来源：https://assets.deep-learning-for-biology.com/urls.txt
当前清单为 2026-10-22 获取的固定快照。默认离线读取随包清单，不静默追随上游变更。如需使用其他清单，传 -Manifest 或 --manifest。
