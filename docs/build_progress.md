## LabelmeAI 安装包任务进度记录（本地构建）

更新时间：2026-01-07

### 任务来源

- 论坛任务：`https://bbs2.dlcv.com.cn/t/1682`（做一个独立的 LabelmeAI Windows 安装包，不依赖 dlcv AI 平台环境；AI 模型需离线内置）

### 当前结论（DLL/依赖）

- **不需要手动“把所有 DLL 都打包”**：使用 PyInstaller 会自动收集 Python 三方库的 `*.pyd/*.dll` 到 `dist/` 产物中。
- 运行缺 DLL 时，再按报错补充到 `packaging/windows/labelmeai.spec` 的 `binaries/datas` 或通过 hooks 处理。

### 当前方案（推荐，Windows 打包“零侵入代码”）

- **一键构建**：`packaging/windows/build.ps1`
  - 创建/复用 `.venv`
  - 安装 `packaging/windows/requirements-win.txt`
  - 打包前 **smoke test**：`import labelme.dlcv.app`（缺依赖直接失败）
  - 模型准备：调用 `scripts/prepare_models.py` 将模型拷贝到 `packaging/windows/_assets/models`
  - 运行 `pyinstaller packaging/windows/labelmeai.spec` 生成 `dist/labelme`（onedir）
  - 调用 `ISCC.exe` 编译 `packaging/windows/LabelmeAI.iss` 生成安装包
  - 如电脑未安装 Inno Setup：可加 `-InstallInnoSetup` 让脚本尝试用 `winget/choco` 自动安装
- **PyInstaller 入口**：`packaging/windows/entrypoint.py`
  - 运行时 monkeypatch `onnxruntime.InferenceSession`：当传入硬编码路径不存在（如新机无 `C:/dlcv/bin/*.onnx`）时，自动回退到安装包内置 `models/<basename>.onnx`。
- **兼容入口**：`scripts/build_windows_installer.ps1` 仅做转发（避免旧流程误用）。

> 备注：早期曾尝试在 `labelme/` 目录内做模型路径/离线下载等改动；你已回滚这些修改，目前以 `packaging/windows/` 作为唯一稳定打包入口。

### 构建过程中的问题与处理

#### onnxruntime DLL 初始化失败（已解决）

- 现象：`ImportError: DLL load failed while importing onnxruntime_pybind11_state: ... (WinError 1114)`，导致 PyInstaller 在解析 `osam` 时崩溃。
- 处理：对 Windows 构建依赖做版本 pin：
  - `onnxruntime==1.17.3`
  - `numpy==1.26.4`
  - `opencv-python==4.10.0.84`
- 以上已写入：`packaging/windows/requirements-win.txt`

### 当前产物状态

- **PyInstaller 产物已生成**：`dist/labelme/`
  - 可执行文件：`dist/labelme/labelme.exe`
  - 依赖目录：`dist/labelme/_internal/`（大量 `dll/pyd/qt` 资源）
- **安装包产物已生成**：`installer_output/LabelmeAI_Setup_2026.01.06.0a0.exe`

### 额外记录（Inno Setup）

- 已通过 Chocolatey 安装 Inno Setup：`choco install innosetup -y`
- 发现直接输出到 repo 目录时，ISCC 可能在 “Updating icons (Setup.exe)” 阶段遇到文件占用错误；已在构建脚本中改为**先输出到临时目录再拷贝**。

### 下一步（建议）

- 在“干净环境/未安装 Python 的机器”上验证安装包：安装、启动、基础标注、AI 标注（EfficientSAM）是否正常。

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\packaging\windows\build.ps1
```

如需手动指定 ISCC 路径：

```powershell
.\packaging\windows\build.ps1 -ISCC "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```


## 2026-01-07 新电脑测试反馈问题（已解决）

### 问题 1：修复 jaraco 后又出现 “No module named shapely”

- **现象**：在干净电脑运行安装包后，启动报 `ModuleNotFoundError: No module named 'shapely'`。
- **原因（高概率）**：
  - 代码中有 `shapely` 的直接/间接引用（例如 `labelme/dlcv/app.py`、`labelme/dlcv/canvas.py`、`labelme/dlcv/shape.py` 等），但构建环境或打包配置未把 `shapely` 作为必需依赖安装/收集，导致 PyInstaller 产物中缺失。
  - 这类问题的本质是：**打包环境的依赖集合 ≠ 运行时真实依赖集合**，缺了就会在“新电脑”暴露出来。
