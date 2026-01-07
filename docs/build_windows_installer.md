## 目标

在 Windows 上一键生成 **LabelmeAI 安装包（Inno Setup .exe）**，并将 EfficientSAM 的 ONNX 模型 **离线内置**。

## 前置条件

- Python 3.11 x64
- Inno Setup 6（需要 `ISCC.exe`）
- 打包依赖文件：`packaging/windows/requirements-win.txt`

可使用 Chocolatey 安装：

```powershell
choco install innosetup -y
```

## 一键构建（推荐）

在仓库根目录运行：

```powershell
.\packaging\windows\build.ps1
```

如果电脑上还没有安装 Inno Setup，可让脚本尝试自动安装（优先 `winget`，其次 `choco`）：

```powershell
.\packaging\windows\build.ps1 -InstallInnoSetup
```

如需仅“生成安装包”（复用已有 `dist\labelme\`，跳过 PyInstaller 以节省时间）：

```powershell
.\packaging\windows\build.ps1 -SkipPyInstaller
```

如需强制 PyInstaller 清理构建（更慢，但更干净）：

```powershell
.\packaging\windows\build.ps1 -CleanPyInstaller
```

如需加速 Inno Setup 打包（安装包更大，但构建更快）：

```powershell
.\packaging\windows\build.ps1 -CompressionProfile fast
```

默认是体积优先（更慢）：`-CompressionProfile small`

如果你的模型文件在 `C:\dlcv\bin` 以外的位置（例如已有离线模型），传入 `-ModelSourceDir`：

```powershell
.\packaging\windows\build.ps1 -ModelSourceDir "D:\models"
```

如果你不希望脚本联网下载模型（必须从 `-ModelSourceDir` 或默认 `C:\dlcv\bin` 拷贝），使用：

```powershell
.\packaging\windows\build.ps1 -NoDownloadModels -ModelSourceDir "D:\models"
```

> 兼容入口：`.\scripts\build_windows_installer.ps1` 会自动转发到 `.\packaging\windows\build.ps1`（参数保持兼容）。  

## 输出

- PyInstaller 产物：`dist\labelme\`
- 安装包输出：`installer_output\LabelmeAI_Setup_<version>.exe`