- **解决（已实现）**：
  - **补齐依赖**：在 `packaging/windows/requirements-win.txt` 固定加入 `shapely==2.0.3`，并补齐 `nvidia-ml-py`（提供 `import pynvml`）。
  - **收集兜底**：PyInstaller 使用 `packaging/windows/hooks/hook-shapely.py`，确保 shapely/GEOS 相关二进制被收集进冻结产物。
  - **打包前自检**：`packaging/windows/build.ps1` 在 PyInstaller 之前执行 `python -c "import labelme.dlcv.app"`，缺依赖会在打包阶段直接失败。

### 问题 2：打包很慢（14 代 i7 也要 ~10 分钟）

- **现象**：全量打包耗时很长，影响迭代效率。
- **原因拆解（常见瓶颈）**：
  - **PyInstaller 分析/收集阶段**：项目依赖大（PyQt5、open3d、dash/plotly/ipywidgets、scipy、onnxruntime…），模块图分析 + 拷贝/重分类会很慢。
  - **Inno Setup 压缩阶段**：`dist/labelme/_internal` 文件数多、体积大，默认 `lzma2` 压缩会显著耗时。
  - **每次都 clean**：如果每次都 `--clean` 会丢缓存，重复工作明显。
- **解决（已实现）**：
  - **复用 dist**：`-SkipPyInstaller` 仅跑 Inno Setup，迭代时最快。
  - **压缩档位**：`-CompressionProfile fast|small`（fast 更快但更大；small 默认体积优先更慢）。

### 问题 3：希望打包流程“零侵入原有代码”

- **现象**：当前为了离线模型与路径适配，对 `labelme/` 下代码做了较大改动；你希望“打包不改原代码”，最好把打包逻辑放到独立目录。
- **目标**：把“打包/离线模型/路径修正/依赖补齐”等逻辑迁移到单独的 `packaging/` 目录，通过 **wrapper/集成/复用** 达到同样效果。
- **约束与挑战**：
  - 若原代码硬编码了模型路径（例如 `C:/dlcv/bin/...`）或依赖在线下载逻辑，想做到“零侵入”通常需要 **运行时 monkeypatch / wrapper 入口**，由 wrapper 在启动前注入路径、替换类/函数或替换模块引用。

- **解决（已实现）**：
  - **独立 packaging 目录**：Windows 打包相关文件迁移到 `packaging/windows/`（requirements/build/spec/iss/hooks）。
  - **wrapper 入口**：PyInstaller 入口使用 `packaging/windows/entrypoint.py`（不改 `labelme/` 源码）。
  - **硬编码模型路径兼容**：`entrypoint.py` monkeypatch `onnxruntime.InferenceSession`：当传入模型路径不存在（例如新机没有 `C:/dlcv/bin/*.onnx`）时，自动回退到内置 `models/<basename>.onnx`。
  - **模型来源（打包机）**：`packaging/windows/build.ps1` 默认优先从 `C:\dlcv\bin`（或 `-ModelSourceDir`）拷贝模型到 `packaging/windows/_assets/models`，再打入安装包。

## 2026-01-07 本次落地（已实现）

- **核心文件**：
  - `packaging/windows/build.ps1`：一键构建（venv/依赖安装/模型准备/PyInstaller/Inno Setup）
  - `packaging/windows/requirements-win.txt`：Windows 打包依赖（包含 shapely）
  - `packaging/windows/labelmeai.spec`：PyInstaller onedir spec（入口为 entrypoint；使用 `SPECPATH` 解析路径，避免工作目录变化导致 entrypoint 找不到）
  - `packaging/windows/entrypoint.py`：wrapper 入口（模型目录定位 + onnxruntime 路径兜底）
  - `packaging/windows/hooks/hook-shapely.py`：shapely 收集兜底
  - `packaging/windows/LabelmeAI.iss`：Inno Setup（支持 `CompressionProfile`）
  - `scripts/build_windows_installer.ps1`：兼容入口，自动转发到 `packaging/windows/build.ps1`

- **额外修复点**：
  - `packaging/windows/build.ps1` 已对外部命令使用 `$LASTEXITCODE` 做失败检查：smoke test / pyinstaller / ISCC 任一步失败会立即停止，不会“报错后继续往下跑”。
